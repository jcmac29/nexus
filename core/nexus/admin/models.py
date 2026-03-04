"""Admin user models for dashboard authentication."""

import enum
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nexus.database import Base


class AdminRole(str, enum.Enum):
    """Admin user roles."""

    SUPER_ADMIN = "super_admin"  # Full access across all tenants
    ADMIN = "admin"  # Full access within their tenant
    VIEWER = "viewer"  # Read-only access


class AdminUser(Base):
    """Admin user for dashboard access."""

    __tablename__ = "admin_users"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[AdminRole] = mapped_column(
        Enum(AdminRole, values_callable=lambda x: [e.value for e in x]),
        default=AdminRole.VIEWER,
    )

    # Multi-tenant: nullable for super_admin (access to all tenants)
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AdminSession(Base):
    """Admin session for refresh token tracking."""

    __tablename__ = "admin_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    admin_id: Mapped[UUID] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
