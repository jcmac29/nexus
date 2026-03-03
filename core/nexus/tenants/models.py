"""Database models for multi-tenant support."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus.database import Base


class TenantSettings(Base):
    """
    Per-tenant configuration settings.

    Each account (tenant) can have custom settings for branding,
    features, security, and rate limits.
    """

    __tablename__ = "tenant_settings"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Subdomain/domain configuration
    subdomain: Mapped[str | None] = mapped_column(
        String(63),
        nullable=True,
        unique=True,
        index=True,
    )  # e.g., "acme" for acme.nexus-cloud.com
    custom_domain: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )  # e.g., "api.acme.com"

    # Branding
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # Hex color
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Feature flags
    features: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )  # e.g., {"graph_memory": true, "federation": false, "webhooks": true}

    # Security settings
    allowed_ip_ranges: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )  # CIDR notation, e.g., ["10.0.0.0/8", "192.168.1.0/24"]
    require_2fa: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    session_timeout_minutes: Mapped[int] = mapped_column(
        default=60 * 24 * 7,  # 7 days
        server_default="10080",
    )
    allowed_oauth_providers: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )  # e.g., ["google", "github"]

    # Rate limiting multiplier (1.0 = standard, 2.0 = double limits)
    rate_limit_multiplier: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        server_default="1.0",
    )
    custom_rate_limits: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )  # Override specific limits

    # Webhook settings
    webhook_signing_version: Mapped[str] = mapped_column(
        String(10),
        default="v1",
        server_default="v1",
    )

    # Data residency
    data_region: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )  # e.g., "us-east-1", "eu-west-1"

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<TenantSettings {self.subdomain or self.account_id}>"


class TenantInvite(Base):
    """
    Invitation to join a tenant/account.

    Used for adding users to an existing account.
    """

    __tablename__ = "tenant_invites"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(
        String(50),
        default="member",
        server_default="member",
    )  # admin, member, viewer
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_tenant_invites_account_email", "account_id", "email"),
    )

    def __repr__(self) -> str:
        return f"<TenantInvite {self.email} -> {self.account_id}>"
