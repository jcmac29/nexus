"""Business logic for memory management."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.memory.embeddings import extract_text_from_value, generate_embedding
from nexus.memory.models import Memory, MemoryScope, MemoryShare


class MemoryService:
    """Service for managing agent memories."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def store(
        self,
        agent_id: UUID,
        key: str,
        value: dict,
        namespace: str = "default",
        scope: str = "agent",
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        text_content: str | None = None,
        expires_in_seconds: int | None = None,
    ) -> Memory:
        """Store or update a memory."""
        # Check for existing memory with same key
        existing = await self.get_by_key(
            agent_id=agent_id,
            key=key,
            namespace=namespace,
            user_id=user_id,
            session_id=session_id,
        )

        # Extract text for embedding
        text_for_embedding = text_content or extract_text_from_value(value)
        embedding = generate_embedding(text_for_embedding)

        # Calculate expiration
        expires_at = None
        if expires_in_seconds:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)

        if existing:
            # Update existing memory
            existing.value = value
            existing.text_content = text_for_embedding
            existing.embedding = embedding
            existing.scope = MemoryScope(scope)
            existing.tags = tags or []
            existing.expires_at = expires_at
            existing.updated_at = datetime.now(timezone.utc)
            return existing
        else:
            # Create new memory
            memory = Memory(
                agent_id=agent_id,
                key=key,
                value=value,
                namespace=namespace,
                scope=MemoryScope(scope),
                user_id=user_id,
                session_id=session_id,
                tags=tags or [],
                text_content=text_for_embedding,
                embedding=embedding,
                expires_at=expires_at,
            )
            self.db.add(memory)
            await self.db.flush()
            return memory

    async def get_by_key(
        self,
        agent_id: UUID,
        key: str,
        namespace: str = "default",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> Memory | None:
        """Get a memory by key."""
        query = select(Memory).where(
            Memory.agent_id == agent_id,
            Memory.key == key,
            Memory.namespace == namespace,
        )

        if user_id:
            query = query.where(Memory.user_id == user_id)
        if session_id:
            query = query.where(Memory.session_id == session_id)

        # Exclude expired memories
        query = query.where(
            or_(Memory.expires_at.is_(None), Memory.expires_at > datetime.now(timezone.utc))
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id(self, memory_id: UUID, agent_id: UUID) -> Memory | None:
        """Get a memory by ID (must belong to agent or be shared with them)."""
        # First check if agent owns it
        result = await self.db.execute(
            select(Memory).where(
                Memory.id == memory_id,
                Memory.agent_id == agent_id,
                or_(Memory.expires_at.is_(None), Memory.expires_at > datetime.now(timezone.utc)),
            )
        )
        memory = result.scalar_one_or_none()
        if memory:
            return memory

        # Check if it's shared with this agent
        result = await self.db.execute(
            select(Memory)
            .join(MemoryShare)
            .where(
                Memory.id == memory_id,
                MemoryShare.shared_with_agent_id == agent_id,
                or_(Memory.expires_at.is_(None), Memory.expires_at > datetime.now(timezone.utc)),
            )
        )
        return result.scalar_one_or_none()

    async def list_memories(
        self,
        agent_id: UUID,
        namespace: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Memory]:
        """List memories for an agent."""
        query = select(Memory).where(
            Memory.agent_id == agent_id,
            or_(Memory.expires_at.is_(None), Memory.expires_at > datetime.now(timezone.utc)),
        )

        if namespace:
            query = query.where(Memory.namespace == namespace)
        if user_id:
            query = query.where(Memory.user_id == user_id)
        if session_id:
            query = query.where(Memory.session_id == session_id)
        if tags:
            query = query.where(Memory.tags.overlap(tags))

        query = query.order_by(Memory.updated_at.desc()).limit(limit).offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search(
        self,
        agent_id: UUID,
        query: str,
        namespace: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
        include_shared: bool = True,
    ) -> list[tuple[Memory, float, UUID | None]]:
        """
        Semantic search for memories.

        Returns list of (Memory, score, owner_agent_id or None if owned)
        """
        # Generate query embedding
        query_embedding = generate_embedding(query)

        # Build base conditions
        base_conditions = [
            or_(Memory.expires_at.is_(None), Memory.expires_at > datetime.now(timezone.utc)),
            Memory.embedding.isnot(None),
        ]

        if namespace:
            base_conditions.append(Memory.namespace == namespace)
        if user_id:
            base_conditions.append(Memory.user_id == user_id)
        if session_id:
            base_conditions.append(Memory.session_id == session_id)
        if tags:
            base_conditions.append(Memory.tags.overlap(tags))

        results: list[tuple[Memory, float, UUID | None]] = []

        # Search own memories
        own_query = (
            select(
                Memory,
                Memory.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .where(Memory.agent_id == agent_id, *base_conditions)
            .order_by("distance")
            .limit(limit)
        )

        own_result = await self.db.execute(own_query)
        for memory, distance in own_result.all():
            score = 1 - distance  # Convert distance to similarity
            results.append((memory, score, None))

        # Search shared memories
        if include_shared:
            shared_query = (
                select(
                    Memory,
                    Memory.embedding.cosine_distance(query_embedding).label("distance"),
                )
                .join(MemoryShare)
                .where(MemoryShare.shared_with_agent_id == agent_id, *base_conditions)
                .order_by("distance")
                .limit(limit)
            )

            shared_result = await self.db.execute(shared_query)
            for memory, distance in shared_result.all():
                score = 1 - distance
                results.append((memory, score, memory.agent_id))

        # Sort combined results by score and limit
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    async def delete(self, memory_id: UUID, agent_id: UUID) -> bool:
        """Delete a memory (must be owned by the agent)."""
        result = await self.db.execute(
            delete(Memory).where(Memory.id == memory_id, Memory.agent_id == agent_id)
        )
        return result.rowcount > 0

    async def delete_by_key(
        self,
        agent_id: UUID,
        key: str,
        namespace: str = "default",
    ) -> bool:
        """Delete a memory by key."""
        result = await self.db.execute(
            delete(Memory).where(
                Memory.agent_id == agent_id,
                Memory.key == key,
                Memory.namespace == namespace,
            )
        )
        return result.rowcount > 0

    # --- Sharing Methods ---

    async def share(
        self,
        memory_id: UUID,
        owner_agent_id: UUID,
        share_with_agent_id: UUID,
        permissions: list[str] | None = None,
    ) -> MemoryShare | None:
        """Share a memory with another agent."""
        # Verify memory exists and is owned by the agent
        memory = await self.get_by_key_id_owned(memory_id, owner_agent_id)
        if not memory:
            return None

        # Check for existing share
        result = await self.db.execute(
            select(MemoryShare).where(
                MemoryShare.memory_id == memory_id,
                MemoryShare.shared_with_agent_id == share_with_agent_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update permissions
            existing.permissions = permissions or ["read"]
            return existing
        else:
            # Create new share
            share = MemoryShare(
                memory_id=memory_id,
                shared_with_agent_id=share_with_agent_id,
                permissions=permissions or ["read"],
            )
            self.db.add(share)
            await self.db.flush()
            return share

    async def revoke_share(
        self,
        memory_id: UUID,
        owner_agent_id: UUID,
        share_with_agent_id: UUID,
    ) -> bool:
        """Revoke a memory share."""
        # Verify ownership
        memory = await self.get_by_key_id_owned(memory_id, owner_agent_id)
        if not memory:
            return False

        result = await self.db.execute(
            delete(MemoryShare).where(
                MemoryShare.memory_id == memory_id,
                MemoryShare.shared_with_agent_id == share_with_agent_id,
            )
        )
        return result.rowcount > 0

    async def get_by_key_id_owned(self, memory_id: UUID, agent_id: UUID) -> Memory | None:
        """Get a memory by ID, only if owned by the agent."""
        result = await self.db.execute(
            select(Memory).where(Memory.id == memory_id, Memory.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def list_shares(self, memory_id: UUID, agent_id: UUID) -> list[MemoryShare]:
        """List all shares for a memory (must be owned by agent)."""
        memory = await self.get_by_key_id_owned(memory_id, agent_id)
        if not memory:
            return []

        result = await self.db.execute(
            select(MemoryShare).where(MemoryShare.memory_id == memory_id)
        )
        return list(result.scalars().all())
