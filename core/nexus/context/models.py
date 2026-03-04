"""Context database models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base

if TYPE_CHECKING:
    from nexus.identity.models import Agent


class ContextPackage(Base):
    """A packaged context ready for transfer."""

    __tablename__ = "context_packages"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # Package identification
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, default=1)
    checksum: Mapped[str | None] = mapped_column(String(64))  # SHA-256

    # Content
    summary: Mapped[str | None] = mapped_column(Text)

    # Structured context
    goals: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    memories: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    conversation_history: Mapped[list | None] = mapped_column(JSONB, default=list)
    reasoning_trace: Mapped[list | None] = mapped_column(JSONB, default=list)
    decisions_made: Mapped[list | None] = mapped_column(JSONB, default=list)
    constraints: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    preferences: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Metadata
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    # Access control
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_agents: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Expiration
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owner: Mapped["Agent"] = relationship("Agent")

    __table_args__ = (
        Index("ix_context_packages_owner_name", "owner_agent_id", "name"),
    )


class TransferStatus(str, enum.Enum):
    """Status of a context transfer."""

    INITIATED = "initiated"
    SENT = "sent"
    RECEIVED = "received"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"


class ContextTransfer(Base):
    """A transfer of context between agents."""

    __tablename__ = "context_transfers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    package_id: Mapped[UUID] = mapped_column(ForeignKey("context_packages.id"), index=True)

    # Participants
    sender_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    receiver_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # Transfer details
    purpose: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)

    # Status
    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus), default=TransferStatus.INITIATED
    )
    status_message: Mapped[str | None] = mapped_column(Text)

    # Diff information (what changed)
    diff_summary: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Timestamps
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Related entities
    related_goal_id: Mapped[UUID | None] = mapped_column()
    related_task_id: Mapped[UUID | None] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    package: Mapped["ContextPackage"] = relationship("ContextPackage")
    sender: Mapped["Agent"] = relationship("Agent", foreign_keys=[sender_id])
    receiver: Mapped["Agent"] = relationship("Agent", foreign_keys=[receiver_id])

    __table_args__ = (
        Index("ix_context_transfers_receiver_status", "receiver_id", "status"),
        Index("ix_context_transfers_sender", "sender_id"),
    )
