"""Tests for swarm module."""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_swarm(authenticated_client: AsyncClient):
    """Test creating a new swarm."""
    response = await authenticated_client.post(
        "/api/v1/swarm",
        json={
            "name": "Test Swarm",
            "config": {"max_members": 10},
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["swarm"]["name"] == "Test Swarm"
    assert "join_code" in data
    assert len(data["join_code"]) == 6
    assert data["member"]["role"] == "leader"


@pytest.mark.asyncio
async def test_join_swarm(authenticated_client: AsyncClient, client: AsyncClient):
    """Test joining an existing swarm."""
    # Create a swarm first
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "Join Test Swarm"},
    )
    assert create_response.status_code == 201
    join_code = create_response.json()["join_code"]

    # Register a second agent
    unique_slug = f"worker-agent-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "worker-agent",
            "slug": unique_slug,
            "description": "A worker agent",
        },
    )
    assert register_response.status_code == 201
    worker_data = register_response.json()

    # Create authenticated client for worker
    client.headers["Authorization"] = f"Bearer {worker_data['api_key']}"
    client.headers["X-Agent-ID"] = str(worker_data["agent"]["id"])

    # Join the swarm
    join_response = await client.post(
        "/api/v1/swarm/join",
        json={
            "join_code": join_code,
            "capabilities": ["code_review", "testing"],
        },
    )
    assert join_response.status_code == 200

    data = join_response.json()
    assert data["member"]["role"] == "worker"
    assert "code_review" in data["member"]["capabilities"]


@pytest.mark.asyncio
async def test_get_swarm_status(authenticated_client: AsyncClient):
    """Test getting swarm status."""
    # Create a swarm
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "Status Test Swarm"},
    )
    assert create_response.status_code == 201
    swarm_id = create_response.json()["swarm"]["id"]

    # Get status
    response = await authenticated_client.get(f"/api/v1/swarm/{swarm_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["swarm"]["name"] == "Status Test Swarm"
    assert len(data["members"]) == 1
    assert data["task_summary"]["pending_tasks"] == 0


@pytest.mark.asyncio
async def test_submit_task(authenticated_client: AsyncClient):
    """Test submitting a task to the swarm."""
    # Create a swarm
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "Task Test Swarm"},
    )
    assert create_response.status_code == 201
    swarm_id = create_response.json()["swarm"]["id"]

    # Submit a task
    response = await authenticated_client.post(
        f"/api/v1/swarm/{swarm_id}/tasks",
        json={
            "title": "Review file.py",
            "description": "Review the file for security issues",
            "task_type": "code_review",
            "priority": 8,
            "input_data": {"file_path": "src/file.py"},
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "Review file.py"
    assert data["status"] == "pending"
    assert data["priority"] == 8


@pytest.mark.asyncio
async def test_submit_batch_tasks(authenticated_client: AsyncClient):
    """Test submitting multiple tasks at once."""
    # Create a swarm
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "Batch Test Swarm"},
    )
    assert create_response.status_code == 201
    swarm_id = create_response.json()["swarm"]["id"]

    # Submit batch
    response = await authenticated_client.post(
        f"/api/v1/swarm/{swarm_id}/tasks/batch",
        json={
            "tasks": [
                {"title": "Task 1", "priority": 5},
                {"title": "Task 2", "priority": 7},
                {"title": "Task 3", "priority": 3},
            ]
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert len(data) == 3
    assert data[0]["title"] == "Task 1"
    assert data[1]["title"] == "Task 2"
    assert data[2]["title"] == "Task 3"


@pytest.mark.asyncio
async def test_claim_task(authenticated_client: AsyncClient):
    """Test claiming a task from the swarm."""
    # Create a swarm
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "Claim Test Swarm"},
    )
    assert create_response.status_code == 201
    swarm_id = create_response.json()["swarm"]["id"]

    # Submit a task
    await authenticated_client.post(
        f"/api/v1/swarm/{swarm_id}/tasks",
        json={"title": "Claimable Task"},
    )

    # Claim the task
    response = await authenticated_client.post(
        f"/api/v1/swarm/tasks/claim?swarm_id={swarm_id}"
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Claimable Task"
    assert data["status"] == "assigned"


@pytest.mark.asyncio
async def test_complete_task(authenticated_client: AsyncClient):
    """Test completing a task."""
    # Create a swarm
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "Complete Test Swarm"},
    )
    assert create_response.status_code == 201
    swarm_id = create_response.json()["swarm"]["id"]

    # Submit a task
    task_response = await authenticated_client.post(
        f"/api/v1/swarm/{swarm_id}/tasks",
        json={"title": "Completable Task"},
    )
    task_id = task_response.json()["id"]

    # Claim the task
    await authenticated_client.post(f"/api/v1/swarm/tasks/claim?swarm_id={swarm_id}")

    # Start the task
    await authenticated_client.post(f"/api/v1/swarm/tasks/{task_id}/start")

    # Complete the task
    response = await authenticated_client.post(
        f"/api/v1/swarm/tasks/{task_id}/complete",
        json={
            "output_data": {"result": "All good!"},
            "success": True,
            "execution_time_ms": 1500,
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["success"] is True
    assert data["output_data"]["result"] == "All good!"


@pytest.mark.asyncio
async def test_list_tasks(authenticated_client: AsyncClient):
    """Test listing tasks in a swarm."""
    # Create a swarm
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "List Test Swarm"},
    )
    assert create_response.status_code == 201
    swarm_id = create_response.json()["swarm"]["id"]

    # Submit some tasks
    for i in range(3):
        await authenticated_client.post(
            f"/api/v1/swarm/{swarm_id}/tasks",
            json={"title": f"Task {i+1}"},
        )

    # List tasks
    response = await authenticated_client.get(f"/api/v1/swarm/{swarm_id}/tasks")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_get_results(authenticated_client: AsyncClient):
    """Test getting aggregated results."""
    # Create a swarm
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "Results Test Swarm"},
    )
    assert create_response.status_code == 201
    swarm_id = create_response.json()["swarm"]["id"]

    # Submit and complete a task
    task_response = await authenticated_client.post(
        f"/api/v1/swarm/{swarm_id}/tasks",
        json={"title": "Result Task"},
    )
    task_id = task_response.json()["id"]

    await authenticated_client.post(f"/api/v1/swarm/tasks/claim?swarm_id={swarm_id}")
    await authenticated_client.post(f"/api/v1/swarm/tasks/{task_id}/start")
    await authenticated_client.post(
        f"/api/v1/swarm/tasks/{task_id}/complete",
        json={"output_data": {"data": "result"}},
    )

    # Get results
    response = await authenticated_client.get(f"/api/v1/swarm/{swarm_id}/results")
    assert response.status_code == 200

    data = response.json()
    assert data["completed_tasks"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["output_data"]["data"] == "result"


@pytest.mark.asyncio
async def test_leave_swarm(authenticated_client: AsyncClient):
    """Test leaving a swarm."""
    # Create a swarm
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "Leave Test Swarm"},
    )
    assert create_response.status_code == 201
    swarm_id = create_response.json()["swarm"]["id"]

    # Leave the swarm
    response = await authenticated_client.post(f"/api/v1/swarm/{swarm_id}/leave")
    assert response.status_code == 200
    assert response.json()["status"] == "left"


@pytest.mark.asyncio
async def test_disband_swarm(authenticated_client: AsyncClient):
    """Test disbanding a swarm."""
    # Create a swarm
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "Disband Test Swarm"},
    )
    assert create_response.status_code == 201
    swarm_id = create_response.json()["swarm"]["id"]

    # Disband the swarm
    response = await authenticated_client.delete(f"/api/v1/swarm/{swarm_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "disbanded"


@pytest.mark.asyncio
async def test_heartbeat(authenticated_client: AsyncClient):
    """Test sending heartbeat."""
    # Create a swarm
    create_response = await authenticated_client.post(
        "/api/v1/swarm",
        json={"name": "Heartbeat Test Swarm"},
    )
    assert create_response.status_code == 201
    swarm_id = create_response.json()["swarm"]["id"]

    # Send heartbeat
    response = await authenticated_client.post(f"/api/v1/swarm/{swarm_id}/heartbeat")
    assert response.status_code == 200

    data = response.json()
    assert "last_heartbeat" in data


@pytest.mark.asyncio
async def test_invalid_join_code(authenticated_client: AsyncClient):
    """Test joining with invalid code."""
    response = await authenticated_client.post(
        "/api/v1/swarm/join",
        json={"join_code": "XXXXXX"},
    )
    assert response.status_code == 400
    assert "Invalid join code" in response.json()["detail"]
