"""OAuth API routes."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.auth import get_current_agent
from nexus.database import get_db
from nexus.identity.models import Agent
from nexus.identity.service import IdentityService
from nexus.oauth.models import OAuthProvider
from nexus.oauth.service import OAuthService

router = APIRouter(prefix="/oauth", tags=["oauth"])


# --- Schemas ---


class OAuthInitRequest(BaseModel):
    """Initialize OAuth flow."""
    provider: OAuthProvider
    redirect_uri: str
    client_id: str


class OAuthCallbackRequest(BaseModel):
    """OAuth callback with code."""
    provider: OAuthProvider
    code: str
    state: str
    redirect_uri: str
    client_id: str
    client_secret: str


class OAuthConnectionResponse(BaseModel):
    """OAuth connection info."""
    id: UUID
    provider: OAuthProvider
    provider_email: str | None
    provider_username: str | None
    connected_at: str

    class Config:
        from_attributes = True


# --- Endpoints ---


@router.post("/init")
async def init_oauth(
    request: OAuthInitRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Initialize OAuth flow.

    Returns authorization URL to redirect user to.
    """
    service = OAuthService(session)
    auth_url, state = service.get_authorization_url(
        provider=request.provider,
        redirect_uri=request.redirect_uri,
        client_id=request.client_id,
    )
    return {
        "authorization_url": auth_url,
        "state": state,
    }


@router.post("/callback")
async def oauth_callback(
    request: OAuthCallbackRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Handle OAuth callback.

    Exchanges code for tokens, gets user info, and either:
    - Returns existing agent's API key if OAuth identity is known
    - Creates new agent if this is a new OAuth identity
    """
    oauth_service = OAuthService(session)
    identity_service = IdentityService(session)

    # Exchange code for tokens
    try:
        tokens = await oauth_service.exchange_code(
            provider=request.provider,
            code=request.code,
            redirect_uri=request.redirect_uri,
            client_id=request.client_id,
            client_secret=request.client_secret,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in")

    token_expires_at = None
    if expires_in:
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Get user info from provider
    try:
        user_info = await oauth_service.get_user_info(request.provider, access_token)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get user info: {e}")

    # Extract provider user ID
    provider_user_id = str(user_info.get("id") or user_info.get("sub"))
    if not provider_user_id:
        raise HTTPException(status_code=400, detail="Could not get user ID from provider")

    # Check if this OAuth identity is already linked to an agent
    existing_agent_id = await oauth_service.find_agent_by_oauth(
        provider=request.provider,
        provider_user_id=provider_user_id,
    )

    if existing_agent_id:
        # Existing user - update connection and return API key
        connection = await oauth_service.find_or_create_connection(
            agent_id=existing_agent_id,
            provider=request.provider,
            provider_user_id=provider_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            profile_data=user_info,
        )

        # Generate new API key for this login
        agent, api_key = await identity_service.create_api_key(
            agent_id=existing_agent_id,
            name=f"{request.provider.value}-login",
            scopes=["all"],
            expires_in_days=30,
        )

        return {
            "status": "existing_user",
            "agent_id": str(existing_agent_id),
            "api_key": api_key,
            "provider": request.provider.value,
            "email": user_info.get("email"),
        }

    else:
        # New user - create agent and link OAuth
        email = user_info.get("email", "")
        name = user_info.get("name") or user_info.get("login") or email.split("@")[0]
        slug = f"{request.provider.value}-{provider_user_id[:8]}"

        agent, api_key = await identity_service.register_agent(
            name=name,
            slug=slug,
            description=f"Registered via {request.provider.value}",
        )

        # Link OAuth connection
        await oauth_service.find_or_create_connection(
            agent_id=agent.id,
            provider=request.provider,
            provider_user_id=provider_user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            profile_data=user_info,
        )

        return {
            "status": "new_user",
            "agent_id": str(agent.id),
            "api_key": api_key,
            "provider": request.provider.value,
            "email": user_info.get("email"),
            "name": name,
        }


@router.post("/connect")
async def connect_oauth(
    request: OAuthCallbackRequest,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """
    Connect OAuth provider to existing agent.

    Use this to add Google/GitHub login to an existing account.
    """
    oauth_service = OAuthService(session)

    # Exchange code for tokens
    try:
        tokens = await oauth_service.exchange_code(
            provider=request.provider,
            code=request.code,
            redirect_uri=request.redirect_uri,
            client_id=request.client_id,
            client_secret=request.client_secret,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in")

    token_expires_at = None
    if expires_in:
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Get user info
    user_info = await oauth_service.get_user_info(request.provider, access_token)
    provider_user_id = str(user_info.get("id") or user_info.get("sub"))

    # Check if this OAuth is already connected to another agent
    existing = await oauth_service.find_agent_by_oauth(request.provider, provider_user_id)
    if existing and existing != agent.id:
        raise HTTPException(
            status_code=400,
            detail="This OAuth account is already connected to another agent",
        )

    # Create connection
    connection = await oauth_service.find_or_create_connection(
        agent_id=agent.id,
        provider=request.provider,
        provider_user_id=provider_user_id,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
        profile_data=user_info,
    )

    return {
        "status": "connected",
        "provider": request.provider.value,
        "email": user_info.get("email"),
    }


@router.get("/connections", response_model=list[OAuthConnectionResponse])
async def list_connections(
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """List all OAuth connections for your agent."""
    service = OAuthService(session)
    connections = await service.list_connections(agent.id)
    return [
        OAuthConnectionResponse(
            id=c.id,
            provider=c.provider,
            provider_email=c.provider_email,
            provider_username=c.provider_username,
            connected_at=c.created_at.isoformat(),
        )
        for c in connections
    ]


@router.delete("/connections/{provider}")
async def disconnect_oauth(
    provider: OAuthProvider,
    agent: Agent = Depends(get_current_agent),
    session: AsyncSession = Depends(get_db),
):
    """Disconnect an OAuth provider."""
    service = OAuthService(session)
    if not await service.disconnect(agent.id, provider):
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"status": "disconnected", "provider": provider.value}
