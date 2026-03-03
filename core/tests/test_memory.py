"""Tests for memory module."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_store_memory(authenticated_client: AsyncClient):
    """Test storing memory."""
    response = await authenticated_client.post(
        "/api/v1/memory",
        json={
            "key": "test-memory",
            "value": {"message": "Hello, World!"},
            "scope": "agent",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["key"] == "test-memory"
    assert data["value"]["message"] == "Hello, World!"


@pytest.mark.asyncio
async def test_get_memory(authenticated_client: AsyncClient):
    """Test retrieving memory."""
    # First store a memory
    store_response = await authenticated_client.post(
        "/api/v1/memory",
        json={
            "key": "get-test-key",
            "value": {"data": "test value"},
        },
    )
    assert store_response.status_code == 201

    # Then retrieve it
    response = await authenticated_client.get("/api/v1/memory/get-test-key")
    assert response.status_code == 200

    data = response.json()
    assert data["key"] == "get-test-key"
    assert data["value"]["data"] == "test value"


@pytest.mark.asyncio
async def test_list_memories(authenticated_client: AsyncClient):
    """Test listing memories."""
    # Store a memory first
    store_response = await authenticated_client.post(
        "/api/v1/memory",
        json={
            "key": "list-test-key",
            "value": {"data": "for listing"},
        },
    )
    assert store_response.status_code == 201

    # List memories
    response = await authenticated_client.get("/api/v1/memory")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_delete_memory(authenticated_client: AsyncClient):
    """Test deleting memory."""
    # Store a memory first
    store_response = await authenticated_client.post(
        "/api/v1/memory",
        json={
            "key": "delete-test-key",
            "value": {"data": "to be deleted"},
        },
    )
    assert store_response.status_code == 201

    # Delete it
    response = await authenticated_client.delete("/api/v1/memory/delete-test-key")
    assert response.status_code == 204

    # Verify it's gone
    get_response = await authenticated_client.get("/api/v1/memory/delete-test-key")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_search_memory(authenticated_client: AsyncClient):
    """Test searching memories."""
    # Store a memory with searchable content
    store_response = await authenticated_client.post(
        "/api/v1/memory",
        json={
            "key": "search-test-key",
            "value": {"data": "searchable content"},
            "text_content": "This is searchable test content for memory search",
        },
    )
    assert store_response.status_code == 201

    # Search for it
    response = await authenticated_client.post(
        "/api/v1/memory/search",
        json={"query": "searchable content"},
    )
    assert response.status_code == 200

    data = response.json()
    assert "results" in data
    assert "total" in data
