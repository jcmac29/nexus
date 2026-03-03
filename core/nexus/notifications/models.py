"""Notification models for push notifications."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID

from nexus.database import Base


class NotificationChannel(str, enum.Enum):
    """Notification delivery channels."""
    PUSH = "push"
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    IN_APP = "in_app"
    SLACK = "slack"
    DISCORD = "discord"


class NotificationPriority(str, enum.Enum):
    """Notification priority."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationStatus(str, enum.Enum):
    """Status of a notification."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    EXPIRED = "expired"


class NotificationCategory(str, enum.Enum):
    """Notification categories."""
    SYSTEM = "system"
    AGENT = "agent"
    MESSAGE = "message"
    ALERT = "alert"
    REMINDER = "reminder"
    UPDATE = "update"
    PROMOTION = "promotion"
    TASK = "task"


class PushDevice(Base):
    """A registered push notification device."""

    __tablename__ = "push_devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    owner_type = Column(String(50), default="agent")

    # Device info
    device_token = Column(String(512), nullable=False, unique=True)
    device_type = Column(String(50), nullable=False)  # ios, android, web
    device_name = Column(String(255), nullable=True)
    device_model = Column(String(255), nullable=True)

    # Push service
    push_provider = Column(String(50), default="fcm")  # fcm, apns, web_push
    endpoint_arn = Column(String(512), nullable=True)  # AWS SNS endpoint

    # Preferences
    enabled = Column(Boolean, default=True)
    categories_enabled = Column(JSON, default=list)  # Empty = all enabled

    # App info
    app_version = Column(String(50), nullable=True)
    os_version = Column(String(50), nullable=True)

    # Activity
    last_active_at = Column(DateTime, nullable=True)
    last_push_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NotificationPreference(Base):
    """User notification preferences."""

    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False, unique=True)

    # Channel preferences
    push_enabled = Column(Boolean, default=True)
    email_enabled = Column(Boolean, default=True)
    sms_enabled = Column(Boolean, default=False)
    in_app_enabled = Column(Boolean, default=True)

    # Category preferences
    categories = Column(JSON, default=dict)  # {category: {channels: [], enabled: bool}}

    # Quiet hours
    quiet_hours_enabled = Column(Boolean, default=False)
    quiet_hours_start = Column(String(10), nullable=True)  # "22:00"
    quiet_hours_end = Column(String(10), nullable=True)  # "08:00"
    quiet_hours_timezone = Column(String(100), default="UTC")

    # Digest preferences
    digest_enabled = Column(Boolean, default=False)
    digest_frequency = Column(String(50), default="daily")  # daily, weekly
    digest_time = Column(String(10), default="09:00")

    # Do not disturb
    dnd_enabled = Column(Boolean, default=False)
    dnd_until = Column(DateTime, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Notification(Base):
    """A notification record."""

    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Recipient
    recipient_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    recipient_type = Column(String(50), default="agent")

    # Sender
    sender_id = Column(UUID(as_uuid=True), nullable=True)
    sender_type = Column(String(50), nullable=True)

    # Content
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    icon = Column(String(512), nullable=True)
    image = Column(String(512), nullable=True)

    # Metadata
    category = Column(Enum(NotificationCategory), default=NotificationCategory.SYSTEM)
    priority = Column(Enum(NotificationPriority), default=NotificationPriority.NORMAL)
    channel = Column(Enum(NotificationChannel), default=NotificationChannel.IN_APP)

    # Data payload
    data = Column(JSON, default=dict)
    action_url = Column(String(1024), nullable=True)
    actions = Column(JSON, default=list)  # [{action_id, label, url}]

    # Status
    status = Column(Enum(NotificationStatus), default=NotificationStatus.PENDING)
    error_message = Column(Text, nullable=True)

    # Timing
    scheduled_for = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Tracking
    device_id = Column(UUID(as_uuid=True), nullable=True)
    provider_message_id = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class NotificationTemplate(Base):
    """Reusable notification template."""

    __tablename__ = "notification_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Template content
    title_template = Column(String(255), nullable=False)
    body_template = Column(Text, nullable=True)
    icon = Column(String(512), nullable=True)

    # Settings
    category = Column(Enum(NotificationCategory), default=NotificationCategory.SYSTEM)
    priority = Column(Enum(NotificationPriority), default=NotificationPriority.NORMAL)
    default_channels = Column(JSON, default=["in_app"])

    # Variables
    variables = Column(JSON, default=list)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
