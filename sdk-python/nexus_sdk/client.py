"""Main Nexus client."""

from __future__ import annotations

from typing import Any

import httpx

from nexus_sdk.memory import Memory, MemoryAsync
from nexus_sdk.discovery import Discovery, DiscoveryAsync
from nexus_sdk.messaging import MessagingClient, InvocationClient, WebhookClient
from nexus_sdk.graph import Graph, GraphAsync
from nexus_sdk.webhooks import Webhooks, WebhooksAsync
from nexus_sdk.analytics import Analytics, AnalyticsAsync
from nexus_sdk.tenants import Tenants, TenantsAsync


class HTTPClient:
    """Wrapper around httpx for consistent API."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def get(self, path: str, params: dict | None = None) -> Any:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()

    def post(self, path: str, data: dict) -> Any:
        response = self._client.post(path, json=data)
        response.raise_for_status()
        return response.json()

    def delete(self, path: str) -> None:
        response = self._client.delete(path)
        response.raise_for_status()


class Nexus:
    """
    Synchronous Nexus client.

    Usage:
        # Register a new agent
        nexus = Nexus.register("my-agent", "My Agent Name")

        # Or connect with existing API key
        nexus = Nexus(api_key="nex_xxx")

        # Use memory
        nexus.memory.store("key", {"data": "value"})
        data = nexus.memory.get("key")

        # Use discovery
        nexus.capabilities.register("translation", "Translate text between languages")
        results = nexus.discover(query="translation")

        # Invoke another agent's capability
        result = nexus.invoke("agent-id", "generate-image", {"prompt": "a cat"})

        # Send messages to other agents
        nexus.messages.send("agent-id", {"text": "Hello!"})
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000/api/v1",
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        self._http = HTTPClient(self._client)
        self._memory = Memory(self._client)
        self._discovery = Discovery(self._client)
        self._messages = MessagingClient(self._http)
        self._invocations = InvocationClient(self._http)
        self._webhook = WebhookClient(self._http)
        self._graph = Graph(self._client)
        self._webhooks = Webhooks(self._client)
        self._analytics = Analytics(self._client)
        self._tenants = Tenants(self._client)

    @classmethod
    def register(
        cls,
        slug: str,
        name: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
        base_url: str = "http://localhost:8000/api/v1",
    ) -> "Nexus":
        """
        Register a new agent and return a connected client.

        Args:
            slug: Unique URL-friendly identifier (lowercase, hyphens allowed)
            name: Display name (defaults to slug)
            description: Agent description
            metadata: Additional metadata
            base_url: Nexus API URL

        Returns:
            Connected Nexus client
        """
        with httpx.Client(base_url=base_url) as client:
            response = client.post(
                "/agents",
                json={
                    "slug": slug,
                    "name": name or slug,
                    "description": description,
                    "metadata": metadata or {},
                },
            )
            response.raise_for_status()
            data = response.json()

        return cls(api_key=data["api_key"], base_url=base_url)

    @property
    def memory(self) -> Memory:
        """Access memory operations."""
        return self._memory

    @property
    def capabilities(self) -> Discovery:
        """Access capability registration."""
        return self._discovery

    @property
    def messages(self) -> MessagingClient:
        """Access messaging operations."""
        return self._messages

    @property
    def invocations(self) -> InvocationClient:
        """Access invocation operations."""
        return self._invocations

    @property
    def webhook(self) -> WebhookClient:
        """Access webhook configuration."""
        return self._webhook

    @property
    def graph(self) -> Graph:
        """Access graph memory operations."""
        return self._graph

    @property
    def webhooks(self) -> Webhooks:
        """Access webhook management."""
        return self._webhooks

    @property
    def analytics(self) -> Analytics:
        """Access analytics and usage metrics."""
        return self._analytics

    @property
    def tenants(self) -> Tenants:
        """Access multi-tenant management."""
        return self._tenants

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
            name: Filter by exact capability name
            category: Filter by category
            tags: Filter by tags
            limit: Max results

        Returns:
            List of discovery results
        """
        return self._discovery.discover(
            query=query,
            name=name,
            category=category,
            tags=tags,
            limit=limit,
        )

    def invoke(
        self,
        agent_id: str,
        capability: str,
        input_data: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        async_mode: bool = False,
    ) -> dict[str, Any]:
        """
        Invoke a capability on another agent.

        Args:
            agent_id: Target agent's ID
            capability: Name of the capability to invoke
            input_data: Input data for the capability
            timeout_seconds: Timeout in seconds
            async_mode: If True, return immediately without waiting

        Returns:
            Invocation result
        """
        return self._invocations.invoke(
            agent_id=agent_id,
            capability=capability,
            input_data=input_data,
            timeout_seconds=timeout_seconds,
            async_mode=async_mode,
        )

    def pending(self) -> dict[str, Any]:
        """
        Get pending work (invocations and messages) for this agent.

        Returns:
            Dict with 'invocations' and 'messages' lists
        """
        return self._invocations.pending()

    def complete(
        self,
        invocation_id: str,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """
        Complete an invocation with a result.

        Args:
            invocation_id: ID of the invocation
            output: Output data (if successful)
            error: Error message (if failed)

        Returns:
            Updated invocation
        """
        return self._invocations.complete(
            invocation_id=invocation_id,
            output=output,
            error=error,
        )

    def me(self) -> dict[str, Any]:
        """Get current agent info."""
        response = self._client.get("/agents/me")
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Close the client connection."""
        self._client.close()

    def __enter__(self) -> "Nexus":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class HTTPClientAsync:
    """Async wrapper around httpx for consistent API."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def get(self, path: str, params: dict | None = None) -> Any:
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()

    async def post(self, path: str, data: dict) -> Any:
        response = await self._client.post(path, json=data)
        response.raise_for_status()
        return response.json()

    async def delete(self, path: str) -> None:
        response = await self._client.delete(path)
        response.raise_for_status()


class MessagingClientAsync:
    """Async client for agent-to-agent messaging."""

    def __init__(self, http_client: HTTPClientAsync):
        self._http = http_client

    async def send(
        self,
        to_agent_id: str,
        content: dict[str, Any],
        subject: str | None = None,
        reply_to_id: str | None = None,
    ) -> dict:
        """Send a message to another agent."""
        data = {
            "to_agent_id": str(to_agent_id),
            "content": content,
        }
        if subject:
            data["subject"] = subject
        if reply_to_id:
            data["reply_to_id"] = str(reply_to_id)
        return await self._http.post("/messages", data)

    async def inbox(
        self,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Get messages received by this agent."""
        params = {
            "inbox": "true",
            "unread_only": str(unread_only).lower(),
            "limit": limit,
            "offset": offset,
        }
        return await self._http.get("/messages", params=params)

    async def sent(self, limit: int = 50, offset: int = 0) -> dict:
        """Get messages sent by this agent."""
        params = {"inbox": "false", "limit": limit, "offset": offset}
        return await self._http.get("/messages", params=params)

    async def mark_read(self, message_id: str) -> dict:
        """Mark a message as read."""
        return await self._http.post(f"/messages/{message_id}/read", {})


class InvocationClientAsync:
    """Async client for invoking capabilities on other agents."""

    def __init__(self, http_client: HTTPClientAsync):
        self._http = http_client

    async def invoke(
        self,
        agent_id: str,
        capability: str,
        input_data: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        async_mode: bool = False,
    ) -> dict:
        """Invoke a capability on another agent."""
        data = {
            "input": input_data or {},
            "timeout_seconds": timeout_seconds,
            "async_mode": async_mode,
        }
        return await self._http.post(f"/invoke/{agent_id}/{capability}", data)

    async def get(self, invocation_id: str) -> dict:
        """Get an invocation by ID."""
        return await self._http.get(f"/invocations/{invocation_id}")

    async def list(
        self,
        as_caller: bool = True,
        status: str | None = None,
        limit: int = 50,
    ) -> dict:
        """List invocations for this agent."""
        params = {"as_caller": str(as_caller).lower(), "limit": limit}
        if status:
            params["status"] = status
        return await self._http.get("/invocations", params=params)

    async def pending(self) -> dict:
        """Get pending work for this agent."""
        return await self._http.get("/agents/me/pending")

    async def complete(
        self,
        invocation_id: str,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict:
        """Complete an invocation with a result."""
        data = {}
        if output is not None:
            data["output"] = output
        if error is not None:
            data["error"] = error
        return await self._http.post(f"/invocations/{invocation_id}/complete", data)


class WebhookClientAsync:
    """Async client for managing webhooks."""

    def __init__(self, http_client: HTTPClientAsync):
        self._http = http_client

    async def set(self, endpoint_url: str, events: list[str] | None = None) -> dict:
        """Configure webhook for receiving invocations and messages."""
        data = {
            "endpoint_url": endpoint_url,
            "events": events or ["invocation", "message"],
        }
        return await self._http.post("/agents/me/webhook", data)

    async def get(self) -> dict | None:
        """Get current webhook configuration."""
        return await self._http.get("/agents/me/webhook")

    async def remove(self) -> None:
        """Remove webhook configuration."""
        await self._http.delete("/agents/me/webhook")


class NexusAsync:
    """
    Asynchronous Nexus client.

    Usage:
        # Register a new agent
        nexus = await NexusAsync.register("my-agent", "My Agent Name")

        # Or connect with existing API key
        nexus = NexusAsync(api_key="nex_xxx")

        # Use memory
        await nexus.memory.store("key", {"data": "value"})
        data = await nexus.memory.get("key")

        # Use discovery
        await nexus.capabilities.register("translation", "Translate text")
        results = await nexus.discover(query="translation")

        # Invoke another agent's capability
        result = await nexus.invoke("agent-id", "generate-image", {"prompt": "a cat"})

        # Send messages
        await nexus.messages.send("agent-id", {"text": "Hello!"})
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000/api/v1",
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        self._http = HTTPClientAsync(self._client)
        self._memory = MemoryAsync(self._client)
        self._discovery = DiscoveryAsync(self._client)
        self._messages = MessagingClientAsync(self._http)
        self._invocations = InvocationClientAsync(self._http)
        self._webhook = WebhookClientAsync(self._http)
        self._graph = GraphAsync(self._client)
        self._webhooks = WebhooksAsync(self._client)
        self._analytics = AnalyticsAsync(self._client)
        self._tenants = TenantsAsync(self._client)

    @classmethod
    async def register(
        cls,
        slug: str,
        name: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
        base_url: str = "http://localhost:8000/api/v1",
    ) -> "NexusAsync":
        """Register a new agent and return a connected client."""
        async with httpx.AsyncClient(base_url=base_url) as client:
            response = await client.post(
                "/agents",
                json={
                    "slug": slug,
                    "name": name or slug,
                    "description": description,
                    "metadata": metadata or {},
                },
            )
            response.raise_for_status()
            data = response.json()

        return cls(api_key=data["api_key"], base_url=base_url)

    @property
    def memory(self) -> MemoryAsync:
        """Access memory operations."""
        return self._memory

    @property
    def capabilities(self) -> DiscoveryAsync:
        """Access capability registration."""
        return self._discovery

    @property
    def messages(self) -> MessagingClientAsync:
        """Access messaging operations."""
        return self._messages

    @property
    def invocations(self) -> InvocationClientAsync:
        """Access invocation operations."""
        return self._invocations

    @property
    def webhook(self) -> WebhookClientAsync:
        """Access webhook configuration."""
        return self._webhook

    @property
    def graph(self) -> GraphAsync:
        """Access graph memory operations."""
        return self._graph

    @property
    def webhooks(self) -> WebhooksAsync:
        """Access webhook management."""
        return self._webhooks

    @property
    def analytics(self) -> AnalyticsAsync:
        """Access analytics and usage metrics."""
        return self._analytics

    @property
    def tenants(self) -> TenantsAsync:
        """Access multi-tenant management."""
        return self._tenants

    async def discover(
        self,
        query: str | None = None,
        name: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Discover capabilities across all agents."""
        return await self._discovery.discover(
            query=query,
            name=name,
            category=category,
            tags=tags,
            limit=limit,
        )

    async def invoke(
        self,
        agent_id: str,
        capability: str,
        input_data: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        async_mode: bool = False,
    ) -> dict[str, Any]:
        """Invoke a capability on another agent."""
        return await self._invocations.invoke(
            agent_id=agent_id,
            capability=capability,
            input_data=input_data,
            timeout_seconds=timeout_seconds,
            async_mode=async_mode,
        )

    async def pending(self) -> dict[str, Any]:
        """Get pending work for this agent."""
        return await self._invocations.pending()

    async def complete(
        self,
        invocation_id: str,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Complete an invocation with a result."""
        return await self._invocations.complete(
            invocation_id=invocation_id,
            output=output,
            error=error,
        )

    async def me(self) -> dict[str, Any]:
        """Get current agent info."""
        response = await self._client.get("/agents/me")
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """Close the client connection."""
        await self._client.aclose()

    async def __aenter__(self) -> "NexusAsync":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
