"""Vitals database models."""

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


class HealthStatus(str, enum.Enum):
    """Health status of an agent."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    OFFLINE = "offline"


class AgentVitals(Base):
    """Real-time health and status metrics for an agent."""

    __tablename__ = "agent_vitals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id"), unique=True, index=True
    )

    # Health status
    status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus, values_callable=lambda x: [e.value for e in x]),
        default=HealthStatus.UNKNOWN,
    )
    status_message: Mapped[str | None] = mapped_column(Text)

    # Availability
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    is_busy: Mapped[bool] = mapped_column(Boolean, default=False)
    current_load: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0 - 1.0
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, default=1)
    current_tasks: Mapped[int] = mapped_column(Integer, default=0)

    # Performance metrics
    avg_response_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    p95_response_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    p99_response_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0 - 1.0

    # Uptime
    uptime_percent: Mapped[float] = mapped_column(Float, default=100.0)
    last_downtime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_uptime_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # Capacity
    queue_depth: Mapped[int] = mapped_column(Integer, default=0)
    estimated_wait_seconds: Mapped[int] = mapped_column(Integer, default=0)

    # Capabilities status
    capabilities_status: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    # {"code_review": "available", "testing": "degraded"}

    # Heartbeat
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_interval_seconds: Mapped[int] = mapped_column(Integer, default=30)
    missed_heartbeats: Mapped[int] = mapped_column(Integer, default=0)

    # Version info
    agent_version: Mapped[str | None] = mapped_column(String(50))
    last_deployed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent")

    __table_args__ = (
        Index("ix_agent_vitals_status_online", "status", "is_online"),
    )


class VitalsSubscription(Base):
    """A subscription to an agent's vitals updates."""

    __tablename__ = "vitals_subscriptions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    subscriber_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    target_agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # Subscription settings
    notify_on: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    # ["status_change", "offline", "degraded", "error_spike", "load_high"]

    threshold_load: Mapped[float | None] = mapped_column(Float)  # Alert if load exceeds
    threshold_error_rate: Mapped[float | None] = mapped_column(Float)
    threshold_response_time_ms: Mapped[int | None] = mapped_column(Integer)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Delivery
    webhook_url: Mapped[str | None] = mapped_column(String(2048))
    last_notified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    subscriber: Mapped["Agent"] = relationship("Agent", foreign_keys=[subscriber_id])
    target_agent: Mapped["Agent"] = relationship("Agent", foreign_keys=[target_agent_id])

    __table_args__ = (
        Index("ix_vitals_subs_subscriber_active", "subscriber_id", "is_active"),
        Index("ix_vitals_subs_target", "target_agent_id"),
    )


class VitalsSnapshot(Base):
    """Historical snapshot of agent vitals."""

    __tablename__ = "vitals_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"), index=True)

    # Snapshot of key metrics
    status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus, values_callable=lambda x: [e.value for e in x])
    )
    is_online: Mapped[bool] = mapped_column(Boolean)
    current_load: Mapped[float] = mapped_column(Float)
    current_tasks: Mapped[int] = mapped_column(Integer)
    avg_response_time_ms: Mapped[int] = mapped_column(Integer)
    error_rate: Mapped[float] = mapped_column(Float)
    queue_depth: Mapped[int] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent")

    __table_args__ = (
        Index("ix_vitals_snapshots_agent_created", "agent_id", "created_at"),
    )
