"""Tests for identity module."""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_register_agent(client: AsyncClient, db_session: AsyncSession):
    """Test agent registration."""
    unique_slug = f"new-test-agent-{uuid.uuid4().hex[:8]}"
    response = await client.post(
        "/api/v1/agents",
        json={
            "name": "new-test-agent",
            "slug": unique_slug,
            "description": "A test agent",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["agent"]["name"] == "new-test-agent"
    assert "api_key" in data


@pytest.mark.asyncio
async def test_get_current_agent(authenticated_client: AsyncClient):
    """Test getting current agent details."""
    response = await authenticated_client.get("/api/v1/agents/me")
    assert response.status_code == 200

    data = response.json()
    # The authenticated_client creates an agent named "test-agent"
    assert "id" in data
    assert "name" in data
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_update_current_agent(authenticated_client: AsyncClient):
    """Test updating current agent details."""
    response = await authenticated_client.patch(
        "/api/v1/agents/me",
        json={
            "description": "Updated description",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_create_api_key(authenticated_client: AsyncClient):
    """Test creating a new API key."""
    response = await authenticated_client.post(
        "/api/v1/agents/me/keys",
        json={
            "name": "test-key",
            "scopes": ["read", "write"],
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["key"]["name"] == "test-key"
    assert "api_key" in data


@pytest.mark.asyncio
async def test_list_api_keys(authenticated_client: AsyncClient):
    """Test listing API keys."""
    response = await authenticated_client.get("/api/v1/agents/me/keys")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    # Should have at least the default key
    assert len(data) >= 1
