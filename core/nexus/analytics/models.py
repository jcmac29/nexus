"""Database models for usage analytics."""

import enum
from datetime import datetime, date
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus.database import Base


class MetricType(str, enum.Enum):
    """Types of metrics tracked."""

    API_REQUEST = "api_request"
    MEMORY_STORE = "memory_store"
    MEMORY_GET = "memory_get"
    MEMORY_SEARCH = "memory_search"
    MEMORY_DELETE = "memory_delete"
    CAPABILITY_INVOKE = "capability_invoke"
    CAPABILITY_DISCOVER = "capability_discover"
    WEBHOOK_DELIVERY = "webhook_delivery"
    MESSAGE_SENT = "message_sent"
    EVENT_PUBLISHED = "event_published"
    GRAPH_TRAVERSE = "graph_traverse"


class HourlyMetric(Base):
    """
    Hourly aggregated metrics.

    Stores metric counts and values aggregated by hour for efficient querying.
    """

    __tablename__ = "hourly_metrics"

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
    team_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metric_type: Mapped[MetricType] = mapped_column(
        Enum(MetricType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    hour: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Aggregated values
    count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    sum_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # For values like bytes, latency
    min_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    avg_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Dimensional breakdown for detailed analysis
    dimensions: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )  # e.g., {"endpoint": "/api/v1/memory", "status_code": "200"}

    __table_args__ = (
        Index("ix_hourly_metrics_agent_hour", "agent_id", "hour"),
        Index("ix_hourly_metrics_team_hour", "team_id", "hour"),
        Index("ix_hourly_metrics_type_hour", "metric_type", "hour"),
        Index("ix_hourly_metrics_lookup", "agent_id", "metric_type", "hour"),
    )

    def __repr__(self) -> str:
        return f"<HourlyMetric {self.metric_type} {self.hour}: {self.count}>"


class DailyMetric(Base):
    """
    Daily aggregated metrics for dashboards.

    Rolled up from hourly metrics with percentile calculations.
    """

    __tablename__ = "daily_metrics"

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
    team_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    metric_type: Mapped[MetricType] = mapped_column(
        Enum(MetricType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    # Aggregated values
    count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    sum_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    min_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    avg_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Percentiles for latency/value distributions
    p50_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    p99_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Dimensional breakdown
    dimensions: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )

    __table_args__ = (
        Index("ix_daily_metrics_agent_date", "agent_id", "date"),
        Index("ix_daily_metrics_team_date", "team_id", "date"),
        Index("ix_daily_metrics_type_date", "metric_type", "date"),
        Index("ix_daily_metrics_lookup", "agent_id", "metric_type", "date"),
    )

    def __repr__(self) -> str:
        return f"<DailyMetric {self.metric_type} {self.date}: {self.count}>"


class EndpointMetric(Base):
    """
    Per-endpoint metrics for API analytics.

    Tracks request counts, latencies, and status codes by endpoint.
    """

    __tablename__ = "endpoint_metrics"

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
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)  # GET, POST, etc.
    hour: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Request counts
    request_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")

    # Latency stats (in milliseconds)
    total_latency_ms: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    min_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Status code breakdown
    status_codes: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )  # {"200": 150, "400": 5, "500": 1}

    __table_args__ = (
        Index("ix_endpoint_metrics_agent_hour", "agent_id", "hour"),
        Index("ix_endpoint_metrics_endpoint_hour", "endpoint", "hour"),
    )

    def __repr__(self) -> str:
        return f"<EndpointMetric {self.method} {self.endpoint}: {self.request_count}>"


class StorageUsage(Base):
    """
    Track storage usage over time.

    Daily snapshots of memory and media storage.
    """

    __tablename__ = "storage_usage"

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
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    # Memory storage
    memory_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    memory_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")

    # Media storage
    media_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    media_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")

    # Peak values during the day
    peak_memory_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    peak_memory_bytes: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")

    # Relationship counts
    relationship_count: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")

    __table_args__ = (
        Index("ix_storage_usage_agent_date", "agent_id", "date", unique=True),
    )

    def __repr__(self) -> str:
        return f"<StorageUsage {self.agent_id} {self.date}: {self.memory_count} memories>"
