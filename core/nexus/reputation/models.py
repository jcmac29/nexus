"""Reputation database models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base

if TYPE_CHECKING:
    from nexus.identity.models import Agent


class ReputationScore(Base):
    """Aggregated reputation score for an agent."""

    __tablename__ = "reputation_scores"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id"), unique=True, index=True
    )

    # Core scores (0.0 - 1.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.5)
    reliability_score: Mapped[float] = mapped_column(Float, default=0.5)
    quality_score: Mapped[float] = mapped_column(Float, default=0.5)
    responsiveness_score: Mapped[float] = mapped_column(Float, default=0.5)
    collaboration_score: Mapped[float] = mapped_column(Float, default=0.5)

    # Statistics
    total_interactions: Mapped[int] = mapped_column(Integer, default=0)
    successful_interactions: Mapped[int] = mapped_column(Integer, default=0)
    vouches_received: Mapped[int] = mapped_column(Integer, default=0)
    vouches_given: Mapped[int] = mapped_column(Integer, default=0)
    disputes_received: Mapped[int] = mapped_column(Integer, default=0)
    disputes_resolved: Mapped[int] = mapped_column(Integer, default=0)

    # Tier
    tier: Mapped[str] = mapped_column(String(20), default="bronze")  # bronze, silver, gold, platinum
    tier_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Metadata
    last_activity: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_calculated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent")


class Vouch(Base):
    """A vouch from one agent for another."""

    __tablename__ = "reputation_vouches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    voucher_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    vouchee_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # Vouch details
    category: Mapped[str] = mapped_column(String(50))  # reliability, quality, expertise, etc.
    strength: Mapped[float] = mapped_column(Float, default=1.0)  # 0.0 - 1.0
    message: Mapped[str | None] = mapped_column(Text)

    # Context
    interaction_id: Mapped[UUID | None] = mapped_column()  # What interaction prompted this
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    voucher: Mapped["Agent"] = relationship("Agent", foreign_keys=[voucher_id])
    vouchee: Mapped["Agent"] = relationship("Agent", foreign_keys=[vouchee_id])

    __table_args__ = (
        UniqueConstraint("voucher_id", "vouchee_id", "category", name="uq_vouch_unique"),
        Index("ix_vouches_vouchee_active", "vouchee_id", "is_active"),
    )


class DisputeStatus(str, enum.Enum):
    """Status of a dispute."""

    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED_VALID = "resolved_valid"
    RESOLVED_INVALID = "resolved_invalid"
    DISMISSED = "dismissed"


class Dispute(Base):
    """A dispute filed against an agent."""

    __tablename__ = "reputation_disputes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    reporter_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    accused_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # Dispute details
    category: Mapped[str] = mapped_column(String(50))  # fraud, poor_quality, unresponsive, etc.
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # low, medium, high, critical
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Context
    interaction_id: Mapped[UUID | None] = mapped_column()
    related_goal_id: Mapped[UUID | None] = mapped_column()

    # Resolution
    status: Mapped[DisputeStatus] = mapped_column(
        Enum(DisputeStatus), default=DisputeStatus.OPEN
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Impact
    reputation_impact: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    reporter: Mapped["Agent"] = relationship("Agent", foreign_keys=[reporter_id])
    accused: Mapped["Agent"] = relationship("Agent", foreign_keys=[accused_id])

    __table_args__ = (
        Index("ix_disputes_accused_status", "accused_id", "status"),
    )


class ReputationEvent(Base):
    """Individual events that affect reputation."""

    __tablename__ = "reputation_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # Event details
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    # task_completed, task_failed, vouch_received, dispute_filed, etc.

    description: Mapped[str | None] = mapped_column(Text)

    # Impact
    score_delta: Mapped[float] = mapped_column(Float, default=0.0)
    category_affected: Mapped[str | None] = mapped_column(String(50))

    # Context
    source_agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))
    related_id: Mapped[UUID | None] = mapped_column()  # vouch_id, dispute_id, task_id, etc.
    metadata_: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", foreign_keys=[agent_id])

    __table_args__ = (
        Index("ix_reputation_events_agent_type", "agent_id", "event_type"),
    )
