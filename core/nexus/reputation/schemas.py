"""Reputation API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ReputationScoreResponse(BaseModel):
    """Response for reputation score."""

    agent_id: UUID
    overall_score: float
    reliability_score: float
    quality_score: float
    responsiveness_score: float
    collaboration_score: float
    total_interactions: int
    successful_interactions: int
    vouches_received: int
    disputes_received: int
    tier: str
    last_activity: datetime | None


class VouchRequest(BaseModel):
    """Request to vouch for an agent."""

    category: str = Field(..., max_length=50)
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    message: str | None = None
    interaction_id: UUID | None = None
    capabilities: list[str] = Field(default_factory=list)


class VouchResponse(BaseModel):
    """Response for vouch."""

    id: UUID
    voucher_id: UUID
    vouchee_id: UUID
    category: str
    strength: float
    message: str | None
    is_active: bool
    created_at: datetime


class DisputeRequest(BaseModel):
    """Request to file a dispute."""

    category: str = Field(..., max_length=50)
    severity: str = Field(default="medium")  # low, medium, high, critical
    title: str = Field(..., max_length=255)
    description: str
    evidence: dict | None = Field(default_factory=dict)
    interaction_id: UUID | None = None
    related_goal_id: UUID | None = None


class DisputeResponse(BaseModel):
    """Response for dispute."""

    id: UUID
    reporter_id: UUID
    accused_id: UUID
    category: str
    severity: str
    title: str
    status: str
    resolution_notes: str | None
    reputation_impact: float
    created_at: datetime
    resolved_at: datetime | None


class ReputationHistoryResponse(BaseModel):
    """Response for reputation history."""

    agent_id: UUID
    events: list[dict]
    score_trend: list[dict]
