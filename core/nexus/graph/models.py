"""Database models for graph relationships."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus.database import Base


class NodeType(str, enum.Enum):
    """Types of nodes that can participate in relationships."""

    MEMORY = "memory"
    AGENT = "agent"
    CAPABILITY = "capability"


class RelationshipType(str, enum.Enum):
    """Types of relationships between nodes."""

    REFERENCES = "references"  # Memory A references Memory B
    DERIVED_FROM = "derived_from"  # Memory A was created from Memory B
    RELATED_TO = "related_to"  # General association
    SUPERSEDES = "supersedes"  # Memory A replaces Memory B
    SIMILAR_TO = "similar_to"  # Embedding-based similarity
    REPLY_TO = "reply_to"  # Conversation threading
    DEPENDS_ON = "depends_on"  # Capability depends on another
    OWNS = "owns"  # Agent owns Memory/Capability
    SHARED_WITH = "shared_with"  # Memory shared with Agent


class MemoryRelationship(Base):
    """
    An edge in the memory graph.

    Represents a directional relationship between two nodes (memories, agents, or capabilities).
    """

    __tablename__ = "memory_relationships"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source_type: Mapped[NodeType] = mapped_column(
        Enum(NodeType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    target_type: Mapped[NodeType] = mapped_column(
        Enum(NodeType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    target_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    weight: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        server_default="1.0",
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default="{}",
    )
    created_by_agent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_relationships_source", "source_type", "source_id"),
        Index("ix_relationships_target", "target_type", "target_id"),
        Index("ix_relationships_type", "relationship_type"),
        UniqueConstraint(
            "source_type",
            "source_id",
            "target_type",
            "target_id",
            "relationship_type",
            name="uq_relationship_edge",
        ),
    )

    def __repr__(self) -> str:
        return f"<MemoryRelationship {self.source_type}:{self.source_id} -[{self.relationship_type}]-> {self.target_type}:{self.target_id}>"
