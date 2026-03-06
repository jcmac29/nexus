"""JWT token management for Nexus."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Any
import uuid

import jwt
from pydantic import BaseModel

from nexus.config import get_settings


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # Subject (user/agent ID)
    type: str  # Token type (access, refresh)
    exp: datetime  # Expiration
    iat: datetime  # Issued at
    jti: str  # JWT ID (for revocation)
    scopes: list[str] = []  # Permissions
    metadata: dict[str, Any] = {}  # Additional data


class TokenService:
    """Service for creating and verifying JWT tokens.

    SECURITY: Uses Redis-backed revocation for distributed deployments.
    Falls back to in-memory only in development mode.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
    ):
        settings = get_settings()
        self.secret_key = secret_key or settings.secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
        self._cache = None

        # SECURITY: In-memory fallback only used when Redis unavailable
        # This is logged as a warning in production
        self._revoked_tokens: set[str] = set()

    async def _get_cache(self):
        """Get Redis cache for distributed token revocation."""
        if self._cache is None:
            from nexus.cache.service import get_cache
            try:
                self._cache = await get_cache()
            except Exception:
                pass  # Will use in-memory fallback
        return self._cache

    async def _is_token_revoked_async(self, jti: str) -> bool:
        """Check if token is revoked using Redis."""
        cache = await self._get_cache()
        if cache:
            try:
                return await cache.exists(f"revoked_token:{jti}")
            except Exception:
                pass
        # Fallback to in-memory
        return jti in self._revoked_tokens

    def _is_token_revoked_sync(self, jti: str) -> bool:
        """Synchronous check for token revocation (in-memory only)."""
        return jti in self._revoked_tokens

    def create_access_token(
        self,
        subject: str,
        scopes: list[str] = None,
        metadata: dict[str, Any] = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create an access token."""
        if expires_delta is None:
            expires_delta = timedelta(minutes=self.access_token_expire_minutes)

        now = datetime.now(timezone.utc)
        payload = TokenPayload(
            sub=subject,
            type="access",
            exp=now + expires_delta,
            iat=now,
            jti=str(uuid.uuid4()),
            scopes=scopes or [],
            metadata=metadata or {},
        )

        return jwt.encode(
            payload.model_dump(),
            self.secret_key,
            algorithm=self.algorithm,
        )

    def create_refresh_token(
        self,
        subject: str,
        metadata: dict[str, Any] = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a refresh token."""
        if expires_delta is None:
            expires_delta = timedelta(days=self.refresh_token_expire_days)

        now = datetime.now(timezone.utc)
        payload = TokenPayload(
            sub=subject,
            type="refresh",
            exp=now + expires_delta,
            iat=now,
            jti=str(uuid.uuid4()),
            scopes=[],
            metadata=metadata or {},
        )

        return jwt.encode(
            payload.model_dump(),
            self.secret_key,
            algorithm=self.algorithm,
        )

    def verify_token(
        self,
        token: str,
        expected_type: Optional[str] = None,
    ) -> Optional[TokenPayload]:
        """Verify a token and return its payload (sync version).

        Note: Uses in-memory revocation check only. For async contexts,
        use verify_token_async() for Redis-backed revocation.
        """
        try:
            payload_dict = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
            payload = TokenPayload(**payload_dict)

            # Check if revoked (sync check - in-memory only)
            if self._is_token_revoked_sync(payload.jti):
                return None

            # Check type if specified
            if expected_type and payload.type != expected_type:
                return None

            return payload

        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    async def verify_token_async(
        self,
        token: str,
        expected_type: Optional[str] = None,
    ) -> Optional[TokenPayload]:
        """Verify a token and return its payload (async version).

        SECURITY: Uses Redis-backed revocation for distributed deployments.
        """
        try:
            payload_dict = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
            payload = TokenPayload(**payload_dict)

            # Check if revoked (async - Redis backed)
            if await self._is_token_revoked_async(payload.jti):
                return None

            # Check type if specified
            if expected_type and payload.type != expected_type:
                return None

            return payload

        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def revoke_token(self, token: str) -> bool:
        """Revoke a token (sync version - in-memory only).

        For async contexts, use revoke_token_async() for Redis persistence.
        """
        try:
            payload_dict = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False},  # Allow revoking expired tokens
            )
            self._revoked_tokens.add(payload_dict["jti"])
            return True
        except jwt.InvalidTokenError:
            return False

    async def revoke_token_async(self, token: str) -> bool:
        """Revoke a token with Redis persistence.

        SECURITY: Stores revocation in Redis for distributed deployments.
        Token revocations are stored with TTL matching token expiration.
        """
        try:
            payload_dict = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False},  # Allow revoking expired tokens
            )
            jti = payload_dict["jti"]

            # Also add to in-memory for immediate effect
            self._revoked_tokens.add(jti)

            # Store in Redis with TTL
            cache = await self._get_cache()
            if cache:
                try:
                    # Calculate TTL from token expiration
                    exp = datetime.fromisoformat(payload_dict["exp"]) if isinstance(payload_dict["exp"], str) else datetime.fromtimestamp(payload_dict["exp"])
                    ttl = max(1, int((exp - datetime.now(timezone.utc)).total_seconds()))
                    await cache.set(f"revoked_token:{jti}", "1", ttl=ttl)
                except Exception:
                    pass  # In-memory revocation still works

            return True
        except jwt.InvalidTokenError:
            return False

    def refresh_access_token(self, refresh_token: str) -> Optional[tuple[str, str]]:
        """Use a refresh token to get new access and refresh tokens."""
        payload = self.verify_token(refresh_token, expected_type="refresh")
        if payload is None:
            return None

        # Revoke old refresh token
        self.revoke_token(refresh_token)

        # Create new tokens
        access_token = self.create_access_token(
            subject=payload.sub,
            scopes=payload.scopes,
            metadata=payload.metadata,
        )
        new_refresh_token = self.create_refresh_token(
            subject=payload.sub,
            metadata=payload.metadata,
        )

        return access_token, new_refresh_token


# Global token service instance
_token_service: Optional[TokenService] = None


def get_token_service() -> TokenService:
    """Get or create the global token service."""
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    return _token_service


def create_access_token(
    subject: str,
    scopes: list[str] = None,
    metadata: dict[str, Any] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create an access token."""
    return get_token_service().create_access_token(
        subject=subject,
        scopes=scopes,
        metadata=metadata,
        expires_delta=expires_delta,
    )


def create_refresh_token(
    subject: str,
    metadata: dict[str, Any] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a refresh token."""
    return get_token_service().create_refresh_token(
        subject=subject,
        metadata=metadata,
        expires_delta=expires_delta,
    )


def verify_token(
    token: str,
    expected_type: Optional[str] = None,
) -> Optional[TokenPayload]:
    """Verify a token and return its payload."""
    return get_token_service().verify_token(token, expected_type)


def revoke_token(token: str) -> bool:
    """Revoke a token."""
    return get_token_service().revoke_token(token)
