"""API routes for identity management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.cache import get_cache
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.identity.schemas import (
    AgentCreate,
    AgentCreateResponse,
    AgentResponse,
    AgentUpdate,
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyResponse,
    APIKeyRotateRequest,
)
from nexus.identity.service import IdentityService
from nexus.security.ip_utils import get_client_ip

router = APIRouter(prefix="/agents", tags=["identity"])


async def get_identity_service(db: AsyncSession = Depends(get_db)) -> IdentityService:
    """Dependency to get identity service."""
    return IdentityService(db)


# --- Rate Limiting ---


async def registration_rate_limit(request: Request):
    """
    SECURITY: Rate limit agent registration to prevent mass account creation.
    Limit: 5 registrations per hour per IP address.
    """
    cache = await get_cache()

    # SECURITY: Use secure IP extraction that validates X-Forwarded-For
    client_ip = get_client_ip(request)

    key = f"ratelimit:registration:{client_ip}"

    allowed, current, remaining = await cache.rate_limit_check(
        key=key,
        limit=5,  # 5 registrations
        window_seconds=3600,  # per hour
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Too many registration attempts. Please try again later.",
                "retry_after": 3600,
            },
            headers={"Retry-After": "3600"},
        )


async def api_key_creation_rate_limit(request: Request):
    """
    SECURITY: Rate limit API key creation to prevent abuse.
    Limit: 10 keys per hour per IP address.
    """
    cache = await get_cache()

    # SECURITY: Use secure IP extraction that validates X-Forwarded-For
    client_ip = get_client_ip(request)

    key = f"ratelimit:apikey_create:{client_ip}"

    allowed, current, remaining = await cache.rate_limit_check(
        key=key,
        limit=10,  # 10 key creations
        window_seconds=3600,  # per hour
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Too many API key creation attempts. Please try again later.",
                "retry_after": 3600,
            },
            headers={"Retry-After": "3600"},
        )


async def api_key_rotation_rate_limit(
    request: Request,
    current_agent: Agent = Depends(get_current_agent),
):
    """
    SECURITY: Rate limit API key rotation to prevent abuse.
    Limit: 5 rotations per hour per AGENT (not IP) - stricter for rotation.
    """
    cache = await get_cache()

    # Rate limit by agent_id (more important than IP for authenticated operations)
    key = f"ratelimit:apikey_rotate:{current_agent.id}"

    allowed, current, remaining = await cache.rate_limit_check(
        key=key,
        limit=5,  # 5 rotations per hour per agent
        window_seconds=3600,
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "message": "Too many API key rotation attempts. Please try again later.",
                "retry_after": 3600,
                "limit": 5,
                "used": current,
            },
            headers={"Retry-After": "3600"},
        )



# --- Agent Routes ---


@router.post(
    "",
    response_model=AgentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new agent",
)
async def create_agent(
    data: AgentCreate,
    service: IdentityService = Depends(get_identity_service),
    _: None = Depends(registration_rate_limit),  # SECURITY: Rate limit registration
) -> AgentCreateResponse:
    """
    Register a new AI agent with Nexus.

    Returns the agent details and an API key. **Save the API key securely -
    it will only be shown once.**
    """
    # Check if slug is already taken
    existing = await service.get_agent_by_slug(data.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent with slug '{data.slug}' already exists",
        )

    agent, api_key = await service.create_agent(
        name=data.name,
        slug=data.slug,
        description=data.description,
        metadata=data.metadata,
    )

    return AgentCreateResponse(
        agent=AgentResponse(
            id=agent.id,
            name=agent.name,
            slug=agent.slug,
            description=agent.description,
            metadata=agent.metadata_,
            status=agent.status.value,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        ),
        api_key=api_key,
    )


@router.get(
    "/me",
    response_model=AgentResponse,
    summary="Get current agent",
)
async def get_me(
    current_agent: Agent = Depends(get_current_agent),
) -> AgentResponse:
    """Get the currently authenticated agent's details."""
    return AgentResponse(
        id=current_agent.id,
        name=current_agent.name,
        slug=current_agent.slug,
        description=current_agent.description,
        metadata=current_agent.metadata_,
        status=current_agent.status.value,
        created_at=current_agent.created_at,
        updated_at=current_agent.updated_at,
    )


@router.patch(
    "/me",
    response_model=AgentResponse,
    summary="Update current agent",
)
async def update_me(
    data: AgentUpdate,
    current_agent: Agent = Depends(get_current_agent),
    service: IdentityService = Depends(get_identity_service),
) -> AgentResponse:
    """Update the currently authenticated agent's details."""
    agent = await service.update_agent(
        agent=current_agent,
        name=data.name,
        description=data.description,
        metadata=data.metadata,
    )
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        slug=agent.slug,
        description=agent.description,
        metadata=agent.metadata_,
        status=agent.status.value,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete current agent",
)
async def delete_me(
    current_agent: Agent = Depends(get_current_agent),
    service: IdentityService = Depends(get_identity_service),
) -> None:
    """Delete the currently authenticated agent (soft delete)."""
    await service.delete_agent(current_agent)


# --- API Key Routes ---


@router.post(
    "/me/keys",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
)
async def create_api_key(
    data: APIKeyCreate,
    current_agent: Agent = Depends(get_current_agent),
    service: IdentityService = Depends(get_identity_service),
    _: None = Depends(api_key_creation_rate_limit),  # SECURITY: Rate limit key creation
) -> APIKeyCreateResponse:
    """
    Create a new API key for the current agent.

    **Save the API key securely - it will only be shown once.**
    """
    api_key_model, api_key_string = await service.create_api_key(
        agent_id=current_agent.id,
        name=data.name,
        scopes=data.scopes,
        expires_in_days=data.expires_in_days,
    )

    return APIKeyCreateResponse(
        key=APIKeyResponse(
            id=api_key_model.id,
            name=api_key_model.name,
            key_prefix=api_key_model.key_prefix,
            scopes=api_key_model.scopes,
            expires_at=api_key_model.expires_at,
            last_used_at=api_key_model.last_used_at,
            created_at=api_key_model.created_at,
        ),
        api_key=api_key_string,
    )


@router.get(
    "/me/keys",
    response_model=list[APIKeyResponse],
    summary="List API keys",
)
async def list_api_keys(
    current_agent: Agent = Depends(get_current_agent),
    service: IdentityService = Depends(get_identity_service),
) -> list[APIKeyResponse]:
    """List all API keys for the current agent."""
    keys = await service.list_api_keys(current_agent.id)
    return [
        APIKeyResponse(
            id=key.id,
            name=key.name,
            key_prefix=key.key_prefix,
            scopes=key.scopes,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
            created_at=key.created_at,
        )
        for key in keys
    ]


@router.delete(
    "/me/keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: UUID,
    current_agent: Agent = Depends(get_current_agent),
    service: IdentityService = Depends(get_identity_service),
) -> None:
    """Revoke (delete) an API key."""
    success = await service.revoke_api_key(current_agent.id, key_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )


@router.post(
    "/me/keys/{key_id}/rotate",
    response_model=APIKeyCreateResponse,
    summary="Rotate an API key",
)
async def rotate_api_key(
    key_id: UUID,
    data: APIKeyRotateRequest,
    current_agent: Agent = Depends(get_current_agent),
    service: IdentityService = Depends(get_identity_service),
    _: None = Depends(api_key_rotation_rate_limit),  # SECURITY: Rate limit rotation
) -> APIKeyCreateResponse:
    """
    Rotate an API key - creates a new key and revokes the old one atomically.

    **Save the new API key securely - it will only be shown once.**
    """
    try:
        new_key, api_key_string = await service.rotate_api_key(
            agent_id=current_agent.id,
            old_key_id=key_id,
            new_name=data.name,
            new_scopes=data.scopes,
            expires_in_days=data.expires_in_days,
        )

        return APIKeyCreateResponse(
            key=APIKeyResponse(
                id=new_key.id,
                name=new_key.name,
                key_prefix=new_key.key_prefix,
                scopes=new_key.scopes,
                expires_at=new_key.expires_at,
                last_used_at=new_key.last_used_at,
                created_at=new_key.created_at,
            ),
            api_key=api_key_string,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
