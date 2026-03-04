"""Context API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PackContextRequest(BaseModel):
    """Request to pack context for transfer."""

    name: str = Field(..., max_length=255)
    summary: str | None = None
    goals: dict | None = Field(default_factory=dict)
    memories: dict | None = Field(default_factory=dict)
    conversation_history: list | None = Field(default_factory=list)
    reasoning_trace: list | None = Field(default_factory=list)
    decisions_made: list | None = Field(default_factory=list)
    constraints: dict | None = Field(default_factory=dict)
    preferences: dict | None = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    is_public: bool = False
    allowed_agents: list[str] = Field(default_factory=list)
    expires_in_hours: int | None = None


class ContextPackageResponse(BaseModel):
    """Response for context package."""

    id: UUID
    owner_agent_id: UUID
    name: str
    version: int
    summary: str | None
    tags: list[str]
    size_bytes: int
    is_public: bool
    expires_at: datetime | None
    created_at: datetime


class ContextPackageDetailResponse(ContextPackageResponse):
    """Detailed response for context package."""

    goals: dict | None
    memories: dict | None
    conversation_history: list | None
    reasoning_trace: list | None
    decisions_made: list | None
    constraints: dict | None
    preferences: dict | None


class TransferContextRequest(BaseModel):
    """Request to transfer context to another agent."""

    package_id: UUID
    receiver_id: UUID
    purpose: str | None = None
    message: str | None = None
    related_goal_id: UUID | None = None
    related_task_id: UUID | None = None


class ContextTransferResponse(BaseModel):
    """Response for context transfer."""

    id: UUID
    package_id: UUID
    sender_id: UUID
    receiver_id: UUID
    purpose: str | None
    status: str
    diff_summary: str | None
    sent_at: datetime | None
    received_at: datetime | None
    applied_at: datetime | None
    created_at: datetime


class AcceptTransferRequest(BaseModel):
    """Request to accept/reject a transfer."""

    accept: bool
    message: str | None = None


class ContextDiffResponse(BaseModel):
    """Response for context diff."""

    package_id: UUID
    previous_version: int | None
    current_version: int
    changes: dict
    summary: str
