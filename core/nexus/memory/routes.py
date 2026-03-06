"""API routes for memory management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.memory.schemas import (
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
    MemoryShareRequest,
    MemoryShareResponse,
    MemoryStore,
    MemoryUpdate,
)
from nexus.memory.service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])


async def get_memory_service(db: AsyncSession = Depends(get_db)) -> MemoryService:
    """Dependency to get memory service."""
    return MemoryService(db)




# --- Memory CRUD Routes ---


@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Store a memory",
)
async def store_memory(
    data: MemoryStore,
    current_agent: Agent = Depends(get_current_agent),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    """
    Store a new memory or update an existing one with the same key.

    Memories are automatically indexed for semantic search.
    """
    memory = await service.store(
        agent_id=current_agent.id,
        key=data.key,
        value=data.value,
        namespace=data.namespace,
        scope=data.scope,
        user_id=data.user_id,
        session_id=data.session_id,
        tags=data.tags,
        text_content=data.text_content,
        expires_in_seconds=data.expires_in_seconds,
    )

    return MemoryResponse(
        id=memory.id,
        key=memory.key,
        value=memory.value,
        namespace=memory.namespace,
        scope=memory.scope.value,
        user_id=memory.user_id,
        session_id=memory.session_id,
        tags=memory.tags,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        expires_at=memory.expires_at,
    )


@router.get(
    "/{key}",
    response_model=MemoryResponse,
    summary="Get a memory by key",
)
async def get_memory(
    key: str,
    namespace: str = Query("default"),
    user_id: str | None = Query(None),
    session_id: str | None = Query(None),
    current_agent: Agent = Depends(get_current_agent),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryResponse:
    """Get a memory by its key."""
    memory = await service.get_by_key(
        agent_id=current_agent.id,
        key=key,
        namespace=namespace,
        user_id=user_id,
        session_id=session_id,
    )

    if not memory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory with key '{key}' not found",
        )

    return MemoryResponse(
        id=memory.id,
        key=memory.key,
        value=memory.value,
        namespace=memory.namespace,
        scope=memory.scope.value,
        user_id=memory.user_id,
        session_id=memory.session_id,
        tags=memory.tags,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        expires_at=memory.expires_at,
    )


@router.get(
    "",
    response_model=list[MemoryResponse],
    summary="List memories",
)
async def list_memories(
    namespace: str | None = Query(None),
    user_id: str | None = Query(None),
    session_id: str | None = Query(None),
    tags: list[str] | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),  # SECURITY: Limit offset to prevent expensive scans
    current_agent: Agent = Depends(get_current_agent),
    service: MemoryService = Depends(get_memory_service),
) -> list[MemoryResponse]:
    """List memories with optional filters."""
    memories = await service.list_memories(
        agent_id=current_agent.id,
        namespace=namespace,
        user_id=user_id,
        session_id=session_id,
        tags=tags,
        limit=limit,
        offset=offset,
    )

    return [
        MemoryResponse(
            id=m.id,
            key=m.key,
            value=m.value,
            namespace=m.namespace,
            scope=m.scope.value,
            user_id=m.user_id,
            session_id=m.session_id,
            tags=m.tags,
            created_at=m.created_at,
            updated_at=m.updated_at,
            expires_at=m.expires_at,
        )
        for m in memories
    ]


@router.delete(
    "/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a memory",
)
async def delete_memory(
    key: str,
    namespace: str = Query("default"),
    current_agent: Agent = Depends(get_current_agent),
    service: MemoryService = Depends(get_memory_service),
) -> None:
    """Delete a memory by its key."""
    deleted = await service.delete_by_key(
        agent_id=current_agent.id,
        key=key,
        namespace=namespace,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory with key '{key}' not found",
        )


# --- Search Routes ---


@router.post(
    "/search",
    response_model=MemorySearchResponse,
    summary="Search memories semantically",
)
async def search_memories(
    data: MemorySearchRequest,
    current_agent: Agent = Depends(get_current_agent),
    service: MemoryService = Depends(get_memory_service),
) -> MemorySearchResponse:
    """
    Search memories using semantic similarity.

    The query is embedded and compared against stored memories.
    Includes memories shared with this agent if `include_shared` is true.
    """
    results = await service.search(
        agent_id=current_agent.id,
        query=data.query,
        namespace=data.namespace,
        user_id=data.user_id,
        session_id=data.session_id,
        tags=data.tags,
        limit=data.limit,
        include_shared=data.include_shared,
    )

    return MemorySearchResponse(
        results=[
            MemorySearchResult(
                memory=MemoryResponse(
                    id=memory.id,
                    key=memory.key,
                    value=memory.value,
                    namespace=memory.namespace,
                    scope=memory.scope.value,
                    user_id=memory.user_id,
                    session_id=memory.session_id,
                    tags=memory.tags,
                    created_at=memory.created_at,
                    updated_at=memory.updated_at,
                    expires_at=memory.expires_at,
                ),
                score=score,
                owner_agent_id=owner_id,
            )
            for memory, score, owner_id in results
        ],
        total=len(results),
    )


# --- Share Routes ---


@router.post(
    "/{memory_id}/share",
    response_model=MemoryShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Share a memory with another agent",
)
async def share_memory(
    memory_id: UUID,
    data: MemoryShareRequest,
    current_agent: Agent = Depends(get_current_agent),
    service: MemoryService = Depends(get_memory_service),
) -> MemoryShareResponse:
    """Share a memory with another agent, granting them access."""
    share = await service.share(
        memory_id=memory_id,
        owner_agent_id=current_agent.id,
        share_with_agent_id=data.agent_id,
        permissions=data.permissions,
    )

    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found or you don't own it",
        )

    return MemoryShareResponse(
        id=share.id,
        memory_id=share.memory_id,
        shared_with_agent_id=share.shared_with_agent_id,
        permissions=share.permissions,
        created_at=share.created_at,
    )


@router.delete(
    "/{memory_id}/share/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a memory share",
)
async def revoke_memory_share(
    memory_id: UUID,
    agent_id: UUID,
    current_agent: Agent = Depends(get_current_agent),
    service: MemoryService = Depends(get_memory_service),
) -> None:
    """Revoke another agent's access to a shared memory."""
    revoked = await service.revoke_share(
        memory_id=memory_id,
        owner_agent_id=current_agent.id,
        share_with_agent_id=agent_id,
    )

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share not found or you don't own the memory",
        )
