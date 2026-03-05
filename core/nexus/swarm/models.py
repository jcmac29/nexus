"""Swarm database models."""

from __future__ import annotations

import enum
import secrets
import string
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


class SwarmStatus(str, enum.Enum):
    """Status of a swarm."""

    FORMING = "forming"
    ACTIVE = "active"
    PAUSED = "paused"
    DISBANDED = "disbanded"


class MemberRole(str, enum.Enum):
    """Role of a swarm member."""

    LEADER = "leader"
    WORKER = "worker"


class MemberStatus(str, enum.Enum):
    """Status of a swarm member."""

    CONNECTED = "connected"
    BUSY = "busy"
    IDLE = "idle"
    DISCONNECTED = "disconnected"


class TaskStatus(str, enum.Enum):
    """Status of a swarm task."""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    REASSIGNED = "reassigned"


def generate_join_code() -> str:
    """Generate a secure join code with high entropy.

    Uses 16 URL-safe characters (~96 bits of entropy) to prevent brute-force attacks.
    """
    return secrets.token_urlsafe(12)  # 12 bytes = 16 base64 chars


class Swarm(Base):
    """A swarm of coordinated agents/terminals."""

    __tablename__ = "swarms"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    join_code: Mapped[str] = mapped_column(
        String(24), unique=True, index=True, default=generate_join_code
    )
    owner_agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"))
    status: Mapped[SwarmStatus] = mapped_column(
        Enum(SwarmStatus), default=SwarmStatus.FORMING
    )
    config: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    disbanded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    owner: Mapped["Agent"] = relationship("Agent", foreign_keys=[owner_agent_id])
    members: Mapped[list["SwarmMember"]] = relationship(
        "SwarmMember", back_populates="swarm", lazy="selectin"
    )
    tasks: Mapped[list["SwarmTask"]] = relationship(
        "SwarmTask", back_populates="swarm", lazy="selectin"
    )

    __table_args__ = (Index("ix_swarms_owner_status", "owner_agent_id", "status"),)


class SwarmMember(Base):
    """A member of a swarm."""

    __tablename__ = "swarm_members"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    swarm_id: Mapped[UUID] = mapped_column(ForeignKey("swarms.id"), index=True)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    role: Mapped[MemberRole] = mapped_column(Enum(MemberRole), default=MemberRole.WORKER)
    status: Mapped[MemberStatus] = mapped_column(
        Enum(MemberStatus), default=MemberStatus.IDLE
    )
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    current_task_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("swarm_tasks.id", use_alter=True, name="fk_swarm_members_current_task")
    )
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    swarm: Mapped["Swarm"] = relationship("Swarm", back_populates="members")
    agent: Mapped["Agent"] = relationship("Agent")
    current_task: Mapped["SwarmTask | None"] = relationship(
        "SwarmTask", foreign_keys=[current_task_id]
    )

    __table_args__ = (
        Index("ix_swarm_members_swarm_status", "swarm_id", "status"),
        Index("ix_swarm_members_agent_swarm", "agent_id", "swarm_id"),
    )


class SwarmTask(Base):
    """A task within a swarm."""

    __tablename__ = "swarm_tasks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    swarm_id: Mapped[UUID] = mapped_column(ForeignKey("swarms.id"), index=True)
    parent_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("swarm_tasks.id"))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(100), default="general")
    priority: Mapped[int] = mapped_column(Integer, default=5)
    input_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    required_capabilities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING
    )
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("swarm_members.id"))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("swarm_members.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    swarm: Mapped["Swarm"] = relationship("Swarm", back_populates="tasks")
    parent_task: Mapped["SwarmTask | None"] = relationship(
        "SwarmTask", remote_side=[id], foreign_keys=[parent_task_id]
    )
    assignee: Mapped["SwarmMember | None"] = relationship(
        "SwarmMember",
        foreign_keys=[assigned_to],
        overlaps="current_task",
    )
    creator: Mapped["SwarmMember | None"] = relationship(
        "SwarmMember", foreign_keys=[created_by]
    )
    result: Mapped["SwarmTaskResult | None"] = relationship(
        "SwarmTaskResult", back_populates="task", uselist=False
    )

    __table_args__ = (
        Index("ix_swarm_tasks_swarm_status", "swarm_id", "status"),
        Index("ix_swarm_tasks_assigned_status", "assigned_to", "status"),
        Index("ix_swarm_tasks_priority_status", "priority", "status"),
    )


class SwarmTaskResult(Base):
    """Result of a completed swarm task."""

    __tablename__ = "swarm_task_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("swarm_tasks.id"), unique=True, index=True
    )
    member_id: Mapped[UUID] = mapped_column(ForeignKey("swarm_members.id"), index=True)
    output_data: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    execution_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    task: Mapped["SwarmTask"] = relationship("SwarmTask", back_populates="result")
    member: Mapped["SwarmMember"] = relationship("SwarmMember")
