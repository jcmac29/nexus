"""Tests for reputation module."""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_own_reputation(authenticated_client: AsyncClient):
    """Test getting own reputation score."""
    response = await authenticated_client.get("/api/v1/reputation/me")
    assert response.status_code == 200

    data = response.json()
    assert "overall_score" in data
    assert "tier" in data
    assert data["tier"] in ["bronze", "silver", "gold", "platinum"]


@pytest.mark.asyncio
async def test_get_agent_reputation(authenticated_client: AsyncClient, client: AsyncClient):
    """Test getting another agent's reputation."""
    # Register another agent
    unique_slug = f"reputation-target-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "reputation-target",
            "slug": unique_slug,
            "description": "Agent to check reputation",
        },
    )
    agent_data = register_response.json()
    agent_id = agent_data["agent"]["id"]

    # Initialize their reputation by calling their endpoint
    client.headers["Authorization"] = f"Bearer {agent_data['api_key']}"
    client.headers["X-Agent-ID"] = str(agent_id)
    await client.get("/api/v1/reputation/me")

    # Get their reputation from original client
    response = await authenticated_client.get(f"/api/v1/reputation/{agent_id}")
    assert response.status_code == 200

    data = response.json()
    assert "overall_score" in data


@pytest.mark.asyncio
async def test_vouch_for_agent(authenticated_client: AsyncClient, client: AsyncClient):
    """Test vouching for another agent."""
    # Register another agent
    unique_slug = f"vouch-target-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "vouch-target",
            "slug": unique_slug,
            "description": "Agent to vouch for",
        },
    )
    agent_id = register_response.json()["agent"]["id"]

    # Vouch for them
    response = await authenticated_client.post(
        f"/api/v1/reputation/{agent_id}/vouch",
        json={
            "category": "quality",
            "strength": 0.8,
            "message": "Great work on code reviews",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["category"] == "quality"
    assert data["strength"] == 0.8


@pytest.mark.asyncio
async def test_get_vouches_for_agent(authenticated_client: AsyncClient):
    """Test listing vouches for an agent."""
    # Get own agent ID
    me_response = await authenticated_client.get("/api/v1/agents/me")
    agent_id = me_response.json()["id"]

    response = await authenticated_client.get(f"/api/v1/reputation/{agent_id}/vouches")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_revoke_vouch(authenticated_client: AsyncClient, client: AsyncClient):
    """Test revoking a vouch."""
    # Register and vouch for an agent
    unique_slug = f"revoke-target-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "revoke-target",
            "slug": unique_slug,
            "description": "Agent to revoke vouch from",
        },
    )
    agent_id = register_response.json()["agent"]["id"]

    vouch_response = await authenticated_client.post(
        f"/api/v1/reputation/{agent_id}/vouch",
        json={"category": "reliability", "strength": 0.7},
    )
    vouch_id = vouch_response.json()["id"]

    # Revoke the vouch - uses DELETE
    response = await authenticated_client.delete(
        f"/api/v1/reputation/vouches/{vouch_id}",
        params={"reason": "Changed my mind"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_file_dispute(authenticated_client: AsyncClient, client: AsyncClient):
    """Test filing a dispute."""
    # Register another agent
    unique_slug = f"dispute-target-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "dispute-target",
            "slug": unique_slug,
            "description": "Agent to dispute",
        },
    )
    agent_id = register_response.json()["agent"]["id"]

    # File a dispute
    response = await authenticated_client.post(
        f"/api/v1/reputation/{agent_id}/dispute",
        json={
            "category": "quality",
            "title": "Incomplete work",
            "description": "Did not complete requirements",
            "severity": "medium",
            "evidence": {"task_id": "task-123"},
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "Incomplete work"
    assert data["status"] in ["open", "pending"]


@pytest.mark.asyncio
async def test_get_disputes(authenticated_client: AsyncClient):
    """Test listing disputes for an agent."""
    # Get own agent ID
    me_response = await authenticated_client.get("/api/v1/agents/me")
    agent_id = me_response.json()["id"]

    response = await authenticated_client.get(f"/api/v1/reputation/{agent_id}/disputes")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_reputation_history(authenticated_client: AsyncClient):
    """Test getting reputation history."""
    # Get own agent ID
    me_response = await authenticated_client.get("/api/v1/agents/me")
    agent_id = me_response.json()["id"]

    response = await authenticated_client.get(f"/api/v1/reputation/{agent_id}/history")
    assert response.status_code == 200

    data = response.json()
    assert "events" in data


@pytest.mark.asyncio
async def test_vouch_categories(authenticated_client: AsyncClient, client: AsyncClient):
    """Test different vouch categories."""
    unique_slug = f"category-target-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "category-target",
            "slug": unique_slug,
            "description": "Agent for category test",
        },
    )
    agent_id = register_response.json()["agent"]["id"]

    categories = ["quality", "reliability", "speed", "communication"]

    for i, category in enumerate(categories):
        # Register new agent for each category to avoid duplicate vouch
        if i > 0:
            unique_slug = f"category-target-{i}-{uuid.uuid4().hex[:8]}"
            register_response = await client.post(
                "/api/v1/agents",
                json={
                    "name": f"category-target-{i}",
                    "slug": unique_slug,
                    "description": f"Agent for category test {i}",
                },
            )
            agent_id = register_response.json()["agent"]["id"]

        response = await authenticated_client.post(
            f"/api/v1/reputation/{agent_id}/vouch",
            json={"category": category, "strength": 0.5},
        )
        assert response.status_code == 201


@pytest.mark.asyncio
async def test_cannot_vouch_for_self(authenticated_client: AsyncClient):
    """Test that agent cannot vouch for themselves."""
    # Get own agent ID
    me_response = await authenticated_client.get("/api/v1/agents/me")
    my_id = me_response.json()["id"]

    # Try to vouch for self
    response = await authenticated_client.post(
        f"/api/v1/reputation/{my_id}/vouch",
        json={"category": "quality", "strength": 1.0},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_record_interaction(authenticated_client: AsyncClient):
    """Test recording an interaction."""
    response = await authenticated_client.post(
        "/api/v1/reputation/interactions",
        params={"success": True},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "recorded"
