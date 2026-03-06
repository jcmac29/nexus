"""WebSocket connection manager for real-time agent communication."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from fastapi import WebSocket
from collections import defaultdict

logger = logging.getLogger(__name__)


# SECURITY: Connection limits to prevent DoS attacks
MAX_CONNECTIONS_PER_AGENT = 5  # Maximum 5 concurrent WebSocket connections per agent
MAX_TOTAL_CONNECTIONS = 10000  # Maximum total connections across all agents
CONNECTION_TIMEOUT_SECONDS = 3600  # 1 hour connection timeout


class ConnectionLimitExceeded(Exception):
    """Raised when connection limits are exceeded."""
    pass


@dataclass
class WebSocketConnection:
    """Represents an active WebSocket connection."""

    websocket: WebSocket
    agent_id: str
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    timeout_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    subscriptions: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Set timeout after initialization."""
        from datetime import timedelta
        self.timeout_at = self.connected_at + timedelta(seconds=CONNECTION_TIMEOUT_SECONDS)

    def is_expired(self) -> bool:
        """Check if connection has exceeded timeout."""
        return datetime.now(timezone.utc) > self.timeout_at


class ConnectionManager:
    """Manages WebSocket connections for all agents."""

    def __init__(self):
        # agent_id -> list of connections (agent can have multiple)
        self._connections: dict[str, list[WebSocketConnection]] = defaultdict(list)
        # channel -> set of agent_ids subscribed
        self._channels: dict[str, set[str]] = defaultdict(set)
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    def _get_total_connections(self) -> int:
        """Count total connections across all agents."""
        return sum(len(conns) for conns in self._connections.values())

    async def connect(
        self,
        websocket: WebSocket,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> WebSocketConnection:
        """Accept a new WebSocket connection.

        SECURITY: Enforces per-agent and global connection limits.
        """
        async with self._lock:
            # SECURITY: Check per-agent connection limit
            current_agent_conns = len(self._connections[agent_id])
            if current_agent_conns >= MAX_CONNECTIONS_PER_AGENT:
                logger.warning(
                    f"Connection limit exceeded for agent {agent_id}: "
                    f"{current_agent_conns}/{MAX_CONNECTIONS_PER_AGENT}"
                )
                await websocket.close(code=4029, reason="Too many connections")
                raise ConnectionLimitExceeded(
                    f"Agent {agent_id} has reached the maximum of "
                    f"{MAX_CONNECTIONS_PER_AGENT} concurrent connections"
                )

            # SECURITY: Check global connection limit
            total_conns = self._get_total_connections()
            if total_conns >= MAX_TOTAL_CONNECTIONS:
                logger.warning(
                    f"Global connection limit exceeded: {total_conns}/{MAX_TOTAL_CONNECTIONS}"
                )
                await websocket.close(code=4029, reason="Server at capacity")
                raise ConnectionLimitExceeded("Server has reached maximum connection capacity")

            await websocket.accept()

            conn = WebSocketConnection(
                websocket=websocket,
                agent_id=agent_id,
                metadata=metadata or {},
            )

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
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            exclude_agent=agent_id,
        )

    async def cleanup_expired_connections(self) -> int:
        """Remove expired connections. Returns count of cleaned connections."""
        cleaned = 0
        async with self._lock:
            for agent_id in list(self._connections.keys()):
                expired = [conn for conn in self._connections[agent_id] if conn.is_expired()]
                for conn in expired:
                    try:
                        await conn.websocket.close(code=4000, reason="Connection timeout")
                    except Exception:
                        pass
                    self._connections[agent_id].remove(conn)
                    cleaned += 1
        return cleaned

    def get_connection_stats(self) -> dict:
        """Get connection statistics for monitoring."""
        return {
            "total_connections": self._get_total_connections(),
            "max_total_connections": MAX_TOTAL_CONNECTIONS,
            "max_per_agent": MAX_CONNECTIONS_PER_AGENT,
            "connected_agents": len([aid for aid, conns in self._connections.items() if conns]),
            "total_channels": len(self._channels),
        }

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
