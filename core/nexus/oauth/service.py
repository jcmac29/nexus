"""OAuth service - Handle OAuth flows."""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.config import get_settings
from nexus.oauth.models import OAuthConnection, OAuthProvider

settings = get_settings()


# OAuth provider configurations
OAUTH_CONFIGS = {
    OAuthProvider.GOOGLE: {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scopes": ["openid", "email", "profile"],
    },
    OAuthProvider.GITHUB: {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scopes": ["read:user", "user:email"],
    },
    OAuthProvider.MICROSOFT: {
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        "scopes": ["openid", "email", "profile"],
    },
    OAuthProvider.DISCORD: {
        "auth_url": "https://discord.com/api/oauth2/authorize",
        "token_url": "https://discord.com/api/oauth2/token",
        "userinfo_url": "https://discord.com/api/users/@me",
        "scopes": ["identify", "email"],
    },
}


class OAuthService:
    """Service for OAuth authentication."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self._state_store: dict[str, dict] = {}  # In production, use Redis

    def get_authorization_url(
        self,
        provider: OAuthProvider,
        redirect_uri: str,
        client_id: str,
    ) -> tuple[str, str]:
        """Generate OAuth authorization URL."""
        config = OAUTH_CONFIGS[provider]
        state = secrets.token_urlsafe(32)

        # Store state for verification
        self._state_store[state] = {
            "provider": provider,
            "redirect_uri": redirect_uri,
            "created_at": datetime.now(timezone.utc),
        }

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(config["scopes"]),
            "state": state,
        }

        if provider == OAuthProvider.GOOGLE:
            params["access_type"] = "offline"
            params["prompt"] = "consent"

        query = "&".join(f"{k}={v}" for k, v in params.items())
        auth_url = f"{config['auth_url']}?{query}"

        return auth_url, state

    async def exchange_code(
        self,
        provider: OAuthProvider,
        code: str,
        redirect_uri: str,
        client_id: str,
        client_secret: str,
    ) -> dict:
        """Exchange authorization code for tokens."""
        config = OAUTH_CONFIGS[provider]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

    async def get_user_info(
        self,
        provider: OAuthProvider,
        access_token: str,
    ) -> dict:
        """Get user info from OAuth provider."""
        config = OAUTH_CONFIGS[provider]

        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token}"}

            # GitHub uses different header format
            if provider == OAuthProvider.GITHUB:
                headers["Authorization"] = f"token {access_token}"

            response = await client.get(
                config["userinfo_url"],
                headers=headers,
            )
            response.raise_for_status()
            user_info = response.json()

            # Normalize user info
            if provider == OAuthProvider.GITHUB:
                # GitHub doesn't return email in userinfo, need separate call
                email_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers=headers,
                )
                if email_response.status_code == 200:
                    emails = email_response.json()
                    primary = next((e for e in emails if e.get("primary")), None)
                    if primary:
                        user_info["email"] = primary["email"]

            return user_info

    async def find_or_create_connection(
        self,
        agent_id: UUID,
        provider: OAuthProvider,
        provider_user_id: str,
        access_token: str,
        refresh_token: str | None,
        token_expires_at: datetime | None,
        profile_data: dict,
    ) -> OAuthConnection:
        """Find existing connection or create new one."""
        result = await self.session.execute(
            select(OAuthConnection).where(
                and_(
                    OAuthConnection.agent_id == agent_id,
                    OAuthConnection.provider == provider,
                )
            )
        )
        connection = result.scalar_one_or_none()

        if connection:
            # Update existing connection
            connection.provider_user_id = provider_user_id
            connection.access_token = access_token
            connection.refresh_token = refresh_token
            connection.token_expires_at = token_expires_at
            connection.profile_data = profile_data
            connection.provider_email = profile_data.get("email")
            connection.provider_username = profile_data.get("login") or profile_data.get("name")
        else:
            # Create new connection
            connection = OAuthConnection(
                agent_id=agent_id,
                provider=provider,
                provider_user_id=provider_user_id,
                provider_email=profile_data.get("email"),
                provider_username=profile_data.get("login") or profile_data.get("name"),
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
                profile_data=profile_data,
            )
            self.session.add(connection)

        await self.session.commit()
        await self.session.refresh(connection)
        return connection

    async def find_agent_by_oauth(
        self,
        provider: OAuthProvider,
        provider_user_id: str,
    ) -> UUID | None:
        """Find agent ID by OAuth identity."""
        result = await self.session.execute(
            select(OAuthConnection).where(
                and_(
                    OAuthConnection.provider == provider,
                    OAuthConnection.provider_user_id == provider_user_id,
                )
            )
        )
        connection = result.scalar_one_or_none()
        return connection.agent_id if connection else None

    async def list_connections(self, agent_id: UUID) -> list[OAuthConnection]:
        """List all OAuth connections for an agent."""
        result = await self.session.execute(
            select(OAuthConnection).where(OAuthConnection.agent_id == agent_id)
        )
        return list(result.scalars().all())

    async def disconnect(self, agent_id: UUID, provider: OAuthProvider) -> bool:
        """Remove an OAuth connection."""
        result = await self.session.execute(
            select(OAuthConnection).where(
                and_(
                    OAuthConnection.agent_id == agent_id,
                    OAuthConnection.provider == provider,
                )
            )
        )
        connection = result.scalar_one_or_none()
        if connection:
            await self.session.delete(connection)
            await self.session.commit()
            return True
        return False

    async def refresh_token(
        self,
        connection: OAuthConnection,
        client_id: str,
        client_secret: str,
    ) -> OAuthConnection:
        """Refresh an expired access token."""
        if not connection.refresh_token:
            raise ValueError("No refresh token available")

        config = OAUTH_CONFIGS[connection.provider]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                config["token_url"],
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": connection.refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            tokens = response.json()

        connection.access_token = tokens["access_token"]
        if "refresh_token" in tokens:
            connection.refresh_token = tokens["refresh_token"]
        if "expires_in" in tokens:
            connection.token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=tokens["expires_in"]
            )

        await self.session.commit()
        await self.session.refresh(connection)
        return connection
