"""Tests for goals module."""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_goal(authenticated_client: AsyncClient):
    """Test creating a new goal."""
    response = await authenticated_client.post(
        "/api/v1/goals",
        json={
            "title": "Complete Project Alpha",
            "description": "Finish all tasks for Project Alpha",
            "success_criteria": "All tests passing, documentation complete",
            "priority": "high",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "Complete Project Alpha"
    assert data["priority"] == "high"
    assert data["status"] == "draft"  # Default status is draft


@pytest.mark.asyncio
async def test_list_goals(authenticated_client: AsyncClient):
    """Test listing goals."""
    # Create a goal first
    await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "List Test Goal"},
    )

    response = await authenticated_client.get("/api/v1/goals")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_goal(authenticated_client: AsyncClient):
    """Test getting a specific goal."""
    # Create a goal
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Get Test Goal", "description": "A goal to retrieve"},
    )
    goal_id = create_response.json()["id"]

    # Get the goal
    response = await authenticated_client.get(f"/api/v1/goals/{goal_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Get Test Goal"


@pytest.mark.asyncio
async def test_update_goal(authenticated_client: AsyncClient):
    """Test updating a goal."""
    # Create a goal
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Update Test Goal", "priority": "low"},
    )
    goal_id = create_response.json()["id"]

    # Update the goal
    response = await authenticated_client.patch(
        f"/api/v1/goals/{goal_id}",
        json={"priority": "high", "description": "Updated description"},
    )
    assert response.status_code == 200
    assert response.json()["priority"] == "high"


@pytest.mark.asyncio
async def test_activate_goal(authenticated_client: AsyncClient):
    """Test activating a goal."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Activate Test Goal"},
    )
    goal_id = create_response.json()["id"]

    response = await authenticated_client.post(f"/api/v1/goals/{goal_id}/activate")
    assert response.status_code == 200
    assert response.json()["status"] == "active"


@pytest.mark.asyncio
async def test_start_goal(authenticated_client: AsyncClient):
    """Test starting a goal."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Start Test Goal"},
    )
    goal_id = create_response.json()["id"]

    # Activate first
    await authenticated_client.post(f"/api/v1/goals/{goal_id}/activate")

    # Start
    response = await authenticated_client.post(f"/api/v1/goals/{goal_id}/start")
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_update_progress(authenticated_client: AsyncClient):
    """Test updating goal progress."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Progress Test Goal"},
    )
    goal_id = create_response.json()["id"]

    # Activate and start
    await authenticated_client.post(f"/api/v1/goals/{goal_id}/activate")
    await authenticated_client.post(f"/api/v1/goals/{goal_id}/start")

    # Update progress
    response = await authenticated_client.post(
        f"/api/v1/goals/{goal_id}/progress",
        json={"progress_percent": 50, "progress_notes": "Halfway there"},
    )
    assert response.status_code == 200
    assert response.json()["progress_percent"] == 50


@pytest.mark.asyncio
async def test_complete_goal(authenticated_client: AsyncClient):
    """Test completing a goal."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Complete Test Goal"},
    )
    goal_id = create_response.json()["id"]

    # Progress through states
    await authenticated_client.post(f"/api/v1/goals/{goal_id}/activate")
    await authenticated_client.post(f"/api/v1/goals/{goal_id}/start")

    # Complete - use query params as the endpoint expects
    response = await authenticated_client.post(
        f"/api/v1/goals/{goal_id}/complete",
        params={"outcome": "All objectives achieved successfully"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_fail_goal(authenticated_client: AsyncClient):
    """Test failing a goal."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Fail Test Goal"},
    )
    goal_id = create_response.json()["id"]

    await authenticated_client.post(f"/api/v1/goals/{goal_id}/activate")
    await authenticated_client.post(f"/api/v1/goals/{goal_id}/start")

    response = await authenticated_client.post(
        f"/api/v1/goals/{goal_id}/fail",
        params={"outcome": "Requirements changed, goal no longer relevant"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_cancel_goal(authenticated_client: AsyncClient):
    """Test canceling a goal."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Cancel Test Goal"},
    )
    goal_id = create_response.json()["id"]

    response = await authenticated_client.post(
        f"/api/v1/goals/{goal_id}/cancel",
        params={"reason": "Project deprioritized"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_add_milestone(authenticated_client: AsyncClient):
    """Test adding a milestone to a goal."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Milestone Test Goal"},
    )
    goal_id = create_response.json()["id"]

    response = await authenticated_client.post(
        f"/api/v1/goals/{goal_id}/milestones",
        json={
            "title": "Phase 1: Design",
            "description": "Complete system design",
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Phase 1: Design"


@pytest.mark.asyncio
async def test_complete_milestone(authenticated_client: AsyncClient):
    """Test completing a milestone."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Complete Milestone Test Goal"},
    )
    goal_id = create_response.json()["id"]

    milestone_response = await authenticated_client.post(
        f"/api/v1/goals/{goal_id}/milestones",
        json={"title": "Test Milestone"},
    )
    milestone_id = milestone_response.json()["id"]

    response = await authenticated_client.post(
        f"/api/v1/goals/milestones/{milestone_id}/complete"
    )
    assert response.status_code == 200
    assert response.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_add_blocker(authenticated_client: AsyncClient):
    """Test adding a blocker to a goal."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Blocker Test Goal"},
    )
    goal_id = create_response.json()["id"]

    response = await authenticated_client.post(
        f"/api/v1/goals/{goal_id}/blockers",
        json={
            "title": "Waiting for API access",
            "description": "Need API credentials from vendor",
            "blocker_type": "external",
            "severity": "high",
        },
    )
    assert response.status_code == 201
    assert response.json()["title"] == "Waiting for API access"


@pytest.mark.asyncio
async def test_list_blockers(authenticated_client: AsyncClient):
    """Test listing blockers for a goal."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "List Blockers Test Goal"},
    )
    goal_id = create_response.json()["id"]

    # Add a blocker
    await authenticated_client.post(
        f"/api/v1/goals/{goal_id}/blockers",
        json={
            "title": "Test blocker",
            "blocker_type": "technical",
        },
    )

    response = await authenticated_client.get(f"/api/v1/goals/{goal_id}/blockers")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_resolve_blocker(authenticated_client: AsyncClient):
    """Test resolving a blocker."""
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Resolve Blocker Test Goal"},
    )
    goal_id = create_response.json()["id"]

    blocker_response = await authenticated_client.post(
        f"/api/v1/goals/{goal_id}/blockers",
        json={
            "title": "Resolvable blocker",
            "blocker_type": "resource",
        },
    )
    blocker_id = blocker_response.json()["id"]

    response = await authenticated_client.post(
        f"/api/v1/goals/blockers/{blocker_id}/resolve",
        json={"resolution": "Got the API access"},
    )
    assert response.status_code == 200
    assert response.json()["resolved_at"] is not None


@pytest.mark.asyncio
async def test_delegate_goal(authenticated_client: AsyncClient, client: AsyncClient):
    """Test delegating a goal to another agent."""
    # Create goal
    create_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Delegate Test Goal"},
    )
    goal_id = create_response.json()["id"]

    # Register another agent
    unique_slug = f"delegate-target-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "delegate-target",
            "slug": unique_slug,
            "description": "Agent to delegate to",
        },
    )
    target_id = register_response.json()["agent"]["id"]

    # Delegate
    response = await authenticated_client.post(
        f"/api/v1/goals/{goal_id}/delegate",
        json={
            "delegate_id": target_id,
            "title": "Help with this goal",
            "description": "Please help with this goal",
        },
    )
    assert response.status_code == 201
    assert response.json()["delegate_id"] == target_id


@pytest.mark.asyncio
async def test_incoming_delegations(authenticated_client: AsyncClient):
    """Test listing incoming delegations."""
    response = await authenticated_client.get("/api/v1/goals/delegations/incoming")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_goal_with_parent(authenticated_client: AsyncClient):
    """Test creating a sub-goal."""
    # Create parent goal
    parent_response = await authenticated_client.post(
        "/api/v1/goals",
        json={"title": "Parent Goal"},
    )
    parent_id = parent_response.json()["id"]

    # Create sub-goal
    response = await authenticated_client.post(
        "/api/v1/goals",
        json={
            "title": "Sub Goal",
            "parent_goal_id": parent_id,
        },
    )
    assert response.status_code == 201
    assert response.json()["parent_goal_id"] == parent_id
