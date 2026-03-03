"""Pydantic schemas for memory API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryStore(BaseModel):
    """Request schema for storing a memory."""

    key: str = Field(..., min_length=1, max_length=255, description="Unique key for this memory")
    value: dict = Field(..., description="The memory content (JSON object)")
    namespace: str = Field("default", max_length=255, description="Namespace for organization")
    scope: str = Field("agent", description="Memory scope: agent, user, session, shared")
    user_id: str | None = Field(None, max_length=255, description="User ID for user-scoped memories")
    session_id: str | None = Field(
        None, max_length=255, description="Session ID for session-scoped memories"
    )
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    text_content: str | None = Field(
        None, description="Text content for semantic search (extracted from value if not provided)"
    )
    expires_in_seconds: int | None = Field(
        None, ge=1, description="Seconds until memory expires (null for no expiration)"
    )


class MemoryUpdate(BaseModel):
    """Request schema for updating a memory."""

    value: dict | None = Field(None, description="Updated memory content")
    tags: list[str] | None = Field(None, description="Updated tags")
    text_content: str | None = Field(None, description="Updated text content for search")
    expires_in_seconds: int | None = Field(None, ge=1, description="New expiration time")


class MemoryResponse(BaseModel):
    """Response schema for memory data."""

    id: UUID
    key: str
    value: dict
    namespace: str
    scope: str
    user_id: str | None
    session_id: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None

    model_config = {"from_attributes": True}


class MemorySearchRequest(BaseModel):
    """Request schema for semantic memory search."""

    query: str = Field(..., min_length=1, description="Search query")
    namespace: str | None = Field(None, description="Filter by namespace")
    user_id: str | None = Field(None, description="Filter by user ID")
    session_id: str | None = Field(None, description="Filter by session ID")
    tags: list[str] | None = Field(None, description="Filter by tags (any match)")
    limit: int = Field(10, ge=1, le=100, description="Maximum results to return")
    include_shared: bool = Field(True, description="Include memories shared with this agent")


class MemorySearchResult(BaseModel):
    """A single search result."""

    memory: MemoryResponse
    score: float = Field(..., description="Similarity score (0-1)")
    owner_agent_id: UUID | None = Field(None, description="Agent ID if this is a shared memory")


class MemorySearchResponse(BaseModel):
    """Response schema for memory search."""

    results: list[MemorySearchResult]
    total: int


class MemoryShareRequest(BaseModel):
    """Request schema for sharing a memory."""

    agent_id: UUID = Field(..., description="Agent ID to share with")
    permissions: list[str] = Field(["read"], description="Permissions to grant: read, write")


class MemoryShareResponse(BaseModel):
    """Response schema for memory share."""

    id: UUID
    memory_id: UUID
    shared_with_agent_id: UUID
    permissions: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryListRequest(BaseModel):
    """Request schema for listing memories."""

    namespace: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    tags: list[str] | None = None
    limit: int = Field(50, ge=1, le=100)
    offset: int = Field(0, ge=0)
