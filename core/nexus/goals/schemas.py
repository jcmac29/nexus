"""Goals API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateGoalRequest(BaseModel):
    """Request to create a goal."""

    title: str = Field(..., max_length=500)
    description: str | None = None
    success_criteria: str | None = None
    goal_type: str = "general"
    tags: list[str] = Field(default_factory=list)
    priority: str = "medium"  # critical, high, medium, low, background
    target_date: datetime | None = None
    parent_goal_id: UUID | None = None
    config: dict | None = Field(default_factory=dict)
    constraints: dict | None = Field(default_factory=dict)


class UpdateGoalRequest(BaseModel):
    """Request to update a goal."""

    title: str | None = None
    description: str | None = None
    success_criteria: str | None = None
    priority: str | None = None
    target_date: datetime | None = None
    config: dict | None = None
    constraints: dict | None = None


class GoalResponse(BaseModel):
    """Response for goal."""

    id: UUID
    agent_id: UUID
    parent_goal_id: UUID | None
    title: str
    description: str | None
    success_criteria: str | None
    goal_type: str
    tags: list[str]
    status: str
    priority: str
    progress_percent: int
    progress_notes: str | None
    target_date: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    outcome: str | None
    created_at: datetime


class UpdateProgressRequest(BaseModel):
    """Request to update goal progress."""

    progress_percent: int = Field(..., ge=0, le=100)
    progress_notes: str | None = None


class MilestoneRequest(BaseModel):
    """Request to add a milestone."""

    title: str = Field(..., max_length=500)
    description: str | None = None
    order: int = 0
    weight: float = Field(default=1.0, ge=0.0)
    target_date: datetime | None = None


class MilestoneResponse(BaseModel):
    """Response for milestone."""

    id: UUID
    goal_id: UUID
    title: str
    description: str | None
    order: int
    weight: float
    is_completed: bool
    completed_at: datetime | None
    target_date: datetime | None


class BlockerRequest(BaseModel):
    """Request to add a blocker."""

    title: str = Field(..., max_length=500)
    description: str | None = None
    blocker_type: str  # dependency, resource, external, technical, approval
    severity: str = "medium"
    blocking_agent_id: UUID | None = None
    blocking_goal_id: UUID | None = None


class BlockerResponse(BaseModel):
    """Response for blocker."""

    id: UUID
    goal_id: UUID
    title: str
    description: str | None
    blocker_type: str
    severity: str
    is_resolved: bool
    resolution: str | None
    resolved_at: datetime | None


class ResolveBlockerRequest(BaseModel):
    """Request to resolve a blocker."""

    resolution: str


class DelegationRequest(BaseModel):
    """Request to delegate work."""

    delegate_id: UUID
    title: str = Field(..., max_length=500)
    description: str | None = None
    scope: dict | None = Field(default_factory=dict)
    deadline: datetime | None = None
    constraints: dict | None = Field(default_factory=dict)


class DelegationResponse(BaseModel):
    """Response for delegation."""

    id: UUID
    goal_id: UUID
    delegator_id: UUID
    delegate_id: UUID
    title: str
    status: str
    deadline: datetime | None
    created_goal_id: UUID | None
    created_at: datetime
