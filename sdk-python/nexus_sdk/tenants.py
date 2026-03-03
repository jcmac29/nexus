"""Multi-tenant operations for Nexus SDK."""

from __future__ import annotations

from typing import Any

import httpx


class Tenants:
    """Synchronous tenant management operations."""

    def __init__(self, client: httpx.Client):
        self._client = client

    def get_settings(self) -> dict[str, Any] | None:
        """
        Get tenant settings.

        Returns:
            Tenant settings or None if not configured
        """
        response = self._client.get("/tenants/settings")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def create_settings(
        self,
        subdomain: str | None = None,
        custom_domain: str | None = None,
        display_name: str | None = None,
        logo_url: str | None = None,
        primary_color: str | None = None,
        features: dict[str, bool] | None = None,
        allowed_ip_ranges: list[str] | None = None,
        rate_limit_multiplier: float = 1.0,
        allowed_oauth_providers: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create tenant settings.

        Args:
            subdomain: Subdomain (e.g., "acme" for acme.nexus-cloud.com)
            custom_domain: Custom domain (e.g., "api.acme.com")
            display_name: Display name for branding
            logo_url: URL to logo image
            primary_color: Hex color code (e.g., "#FF5733")
            features: Feature flags (e.g., {"graph_memory": True})
            allowed_ip_ranges: IP allowlist in CIDR notation
            rate_limit_multiplier: Rate limit multiplier (1.0 = standard)
            allowed_oauth_providers: Allowed OAuth providers

        Returns:
            Created tenant settings
        """
        data: dict[str, Any] = {
            "rate_limit_multiplier": rate_limit_multiplier,
        }
        if subdomain is not None:
            data["subdomain"] = subdomain
        if custom_domain is not None:
            data["custom_domain"] = custom_domain
        if display_name is not None:
            data["display_name"] = display_name
        if logo_url is not None:
            data["logo_url"] = logo_url
        if primary_color is not None:
            data["primary_color"] = primary_color
        if features is not None:
            data["features"] = features
        if allowed_ip_ranges is not None:
            data["allowed_ip_ranges"] = allowed_ip_ranges
        if allowed_oauth_providers is not None:
            data["allowed_oauth_providers"] = allowed_oauth_providers

        response = self._client.post("/tenants/settings", json=data)
        response.raise_for_status()
        return response.json()

    def update_settings(
        self,
        subdomain: str | None = None,
        custom_domain: str | None = None,
        display_name: str | None = None,
        logo_url: str | None = None,
        primary_color: str | None = None,
        features: dict[str, bool] | None = None,
        allowed_ip_ranges: list[str] | None = None,
        rate_limit_multiplier: float | None = None,
        allowed_oauth_providers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update tenant settings."""
        data: dict[str, Any] = {}
        if subdomain is not None:
            data["subdomain"] = subdomain
        if custom_domain is not None:
            data["custom_domain"] = custom_domain
        if display_name is not None:
            data["display_name"] = display_name
        if logo_url is not None:
            data["logo_url"] = logo_url
        if primary_color is not None:
            data["primary_color"] = primary_color
        if features is not None:
            data["features"] = features
        if allowed_ip_ranges is not None:
            data["allowed_ip_ranges"] = allowed_ip_ranges
        if rate_limit_multiplier is not None:
            data["rate_limit_multiplier"] = rate_limit_multiplier
        if allowed_oauth_providers is not None:
            data["allowed_oauth_providers"] = allowed_oauth_providers

        response = self._client.patch("/tenants/settings", json=data)
        response.raise_for_status()
        return response.json()

    def get_limits(self) -> dict[str, Any]:
        """
        Get resource limits for the tenant.

        Returns:
            Current limits and usage
        """
        response = self._client.get("/tenants/limits")
        response.raise_for_status()
        return response.json()

    def invite(self, email: str, role: str = "member") -> dict[str, Any]:
        """
        Create a tenant invite.

        Args:
            email: Email address to invite
            role: Role to assign (admin, member, viewer)

        Returns:
            Invite with token
        """
        response = self._client.post(
            "/tenants/invites",
            json={"email": email, "role": role},
        )
        response.raise_for_status()
        return response.json()

    def list_invites(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """List pending invites."""
        response = self._client.get(
            "/tenants/invites",
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return response.json()["invites"]

    def revoke_invite(self, invite_id: str) -> bool:
        """Revoke an invite. Returns True if revoked."""
        response = self._client.delete(f"/tenants/invites/{invite_id}")
        return response.status_code in [200, 204]


class TenantsAsync:
    """Asynchronous tenant management operations."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def get_settings(self) -> dict[str, Any] | None:
        """Get tenant settings."""
        response = await self._client.get("/tenants/settings")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    async def create_settings(
        self,
        subdomain: str | None = None,
        custom_domain: str | None = None,
        display_name: str | None = None,
        logo_url: str | None = None,
        primary_color: str | None = None,
        features: dict[str, bool] | None = None,
        allowed_ip_ranges: list[str] | None = None,
        rate_limit_multiplier: float = 1.0,
        allowed_oauth_providers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create tenant settings."""
        data: dict[str, Any] = {
            "rate_limit_multiplier": rate_limit_multiplier,
        }
        if subdomain is not None:
            data["subdomain"] = subdomain
        if custom_domain is not None:
            data["custom_domain"] = custom_domain
        if display_name is not None:
            data["display_name"] = display_name
        if logo_url is not None:
            data["logo_url"] = logo_url
        if primary_color is not None:
            data["primary_color"] = primary_color
        if features is not None:
            data["features"] = features
        if allowed_ip_ranges is not None:
            data["allowed_ip_ranges"] = allowed_ip_ranges
        if allowed_oauth_providers is not None:
            data["allowed_oauth_providers"] = allowed_oauth_providers

        response = await self._client.post("/tenants/settings", json=data)
        response.raise_for_status()
        return response.json()

    async def update_settings(
        self,
        subdomain: str | None = None,
        custom_domain: str | None = None,
        display_name: str | None = None,
        logo_url: str | None = None,
        primary_color: str | None = None,
        features: dict[str, bool] | None = None,
        allowed_ip_ranges: list[str] | None = None,
        rate_limit_multiplier: float | None = None,
        allowed_oauth_providers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update tenant settings."""
        data: dict[str, Any] = {}
        if subdomain is not None:
            data["subdomain"] = subdomain
        if custom_domain is not None:
            data["custom_domain"] = custom_domain
        if display_name is not None:
            data["display_name"] = display_name
        if logo_url is not None:
            data["logo_url"] = logo_url
        if primary_color is not None:
            data["primary_color"] = primary_color
        if features is not None:
            data["features"] = features
        if allowed_ip_ranges is not None:
            data["allowed_ip_ranges"] = allowed_ip_ranges
        if rate_limit_multiplier is not None:
            data["rate_limit_multiplier"] = rate_limit_multiplier
        if allowed_oauth_providers is not None:
            data["allowed_oauth_providers"] = allowed_oauth_providers

        response = await self._client.patch("/tenants/settings", json=data)
        response.raise_for_status()
        return response.json()

    async def get_limits(self) -> dict[str, Any]:
        """Get resource limits for the tenant."""
        response = await self._client.get("/tenants/limits")
        response.raise_for_status()
        return response.json()

    async def invite(self, email: str, role: str = "member") -> dict[str, Any]:
        """Create a tenant invite."""
        response = await self._client.post(
            "/tenants/invites",
            json={"email": email, "role": role},
        )
        response.raise_for_status()
        return response.json()

    async def list_invites(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """List pending invites."""
        response = await self._client.get(
            "/tenants/invites",
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return response.json()["invites"]

    async def revoke_invite(self, invite_id: str) -> bool:
        """Revoke an invite."""
        response = await self._client.delete(f"/tenants/invites/{invite_id}")
        return response.status_code in [200, 204]
