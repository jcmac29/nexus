"""Tenant middleware for multi-tenant request handling."""

from typing import Callable
from uuid import UUID

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from nexus.config import get_settings


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
        self._tenant_cache: dict[str, dict] = {}

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

    async def _get_tenant_by_id(self, tenant_id: str) -> dict | None:
        """Look up tenant by account ID."""
        # Check cache first
        cache_key = f"id:{tenant_id}"
        if cache_key in self._tenant_cache:
            return self._tenant_cache[cache_key]

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
                    self._tenant_cache[cache_key] = tenant_info
                    return tenant_info
            except (ValueError, Exception):
                pass

        return None

    async def _get_tenant_by_subdomain(self, subdomain: str) -> dict | None:
        """Look up tenant by subdomain."""
        cache_key = f"subdomain:{subdomain}"
        if cache_key in self._tenant_cache:
            return self._tenant_cache[cache_key]

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
                self._tenant_cache[cache_key] = tenant_info
                return tenant_info

        return None

    async def _get_tenant_by_custom_domain(self, domain: str) -> dict | None:
        """Look up tenant by custom domain."""
        cache_key = f"domain:{domain}"
        if cache_key in self._tenant_cache:
            return self._tenant_cache[cache_key]

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
                self._tenant_cache[cache_key] = tenant_info
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
