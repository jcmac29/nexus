"""OAuth models."""

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nexus.database import Base
from nexus.security.encryption import EncryptedText


class OAuthProvider(str, Enum):
    """Supported OAuth providers."""
    GOOGLE = "google"
    GITHUB = "github"
    MICROSOFT = "microsoft"
    DISCORD = "discord"


class OAuthConnection(Base):
    """OAuth connection linking external identity to agent."""

    __tablename__ = "oauth_connections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id"))

    # Provider info
    provider: Mapped[OAuthProvider] = mapped_column(SQLEnum(OAuthProvider))
    provider_user_id: Mapped[str] = mapped_column(String(255))
    provider_email: Mapped[str | None] = mapped_column(String(255))
    provider_username: Mapped[str | None] = mapped_column(String(255))

    # SECURITY: Tokens encrypted at rest using EncryptedText column type
    access_token: Mapped[str] = mapped_column(EncryptedText)
    refresh_token: Mapped[str | None] = mapped_column(EncryptedText)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Profile data from provider
    profile_data: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent = relationship("Agent", backref="oauth_connections")
