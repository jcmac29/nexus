"""WebSocket module for real-time bidirectional communication."""

from nexus.websockets.manager import ConnectionManager, WebSocketConnection
from nexus.websockets.routes import router

__all__ = ["ConnectionManager", "WebSocketConnection", "router"]
