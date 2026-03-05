"""Marketplace service."""

from datetime import datetime, timezone
from uuid import UUID
from typing import Any

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.marketplace.models import (
    MarketplaceListing,
    MarketplaceReview,
    MarketplaceFavorite,
    ListingStatus,
)
from nexus.discovery.models import Capability
from nexus.identity.models import Agent


class MarketplaceService:
    """Service for managing the public marketplace."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # --- Listings ---

    async def create_listing(
        self,
        capability_id: UUID,
        agent_id: UUID,
        title: str,
        short_description: str,
        category: str,
        long_description: str | None = None,
        tags: list[str] | None = None,
    ) -> MarketplaceListing:
        """Create a new marketplace listing."""
        listing = MarketplaceListing(
            capability_id=capability_id,
            agent_id=agent_id,
            title=title,
            short_description=short_description,
            long_description=long_description,
            category=category,
            tags=",".join(tags) if tags else None,
            status=ListingStatus.DRAFT,
        )
        self.db.add(listing)
        await self.db.flush()
        return listing

    async def get_listing(self, listing_id: UUID) -> MarketplaceListing | None:
        """Get a listing by ID."""
        result = await self.db.execute(
            select(MarketplaceListing).where(MarketplaceListing.id == listing_id)
        )
        return result.scalar_one_or_none()

    async def get_listing_by_capability(self, capability_id: UUID) -> MarketplaceListing | None:
        """Get listing for a capability."""
        result = await self.db.execute(
            select(MarketplaceListing).where(MarketplaceListing.capability_id == capability_id)
        )
        return result.scalar_one_or_none()

    async def update_listing(
        self,
        listing_id: UUID,
        agent_id: UUID,
        **updates,
    ) -> MarketplaceListing | None:
        """Update a listing."""
        result = await self.db.execute(
            select(MarketplaceListing).where(
                MarketplaceListing.id == listing_id,
                MarketplaceListing.agent_id == agent_id,
            )
        )
        listing = result.scalar_one_or_none()
        if not listing:
            return None

        # SECURITY: Whitelist of allowed fields to prevent mass assignment attacks
        allowed_fields = {
            "name", "slug", "description", "listing_type", "category",
            "price_credits", "tags", "documentation_url", "source_url",
            "status", "metadata",
        }
        for key, value in updates.items():
            if key in allowed_fields and value is not None:
                if key == "tags" and isinstance(value, list):
                    value = ",".join(value)
                setattr(listing, key, value)

        listing.updated_at = datetime.now(timezone.utc)
        return listing

    async def publish_listing(self, listing_id: UUID, agent_id: UUID) -> MarketplaceListing | None:
        """Publish a listing to the marketplace."""
        listing = await self.update_listing(
            listing_id,
            agent_id,
            status=ListingStatus.PUBLISHED,
        )
        if listing:
            listing.published_at = datetime.now(timezone.utc)
        return listing

    async def unpublish_listing(self, listing_id: UUID, agent_id: UUID) -> MarketplaceListing | None:
        """Unpublish a listing."""
        return await self.update_listing(
            listing_id,
            agent_id,
            status=ListingStatus.ARCHIVED,
        )

    async def search_listings(
        self,
        query: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        featured_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search marketplace listings."""
        stmt = (
            select(MarketplaceListing, Capability, Agent)
            .join(Capability, MarketplaceListing.capability_id == Capability.id)
            .join(Agent, MarketplaceListing.agent_id == Agent.id)
            .where(MarketplaceListing.status == ListingStatus.PUBLISHED)
        )

        if query:
            search_term = f"%{query}%"
            stmt = stmt.where(
                or_(
                    MarketplaceListing.title.ilike(search_term),
                    MarketplaceListing.short_description.ilike(search_term),
                    MarketplaceListing.tags.ilike(search_term),
                )
            )

        if category:
            stmt = stmt.where(MarketplaceListing.category == category)

        if tags:
            for tag in tags:
                stmt = stmt.where(MarketplaceListing.tags.ilike(f"%{tag}%"))

        if featured_only:
            now = datetime.now(timezone.utc)
            stmt = stmt.where(
                MarketplaceListing.is_featured == True,
                or_(
                    MarketplaceListing.featured_until.is_(None),
                    MarketplaceListing.featured_until > now,
                ),
            )

        stmt = (
            stmt
            .order_by(
                MarketplaceListing.is_featured.desc(),
                MarketplaceListing.invocation_count.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        listings = []
        for row in result.all():
            listing, capability, agent = row
            listings.append({
                "id": str(listing.id),
                "capability_id": str(listing.capability_id),
                "capability_name": capability.name,
                "agent_id": str(listing.agent_id),
                "agent_name": agent.name,
                "agent_slug": agent.slug,
                "title": listing.title,
                "short_description": listing.short_description,
                "category": listing.category,
                "tags": listing.tags.split(",") if listing.tags else [],
                "invocation_count": listing.invocation_count,
                "avg_rating": listing.avg_rating,
                "review_count": listing.review_count,
                "is_featured": listing.is_featured,
                "published_at": listing.published_at.isoformat() if listing.published_at else None,
            })

        return listings

    async def get_categories(self) -> list[dict[str, Any]]:
        """Get all categories with counts."""
        result = await self.db.execute(
            select(
                MarketplaceListing.category,
                func.count(MarketplaceListing.id).label("count"),
            )
            .where(MarketplaceListing.status == ListingStatus.PUBLISHED)
            .group_by(MarketplaceListing.category)
            .order_by(func.count(MarketplaceListing.id).desc())
        )
        return [
            {"category": row.category, "count": row.count}
            for row in result.all()
        ]

    async def increment_invocation_count(self, capability_id: UUID) -> None:
        """Increment invocation count for a listing."""
        result = await self.db.execute(
            select(MarketplaceListing).where(MarketplaceListing.capability_id == capability_id)
        )
        listing = result.scalar_one_or_none()
        if listing:
            listing.invocation_count += 1

    # --- Reviews ---

    async def add_review(
        self,
        listing_id: UUID,
        reviewer_agent_id: UUID,
        rating: int,
        comment: str | None = None,
    ) -> MarketplaceReview:
        """Add a review to a listing."""
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        review = MarketplaceReview(
            listing_id=listing_id,
            reviewer_agent_id=reviewer_agent_id,
            rating=rating,
            comment=comment,
        )
        self.db.add(review)
        await self.db.flush()

        # Update listing stats
        await self._update_listing_stats(listing_id)

        return review

    async def get_reviews(
        self,
        listing_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get reviews for a listing."""
        result = await self.db.execute(
            select(MarketplaceReview, Agent)
            .join(Agent, MarketplaceReview.reviewer_agent_id == Agent.id)
            .where(MarketplaceReview.listing_id == listing_id)
            .order_by(MarketplaceReview.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return [
            {
                "id": str(review.id),
                "reviewer_id": str(agent.id),
                "reviewer_name": agent.name,
                "rating": review.rating,
                "comment": review.comment,
                "created_at": review.created_at.isoformat(),
            }
            for review, agent in result.all()
        ]

    async def _update_listing_stats(self, listing_id: UUID) -> None:
        """Update listing stats from reviews."""
        result = await self.db.execute(
            select(
                func.count(MarketplaceReview.id).label("count"),
                func.avg(MarketplaceReview.rating).label("avg"),
            ).where(MarketplaceReview.listing_id == listing_id)
        )
        row = result.one()

        listing_result = await self.db.execute(
            select(MarketplaceListing).where(MarketplaceListing.id == listing_id)
        )
        listing = listing_result.scalar_one_or_none()
        if listing:
            listing.review_count = row.count or 0
            listing.avg_rating = float(row.avg) if row.avg else 0.0

    # --- Favorites ---

    async def add_favorite(self, listing_id: UUID, agent_id: UUID) -> MarketplaceFavorite:
        """Add a listing to favorites."""
        # Check if already favorited
        result = await self.db.execute(
            select(MarketplaceFavorite).where(
                MarketplaceFavorite.listing_id == listing_id,
                MarketplaceFavorite.agent_id == agent_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        favorite = MarketplaceFavorite(
            listing_id=listing_id,
            agent_id=agent_id,
        )
        self.db.add(favorite)
        await self.db.flush()
        return favorite

    async def remove_favorite(self, listing_id: UUID, agent_id: UUID) -> bool:
        """Remove a listing from favorites."""
        result = await self.db.execute(
            select(MarketplaceFavorite).where(
                MarketplaceFavorite.listing_id == listing_id,
                MarketplaceFavorite.agent_id == agent_id,
            )
        )
        favorite = result.scalar_one_or_none()
        if favorite:
            await self.db.delete(favorite)
            return True
        return False

    async def get_favorites(self, agent_id: UUID) -> list[dict[str, Any]]:
        """Get an agent's favorite listings."""
        result = await self.db.execute(
            select(MarketplaceFavorite, MarketplaceListing)
            .join(MarketplaceListing, MarketplaceFavorite.listing_id == MarketplaceListing.id)
            .where(MarketplaceFavorite.agent_id == agent_id)
            .order_by(MarketplaceFavorite.created_at.desc())
        )
        return [
            {
                "listing_id": str(listing.id),
                "title": listing.title,
                "category": listing.category,
                "favorited_at": fav.created_at.isoformat(),
            }
            for fav, listing in result.all()
        ]
