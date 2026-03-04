"""Budgets SDK - Resource quotas and reservations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx


class Budgets:
    """Synchronous client for budget management."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def create(
        self,
        budget_type: str,
        name: str,
        total_limit: int,
        description: str | None = None,
        period_type: str = "monthly",
        alert_threshold: float = 0.8,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new budget.

        Args:
            budget_type: Type (api_calls, tokens, credits, compute_seconds, storage_bytes, bandwidth_bytes, custom)
            name: Budget name
            total_limit: Maximum limit for the budget
            description: Budget description
            period_type: Period (hourly, daily, weekly, monthly, yearly, lifetime)
            alert_threshold: Alert when usage exceeds this percentage (0.0-1.0)
            config: Additional configuration

        Returns:
            Created budget
        """
        response = self._client.post(
            "/budgets",
            json={
                "budget_type": budget_type,
                "name": name,
                "total_limit": total_limit,
                "description": description,
                "period_type": period_type,
                "alert_threshold": alert_threshold,
                "config": config or {},
            },
        )
        response.raise_for_status()
        return response.json()

    def list(
        self,
        budget_type: str | None = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """List budgets."""
        params: dict[str, Any] = {"active_only": str(active_only).lower()}
        if budget_type:
            params["budget_type"] = budget_type
        response = self._client.get("/budgets", params=params)
        response.raise_for_status()
        return response.json()

    def get(self, budget_id: str) -> dict[str, Any]:
        """Get a budget by ID."""
        response = self._client.get(f"/budgets/{budget_id}")
        response.raise_for_status()
        return response.json()

    def get_summary(self) -> dict[str, Any]:
        """Get budget summary for the current agent."""
        response = self._client.get("/budgets/me")
        response.raise_for_status()
        return response.json()

    def update(
        self,
        budget_id: str,
        total_limit: int | None = None,
        alert_threshold: float | None = None,
        is_active: bool | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a budget."""
        data: dict[str, Any] = {}
        if total_limit is not None:
            data["total_limit"] = total_limit
        if alert_threshold is not None:
            data["alert_threshold"] = alert_threshold
        if is_active is not None:
            data["is_active"] = is_active
        if config is not None:
            data["config"] = config
        response = self._client.patch(f"/budgets/{budget_id}", json=data)
        response.raise_for_status()
        return response.json()

    def reset(self, budget_id: str) -> dict[str, Any]:
        """Reset a budget for a new period."""
        response = self._client.post(f"/budgets/{budget_id}/reset")
        response.raise_for_status()
        return response.json()

    def estimate(
        self,
        budget_type: str,
        estimated_amount: int,
    ) -> dict[str, Any]:
        """
        Estimate if an action fits in budget.

        Args:
            budget_type: Type of budget
            estimated_amount: Amount to estimate

        Returns:
            Estimation including fits_in_budget, remaining_after, warning
        """
        response = self._client.post(
            "/budgets/estimate",
            json={"budget_type": budget_type, "estimated_amount": estimated_amount},
        )
        response.raise_for_status()
        return response.json()

    def reserve(
        self,
        budget_id: str,
        amount: int,
        purpose: str | None = None,
        expires_in_seconds: int = 300,
        task_id: str | None = None,
        goal_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Reserve budget for a task.

        Args:
            budget_id: Budget to reserve from
            amount: Amount to reserve
            purpose: What the reservation is for
            expires_in_seconds: How long until reservation expires
            task_id: Related task ID
            goal_id: Related goal ID

        Returns:
            Created reservation
        """
        response = self._client.post(
            "/budgets/reserve",
            json={
                "budget_id": budget_id,
                "amount": amount,
                "purpose": purpose,
                "expires_in_seconds": expires_in_seconds,
                "task_id": task_id,
                "goal_id": goal_id,
            },
        )
        response.raise_for_status()
        return response.json()

    def consume_reservation(
        self,
        reservation_id: str,
        actual_amount: int | None = None,
    ) -> dict[str, Any]:
        """
        Consume a reservation.

        Args:
            reservation_id: Reservation to consume
            actual_amount: Actual amount used (defaults to reserved amount)

        Returns:
            Updated reservation
        """
        response = self._client.post(
            f"/budgets/reservations/{reservation_id}/consume",
            json={"actual_amount": actual_amount},
        )
        response.raise_for_status()
        return response.json()

    def release_reservation(self, reservation_id: str) -> dict[str, Any]:
        """Release a reservation without consuming it."""
        response = self._client.post(f"/budgets/reservations/{reservation_id}/release")
        response.raise_for_status()
        return response.json()

    def get_usage_history(
        self,
        budget_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get usage history for a budget."""
        response = self._client.get(f"/budgets/{budget_id}/usage", params={"limit": limit})
        response.raise_for_status()
        return response.json()


class BudgetsAsync:
    """Asynchronous client for budget management."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def create(
        self,
        budget_type: str,
        name: str,
        total_limit: int,
        description: str | None = None,
        period_type: str = "monthly",
        alert_threshold: float = 0.8,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new budget."""
        response = await self._client.post(
            "/budgets",
            json={
                "budget_type": budget_type,
                "name": name,
                "total_limit": total_limit,
                "description": description,
                "period_type": period_type,
                "alert_threshold": alert_threshold,
                "config": config or {},
            },
        )
        response.raise_for_status()
        return response.json()

    async def list(
        self,
        budget_type: str | None = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """List budgets."""
        params: dict[str, Any] = {"active_only": str(active_only).lower()}
        if budget_type:
            params["budget_type"] = budget_type
        response = await self._client.get("/budgets", params=params)
        response.raise_for_status()
        return response.json()

    async def get(self, budget_id: str) -> dict[str, Any]:
        """Get a budget by ID."""
        response = await self._client.get(f"/budgets/{budget_id}")
        response.raise_for_status()
        return response.json()

    async def get_summary(self) -> dict[str, Any]:
        """Get budget summary for the current agent."""
        response = await self._client.get("/budgets/me")
        response.raise_for_status()
        return response.json()

    async def update(
        self,
        budget_id: str,
        total_limit: int | None = None,
        alert_threshold: float | None = None,
        is_active: bool | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a budget."""
        data: dict[str, Any] = {}
        if total_limit is not None:
            data["total_limit"] = total_limit
        if alert_threshold is not None:
            data["alert_threshold"] = alert_threshold
        if is_active is not None:
            data["is_active"] = is_active
        if config is not None:
            data["config"] = config
        response = await self._client.patch(f"/budgets/{budget_id}", json=data)
        response.raise_for_status()
        return response.json()

    async def reset(self, budget_id: str) -> dict[str, Any]:
        """Reset a budget for a new period."""
        response = await self._client.post(f"/budgets/{budget_id}/reset")
        response.raise_for_status()
        return response.json()

    async def estimate(
        self,
        budget_type: str,
        estimated_amount: int,
    ) -> dict[str, Any]:
        """Estimate if an action fits in budget."""
        response = await self._client.post(
            "/budgets/estimate",
            json={"budget_type": budget_type, "estimated_amount": estimated_amount},
        )
        response.raise_for_status()
        return response.json()

    async def reserve(
        self,
        budget_id: str,
        amount: int,
        purpose: str | None = None,
        expires_in_seconds: int = 300,
        task_id: str | None = None,
        goal_id: str | None = None,
    ) -> dict[str, Any]:
        """Reserve budget for a task."""
        response = await self._client.post(
            "/budgets/reserve",
            json={
                "budget_id": budget_id,
                "amount": amount,
                "purpose": purpose,
                "expires_in_seconds": expires_in_seconds,
                "task_id": task_id,
                "goal_id": goal_id,
            },
        )
        response.raise_for_status()
        return response.json()

    async def consume_reservation(
        self,
        reservation_id: str,
        actual_amount: int | None = None,
    ) -> dict[str, Any]:
        """Consume a reservation."""
        response = await self._client.post(
            f"/budgets/reservations/{reservation_id}/consume",
            json={"actual_amount": actual_amount},
        )
        response.raise_for_status()
        return response.json()

    async def release_reservation(self, reservation_id: str) -> dict[str, Any]:
        """Release a reservation without consuming it."""
        response = await self._client.post(f"/budgets/reservations/{reservation_id}/release")
        response.raise_for_status()
        return response.json()

    async def get_usage_history(
        self,
        budget_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get usage history for a budget."""
        response = await self._client.get(f"/budgets/{budget_id}/usage", params={"limit": limit})
        response.raise_for_status()
        return response.json()
