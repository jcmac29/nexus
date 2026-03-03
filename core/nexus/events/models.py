"""Event models for pub/sub system."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer, Index
from sqlalchemy.dialects.postgresql import UUID

from nexus.database import Base


class EventType(str, enum.Enum):
    """Built-in event types."""
    # Agent events
    AGENT_CONNECTED = "agent.connected"
    AGENT_DISCONNECTED = "agent.disconnected"
    AGENT_UPDATED = "agent.updated"

    # Memory events
    MEMORY_CREATED = "memory.created"
    MEMORY_UPDATED = "memory.updated"
    MEMORY_DELETED = "memory.deleted"

    # Message events
    MESSAGE_SENT = "message.sent"
    MESSAGE_RECEIVED = "message.received"

    # Invocation events
    INVOCATION_STARTED = "invocation.started"
    INVOCATION_COMPLETED = "invocation.completed"
    INVOCATION_FAILED = "invocation.failed"

    # Conversation events
    CONVERSATION_CREATED = "conversation.created"
    CONVERSATION_MESSAGE = "conversation.message"
    CONVERSATION_CLOSED = "conversation.closed"

    # Tool events
    TOOL_EXECUTED = "tool.executed"
    TOOL_FAILED = "tool.failed"

    # Team events
    TEAM_JOINED = "team.joined"
    TEAM_LEFT = "team.left"

    # Workflow events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_STEP_COMPLETED = "workflow.step_completed"
    WORKFLOW_COMPLETED = "workflow.completed"

    # System events
    SYSTEM_ALERT = "system.alert"
    SYSTEM_MAINTENANCE = "system.maintenance"

    # Custom events
    CUSTOM = "custom"


class Event(Base):
    """An event in the system."""

    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Event identification
    event_type = Column(String(100), nullable=False, index=True)
    topic = Column(String(255), nullable=False, index=True)  # e.g., "agent.123", "team.456", "global"

    # Source
    source_id = Column(UUID(as_uuid=True), nullable=True)
    source_type = Column(String(50), nullable=True)  # agent, system, tool, etc.

    # Event data
    payload = Column(JSON, default=dict)
    metadata = Column(JSON, default=dict)

    # Targeting (optional - for directed events)
    target_id = Column(UUID(as_uuid=True), nullable=True)
    target_type = Column(String(50), nullable=True)

    # Delivery tracking
    delivered_count = Column(Integer, default=0)
    acknowledged_count = Column(Integer, default=0)

    # TTL for event cleanup
    expires_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_events_topic_created", "topic", "created_at"),
        Index("ix_events_type_created", "event_type", "created_at"),
    )


class EventSubscription(Base):
    """A subscription to events."""

    __tablename__ = "event_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Subscriber
    subscriber_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    subscriber_type = Column(String(50), default="agent")

    # What to subscribe to
    topic_pattern = Column(String(255), nullable=False)  # Supports wildcards: "agent.*", "team.123.*"
    event_types = Column(JSON, default=list)  # Empty = all types

    # Delivery configuration
    delivery_method = Column(String(50), default="websocket")  # websocket, webhook, queue
    webhook_url = Column(String(1024), nullable=True)
    webhook_secret = Column(String(255), nullable=True)

    # Filters
    filters = Column(JSON, default=dict)  # Additional filter conditions

    # State
    is_active = Column(Boolean, default=True)
    last_event_at = Column(DateTime, nullable=True)
    event_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_subscriptions_topic", "topic_pattern"),
    )


class EventDelivery(Base):
    """Track event delivery to subscribers."""

    __tablename__ = "event_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("event_subscriptions.id", ondelete="CASCADE"), nullable=False)

    status = Column(String(50), default="pending")  # pending, delivered, failed, acknowledged
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
