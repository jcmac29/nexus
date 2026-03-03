"""Business logic for identity management."""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.config import get_settings
from nexus.identity.models import Agent, AgentStatus, APIKey

settings = get_settings()


class IdentityService:
    """Service for managing agent identities and API keys."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Agent Methods ---

    async def create_agent(
        self,
        name: str,
        slug: str,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> tuple[Agent, str]:
        """
        Create a new agent and generate initial API key.

        Returns:
            Tuple of (Agent, api_key_string)
        """
        agent = Agent(
            name=name,
            slug=slug,
            description=description,
            metadata_=metadata or {},
        )
        self.db.add(agent)
        await self.db.flush()  # Get the agent ID

        # Create initial API key
        api_key_string = await self._create_api_key_for_agent(
            agent_id=agent.id,
            name="default",
            scopes=["read", "write", "share", "discover"],
        )

        return agent, api_key_string

    async def get_agent_by_id(self, agent_id: UUID) -> Agent | None:
        """Get an agent by ID."""
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.status != AgentStatus.DELETED)
        )
        return result.scalar_one_or_none()

    async def get_agent_by_slug(self, slug: str) -> Agent | None:
        """Get an agent by slug."""
        result = await self.db.execute(
            select(Agent).where(Agent.slug == slug, Agent.status != AgentStatus.DELETED)
        )
        return result.scalar_one_or_none()

    async def update_agent(
        self,
        agent: Agent,
        name: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> Agent:
        """Update an agent's details."""
        if name is not None:
            agent.name = name
        if description is not None:
            agent.description = description
        if metadata is not None:
            agent.metadata_ = metadata
        agent.updated_at = datetime.now(timezone.utc)
        return agent

    async def delete_agent(self, agent: Agent) -> None:
        """Soft delete an agent."""
        agent.status = AgentStatus.DELETED
        agent.updated_at = datetime.now(timezone.utc)

    # --- API Key Methods ---

    async def create_api_key(
        self,
        agent_id: UUID,
        name: str = "default",
        scopes: list[str] | None = None,
        expires_in_days: int | None = None,
    ) -> tuple[APIKey, str]:
        """
        Create a new API key for an agent.

        Returns:
            Tuple of (APIKey, api_key_string)
        """
        api_key_string = await self._create_api_key_for_agent(
            agent_id=agent_id,
            name=name,
            scopes=scopes or ["read", "write"],
            expires_in_days=expires_in_days,
        )

        # Get the created key
        result = await self.db.execute(
            select(APIKey)
            .where(APIKey.agent_id == agent_id)
            .order_by(APIKey.created_at.desc())
            .limit(1)
        )
        api_key = result.scalar_one()

        return api_key, api_key_string

    async def _create_api_key_for_agent(
        self,
        agent_id: UUID,
        name: str,
        scopes: list[str],
        expires_in_days: int | None = None,
    ) -> str:
        """Internal method to create an API key."""
        # Generate a secure random key
        raw_key = secrets.token_urlsafe(32)
        full_key = f"{settings.api_key_prefix}{raw_key}"

        # Hash the key for storage
        key_hash = bcrypt.hashpw(full_key.encode(), bcrypt.gensalt()).decode()

        # Create prefix for display (first 12 chars after prefix)
        key_prefix = f"{settings.api_key_prefix}{raw_key[:8]}..."

        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        api_key = APIKey(
            agent_id=agent_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            scopes=scopes,
            expires_at=expires_at,
        )
        self.db.add(api_key)

        return full_key

    async def verify_api_key(self, api_key_string: str) -> Agent | None:
        """
        Verify an API key and return the associated agent.

        Returns:
            Agent if key is valid, None otherwise
        """
        if not api_key_string.startswith(settings.api_key_prefix):
            return None

        # Get all active API keys (we need to check against hashes)
        result = await self.db.execute(
            select(APIKey, Agent)
            .join(Agent)
            .where(
                Agent.status == AgentStatus.ACTIVE,
            )
        )

        for api_key, agent in result.all():
            # Check if key matches hash
            if bcrypt.checkpw(api_key_string.encode(), api_key.key_hash.encode()):
                # Check expiration
                if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
                    return None

                # Update last used
                api_key.last_used_at = datetime.now(timezone.utc)
                return agent

        return None

    async def list_api_keys(self, agent_id: UUID) -> list[APIKey]:
        """List all API keys for an agent."""
        result = await self.db.execute(
            select(APIKey)
            .where(APIKey.agent_id == agent_id)
            .order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_api_key(self, agent_id: UUID, key_id: UUID) -> bool:
        """Revoke (delete) an API key."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id, APIKey.agent_id == agent_id)
        )
        api_key = result.scalar_one_or_none()

        if api_key:
            await self.db.delete(api_key)
            return True
        return False

    async def rotate_api_key(
        self,
        agent_id: UUID,
        old_key_id: UUID,
        new_name: str | None = None,
        new_scopes: list[str] | None = None,
        expires_in_days: int | None = None,
    ) -> tuple[APIKey, str]:
        """
        Rotate an API key - creates new key and revokes old one atomically.

        Returns:
            Tuple of (new APIKey, new api_key_string)
        """
        # Get old key to copy settings
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == old_key_id, APIKey.agent_id == agent_id)
        )
        old_key = result.scalar_one_or_none()

        if not old_key:
            raise ValueError("API key not found")

        # Use old key settings as defaults
        name = new_name or f"{old_key.name} (rotated)"
        scopes = new_scopes or old_key.scopes

        # Create new key
        new_api_key, api_key_string = await self.create_api_key(
            agent_id=agent_id,
            name=name,
            scopes=scopes,
            expires_in_days=expires_in_days,
        )

        # Revoke old key
        await self.db.delete(old_key)

        return new_api_key, api_key_string

    async def get_api_key_by_id(self, agent_id: UUID, key_id: UUID) -> APIKey | None:
        """Get a specific API key."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id, APIKey.agent_id == agent_id)
        )
        return result.scalar_one_or_none()
