"""API routes for graph relationships."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.graph.models import NodeType, RelationshipType
from nexus.graph.schemas import (
    EdgeResponse,
    EdgesResponse,
    NodeReference,
    PathRequest,
    PathResponse,
    RelatedMemoriesResponse,
    RelationshipCreate,
    RelationshipResponse,
    TraversalRequest,
    TraversalResponse,
    TraversalNode,
)
from nexus.graph.service import GraphService
from nexus.identity.models import Agent

router = APIRouter(prefix="/graph", tags=["graph"])


async def get_graph_service(db: AsyncSession = Depends(get_db)) -> GraphService:
    """Get graph service instance."""
    return GraphService(db)


@router.post(
    "/relationships",
    response_model=RelationshipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_relationship(
    data: RelationshipCreate,
    agent: Agent = Depends(get_current_agent),
    service: GraphService = Depends(get_graph_service),
):
    """
    Create a relationship between two nodes.

    Relationships are directional: source -> target.
    If the relationship already exists, its weight and metadata are updated.
    """
    relationship = await service.create_relationship(
        source_type=data.source_type,
        source_id=data.source_id,
        target_type=data.target_type,
        target_id=data.target_id,
        relationship_type=data.relationship_type,
        weight=data.weight,
        metadata=data.metadata,
        created_by_agent_id=agent.id,
    )
    return relationship


@router.get("/relationships/{relationship_id}", response_model=RelationshipResponse)
async def get_relationship(
    relationship_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: GraphService = Depends(get_graph_service),
):
    """Get a relationship by ID."""
    relationship = await service.get_relationship(relationship_id)
    if not relationship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found",
        )
    # SECURITY: Only allow viewing relationships created by this agent
    if relationship.created_by_agent_id != agent.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this relationship",
        )
    return relationship


@router.delete(
    "/relationships/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_relationship(
    relationship_id: UUID,
    agent: Agent = Depends(get_current_agent),
    service: GraphService = Depends(get_graph_service),
):
    """
    Delete a relationship by ID.

    Only the agent who created the relationship can delete it.
    """
    deleted = await service.delete_relationship(relationship_id, agent_id=agent.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship not found or not authorized to delete",
        )


@router.get("/nodes/{node_type}/{node_id}/edges", response_model=EdgesResponse)
async def get_node_edges(
    node_type: NodeType,
    node_id: UUID,
    direction: str = Query(default="both", pattern="^(outgoing|incoming|both)$"),
    relationship_types: list[RelationshipType] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    agent: Agent = Depends(get_current_agent),
    service: GraphService = Depends(get_graph_service),
):
    """
    Get all edges connected to a node.

    - **direction**: Filter by edge direction (outgoing, incoming, or both)
    - **relationship_types**: Filter by relationship types
    """
    # SECURITY: Pass agent_id to filter to relationships this agent can access
    edges, total = await service.get_edges(
        node_type=node_type,
        node_id=node_id,
        direction=direction,
        relationship_types=relationship_types,
        limit=limit,
        offset=offset,
        agent_id=agent.id,
    )

    edge_responses = []
    for rel, dir in edges:
        # Determine connected node based on direction
        if dir == "outgoing":
            connected = NodeReference(node_type=rel.target_type, node_id=rel.target_id)
        else:
            connected = NodeReference(node_type=rel.source_type, node_id=rel.source_id)

        edge_responses.append(
            EdgeResponse(
                relationship=RelationshipResponse.model_validate(rel),
                direction=dir,
                connected_node=connected,
            )
        )

    return EdgesResponse(
        node=NodeReference(node_type=node_type, node_id=node_id),
        edges=edge_responses,
        total=total,
    )


@router.post("/traverse", response_model=TraversalResponse)
async def traverse_graph(
    data: TraversalRequest,
    agent: Agent = Depends(get_current_agent),
    service: GraphService = Depends(get_graph_service),
):
    """
    Traverse the graph from a starting node.

    Returns all reachable nodes up to max_depth, along with the relationships traversed.
    """
    # SECURITY: Pass agent_id to filter traversal to accessible relationships
    nodes, relationships = await service.traverse(
        start_type=data.start_type,
        start_id=data.start_id,
        max_depth=data.max_depth,
        relationship_types=data.relationship_types,
        direction=data.direction,
        agent_id=agent.id,
    )

    return TraversalResponse(
        start=NodeReference(node_type=data.start_type, node_id=data.start_id),
        nodes=[
            TraversalNode(
                node_type=n["node_type"],
                node_id=n["node_id"],
                depth=n["depth"],
                path=n["path"],
            )
            for n in nodes
        ],
        relationships=[RelationshipResponse.model_validate(r) for r in relationships],
    )


@router.post("/path", response_model=PathResponse)
async def find_path(
    data: PathRequest,
    agent: Agent = Depends(get_current_agent),
    service: GraphService = Depends(get_graph_service),
):
    """
    Find the shortest path between two nodes.

    Uses breadth-first search to find the shortest path.
    """
    # SECURITY: Pass agent_id to filter path search to accessible relationships
    path = await service.find_path(
        source_type=data.source_type,
        source_id=data.source_id,
        target_type=data.target_type,
        target_id=data.target_id,
        max_depth=data.max_depth,
        agent_id=agent.id,
    )

    if path is None:
        return PathResponse(found=False)

    return PathResponse(
        found=True,
        path=[RelationshipResponse.model_validate(r) for r in path],
        length=len(path),
    )


@router.get("/memories/{memory_id}/related", response_model=RelatedMemoriesResponse)
async def get_related_memories(
    memory_id: UUID,
    relationship_types: list[RelationshipType] | None = Query(default=None),
    max_depth: int = Query(default=1, ge=1, le=3),
    limit: int = Query(default=50, ge=1, le=200),
    agent: Agent = Depends(get_current_agent),
    service: GraphService = Depends(get_graph_service),
):
    """
    Get memories related to a given memory.

    Returns memories connected via graph relationships, with relationship info.
    """
    # SECURITY: Pass agent_id to filter to memories this agent can access
    related = await service.get_related_memories(
        memory_id=memory_id,
        relationship_types=relationship_types,
        max_depth=max_depth,
        limit=limit,
        agent_id=agent.id,
    )

    return RelatedMemoriesResponse(
        memory_id=memory_id,
        related=related,
        total=len(related),
    )
