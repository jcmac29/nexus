"""Learning database models."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
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


class FeedbackType(str, enum.Enum):
    """Type of feedback."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    ERROR = "error"


class Feedback(Base):
    """Feedback record for agent actions."""

    __tablename__ = "learning_feedback"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # What was attempted
    action_type: Mapped[str] = mapped_column(String(100), index=True)
    action_description: Mapped[str | None] = mapped_column(Text)
    input_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # What happened
    feedback_type: Mapped[FeedbackType] = mapped_column(Enum(FeedbackType))
    output_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Context
    context_tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    related_agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))
    related_goal_id: Mapped[UUID | None] = mapped_column()

    # Metrics
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    confidence_score: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent", foreign_keys=[agent_id])

    __table_args__ = (
        Index("ix_learning_feedback_agent_action", "agent_id", "action_type"),
        Index("ix_learning_feedback_agent_type", "agent_id", "feedback_type"),
    )


class Pattern(Base):
    """Learned patterns from feedback aggregation."""

    __tablename__ = "learning_patterns"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # Pattern identification
    action_type: Mapped[str] = mapped_column(String(100), index=True)
    context_signature: Mapped[str] = mapped_column(String(500))  # Hash of context

    # Statistics
    total_attempts: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_duration_ms: Mapped[int | None] = mapped_column(Integer)

    # Learned insights
    best_practices: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    failure_modes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    recommended_approach: Mapped[str | None] = mapped_column(Text)

    # Metadata
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent")

    __table_args__ = (
        Index("ix_learning_patterns_agent_action", "agent_id", "action_type"),
    )


class ImprovementStatus(str, enum.Enum):
    """Status of an improvement suggestion."""

    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"


class Improvement(Base):
    """Suggested improvements based on feedback patterns."""

    __tablename__ = "learning_improvements"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    pattern_id: Mapped[UUID | None] = mapped_column(ForeignKey("learning_patterns.id"))

    # Suggestion
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    improvement_type: Mapped[str] = mapped_column(String(50))  # capability, behavior, config

    # Impact
    expected_impact: Mapped[str | None] = mapped_column(Text)
    priority_score: Mapped[float] = mapped_column(Float, default=0.5)

    # Status
    status: Mapped[ImprovementStatus] = mapped_column(
        Enum(ImprovementStatus), default=ImprovementStatus.SUGGESTED
    )
    status_reason: Mapped[str | None] = mapped_column(Text)

    # Implementation
    implementation_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    implemented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent")
    pattern: Mapped["Pattern | None"] = relationship("Pattern")

    __table_args__ = (
        Index("ix_learning_improvements_agent_status", "agent_id", "status"),
    )
