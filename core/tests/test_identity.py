"""Tests for identity module."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_register_agent(client: AsyncClient):
    """Test agent registration."""
    response = await client.post(
        "/api/v1/agents/register",
        json={
            "name": "new-test-agent",
            "version": "1.0.0",
            "description": "A test agent",
            "capabilities": ["testing", "automation"],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "new-test-agent"
    assert "id" in data
    assert "api_key" in data


@pytest.mark.asyncio
async def test_get_agent(authenticated_client: AsyncClient, test_agent):
    """Test getting agent details."""
    response = await authenticated_client.get(f"/api/v1/agents/{test_agent.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(test_agent.id)
    assert data["name"] == test_agent.name


@pytest.mark.asyncio
async def test_update_agent(authenticated_client: AsyncClient, test_agent):
    """Test updating agent details."""
    response = await authenticated_client.patch(
        f"/api/v1/agents/{test_agent.id}",
        json={
            "description": "Updated description",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_agent_heartbeat(authenticated_client: AsyncClient, test_agent):
    """Test agent heartbeat."""
    response = await authenticated_client.post(
        f"/api/v1/agents/{test_agent.id}/heartbeat"
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_agents(authenticated_client: AsyncClient, test_agent):
    """Test listing agents."""
    response = await authenticated_client.get("/api/v1/agents")
    assert response.status_code == 200

    data = response.json()
    assert "agents" in data
    assert len(data["agents"]) > 0
