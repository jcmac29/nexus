"""Vitals SDK - Agent health monitoring and performance metrics."""

from __future__ import annotations

from typing import Any

import httpx


class Vitals:
    """Synchronous client for vitals management."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def get(self, agent_id: str | None = None) -> dict[str, Any]:
        """
        Get vitals for an agent.

        Args:
            agent_id: Agent ID (defaults to self)

        Returns:
            Agent vitals with health status and metrics
        """
        path = f"/vitals/{agent_id}" if agent_id else "/vitals/me"
        response = self._client.get(path)
        response.raise_for_status()
        return response.json()

    def update(
        self,
        is_online: bool | None = None,
        is_busy: bool | None = None,
        current_load: float | None = None,
        max_concurrent_tasks: int | None = None,
        current_tasks: int | None = None,
        queue_depth: int | None = None,
        estimated_wait_seconds: int | None = None,
        capabilities_status: dict[str, str] | None = None,
        agent_version: str | None = None,
    ) -> dict[str, Any]:
        """
        Update vitals for the current agent.

        Args:
            is_online: Whether agent is online
            is_busy: Whether agent is busy
            current_load: Current load (0.0-1.0)
            max_concurrent_tasks: Max concurrent tasks
            current_tasks: Current number of tasks
            queue_depth: Number of items in queue
            estimated_wait_seconds: Estimated wait time
            capabilities_status: Status of each capability (e.g., {"code_review": "available"})
            agent_version: Current version of the agent

        Returns:
            Updated vitals
        """
        data: dict[str, Any] = {}
        if is_online is not None:
            data["is_online"] = is_online
        if is_busy is not None:
            data["is_busy"] = is_busy
        if current_load is not None:
            data["current_load"] = current_load
        if max_concurrent_tasks is not None:
            data["max_concurrent_tasks"] = max_concurrent_tasks
        if current_tasks is not None:
            data["current_tasks"] = current_tasks
        if queue_depth is not None:
            data["queue_depth"] = queue_depth
        if estimated_wait_seconds is not None:
            data["estimated_wait_seconds"] = estimated_wait_seconds
        if capabilities_status is not None:
            data["capabilities_status"] = capabilities_status
        if agent_version is not None:
            data["agent_version"] = agent_version
        response = self._client.patch("/vitals/me", json=data)
        response.raise_for_status()
        return response.json()

    def heartbeat(self) -> dict[str, Any]:
        """
        Send a heartbeat to indicate the agent is alive.

        Returns:
            Heartbeat response with status and missed heartbeats count
        """
        response = self._client.post("/vitals/heartbeat")
        response.raise_for_status()
        return response.json()

    def subscribe(
        self,
        target_agent_id: str,
        notify_on: list[str] | None = None,
        threshold_load: float | None = None,
        threshold_error_rate: float | None = None,
        threshold_response_time_ms: int | None = None,
        webhook_url: str | None = None,
    ) -> dict[str, Any]:
        """
        Subscribe to another agent's vitals updates.

        Args:
            target_agent_id: Agent to subscribe to
            notify_on: Events to notify on (status_change, offline, degraded, error_spike, load_high)
            threshold_load: Alert when load exceeds this value
            threshold_error_rate: Alert when error rate exceeds this value
            threshold_response_time_ms: Alert when response time exceeds this
            webhook_url: URL to send notifications to

        Returns:
            Subscription details
        """
        response = self._client.post(
            f"/vitals/{target_agent_id}/subscribe",
            json={
                "notify_on": notify_on or ["status_change", "offline"],
                "threshold_load": threshold_load,
                "threshold_error_rate": threshold_error_rate,
                "threshold_response_time_ms": threshold_response_time_ms,
                "webhook_url": webhook_url,
            },
        )
        response.raise_for_status()
        return response.json()

    def unsubscribe(self, subscription_id: str) -> dict[str, Any]:
        """Unsubscribe from vitals updates."""
        response = self._client.delete(f"/vitals/subscriptions/{subscription_id}")
        response.raise_for_status()
        return response.json()

    def list_subscriptions(self, active_only: bool = True) -> list[dict[str, Any]]:
        """List vitals subscriptions."""
        response = self._client.get("/vitals/subscriptions", params={"active_only": str(active_only).lower()})
        response.raise_for_status()
        return response.json()

    def find_healthy(
        self,
        capability: str | None = None,
        max_load: float = 0.8,
        max_response_time_ms: int | None = None,
        require_online: bool = True,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Find healthy agents matching criteria.

        Args:
            capability: Required capability
            max_load: Maximum load threshold
            max_response_time_ms: Maximum response time
            require_online: Must be online
            limit: Maximum results

        Returns:
            List of healthy agents with their vitals
        """
        response = self._client.post(
            "/vitals/find-healthy",
            json={
                "capability": capability,
                "max_load": max_load,
                "max_response_time_ms": max_response_time_ms,
                "require_online": require_online,
                "limit": limit,
            },
        )
        response.raise_for_status()
        return response.json()

    def find_best(
        self,
        capability: str | None = None,
        max_load: float = 0.8,
    ) -> dict[str, Any] | None:
        """
        Find the best healthy agent for a task.

        Args:
            capability: Required capability
            max_load: Maximum load threshold

        Returns:
            Best agent or None if none available
        """
        params: dict[str, Any] = {"max_load": max_load}
        if capability:
            params["capability"] = capability
        response = self._client.get("/vitals/best", params=params)
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json()

    def take_snapshot(self) -> dict[str, Any]:
        """Take a snapshot of current vitals."""
        response = self._client.post("/vitals/snapshot")
        response.raise_for_status()
        return response.json()

    def get_snapshots(
        self,
        agent_id: str,
        hours: int = 24,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get historical vitals snapshots."""
        response = self._client.get(
            f"/vitals/{agent_id}/snapshots",
            params={"hours": hours, "limit": limit},
        )
        response.raise_for_status()
        return response.json()


class VitalsAsync:
    """Asynchronous client for vitals management."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def get(self, agent_id: str | None = None) -> dict[str, Any]:
        """Get vitals for an agent."""
        path = f"/vitals/{agent_id}" if agent_id else "/vitals/me"
        response = await self._client.get(path)
        response.raise_for_status()
        return response.json()

    async def update(
        self,
        is_online: bool | None = None,
        is_busy: bool | None = None,
        current_load: float | None = None,
        max_concurrent_tasks: int | None = None,
        current_tasks: int | None = None,
        queue_depth: int | None = None,
        estimated_wait_seconds: int | None = None,
        capabilities_status: dict[str, str] | None = None,
        agent_version: str | None = None,
    ) -> dict[str, Any]:
        """Update vitals for the current agent."""
        data: dict[str, Any] = {}
        if is_online is not None:
            data["is_online"] = is_online
        if is_busy is not None:
            data["is_busy"] = is_busy
        if current_load is not None:
            data["current_load"] = current_load
        if max_concurrent_tasks is not None:
            data["max_concurrent_tasks"] = max_concurrent_tasks
        if current_tasks is not None:
            data["current_tasks"] = current_tasks
        if queue_depth is not None:
            data["queue_depth"] = queue_depth
        if estimated_wait_seconds is not None:
            data["estimated_wait_seconds"] = estimated_wait_seconds
        if capabilities_status is not None:
            data["capabilities_status"] = capabilities_status
        if agent_version is not None:
            data["agent_version"] = agent_version
        response = await self._client.patch("/vitals/me", json=data)
        response.raise_for_status()
        return response.json()

    async def heartbeat(self) -> dict[str, Any]:
        """Send a heartbeat to indicate the agent is alive."""
        response = await self._client.post("/vitals/heartbeat")
        response.raise_for_status()
        return response.json()

    async def subscribe(
        self,
        target_agent_id: str,
        notify_on: list[str] | None = None,
        threshold_load: float | None = None,
        threshold_error_rate: float | None = None,
        threshold_response_time_ms: int | None = None,
        webhook_url: str | None = None,
    ) -> dict[str, Any]:
        """Subscribe to another agent's vitals updates."""
        response = await self._client.post(
            f"/vitals/{target_agent_id}/subscribe",
            json={
                "notify_on": notify_on or ["status_change", "offline"],
                "threshold_load": threshold_load,
                "threshold_error_rate": threshold_error_rate,
                "threshold_response_time_ms": threshold_response_time_ms,
                "webhook_url": webhook_url,
            },
        )
        response.raise_for_status()
        return response.json()

    async def unsubscribe(self, subscription_id: str) -> dict[str, Any]:
        """Unsubscribe from vitals updates."""
        response = await self._client.delete(f"/vitals/subscriptions/{subscription_id}")
        response.raise_for_status()
        return response.json()

    async def list_subscriptions(self, active_only: bool = True) -> list[dict[str, Any]]:
        """List vitals subscriptions."""
        response = await self._client.get("/vitals/subscriptions", params={"active_only": str(active_only).lower()})
        response.raise_for_status()
        return response.json()

    async def find_healthy(
        self,
        capability: str | None = None,
        max_load: float = 0.8,
        max_response_time_ms: int | None = None,
        require_online: bool = True,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find healthy agents matching criteria."""
        response = await self._client.post(
            "/vitals/find-healthy",
            json={
                "capability": capability,
                "max_load": max_load,
                "max_response_time_ms": max_response_time_ms,
                "require_online": require_online,
                "limit": limit,
            },
        )
        response.raise_for_status()
        return response.json()

    async def find_best(
        self,
        capability: str | None = None,
        max_load: float = 0.8,
    ) -> dict[str, Any] | None:
        """Find the best healthy agent for a task."""
        params: dict[str, Any] = {"max_load": max_load}
        if capability:
            params["capability"] = capability
        response = await self._client.get("/vitals/best", params=params)
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json()

    async def take_snapshot(self) -> dict[str, Any]:
        """Take a snapshot of current vitals."""
        response = await self._client.post("/vitals/snapshot")
        response.raise_for_status()
        return response.json()

    async def get_snapshots(
        self,
        agent_id: str,
        hours: int = 24,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get historical vitals snapshots."""
        response = await self._client.get(
            f"/vitals/{agent_id}/snapshots",
            params={"hours": hours, "limit": limit},
        )
        response.raise_for_status()
        return response.json()
