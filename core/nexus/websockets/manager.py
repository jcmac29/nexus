"""WebSocket connection manager for real-time agent communication."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from fastapi import WebSocket
from collections import defaultdict


@dataclass
class WebSocketConnection:
    """Represents an active WebSocket connection."""

    websocket: WebSocket
    agent_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    subscriptions: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)


class ConnectionManager:
    """Manages WebSocket connections for all agents."""

    def __init__(self):
        # agent_id -> list of connections (agent can have multiple)
        self._connections: dict[str, list[WebSocketConnection]] = defaultdict(list)
        # channel -> set of agent_ids subscribed
        self._channels: dict[str, set[str]] = defaultdict(set)
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> WebSocketConnection:
        """Accept a new WebSocket connection."""
        await websocket.accept()

        conn = WebSocketConnection(
            websocket=websocket,
            agent_id=agent_id,
            metadata=metadata or {},
        )

        async with self._lock:
            self._connections[agent_id].append(conn)

        # Notify presence
        await self._broadcast_presence(agent_id, "online")

        return conn

    async def disconnect(self, conn: WebSocketConnection):
        """Remove a WebSocket connection."""
        async with self._lock:
            if conn in self._connections[conn.agent_id]:
                self._connections[conn.agent_id].remove(conn)

            # Remove from all channels
            for channel in list(conn.subscriptions):
                self._channels[channel].discard(conn.agent_id)

        # Notify presence if no more connections
        if not self._connections[conn.agent_id]:
            await self._broadcast_presence(conn.agent_id, "offline")

    async def subscribe(self, conn: WebSocketConnection, channel: str):
        """Subscribe an agent to a channel."""
        async with self._lock:
            conn.subscriptions.add(channel)
            self._channels[channel].add(conn.agent_id)

    async def unsubscribe(self, conn: WebSocketConnection, channel: str):
        """Unsubscribe an agent from a channel."""
        async with self._lock:
            conn.subscriptions.discard(channel)
            self._channels[channel].discard(conn.agent_id)

    async def send_to_agent(
        self,
        agent_id: str,
        message: dict[str, Any],
    ) -> int:
        """Send a message to all connections of an agent. Returns count sent."""
        connections = self._connections.get(agent_id, [])
        sent = 0

        for conn in connections:
            try:
                await conn.websocket.send_json(message)
                sent += 1
            except Exception:
                # Connection might be closed
                pass

        return sent

    async def send_to_channel(
        self,
        channel: str,
        message: dict[str, Any],
        exclude_agent: str | None = None,
    ) -> int:
        """Broadcast a message to all agents in a channel."""
        agent_ids = self._channels.get(channel, set())
        sent = 0

        for agent_id in agent_ids:
            if agent_id == exclude_agent:
                continue
            sent += await self.send_to_agent(agent_id, message)

        return sent

    async def broadcast(
        self,
        message: dict[str, Any],
        exclude_agent: str | None = None,
    ) -> int:
        """Broadcast a message to all connected agents."""
        sent = 0

        for agent_id, connections in self._connections.items():
            if agent_id == exclude_agent:
                continue
            for conn in connections:
                try:
                    await conn.websocket.send_json(message)
                    sent += 1
                except Exception:
                    pass

        return sent

    async def _broadcast_presence(self, agent_id: str, status: str):
        """Broadcast agent presence change."""
        await self.broadcast(
            {
                "type": "presence",
                "agent_id": agent_id,
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
            },
            exclude_agent=agent_id,
        )

    def get_online_agents(self) -> list[str]:
        """Get list of all online agent IDs."""
        return [
            agent_id
            for agent_id, conns in self._connections.items()
            if conns
        ]

    def get_channel_members(self, channel: str) -> set[str]:
        """Get all agents subscribed to a channel."""
        return self._channels.get(channel, set()).copy()

    def is_online(self, agent_id: str) -> bool:
        """Check if an agent is online."""
        return bool(self._connections.get(agent_id))


# Global connection manager instance
manager = ConnectionManager()
