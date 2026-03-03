"""Chat models for external chat platform integrations."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class ChatPlatform(str, enum.Enum):
    """Supported chat platforms."""
    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    TEAMS = "teams"
    MATTERMOST = "mattermost"
    ROCKET_CHAT = "rocket_chat"


class ChatConnectionStatus(str, enum.Enum):
    """Connection status."""
    PENDING = "pending"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    REVOKED = "revoked"


class ChatConnection(Base):
    """Connection to an external chat platform."""

    __tablename__ = "chat_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    owner_type = Column(String(50), default="agent")

    # Platform
    platform = Column(Enum(ChatPlatform), nullable=False)
    status = Column(Enum(ChatConnectionStatus), default=ChatConnectionStatus.PENDING)

    # Credentials (encrypted)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    bot_token = Column(Text, nullable=True)
    webhook_url = Column(String(1024), nullable=True)

    # Platform-specific IDs
    workspace_id = Column(String(255), nullable=True)  # Slack workspace, Discord guild
    workspace_name = Column(String(255), nullable=True)
    bot_user_id = Column(String(255), nullable=True)

    # Configuration
    config = Column(JSON, default=dict)

    # AI agent handling messages
    ai_agent_id = Column(UUID(as_uuid=True), nullable=True)
    auto_reply_enabled = Column(Boolean, default=False)
    system_prompt = Column(Text, nullable=True)

    # Sync settings
    sync_channels = Column(JSON, default=list)  # Channel IDs to sync
    sync_history = Column(Boolean, default=False)

    # Token expiry
    token_expires_at = Column(DateTime, nullable=True)

    # Metadata
    last_sync_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    channels = relationship("ChatChannel", back_populates="connection", cascade="all, delete-orphan")


class ChatChannel(Base):
    """A channel in a chat platform."""

    __tablename__ = "chat_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("chat_connections.id", ondelete="CASCADE"), nullable=False)

    # Channel info
    channel_id = Column(String(255), nullable=False)  # Platform's channel ID
    channel_name = Column(String(255), nullable=True)
    channel_type = Column(String(50), nullable=True)  # public, private, dm, group

    # Topic/description
    topic = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    # Membership
    member_count = Column(Integer, default=0)
    is_member = Column(Boolean, default=True)

    # AI handling
    ai_agent_id = Column(UUID(as_uuid=True), nullable=True)
    auto_reply_enabled = Column(Boolean, default=False)
    mention_only = Column(Boolean, default=True)  # Only respond when mentioned

    # Sync
    is_synced = Column(Boolean, default=False)
    last_message_at = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    connection = relationship("ChatConnection", back_populates="channels")
    messages = relationship("ChatMessage", back_populates="channel", cascade="all, delete-orphan")


class ChatMessage(Base):
    """A message from a chat platform."""

    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("chat_channels.id", ondelete="CASCADE"), nullable=False)

    # Message info
    message_id = Column(String(255), nullable=False)  # Platform's message ID
    thread_id = Column(String(255), nullable=True)  # Thread/reply chain ID

    # Sender
    sender_id = Column(String(255), nullable=False)  # Platform user ID
    sender_name = Column(String(255), nullable=True)
    sender_avatar = Column(String(1024), nullable=True)
    is_bot = Column(Boolean, default=False)

    # Content
    content = Column(Text, nullable=True)
    content_type = Column(String(50), default="text")  # text, image, file, etc.
    attachments = Column(JSON, default=list)
    embeds = Column(JSON, default=list)
    mentions = Column(JSON, default=list)

    # Reactions
    reactions = Column(JSON, default=list)

    # Reply info
    is_reply = Column(Boolean, default=False)
    reply_to_id = Column(String(255), nullable=True)

    # AI response
    ai_response_id = Column(UUID(as_uuid=True), nullable=True)  # Our response message
    ai_processed = Column(Boolean, default=False)

    # Timing
    platform_timestamp = Column(DateTime, nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow)

    channel = relationship("ChatChannel", back_populates="messages")


class ChatCommand(Base):
    """Custom slash command for chat platforms."""

    __tablename__ = "chat_commands"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("chat_connections.id", ondelete="CASCADE"), nullable=False)

    # Command info
    name = Column(String(100), nullable=False)  # /command
    description = Column(Text, nullable=True)
    usage = Column(String(255), nullable=True)

    # Handler
    handler_type = Column(String(50), default="agent")  # agent, workflow, webhook
    handler_id = Column(UUID(as_uuid=True), nullable=True)
    handler_config = Column(JSON, default=dict)

    # Options/arguments
    options = Column(JSON, default=list)  # Command options/arguments

    # Permissions
    allowed_channels = Column(JSON, default=list)  # Empty = all
    allowed_roles = Column(JSON, default=list)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
