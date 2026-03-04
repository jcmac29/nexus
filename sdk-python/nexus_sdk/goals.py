"""Goals SDK - Persistent objectives with milestones and delegations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx


class Goals:
    """Synchronous client for goal management."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def create(
        self,
        title: str,
        description: str | None = None,
        success_criteria: str | None = None,
        goal_type: str = "general",
        tags: list[str] | None = None,
        priority: str = "medium",
        target_date: datetime | str | None = None,
        parent_goal_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new goal.

        Args:
            title: Goal title
            description: Detailed description
            success_criteria: How to know when goal is achieved
            goal_type: Type (general, project, learning, etc.)
            tags: Categorization tags
            priority: Priority (critical, high, medium, low, background)
            target_date: Target completion date
            parent_goal_id: Parent goal if this is a sub-goal

        Returns:
            Created goal
        """
        data: dict[str, Any] = {
            "title": title,
            "description": description,
            "success_criteria": success_criteria,
            "goal_type": goal_type,
            "tags": tags or [],
            "priority": priority,
        }
        if target_date:
            data["target_date"] = target_date.isoformat() if isinstance(target_date, datetime) else target_date
        if parent_goal_id:
            data["parent_goal_id"] = parent_goal_id
        response = self._client.post("/goals", json=data)
        response.raise_for_status()
        return response.json()

    def get(self, goal_id: str) -> dict[str, Any]:
        """Get a goal by ID."""
        response = self._client.get(f"/goals/{goal_id}")
        response.raise_for_status()
        return response.json()

    def list(
        self,
        status: str | None = None,
        priority: str | None = None,
        include_completed: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List goals."""
        params: dict[str, Any] = {"limit": limit, "include_completed": str(include_completed).lower()}
        if status:
            params["status"] = status
        if priority:
            params["priority"] = priority
        response = self._client.get("/goals", params=params)
        response.raise_for_status()
        return response.json()

    def activate(self, goal_id: str) -> dict[str, Any]:
        """Activate a draft goal."""
        response = self._client.post(f"/goals/{goal_id}/activate")
        response.raise_for_status()
        return response.json()

    def start(self, goal_id: str) -> dict[str, Any]:
        """Start working on a goal."""
        response = self._client.post(f"/goals/{goal_id}/start")
        response.raise_for_status()
        return response.json()

    def update_progress(
        self,
        goal_id: str,
        progress_percent: int,
        progress_notes: str | None = None,
    ) -> dict[str, Any]:
        """Update goal progress."""
        response = self._client.post(
            f"/goals/{goal_id}/progress",
            json={"progress_percent": progress_percent, "progress_notes": progress_notes},
        )
        response.raise_for_status()
        return response.json()

    def complete(
        self,
        goal_id: str,
        outcome: str | None = None,
        outcome_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Complete a goal."""
        response = self._client.post(
            f"/goals/{goal_id}/complete",
            json={"outcome": outcome, "outcome_data": outcome_data or {}},
        )
        response.raise_for_status()
        return response.json()

    def fail(self, goal_id: str, outcome: str | None = None) -> dict[str, Any]:
        """Mark a goal as failed."""
        response = self._client.post(f"/goals/{goal_id}/fail", json={"outcome": outcome})
        response.raise_for_status()
        return response.json()

    def cancel(self, goal_id: str, reason: str | None = None) -> dict[str, Any]:
        """Cancel a goal."""
        response = self._client.post(f"/goals/{goal_id}/cancel", json={"reason": reason})
        response.raise_for_status()
        return response.json()

    # Milestones
    def add_milestone(
        self,
        goal_id: str,
        title: str,
        description: str | None = None,
        order: int = 0,
        weight: float = 1.0,
        target_date: datetime | str | None = None,
    ) -> dict[str, Any]:
        """Add a milestone to a goal."""
        data: dict[str, Any] = {
            "title": title,
            "description": description,
            "order": order,
            "weight": weight,
        }
        if target_date:
            data["target_date"] = target_date.isoformat() if isinstance(target_date, datetime) else target_date
        response = self._client.post(f"/goals/{goal_id}/milestones", json=data)
        response.raise_for_status()
        return response.json()

    def complete_milestone(self, milestone_id: str) -> dict[str, Any]:
        """Complete a milestone."""
        response = self._client.post(f"/goals/milestones/{milestone_id}/complete")
        response.raise_for_status()
        return response.json()

    # Blockers
    def add_blocker(
        self,
        goal_id: str,
        title: str,
        blocker_type: str,
        description: str | None = None,
        severity: str = "medium",
        blocking_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Add a blocker to a goal."""
        response = self._client.post(
            f"/goals/{goal_id}/blockers",
            json={
                "title": title,
                "blocker_type": blocker_type,
                "description": description,
                "severity": severity,
                "blocking_agent_id": blocking_agent_id,
            },
        )
        response.raise_for_status()
        return response.json()

    def resolve_blocker(self, blocker_id: str, resolution: str) -> dict[str, Any]:
        """Resolve a blocker."""
        response = self._client.post(
            f"/goals/blockers/{blocker_id}/resolve",
            json={"resolution": resolution},
        )
        response.raise_for_status()
        return response.json()

    # Delegations
    def delegate(
        self,
        goal_id: str,
        delegate_id: str,
        title: str,
        description: str | None = None,
        scope: dict[str, Any] | None = None,
        deadline: datetime | str | None = None,
    ) -> dict[str, Any]:
        """Delegate part of a goal to another agent."""
        data: dict[str, Any] = {
            "delegate_id": delegate_id,
            "title": title,
            "description": description,
            "scope": scope or {},
        }
        if deadline:
            data["deadline"] = deadline.isoformat() if isinstance(deadline, datetime) else deadline
        response = self._client.post(f"/goals/{goal_id}/delegate", json=data)
        response.raise_for_status()
        return response.json()

    def get_incoming_delegations(self, status: str | None = None) -> list[dict[str, Any]]:
        """Get delegations assigned to me."""
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        response = self._client.get("/goals/delegations/incoming", params=params)
        response.raise_for_status()
        return response.json()

    def accept_delegation(self, delegation_id: str) -> dict[str, Any]:
        """Accept a delegation."""
        response = self._client.post(f"/goals/delegations/{delegation_id}/accept")
        response.raise_for_status()
        return response.json()

    def reject_delegation(self, delegation_id: str) -> dict[str, Any]:
        """Reject a delegation."""
        response = self._client.post(f"/goals/delegations/{delegation_id}/reject")
        response.raise_for_status()
        return response.json()


class GoalsAsync:
    """Asynchronous client for goal management."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def create(
        self,
        title: str,
        description: str | None = None,
        success_criteria: str | None = None,
        goal_type: str = "general",
        tags: list[str] | None = None,
        priority: str = "medium",
        target_date: datetime | str | None = None,
        parent_goal_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new goal."""
        data: dict[str, Any] = {
            "title": title,
            "description": description,
            "success_criteria": success_criteria,
            "goal_type": goal_type,
            "tags": tags or [],
            "priority": priority,
        }
        if target_date:
            data["target_date"] = target_date.isoformat() if isinstance(target_date, datetime) else target_date
        if parent_goal_id:
            data["parent_goal_id"] = parent_goal_id
        response = await self._client.post("/goals", json=data)
        response.raise_for_status()
        return response.json()

    async def get(self, goal_id: str) -> dict[str, Any]:
        """Get a goal by ID."""
        response = await self._client.get(f"/goals/{goal_id}")
        response.raise_for_status()
        return response.json()

    async def list(
        self,
        status: str | None = None,
        priority: str | None = None,
        include_completed: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List goals."""
        params: dict[str, Any] = {"limit": limit, "include_completed": str(include_completed).lower()}
        if status:
            params["status"] = status
        if priority:
            params["priority"] = priority
        response = await self._client.get("/goals", params=params)
        response.raise_for_status()
        return response.json()

    async def activate(self, goal_id: str) -> dict[str, Any]:
        """Activate a draft goal."""
        response = await self._client.post(f"/goals/{goal_id}/activate")
        response.raise_for_status()
        return response.json()

    async def start(self, goal_id: str) -> dict[str, Any]:
        """Start working on a goal."""
        response = await self._client.post(f"/goals/{goal_id}/start")
        response.raise_for_status()
        return response.json()

    async def update_progress(
        self,
        goal_id: str,
        progress_percent: int,
        progress_notes: str | None = None,
    ) -> dict[str, Any]:
        """Update goal progress."""
        response = await self._client.post(
            f"/goals/{goal_id}/progress",
            json={"progress_percent": progress_percent, "progress_notes": progress_notes},
        )
        response.raise_for_status()
        return response.json()

    async def complete(
        self,
        goal_id: str,
        outcome: str | None = None,
        outcome_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Complete a goal."""
        response = await self._client.post(
            f"/goals/{goal_id}/complete",
            json={"outcome": outcome, "outcome_data": outcome_data or {}},
        )
        response.raise_for_status()
        return response.json()

    async def fail(self, goal_id: str, outcome: str | None = None) -> dict[str, Any]:
        """Mark a goal as failed."""
        response = await self._client.post(f"/goals/{goal_id}/fail", json={"outcome": outcome})
        response.raise_for_status()
        return response.json()

    async def cancel(self, goal_id: str, reason: str | None = None) -> dict[str, Any]:
        """Cancel a goal."""
        response = await self._client.post(f"/goals/{goal_id}/cancel", json={"reason": reason})
        response.raise_for_status()
        return response.json()

    async def add_milestone(
        self,
        goal_id: str,
        title: str,
        description: str | None = None,
        order: int = 0,
        weight: float = 1.0,
        target_date: datetime | str | None = None,
    ) -> dict[str, Any]:
        """Add a milestone to a goal."""
        data: dict[str, Any] = {"title": title, "description": description, "order": order, "weight": weight}
        if target_date:
            data["target_date"] = target_date.isoformat() if isinstance(target_date, datetime) else target_date
        response = await self._client.post(f"/goals/{goal_id}/milestones", json=data)
        response.raise_for_status()
        return response.json()

    async def complete_milestone(self, milestone_id: str) -> dict[str, Any]:
        """Complete a milestone."""
        response = await self._client.post(f"/goals/milestones/{milestone_id}/complete")
        response.raise_for_status()
        return response.json()

    async def add_blocker(
        self,
        goal_id: str,
        title: str,
        blocker_type: str,
        description: str | None = None,
        severity: str = "medium",
        blocking_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Add a blocker to a goal."""
        response = await self._client.post(
            f"/goals/{goal_id}/blockers",
            json={
                "title": title,
                "blocker_type": blocker_type,
                "description": description,
                "severity": severity,
                "blocking_agent_id": blocking_agent_id,
            },
        )
        response.raise_for_status()
        return response.json()

    async def resolve_blocker(self, blocker_id: str, resolution: str) -> dict[str, Any]:
        """Resolve a blocker."""
        response = await self._client.post(f"/goals/blockers/{blocker_id}/resolve", json={"resolution": resolution})
        response.raise_for_status()
        return response.json()

    async def delegate(
        self,
        goal_id: str,
        delegate_id: str,
        title: str,
        description: str | None = None,
        scope: dict[str, Any] | None = None,
        deadline: datetime | str | None = None,
    ) -> dict[str, Any]:
        """Delegate part of a goal to another agent."""
        data: dict[str, Any] = {"delegate_id": delegate_id, "title": title, "description": description, "scope": scope or {}}
        if deadline:
            data["deadline"] = deadline.isoformat() if isinstance(deadline, datetime) else deadline
        response = await self._client.post(f"/goals/{goal_id}/delegate", json=data)
        response.raise_for_status()
        return response.json()

    async def get_incoming_delegations(self, status: str | None = None) -> list[dict[str, Any]]:
        """Get delegations assigned to me."""
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        response = await self._client.get("/goals/delegations/incoming", params=params)
        response.raise_for_status()
        return response.json()

    async def accept_delegation(self, delegation_id: str) -> dict[str, Any]:
        """Accept a delegation."""
        response = await self._client.post(f"/goals/delegations/{delegation_id}/accept")
        response.raise_for_status()
        return response.json()

    async def reject_delegation(self, delegation_id: str) -> dict[str, Any]:
        """Reject a delegation."""
        response = await self._client.post(f"/goals/delegations/{delegation_id}/reject")
        response.raise_for_status()
        return response.json()
