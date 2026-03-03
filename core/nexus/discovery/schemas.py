"""Pydantic schemas for discovery API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CapabilityCreate(BaseModel):
    """Request schema for registering a capability."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Name of the capability (e.g., 'text-translation')",
    )
    description: str | None = Field(
        None,
        max_length=2000,
        description="Human-readable description of what this capability does",
    )
    category: str | None = Field(
        None,
        max_length=100,
        description="Category (e.g., 'language', 'code', 'data')",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Tags for filtering",
    )
    endpoint_url: str | None = Field(
        None,
        description="URL endpoint for this capability (if applicable)",
    )
    input_schema: dict | None = Field(
        None,
        description="JSON Schema for expected input",
    )
    output_schema: dict | None = Field(
        None,
        description="JSON Schema for expected output",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata",
    )


class CapabilityUpdate(BaseModel):
    """Request schema for updating a capability."""

    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    endpoint_url: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    metadata: dict | None = None
    status: str | None = Field(None, description="active, inactive, or deprecated")


class CapabilityResponse(BaseModel):
    """Response schema for capability data."""

    id: UUID
    agent_id: UUID
    name: str
    description: str | None
    category: str | None
    tags: list[str]
    endpoint_url: str | None
    input_schema: dict | None
    output_schema: dict | None
    metadata: dict
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscoverRequest(BaseModel):
    """Request schema for discovering capabilities."""

    query: str | None = Field(
        None,
        description="Semantic search query",
    )
    name: str | None = Field(
        None,
        description="Filter by exact capability name",
    )
    category: str | None = Field(
        None,
        description="Filter by category",
    )
    tags: list[str] | None = Field(
        None,
        description="Filter by tags (any match)",
    )
    limit: int = Field(20, ge=1, le=100)


class DiscoverResult(BaseModel):
    """A single discovery result."""

    agent_id: UUID
    agent_name: str
    agent_slug: str
    capability: CapabilityResponse
    score: float | None = Field(None, description="Relevance score (for semantic search)")


class DiscoverResponse(BaseModel):
    """Response schema for discovery search."""

    results: list[DiscoverResult]
    total: int


class AgentCapabilitiesResponse(BaseModel):
    """Response schema for listing an agent's capabilities."""

    agent_id: UUID
    agent_name: str
    agent_slug: str
    capabilities: list[CapabilityResponse]
