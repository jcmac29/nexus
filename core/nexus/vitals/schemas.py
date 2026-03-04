"""Vitals API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class UpdateVitalsRequest(BaseModel):
    """Request to update agent vitals."""

    is_online: bool | None = None
    is_busy: bool | None = None
    current_load: float | None = Field(default=None, ge=0.0, le=1.0)
    max_concurrent_tasks: int | None = None
    current_tasks: int | None = None
    queue_depth: int | None = None
    estimated_wait_seconds: int | None = None
    capabilities_status: dict | None = None
    agent_version: str | None = None


class VitalsResponse(BaseModel):
    """Response for agent vitals."""

    agent_id: UUID
    status: str
    status_message: str | None
    is_online: bool
    is_busy: bool
    current_load: float
    max_concurrent_tasks: int
    current_tasks: int
    avg_response_time_ms: int
    p95_response_time_ms: int
    p99_response_time_ms: int
    error_rate: float
    uptime_percent: float
    queue_depth: int
    estimated_wait_seconds: int
    capabilities_status: dict | None
    last_heartbeat: datetime | None
    agent_version: str | None
    updated_at: datetime


class HeartbeatResponse(BaseModel):
    """Response for heartbeat."""

    agent_id: UUID
    status: str
    last_heartbeat: datetime
    missed_heartbeats: int


class SubscribeRequest(BaseModel):
    """Request to subscribe to agent vitals."""

    # target_agent_id comes from path parameter, not body
    notify_on: list[str] = Field(default_factory=list)
    # status_change, offline, degraded, error_spike, load_high
    threshold_load: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_error_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_response_time_ms: int | None = None
    webhook_url: str | None = Field(default=None, max_length=2048)


class SubscriptionResponse(BaseModel):
    """Response for subscription."""

    id: UUID
    subscriber_id: UUID
    target_agent_id: UUID
    notify_on: list[str]
    threshold_load: float | None
    threshold_error_rate: float | None
    threshold_response_time_ms: int | None
    is_active: bool
    webhook_url: str | None
    last_notified: datetime | None
    created_at: datetime


class FindHealthyRequest(BaseModel):
    """Request to find healthy agents."""

    capability: str | None = None
    max_load: float = Field(default=0.8, ge=0.0, le=1.0)
    max_response_time_ms: int | None = None
    require_online: bool = True
    limit: int = Field(default=10, ge=1, le=100)


class HealthyAgentResponse(BaseModel):
    """Response for a healthy agent."""

    agent_id: UUID
    agent_name: str | None
    status: str
    current_load: float
    avg_response_time_ms: int
    queue_depth: int
    estimated_wait_seconds: int
    capabilities_status: dict | None


class VitalsSnapshotResponse(BaseModel):
    """Response for vitals snapshot."""

    agent_id: UUID
    status: str
    is_online: bool
    current_load: float
    current_tasks: int
    avg_response_time_ms: int
    error_rate: float
    queue_depth: int
    created_at: datetime
