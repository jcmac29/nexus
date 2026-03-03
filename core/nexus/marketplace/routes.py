"""Marketplace API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.marketplace.service import MarketplaceService
from nexus.marketplace.models import ListingStatus

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


# --- Schemas ---

class CreateListingRequest(BaseModel):
    capability_id: str = Field(..., description="Capability to list")
    title: str = Field(..., max_length=200)
    short_description: str = Field(..., max_length=500)
    long_description: str | None = None
    category: str = Field(..., max_length=50)
    tags: list[str] | None = None


class UpdateListingRequest(BaseModel):
    title: str | None = None
    short_description: str | None = None
    long_description: str | None = None
    category: str | None = None
    tags: list[str] | None = None


class ListingResponse(BaseModel):
    id: str
    capability_id: str
    agent_id: str
    title: str
    short_description: str
    long_description: str | None
    category: str
    tags: list[str]
    status: str
    invocation_count: int
    avg_rating: float
    review_count: int
    is_featured: bool
    created_at: str
    published_at: str | None


class AddReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


class ReviewResponse(BaseModel):
    id: str
    reviewer_id: str
    reviewer_name: str
    rating: int
    comment: str | None
    created_at: str


# --- Routes ---

async def get_marketplace_service(db: AsyncSession = Depends(get_db)) -> MarketplaceService:
    return MarketplaceService(db)


@router.get("/search")
async def search_listings(
    q: str | None = Query(None, description="Search query"),
    category: str | None = None,
    tags: str | None = Query(None, description="Comma-separated tags"),
    featured: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Search marketplace listings."""
    tag_list = tags.split(",") if tags else None
    return await service.search_listings(
        query=q,
        category=category,
        tags=tag_list,
        featured_only=featured,
        limit=limit,
        offset=offset,
    )


@router.get("/categories")
async def get_categories(
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Get all marketplace categories."""
    return await service.get_categories()


@router.get("/featured")
async def get_featured_listings(
    limit: int = Query(10, ge=1, le=50),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Get featured listings."""
    return await service.search_listings(featured_only=True, limit=limit)


@router.post("", response_model=ListingResponse, status_code=status.HTTP_201_CREATED)
async def create_listing(
    data: CreateListingRequest,
    agent: Agent = Depends(get_current_agent),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Create a new marketplace listing."""
    listing = await service.create_listing(
        capability_id=UUID(data.capability_id),
        agent_id=agent.id,
        title=data.title,
        short_description=data.short_description,
        long_description=data.long_description,
        category=data.category,
        tags=data.tags,
    )
    return _listing_to_response(listing)


@router.get("/{listing_id}", response_model=ListingResponse)
async def get_listing(
    listing_id: UUID,
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Get a listing by ID."""
    listing = await service.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _listing_to_response(listing)


@router.patch("/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: UUID,
    data: UpdateListingRequest,
    agent: Agent = Depends(get_current_agent),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Update a listing."""
    listing = await service.update_listing(
        listing_id=listing_id,
        agent_id=agent.id,
        title=data.title,
        short_description=data.short_description,
        long_description=data.long_description,
        category=data.category,
        tags=data.tags,
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _listing_to_response(listing)


@router.post("/{listing_id}/publish", response_model=ListingResponse)
async def publish_listing(
    listing_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Publish a listing to the marketplace."""
    listing = await service.publish_listing(listing_id, agent.id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _listing_to_response(listing)


@router.post("/{listing_id}/unpublish", response_model=ListingResponse)
async def unpublish_listing(
    listing_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Unpublish a listing."""
    listing = await service.unpublish_listing(listing_id, agent.id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return _listing_to_response(listing)


# --- Reviews ---

@router.get("/{listing_id}/reviews", response_model=list[ReviewResponse])
async def get_listing_reviews(
    listing_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Get reviews for a listing."""
    reviews = await service.get_reviews(listing_id, limit=limit, offset=offset)
    return [ReviewResponse(**r) for r in reviews]


@router.post("/{listing_id}/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def add_review(
    listing_id: UUID,
    data: AddReviewRequest,
    agent: Agent = Depends(get_current_agent),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Add a review to a listing."""
    review = await service.add_review(
        listing_id=listing_id,
        reviewer_agent_id=agent.id,
        rating=data.rating,
        comment=data.comment,
    )
    return ReviewResponse(
        id=str(review.id),
        reviewer_id=str(agent.id),
        reviewer_name=agent.name,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at.isoformat(),
    )


# --- Favorites ---

@router.get("/favorites/me")
async def get_my_favorites(
    agent: Agent = Depends(get_current_agent),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Get my favorite listings."""
    return await service.get_favorites(agent.id)


@router.post("/{listing_id}/favorite")
async def add_favorite(
    listing_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Add a listing to favorites."""
    await service.add_favorite(listing_id, agent.id)
    return {"status": "favorited"}


@router.delete("/{listing_id}/favorite")
async def remove_favorite(
    listing_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: MarketplaceService = Depends(get_marketplace_service),
):
    """Remove a listing from favorites."""
    removed = await service.remove_favorite(listing_id, agent.id)
    if not removed:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"status": "removed"}


def _listing_to_response(listing) -> ListingResponse:
    return ListingResponse(
        id=str(listing.id),
        capability_id=str(listing.capability_id),
        agent_id=str(listing.agent_id),
        title=listing.title,
        short_description=listing.short_description,
        long_description=listing.long_description,
        category=listing.category,
        tags=listing.tags.split(",") if listing.tags else [],
        status=listing.status.value,
        invocation_count=listing.invocation_count,
        avg_rating=listing.avg_rating,
        review_count=listing.review_count,
        is_featured=listing.is_featured,
        created_at=listing.created_at.isoformat(),
        published_at=listing.published_at.isoformat() if listing.published_at else None,
    )
