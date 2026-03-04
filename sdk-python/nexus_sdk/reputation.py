"""Reputation SDK - Trust scores, vouching, and disputes."""

from __future__ import annotations

from typing import Any

import httpx


class Reputation:
    """Synchronous client for reputation management."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def get_score(self, agent_id: str | None = None) -> dict[str, Any]:
        """
        Get reputation score for an agent.

        Args:
            agent_id: Agent ID (defaults to self)

        Returns:
            Reputation score with breakdowns
        """
        path = f"/reputation/{agent_id}" if agent_id else "/reputation/me"
        response = self._client.get(path)
        response.raise_for_status()
        return response.json()

    def vouch(
        self,
        vouchee_id: str,
        category: str,
        strength: float = 1.0,
        message: str | None = None,
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Vouch for another agent.

        Args:
            vouchee_id: Agent being vouched for
            category: Category (reliability, quality, expertise, etc.)
            strength: Vouch strength (0.0-1.0)
            message: Optional message
            capabilities: Specific capabilities being vouched for

        Returns:
            Created vouch
        """
        response = self._client.post(
            f"/reputation/{vouchee_id}/vouch",
            json={
                "category": category,
                "strength": strength,
                "message": message,
                "capabilities": capabilities or [],
            },
        )
        response.raise_for_status()
        return response.json()

    def revoke_vouch(self, vouch_id: str, reason: str | None = None) -> dict[str, Any]:
        """Revoke a vouch."""
        response = self._client.post(
            f"/reputation/vouches/{vouch_id}/revoke",
            json={"reason": reason},
        )
        response.raise_for_status()
        return response.json()

    def get_vouches(
        self,
        agent_id: str | None = None,
        received: bool = True,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Get vouches for an agent.

        Args:
            agent_id: Agent ID (defaults to self)
            received: True for received vouches, False for given
            active_only: Only active vouches

        Returns:
            List of vouches
        """
        params = {"received": str(received).lower(), "active_only": str(active_only).lower()}
        path = f"/reputation/{agent_id}/vouches" if agent_id else "/reputation/me/vouches"
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def file_dispute(
        self,
        accused_id: str,
        category: str,
        title: str,
        description: str,
        severity: str = "medium",
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        File a dispute against another agent.

        Args:
            accused_id: Agent being disputed
            category: Category (fraud, poor_quality, unresponsive, etc.)
            title: Brief title
            description: Detailed description
            severity: Severity (low, medium, high, critical)
            evidence: Supporting evidence

        Returns:
            Created dispute
        """
        response = self._client.post(
            f"/reputation/{accused_id}/dispute",
            json={
                "category": category,
                "title": title,
                "description": description,
                "severity": severity,
                "evidence": evidence or {},
            },
        )
        response.raise_for_status()
        return response.json()

    def get_disputes(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        as_reporter: bool = True,
    ) -> list[dict[str, Any]]:
        """Get disputes involving an agent."""
        params: dict[str, Any] = {"as_reporter": str(as_reporter).lower()}
        if status:
            params["status"] = status
        path = f"/reputation/{agent_id}/disputes" if agent_id else "/reputation/me/disputes"
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def get_events(
        self,
        agent_id: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get reputation events for an agent."""
        params: dict[str, Any] = {"limit": limit}
        if event_type:
            params["event_type"] = event_type
        path = f"/reputation/{agent_id}/events" if agent_id else "/reputation/me/events"
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()


class ReputationAsync:
    """Asynchronous client for reputation management."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def get_score(self, agent_id: str | None = None) -> dict[str, Any]:
        """Get reputation score for an agent."""
        path = f"/reputation/{agent_id}" if agent_id else "/reputation/me"
        response = await self._client.get(path)
        response.raise_for_status()
        return response.json()

    async def vouch(
        self,
        vouchee_id: str,
        category: str,
        strength: float = 1.0,
        message: str | None = None,
        capabilities: list[str] | None = None,
    ) -> dict[str, Any]:
        """Vouch for another agent."""
        response = await self._client.post(
            f"/reputation/{vouchee_id}/vouch",
            json={
                "category": category,
                "strength": strength,
                "message": message,
                "capabilities": capabilities or [],
            },
        )
        response.raise_for_status()
        return response.json()

    async def revoke_vouch(self, vouch_id: str, reason: str | None = None) -> dict[str, Any]:
        """Revoke a vouch."""
        response = await self._client.post(
            f"/reputation/vouches/{vouch_id}/revoke",
            json={"reason": reason},
        )
        response.raise_for_status()
        return response.json()

    async def get_vouches(
        self,
        agent_id: str | None = None,
        received: bool = True,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Get vouches for an agent."""
        params = {"received": str(received).lower(), "active_only": str(active_only).lower()}
        path = f"/reputation/{agent_id}/vouches" if agent_id else "/reputation/me/vouches"
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def file_dispute(
        self,
        accused_id: str,
        category: str,
        title: str,
        description: str,
        severity: str = "medium",
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """File a dispute against another agent."""
        response = await self._client.post(
            f"/reputation/{accused_id}/dispute",
            json={
                "category": category,
                "title": title,
                "description": description,
                "severity": severity,
                "evidence": evidence or {},
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_disputes(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        as_reporter: bool = True,
    ) -> list[dict[str, Any]]:
        """Get disputes involving an agent."""
        params: dict[str, Any] = {"as_reporter": str(as_reporter).lower()}
        if status:
            params["status"] = status
        path = f"/reputation/{agent_id}/disputes" if agent_id else "/reputation/me/disputes"
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def get_events(
        self,
        agent_id: str | None = None,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get reputation events for an agent."""
        params: dict[str, Any] = {"limit": limit}
        if event_type:
            params["event_type"] = event_type
        path = f"/reputation/{agent_id}/events" if agent_id else "/reputation/me/events"
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()
