"""Swarm SDK - Multi-terminal coordination."""

from __future__ import annotations

from typing import Any

import httpx


class Swarm:
    """Synchronous client for swarm coordination."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def create(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new swarm and become the leader.

        Args:
            name: Name for the swarm
            config: Optional configuration (max_members, task_timeout, etc.)

        Returns:
            Swarm details including join_code for others to join
        """
        response = self._client.post(
            "/swarm",
            json={"name": name, "config": config or {}},
        )
        response.raise_for_status()
        return response.json()

    def join(self, join_code: str, capabilities: list[str] | None = None) -> dict[str, Any]:
        """
        Join an existing swarm using its join code.

        Args:
            join_code: 6-character code from swarm creation
            capabilities: List of capabilities this worker provides

        Returns:
            Membership details
        """
        response = self._client.post(
            "/swarm/join",
            json={"join_code": join_code, "capabilities": capabilities or []},
        )
        response.raise_for_status()
        return response.json()

    def get(self, swarm_id: str) -> dict[str, Any]:
        """Get swarm status and member list."""
        response = self._client.get(f"/swarm/{swarm_id}")
        response.raise_for_status()
        return response.json()

    def leave(self, swarm_id: str) -> dict[str, Any]:
        """Leave a swarm."""
        response = self._client.post(f"/swarm/{swarm_id}/leave")
        response.raise_for_status()
        return response.json()

    def disband(self, swarm_id: str) -> dict[str, Any]:
        """Disband a swarm (leader only)."""
        response = self._client.delete(f"/swarm/{swarm_id}")
        response.raise_for_status()
        return response.json()

    def submit_task(
        self,
        swarm_id: str,
        title: str,
        description: str | None = None,
        task_type: str = "general",
        priority: int = 5,
        input_data: dict[str, Any] | None = None,
        required_capabilities: list[str] | None = None,
        timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        """
        Submit a task to the swarm for distribution.

        Args:
            swarm_id: ID of the swarm
            title: Task title
            description: Detailed description
            task_type: Type of task (code_review, test, analyze, etc.)
            priority: Priority (1=highest, 10=lowest)
            input_data: Data for the task
            required_capabilities: Capabilities needed to execute
            timeout_seconds: Task timeout

        Returns:
            Created task details
        """
        response = self._client.post(
            f"/swarm/{swarm_id}/tasks",
            json={
                "title": title,
                "description": description,
                "task_type": task_type,
                "priority": priority,
                "input_data": input_data or {},
                "required_capabilities": required_capabilities or [],
                "timeout_seconds": timeout_seconds,
            },
        )
        response.raise_for_status()
        return response.json()

    def submit_batch(
        self,
        swarm_id: str,
        tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Submit multiple tasks at once.

        Args:
            swarm_id: ID of the swarm
            tasks: List of task definitions

        Returns:
            List of created tasks
        """
        response = self._client.post(
            f"/swarm/{swarm_id}/tasks/batch",
            json={"tasks": tasks},
        )
        response.raise_for_status()
        return response.json()

    def claim_task(self) -> dict[str, Any] | None:
        """
        Claim the next available task as a worker.

        Returns:
            Task to work on, or None if no tasks available
        """
        response = self._client.post("/swarm/tasks/claim")
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json()

    def complete_task(
        self,
        task_id: str,
        output_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Mark a task as completed with results.

        Args:
            task_id: ID of the task
            output_data: Results from the task

        Returns:
            Updated task details
        """
        response = self._client.post(
            f"/swarm/tasks/{task_id}/complete",
            json={"output_data": output_data or {}},
        )
        response.raise_for_status()
        return response.json()

    def fail_task(self, task_id: str, error_message: str) -> dict[str, Any]:
        """
        Mark a task as failed.

        Args:
            task_id: ID of the task
            error_message: Description of the failure

        Returns:
            Updated task details
        """
        response = self._client.post(
            f"/swarm/tasks/{task_id}/fail",
            json={"error_message": error_message},
        )
        response.raise_for_status()
        return response.json()

    def list_tasks(
        self,
        swarm_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List tasks in a swarm."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        response = self._client.get(f"/swarm/{swarm_id}/tasks", params=params)
        response.raise_for_status()
        return response.json()

    def get_results(self, swarm_id: str) -> list[dict[str, Any]]:
        """Get aggregated results from all completed tasks."""
        response = self._client.get(f"/swarm/{swarm_id}/results")
        response.raise_for_status()
        return response.json()


class SwarmAsync:
    """Asynchronous client for swarm coordination."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def create(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new swarm and become the leader."""
        response = await self._client.post(
            "/swarm",
            json={"name": name, "config": config or {}},
        )
        response.raise_for_status()
        return response.json()

    async def join(self, join_code: str, capabilities: list[str] | None = None) -> dict[str, Any]:
        """Join an existing swarm using its join code."""
        response = await self._client.post(
            "/swarm/join",
            json={"join_code": join_code, "capabilities": capabilities or []},
        )
        response.raise_for_status()
        return response.json()

    async def get(self, swarm_id: str) -> dict[str, Any]:
        """Get swarm status and member list."""
        response = await self._client.get(f"/swarm/{swarm_id}")
        response.raise_for_status()
        return response.json()

    async def leave(self, swarm_id: str) -> dict[str, Any]:
        """Leave a swarm."""
        response = await self._client.post(f"/swarm/{swarm_id}/leave")
        response.raise_for_status()
        return response.json()

    async def disband(self, swarm_id: str) -> dict[str, Any]:
        """Disband a swarm (leader only)."""
        response = await self._client.delete(f"/swarm/{swarm_id}")
        response.raise_for_status()
        return response.json()

    async def submit_task(
        self,
        swarm_id: str,
        title: str,
        description: str | None = None,
        task_type: str = "general",
        priority: int = 5,
        input_data: dict[str, Any] | None = None,
        required_capabilities: list[str] | None = None,
        timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        """Submit a task to the swarm for distribution."""
        response = await self._client.post(
            f"/swarm/{swarm_id}/tasks",
            json={
                "title": title,
                "description": description,
                "task_type": task_type,
                "priority": priority,
                "input_data": input_data or {},
                "required_capabilities": required_capabilities or [],
                "timeout_seconds": timeout_seconds,
            },
        )
        response.raise_for_status()
        return response.json()

    async def submit_batch(
        self,
        swarm_id: str,
        tasks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Submit multiple tasks at once."""
        response = await self._client.post(
            f"/swarm/{swarm_id}/tasks/batch",
            json={"tasks": tasks},
        )
        response.raise_for_status()
        return response.json()

    async def claim_task(self) -> dict[str, Any] | None:
        """Claim the next available task as a worker."""
        response = await self._client.post("/swarm/tasks/claim")
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json()

    async def complete_task(
        self,
        task_id: str,
        output_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Mark a task as completed with results."""
        response = await self._client.post(
            f"/swarm/tasks/{task_id}/complete",
            json={"output_data": output_data or {}},
        )
        response.raise_for_status()
        return response.json()

    async def fail_task(self, task_id: str, error_message: str) -> dict[str, Any]:
        """Mark a task as failed."""
        response = await self._client.post(
            f"/swarm/tasks/{task_id}/fail",
            json={"error_message": error_message},
        )
        response.raise_for_status()
        return response.json()

    async def list_tasks(
        self,
        swarm_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List tasks in a swarm."""
        params = {"limit": limit}
        if status:
            params["status"] = status
        response = await self._client.get(f"/swarm/{swarm_id}/tasks", params=params)
        response.raise_for_status()
        return response.json()

    async def get_results(self, swarm_id: str) -> list[dict[str, Any]]:
        """Get aggregated results from all completed tasks."""
        response = await self._client.get(f"/swarm/{swarm_id}/results")
        response.raise_for_status()
        return response.json()
