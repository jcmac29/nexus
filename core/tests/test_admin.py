"""Tests for admin authentication and dashboard."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_login_invalid_credentials(client: AsyncClient):
    """Test login with invalid credentials."""
    response = await client.post(
        "/api/v1/admin/auth/login",
        json={"email": "invalid@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_stats_requires_auth(client: AsyncClient):
    """Test that stats endpoint requires authentication."""
    response = await client.get("/api/v1/admin/stats")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_agents_requires_auth(client: AsyncClient):
    """Test that agents endpoint requires authentication."""
    response = await client.get("/api/v1/admin/agents")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_teams_requires_auth(client: AsyncClient):
    """Test that teams endpoint requires authentication."""
    response = await client.get("/api/v1/admin/teams")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_activity_requires_auth(client: AsyncClient):
    """Test that activity endpoint requires authentication."""
    response = await client.get("/api/v1/admin/activity")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_settings_requires_auth(client: AsyncClient):
    """Test that settings endpoint requires authentication."""
    response = await client.get("/api/v1/admin/settings")
    assert response.status_code == 401
