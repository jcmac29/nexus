"""Server-Sent Events streaming service."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import UUID


class EventStream:
    """Manages event streams for an agent."""

    def __init__(self, agent_id: UUID):
        self.agent_id = agent_id
        self.queue: asyncio.Queue = asyncio.Queue()
        self.connected = True

    async def send(self, event: str, data: dict[str, Any]):
        """Send an event to this stream."""
        if self.connected:
            await self.queue.put({
                "event": event,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    async def events(self) -> AsyncGenerator[str, None]:
        """Generate SSE formatted events."""
        try:
            while self.connected:
                try:
                    # Wait for event with timeout to send keepalive
                    event = await asyncio.wait_for(self.queue.get(), timeout=30)
                    yield f"event: {event['event']}\n"
                    yield f"data: {json.dumps(event['data'])}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        finally:
            self.connected = False

    def disconnect(self):
        """Disconnect this stream."""
        self.connected = False


class EventManager:
    """Manages all event streams."""

    def __init__(self):
        self._streams: dict[UUID, list[EventStream]] = {}

    def connect(self, agent_id: UUID) -> EventStream:
        """Create a new event stream for an agent."""
        stream = EventStream(agent_id)
        if agent_id not in self._streams:
            self._streams[agent_id] = []
        self._streams[agent_id].append(stream)
        return stream

    def disconnect(self, stream: EventStream):
        """Remove an event stream."""
        stream.disconnect()
        if stream.agent_id in self._streams:
            self._streams[stream.agent_id] = [
                s for s in self._streams[stream.agent_id] if s != stream
            ]

    async def broadcast(self, agent_id: UUID, event: str, data: dict[str, Any]):
        """Broadcast an event to all streams for an agent."""
        if agent_id in self._streams:
            for stream in self._streams[agent_id]:
                await stream.send(event, data)

    async def broadcast_invocation_update(
        self,
        agent_id: UUID,
        invocation_id: str,
        status: str,
        output_data: dict | None = None,
        error: str | None = None,
    ):
        """Broadcast an invocation status update."""
        await self.broadcast(agent_id, "invocation.update", {
            "invocation_id": invocation_id,
            "status": status,
            "output_data": output_data,
            "error": error,
        })

    async def broadcast_message(
        self,
        agent_id: UUID,
        message_id: str,
        from_agent_id: str,
        subject: str | None,
        content: dict,
    ):
        """Broadcast a new message notification."""
        await self.broadcast(agent_id, "message.received", {
            "message_id": message_id,
            "from_agent_id": from_agent_id,
            "subject": subject,
            "content": content,
        })

    def get_connection_count(self, agent_id: UUID) -> int:
        """Get number of active connections for an agent."""
        return len(self._streams.get(agent_id, []))


# Singleton instance
event_manager = EventManager()
