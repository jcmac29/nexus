"""Pydantic schemas for graph API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from nexus.graph.models import NodeType, RelationshipType


class RelationshipCreate(BaseModel):
    """Request to create a relationship."""

    source_type: NodeType
    source_id: UUID
    target_type: NodeType
    target_id: UUID
    relationship_type: RelationshipType
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)


class RelationshipResponse(BaseModel):
    """Response containing a relationship."""

    id: UUID
    source_type: NodeType
    source_id: UUID
    target_type: NodeType
    target_id: UUID
    relationship_type: RelationshipType
    weight: float
    metadata: dict
    created_by_agent_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NodeReference(BaseModel):
    """Reference to a node in the graph."""

    node_type: NodeType
    node_id: UUID


class EdgeResponse(BaseModel):
    """An edge connected to a node."""

    relationship: RelationshipResponse
    direction: str  # "outgoing" or "incoming"
    connected_node: NodeReference


class EdgesResponse(BaseModel):
    """Response containing edges for a node."""

    node: NodeReference
    edges: list[EdgeResponse]
    total: int


class TraversalRequest(BaseModel):
    """Request for graph traversal."""

    start_type: NodeType
    start_id: UUID
    max_depth: int = Field(default=2, ge=1, le=5)
    relationship_types: list[RelationshipType] | None = None
    direction: str = Field(default="outgoing", pattern="^(outgoing|incoming|both)$")


class TraversalNode(BaseModel):
    """A node in traversal results."""

    node_type: NodeType
    node_id: UUID
    depth: int
    path: list[UUID]  # Relationship IDs in path


class TraversalResponse(BaseModel):
    """Response from graph traversal."""

    start: NodeReference
    nodes: list[TraversalNode]
    relationships: list[RelationshipResponse]


class RelatedMemoriesResponse(BaseModel):
    """Response for related memories query."""

    memory_id: UUID
    related: list[dict]  # Memory data with relationship info
    total: int


class PathRequest(BaseModel):
    """Request to find path between nodes."""

    source_type: NodeType
    source_id: UUID
    target_type: NodeType
    target_id: UUID
    max_depth: int = Field(default=5, ge=1, le=10)


class PathResponse(BaseModel):
    """Response containing path between nodes."""

    found: bool
    path: list[RelationshipResponse] | None = None
    length: int | None = None
