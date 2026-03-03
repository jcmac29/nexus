"""Chat module - External chat platform integrations for AI and human agents."""

from nexus.chat.models import ChatConnection, ChatChannel, ChatMessage, ChatCommand
from nexus.chat.service import ChatService
from nexus.chat.routes import router

__all__ = ["ChatConnection", "ChatChannel", "ChatMessage", "ChatCommand", "ChatService", "router"]
