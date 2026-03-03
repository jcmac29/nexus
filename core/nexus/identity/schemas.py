"""Pydantic schemas for identity API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# --- Agent Schemas ---


class AgentCreate(BaseModel):
    """Request schema for creating an agent."""

    name: str = Field(..., min_length=1, max_length=255, description="Display name for the agent")
    slug: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="Unique URL-friendly identifier (lowercase, hyphens allowed)",
    )
    description: str | None = Field(None, max_length=2000, description="Agent description")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class AgentUpdate(BaseModel):
    """Request schema for updating an agent."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    metadata: dict | None = None


class AgentResponse(BaseModel):
    """Response schema for agent data."""

    id: UUID
    name: str
    slug: str
    description: str | None
    metadata: dict
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentCreateResponse(BaseModel):
    """Response schema for agent creation (includes API key)."""

    agent: AgentResponse
    api_key: str = Field(..., description="API key - only shown once, save it securely")


# --- API Key Schemas ---


class APIKeyCreate(BaseModel):
    """Request schema for creating an API key."""

    name: str = Field("default", max_length=255, description="Name for this API key")
    scopes: list[str] = Field(
        default=["read", "write"],
        description="Permission scopes for this key",
    )
    expires_in_days: int | None = Field(
        None,
        ge=1,
        le=365,
        description="Days until key expires (null for no expiration)",
    )


class APIKeyResponse(BaseModel):
    """Response schema for API key data (without the actual key)."""

    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreateResponse(BaseModel):
    """Response schema for API key creation (includes full key)."""

    key: APIKeyResponse
    api_key: str = Field(..., description="Full API key - only shown once, save it securely")


class APIKeyRotateRequest(BaseModel):
    """Request schema for rotating an API key."""

    name: str | None = Field(None, max_length=255, description="Name for new key (defaults to old name + rotated)")
    scopes: list[str] | None = Field(None, description="Scopes for new key (defaults to old key's scopes)")
    expires_in_days: int | None = Field(
        None,
        ge=1,
        le=365,
        description="Days until new key expires",
    )
