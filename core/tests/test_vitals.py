"""Tests for vitals module."""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_own_vitals(authenticated_client: AsyncClient):
    """Test getting own vitals."""
    response = await authenticated_client.get("/api/v1/vitals/me")
    assert response.status_code == 200

    data = response.json()
    assert "is_online" in data
    assert "current_load" in data


@pytest.mark.asyncio
async def test_update_vitals(authenticated_client: AsyncClient):
    """Test updating own vitals."""
    response = await authenticated_client.patch(
        "/api/v1/vitals/me",
        json={
            "is_online": True,
            "current_load": 0.5,
            "capabilities_status": {"code_review": "available", "testing": "busy"},
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["is_online"] is True
    assert data["current_load"] == 0.5


@pytest.mark.asyncio
async def test_send_heartbeat(authenticated_client: AsyncClient):
    """Test sending heartbeat."""
    response = await authenticated_client.post("/api/v1/vitals/heartbeat")
    assert response.status_code == 200

    data = response.json()
    assert "last_heartbeat" in data


@pytest.mark.asyncio
async def test_get_agent_vitals(authenticated_client: AsyncClient, client: AsyncClient):
    """Test getting another agent's vitals."""
    # Register another agent
    unique_slug = f"vitals-target-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "vitals-target",
            "slug": unique_slug,
            "description": "Agent to check vitals",
        },
    )
    agent_data = register_response.json()
    agent_id = agent_data["agent"]["id"]

    # Set up auth for new agent and update their vitals
    client.headers["Authorization"] = f"Bearer {agent_data['api_key']}"
    client.headers["X-Agent-ID"] = str(agent_id)
    await client.patch("/api/v1/vitals/me", json={"is_online": True})

    # Get their vitals from original authenticated client
    response = await authenticated_client.get(f"/api/v1/vitals/{agent_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_subscribe_to_vitals(authenticated_client: AsyncClient, client: AsyncClient):
    """Test subscribing to another agent's vitals."""
    # Register another agent
    unique_slug = f"subscribe-target-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "subscribe-target",
            "slug": unique_slug,
            "description": "Agent to subscribe to",
        },
    )
    agent_id = register_response.json()["agent"]["id"]

    # Subscribe - note: endpoint uses agent_id in path, not in body
    response = await authenticated_client.post(
        f"/api/v1/vitals/{agent_id}/subscribe",
        json={"notify_on": ["status_change", "offline"]},
    )
    assert response.status_code == 201

    data = response.json()
    assert "id" in data


@pytest.mark.asyncio
async def test_unsubscribe_from_vitals(
    authenticated_client: AsyncClient, client: AsyncClient
):
    """Test unsubscribing from vitals."""
    # Register and subscribe
    unique_slug = f"unsub-target-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "unsub-target",
            "slug": unique_slug,
            "description": "Agent to unsubscribe from",
        },
    )
    agent_id = register_response.json()["agent"]["id"]

    sub_response = await authenticated_client.post(
        f"/api/v1/vitals/{agent_id}/subscribe",
        json={"notify_on": ["status_change"]},
    )
    subscription_id = sub_response.json()["id"]

    # Unsubscribe
    response = await authenticated_client.delete(
        f"/api/v1/vitals/subscriptions/{subscription_id}"
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_subscriptions(authenticated_client: AsyncClient):
    """Test listing vitals subscriptions."""
    response = await authenticated_client.get("/api/v1/vitals/subscriptions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_find_healthy_agents(authenticated_client: AsyncClient):
    """Test finding healthy agents."""
    # First update own vitals to be healthy
    await authenticated_client.patch(
        "/api/v1/vitals/me",
        json={
            "is_online": True,
            "current_load": 0.3,
            "capabilities_status": {"code_review": "available"},
        },
    )

    # Find healthy agents
    response = await authenticated_client.post(
        "/api/v1/vitals/find-healthy",
        json={
            "capability": "code_review",
            "max_load": 0.8,
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_find_best_agent(authenticated_client: AsyncClient):
    """Test finding the best agent for a task."""
    # Update own vitals
    await authenticated_client.patch(
        "/api/v1/vitals/me",
        json={
            "is_online": True,
            "current_load": 0.2,
            "capabilities_status": {"analysis": "available"},
        },
    )

    # Find best agent
    response = await authenticated_client.get(
        "/api/v1/vitals/best",
        params={"capability": "analysis"},
    )
    # May return null if no suitable agent, or agent data
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_take_snapshot(authenticated_client: AsyncClient):
    """Test taking a vitals snapshot."""
    # Update vitals first
    await authenticated_client.patch(
        "/api/v1/vitals/me",
        json={"is_online": True, "current_load": 0.6},
    )

    # Take snapshot
    response = await authenticated_client.post("/api/v1/vitals/snapshot")
    assert response.status_code == 200

    data = response.json()
    assert "agent_id" in data


@pytest.mark.asyncio
async def test_get_snapshots(authenticated_client: AsyncClient):
    """Test getting vitals snapshots."""
    # Get own agent ID
    me_response = await authenticated_client.get("/api/v1/agents/me")
    agent_id = me_response.json()["id"]

    # Take a snapshot first
    await authenticated_client.post("/api/v1/vitals/snapshot")

    # Get snapshots
    response = await authenticated_client.get(f"/api/v1/vitals/{agent_id}/snapshots")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_vitals_load_levels(authenticated_client: AsyncClient):
    """Test different load levels."""
    load_levels = [0.0, 0.25, 0.5, 0.75, 1.0]

    for load in load_levels:
        response = await authenticated_client.patch(
            "/api/v1/vitals/me",
            json={"current_load": load},
        )
        assert response.status_code == 200
        assert response.json()["current_load"] == load


@pytest.mark.asyncio
async def test_vitals_offline_status(authenticated_client: AsyncClient):
    """Test setting offline status."""
    # Go offline
    response = await authenticated_client.patch(
        "/api/v1/vitals/me",
        json={"is_online": False},
    )
    assert response.status_code == 200
    assert response.json()["is_online"] is False

    # Go back online
    response = await authenticated_client.patch(
        "/api/v1/vitals/me",
        json={"is_online": True},
    )
    assert response.status_code == 200
    assert response.json()["is_online"] is True


@pytest.mark.asyncio
async def test_capabilities_status_updates(authenticated_client: AsyncClient):
    """Test updating capabilities status."""
    statuses = ["available", "busy", "unavailable", "maintenance"]

    for status in statuses:
        response = await authenticated_client.patch(
            "/api/v1/vitals/me",
            json={"capabilities_status": {"test_capability": status}},
        )
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_heartbeat_updates_last_seen(authenticated_client: AsyncClient):
    """Test that heartbeat updates last seen timestamp."""
    # First heartbeat
    response1 = await authenticated_client.post("/api/v1/vitals/heartbeat")
    assert response1.status_code == 200
    first_heartbeat = response1.json()["last_heartbeat"]

    # Second heartbeat
    response2 = await authenticated_client.post("/api/v1/vitals/heartbeat")
    assert response2.status_code == 200
    second_heartbeat = response2.json()["last_heartbeat"]

    # Timestamps should be different (or at least second >= first)
    assert second_heartbeat >= first_heartbeat
