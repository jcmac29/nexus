"""Messaging and invocation functionality for Nexus SDK."""

from typing import Any
from uuid import UUID


class MessagingClient:
    """Client for agent-to-agent messaging."""

    def __init__(self, http_client):
        self._http = http_client

    def send(
        self,
        to_agent_id: str | UUID,
        content: dict[str, Any],
        subject: str | None = None,
        reply_to_id: str | UUID | None = None,
    ) -> dict:
        """
        Send a message to another agent.

        Args:
            to_agent_id: Target agent's ID
            content: Message content (dict)
            subject: Optional message subject
            reply_to_id: Optional ID of message being replied to

        Returns:
            Message object with id, status, etc.
        """
        data = {
            "to_agent_id": str(to_agent_id),
            "content": content,
        }
        if subject:
            data["subject"] = subject
        if reply_to_id:
            data["reply_to_id"] = str(reply_to_id)

        return self._http.post("/messages", data)

    def inbox(
        self,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        Get messages received by this agent.

        Args:
            unread_only: Only return unread messages
            limit: Max messages to return
            offset: Pagination offset

        Returns:
            Dict with 'messages' list and 'total' count
        """
        params = {
            "inbox": "true",
            "unread_only": str(unread_only).lower(),
            "limit": limit,
            "offset": offset,
        }
        return self._http.get("/messages", params=params)

    def sent(self, limit: int = 50, offset: int = 0) -> dict:
        """
        Get messages sent by this agent.

        Args:
            limit: Max messages to return
            offset: Pagination offset

        Returns:
            Dict with 'messages' list and 'total' count
        """
        params = {
            "inbox": "false",
            "limit": limit,
            "offset": offset,
        }
        return self._http.get("/messages", params=params)

    def mark_read(self, message_id: str | UUID) -> dict:
        """
        Mark a message as read.

        Args:
            message_id: ID of the message

        Returns:
            Updated message object
        """
        return self._http.post(f"/messages/{message_id}/read", {})


class InvocationClient:
    """Client for invoking capabilities on other agents."""

    def __init__(self, http_client):
        self._http = http_client

    def invoke(
        self,
        agent_id: str | UUID,
        capability: str,
        input_data: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        async_mode: bool = False,
    ) -> dict:
        """
        Invoke a capability on another agent.

        Args:
            agent_id: Target agent's ID
            capability: Name of the capability to invoke
            input_data: Input data for the capability
            timeout_seconds: Timeout in seconds (1-300)
            async_mode: If True, return immediately with invocation ID

        Returns:
            Invocation object with id, status, output_data, etc.
        """
        data = {
            "input": input_data or {},
            "timeout_seconds": timeout_seconds,
            "async_mode": async_mode,
        }
        return self._http.post(f"/invoke/{agent_id}/{capability}", data)

    def get(self, invocation_id: str | UUID) -> dict:
        """
        Get an invocation by ID.

        Args:
            invocation_id: ID of the invocation

        Returns:
            Invocation object
        """
        return self._http.get(f"/invocations/{invocation_id}")

    def list(
        self,
        as_caller: bool = True,
        status: str | None = None,
        limit: int = 50,
    ) -> dict:
        """
        List invocations for this agent.

        Args:
            as_caller: If True, list invocations made by this agent.
                      If False, list invocations received.
            status: Filter by status (pending, processing, completed, failed)
            limit: Max invocations to return

        Returns:
            Dict with 'invocations' list and 'total' count
        """
        params = {
            "as_caller": str(as_caller).lower(),
            "limit": limit,
        }
        if status:
            params["status"] = status
        return self._http.get("/invocations", params=params)

    def pending(self) -> dict:
        """
        Get pending work for this agent (invocations and messages).

        Returns:
            Dict with 'invocations' and 'messages' lists
        """
        return self._http.get("/agents/me/pending")

    def complete(
        self,
        invocation_id: str | UUID,
        output: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict:
        """
        Complete an invocation with a result.

        Args:
            invocation_id: ID of the invocation to complete
            output: Output data (if successful)
            error: Error message (if failed)

        Returns:
            Updated invocation object
        """
        data = {}
        if output is not None:
            data["output"] = output
        if error is not None:
            data["error"] = error
        return self._http.post(f"/invocations/{invocation_id}/complete", data)


class WebhookClient:
    """Client for managing webhooks."""

    def __init__(self, http_client):
        self._http = http_client

    def set(
        self,
        endpoint_url: str,
        events: list[str] | None = None,
    ) -> dict:
        """
        Configure webhook for receiving invocations and messages.

        Args:
            endpoint_url: URL to receive webhook calls
            events: List of events to receive (invocation, message)

        Returns:
            Webhook configuration
        """
        data = {
            "endpoint_url": endpoint_url,
            "events": events or ["invocation", "message"],
        }
        return self._http.post("/agents/me/webhook", data)

    def get(self) -> dict | None:
        """
        Get current webhook configuration.

        Returns:
            Webhook config or None if not set
        """
        return self._http.get("/agents/me/webhook")

    def remove(self) -> None:
        """Remove webhook configuration."""
        self._http.delete("/agents/me/webhook")
