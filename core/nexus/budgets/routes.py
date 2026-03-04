"""Budgets API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.budgets.models import BudgetType
from nexus.budgets.schemas import (
    BudgetResponse,
    BudgetSummaryResponse,
    ConsumeReservationRequest,
    CreateBudgetRequest,
    EstimateRequest,
    EstimateResponse,
    ReservationRequest,
    ReservationResponse,
    UpdateBudgetRequest,
    UsageRecordResponse,
)
from nexus.budgets.service import BudgetsService

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _budget_to_response(budget) -> BudgetResponse:
    return BudgetResponse(
        id=budget.id,
        agent_id=budget.agent_id,
        budget_type=budget.budget_type.value,
        name=budget.name,
        description=budget.description,
        total_limit=budget.total_limit,
        used_amount=budget.used_amount,
        reserved_amount=budget.reserved_amount,
        available_amount=budget.available_amount,
        usage_percent=budget.usage_percent,
        period_type=budget.period_type,
        period_start=budget.period_start,
        period_end=budget.period_end,
        alert_threshold=budget.alert_threshold,
        alert_sent=budget.alert_sent,
        is_active=budget.is_active,
        is_exceeded=budget.is_exceeded,
        created_at=budget.created_at,
    )


@router.post("", status_code=201)
async def create_budget(
    request: CreateBudgetRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    """Create a new budget."""
    service = BudgetsService(db)

    budget = await service.create_budget(
        agent_id=agent.id,
        budget_type=BudgetType(request.budget_type),
        name=request.name,
        total_limit=request.total_limit,
        description=request.description,
        period_type=request.period_type,
        alert_threshold=request.alert_threshold,
        config=request.config,
    )

    return _budget_to_response(budget)


@router.get("")
async def list_budgets(
    budget_type: str | None = None,
    active_only: bool = True,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[BudgetResponse]:
    """List my budgets."""
    service = BudgetsService(db)

    bt = BudgetType(budget_type) if budget_type else None
    budgets = await service.get_budgets(agent.id, bt, active_only)

    return [_budget_to_response(b) for b in budgets]


@router.get("/me")
async def get_budget_summary(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> BudgetSummaryResponse:
    """Get budget summary."""
    service = BudgetsService(db)
    summary = await service.get_summary(agent.id)

    return BudgetSummaryResponse(
        total_budgets=summary["total_budgets"],
        budgets=[_budget_to_response(b) for b in summary["budgets"]],
        alerts=summary["alerts"],
    )


@router.get("/{budget_id}")
async def get_budget(
    budget_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    """Get a budget."""
    service = BudgetsService(db)
    budget = await service.get_budget(budget_id)

    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")

    if budget.agent_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    return _budget_to_response(budget)


@router.patch("/{budget_id}")
async def update_budget(
    budget_id: UUID,
    request: UpdateBudgetRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    """Update a budget."""
    service = BudgetsService(db)

    try:
        budget = await service.update_budget(
            budget_id=budget_id,
            total_limit=request.total_limit,
            alert_threshold=request.alert_threshold,
            is_active=request.is_active,
            config=request.config,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _budget_to_response(budget)


@router.post("/{budget_id}/reset")
async def reset_budget(
    budget_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    """Reset a budget for new period."""
    service = BudgetsService(db)

    try:
        budget = await service.reset_budget(budget_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _budget_to_response(budget)


@router.post("/estimate")
async def estimate_budget(
    request: EstimateRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> EstimateResponse:
    """Estimate if an action fits in budget."""
    service = BudgetsService(db)

    result = await service.estimate(
        agent_id=agent.id,
        budget_type=BudgetType(request.budget_type),
        estimated_amount=request.estimated_amount,
    )

    return EstimateResponse(
        budget_type=result["budget_type"],
        estimated_amount=result["estimated_amount"],
        current_available=result["current_available"],
        fits_in_budget=result["fits_in_budget"],
        remaining_after=result["remaining_after"],
        usage_percent_after=result["usage_percent_after"],
        warning=result.get("warning"),
    )


@router.post("/reserve", status_code=201)
async def create_reservation(
    request: ReservationRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ReservationResponse:
    """Reserve budget for a task."""
    service = BudgetsService(db)

    try:
        reservation = await service.reserve(
            budget_id=request.budget_id,
            agent_id=agent.id,
            amount=request.amount,
            purpose=request.purpose,
            expires_in_seconds=request.expires_in_seconds,
            task_id=request.task_id,
            goal_id=request.goal_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ReservationResponse(
        id=reservation.id,
        budget_id=reservation.budget_id,
        agent_id=reservation.agent_id,
        amount=reservation.amount,
        purpose=reservation.purpose,
        status=reservation.status.value,
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
    )


@router.post("/reservations/{reservation_id}/consume")
async def consume_reservation(
    reservation_id: UUID,
    request: ConsumeReservationRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ReservationResponse:
    """Consume a reservation."""
    service = BudgetsService(db)

    try:
        reservation = await service.consume_reservation(
            reservation_id, request.actual_amount
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ReservationResponse(
        id=reservation.id,
        budget_id=reservation.budget_id,
        agent_id=reservation.agent_id,
        amount=reservation.amount,
        purpose=reservation.purpose,
        status=reservation.status.value,
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
    )


@router.post("/reservations/{reservation_id}/release")
async def release_reservation(
    reservation_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> ReservationResponse:
    """Release a reservation without consuming."""
    service = BudgetsService(db)

    try:
        reservation = await service.release_reservation(reservation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ReservationResponse(
        id=reservation.id,
        budget_id=reservation.budget_id,
        agent_id=reservation.agent_id,
        amount=reservation.amount,
        purpose=reservation.purpose,
        status=reservation.status.value,
        expires_at=reservation.expires_at,
        created_at=reservation.created_at,
    )


@router.get("/{budget_id}/usage")
async def get_usage_history(
    budget_id: UUID,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
) -> list[UsageRecordResponse]:
    """Get usage history for a budget."""
    service = BudgetsService(db)
    records = await service.get_usage_history(budget_id, limit)

    return [
        UsageRecordResponse(
            id=r.id,
            budget_id=r.budget_id,
            amount=r.amount,
            action=r.action,
            description=r.description,
            created_at=r.created_at,
        )
        for r in records
    ]
