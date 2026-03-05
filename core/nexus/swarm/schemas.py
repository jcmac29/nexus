"""Swarm API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateSwarmRequest(BaseModel):
    """Request to create a new swarm."""

    name: str = Field(..., min_length=1, max_length=255)
    config: dict | None = Field(default_factory=dict)


class JoinSwarmRequest(BaseModel):
    """Request to join an existing swarm."""

    join_code: str = Field(..., min_length=6, max_length=24)  # Supports 16-char secure codes
    capabilities: list[str] = Field(default_factory=list)


class SubmitTaskRequest(BaseModel):
    """Request to submit a task to the swarm."""

    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    task_type: str = "general"
    priority: int = Field(default=5, ge=1, le=10)
    input_data: dict | None = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    max_retries: int = Field(default=3, ge=0, le=10)


class SubmitBatchRequest(BaseModel):
    """Request to submit multiple tasks."""

    tasks: list[SubmitTaskRequest]


class CompleteTaskRequest(BaseModel):
    """Request to mark a task as complete."""

    output_data: dict | None = Field(default_factory=dict)
    success: bool = True
    error_message: str | None = None
    execution_time_ms: int = 0


class SwarmResponse(BaseModel):
    """Response for swarm details."""

    id: UUID
    name: str
    join_code: str
    status: str
    config: dict | None
    created_at: datetime
    disbanded_at: datetime | None
    member_count: int
    pending_tasks: int
    completed_tasks: int


class SwarmMemberResponse(BaseModel):
    """Response for swarm member details."""

    id: UUID
    agent_id: UUID
    agent_name: str | None = None
    role: str
    status: str
    capabilities: list[str]
    tasks_completed: int
    last_heartbeat: datetime
    joined_at: datetime


class SwarmTaskResponse(BaseModel):
    """Response for task details."""

    id: UUID
    swarm_id: UUID
    parent_task_id: UUID | None
    title: str
    description: str | None
    task_type: str
    priority: int
    input_data: dict | None
    required_capabilities: list[str]
    status: str
    assigned_to: UUID | None
    assigned_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    timeout_seconds: int
    retry_count: int
    created_at: datetime


class SwarmTaskResultResponse(BaseModel):
    """Response for task result."""

    id: UUID
    task_id: UUID
    member_id: UUID
    output_data: dict | None
    success: bool
    error_message: str | None
    execution_time_ms: int
    created_at: datetime


class SwarmStatusResponse(BaseModel):
    """Response for full swarm status."""

    swarm: SwarmResponse
    members: list[SwarmMemberResponse]
    recent_tasks: list[SwarmTaskResponse]
    task_summary: dict


class AggregatedResultsResponse(BaseModel):
    """Response for aggregated task results."""

    swarm_id: UUID
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    pending_tasks: int
    results: list[SwarmTaskResultResponse]
