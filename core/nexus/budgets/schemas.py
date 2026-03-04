"""Budgets API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateBudgetRequest(BaseModel):
    """Request to create a budget."""

    budget_type: str  # api_calls, tokens, credits, compute_seconds, storage_bytes, bandwidth_bytes, custom
    name: str = Field(..., max_length=100)
    description: str | None = None
    total_limit: int = Field(..., gt=0)
    period_type: str = "monthly"  # hourly, daily, weekly, monthly, yearly, lifetime
    alert_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    config: dict | None = Field(default_factory=dict)


class BudgetResponse(BaseModel):
    """Response for budget."""

    id: UUID
    agent_id: UUID
    budget_type: str
    name: str
    description: str | None
    total_limit: int
    used_amount: int
    reserved_amount: int
    available_amount: int
    usage_percent: float
    period_type: str
    period_start: datetime
    period_end: datetime | None
    alert_threshold: float
    alert_sent: bool
    is_active: bool
    is_exceeded: bool
    created_at: datetime


class UpdateBudgetRequest(BaseModel):
    """Request to update a budget."""

    total_limit: int | None = None
    alert_threshold: float | None = None
    is_active: bool | None = None
    config: dict | None = None


class EstimateRequest(BaseModel):
    """Request to estimate if an action fits in budget."""

    budget_type: str
    estimated_amount: int
    action_description: str | None = None


class EstimateResponse(BaseModel):
    """Response for budget estimate."""

    budget_type: str
    estimated_amount: int
    current_available: int
    fits_in_budget: bool
    remaining_after: int
    usage_percent_after: float
    warning: str | None = None


class ReservationRequest(BaseModel):
    """Request to reserve budget."""

    budget_id: UUID
    amount: int = Field(..., gt=0)
    purpose: str | None = None
    expires_in_seconds: int = Field(default=3600, gt=0, le=86400)
    task_id: UUID | None = None
    goal_id: UUID | None = None


class ReservationResponse(BaseModel):
    """Response for reservation."""

    id: UUID
    budget_id: UUID
    agent_id: UUID
    amount: int
    purpose: str | None
    status: str
    expires_at: datetime
    created_at: datetime


class ConsumeReservationRequest(BaseModel):
    """Request to consume a reservation."""

    actual_amount: int = Field(..., ge=0)


class UsageRecordResponse(BaseModel):
    """Response for usage record."""

    id: UUID
    budget_id: UUID
    amount: int
    action: str
    description: str | None
    created_at: datetime


class BudgetSummaryResponse(BaseModel):
    """Response for budget summary."""

    total_budgets: int
    budgets: list[BudgetResponse]
    alerts: list[dict]
