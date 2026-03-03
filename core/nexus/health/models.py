"""Health monitoring models."""

import enum
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import String, Integer, DateTime, ForeignKey, Float, Enum, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from nexus.database import Base


class HealthStatus(str, enum.Enum):
    """Agent health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AgentHealth(Base):
    """Health status for an agent."""

    __tablename__ = "agent_health"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), unique=True)

    status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus), default=HealthStatus.UNKNOWN
    )

    # Last activity timestamps
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_invocation_received: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_invocation_completed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Response metrics (rolling averages)
    avg_response_time_ms: Mapped[float] = mapped_column(Float, default=0.0)
    success_rate: Mapped[float] = mapped_column(Float, default=100.0)  # percentage

    # Error tracking
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    total_failures_24h: Mapped[int] = mapped_column(Integer, default=0)

    # Uptime
    uptime_percentage: Mapped[float] = mapped_column(Float, default=100.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class HealthCheck(Base):
    """Individual health check record."""

    __tablename__ = "health_checks"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    check_type: Mapped[str] = mapped_column(String(50))  # heartbeat, invocation, ping
    status: Mapped[HealthStatus] = mapped_column(Enum(HealthStatus))
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_health_checks_agent_created", "agent_id", "created_at"),
    )


class HealthAlert(Base):
    """Health alert notification."""

    __tablename__ = "health_alerts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    alert_type: Mapped[str] = mapped_column(String(50))  # degraded, unhealthy, recovered
    message: Mapped[str] = mapped_column(Text)
    acknowledged: Mapped[bool] = mapped_column(default=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_health_alerts_agent_created", "agent_id", "created_at"),
    )
