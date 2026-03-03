"""Discovery operations for Nexus SDK."""

from __future__ import annotations

from typing import Any

import httpx


class Discovery:
    """Synchronous discovery operations."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def register(
        self,
        name: str,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        endpoint_url: str | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """
        Register a capability for your agent.

        Args:
            name: Capability name (e.g., 'text-translation')
            description: What this capability does
            category: Category (e.g., 'language', 'code')
            tags: Tags for filtering
            endpoint_url: URL endpoint if applicable
            input_schema: JSON Schema for input
            output_schema: JSON Schema for output
            metadata: Additional metadata

        Returns:
            Registered capability data
        """
        response = self._client.post(
            "/capabilities",
            json={
                "name": name,
                "description": description,
                "category": category,
                "tags": tags or [],
                "endpoint_url": endpoint_url,
                "input_schema": input_schema,
                "output_schema": output_schema,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return response.json()

    def list(self) -> list[dict[str, Any]]:
        """List your agent's capabilities."""
        response = self._client.get("/capabilities")
        response.raise_for_status()
        return response.json()

    def update(
        self,
        name: str,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        endpoint_url: str | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        metadata: dict | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Update a capability."""
        response = self._client.patch(
            f"/capabilities/{name}",
            json={
                "description": description,
                "category": category,
                "tags": tags,
                "endpoint_url": endpoint_url,
                "input_schema": input_schema,
                "output_schema": output_schema,
                "metadata": metadata,
                "status": status,
            },
        )
        response.raise_for_status()
        return response.json()

    def delete(self, name: str) -> bool:
        """Delete a capability. Returns True if deleted."""
        response = self._client.delete(f"/capabilities/{name}")
        return response.status_code == 204

    def discover(
        self,
        query: str | None = None,
        name: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Discover capabilities across all agents.

        Args:
            query: Semantic search query
            name: Filter by exact name
            category: Filter by category
            tags: Filter by tags
            limit: Max results

        Returns:
            List of discovery results
        """
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if name:
            params["name"] = name
        if category:
            params["category"] = category
        if tags:
            params["tags"] = tags

        response = self._client.get("/discover", params=params)
        response.raise_for_status()
        return response.json()["results"]

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        """Get an agent's capabilities."""
        response = self._client.get(f"/discover/agents/{agent_id}")
        response.raise_for_status()
        return response.json()


class DiscoveryAsync:
    """Asynchronous discovery operations."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def register(
        self,
        name: str,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        endpoint_url: str | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Register a capability for your agent."""
        response = await self._client.post(
            "/capabilities",
            json={
                "name": name,
                "description": description,
                "category": category,
                "tags": tags or [],
                "endpoint_url": endpoint_url,
                "input_schema": input_schema,
                "output_schema": output_schema,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        return response.json()

    async def list(self) -> list[dict[str, Any]]:
        """List your agent's capabilities."""
        response = await self._client.get("/capabilities")
        response.raise_for_status()
        return response.json()

    async def update(
        self,
        name: str,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        endpoint_url: str | None = None,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        metadata: dict | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Update a capability."""
        response = await self._client.patch(
            f"/capabilities/{name}",
            json={
                "description": description,
                "category": category,
                "tags": tags,
                "endpoint_url": endpoint_url,
                "input_schema": input_schema,
                "output_schema": output_schema,
                "metadata": metadata,
                "status": status,
            },
        )
        response.raise_for_status()
        return response.json()

    async def delete(self, name: str) -> bool:
        """Delete a capability."""
        response = await self._client.delete(f"/capabilities/{name}")
        return response.status_code == 204

    async def discover(
        self,
        query: str | None = None,
        name: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Discover capabilities across all agents."""
        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if name:
            params["name"] = name
        if category:
            params["category"] = category
        if tags:
            params["tags"] = tags

        response = await self._client.get("/discover", params=params)
        response.raise_for_status()
        return response.json()["results"]

    async def get_agent(self, agent_id: str) -> dict[str, Any]:
        """Get an agent's capabilities."""
        response = await self._client.get(f"/discover/agents/{agent_id}")
        response.raise_for_status()
        return response.json()
