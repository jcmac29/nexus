"""HTTP client for Nexus API."""

from typing import Any

import httpx

from nexus_cli.config import load_config


class NexusAPIError(Exception):
    """Error from Nexus API."""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API Error ({status_code}): {detail}")


class NexusClient:
    """Client for interacting with Nexus API."""

    def __init__(self, api_url: str | None = None, api_key: str | None = None):
        config = load_config()
        self.api_url = api_url or config.api_url
        self.api_key = api_key or config.api_key

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.Client(
            base_url=self.api_url,
            headers=headers,
            timeout=30.0,
        )

    def _handle_response(self, response: httpx.Response) -> Any:
        """Handle API response, raising errors if needed."""
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise NexusAPIError(response.status_code, detail)

        if response.status_code == 204:
            return None
        return response.json()

    # --- Agent Operations ---

    def register(
        self,
        name: str,
        slug: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Register a new agent."""
        response = self.client.post(
            "/agents",
            json={
                "name": name,
                "slug": slug,
                "description": description,
            },
        )
        return self._handle_response(response)

    def whoami(self) -> dict[str, Any]:
        """Get current agent info."""
        response = self.client.get("/agents/me")
        return self._handle_response(response)

    def update_agent(
        self,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update current agent."""
        data = {}
        if name:
            data["name"] = name
        if description:
            data["description"] = description

        response = self.client.patch("/agents/me", json=data)
        return self._handle_response(response)

    # --- Discovery Operations ---

    def search(
        self,
        query: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for capabilities."""
        params = {"limit": limit}
        if query:
            params["query"] = query
        if tags:
            params["tags"] = ",".join(tags)

        response = self.client.get("/discover/search", params=params)
        return self._handle_response(response)

    def get_agent(self, slug: str) -> dict[str, Any]:
        """Get agent by slug."""
        response = self.client.get(f"/discover/agents/{slug}")
        return self._handle_response(response)

    def register_capability(
        self,
        name: str,
        description: str,
        input_schema: dict | None = None,
        output_schema: dict | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Register a capability."""
        response = self.client.post(
            "/discover/capabilities",
            json={
                "name": name,
                "description": description,
                "input_schema": input_schema or {},
                "output_schema": output_schema or {},
                "tags": tags or [],
            },
        )
        return self._handle_response(response)

    def list_capabilities(self) -> list[dict[str, Any]]:
        """List my capabilities."""
        response = self.client.get("/discover/capabilities/me")
        return self._handle_response(response)

    # --- Invocation Operations ---

    def invoke(
        self,
        agent_slug: str,
        capability: str,
        input_data: dict | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Invoke a capability on another agent."""
        # First find the agent
        agent = self.get_agent(agent_slug)

        response = self.client.post(
            "/invocations",
            json={
                "target_agent_id": agent["id"],
                "capability": capability,
                "input": input_data or {},
                "timeout_seconds": timeout,
            },
        )
        return self._handle_response(response)

    def get_invocation(self, invocation_id: str) -> dict[str, Any]:
        """Get invocation status."""
        response = self.client.get(f"/invocations/{invocation_id}")
        return self._handle_response(response)

    def pending(self) -> list[dict[str, Any]]:
        """Get pending invocations to handle."""
        response = self.client.get("/invocations/pending")
        return self._handle_response(response)

    def complete(
        self,
        invocation_id: str,
        output: dict | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Complete an invocation."""
        data = {}
        if output is not None:
            data["output"] = output
        if error is not None:
            data["error"] = error

        response = self.client.post(
            f"/invocations/{invocation_id}/complete",
            json=data,
        )
        return self._handle_response(response)

    # --- Messaging Operations ---

    def send_message(
        self,
        to_agent_slug: str,
        content: str,
        subject: str | None = None,
    ) -> dict[str, Any]:
        """Send a message to another agent."""
        agent = self.get_agent(to_agent_slug)

        response = self.client.post(
            "/messages",
            json={
                "to_agent_id": agent["id"],
                "content": content,
                "subject": subject,
            },
        )
        return self._handle_response(response)

    def inbox(self, unread_only: bool = False) -> list[dict[str, Any]]:
        """Get inbox messages."""
        params = {}
        if unread_only:
            params["unread_only"] = "true"

        response = self.client.get("/messages/inbox", params=params)
        return self._handle_response(response)

    # --- Health Operations ---

    def heartbeat(self) -> dict[str, Any]:
        """Send a heartbeat."""
        response = self.client.post("/health/heartbeat")
        return self._handle_response(response)

    def health_status(self) -> dict[str, Any]:
        """Get my health status."""
        response = self.client.get("/health/me")
        return self._handle_response(response)

    def close(self):
        """Close the client."""
        self.client.close()
