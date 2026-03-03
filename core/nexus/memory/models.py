"""Database models for memory storage."""

import enum
from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.config import get_settings
from nexus.database import Base

settings = get_settings()


class MemoryScope(str, enum.Enum):
    """Memory scope enumeration."""

    AGENT = "agent"  # Private to the agent
    USER = "user"  # Scoped to a specific user
    SESSION = "session"  # Scoped to a specific session
    SHARED = "shared"  # Explicitly shared with other agents


class Memory(Base):
    """A memory stored by an agent."""

    __tablename__ = "memories"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    agent_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    namespace: Mapped[str] = mapped_column(String(255), default="default", index=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)  # For embedding
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimension),
        nullable=True,
    )
    scope: Mapped[MemoryScope] = mapped_column(
        Enum(MemoryScope, values_callable=lambda x: [e.value for e in x]),
        default=MemoryScope.AGENT,
        server_default="agent",
    )
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=[], server_default="{}")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    shares: Mapped[list["MemoryShare"]] = relationship(
        "MemoryShare",
        back_populates="memory",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_memories_agent_namespace_key", "agent_id", "namespace", "key"),
        Index(
            "ix_memories_agent_user_session",
            "agent_id",
            "user_id",
            "session_id",
        ),
    )

    def __repr__(self) -> str:
        return f"<Memory {self.namespace}:{self.key}>"


class MemoryShare(Base):
    """A share grant for a memory to another agent."""

    __tablename__ = "memory_shares"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    memory_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shared_with_agent_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        default=["read"],
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    memory: Mapped["Memory"] = relationship("Memory", back_populates="shares")

    __table_args__ = (
        Index("ix_memory_shares_unique", "memory_id", "shared_with_agent_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<MemoryShare {self.memory_id} -> {self.shared_with_agent_id}>"
