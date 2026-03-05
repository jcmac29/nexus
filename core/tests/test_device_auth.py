"""Integration tests for device API key authentication."""

import pytest
from uuid import uuid4
from datetime import datetime
from httpx import AsyncClient


@pytest.fixture
def device_data():
    """Sample device registration data."""
    return {
        "device_id": f"sensor-{uuid4().hex[:8]}",
        "name": "Temperature Sensor Alpha",
        "device_type": "sensor",
        "protocol": "mqtt",
        "capabilities": ["temperature", "humidity"],
        "sensors": ["dht22"],
    }


class TestDeviceAPIKeyManagement:
    """Test device API key lifecycle."""

    async def test_generate_device_api_key(self, client: AsyncClient, auth_headers: dict, device_data: dict):
        """Test generating an API key for a device."""
        # Register device
        reg_response = await client.post(
            "/api/v1/devices/register",
            json=device_data,
            headers=auth_headers,
        )
        assert reg_response.status_code == 200
        device_id = device_data["device_id"]

        # Generate API key
        response = await client.post(
            f"/api/v1/devices/{device_id}/api-key",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert "api_key" in data
        assert data["api_key"].startswith("nex_dev_")
        assert data["device_id"] == device_id
        assert "message" in data  # Warning to store securely

    async def test_device_shows_has_api_key(self, client: AsyncClient, auth_headers: dict, device_data: dict):
        """Test that device details show API key status."""
        # Register device
        await client.post(
            "/api/v1/devices/register",
            json=device_data,
            headers=auth_headers,
        )
        device_id = device_data["device_id"]

        # Check device before API key
        response1 = await client.get(
            f"/api/v1/devices/{device_id}",
            headers=auth_headers,
        )
        assert response1.status_code == 200
        assert response1.json().get("has_api_key") == False

        # Generate API key
        await client.post(
            f"/api/v1/devices/{device_id}/api-key",
            headers=auth_headers,
        )

        # Check device after API key
        response2 = await client.get(
            f"/api/v1/devices/{device_id}",
            headers=auth_headers,
        )
        assert response2.status_code == 200
        assert response2.json().get("has_api_key") == True

    async def test_revoke_device_api_key(self, client: AsyncClient, auth_headers: dict, device_data: dict):
        """Test revoking a device API key."""
        # Register and generate key
        await client.post(
            "/api/v1/devices/register",
            json=device_data,
            headers=auth_headers,
        )
        device_id = device_data["device_id"]
        await client.post(
            f"/api/v1/devices/{device_id}/api-key",
            headers=auth_headers,
        )

        # Revoke key
        response = await client.delete(
            f"/api/v1/devices/{device_id}/api-key",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["revoked"] == True

        # Verify device no longer has key
        device_response = await client.get(
            f"/api/v1/devices/{device_id}",
            headers=auth_headers,
        )
        assert device_response.json().get("has_api_key") == False

    async def test_rotate_device_api_key(self, client: AsyncClient, auth_headers: dict, device_data: dict):
        """Test rotating a device API key."""
        # Register and generate initial key
        await client.post(
            "/api/v1/devices/register",
            json=device_data,
            headers=auth_headers,
        )
        device_id = device_data["device_id"]
        key_response1 = await client.post(
            f"/api/v1/devices/{device_id}/api-key",
            headers=auth_headers,
        )
        old_key = key_response1.json()["api_key"]

        # Rotate key
        rotate_response = await client.post(
            f"/api/v1/devices/{device_id}/api-key/rotate",
            headers=auth_headers,
        )
        assert rotate_response.status_code == 200
        new_key = rotate_response.json()["api_key"]

        # Keys should be different
        assert new_key != old_key
        assert new_key.startswith("nex_dev_")


class TestDeviceAPIKeyAuthentication:
    """Test device authentication using API keys."""

    async def test_telemetry_with_api_key_bearer(self, client: AsyncClient, auth_headers: dict, device_data: dict):
        """Test submitting telemetry with API key in Authorization header."""
        # Register and get API key
        await client.post(
            "/api/v1/devices/register",
            json=device_data,
            headers=auth_headers,
        )
        device_id = device_data["device_id"]
        key_response = await client.post(
            f"/api/v1/devices/{device_id}/api-key",
            headers=auth_headers,
        )
        api_key = key_response.json()["api_key"]

        # Submit telemetry with API key
        response = await client.post(
            f"/api/v1/devices/{device_id}/telemetry",
            json={
                "timestamp": datetime.utcnow().isoformat(),
                "latitude": 37.7749,
                "longitude": -122.4194,
                "battery_level": 85.0,
                "sensors": {"temperature": 22.5, "humidity": 45.0},
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 200
        assert response.json()["received"] == True

    async def test_telemetry_multiple_submissions(self, client: AsyncClient, auth_headers: dict, device_data: dict):
        """Test submitting multiple telemetry readings."""
        # Register and get API key
        await client.post(
            "/api/v1/devices/register",
            json=device_data,
            headers=auth_headers,
        )
        device_id = device_data["device_id"]
        key_response = await client.post(
            f"/api/v1/devices/{device_id}/api-key",
            headers=auth_headers,
        )
        api_key = key_response.json()["api_key"]

        # Submit multiple telemetry readings
        for i in range(3):
            response = await client.post(
                f"/api/v1/devices/{device_id}/telemetry",
                json={
                    "timestamp": datetime.utcnow().isoformat(),
                    "sensors": {"temperature": 20 + i, "pressure": 1013.25 + i},
                    "battery_level": 100 - (i * 5),
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            assert response.status_code == 200
            assert response.json()["received"] == True

    async def test_telemetry_with_invalid_api_key(self, client: AsyncClient, auth_headers: dict, device_data: dict):
        """Test that invalid API key is rejected."""
        # Register device
        await client.post(
            "/api/v1/devices/register",
            json=device_data,
            headers=auth_headers,
        )
        device_id = device_data["device_id"]

        # Submit telemetry with invalid API key
        response = await client.post(
            f"/api/v1/devices/{device_id}/telemetry",
            json={
                "timestamp": datetime.utcnow().isoformat(),
                "sensors": {"temperature": 25.0},
            },
            headers={"Authorization": "Bearer nex_dev_invalid_key_12345"},
        )
        assert response.status_code == 401

    async def test_telemetry_with_wrong_device_api_key(self, client: AsyncClient, auth_headers: dict):
        """Test that API key for different device is rejected."""
        # Register two devices
        device1_id = f"device1-{uuid4().hex[:8]}"
        device2_id = f"device2-{uuid4().hex[:8]}"

        await client.post(
            "/api/v1/devices/register",
            json={
                "device_id": device1_id,
                "name": "Device 1",
                "device_type": "sensor",
            },
            headers=auth_headers,
        )
        await client.post(
            "/api/v1/devices/register",
            json={
                "device_id": device2_id,
                "name": "Device 2",
                "device_type": "sensor",
            },
            headers=auth_headers,
        )

        # Get API key for device 1
        key_response = await client.post(
            f"/api/v1/devices/{device1_id}/api-key",
            headers=auth_headers,
        )
        device1_key = key_response.json()["api_key"]

        # Try to use device1's key for device2's telemetry
        response = await client.post(
            f"/api/v1/devices/{device2_id}/telemetry",
            json={
                "timestamp": datetime.utcnow().isoformat(),
                "sensors": {"temperature": 25.0},
            },
            headers={"Authorization": f"Bearer {device1_key}"},
        )
        assert response.status_code == 403

    async def test_revoked_key_rejected(self, client: AsyncClient, auth_headers: dict, device_data: dict):
        """Test that revoked API key is rejected."""
        # Register and get API key
        await client.post(
            "/api/v1/devices/register",
            json=device_data,
            headers=auth_headers,
        )
        device_id = device_data["device_id"]
        key_response = await client.post(
            f"/api/v1/devices/{device_id}/api-key",
            headers=auth_headers,
        )
        api_key = key_response.json()["api_key"]

        # Revoke the key
        await client.delete(
            f"/api/v1/devices/{device_id}/api-key",
            headers=auth_headers,
        )

        # Try to use revoked key
        response = await client.post(
            f"/api/v1/devices/{device_id}/telemetry",
            json={
                "timestamp": datetime.utcnow().isoformat(),
                "sensors": {"temperature": 25.0},
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert response.status_code == 401


class TestDeviceAPIKeySecurity:
    """Test security aspects of device API keys."""

    async def test_api_key_management_requires_owner_auth(self, client: AsyncClient, device_data: dict):
        """Test that API key management requires agent authentication."""
        # Try to generate key without auth
        response = await client.post(
            f"/api/v1/devices/test-device/api-key",
        )
        assert response.status_code == 401

    async def test_api_key_only_shown_once(self, client: AsyncClient, auth_headers: dict, device_data: dict):
        """Test that API key is only returned on generation, not on device GET."""
        # Register and generate key
        await client.post(
            "/api/v1/devices/register",
            json=device_data,
            headers=auth_headers,
        )
        device_id = device_data["device_id"]
        await client.post(
            f"/api/v1/devices/{device_id}/api-key",
            headers=auth_headers,
        )

        # Get device details - should not include the key
        response = await client.get(
            f"/api/v1/devices/{device_id}",
            headers=auth_headers,
        )
        data = response.json()
        assert "api_key" not in data
        assert "api_key_hash" not in data
        assert data.get("has_api_key") == True

    async def test_different_devices_get_different_keys(self, client: AsyncClient, auth_headers: dict):
        """Test that each device gets a unique API key."""
        keys = []
        for i in range(3):
            device_id = f"unique-device-{uuid4().hex[:8]}"
            await client.post(
                "/api/v1/devices/register",
                json={
                    "device_id": device_id,
                    "name": f"Device {i}",
                    "device_type": "sensor",
                },
                headers=auth_headers,
            )
            key_response = await client.post(
                f"/api/v1/devices/{device_id}/api-key",
                headers=auth_headers,
            )
            keys.append(key_response.json()["api_key"])

        # All keys should be unique
        assert len(set(keys)) == 3
