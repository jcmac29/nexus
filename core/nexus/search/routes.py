"""Search API routes."""

from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.search.service import SearchService
from nexus.search.models import IndexedContentType

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    content_types: list[str] | None = None
    tags: list[str] | None = None
    categories: list[str] | None = None
    include_public: bool = True
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    search_type: str = "hybrid"  # text, semantic, hybrid


class IndexContentRequest(BaseModel):
    content_type: str
    content_id: str
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    metadata: dict | None = None
    categories: list[str] | None = None
    is_public: bool = False
    boost: float = 1.0


@router.post("/")
async def search(
    request: SearchRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Search indexed content."""
    service = SearchService(db)

    content_type_map = {
        "agent": IndexedContentType.AGENT,
        "memory": IndexedContentType.MEMORY,
        "message": IndexedContentType.MESSAGE,
        "document": IndexedContentType.DOCUMENT,
        "conversation": IndexedContentType.CONVERSATION,
        "tool": IndexedContentType.TOOL,
        "capability": IndexedContentType.CAPABILITY,
        "event": IndexedContentType.EVENT,
        "file": IndexedContentType.FILE,
        "device": IndexedContentType.DEVICE,
    }

    content_types = None
    if request.content_types:
        content_types = [
            content_type_map[ct]
            for ct in request.content_types
            if ct in content_type_map
        ]

    results = await service.search(
        query=request.query,
        owner_id=agent.id,
        content_types=content_types,
        tags=request.tags,
        categories=request.categories,
        include_public=request.include_public,
        limit=request.limit,
        offset=request.offset,
        search_type=request.search_type,
        user_id=agent.id,
    )

    return {
        "query": request.query,
        "count": len(results),
        "results": results,
    }


@router.get("/suggest")
async def suggest(
    prefix: str,
    content_types: str | None = None,
    limit: int = Query(default=10, le=50),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get search suggestions."""
    service = SearchService(db)

    content_type_map = {
        "agent": IndexedContentType.AGENT,
        "memory": IndexedContentType.MEMORY,
        "document": IndexedContentType.DOCUMENT,
    }

    types = None
    if content_types:
        types = [
            content_type_map[ct]
            for ct in content_types.split(",")
            if ct in content_type_map
        ]

    suggestions = await service.suggest(
        prefix=prefix,
        owner_id=agent.id,
        content_types=types,
        limit=limit,
    )

    return {"suggestions": suggestions}


@router.get("/similar/{content_id}")
async def get_similar(
    content_id: str,
    limit: int = Query(default=10, le=50),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Find similar content."""
    service = SearchService(db)
    # SECURITY: Pass owner_id to filter results to content the agent can access
    results = await service.get_similar(UUID(content_id), owner_id=agent.id, limit=limit)
    return {"results": results}


@router.post("/index")
async def index_content(
    request: IndexContentRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Index content for search."""
    service = SearchService(db)

    content_type_map = {
        "agent": IndexedContentType.AGENT,
        "memory": IndexedContentType.MEMORY,
        "message": IndexedContentType.MESSAGE,
        "document": IndexedContentType.DOCUMENT,
        "conversation": IndexedContentType.CONVERSATION,
        "tool": IndexedContentType.TOOL,
        "capability": IndexedContentType.CAPABILITY,
        "event": IndexedContentType.EVENT,
        "file": IndexedContentType.FILE,
        "device": IndexedContentType.DEVICE,
    }

    content_type = content_type_map.get(request.content_type)
    if not content_type:
        return {"error": f"Unknown content type: {request.content_type}"}

    index_entry = await service.index_content(
        content_type=content_type,
        content_id=UUID(request.content_id),
        owner_id=agent.id,
        title=request.title,
        content=request.content,
        summary=request.summary,
        tags=request.tags,
        metadata=request.metadata,
        categories=request.categories,
        is_public=request.is_public,
        boost=request.boost,
    )

    return {
        "id": str(index_entry.id),
        "indexed_at": index_entry.indexed_at.isoformat(),
        "has_embedding": index_entry.embedding is not None,
    }


@router.delete("/index/{content_type}/{content_id}")
async def remove_from_index(
    content_type: str,
    content_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Remove content from search index."""
    service = SearchService(db)

    content_type_map = {
        "agent": IndexedContentType.AGENT,
        "memory": IndexedContentType.MEMORY,
        "document": IndexedContentType.DOCUMENT,
    }

    ct = content_type_map.get(content_type)
    if ct:
        # SECURITY: Pass owner_id to ensure only owned content is removed
        await service.remove_from_index(ct, UUID(content_id), owner_id=agent.id)

    return {"status": "removed"}
