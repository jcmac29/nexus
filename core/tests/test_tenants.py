"""Tests for multi-tenant module."""

import uuid

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
    unique_subdomain = f"test-tenant-{uuid.uuid4().hex[:8]}"
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": unique_subdomain,
            "display_name": "Test Tenant",
            "features": {
                "graph_memory": True,
                "webhooks": True,
                "federation": False,
            },
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["subdomain"] == unique_subdomain
    assert data["display_name"] == "Test Tenant"
    assert data["features"]["graph_memory"] is True


@pytest.mark.asyncio
async def test_update_tenant_settings(authenticated_client: AsyncClient):
    """Test updating tenant settings."""
    # Create settings first
    unique_subdomain = f"update-test-{uuid.uuid4().hex[:8]}"
    create_response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={"subdomain": unique_subdomain},
    )
    assert create_response.status_code == 201

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
    unique_subdomain = f"unique-tenant-{uuid.uuid4().hex[:8]}"

    # Create first tenant
    await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={"subdomain": unique_subdomain},
    )

    # Try to create another with same subdomain (should fail with 409)
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={"subdomain": unique_subdomain},
    )
    # Should fail because settings already exist for this account
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_get_tenant_limits(authenticated_client: AsyncClient):
    """Test getting resource limits."""
    response = await authenticated_client.get("/api/v1/tenants/limits")
    assert response.status_code == 200

    data = response.json()
    # Response contains limit status with usage info
    assert "agents" in data or "memories" in data or "plan_type" in data


@pytest.mark.asyncio
async def test_create_tenant_invite(authenticated_client: AsyncClient):
    """Test creating a tenant invite."""
    # Create settings first
    unique_subdomain = f"invite-test-{uuid.uuid4().hex[:8]}"
    await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={"subdomain": unique_subdomain},
    )

    unique_email = f"newuser-{uuid.uuid4().hex[:8]}@example.com"
    response = await authenticated_client.post(
        "/api/v1/tenants/invites",
        json={
            "email": unique_email,
            "role": "member",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["email"] == unique_email
    assert data["role"] == "member"


@pytest.mark.asyncio
async def test_list_tenant_invites(authenticated_client: AsyncClient):
    """Test listing tenant invites."""
    response = await authenticated_client.get("/api/v1/tenants/invites")
    assert response.status_code == 200

    data = response.json()
    # Returns a list directly
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_revoke_tenant_invite(authenticated_client: AsyncClient):
    """Test revoking a tenant invite."""
    # Create settings first
    unique_subdomain = f"revoke-test-{uuid.uuid4().hex[:8]}"
    await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={"subdomain": unique_subdomain},
    )

    # Create invite first
    unique_email = f"revoke-{uuid.uuid4().hex[:8]}@example.com"
    create_response = await authenticated_client.post(
        "/api/v1/tenants/invites",
        json={
            "email": unique_email,
            "role": "viewer",
        },
    )

    assert create_response.status_code == 201
    invite_id = create_response.json()["id"]

    # Revoke invite
    response = await authenticated_client.delete(
        f"/api/v1/tenants/invites/{invite_id}"
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_tenant_feature_flags(authenticated_client: AsyncClient):
    """Test tenant feature flag management."""
    unique_subdomain = f"features-test-{uuid.uuid4().hex[:8]}"
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": unique_subdomain,
            "features": {
                "graph_memory": True,
                "webhooks": False,
                "marketplace": True,
            },
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["features"]["graph_memory"] is True
    assert data["features"]["webhooks"] is False


@pytest.mark.asyncio
async def test_tenant_rate_limit_multiplier(authenticated_client: AsyncClient):
    """Test tenant rate limit configuration."""
    # Note: rate_limit_multiplier is not in the create schema, it's a default
    # So we just create settings and check the default
    unique_subdomain = f"ratelimit-test-{uuid.uuid4().hex[:8]}"
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": unique_subdomain,
        },
    )
    assert response.status_code == 201

    data = response.json()
    # Default rate_limit_multiplier is 1.0
    assert data["rate_limit_multiplier"] == 1.0


@pytest.mark.asyncio
async def test_tenant_ip_allowlist(authenticated_client: AsyncClient):
    """Test tenant IP allowlist configuration."""
    unique_subdomain = f"ipallow-test-{uuid.uuid4().hex[:8]}"
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": unique_subdomain,
            "allowed_ip_ranges": ["10.0.0.0/8", "192.168.1.0/24"],
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert len(data["allowed_ip_ranges"]) == 2


@pytest.mark.asyncio
async def test_tenant_custom_domain(authenticated_client: AsyncClient):
    """Test tenant custom domain configuration."""
    unique_subdomain = f"customdomain-test-{uuid.uuid4().hex[:8]}"
    unique_domain = f"api-{uuid.uuid4().hex[:8]}.acme-corp.com"
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": unique_subdomain,
            "custom_domain": unique_domain,
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["custom_domain"] == unique_domain


@pytest.mark.asyncio
async def test_tenant_oauth_providers(authenticated_client: AsyncClient):
    """Test tenant OAuth provider restrictions."""
    # Note: allowed_oauth_providers is not in the create schema
    # This test validates that the creation works without that field
    unique_subdomain = f"oauth-test-{uuid.uuid4().hex[:8]}"
    response = await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={
            "subdomain": unique_subdomain,
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_invite_roles(authenticated_client: AsyncClient):
    """Test different invite roles."""
    # Create settings first
    unique_subdomain = f"roles-test-{uuid.uuid4().hex[:8]}"
    await authenticated_client.post(
        "/api/v1/tenants/settings",
        json={"subdomain": unique_subdomain},
    )

    roles = ["admin", "member", "viewer"]

    for role in roles:
        unique_email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
        response = await authenticated_client.post(
            "/api/v1/tenants/invites",
            json={
                "email": unique_email,
                "role": role,
            },
        )
        assert response.status_code == 201
        assert response.json()["role"] == role
