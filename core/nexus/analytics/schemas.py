"""Pydantic schemas for analytics API."""

from datetime import datetime, date
from uuid import UUID

from pydantic import BaseModel, Field

from nexus.analytics.models import MetricType


class DashboardSummary(BaseModel):
    """Dashboard summary data."""

    # Totals for current period
    total_api_requests: int
    total_memory_operations: int
    total_capability_invocations: int
    total_webhook_deliveries: int

    # Comparison with previous period
    api_requests_change_percent: float | None
    memory_ops_change_percent: float | None
    invocations_change_percent: float | None

    # Current storage
    memory_count: int
    memory_bytes: int
    relationship_count: int

    # Top metrics
    top_endpoints: list[dict]
    top_capabilities: list[dict]

    # Period info
    period_start: datetime
    period_end: datetime


class UsageMetric(BaseModel):
    """Single usage metric data point."""

    metric_type: MetricType
    timestamp: datetime
    count: int
    sum_value: int | None = None
    avg_value: float | None = None


class UsageTimeline(BaseModel):
    """Usage timeline data."""

    metric_type: MetricType
    data_points: list[UsageMetric]
    total: int
    period_start: datetime
    period_end: datetime
    granularity: str  # "hour" or "day"


class UsageResponse(BaseModel):
    """Response containing usage metrics."""

    metrics: dict[str, UsageTimeline]  # Keyed by metric type
    period_start: datetime
    period_end: datetime


class EndpointUsage(BaseModel):
    """Usage data for a single endpoint."""

    endpoint: str
    method: str
    request_count: int
    error_count: int
    error_rate: float
    avg_latency_ms: float | None
    min_latency_ms: int | None
    max_latency_ms: int | None
    status_codes: dict[str, int]


class EndpointsResponse(BaseModel):
    """Response containing endpoint metrics."""

    endpoints: list[EndpointUsage]
    total_requests: int
    period_start: datetime
    period_end: datetime


class StorageSnapshot(BaseModel):
    """Storage usage at a point in time."""

    date: date
    memory_count: int
    memory_bytes: int
    media_count: int
    media_bytes: int
    relationship_count: int
    total_bytes: int


class StorageResponse(BaseModel):
    """Response containing storage usage."""

    current: StorageSnapshot
    history: list[StorageSnapshot]
    period_days: int


class TeamUsage(BaseModel):
    """Usage metrics for a team."""

    team_id: UUID
    team_name: str
    total_api_requests: int
    total_memory_operations: int
    total_invocations: int
    storage_bytes: int
    agent_count: int
    top_agents: list[dict]


class QuotaUsage(BaseModel):
    """Current quota usage against plan limits."""

    # Current usage
    api_requests_used: int
    memory_ops_used: int
    stored_memories: int
    storage_bytes_used: int

    # Plan limits
    api_requests_limit: int | None
    memory_ops_limit: int | None
    stored_memories_limit: int | None
    storage_bytes_limit: int | None

    # Percentages
    api_requests_percent: float | None
    memory_ops_percent: float | None
    stored_memories_percent: float | None
    storage_percent: float | None

    # Period
    billing_period_start: datetime
    billing_period_end: datetime


class ExportRequest(BaseModel):
    """Request for data export."""

    start_date: date
    end_date: date
    metric_types: list[MetricType] | None = None
    format: str = Field(default="json", pattern="^(json|csv)$")
    include_dimensions: bool = False


class ExportResponse(BaseModel):
    """Response for data export."""

    format: str
    data: list[dict] | str  # List for JSON, string for CSV
    row_count: int
    period_start: date
    period_end: date
