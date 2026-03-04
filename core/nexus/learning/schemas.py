"""Learning API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RecordFeedbackRequest(BaseModel):
    """Request to record feedback."""

    action_type: str = Field(..., max_length=100)
    action_description: str | None = None
    input_data: dict | None = Field(default_factory=dict)
    feedback_type: str  # success, failure, partial, timeout, error
    output_data: dict | None = Field(default_factory=dict)
    error_message: str | None = None
    context_tags: list[str] = Field(default_factory=list)
    related_agent_id: UUID | None = None
    related_goal_id: UUID | None = None
    duration_ms: int | None = None
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)


class FeedbackResponse(BaseModel):
    """Response for feedback."""

    id: UUID
    agent_id: UUID
    action_type: str
    feedback_type: str
    context_tags: list[str]
    duration_ms: int | None
    created_at: datetime


class PatternResponse(BaseModel):
    """Response for pattern."""

    id: UUID
    agent_id: UUID
    action_type: str
    total_attempts: int
    success_count: int
    failure_count: int
    success_rate: float
    avg_duration_ms: int | None
    best_practices: dict | None
    failure_modes: list[str]
    recommended_approach: str | None
    last_updated: datetime


class QueryPatternsRequest(BaseModel):
    """Request to query patterns."""

    action_type: str | None = None
    min_attempts: int = 5
    min_success_rate: float | None = None


class ImprovementResponse(BaseModel):
    """Response for improvement suggestion."""

    id: UUID
    agent_id: UUID
    title: str
    description: str
    improvement_type: str
    expected_impact: str | None
    priority_score: float
    status: str
    created_at: datetime


class AcceptImprovementRequest(BaseModel):
    """Request to accept/reject an improvement."""

    accept: bool
    reason: str | None = None
