"""Streaming module - Server-Sent Events for real-time updates."""

from nexus.streaming.service import EventStream, event_manager
from nexus.streaming.routes import router

__all__ = ["EventStream", "event_manager", "router"]
