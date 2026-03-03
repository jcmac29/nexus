"""Webhook management for Nexus SDK."""

from __future__ import annotations

from typing import Any

import httpx


class Webhooks:
    """Synchronous webhook management."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def create(
        self,
        name: str,
        url: str,
        event_types: list[str],
        description: str | None = None,
        retry_policy: str = "exponential",
        max_retries: int = 5,
        timeout_seconds: int = 30,
        custom_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new webhook endpoint.

        Args:
            name: Webhook name
            url: Destination URL for webhook deliveries
            event_types: Event patterns to subscribe to (e.g., ["memory.*", "agent.connected"])
            description: Optional description
            retry_policy: Retry strategy (exponential, linear, none)
            max_retries: Maximum retry attempts (0-10)
            timeout_seconds: Request timeout
            custom_headers: Additional headers to include

        Returns:
            Created webhook with secret (save this!)
        """
        response = self._client.post(
            "/webhooks",
            json={
                "name": name,
                "url": url,
                "event_types": event_types,
                "description": description,
                "retry_policy": retry_policy,
                "max_retries": max_retries,
                "timeout_seconds": timeout_seconds,
                "custom_headers": custom_headers or {},
            },
        )
        response.raise_for_status()
        return response.json()

    def list(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """List all webhook endpoints."""
        response = self._client.get(
            "/webhooks",
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return response.json()["webhooks"]

    def get(self, webhook_id: str) -> dict[str, Any]:
        """Get a webhook by ID."""
        response = self._client.get(f"/webhooks/{webhook_id}")
        response.raise_for_status()
        return response.json()

    def update(
        self,
        webhook_id: str,
        name: str | None = None,
        url: str | None = None,
        event_types: list[str] | None = None,
        is_active: bool | None = None,
        retry_policy: str | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """Update a webhook endpoint."""
        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name
        if url is not None:
            data["url"] = url
        if event_types is not None:
            data["event_types"] = event_types
        if is_active is not None:
            data["is_active"] = is_active
        if retry_policy is not None:
            data["retry_policy"] = retry_policy
        if max_retries is not None:
            data["max_retries"] = max_retries

        response = self._client.patch(f"/webhooks/{webhook_id}", json=data)
        response.raise_for_status()
        return response.json()

    def delete(self, webhook_id: str) -> bool:
        """Delete a webhook. Returns True if deleted."""
        response = self._client.delete(f"/webhooks/{webhook_id}")
        return response.status_code in [200, 204]

    def test(self, webhook_id: str) -> dict[str, Any]:
        """Send a test ping to the webhook."""
        response = self._client.post(f"/webhooks/{webhook_id}/test")
        response.raise_for_status()
        return response.json()

    def rotate_secret(self, webhook_id: str) -> dict[str, Any]:
        """
        Rotate the webhook's signing secret.

        Returns the new secret - save this!
        """
        response = self._client.post(f"/webhooks/{webhook_id}/rotate-secret")
        response.raise_for_status()
        return response.json()

    def list_deliveries(
        self,
        webhook_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        List delivery logs for a webhook.

        Args:
            webhook_id: Webhook ID
            status: Filter by status (pending, delivered, failed, retrying)
            limit: Max results
            offset: Pagination offset

        Returns:
            List of delivery logs
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        response = self._client.get(
            f"/webhooks/{webhook_id}/deliveries",
            params=params,
        )
        response.raise_for_status()
        return response.json()["deliveries"]

    def retry_delivery(self, delivery_id: str) -> dict[str, Any]:
        """Manually retry a failed delivery."""
        response = self._client.post(f"/webhooks/deliveries/{delivery_id}/retry")
        response.raise_for_status()
        return response.json()


class WebhooksAsync:
    """Asynchronous webhook management."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def create(
        self,
        name: str,
        url: str,
        event_types: list[str],
        description: str | None = None,
        retry_policy: str = "exponential",
        max_retries: int = 5,
        timeout_seconds: int = 30,
        custom_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a new webhook endpoint."""
        response = await self._client.post(
            "/webhooks",
            json={
                "name": name,
                "url": url,
                "event_types": event_types,
                "description": description,
                "retry_policy": retry_policy,
                "max_retries": max_retries,
                "timeout_seconds": timeout_seconds,
                "custom_headers": custom_headers or {},
            },
        )
        response.raise_for_status()
        return response.json()

    async def list(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """List all webhook endpoints."""
        response = await self._client.get(
            "/webhooks",
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return response.json()["webhooks"]

    async def get(self, webhook_id: str) -> dict[str, Any]:
        """Get a webhook by ID."""
        response = await self._client.get(f"/webhooks/{webhook_id}")
        response.raise_for_status()
        return response.json()

    async def update(
        self,
        webhook_id: str,
        name: str | None = None,
        url: str | None = None,
        event_types: list[str] | None = None,
        is_active: bool | None = None,
        retry_policy: str | None = None,
        max_retries: int | None = None,
    ) -> dict[str, Any]:
        """Update a webhook endpoint."""
        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name
        if url is not None:
            data["url"] = url
        if event_types is not None:
            data["event_types"] = event_types
        if is_active is not None:
            data["is_active"] = is_active
        if retry_policy is not None:
            data["retry_policy"] = retry_policy
        if max_retries is not None:
            data["max_retries"] = max_retries

        response = await self._client.patch(f"/webhooks/{webhook_id}", json=data)
        response.raise_for_status()
        return response.json()

    async def delete(self, webhook_id: str) -> bool:
        """Delete a webhook."""
        response = await self._client.delete(f"/webhooks/{webhook_id}")
        return response.status_code in [200, 204]

    async def test(self, webhook_id: str) -> dict[str, Any]:
        """Send a test ping to the webhook."""
        response = await self._client.post(f"/webhooks/{webhook_id}/test")
        response.raise_for_status()
        return response.json()

    async def rotate_secret(self, webhook_id: str) -> dict[str, Any]:
        """Rotate the webhook's signing secret."""
        response = await self._client.post(f"/webhooks/{webhook_id}/rotate-secret")
        response.raise_for_status()
        return response.json()

    async def list_deliveries(
        self,
        webhook_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List delivery logs for a webhook."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        response = await self._client.get(
            f"/webhooks/{webhook_id}/deliveries",
            params=params,
        )
        response.raise_for_status()
        return response.json()["deliveries"]

    async def retry_delivery(self, delivery_id: str) -> dict[str, Any]:
        """Manually retry a failed delivery."""
        response = await self._client.post(f"/webhooks/deliveries/{delivery_id}/retry")
        response.raise_for_status()
        return response.json()
