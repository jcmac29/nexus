"""Tests for memory module."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_store_memory(authenticated_client: AsyncClient, test_agent):
    """Test storing memory."""
    response = await authenticated_client.post(
        "/api/v1/memory",
        json={
            "key": "test-memory",
            "value": {"message": "Hello, World!"},
            "memory_type": "short_term",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["key"] == "test-memory"
    assert data["value"]["message"] == "Hello, World!"


@pytest.mark.asyncio
async def test_get_memory(authenticated_client: AsyncClient, test_memory):
    """Test retrieving memory."""
    response = await authenticated_client.get(f"/api/v1/memory/{test_memory.key}")
    assert response.status_code == 200

    data = response.json()
    assert data["key"] == test_memory.key


@pytest.mark.asyncio
async def test_list_memories(authenticated_client: AsyncClient, test_memory):
    """Test listing memories."""
    response = await authenticated_client.get("/api/v1/memory")
    assert response.status_code == 200

    data = response.json()
    assert "memories" in data


@pytest.mark.asyncio
async def test_delete_memory(authenticated_client: AsyncClient, test_memory):
    """Test deleting memory."""
    response = await authenticated_client.delete(f"/api/v1/memory/{test_memory.key}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_search_memory(authenticated_client: AsyncClient, test_memory):
    """Test searching memories."""
    response = await authenticated_client.get(
        "/api/v1/memory/search",
        params={"query": "test"},
    )
    assert response.status_code == 200

    data = response.json()
    assert "results" in data
