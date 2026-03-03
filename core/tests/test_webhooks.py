"""Tests for webhooks module."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_webhook(authenticated_client: AsyncClient):
    """Test creating a webhook endpoint."""
    response = await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "Test Webhook",
            "url": "https://example.com/webhook",
            "event_types": ["memory.created", "memory.updated"],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Test Webhook"
    assert data["url"] == "https://example.com/webhook"
    assert "memory.created" in data["event_types"]
    assert "secret" in data  # Secret should be returned on creation
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_webhook_with_options(authenticated_client: AsyncClient):
    """Test creating a webhook with custom options."""
    response = await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "Custom Webhook",
            "url": "https://example.com/hook",
            "event_types": ["agent.*"],
            "retry_policy": "linear",
            "max_retries": 3,
            "timeout_seconds": 60,
            "custom_headers": {"X-Custom-Header": "value"},
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["retry_policy"] == "linear"
    assert data["max_retries"] == 3
    assert data["timeout_seconds"] == 60


@pytest.mark.asyncio
async def test_list_webhooks(authenticated_client: AsyncClient):
    """Test listing webhooks."""
    # Create a webhook first
    await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "List Test Webhook",
            "url": "https://example.com/list-test",
            "event_types": ["memory.*"],
        },
    )

    response = await authenticated_client.get("/api/v1/webhooks")
    assert response.status_code == 200

    data = response.json()
    assert "webhooks" in data
    assert len(data["webhooks"]) >= 1


@pytest.mark.asyncio
async def test_get_webhook(authenticated_client: AsyncClient):
    """Test retrieving a single webhook."""
    # Create webhook
    create_response = await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "Get Test Webhook",
            "url": "https://example.com/get-test",
            "event_types": ["memory.created"],
        },
    )
    webhook_id = create_response.json()["id"]

    # Get webhook
    response = await authenticated_client.get(f"/api/v1/webhooks/{webhook_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == webhook_id
    assert data["name"] == "Get Test Webhook"


@pytest.mark.asyncio
async def test_update_webhook(authenticated_client: AsyncClient):
    """Test updating a webhook."""
    # Create webhook
    create_response = await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "Update Test Webhook",
            "url": "https://example.com/update-test",
            "event_types": ["memory.created"],
        },
    )
    webhook_id = create_response.json()["id"]

    # Update webhook
    response = await authenticated_client.patch(
        f"/api/v1/webhooks/{webhook_id}",
        json={
            "name": "Updated Webhook",
            "is_active": False,
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "Updated Webhook"
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_delete_webhook(authenticated_client: AsyncClient):
    """Test deleting a webhook."""
    # Create webhook
    create_response = await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "Delete Test Webhook",
            "url": "https://example.com/delete-test",
            "event_types": ["memory.deleted"],
        },
    )
    webhook_id = create_response.json()["id"]

    # Delete webhook
    response = await authenticated_client.delete(f"/api/v1/webhooks/{webhook_id}")
    assert response.status_code == 200

    # Verify deleted
    get_response = await authenticated_client.get(f"/api/v1/webhooks/{webhook_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_test_webhook(authenticated_client: AsyncClient):
    """Test sending a test ping to a webhook."""
    # Create webhook
    create_response = await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "Ping Test Webhook",
            "url": "https://httpbin.org/post",  # Use httpbin for testing
            "event_types": ["test.ping"],
        },
    )
    webhook_id = create_response.json()["id"]

    # Send test ping
    response = await authenticated_client.post(f"/api/v1/webhooks/{webhook_id}/test")
    assert response.status_code == 200

    data = response.json()
    assert "delivery_id" in data


@pytest.mark.asyncio
async def test_rotate_webhook_secret(authenticated_client: AsyncClient):
    """Test rotating a webhook's secret."""
    # Create webhook
    create_response = await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "Rotate Test Webhook",
            "url": "https://example.com/rotate-test",
            "event_types": ["memory.*"],
        },
    )
    webhook_id = create_response.json()["id"]
    original_secret = create_response.json()["secret"]

    # Rotate secret
    response = await authenticated_client.post(
        f"/api/v1/webhooks/{webhook_id}/rotate-secret"
    )
    assert response.status_code == 200

    data = response.json()
    assert "secret" in data
    assert data["secret"] != original_secret


@pytest.mark.asyncio
async def test_list_webhook_deliveries(authenticated_client: AsyncClient):
    """Test listing webhook delivery logs."""
    # Create webhook
    create_response = await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "Deliveries Test Webhook",
            "url": "https://httpbin.org/post",
            "event_types": ["test.*"],
        },
    )
    webhook_id = create_response.json()["id"]

    # Trigger a test delivery
    await authenticated_client.post(f"/api/v1/webhooks/{webhook_id}/test")

    # List deliveries
    response = await authenticated_client.get(
        f"/api/v1/webhooks/{webhook_id}/deliveries"
    )
    assert response.status_code == 200

    data = response.json()
    assert "deliveries" in data


@pytest.mark.asyncio
async def test_webhook_url_validation(authenticated_client: AsyncClient):
    """Test that invalid webhook URLs are rejected."""
    response = await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "Invalid URL Webhook",
            "url": "not-a-valid-url",
            "event_types": ["memory.*"],
        },
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_webhook_wildcard_events(authenticated_client: AsyncClient):
    """Test webhook with wildcard event patterns."""
    response = await authenticated_client.post(
        "/api/v1/webhooks",
        json={
            "name": "Wildcard Webhook",
            "url": "https://example.com/wildcard",
            "event_types": ["memory.*", "agent.*", "capability.*"],
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["event_types"]) == 3
