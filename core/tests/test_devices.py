"""Tests for device gateway (robotics/IoT) functionality."""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from httpx import AsyncClient


# =============================================================================
# Device Registration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_register_device(authenticated_client: AsyncClient):
    """Test registering a new device."""
    response = await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": f"drone-{uuid4().hex[:8]}",
            "name": "Test Drone Alpha",
            "device_type": "drone",
            "protocol": "mavlink",
            "capabilities": ["fly", "hover", "camera"],
            "sensors": ["gps", "imu", "barometer", "camera"],
            "autonomy_level": "supervised",
            "connection_config": {
                "connection_string": "udp:127.0.0.1:14550"
            },
            "metadata": {
                "manufacturer": "TestCorp",
                "model": "DroneX1",
                "firmware_version": "2.1.0"
            }
        }
    )

    assert response.status_code in (200, 201), f"Failed: {response.text}"
    data = response.json()
    assert "id" in data
    assert data["name"] == "Test Drone Alpha"
    assert data["device_type"] == "drone"
    assert data["protocol"] == "mavlink"
    # capabilities is now in response
    assert "capabilities" in data
    assert "fly" in data["capabilities"]


@pytest.mark.asyncio
async def test_register_robot(authenticated_client: AsyncClient):
    """Test registering a ground robot."""
    response = await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": f"robot-{uuid4().hex[:8]}",
            "name": "Warehouse Bot",
            "device_type": "robot",
            "protocol": "mqtt",
            "capabilities": ["navigate", "pickup", "deliver"],
            "sensors": ["lidar", "camera", "ultrasonic"],
            "autonomy_level": "autonomous",
            "geofence": {
                "type": "rectangle",
                "bounds": {
                    "min_lat": 37.0,
                    "max_lat": 38.0,
                    "min_lon": -122.5,
                    "max_lon": -121.5
                }
            }
        }
    )

    assert response.status_code in (200, 201), f"Failed: {response.text}"
    data = response.json()
    assert data["device_type"] == "robot"
    # autonomy_level is now in response
    assert "autonomy_level" in data
    assert data["autonomy_level"] == "autonomous"


@pytest.mark.asyncio
async def test_register_sensor(authenticated_client: AsyncClient):
    """Test registering an IoT sensor."""
    response = await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": f"sensor-{uuid4().hex[:8]}",
            "name": "Temperature Sensor A1",
            "device_type": "sensor",
            "protocol": "mqtt",
            "sensors": ["temperature", "humidity"],
            "connection_config": {
                "broker": "mqtt://localhost:1883",
                "topic": "sensors/temp/a1"
            }
        }
    )

    assert response.status_code in (200, 201), f"Failed: {response.text}"
    data = response.json()
    assert data["device_type"] == "sensor"


# =============================================================================
# Device Listing & Query Tests
# =============================================================================

@pytest.mark.asyncio
async def test_list_devices(authenticated_client: AsyncClient):
    """Test listing registered devices."""
    # Register a device first
    device_id = f"list-test-{uuid4().hex[:8]}"
    await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "name": "List Test Device",
            "device_type": "sensor",
            "protocol": "http",
        }
    )

    # List devices
    response = await authenticated_client.get("/api/v1/devices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_filter_devices_by_type(authenticated_client: AsyncClient):
    """Test filtering devices by type."""
    # Register devices of different types
    for dtype in ["drone", "robot", "sensor"]:
        await authenticated_client.post(
            "/api/v1/devices/register",
            json={
                "device_id": f"filter-{dtype}-{uuid4().hex[:6]}",
                "name": f"Filter Test {dtype}",
                "device_type": dtype,
                "protocol": "mqtt",
            }
        )

    # Filter by drone type
    response = await authenticated_client.get("/api/v1/devices?device_type=drone")
    assert response.status_code == 200
    data = response.json()
    for device in data:
        assert device["device_type"] == "drone"


# =============================================================================
# Telemetry Tests
# =============================================================================

@pytest.mark.asyncio
async def test_send_telemetry(authenticated_client: AsyncClient):
    """Test sending telemetry data from a device with API key auth."""
    device_id = f"telem-{uuid4().hex[:8]}"

    # Register device
    await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "name": "Telemetry Test Device",
            "device_type": "drone",
            "protocol": "mavlink",
        }
    )

    # Generate device API key
    key_response = await authenticated_client.post(
        f"/api/v1/devices/{device_id}/api-key"
    )
    api_key = key_response.json()["api_key"]

    # Send telemetry with device API key
    response = await authenticated_client.post(
        f"/api/v1/devices/{device_id}/telemetry",
        json={
            "timestamp": datetime.utcnow().isoformat(),
            "latitude": 37.7749,
            "longitude": -122.4194,
            "altitude": 100.5,
            "heading": 45.0,
            "speed": 12.5,
            "battery_level": 85.0,
            "signal_strength": 95.0,
            "sensors": {
                "temperature": 22.5,
                "pressure": 1013.25
            }
        },
        headers={"Authorization": f"Bearer {api_key}"}
    )

    assert response.status_code in (200, 201), f"Failed: {response.text}"


@pytest.mark.asyncio
async def test_get_telemetry_history(authenticated_client: AsyncClient):
    """Test retrieving telemetry history."""
    device_id = f"history-{uuid4().hex[:8]}"

    # Register device
    await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "name": "History Test Device",
            "device_type": "drone",
            "protocol": "mavlink",
        }
    )

    # Generate device API key for telemetry submission
    key_response = await authenticated_client.post(
        f"/api/v1/devices/{device_id}/api-key"
    )
    api_key = key_response.json()["api_key"]

    # Send multiple telemetry points with device API key
    for i in range(5):
        await authenticated_client.post(
            f"/api/v1/devices/{device_id}/telemetry",
            json={
                "timestamp": (datetime.utcnow() - timedelta(minutes=i)).isoformat(),
                "latitude": 37.7749 + (i * 0.001),
                "longitude": -122.4194,
                "altitude": 100 + i,
                "battery_level": 90 - i,
            },
            headers={"Authorization": f"Bearer {api_key}"}
        )

    # Get history (uses agent auth, not device auth)
    start_time = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    response = await authenticated_client.get(
        f"/api/v1/devices/{device_id}/telemetry?start_time={start_time}"
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


# =============================================================================
# Command Tests
# =============================================================================

@pytest.mark.asyncio
async def test_send_command(authenticated_client: AsyncClient):
    """Test sending a command to a device."""
    device_id = f"cmd-{uuid4().hex[:8]}"

    # Register device
    await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "name": "Command Test Device",
            "device_type": "drone",
            "protocol": "http",  # Use HTTP to avoid MAVLink connection
        }
    )

    # Send command
    response = await authenticated_client.post(
        f"/api/v1/devices/{device_id}/commands",
        json={
            "command_type": "takeoff",
            "parameters": {"altitude": 50},
            "priority": "normal",
            "timeout_seconds": 30
        }
    )

    assert response.status_code in (200, 201), f"Failed: {response.text}"
    data = response.json()
    assert "command_id" in data
    assert "status" in data


@pytest.mark.asyncio
async def test_emergency_stop(authenticated_client: AsyncClient):
    """Test emergency stop command."""
    device_id = f"estop-{uuid4().hex[:8]}"

    # Register device
    await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "name": "E-Stop Test Device",
            "device_type": "drone",
            "protocol": "http",
        }
    )

    # Send emergency stop
    response = await authenticated_client.post(
        f"/api/v1/devices/{device_id}/emergency-stop"
    )

    assert response.status_code in (200, 201), f"Failed: {response.text}"
    data = response.json()
    assert "command_id" in data
    assert "status" in data


@pytest.mark.asyncio
async def test_return_to_base(authenticated_client: AsyncClient):
    """Test return to base command."""
    device_id = f"rtb-{uuid4().hex[:8]}"

    # Register device
    await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "name": "RTB Test Device",
            "device_type": "drone",
            "protocol": "http",
        }
    )

    # Send return to base
    response = await authenticated_client.post(
        f"/api/v1/devices/{device_id}/return-to-base"
    )

    assert response.status_code in (200, 201), f"Failed: {response.text}"
    data = response.json()
    assert "command_id" in data
    assert "status" in data


# =============================================================================
# Fleet Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_fleet(authenticated_client: AsyncClient):
    """Test creating a device fleet."""
    response = await authenticated_client.post(
        "/api/v1/devices/fleets",
        json={
            "name": "Delivery Fleet Alpha",
            "description": "Urban delivery drones",
            "coordination_mode": "coordinated",
            "geofence": {
                "type": "rectangle",
                "bounds": {
                    "min_lat": 37.7,
                    "max_lat": 37.8,
                    "min_lon": -122.5,
                    "max_lon": -122.3
                }
            }
        }
    )

    assert response.status_code in (200, 201), f"Failed: {response.text}"
    data = response.json()
    assert "id" in data
    assert data["name"] == "Delivery Fleet Alpha"
    assert data["coordination_mode"] == "coordinated"


@pytest.mark.asyncio
async def test_assign_device_to_fleet(authenticated_client: AsyncClient):
    """Test assigning a device to a fleet."""
    # Create fleet
    fleet_resp = await authenticated_client.post(
        "/api/v1/devices/fleets",
        json={
            "name": f"Assign Test Fleet {uuid4().hex[:6]}",
            "coordination_mode": "independent"
        }
    )
    fleet_id = fleet_resp.json()["id"]

    # Register device
    device_id = f"assign-{uuid4().hex[:8]}"
    await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "name": "Fleet Assignment Test",
            "device_type": "drone",
            "protocol": "mqtt",
        }
    )

    # Assign to fleet
    response = await authenticated_client.post(
        f"/api/v1/devices/{device_id}/assign-fleet/{fleet_id}"
    )

    assert response.status_code == 200, f"Failed: {response.text}"


@pytest.mark.asyncio
async def test_fleet_emergency_stop(authenticated_client: AsyncClient):
    """Test fleet-wide emergency stop."""
    # Create fleet
    fleet_resp = await authenticated_client.post(
        "/api/v1/devices/fleets",
        json={
            "name": f"Fleet E-Stop Test {uuid4().hex[:6]}",
            "coordination_mode": "swarm"
        }
    )
    fleet_id = fleet_resp.json()["id"]

    # Register and assign devices
    for i in range(3):
        device_id = f"fleet-drone-{i}-{uuid4().hex[:6]}"
        await authenticated_client.post(
            "/api/v1/devices/register",
            json={
                "device_id": device_id,
                "name": f"Fleet Drone {i}",
                "device_type": "drone",
                "protocol": "http",
                "fleet_id": fleet_id,
            }
        )

    # Fleet emergency stop
    response = await authenticated_client.post(
        f"/api/v1/devices/fleets/{fleet_id}/emergency-stop"
    )

    assert response.status_code == 200, f"Failed: {response.text}"


# =============================================================================
# Mission Tests
# =============================================================================

@pytest.mark.asyncio
async def test_create_mission(authenticated_client: AsyncClient):
    """Test creating a mission with waypoints."""
    # Register device
    device_id = f"mission-{uuid4().hex[:8]}"
    await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "name": "Mission Test Drone",
            "device_type": "drone",
            "protocol": "mavlink",
        }
    )

    # Create mission
    response = await authenticated_client.post(
        "/api/v1/devices/missions",
        json={
            "name": "Delivery Route A",
            "mission_type": "delivery",
            "device_ids": [device_id],
            "waypoints": [
                {"latitude": 37.7749, "longitude": -122.4194, "altitude": 50},
                {"latitude": 37.7849, "longitude": -122.4094, "altitude": 50},
                {"latitude": 37.7949, "longitude": -122.3994, "altitude": 50},
            ],
            "parameters": {
                "speed": 10,
                "hover_time": 5
            }
        }
    )

    assert response.status_code in (200, 201), f"Failed: {response.text}"
    data = response.json()
    assert "id" in data
    assert data["name"] == "Delivery Route A"
    assert len(data["waypoints"]) == 3


# =============================================================================
# Event Tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_device_events(authenticated_client: AsyncClient):
    """Test retrieving device events."""
    device_id = f"events-{uuid4().hex[:8]}"

    # Register device
    await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "name": "Events Test Device",
            "device_type": "drone",
            "protocol": "mqtt",
        }
    )

    # Generate device API key for telemetry submission
    key_response = await authenticated_client.post(
        f"/api/v1/devices/{device_id}/api-key"
    )
    api_key = key_response.json()["api_key"]

    # Send low battery telemetry to trigger event
    await authenticated_client.post(
        f"/api/v1/devices/{device_id}/telemetry",
        json={
            "timestamp": datetime.utcnow().isoformat(),
            "latitude": 37.7749,
            "longitude": -122.4194,
            "battery_level": 15.0,  # Low battery triggers event
        },
        headers={"Authorization": f"Bearer {api_key}"}
    )

    # Get events
    response = await authenticated_client.get(
        f"/api/v1/devices/{device_id}/events"
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Should have a low_battery event
    low_battery_events = [e for e in data if e.get("event_type") == "low_battery"]
    assert len(low_battery_events) > 0, "Expected low_battery event"


# =============================================================================
# Geofence Tests
# =============================================================================

@pytest.mark.asyncio
async def test_geofence_breach_detection(authenticated_client: AsyncClient):
    """Test that geofence breaches are detected."""
    device_id = f"geofence-{uuid4().hex[:8]}"

    # Register device with geofence
    await authenticated_client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            "name": "Geofence Test Drone",
            "device_type": "drone",
            "protocol": "mqtt",
            "geofence": {
                "type": "rectangle",
                "bounds": {
                    "min_lat": 37.0,
                    "max_lat": 38.0,
                    "min_lon": -123.0,
                    "max_lon": -122.0
                }
            }
        }
    )

    # Generate device API key for telemetry submission
    key_response = await authenticated_client.post(
        f"/api/v1/devices/{device_id}/api-key"
    )
    api_key = key_response.json()["api_key"]

    # Send telemetry outside geofence using device API key
    telemetry_response = await authenticated_client.post(
        f"/api/v1/devices/{device_id}/telemetry",
        json={
            "timestamp": datetime.utcnow().isoformat(),
            "latitude": 40.0,  # Outside geofence
            "longitude": -122.5,
            "altitude": 100,
        },
        headers={"Authorization": f"Bearer {api_key}"}
    )
    assert telemetry_response.status_code in (200, 201), f"Telemetry failed: {telemetry_response.text}"

    # Check for geofence breach event
    response = await authenticated_client.get(
        f"/api/v1/devices/{device_id}/events"
    )

    assert response.status_code == 200
    events = response.json()
    # Should have a geofence_breach event
    breach_events = [e for e in events if e.get("event_type") == "geofence_breach"]
    assert len(breach_events) > 0, "Expected geofence breach event"


# =============================================================================
# Protocol Tests
# =============================================================================

@pytest.mark.asyncio
async def test_device_protocols_supported(authenticated_client: AsyncClient):
    """Test that all device protocols can be registered."""
    protocols = ["mqtt", "mavlink", "modbus", "http", "websocket"]

    for protocol in protocols:
        response = await authenticated_client.post(
            "/api/v1/devices/register",
            json={
                "device_id": f"proto-{protocol}-{uuid4().hex[:6]}",
                "name": f"Protocol Test {protocol}",
                "device_type": "sensor",
                "protocol": protocol,
            }
        )
        assert response.status_code in (200, 201), f"Failed for {protocol}: {response.text}"


@pytest.mark.asyncio
async def test_device_types_supported(authenticated_client: AsyncClient):
    """Test that all device types can be registered."""
    device_types = ["drone", "robot", "vehicle", "sensor", "camera", "actuator", "gateway", "industrial"]

    for dtype in device_types:
        response = await authenticated_client.post(
            "/api/v1/devices/register",
            json={
                "device_id": f"type-{dtype}-{uuid4().hex[:6]}",
                "name": f"Type Test {dtype}",
                "device_type": dtype,
                "protocol": "mqtt",
            }
        )
        assert response.status_code in (200, 201), f"Failed for {dtype}: {response.text}"
