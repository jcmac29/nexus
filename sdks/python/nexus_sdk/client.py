"""Nexus Python SDK Client."""

from __future__ import annotations

import httpx
from typing import Any
from dataclasses import dataclass


@dataclass
class Agent:
    id: str
    name: str
    slug: str
    description: str | None = None


@dataclass
class Memory:
    id: str
    key: str
    value: dict
    tags: list[str]


@dataclass
class Capability:
    name: str
    description: str | None
    input_schema: dict | None = None


@dataclass
class Invocation:
    id: str
    status: str
    output: dict | None = None


@dataclass
class Message:
    id: str
    from_agent_id: str
    subject: str
    body: str


class NexusClient:
    """Nexus API Client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def close(self):
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # --- Identity ---

    def whoami(self) -> Agent:
        """Get current agent info."""
        response = self._client.get("/api/v1/agents/me")
        response.raise_for_status()
        data = response.json()
        return Agent(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            description=data.get("description"),
        )

    # --- Memory ---

    def store_memory(
        self,
        key: str,
        value: dict,
        text_content: str | None = None,
        tags: list[str] | None = None,
        scope: str = "agent",
    ) -> Memory:
        """Store a memory."""
        response = self._client.post(
            "/api/v1/memory",
            json={
                "key": key,
                "value": value,
                "text_content": text_content or str(value),
                "tags": tags or [],
                "scope": scope,
            },
        )
        response.raise_for_status()
        data = response.json()
        return Memory(
            id=data["id"],
            key=data["key"],
            value=data["value"],
            tags=data.get("tags", []),
        )

    def search_memory(
        self,
        query: str,
        limit: int = 10,
        include_shared: bool = True,
    ) -> list[tuple[Memory, float]]:
        """Search memories semantically."""
        response = self._client.post(
            "/api/v1/memory/search",
            json={
                "query": query,
                "limit": limit,
                "include_shared": include_shared,
            },
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for r in data.get("results", []):
            mem = r["memory"]
            memory = Memory(
                id=mem["id"],
                key=mem["key"],
                value=mem["value"],
                tags=mem.get("tags", []),
            )
            results.append((memory, r["score"]))

        return results

    def get_memory(self, memory_id: str) -> Memory:
        """Get a specific memory."""
        response = self._client.get(f"/api/v1/memory/{memory_id}")
        response.raise_for_status()
        data = response.json()
        return Memory(
            id=data["id"],
            key=data["key"],
            value=data["value"],
            tags=data.get("tags", []),
        )

    # --- Capabilities ---

    def register_capability(
        self,
        name: str,
        description: str,
        input_schema: dict | None = None,
    ) -> Capability:
        """Register a capability."""
        response = self._client.post(
            "/api/v1/capabilities",
            json={
                "name": name,
                "description": description,
                "input_schema": input_schema or {},
            },
        )
        response.raise_for_status()
        data = response.json()
        return Capability(
            name=data["name"],
            description=data.get("description"),
            input_schema=data.get("input_schema"),
        )

    def discover_agents(self, capability: str) -> list[Agent]:
        """Find agents with a capability."""
        response = self._client.get(f"/api/v1/discover/capabilities/{capability}")
        response.raise_for_status()
        data = response.json()

        return [
            Agent(
                id=a["id"],
                name=a["name"],
                slug=a["slug"],
                description=a.get("description"),
            )
            for a in data.get("agents", [])
        ]

    # --- Invocations ---

    def invoke(
        self,
        agent_id: str,
        capability: str,
        input_data: dict,
        wait: bool = False,
    ) -> Invocation:
        """Invoke a capability on an agent."""
        response = self._client.post(
            f"/api/v1/invoke/{agent_id}/{capability}",
            json={"input": input_data},
        )
        response.raise_for_status()
        data = response.json()

        invocation = Invocation(
            id=data.get("invocation_id", data.get("id")),
            status=data["status"],
            output=data.get("output"),
        )

        if wait and invocation.status == "pending":
            # Poll for completion
            import time
            for _ in range(60):  # Max 60 seconds
                time.sleep(1)
                status = self.get_invocation(invocation.id)
                if status.status in ("completed", "failed"):
                    return status

        return invocation

    def get_invocation(self, invocation_id: str) -> Invocation:
        """Get invocation status."""
        response = self._client.get(f"/api/v1/invocations/{invocation_id}")
        response.raise_for_status()
        data = response.json()
        return Invocation(
            id=data["id"],
            status=data["status"],
            output=data.get("output"),
        )

    def get_pending_work(self) -> list[Invocation]:
        """Get pending invocations for this agent."""
        response = self._client.get("/api/v1/agents/me/pending")
        response.raise_for_status()
        data = response.json()

        return [
            Invocation(id=i["id"], status="pending", output=None)
            for i in data
        ]

    def complete_invocation(
        self,
        invocation_id: str,
        output: dict,
        success: bool = True,
    ) -> None:
        """Complete an invocation."""
        response = self._client.post(
            f"/api/v1/invocations/{invocation_id}/complete",
            json={"output": output, "success": success},
        )
        response.raise_for_status()

    # --- Messaging ---

    def send_message(
        self,
        to_agent_id: str,
        subject: str,
        body: str,
    ) -> Message:
        """Send a message to another agent."""
        response = self._client.post(
            "/api/v1/messages",
            json={
                "to_agent_id": to_agent_id,
                "subject": subject,
                "body": body,
            },
        )
        response.raise_for_status()
        data = response.json()
        return Message(
            id=data["id"],
            from_agent_id=data["from_agent_id"],
            subject=data["subject"],
            body=data["body"],
        )

    def get_inbox(self, unread_only: bool = False) -> list[Message]:
        """Get inbox messages."""
        params = {"unread": unread_only} if unread_only else {}
        response = self._client.get("/api/v1/messages/inbox", params=params)
        response.raise_for_status()
        data = response.json()

        return [
            Message(
                id=m["id"],
                from_agent_id=m["from_agent_id"],
                subject=m["subject"],
                body=m["body"],
            )
            for m in data
        ]

    # --- Health ---

    def heartbeat(self, status: str = "healthy") -> None:
        """Send a heartbeat."""
        response = self._client.post(
            "/api/v1/health/heartbeat",
            json={"status": status},
        )
        response.raise_for_status()


class AsyncNexusClient:
    """Async Nexus API Client."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def whoami(self) -> Agent:
        response = await self._client.get("/api/v1/agents/me")
        response.raise_for_status()
        data = response.json()
        return Agent(
            id=data["id"],
            name=data["name"],
            slug=data["slug"],
            description=data.get("description"),
        )

    async def search_memory(
        self,
        query: str,
        limit: int = 10,
        include_shared: bool = True,
    ) -> list[tuple[Memory, float]]:
        response = await self._client.post(
            "/api/v1/memory/search",
            json={
                "query": query,
                "limit": limit,
                "include_shared": include_shared,
            },
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for r in data.get("results", []):
            mem = r["memory"]
            memory = Memory(
                id=mem["id"],
                key=mem["key"],
                value=mem["value"],
                tags=mem.get("tags", []),
            )
            results.append((memory, r["score"]))

        return results

    async def invoke(
        self,
        agent_id: str,
        capability: str,
        input_data: dict,
    ) -> Invocation:
        response = await self._client.post(
            f"/api/v1/invoke/{agent_id}/{capability}",
            json={"input": input_data},
        )
        response.raise_for_status()
        data = response.json()
        return Invocation(
            id=data.get("invocation_id", data.get("id")),
            status=data["status"],
            output=data.get("output"),
        )
