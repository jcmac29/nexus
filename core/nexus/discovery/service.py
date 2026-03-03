"""Business logic for capability discovery."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.discovery.models import Capability, CapabilityStatus
from nexus.identity.models import Agent, AgentStatus
from nexus.memory.embeddings import generate_embedding


class DiscoveryService:
    """Service for managing and discovering capabilities."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def register_capability(
        self,
        agent_id: UUID,
        name: str,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        endpoint_url: str | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        metadata: dict | None = None,
    ) -> Capability:
        """Register or update a capability for an agent."""
        # Check for existing capability
        existing = await self.get_capability_by_name(agent_id, name)

        # Generate embedding from name + description
        text_for_embedding = name
        if description:
            text_for_embedding = f"{name}: {description}"
        embedding = generate_embedding(text_for_embedding)

        if existing:
            # Update existing
            existing.description = description
            existing.category = category
            existing.tags = tags or []
            existing.endpoint_url = endpoint_url
            existing.input_schema = input_schema
            existing.output_schema = output_schema
            existing.metadata_ = metadata or {}
            existing.embedding = embedding
            existing.status = CapabilityStatus.ACTIVE
            existing.updated_at = datetime.now(timezone.utc)
            return existing
        else:
            # Create new
            capability = Capability(
                agent_id=agent_id,
                name=name,
                description=description,
                category=category,
                tags=tags or [],
                endpoint_url=endpoint_url,
                input_schema=input_schema,
                output_schema=output_schema,
                metadata_=metadata or {},
                embedding=embedding,
            )
            self.db.add(capability)
            await self.db.flush()
            return capability

    async def get_capability_by_name(self, agent_id: UUID, name: str) -> Capability | None:
        """Get a capability by agent ID and name."""
        result = await self.db.execute(
            select(Capability).where(
                Capability.agent_id == agent_id,
                Capability.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def list_agent_capabilities(self, agent_id: UUID) -> list[Capability]:
        """List all capabilities for an agent."""
        result = await self.db.execute(
            select(Capability)
            .where(
                Capability.agent_id == agent_id,
                Capability.status == CapabilityStatus.ACTIVE,
            )
            .order_by(Capability.name)
        )
        return list(result.scalars().all())

    async def update_capability(
        self,
        agent_id: UUID,
        name: str,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        endpoint_url: str | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        metadata: dict | None = None,
        status: str | None = None,
    ) -> Capability | None:
        """Update a capability."""
        capability = await self.get_capability_by_name(agent_id, name)
        if not capability:
            return None

        if description is not None:
            capability.description = description
            # Re-generate embedding
            text = f"{name}: {description}" if description else name
            capability.embedding = generate_embedding(text)

        if category is not None:
            capability.category = category
        if tags is not None:
            capability.tags = tags
        if endpoint_url is not None:
            capability.endpoint_url = endpoint_url
        if input_schema is not None:
            capability.input_schema = input_schema
        if output_schema is not None:
            capability.output_schema = output_schema
        if metadata is not None:
            capability.metadata_ = metadata
        if status is not None:
            capability.status = CapabilityStatus(status)

        capability.updated_at = datetime.now(timezone.utc)
        return capability

    async def delete_capability(self, agent_id: UUID, name: str) -> bool:
        """Delete a capability."""
        result = await self.db.execute(
            delete(Capability).where(
                Capability.agent_id == agent_id,
                Capability.name == name,
            )
        )
        return result.rowcount > 0

    async def discover(
        self,
        query: str | None = None,
        name: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[tuple[Capability, Agent, float | None]]:
        """
        Discover capabilities across all agents.

        Returns list of (Capability, Agent, score or None)
        """
        base_conditions = [
            Capability.status == CapabilityStatus.ACTIVE,
            Agent.status == AgentStatus.ACTIVE,
        ]

        if name:
            base_conditions.append(Capability.name == name)
        if category:
            base_conditions.append(Capability.category == category)
        if tags:
            # Check if any tag matches
            base_conditions.append(
                or_(*[Capability.tags.contains([tag]) for tag in tags])
            )

        if query:
            # Semantic search
            query_embedding = generate_embedding(query)

            stmt = (
                select(
                    Capability,
                    Agent,
                    Capability.embedding.cosine_distance(query_embedding).label("distance"),
                )
                .join(Agent, Capability.agent_id == Agent.id)
                .where(*base_conditions, Capability.embedding.isnot(None))
                .order_by("distance")
                .limit(limit)
            )

            result = await self.db.execute(stmt)
            return [
                (cap, agent, 1 - dist)  # Convert distance to similarity
                for cap, agent, dist in result.all()
            ]
        else:
            # Non-semantic search
            stmt = (
                select(Capability, Agent)
                .join(Agent, Capability.agent_id == Agent.id)
                .where(*base_conditions)
                .order_by(Capability.name)
                .limit(limit)
            )

            result = await self.db.execute(stmt)
            return [(cap, agent, None) for cap, agent in result.all()]

    async def get_agent_with_capabilities(
        self, agent_id: UUID
    ) -> tuple[Agent, list[Capability]] | None:
        """Get an agent and all their active capabilities."""
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.status == AgentStatus.ACTIVE)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            return None

        capabilities = await self.list_agent_capabilities(agent_id)
        return agent, capabilities
