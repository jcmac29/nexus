"""Pydantic schemas for messaging API."""

from datetime import datetime
from uuid import UUID
from typing import Any

from pydantic import BaseModel, Field


# --- Message Schemas ---

class SendMessageRequest(BaseModel):
    """Send a message to another agent."""
    to_agent_id: UUID = Field(..., description="Target agent ID")
    subject: str | None = Field(None, description="Message subject")
    content: dict[str, Any] = Field(..., description="Message content (JSON)")
    reply_to_id: UUID | None = Field(None, description="Reply to message ID")


class MessageResponse(BaseModel):
    """Message response."""
    id: UUID
    from_agent_id: UUID
    to_agent_id: UUID
    subject: str | None
    content: dict[str, Any]
    reply_to_id: UUID | None
    status: str
    created_at: datetime
    read_at: datetime | None

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    """List of messages."""
    messages: list[MessageResponse]
    total: int


# --- Invocation Schemas ---

class InvokeCapabilityRequest(BaseModel):
    """Invoke a capability on another agent."""
    input: dict[str, Any] = Field(default_factory=dict, description="Input data for the capability")
    timeout_seconds: int = Field(30, description="Timeout in seconds", ge=1, le=300)
    async_mode: bool = Field(False, description="If true, return immediately with invocation ID")


class InvocationResponse(BaseModel):
    """Invocation response."""
    id: UUID
    caller_agent_id: UUID
    target_agent_id: UUID
    capability_id: UUID
    capability_name: str | None = None
    status: str
    input_data: dict[str, Any]
    output_data: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class InvocationListResponse(BaseModel):
    """List of invocations."""
    invocations: list[InvocationResponse]
    total: int


# --- Webhook Schemas ---

class WebhookConfig(BaseModel):
    """Webhook configuration for an agent."""
    endpoint_url: str = Field(..., description="URL to receive invocation requests")
    secret: str | None = Field(None, description="Secret for signing requests")
    events: list[str] = Field(
        default=["invocation", "message"],
        description="Events to receive: invocation, message"
    )


class WebhookResponse(BaseModel):
    """Webhook configuration response."""
    endpoint_url: str
    events: list[str]
    active: bool


# --- Pending Work Schemas ---

class PendingInvocation(BaseModel):
    """Pending invocation for an agent to process."""
    id: UUID
    caller_agent_id: UUID
    caller_agent_name: str | None
    capability_name: str
    input_data: dict[str, Any]
    created_at: datetime
    timeout_seconds: int


class PendingWorkResponse(BaseModel):
    """Pending work for an agent."""
    invocations: list[PendingInvocation]
    messages: list[MessageResponse]


class CompleteInvocationRequest(BaseModel):
    """Complete an invocation with a result."""
    output: dict[str, Any] = Field(default_factory=dict, description="Output data")
    error: str | None = Field(None, description="Error message if failed")
