"""Admin API schemas."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from nexus.admin.models import AdminRole


def validate_password_strength(password: str) -> str:
    """
    SECURITY: Validate password meets complexity requirements.
    Requirements:
    - At least 12 characters (increased from 8 for better security)
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character
    - Not a commonly used password
    """
    # SECURITY: Common passwords to block
    COMMON_PASSWORDS = {
        "password123!", "admin123456!", "welcome12345!", "changeme1234!",
        "letmein12345!", "qwerty123456!", "password1234!", "admin1234567!",
    }

    if password.lower() in COMMON_PASSWORDS:
        raise ValueError("This password is too common. Please choose a stronger password.")

    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\;'/`~]", password):
        raise ValueError("Password must contain at least one special character")
    return password


# Auth schemas
class LoginRequest(BaseModel):
    """Login request with email and password."""

    email: EmailStr
    password: str = Field(min_length=8)


class LoginResponse(BaseModel):
    """Login response with tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


class AdminUserResponse(BaseModel):
    """Admin user info response."""

    id: UUID
    email: str
    name: str
    role: AdminRole
    account_id: UUID | None
    is_active: bool
    created_at: datetime
    last_login: datetime | None

    model_config = {"from_attributes": True}


# Dashboard stats schemas
class DashboardStats(BaseModel):
    """Dashboard statistics."""

    total_agents: int
    active_agents: int
    total_memories: int
    total_teams: int
    total_capabilities: int
    api_calls_today: int
    api_calls_this_month: int


class AgentSummary(BaseModel):
    """Agent summary for admin listing."""

    id: UUID
    name: str
    slug: str
    status: str
    capabilities_count: int
    memories_count: int
    created_at: datetime
    last_seen: datetime | None

    model_config = {"from_attributes": True}


class AgentCreate(BaseModel):
    """Create agent request."""

    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    status: str = "active"


class AgentUpdate(BaseModel):
    """Update agent request."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    status: str | None = None


class AgentDetail(BaseModel):
    """Detailed agent info."""

    id: UUID
    name: str
    slug: str
    description: str | None
    status: str
    capabilities_count: int
    memories_count: int
    created_at: datetime
    last_seen: datetime | None
    api_key_prefix: str | None = None

    model_config = {"from_attributes": True}


class TeamSummary(BaseModel):
    """Team summary for admin listing."""

    id: UUID
    name: str
    slug: str
    member_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamCreate(BaseModel):
    """Create team request."""

    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: str | None = None
    owner_agent_id: UUID


class TeamUpdate(BaseModel):
    """Update team request."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None


class TeamMemberAdd(BaseModel):
    """Add team member request."""

    agent_id: UUID
    role: str = "member"


class TeamDetail(BaseModel):
    """Detailed team info."""

    id: UUID
    name: str
    slug: str
    description: str | None
    owner_agent_id: UUID
    member_count: int
    members: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class MemorySearchResult(BaseModel):
    """Memory search result."""

    id: UUID
    agent_id: UUID
    agent_name: str
    content: str
    memory_type: str
    created_at: datetime
    relevance_score: float | None = None

    model_config = {"from_attributes": True}


class ActivityItem(BaseModel):
    """Recent activity item."""

    id: UUID
    type: str  # agent_created, memory_stored, capability_invoked, etc.
    description: str
    agent_id: UUID | None
    agent_name: str | None
    timestamp: datetime

    model_config = {"from_attributes": True}


class InstanceSettings(BaseModel):
    """Instance-level settings."""

    instance_name: str
    allow_registration: bool
    require_email_verification: bool
    default_rate_limit: int
    features: dict


class InstanceSettingsUpdate(BaseModel):
    """Update instance settings."""

    instance_name: str | None = None
    allow_registration: bool | None = None
    require_email_verification: bool | None = None
    default_rate_limit: int | None = None
    features: dict | None = None


# Pagination
class PaginatedResponse(BaseModel):
    """Generic paginated response."""

    items: list
    total: int
    page: int
    page_size: int
    pages: int
