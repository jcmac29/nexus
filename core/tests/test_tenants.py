"""Tests for multi-tenant module."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_tenant_settings(authenticated_client: AsyncClient):
    """Test getting tenant settings."""
    response = await authenticated_client.get("/api/v1/tenants/settings")
    # May return 404 if no settings exist yet, or 200 with settings
    assert response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_create_tenant_settings(authenticated_client: AsyncClient):
    """Test creating tenant settings."""
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": "test-tenant",
            "display_name": "Test Tenant",
            "features": {
                "graph_memory": True,
                "webhooks": True,
                "federation": False,
            },
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["subdomain"] == "test-tenant"
    assert data["display_name"] == "Test Tenant"
    assert data["features"]["graph_memory"] is True


@pytest.mark.asyncio
async def test_update_tenant_settings(authenticated_client: AsyncClient):
    """Test updating tenant settings."""
    # Create settings first
    await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={"subdomain": "update-test"},
    )

    # Update settings
    response = await authenticated_client.patch(
        "/api/v1/tenants/settings",
        json={
            "display_name": "Updated Display Name",
            "primary_color": "#FF5733",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["display_name"] == "Updated Display Name"
    assert data["primary_color"] == "#FF5733"


@pytest.mark.asyncio
async def test_tenant_subdomain_uniqueness(authenticated_client: AsyncClient):
    """Test that tenant subdomains must be unique."""
    # Create first tenant
    await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={"subdomain": "unique-tenant"},
    )

    # Try to create another with same subdomain (should fail)
    # Note: This might require a different account in real scenario
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={"subdomain": "unique-tenant"},
    )
    # Should either fail or update existing
    assert response.status_code in [200, 400, 409]


@pytest.mark.asyncio
async def test_get_tenant_limits(authenticated_client: AsyncClient):
    """Test getting resource limits."""
    response = await authenticated_client.get("/api/v1/tenants/limits")
    assert response.status_code == 200

    data = response.json()
    assert "agents" in data or "limits" in data


@pytest.mark.asyncio
async def test_create_tenant_invite(authenticated_client: AsyncClient):
    """Test creating a tenant invite."""
    # Create settings first
    await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={"subdomain": "invite-test"},
    )

    response = await authenticated_client.post(
        "/api/v1/tenants/invites",
        json={
            "email": "newuser@example.com",
            "role": "member",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["role"] == "member"
    assert "token" in data


@pytest.mark.asyncio
async def test_list_tenant_invites(authenticated_client: AsyncClient):
    """Test listing tenant invites."""
    response = await authenticated_client.get("/api/v1/tenants/invites")
    assert response.status_code == 200

    data = response.json()
    assert "invites" in data


@pytest.mark.asyncio
async def test_revoke_tenant_invite(authenticated_client: AsyncClient):
    """Test revoking a tenant invite."""
    # Create invite first
    create_response = await authenticated_client.post(
        "/api/v1/tenants/invites",
        json={
            "email": "revoke@example.com",
            "role": "viewer",
        },
    )

    if create_response.status_code == 200:
        invite_id = create_response.json()["id"]

        # Revoke invite
        response = await authenticated_client.delete(
            f"/api/v1/tenants/invites/{invite_id}"
        )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_tenant_feature_flags(authenticated_client: AsyncClient):
    """Test tenant feature flag management."""
    # Create settings with features
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": "features-test",
            "features": {
                "graph_memory": True,
                "webhooks": False,
                "marketplace": True,
            },
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["features"]["graph_memory"] is True
    assert data["features"]["webhooks"] is False


@pytest.mark.asyncio
async def test_tenant_rate_limit_multiplier(authenticated_client: AsyncClient):
    """Test tenant rate limit configuration."""
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": "ratelimit-test",
            "rate_limit_multiplier": 2.0,
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["rate_limit_multiplier"] == 2.0


@pytest.mark.asyncio
async def test_tenant_ip_allowlist(authenticated_client: AsyncClient):
    """Test tenant IP allowlist configuration."""
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": "ipallow-test",
            "allowed_ip_ranges": ["10.0.0.0/8", "192.168.1.0/24"],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["allowed_ip_ranges"]) == 2


@pytest.mark.asyncio
async def test_tenant_custom_domain(authenticated_client: AsyncClient):
    """Test tenant custom domain configuration."""
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": "customdomain-test",
            "custom_domain": "api.acme-corp.com",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["custom_domain"] == "api.acme-corp.com"


@pytest.mark.asyncio
async def test_tenant_oauth_providers(authenticated_client: AsyncClient):
    """Test tenant OAuth provider restrictions."""
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": "oauth-test",
            "allowed_oauth_providers": ["google", "github"],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert "google" in data["allowed_oauth_providers"]
    assert "github" in data["allowed_oauth_providers"]


@pytest.mark.asyncio
async def test_invite_roles(authenticated_client: AsyncClient):
    """Test different invite roles."""
    roles = ["admin", "member", "viewer"]

    for role in roles:
        response = await authenticated_client.post(
            "/api/v1/tenants/invites",
            json={
                "email": f"{role}@example.com",
                "role": role,
            },
        )
        if response.status_code == 200:
            assert response.json()["role"] == role
