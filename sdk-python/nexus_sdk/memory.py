"""Memory operations for Nexus SDK."""

from __future__ import annotations

from typing import Any

import httpx


class Memory:
    """Synchronous memory operations."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def store(
        self,
        key: str,
        value: dict[str, Any],
        namespace: str = "default",
        scope: str = "agent",
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        text_content: str | None = None,
        expires_in_seconds: int | None = None,
    ) -> dict[str, Any]:
        """
        Store a memory.

        Args:
            key: Unique key for this memory
            value: The memory content (dict)
            namespace: Namespace for organization
            scope: Memory scope (agent, user, session, shared)
            user_id: User ID for user-scoped memories
            session_id: Session ID for session-scoped memories
            tags: Tags for categorization
            text_content: Text for semantic search
            expires_in_seconds: TTL in seconds

        Returns:
            Stored memory data
        """
        response = self._client.post(
            "/memory",
            json={
                "key": key,
                "value": value,
                "namespace": namespace,
                "scope": scope,
                "user_id": user_id,
                "session_id": session_id,
                "tags": tags or [],
                "text_content": text_content,
                "expires_in_seconds": expires_in_seconds,
            },
        )
        response.raise_for_status()
        return response.json()

    def get(
        self,
        key: str,
        namespace: str = "default",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Get a memory by key.

        Returns None if not found.
        """
        params = {"namespace": namespace}
        if user_id:
            params["user_id"] = user_id
        if session_id:
            params["session_id"] = session_id

        response = self._client.get(f"/memory/{key}", params=params)

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json()

    def search(
        self,
        query: str,
        namespace: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
        include_shared: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Search memories semantically.

        Args:
            query: Search query
            namespace: Filter by namespace
            user_id: Filter by user
            session_id: Filter by session
            tags: Filter by tags
            limit: Max results
            include_shared: Include shared memories

        Returns:
            List of search results with scores
        """
        response = self._client.post(
            "/memory/search",
            json={
                "query": query,
                "namespace": namespace,
                "user_id": user_id,
                "session_id": session_id,
                "tags": tags,
                "limit": limit,
                "include_shared": include_shared,
            },
        )
        response.raise_for_status()
        return response.json()["results"]

    def list(
        self,
        namespace: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List memories with filters."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if namespace:
            params["namespace"] = namespace
        if user_id:
            params["user_id"] = user_id
        if session_id:
            params["session_id"] = session_id
        if tags:
            params["tags"] = tags

        response = self._client.get("/memory", params=params)
        response.raise_for_status()
        return response.json()

    def delete(self, key: str, namespace: str = "default") -> bool:
        """Delete a memory. Returns True if deleted."""
        response = self._client.delete(
            f"/memory/{key}",
            params={"namespace": namespace},
        )
        return response.status_code == 204

    def share(
        self,
        memory_id: str,
        agent_id: str,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Share a memory with another agent."""
        response = self._client.post(
            f"/memory/{memory_id}/share",
            json={
                "agent_id": agent_id,
                "permissions": permissions or ["read"],
            },
        )
        response.raise_for_status()
        return response.json()


class MemoryAsync:
    """Asynchronous memory operations."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def store(
        self,
        key: str,
        value: dict[str, Any],
        namespace: str = "default",
        scope: str = "agent",
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        text_content: str | None = None,
        expires_in_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Store a memory."""
        response = await self._client.post(
            "/memory",
            json={
                "key": key,
                "value": value,
                "namespace": namespace,
                "scope": scope,
                "user_id": user_id,
                "session_id": session_id,
                "tags": tags or [],
                "text_content": text_content,
                "expires_in_seconds": expires_in_seconds,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get(
        self,
        key: str,
        namespace: str = "default",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get a memory by key."""
        params = {"namespace": namespace}
        if user_id:
            params["user_id"] = user_id
        if session_id:
            params["session_id"] = session_id

        response = await self._client.get(f"/memory/{key}", params=params)

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json()

    async def search(
        self,
        query: str,
        namespace: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
        include_shared: bool = True,
    ) -> list[dict[str, Any]]:
        """Search memories semantically."""
        response = await self._client.post(
            "/memory/search",
            json={
                "query": query,
                "namespace": namespace,
                "user_id": user_id,
                "session_id": session_id,
                "tags": tags,
                "limit": limit,
                "include_shared": include_shared,
            },
        )
        response.raise_for_status()
        return response.json()["results"]

    async def list(
        self,
        namespace: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List memories with filters."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if namespace:
            params["namespace"] = namespace
        if user_id:
            params["user_id"] = user_id
        if session_id:
            params["session_id"] = session_id
        if tags:
            params["tags"] = tags

        response = await self._client.get("/memory", params=params)
        response.raise_for_status()
        return response.json()

    async def delete(self, key: str, namespace: str = "default") -> bool:
        """Delete a memory."""
        response = await self._client.delete(
            f"/memory/{key}",
            params={"namespace": namespace},
        )
        return response.status_code == 204

    async def share(
        self,
        memory_id: str,
        agent_id: str,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Share a memory with another agent."""
        response = await self._client.post(
            f"/memory/{memory_id}/share",
            json={
                "agent_id": agent_id,
                "permissions": permissions or ["read"],
            },
        )
        response.raise_for_status()
        return response.json()
