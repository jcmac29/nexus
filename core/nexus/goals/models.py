"""Goals database models."""

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
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base

if TYPE_CHECKING:
    from nexus.identity.models import Agent


class GoalStatus(str, enum.Enum):
    """Status of a goal."""

    DRAFT = "draft"
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class GoalPriority(str, enum.Enum):
    """Priority level of a goal."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BACKGROUND = "background"


class Goal(Base):
    """A persistent objective for an agent."""

    __tablename__ = "goals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    parent_goal_id: Mapped[UUID | None] = mapped_column(ForeignKey("goals.id"))

    # Goal definition
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    success_criteria: Mapped[str | None] = mapped_column(Text)

    # Classification
    goal_type: Mapped[str] = mapped_column(String(50), default="general")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Status
    status: Mapped[GoalStatus] = mapped_column(Enum(GoalStatus), default=GoalStatus.DRAFT)
    priority: Mapped[GoalPriority] = mapped_column(
        Enum(GoalPriority), default=GoalPriority.MEDIUM
    )

    # Progress
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    progress_notes: Mapped[str | None] = mapped_column(Text)

    # Timeline
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Outcome
    outcome: Mapped[str | None] = mapped_column(Text)
    outcome_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Configuration
    config: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    constraints: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent")
    parent_goal: Mapped["Goal | None"] = relationship(
        "Goal", remote_side=[id], foreign_keys=[parent_goal_id]
    )
    milestones: Mapped[list["Milestone"]] = relationship(
        "Milestone", back_populates="goal", lazy="selectin"
    )
    blockers: Mapped[list["Blocker"]] = relationship(
        "Blocker",
        back_populates="goal",
        lazy="selectin",
        foreign_keys="[Blocker.goal_id]",
    )
    delegations: Mapped[list["Delegation"]] = relationship(
        "Delegation",
        back_populates="goal",
        lazy="selectin",
        foreign_keys="[Delegation.goal_id]",
    )

    __table_args__ = (
        Index("ix_goals_agent_status", "agent_id", "status"),
        Index("ix_goals_agent_priority", "agent_id", "priority"),
    )


class Milestone(Base):
    """A milestone within a goal."""

    __tablename__ = "goal_milestones"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    goal_id: Mapped[UUID] = mapped_column(ForeignKey("goals.id"), index=True)

    # Milestone definition
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Progress
    weight: Mapped[float] = mapped_column(Float, default=1.0)  # Contribution to goal progress

    # Timeline
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    goal: Mapped["Goal"] = relationship("Goal", back_populates="milestones")

    __table_args__ = (
        Index("ix_milestones_goal_order", "goal_id", "order"),
    )


class Blocker(Base):
    """A blocker preventing goal progress."""

    __tablename__ = "goal_blockers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    goal_id: Mapped[UUID] = mapped_column(ForeignKey("goals.id"), index=True)

    # Blocker details
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    blocker_type: Mapped[str] = mapped_column(String(50))
    # dependency, resource, external, technical, approval, etc.

    # Severity
    severity: Mapped[str] = mapped_column(String(20), default="medium")

    # Resolution
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Related entities
    blocking_agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))
    blocking_goal_id: Mapped[UUID | None] = mapped_column(ForeignKey("goals.id"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    goal: Mapped["Goal"] = relationship("Goal", back_populates="blockers", foreign_keys=[goal_id])
    blocking_agent: Mapped["Agent | None"] = relationship("Agent")
    blocking_goal: Mapped["Goal | None"] = relationship("Goal", foreign_keys=[blocking_goal_id])

    __table_args__ = (
        Index("ix_blockers_goal_resolved", "goal_id", "is_resolved"),
    )


class Delegation(Base):
    """A delegation of work to another agent."""

    __tablename__ = "goal_delegations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    goal_id: Mapped[UUID] = mapped_column(ForeignKey("goals.id"), index=True)
    delegator_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    delegate_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # What's delegated
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending, accepted, rejected, in_progress, completed, failed

    # Terms
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    constraints: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Outcome
    result: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Linked entities
    created_goal_id: Mapped[UUID | None] = mapped_column(ForeignKey("goals.id"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    goal: Mapped["Goal"] = relationship("Goal", back_populates="delegations", foreign_keys=[goal_id])
    delegator: Mapped["Agent"] = relationship("Agent", foreign_keys=[delegator_id])
    delegate: Mapped["Agent"] = relationship("Agent", foreign_keys=[delegate_id])
    created_goal: Mapped["Goal | None"] = relationship("Goal", foreign_keys=[created_goal_id])

    __table_args__ = (
        Index("ix_delegations_delegate_status", "delegate_id", "status"),
    )
