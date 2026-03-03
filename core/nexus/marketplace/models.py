"""Marketplace models."""

import enum
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import String, Integer, DateTime, ForeignKey, Float, Enum, Text, Index, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from nexus.database import Base


class ListingStatus(str, enum.Enum):
    """Marketplace listing status."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class MarketplaceListing(Base):
    """Public marketplace listing for a capability."""

    __tablename__ = "marketplace_listings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    capability_id: Mapped[UUID] = mapped_column(ForeignKey("capabilities.id", ondelete="CASCADE"), unique=True)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    # Display info
    title: Mapped[str] = mapped_column(String(200))
    short_description: Mapped[str] = mapped_column(String(500))
    long_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Categorization
    category: Mapped[str] = mapped_column(String(50))  # ai, data, media, utility, etc.
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # comma-separated

    # Status
    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus), default=ListingStatus.DRAFT
    )

    # Stats
    invocation_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_rating: Mapped[float] = mapped_column(Float, default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)

    # Featured/promoted
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    featured_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_marketplace_category", "category"),
        Index("ix_marketplace_status", "status"),
    )


class MarketplaceReview(Base):
    """Review for a marketplace listing."""

    __tablename__ = "marketplace_reviews"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(ForeignKey("marketplace_listings.id", ondelete="CASCADE"))
    reviewer_agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    rating: Mapped[int] = mapped_column(Integer)  # 1-5
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_marketplace_reviews_listing", "listing_id"),
    )


class MarketplaceFavorite(Base):
    """User favorites in marketplace."""

    __tablename__ = "marketplace_favorites"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    listing_id: Mapped[UUID] = mapped_column(ForeignKey("marketplace_listings.id", ondelete="CASCADE"))
    agent_id: Mapped[UUID] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_marketplace_favorites_agent", "agent_id"),
    )
