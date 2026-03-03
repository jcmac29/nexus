"""Rate limiting models."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from nexus.database import Base


class RateLimitConfig(Base):
    """Rate limit configuration for an agent."""

    __tablename__ = "rate_limit_configs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), unique=True)

    # Requests per minute
    requests_per_minute: Mapped[int] = mapped_column(Integer, default=60)
    # Requests per hour
    requests_per_hour: Mapped[int] = mapped_column(Integer, default=1000)
    # Requests per day
    requests_per_day: Mapped[int] = mapped_column(Integer, default=10000)

    # Invocations limits (subset of requests)
    invocations_per_minute: Mapped[int] = mapped_column(Integer, default=30)
    invocations_per_hour: Mapped[int] = mapped_column(Integer, default=500)

    # Burst allowance (temporary spike above limit)
    burst_allowance: Mapped[int] = mapped_column(Integer, default=10)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class RateLimitCounter(Base):
    """Tracks rate limit usage per agent per time window."""

    __tablename__ = "rate_limit_counters"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    # Window type: minute, hour, day
    window_type: Mapped[str] = mapped_column(String(10))
    # Window start time (truncated to minute/hour/day)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Counters
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    invocation_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_rate_limit_counters_agent_window", "agent_id", "window_type", "window_start"),
    )
