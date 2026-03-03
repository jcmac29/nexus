"""Database models for webhook management."""

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base


class RetryPolicy(str, enum.Enum):
    """Webhook retry policies."""

    EXPONENTIAL = "exponential"  # 2^n seconds
    LINEAR = "linear"  # n * 10 seconds
    NONE = "none"  # No retries


class DeliveryStatus(str, enum.Enum):
    """Webhook delivery status."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


class WebhookEndpoint(Base):
    """
    User-configured webhook endpoint.

    Agents can register webhooks to receive event notifications.
    """

    __tablename__ = "webhook_endpoints"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    agent_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)  # For HMAC signing

    # Event subscriptions - supports wildcards like "memory.*"
    event_types: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        default=[],
        server_default="{}",
    )

    # Configuration
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    retry_policy: Mapped[RetryPolicy] = mapped_column(
        Enum(RetryPolicy, values_callable=lambda x: [e.value for e in x]),
        default=RetryPolicy.EXPONENTIAL,
        server_default="exponential",
    )
    max_retries: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, server_default="30")

    # Custom headers to include in requests
    custom_headers: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )

    # Statistics
    total_deliveries: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    successful_deliveries: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    failed_deliveries: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    delivery_logs: Mapped[list["WebhookDeliveryLog"]] = relationship(
        "WebhookDeliveryLog",
        back_populates="endpoint",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<WebhookEndpoint {self.name} ({self.url})>"


class WebhookDeliveryLog(Base):
    """
    Persistent delivery log for webhook attempts.

    Tracks each delivery attempt with response details.
    """

    __tablename__ = "webhook_delivery_logs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    webhook_endpoint_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    # Event information
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Delivery status
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, values_callable=lambda x: [e.value for e in x]),
        default=DeliveryStatus.PENDING,
        server_default="pending",
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Response details
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)  # Truncated to 10KB
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Error tracking
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    endpoint: Mapped["WebhookEndpoint"] = relationship(
        "WebhookEndpoint",
        back_populates="delivery_logs",
    )

    __table_args__ = (
        Index("ix_webhook_logs_endpoint_created", "webhook_endpoint_id", "created_at"),
        Index("ix_webhook_logs_status_retry", "status", "next_retry_at"),
    )

    def __repr__(self) -> str:
        return f"<WebhookDeliveryLog {self.event_type} -> {self.status}>"
