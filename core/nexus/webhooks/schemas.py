"""Pydantic schemas for webhook API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from nexus.webhooks.models import DeliveryStatus, RetryPolicy


class WebhookCreate(BaseModel):
    """Request to create a webhook endpoint."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    url: HttpUrl
    event_types: list[str] = Field(
        default=["*"],
        description="Event types to subscribe to. Supports wildcards like 'memory.*'",
    )
    retry_policy: RetryPolicy = RetryPolicy.EXPONENTIAL
    max_retries: int = Field(default=5, ge=0, le=10)
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    custom_headers: dict[str, str] = Field(default_factory=dict)


class WebhookUpdate(BaseModel):
    """Request to update a webhook endpoint."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    url: HttpUrl | None = None
    event_types: list[str] | None = None
    is_active: bool | None = None
    retry_policy: RetryPolicy | None = None
    max_retries: int | None = Field(default=None, ge=0, le=10)
    timeout_seconds: int | None = Field(default=None, ge=5, le=120)
    custom_headers: dict[str, str] | None = None


class WebhookResponse(BaseModel):
    """Response containing a webhook endpoint."""

    id: UUID
    agent_id: UUID
    name: str
    description: str | None
    url: str
    event_types: list[str]
    is_active: bool
    retry_policy: RetryPolicy
    max_retries: int
    timeout_seconds: int
    custom_headers: dict
    total_deliveries: int
    successful_deliveries: int
    failed_deliveries: int
    last_triggered_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WebhookListResponse(BaseModel):
    """Response containing list of webhooks."""

    webhooks: list[WebhookResponse]
    total: int


class WebhookSecretResponse(BaseModel):
    """Response containing webhook with secret (only shown on create/rotate)."""

    webhook: WebhookResponse
    secret: str


class DeliveryLogResponse(BaseModel):
    """Response containing a delivery log entry."""

    id: UUID
    webhook_endpoint_id: UUID
    event_id: UUID | None
    event_type: str
    payload: dict
    status: DeliveryStatus
    attempts: int
    response_status_code: int | None
    response_body: str | None
    response_time_ms: int | None
    last_error: str | None
    next_retry_at: datetime | None
    created_at: datetime
    delivered_at: datetime | None

    model_config = {"from_attributes": True}


class DeliveryLogListResponse(BaseModel):
    """Response containing list of delivery logs."""

    logs: list[DeliveryLogResponse]
    total: int


class TestWebhookResponse(BaseModel):
    """Response from webhook test ping."""

    success: bool
    status_code: int | None
    response_time_ms: int | None
    error: str | None


class EventTypesResponse(BaseModel):
    """Response listing available event types."""

    event_types: list[dict]  # {"type": "memory.created", "description": "..."}
