"""Tests for health check endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test basic health check."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test root endpoint."""
    response = await client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Nexus"
    assert "version" in data


@pytest.mark.asyncio
async def test_liveness_probe(client: AsyncClient):
    """Test Kubernetes liveness probe."""
    response = await client.get("/api/v1/health/live")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "alive"
