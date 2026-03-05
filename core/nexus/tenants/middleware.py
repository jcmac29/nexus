"""Tenant middleware for multi-tenant request handling."""

from datetime import datetime, timezone
from typing import Callable
from uuid import UUID

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from nexus.config import get_settings

# Cache TTL in seconds (5 minutes)
TENANT_CACHE_TTL = 300
# Maximum cache size to prevent memory exhaustion
TENANT_CACHE_MAX_SIZE = 10000


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and validate tenant context from requests.

    Supports:
    - Subdomain-based routing (acme.nexus-cloud.com)
    - Custom domain routing (api.acme.com)
    - Header-based tenant selection (X-Tenant-ID)
    """

    def __init__(self, app: ASGIApp, enabled: bool = True, base_domain: str = "nexus-cloud.com"):
        super().__init__(app)
        self.enabled = enabled
        self.base_domain = base_domain
        # Cache stores (data, timestamp) tuples
        self._tenant_cache: dict[str, tuple[dict, datetime]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enabled:
            return await call_next(request)

        # Try to extract tenant from various sources
        tenant_info = await self._extract_tenant(request)

        if tenant_info:
            # Store tenant info in request state
            request.state.tenant_id = tenant_info.get("account_id")
            request.state.tenant_settings = tenant_info.get("settings", {})

            # Set PostgreSQL session variable for RLS
            # This would be done in the database session
            # await self._set_rls_context(request.state.tenant_id)

        return await call_next(request)

    async def _extract_tenant(self, request: Request) -> dict | None:
        """Extract tenant information from the request."""
        # Priority 1: X-Tenant-ID header (for API testing/internal use)
        tenant_header = request.headers.get("X-Tenant-ID")
        if tenant_header:
            return await self._get_tenant_by_id(tenant_header)

        # Priority 2: Subdomain
        host = request.headers.get("host", "")
        subdomain = self._extract_subdomain(host)
        if subdomain:
            return await self._get_tenant_by_subdomain(subdomain)

        # Priority 3: Custom domain
        if host and not host.endswith(self.base_domain):
            return await self._get_tenant_by_custom_domain(host)

        return None

    def _extract_subdomain(self, host: str) -> str | None:
        """Extract subdomain from host header."""
        if not host:
            return None

        # Remove port if present
        host = host.split(":")[0]

        # Check if it's a subdomain of our base domain
        if host.endswith(f".{self.base_domain}"):
            subdomain = host.replace(f".{self.base_domain}", "")
            # Ignore common subdomains
            if subdomain not in ("www", "api", "app", "admin"):
                return subdomain

        return None

    def _get_from_cache(self, cache_key: str) -> dict | None:
        """Get item from cache if not expired."""
        if cache_key not in self._tenant_cache:
            return None

        data, timestamp = self._tenant_cache[cache_key]
        if (datetime.now(timezone.utc) - timestamp).total_seconds() > TENANT_CACHE_TTL:
            # Entry expired, remove it
            del self._tenant_cache[cache_key]
            return None

        return data

    def _set_cache(self, cache_key: str, data: dict) -> None:
        """Set item in cache with timestamp."""
        # SECURITY: Prevent unbounded cache growth
        if len(self._tenant_cache) >= TENANT_CACHE_MAX_SIZE:
            # Remove oldest entries (simple eviction)
            self._cleanup_expired_entries()
            # If still too large, clear oldest 10%
            if len(self._tenant_cache) >= TENANT_CACHE_MAX_SIZE:
                sorted_keys = sorted(
                    self._tenant_cache.keys(),
                    key=lambda k: self._tenant_cache[k][1]
                )
                for key in sorted_keys[:len(sorted_keys) // 10]:
                    del self._tenant_cache[key]

        self._tenant_cache[cache_key] = (data, datetime.now(timezone.utc))

    def _cleanup_expired_entries(self) -> int:
        """Remove expired cache entries. Returns count of removed entries."""
        now = datetime.now(timezone.utc)
        expired = [
            key for key, (_, timestamp) in self._tenant_cache.items()
            if (now - timestamp).total_seconds() > TENANT_CACHE_TTL
        ]
        for key in expired:
            del self._tenant_cache[key]
        return len(expired)

    async def _get_tenant_by_id(self, tenant_id: str) -> dict | None:
        """Look up tenant by account ID."""
        # Check cache first
        cache_key = f"id:{tenant_id}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        # Query database
        from nexus.database import async_session_maker
        from nexus.tenants.models import TenantSettings
        from nexus.billing.models import Account
        from sqlalchemy import select

        async with async_session_maker() as db:
            try:
                account_uuid = UUID(tenant_id)
                stmt = select(TenantSettings).where(
                    TenantSettings.account_id == account_uuid,
                    TenantSettings.is_active == True,
                )
                result = await db.execute(stmt)
                settings = result.scalar_one_or_none()

                if settings:
                    tenant_info = {
                        "account_id": settings.account_id,
                        "settings": self._settings_to_dict(settings),
                    }
                    self._set_cache(cache_key, tenant_info)
                    return tenant_info
            except (ValueError, Exception):
                pass

        return None

    async def _get_tenant_by_subdomain(self, subdomain: str) -> dict | None:
        """Look up tenant by subdomain."""
        cache_key = f"subdomain:{subdomain}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        from nexus.database import async_session_maker
        from nexus.tenants.models import TenantSettings
        from sqlalchemy import select

        async with async_session_maker() as db:
            stmt = select(TenantSettings).where(
                TenantSettings.subdomain == subdomain,
                TenantSettings.is_active == True,
            )
            result = await db.execute(stmt)
            settings = result.scalar_one_or_none()

            if settings:
                tenant_info = {
                    "account_id": settings.account_id,
                    "settings": self._settings_to_dict(settings),
                }
                self._set_cache(cache_key, tenant_info)
                return tenant_info

        return None

    async def _get_tenant_by_custom_domain(self, domain: str) -> dict | None:
        """Look up tenant by custom domain."""
        cache_key = f"domain:{domain}"
        cached = self._get_from_cache(cache_key)
        if cached:
            return cached

        from nexus.database import async_session_maker
        from nexus.tenants.models import TenantSettings
        from sqlalchemy import select

        async with async_session_maker() as db:
            stmt = select(TenantSettings).where(
                TenantSettings.custom_domain == domain,
                TenantSettings.is_active == True,
            )
            result = await db.execute(stmt)
            settings = result.scalar_one_or_none()

            if settings:
                tenant_info = {
                    "account_id": settings.account_id,
                    "settings": self._settings_to_dict(settings),
                }
                self._set_cache(cache_key, tenant_info)
                return tenant_info

        return None

    def _settings_to_dict(self, settings) -> dict:
        """Convert TenantSettings model to dict."""
        return {
            "subdomain": settings.subdomain,
            "custom_domain": settings.custom_domain,
            "features": settings.features,
            "allowed_ip_ranges": settings.allowed_ip_ranges,
            "require_2fa": settings.require_2fa,
            "rate_limit_multiplier": settings.rate_limit_multiplier,
            "custom_rate_limits": settings.custom_rate_limits,
            "data_region": settings.data_region,
        }

    def clear_cache(self):
        """Clear the tenant cache."""
        self._tenant_cache.clear()


def get_tenant_id(request: Request) -> UUID | None:
    """Get tenant ID from request state."""
    return getattr(request.state, "tenant_id", None)


def get_tenant_settings(request: Request) -> dict:
    """Get tenant settings from request state."""
    return getattr(request.state, "tenant_settings", {})


def is_feature_enabled(request: Request, feature: str) -> bool:
    """Check if a feature is enabled for the current tenant."""
    settings = get_tenant_settings(request)
    features = settings.get("features", {})
    return features.get(feature, True)  # Default to enabled
