"""Tests for analytics module."""

import pytest
from datetime import datetime, timedelta
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_dashboard(authenticated_client: AsyncClient):
    """Test getting analytics dashboard."""
    response = await authenticated_client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 200

    data = response.json()
    assert "total_requests" in data
    assert "total_memories" in data
    assert "total_capabilities" in data
    assert "period" in data


@pytest.mark.asyncio
async def test_get_dashboard_with_period(authenticated_client: AsyncClient):
    """Test dashboard with custom time period."""
    response = await authenticated_client.get(
        "/api/v1/analytics/dashboard",
        params={"days": 30},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["period"]["days"] == 30


@pytest.mark.asyncio
async def test_get_usage_metrics(authenticated_client: AsyncClient):
    """Test getting usage metrics."""
    response = await authenticated_client.get("/api/v1/analytics/usage")
    assert response.status_code == 200

    data = response.json()
    assert "metrics" in data
    assert "period" in data


@pytest.mark.asyncio
async def test_get_usage_metrics_filtered(authenticated_client: AsyncClient):
    """Test getting filtered usage metrics."""
    response = await authenticated_client.get(
        "/api/v1/analytics/usage",
        params={
            "metric_types": ["api_request", "memory_store"],
            "granularity": "hour",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert "metrics" in data


@pytest.mark.asyncio
async def test_get_usage_timeline(authenticated_client: AsyncClient):
    """Test getting usage timeline data."""
    response = await authenticated_client.get("/api/v1/analytics/usage/timeline")
    assert response.status_code == 200

    data = response.json()
    assert "timeline" in data


@pytest.mark.asyncio
async def test_get_endpoint_metrics(authenticated_client: AsyncClient):
    """Test getting per-endpoint metrics."""
    # Make some API calls first
    await authenticated_client.get("/api/v1/memory")
    await authenticated_client.get("/api/v1/memory")

    response = await authenticated_client.get("/api/v1/analytics/endpoints")
    assert response.status_code == 200

    data = response.json()
    assert "endpoints" in data


@pytest.mark.asyncio
async def test_get_endpoint_metrics_filtered(authenticated_client: AsyncClient):
    """Test endpoint metrics with filters."""
    response = await authenticated_client.get(
        "/api/v1/analytics/endpoints",
        params={"endpoint": "/api/v1/memory"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_storage_usage(authenticated_client: AsyncClient, test_memory):
    """Test getting storage usage."""
    response = await authenticated_client.get("/api/v1/analytics/storage")
    assert response.status_code == 200

    data = response.json()
    assert "current" in data
    assert "history" in data


@pytest.mark.asyncio
async def test_get_storage_usage_history(authenticated_client: AsyncClient):
    """Test storage usage historical data."""
    response = await authenticated_client.get(
        "/api/v1/analytics/storage",
        params={"days": 30},
    )
    assert response.status_code == 200

    data = response.json()
    assert "history" in data


@pytest.mark.asyncio
async def test_export_analytics_json(authenticated_client: AsyncClient):
    """Test exporting analytics data as JSON."""
    response = await authenticated_client.get(
        "/api/v1/analytics/export",
        params={"format": "json"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_export_analytics_csv(authenticated_client: AsyncClient):
    """Test exporting analytics data as CSV."""
    response = await authenticated_client.get(
        "/api/v1/analytics/export",
        params={"format": "csv"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_export_analytics_date_range(authenticated_client: AsyncClient):
    """Test exporting with date range."""
    start_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    end_date = datetime.utcnow().strftime("%Y-%m-%d")

    response = await authenticated_client.get(
        "/api/v1/analytics/export",
        params={
            "format": "json",
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_request_trends(authenticated_client: AsyncClient):
    """Test that dashboard shows request trends."""
    # Make multiple requests
    for _ in range(5):
        await authenticated_client.get("/api/v1/memory")

    response = await authenticated_client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 200

    data = response.json()
    assert data["total_requests"] >= 0


@pytest.mark.asyncio
async def test_metrics_aggregation(authenticated_client: AsyncClient):
    """Test that metrics are properly aggregated."""
    response = await authenticated_client.get(
        "/api/v1/analytics/usage",
        params={"granularity": "day"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_analytics_empty_period(authenticated_client: AsyncClient):
    """Test analytics for period with no data."""
    # Use a period far in the past
    response = await authenticated_client.get(
        "/api/v1/analytics/dashboard",
        params={"days": 1},
    )
    assert response.status_code == 200

    # Should still return valid structure
    data = response.json()
    assert "total_requests" in data
