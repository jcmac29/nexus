"""API routes for capability discovery."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.discovery.schemas import (
    AgentCapabilitiesResponse,
    CapabilityCreate,
    CapabilityResponse,
    CapabilityUpdate,
    DiscoverRequest,
    DiscoverResponse,
    DiscoverResult,
)
from nexus.discovery.service import DiscoveryService
from nexus.identity.models import Agent

router = APIRouter(tags=["discovery"])


async def get_discovery_service(db: AsyncSession = Depends(get_db)) -> DiscoveryService:
    """Dependency to get discovery service."""
    return DiscoveryService(db)




# --- Capability Management Routes (authenticated) ---


@router.post(
    "/capabilities",
    response_model=CapabilityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a capability",
)
async def register_capability(
    data: CapabilityCreate,
    current_agent: Agent = Depends(get_current_agent),
    service: DiscoveryService = Depends(get_discovery_service),
) -> CapabilityResponse:
    """
    Register a capability for your agent.

    This makes your agent discoverable for this capability.
    """
    capability = await service.register_capability(
        agent_id=current_agent.id,
        name=data.name,
        description=data.description,
        category=data.category,
        tags=data.tags,
        endpoint_url=data.endpoint_url,
        input_schema=data.input_schema,
        output_schema=data.output_schema,
        metadata=data.metadata,
    )

    return CapabilityResponse(
        id=capability.id,
        agent_id=capability.agent_id,
        name=capability.name,
        description=capability.description,
        category=capability.category,
        tags=capability.tags,
        endpoint_url=capability.endpoint_url,
        input_schema=capability.input_schema,
        output_schema=capability.output_schema,
        metadata=capability.metadata_,
        status=capability.status.value,
        created_at=capability.created_at,
        updated_at=capability.updated_at,
    )


@router.get(
    "/capabilities",
    response_model=list[CapabilityResponse],
    summary="List your capabilities",
)
async def list_capabilities(
    current_agent: Agent = Depends(get_current_agent),
    service: DiscoveryService = Depends(get_discovery_service),
) -> list[CapabilityResponse]:
    """List all capabilities registered by your agent."""
    capabilities = await service.list_agent_capabilities(current_agent.id)

    return [
        CapabilityResponse(
            id=cap.id,
            agent_id=cap.agent_id,
            name=cap.name,
            description=cap.description,
            category=cap.category,
            tags=cap.tags,
            endpoint_url=cap.endpoint_url,
            input_schema=cap.input_schema,
            output_schema=cap.output_schema,
            metadata=cap.metadata_,
            status=cap.status.value,
            created_at=cap.created_at,
            updated_at=cap.updated_at,
        )
        for cap in capabilities
    ]


@router.patch(
    "/capabilities/{name}",
    response_model=CapabilityResponse,
    summary="Update a capability",
)
async def update_capability(
    name: str,
    data: CapabilityUpdate,
    current_agent: Agent = Depends(get_current_agent),
    service: DiscoveryService = Depends(get_discovery_service),
) -> CapabilityResponse:
    """Update a capability's details."""
    capability = await service.update_capability(
        agent_id=current_agent.id,
        name=name,
        description=data.description,
        category=data.category,
        tags=data.tags,
        endpoint_url=data.endpoint_url,
        input_schema=data.input_schema,
        output_schema=data.output_schema,
        metadata=data.metadata,
        status=data.status,
    )

    if not capability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability '{name}' not found",
        )

    return CapabilityResponse(
        id=capability.id,
        agent_id=capability.agent_id,
        name=capability.name,
        description=capability.description,
        category=capability.category,
        tags=capability.tags,
        endpoint_url=capability.endpoint_url,
        input_schema=capability.input_schema,
        output_schema=capability.output_schema,
        metadata=capability.metadata_,
        status=capability.status.value,
        created_at=capability.created_at,
        updated_at=capability.updated_at,
    )


@router.delete(
    "/capabilities/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a capability",
)
async def delete_capability(
    name: str,
    current_agent: Agent = Depends(get_current_agent),
    service: DiscoveryService = Depends(get_discovery_service),
) -> None:
    """Remove a capability from your agent."""
    deleted = await service.delete_capability(current_agent.id, name)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability '{name}' not found",
        )


# --- Discovery Routes (public/authenticated) ---


@router.get(
    "/discover",
    response_model=DiscoverResponse,
    summary="Discover capabilities",
)
async def discover(
    query: str | None = Query(None, description="Semantic search query"),
    name: str | None = Query(None, description="Filter by exact name"),
    category: str | None = Query(None, description="Filter by category"),
    tags: list[str] | None = Query(None, description="Filter by tags"),
    limit: int = Query(20, ge=1, le=100),
    service: DiscoveryService = Depends(get_discovery_service),
) -> DiscoverResponse:
    """
    Discover capabilities across all agents.

    Use `query` for semantic search, or filter by name/category/tags.
    """
    results = await service.discover(
        query=query,
        name=name,
        category=category,
        tags=tags,
        limit=limit,
    )

    return DiscoverResponse(
        results=[
            DiscoverResult(
                agent_id=agent.id,
                agent_name=agent.name,
                agent_slug=agent.slug,
                capability=CapabilityResponse(
                    id=cap.id,
                    agent_id=cap.agent_id,
                    name=cap.name,
                    description=cap.description,
                    category=cap.category,
                    tags=cap.tags,
                    endpoint_url=cap.endpoint_url,
                    input_schema=cap.input_schema,
                    output_schema=cap.output_schema,
                    metadata=cap.metadata_,
                    status=cap.status.value,
                    created_at=cap.created_at,
                    updated_at=cap.updated_at,
                ),
                score=score,
            )
            for cap, agent, score in results
        ],
        total=len(results),
    )


@router.get(
    "/discover/agents/{agent_id}",
    response_model=AgentCapabilitiesResponse,
    summary="Get agent capabilities",
)
async def get_agent_capabilities(
    agent_id: UUID,
    service: DiscoveryService = Depends(get_discovery_service),
) -> AgentCapabilitiesResponse:
    """Get all capabilities for a specific agent."""
    result = await service.get_agent_with_capabilities(agent_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    agent, capabilities = result

    return AgentCapabilitiesResponse(
        agent_id=agent.id,
        agent_name=agent.name,
        agent_slug=agent.slug,
        capabilities=[
            CapabilityResponse(
                id=cap.id,
                agent_id=cap.agent_id,
                name=cap.name,
                description=cap.description,
                category=cap.category,
                tags=cap.tags,
                endpoint_url=cap.endpoint_url,
                input_schema=cap.input_schema,
                output_schema=cap.output_schema,
                metadata=cap.metadata_,
                status=cap.status.value,
                created_at=cap.created_at,
                updated_at=cap.updated_at,
            )
            for cap in capabilities
        ],
    )
