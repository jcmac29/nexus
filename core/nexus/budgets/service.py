"""Budgets service for resource awareness."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nexus.budgets.models import (
    Budget,
    BudgetType,
    Reservation,
    ReservationStatus,
    UsageRecord,
)

if TYPE_CHECKING:
    pass


class BudgetsService:
    """Service for managing agent budgets."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== Budgets ====================

    async def create_budget(
        self,
        agent_id: UUID,
        budget_type: BudgetType,
        name: str,
        total_limit: int,
        description: str | None = None,
        period_type: str = "monthly",
        alert_threshold: float = 0.8,
        config: dict | None = None,
    ) -> Budget:
        """Create a new budget."""
        now = datetime.now(timezone.utc)

        # Calculate period end
        period_end = None
        if period_type == "hourly":
            period_end = now + timedelta(hours=1)
        elif period_type == "daily":
            period_end = now + timedelta(days=1)
        elif period_type == "weekly":
            period_end = now + timedelta(weeks=1)
        elif period_type == "monthly":
            period_end = now + timedelta(days=30)
        elif period_type == "yearly":
            period_end = now + timedelta(days=365)
        # lifetime has no end

        budget = Budget(
            agent_id=agent_id,
            budget_type=budget_type,
            name=name,
            description=description,
            total_limit=total_limit,
            period_type=period_type,
            period_start=now,
            period_end=period_end,
            alert_threshold=alert_threshold,
            config=config or {},
        )
        self.db.add(budget)
        await self.db.commit()
        await self.db.refresh(budget)

        return budget

    async def get_budget(self, budget_id: UUID) -> Budget | None:
        """Get a budget by ID."""
        result = await self.db.execute(
            select(Budget)
            .options(selectinload(Budget.reservations))
            .where(Budget.id == budget_id)
        )
        return result.scalar_one_or_none()

    async def get_budgets(
        self,
        agent_id: UUID,
        budget_type: BudgetType | None = None,
        active_only: bool = True,
    ) -> list[Budget]:
        """Get budgets for an agent."""
        query = select(Budget).where(Budget.agent_id == agent_id)

        if budget_type:
            query = query.where(Budget.budget_type == budget_type)
        if active_only:
            query = query.where(Budget.is_active == True)

        query = query.order_by(Budget.budget_type)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_budget(
        self,
        budget_id: UUID,
        total_limit: int | None = None,
        alert_threshold: float | None = None,
        is_active: bool | None = None,
        config: dict | None = None,
    ) -> Budget:
        """Update a budget."""
        budget = await self.get_budget(budget_id)
        if not budget:
            raise ValueError("Budget not found")

        if total_limit is not None:
            budget.total_limit = total_limit
        if alert_threshold is not None:
            budget.alert_threshold = alert_threshold
        if is_active is not None:
            budget.is_active = is_active
        if config is not None:
            budget.config = config

        # Recalculate exceeded status
        budget.is_exceeded = budget.used_amount >= budget.total_limit

        await self.db.commit()
        await self.db.refresh(budget)

        return budget

    async def reset_budget(self, budget_id: UUID) -> Budget:
        """Reset a budget for new period."""
        budget = await self.get_budget(budget_id)
        if not budget:
            raise ValueError("Budget not found")

        budget.used_amount = 0
        budget.reserved_amount = 0
        budget.period_start = datetime.now(timezone.utc)
        budget.is_exceeded = False
        budget.alert_sent = False

        # Calculate new period end
        if budget.period_type == "hourly":
            budget.period_end = budget.period_start + timedelta(hours=1)
        elif budget.period_type == "daily":
            budget.period_end = budget.period_start + timedelta(days=1)
        elif budget.period_type == "weekly":
            budget.period_end = budget.period_start + timedelta(weeks=1)
        elif budget.period_type == "monthly":
            budget.period_end = budget.period_start + timedelta(days=30)
        elif budget.period_type == "yearly":
            budget.period_end = budget.period_start + timedelta(days=365)

        await self.db.commit()
        await self.db.refresh(budget)

        return budget

    # ==================== Estimates ====================

    async def estimate(
        self,
        agent_id: UUID,
        budget_type: BudgetType,
        estimated_amount: int,
    ) -> dict:
        """Estimate if an action fits in budget."""
        budgets = await self.get_budgets(agent_id, budget_type)

        if not budgets:
            return {
                "budget_type": budget_type.value,
                "estimated_amount": estimated_amount,
                "current_available": 0,
                "fits_in_budget": False,
                "remaining_after": 0,
                "usage_percent_after": 100.0,
                "warning": "No budget configured for this type",
            }

        # Use first matching budget
        budget = budgets[0]
        available = budget.total_limit - budget.used_amount - budget.reserved_amount
        fits = estimated_amount <= available
        remaining = available - estimated_amount
        usage_after = ((budget.used_amount + estimated_amount) / budget.total_limit * 100
                       if budget.total_limit > 0 else 100)

        warning = None
        if not fits:
            warning = f"Insufficient budget: need {estimated_amount}, have {available}"
        elif usage_after > budget.alert_threshold * 100:
            warning = f"Action would use {usage_after:.1f}% of budget"

        return {
            "budget_type": budget_type.value,
            "estimated_amount": estimated_amount,
            "current_available": available,
            "fits_in_budget": fits,
            "remaining_after": max(0, remaining),
            "usage_percent_after": min(100, usage_after),
            "warning": warning,
        }

    # ==================== Reservations ====================

    async def reserve(
        self,
        budget_id: UUID,
        agent_id: UUID,
        amount: int,
        purpose: str | None = None,
        expires_in_seconds: int = 3600,
        task_id: UUID | None = None,
        goal_id: UUID | None = None,
    ) -> Reservation:
        """Reserve budget for a task."""
        budget = await self.get_budget(budget_id)
        if not budget:
            raise ValueError("Budget not found")

        if budget.agent_id != agent_id:
            raise ValueError("Budget does not belong to agent")

        available = budget.total_limit - budget.used_amount - budget.reserved_amount
        if amount > available:
            raise ValueError(f"Insufficient budget: need {amount}, have {available}")

        reservation = Reservation(
            budget_id=budget_id,
            agent_id=agent_id,
            amount=amount,
            purpose=purpose,
            status=ReservationStatus.CONFIRMED,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds),
            task_id=task_id,
            goal_id=goal_id,
        )
        self.db.add(reservation)

        # Update budget reserved amount
        budget.reserved_amount += amount

        await self.db.commit()
        await self.db.refresh(reservation)

        return reservation

    async def consume_reservation(
        self,
        reservation_id: UUID,
        actual_amount: int,
    ) -> Reservation:
        """Consume a reservation (convert to usage)."""
        result = await self.db.execute(
            select(Reservation).where(Reservation.id == reservation_id)
        )
        reservation = result.scalar_one_or_none()

        if not reservation:
            raise ValueError("Reservation not found")

        if reservation.status != ReservationStatus.CONFIRMED:
            raise ValueError(f"Reservation is {reservation.status.value}")

        budget = await self.get_budget(reservation.budget_id)
        if not budget:
            raise ValueError("Budget not found")

        # Update reservation
        reservation.status = ReservationStatus.CONSUMED
        reservation.actual_amount = actual_amount
        reservation.consumed_at = datetime.now(timezone.utc)

        # Update budget
        budget.reserved_amount -= reservation.amount
        budget.used_amount += actual_amount

        # Check if exceeded
        if budget.used_amount >= budget.total_limit:
            budget.is_exceeded = True

        # Check alert threshold
        usage_percent = budget.used_amount / budget.total_limit
        if usage_percent >= budget.alert_threshold and not budget.alert_sent:
            budget.alert_sent = True
            # In a real system, send alert notification here

        # Record usage
        usage = UsageRecord(
            budget_id=budget.id,
            agent_id=reservation.agent_id,
            reservation_id=reservation.id,
            amount=actual_amount,
            action="reservation_consumed",
            description=reservation.purpose,
        )
        self.db.add(usage)

        await self.db.commit()
        await self.db.refresh(reservation)

        return reservation

    async def release_reservation(
        self,
        reservation_id: UUID,
    ) -> Reservation:
        """Release a reservation without consuming."""
        result = await self.db.execute(
            select(Reservation).where(Reservation.id == reservation_id)
        )
        reservation = result.scalar_one_or_none()

        if not reservation:
            raise ValueError("Reservation not found")

        if reservation.status != ReservationStatus.CONFIRMED:
            raise ValueError(f"Reservation is {reservation.status.value}")

        budget = await self.get_budget(reservation.budget_id)
        if not budget:
            raise ValueError("Budget not found")

        # Update reservation
        reservation.status = ReservationStatus.RELEASED
        reservation.released_at = datetime.now(timezone.utc)

        # Update budget
        budget.reserved_amount -= reservation.amount

        await self.db.commit()
        await self.db.refresh(reservation)

        return reservation

    async def expire_stale_reservations(self) -> int:
        """Expire reservations past their expiration time."""
        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(Reservation).where(
                and_(
                    Reservation.status == ReservationStatus.CONFIRMED,
                    Reservation.expires_at < now,
                )
            )
        )
        stale = list(result.scalars().all())

        count = 0
        for reservation in stale:
            budget = await self.get_budget(reservation.budget_id)
            if budget:
                budget.reserved_amount -= reservation.amount
            reservation.status = ReservationStatus.EXPIRED
            count += 1

        if count > 0:
            await self.db.commit()

        return count

    # ==================== Usage ====================

    async def record_usage(
        self,
        budget_id: UUID,
        agent_id: UUID,
        amount: int,
        action: str,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> UsageRecord:
        """Record direct usage (without reservation)."""
        budget = await self.get_budget(budget_id)
        if not budget:
            raise ValueError("Budget not found")

        if budget.agent_id != agent_id:
            raise ValueError("Budget does not belong to agent")

        # Update budget
        budget.used_amount += amount

        # Check if exceeded
        if budget.used_amount >= budget.total_limit:
            budget.is_exceeded = True

        # Check alert
        usage_percent = budget.used_amount / budget.total_limit
        if usage_percent >= budget.alert_threshold and not budget.alert_sent:
            budget.alert_sent = True

        # Record usage
        usage = UsageRecord(
            budget_id=budget_id,
            agent_id=agent_id,
            amount=amount,
            action=action,
            description=description,
            metadata_=metadata or {},
        )
        self.db.add(usage)

        await self.db.commit()
        await self.db.refresh(usage)

        return usage

    async def get_usage_history(
        self,
        budget_id: UUID,
        limit: int = 100,
    ) -> list[UsageRecord]:
        """Get usage history for a budget."""
        result = await self.db.execute(
            select(UsageRecord)
            .where(UsageRecord.budget_id == budget_id)
            .order_by(UsageRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ==================== Summary ====================

    async def get_summary(self, agent_id: UUID) -> dict:
        """Get budget summary for an agent."""
        budgets = await self.get_budgets(agent_id)

        alerts = []
        for budget in budgets:
            if budget.is_exceeded:
                alerts.append({
                    "budget_id": str(budget.id),
                    "type": "exceeded",
                    "message": f"Budget '{budget.name}' is exceeded",
                })
            elif budget.used_amount / budget.total_limit >= budget.alert_threshold:
                alerts.append({
                    "budget_id": str(budget.id),
                    "type": "threshold",
                    "message": f"Budget '{budget.name}' is at {budget.used_amount / budget.total_limit * 100:.0f}%",
                })

        return {
            "total_budgets": len(budgets),
            "budgets": budgets,
            "alerts": alerts,
        }
