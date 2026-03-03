"""Audit log models."""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base


class AuditAction(str, Enum):
    """Types of auditable actions."""
    # Auth
    LOGIN = "login"
    LOGOUT = "logout"
    API_KEY_CREATED = "api_key_created"
    API_KEY_ROTATED = "api_key_rotated"
    API_KEY_REVOKED = "api_key_revoked"

    # Agent
    AGENT_CREATED = "agent_created"
    AGENT_UPDATED = "agent_updated"
    AGENT_DELETED = "agent_deleted"

    # Memory
    MEMORY_CREATED = "memory_created"
    MEMORY_UPDATED = "memory_updated"
    MEMORY_DELETED = "memory_deleted"
    MEMORY_SHARED = "memory_shared"
    MEMORY_SEARCHED = "memory_searched"

    # Capabilities
    CAPABILITY_REGISTERED = "capability_registered"
    CAPABILITY_UPDATED = "capability_updated"
    CAPABILITY_REMOVED = "capability_removed"

    # Invocations
    INVOCATION_CREATED = "invocation_created"
    INVOCATION_COMPLETED = "invocation_completed"
    INVOCATION_FAILED = "invocation_failed"

    # Teams
    TEAM_CREATED = "team_created"
    TEAM_UPDATED = "team_updated"
    TEAM_DELETED = "team_deleted"
    TEAM_MEMBER_ADDED = "team_member_added"
    TEAM_MEMBER_REMOVED = "team_member_removed"

    # Federation
    PEER_CONNECTED = "peer_connected"
    PEER_DISCONNECTED = "peer_disconnected"
    FEDERATION_REQUEST = "federation_request"

    # Public
    CAPABILITY_PUBLISHED = "capability_published"
    CAPABILITY_UNPUBLISHED = "capability_unpublished"
    PUBLIC_REQUEST = "public_request"

    # Billing
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    PAYMENT_RECEIVED = "payment_received"

    # Admin
    SETTINGS_CHANGED = "settings_changed"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_REVOKED = "permission_revoked"


class AuditResource(str, Enum):
    """Types of resources being audited."""
    AGENT = "agent"
    API_KEY = "api_key"
    MEMORY = "memory"
    CAPABILITY = "capability"
    INVOCATION = "invocation"
    TEAM = "team"
    PEER = "peer"
    SUBSCRIPTION = "subscription"
    SETTINGS = "settings"
    WEBHOOK = "webhook"
    MEDIA = "media"


class AuditLog(Base):
    """Immutable audit log entry."""

    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # Who performed the action
    agent_id: Mapped[UUID | None] = mapped_column(ForeignKey("agents.id"))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(500))

    # What happened
    action: Mapped[AuditAction] = mapped_column(SQLEnum(AuditAction))
    resource_type: Mapped[AuditResource] = mapped_column(SQLEnum(AuditResource))
    resource_id: Mapped[str | None] = mapped_column(String(255))

    # Details (sanitized - no secrets)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)

    # Status
    success: Mapped[bool] = mapped_column(default=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Context
    request_id: Mapped[str | None] = mapped_column(String(100))
    session_id: Mapped[str | None] = mapped_column(String(100))

    # Timestamp (immutable)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    agent = relationship("Agent", backref="audit_logs")

    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_audit_logs_agent_id_timestamp", "agent_id", "timestamp"),
        Index("ix_audit_logs_action_timestamp", "action", "timestamp"),
        Index("ix_audit_logs_resource_timestamp", "resource_type", "resource_id", "timestamp"),
    )
