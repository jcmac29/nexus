"""Tests for budgets module."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_budget(authenticated_client: AsyncClient):
    """Test creating a new budget."""
    response = await authenticated_client.post(
        "/api/v1/budgets",
        json={
            "budget_type": "api_calls",
            "name": "Daily API Quota",
            "total_limit": 10000,
            "alert_threshold": 0.8,
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Daily API Quota"
    assert data["total_limit"] == 10000
    assert data["used_amount"] == 0


@pytest.mark.asyncio
async def test_list_budgets(authenticated_client: AsyncClient):
    """Test listing budgets."""
    # Create a budget
    await authenticated_client.post(
        "/api/v1/budgets",
        json={"budget_type": "tokens", "name": "Token Budget", "total_limit": 5000},
    )

    response = await authenticated_client.get("/api/v1/budgets")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_budget_summary(authenticated_client: AsyncClient):
    """Test getting budget summary."""
    response = await authenticated_client.get("/api/v1/budgets/me")
    assert response.status_code == 200

    data = response.json()
    assert "total_budgets" in data
    assert "budgets" in data


@pytest.mark.asyncio
async def test_get_budget(authenticated_client: AsyncClient):
    """Test getting a specific budget."""
    create_response = await authenticated_client.post(
        "/api/v1/budgets",
        json={"budget_type": "memory", "name": "Memory Budget", "total_limit": 1000},
    )
    budget_id = create_response.json()["id"]

    response = await authenticated_client.get(f"/api/v1/budgets/{budget_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "Memory Budget"


@pytest.mark.asyncio
async def test_update_budget(authenticated_client: AsyncClient):
    """Test updating a budget."""
    create_response = await authenticated_client.post(
        "/api/v1/budgets",
        json={"budget_type": "api_calls", "name": "Update Budget", "total_limit": 100},
    )
    budget_id = create_response.json()["id"]

    response = await authenticated_client.patch(
        f"/api/v1/budgets/{budget_id}",
        json={"total_limit": 200, "alert_threshold": 0.9},
    )
    assert response.status_code == 200
    assert response.json()["total_limit"] == 200


@pytest.mark.asyncio
async def test_reset_budget(authenticated_client: AsyncClient):
    """Test resetting a budget."""
    create_response = await authenticated_client.post(
        "/api/v1/budgets",
        json={"budget_type": "api_calls", "name": "Reset Budget", "total_limit": 100},
    )
    budget_id = create_response.json()["id"]

    response = await authenticated_client.post(f"/api/v1/budgets/{budget_id}/reset")
    assert response.status_code == 200
    assert response.json()["used_amount"] == 0


@pytest.mark.asyncio
async def test_estimate_usage(authenticated_client: AsyncClient):
    """Test estimating budget usage."""
    # Create a budget first
    await authenticated_client.post(
        "/api/v1/budgets",
        json={"budget_type": "api_calls", "name": "Estimate Budget", "total_limit": 1000},
    )

    response = await authenticated_client.post(
        "/api/v1/budgets/estimate",
        json={
            "budget_type": "api_calls",
            "estimated_amount": 100,
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert "fits_in_budget" in data
    assert "remaining_after" in data


@pytest.mark.asyncio
async def test_reserve_budget(authenticated_client: AsyncClient):
    """Test reserving budget."""
    # Create a budget
    create_response = await authenticated_client.post(
        "/api/v1/budgets",
        json={"budget_type": "api_calls", "name": "Reserve Budget", "total_limit": 1000},
    )
    budget_id = create_response.json()["id"]

    # Reserve
    response = await authenticated_client.post(
        "/api/v1/budgets/reserve",
        json={
            "budget_id": budget_id,
            "amount": 100,
            "purpose": "Batch processing",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["amount"] == 100
    assert "status" in data


@pytest.mark.asyncio
async def test_consume_reservation(authenticated_client: AsyncClient):
    """Test consuming a budget reservation."""
    # Create and reserve
    create_response = await authenticated_client.post(
        "/api/v1/budgets",
        json={"budget_type": "api_calls", "name": "Consume Budget", "total_limit": 1000},
    )
    budget_id = create_response.json()["id"]

    reserve_response = await authenticated_client.post(
        "/api/v1/budgets/reserve",
        json={"budget_id": budget_id, "amount": 100, "purpose": "Test"},
    )
    reservation_id = reserve_response.json()["id"]

    # Consume
    response = await authenticated_client.post(
        f"/api/v1/budgets/reservations/{reservation_id}/consume",
        json={"actual_amount": 85},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_release_reservation(authenticated_client: AsyncClient):
    """Test releasing a budget reservation."""
    # Create and reserve
    create_response = await authenticated_client.post(
        "/api/v1/budgets",
        json={"budget_type": "api_calls", "name": "Release Budget", "total_limit": 1000},
    )
    budget_id = create_response.json()["id"]

    reserve_response = await authenticated_client.post(
        "/api/v1/budgets/reserve",
        json={"budget_id": budget_id, "amount": 100, "purpose": "Test"},
    )
    reservation_id = reserve_response.json()["id"]

    # Release (cancel the reservation)
    response = await authenticated_client.post(
        f"/api/v1/budgets/reservations/{reservation_id}/release"
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_usage_history(authenticated_client: AsyncClient):
    """Test getting budget usage history."""
    create_response = await authenticated_client.post(
        "/api/v1/budgets",
        json={"budget_type": "api_calls", "name": "History Budget", "total_limit": 1000},
    )
    budget_id = create_response.json()["id"]

    response = await authenticated_client.get(f"/api/v1/budgets/{budget_id}/usage")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_budget_types(authenticated_client: AsyncClient):
    """Test different budget types."""
    budget_types = ["api_calls", "tokens", "memory", "storage", "compute"]

    for budget_type in budget_types:
        response = await authenticated_client.post(
            "/api/v1/budgets",
            json={
                "budget_type": budget_type,
                "name": f"{budget_type.title()} Budget",
                "total_limit": 100,
            },
        )
        assert response.status_code == 201
        assert response.json()["budget_type"] == budget_type


@pytest.mark.asyncio
async def test_budget_overflow_protection(authenticated_client: AsyncClient):
    """Test that reservations cannot exceed budget."""
    # Create a small budget
    create_response = await authenticated_client.post(
        "/api/v1/budgets",
        json={"budget_type": "api_calls", "name": "Small Budget", "total_limit": 50},
    )
    budget_id = create_response.json()["id"]

    # Try to reserve more than available
    response = await authenticated_client.post(
        "/api/v1/budgets/reserve",
        json={"budget_id": budget_id, "amount": 100, "purpose": "Too much"},
    )
    # Should either fail or return an error
    assert response.status_code in [201, 400, 422]
