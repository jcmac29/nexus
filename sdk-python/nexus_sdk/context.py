"""Context SDK - Context packaging and transfer between agents."""

from __future__ import annotations

from typing import Any

import httpx


class Context:
    """Synchronous client for context management."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def pack(
        self,
        name: str,
        summary: str | None = None,
        goals: dict[str, Any] | None = None,
        memories: dict[str, Any] | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        reasoning_trace: list[str] | None = None,
        decisions_made: list[dict[str, Any]] | None = None,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        is_public: bool = False,
        allowed_agents: list[str] | None = None,
        expires_in_hours: int | None = None,
    ) -> dict[str, Any]:
        """
        Pack context into a transferable package.

        Args:
            name: Package name
            summary: Brief summary of the context
            goals: Current goals and their status
            memories: Relevant memories
            conversation_history: Recent conversation history
            reasoning_trace: Reasoning steps taken
            decisions_made: Decisions and their rationale
            constraints: Constraints on the work
            preferences: Agent preferences
            tags: Categorization tags
            is_public: Whether package is publicly accessible
            allowed_agents: Specific agents allowed to access
            expires_in_hours: How long until package expires

        Returns:
            Created context package
        """
        response = self._client.post(
            "/context/pack",
            json={
                "name": name,
                "summary": summary,
                "goals": goals or {},
                "memories": memories or {},
                "conversation_history": conversation_history or [],
                "reasoning_trace": reasoning_trace or [],
                "decisions_made": decisions_made or [],
                "constraints": constraints or {},
                "preferences": preferences or {},
                "tags": tags or [],
                "is_public": is_public,
                "allowed_agents": allowed_agents or [],
                "expires_in_hours": expires_in_hours,
            },
        )
        response.raise_for_status()
        return response.json()

    def list_packages(
        self,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List context packages."""
        params: dict[str, Any] = {"limit": limit}
        if tags:
            params["tags"] = ",".join(tags)
        response = self._client.get("/context/packages", params=params)
        response.raise_for_status()
        return response.json()

    def get_package(self, package_id: str) -> dict[str, Any]:
        """Get a context package with full details."""
        response = self._client.get(f"/context/packages/{package_id}")
        response.raise_for_status()
        return response.json()

    def unpack(self, package_id: str) -> dict[str, Any]:
        """Unpack a context package for use."""
        response = self._client.get(f"/context/packages/{package_id}/unpack")
        response.raise_for_status()
        return response.json()

    def delete_package(self, package_id: str) -> dict[str, Any]:
        """Delete a context package."""
        response = self._client.delete(f"/context/packages/{package_id}")
        response.raise_for_status()
        return response.json()

    def transfer(
        self,
        package_id: str,
        receiver_id: str,
        purpose: str | None = None,
        message: str | None = None,
        related_goal_id: str | None = None,
        related_task_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Transfer context to another agent.

        Args:
            package_id: Context package to transfer
            receiver_id: Agent receiving the context
            purpose: Why the transfer is happening
            message: Message to the receiver
            related_goal_id: Related goal ID
            related_task_id: Related task ID

        Returns:
            Transfer details
        """
        response = self._client.post(
            "/context/transfer",
            json={
                "package_id": package_id,
                "receiver_id": receiver_id,
                "purpose": purpose,
                "message": message,
                "related_goal_id": related_goal_id,
                "related_task_id": related_task_id,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_incoming_transfers(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get incoming context transfers."""
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        response = self._client.get("/context/transfers/incoming", params=params)
        response.raise_for_status()
        return response.json()

    def get_outgoing_transfers(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get outgoing context transfers."""
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        response = self._client.get("/context/transfers/outgoing", params=params)
        response.raise_for_status()
        return response.json()

    def receive_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Mark a transfer as received."""
        response = self._client.post(f"/context/transfers/{transfer_id}/receive")
        response.raise_for_status()
        return response.json()

    def accept_transfer(self, transfer_id: str, message: str | None = None) -> dict[str, Any]:
        """Accept a transfer."""
        response = self._client.post(
            f"/context/transfers/{transfer_id}/decide",
            json={"accept": True, "message": message},
        )
        response.raise_for_status()
        return response.json()

    def reject_transfer(self, transfer_id: str, message: str | None = None) -> dict[str, Any]:
        """Reject a transfer."""
        response = self._client.post(
            f"/context/transfers/{transfer_id}/decide",
            json={"accept": False, "message": message},
        )
        response.raise_for_status()
        return response.json()

    def apply_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Apply a transfer (mark as used)."""
        response = self._client.post(f"/context/transfers/{transfer_id}/apply")
        response.raise_for_status()
        return response.json()


class ContextAsync:
    """Asynchronous client for context management."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def pack(
        self,
        name: str,
        summary: str | None = None,
        goals: dict[str, Any] | None = None,
        memories: dict[str, Any] | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        reasoning_trace: list[str] | None = None,
        decisions_made: list[dict[str, Any]] | None = None,
        constraints: dict[str, Any] | None = None,
        preferences: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        is_public: bool = False,
        allowed_agents: list[str] | None = None,
        expires_in_hours: int | None = None,
    ) -> dict[str, Any]:
        """Pack context into a transferable package."""
        response = await self._client.post(
            "/context/pack",
            json={
                "name": name,
                "summary": summary,
                "goals": goals or {},
                "memories": memories or {},
                "conversation_history": conversation_history or [],
                "reasoning_trace": reasoning_trace or [],
                "decisions_made": decisions_made or [],
                "constraints": constraints or {},
                "preferences": preferences or {},
                "tags": tags or [],
                "is_public": is_public,
                "allowed_agents": allowed_agents or [],
                "expires_in_hours": expires_in_hours,
            },
        )
        response.raise_for_status()
        return response.json()

    async def list_packages(
        self,
        tags: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List context packages."""
        params: dict[str, Any] = {"limit": limit}
        if tags:
            params["tags"] = ",".join(tags)
        response = await self._client.get("/context/packages", params=params)
        response.raise_for_status()
        return response.json()

    async def get_package(self, package_id: str) -> dict[str, Any]:
        """Get a context package with full details."""
        response = await self._client.get(f"/context/packages/{package_id}")
        response.raise_for_status()
        return response.json()

    async def unpack(self, package_id: str) -> dict[str, Any]:
        """Unpack a context package for use."""
        response = await self._client.get(f"/context/packages/{package_id}/unpack")
        response.raise_for_status()
        return response.json()

    async def delete_package(self, package_id: str) -> dict[str, Any]:
        """Delete a context package."""
        response = await self._client.delete(f"/context/packages/{package_id}")
        response.raise_for_status()
        return response.json()

    async def transfer(
        self,
        package_id: str,
        receiver_id: str,
        purpose: str | None = None,
        message: str | None = None,
        related_goal_id: str | None = None,
        related_task_id: str | None = None,
    ) -> dict[str, Any]:
        """Transfer context to another agent."""
        response = await self._client.post(
            "/context/transfer",
            json={
                "package_id": package_id,
                "receiver_id": receiver_id,
                "purpose": purpose,
                "message": message,
                "related_goal_id": related_goal_id,
                "related_task_id": related_task_id,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_incoming_transfers(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get incoming context transfers."""
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        response = await self._client.get("/context/transfers/incoming", params=params)
        response.raise_for_status()
        return response.json()

    async def get_outgoing_transfers(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get outgoing context transfers."""
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        response = await self._client.get("/context/transfers/outgoing", params=params)
        response.raise_for_status()
        return response.json()

    async def receive_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Mark a transfer as received."""
        response = await self._client.post(f"/context/transfers/{transfer_id}/receive")
        response.raise_for_status()
        return response.json()

    async def accept_transfer(self, transfer_id: str, message: str | None = None) -> dict[str, Any]:
        """Accept a transfer."""
        response = await self._client.post(
            f"/context/transfers/{transfer_id}/decide",
            json={"accept": True, "message": message},
        )
        response.raise_for_status()
        return response.json()

    async def reject_transfer(self, transfer_id: str, message: str | None = None) -> dict[str, Any]:
        """Reject a transfer."""
        response = await self._client.post(
            f"/context/transfers/{transfer_id}/decide",
            json={"accept": False, "message": message},
        )
        response.raise_for_status()
        return response.json()

    async def apply_transfer(self, transfer_id: str) -> dict[str, Any]:
        """Apply a transfer (mark as used)."""
        response = await self._client.post(f"/context/transfers/{transfer_id}/apply")
        response.raise_for_status()
        return response.json()
