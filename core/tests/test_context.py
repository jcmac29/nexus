"""Tests for context module."""

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_pack_context(authenticated_client: AsyncClient):
    """Test packing context into a package."""
    response = await authenticated_client.post(
        "/api/v1/context/pack",
        json={
            "name": "Research Context",
            "summary": "Research findings on quantum computing",
            "goals": {"current": "analysis", "completed": ["research"]},
            "memories": {"findings": ["finding1", "finding2"]},
            "reasoning_trace": [
                "Step 1: Gathered initial data",
                "Step 2: Analyzed patterns",
            ],
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Research Context"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_packages(authenticated_client: AsyncClient):
    """Test listing context packages."""
    # Create a package first
    await authenticated_client.post(
        "/api/v1/context/pack",
        json={"name": "List Test Package", "summary": "Test package"},
    )

    response = await authenticated_client.get("/api/v1/context/packages")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_package(authenticated_client: AsyncClient):
    """Test getting a specific context package."""
    # Create a package
    create_response = await authenticated_client.post(
        "/api/v1/context/pack",
        json={"name": "Get Test Package", "summary": "Package to retrieve"},
    )
    package_id = create_response.json()["id"]

    # Get the package - returns detailed view
    response = await authenticated_client.get(f"/api/v1/context/packages/{package_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Get Test Package"


@pytest.mark.asyncio
async def test_unpack_package(authenticated_client: AsyncClient):
    """Test unpacking a context package."""
    # Create a package with data
    create_response = await authenticated_client.post(
        "/api/v1/context/pack",
        json={
            "name": "Unpack Test Package",
            "summary": "Package with data",
            "memories": {"key": "value"},
            "reasoning_trace": ["step 1", "step 2"],
        },
    )
    package_id = create_response.json()["id"]

    # Unpack
    response = await authenticated_client.get(
        f"/api/v1/context/packages/{package_id}/unpack"
    )
    assert response.status_code == 200

    data = response.json()
    assert data["memories"]["key"] == "value"
    assert len(data["reasoning_trace"]) == 2


@pytest.mark.asyncio
async def test_delete_package(authenticated_client: AsyncClient):
    """Test deleting a context package."""
    create_response = await authenticated_client.post(
        "/api/v1/context/pack",
        json={"name": "Delete Test Package", "summary": "Package to delete"},
    )
    package_id = create_response.json()["id"]

    # Delete
    response = await authenticated_client.delete(
        f"/api/v1/context/packages/{package_id}"
    )
    assert response.status_code == 200

    # Verify deleted
    get_response = await authenticated_client.get(
        f"/api/v1/context/packages/{package_id}"
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_transfer_context(authenticated_client: AsyncClient, client: AsyncClient):
    """Test transferring context to another agent."""
    # Create a package
    create_response = await authenticated_client.post(
        "/api/v1/context/pack",
        json={"name": "Transfer Test Package", "summary": "Package to transfer"},
    )
    package_id = create_response.json()["id"]

    # Register another agent
    unique_slug = f"transfer-target-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "transfer-target",
            "slug": unique_slug,
            "description": "Agent to receive context",
        },
    )
    receiver_id = register_response.json()["agent"]["id"]

    # Transfer
    response = await authenticated_client.post(
        "/api/v1/context/transfer",
        json={
            "package_id": package_id,
            "receiver_id": receiver_id,
            "purpose": "Need domain expertise",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["receiver_id"] == receiver_id
    assert data["purpose"] == "Need domain expertise"


@pytest.mark.asyncio
async def test_incoming_transfers(authenticated_client: AsyncClient):
    """Test listing incoming transfers."""
    response = await authenticated_client.get("/api/v1/context/transfers/incoming")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_outgoing_transfers(authenticated_client: AsyncClient):
    """Test listing outgoing transfers."""
    response = await authenticated_client.get("/api/v1/context/transfers/outgoing")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_transfer_flow(authenticated_client: AsyncClient, client: AsyncClient):
    """Test full transfer flow: create, send, receive, apply."""
    # Create package
    create_response = await authenticated_client.post(
        "/api/v1/context/pack",
        json={
            "name": "Flow Test Package",
            "summary": "Package for flow test",
            "memories": {"data": "important"},
        },
    )
    package_id = create_response.json()["id"]

    # Register receiver agent
    unique_slug = f"flow-receiver-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "flow-receiver",
            "slug": unique_slug,
            "description": "Flow test receiver",
        },
    )
    receiver_data = register_response.json()
    receiver_id = receiver_data["agent"]["id"]

    # Transfer
    transfer_response = await authenticated_client.post(
        "/api/v1/context/transfer",
        json={
            "package_id": package_id,
            "receiver_id": receiver_id,
            "purpose": "Flow test",
        },
    )
    transfer_id = transfer_response.json()["id"]

    # Switch to receiver client
    client.headers["Authorization"] = f"Bearer {receiver_data['api_key']}"
    client.headers["X-Agent-ID"] = str(receiver_id)

    # Mark as received
    receive_response = await client.post(
        f"/api/v1/context/transfers/{transfer_id}/receive"
    )
    assert receive_response.status_code == 200

    # Accept the transfer
    decide_response = await client.post(
        f"/api/v1/context/transfers/{transfer_id}/decide",
        json={"accept": True},
    )
    assert decide_response.status_code == 200

    # Apply the transfer
    apply_response = await client.post(
        f"/api/v1/context/transfers/{transfer_id}/apply"
    )
    assert apply_response.status_code == 200


@pytest.mark.asyncio
async def test_reject_transfer(authenticated_client: AsyncClient, client: AsyncClient):
    """Test rejecting a context transfer."""
    # Create and transfer
    create_response = await authenticated_client.post(
        "/api/v1/context/pack",
        json={"name": "Reject Test", "summary": "Test"},
    )
    package_id = create_response.json()["id"]

    unique_slug = f"reject-receiver-{uuid.uuid4().hex[:8]}"
    register_response = await client.post(
        "/api/v1/agents",
        json={
            "name": "reject-receiver",
            "slug": unique_slug,
            "description": "Rejecting receiver",
        },
    )
    receiver_data = register_response.json()
    receiver_id = receiver_data["agent"]["id"]

    transfer_response = await authenticated_client.post(
        "/api/v1/context/transfer",
        json={"package_id": package_id, "receiver_id": receiver_id, "purpose": "Test"},
    )
    transfer_id = transfer_response.json()["id"]

    # Switch to receiver
    client.headers["Authorization"] = f"Bearer {receiver_data['api_key']}"
    client.headers["X-Agent-ID"] = str(receiver_id)

    # Reject
    response = await client.post(
        f"/api/v1/context/transfers/{transfer_id}/decide",
        json={"accept": False, "message": "Not relevant to my work"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_pack_with_tags(authenticated_client: AsyncClient):
    """Test packing context with tags."""
    response = await authenticated_client.post(
        "/api/v1/context/pack",
        json={
            "name": "Tagged Package",
            "summary": "Package with tags",
            "tags": ["research", "analysis"],
        },
    )
    assert response.status_code == 201
    assert "research" in response.json()["tags"]
