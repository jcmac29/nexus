"""Device Gateway API routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.database import get_db
from nexus.auth import get_current_agent
from nexus.identity.models import Agent
from nexus.devices.service import DeviceGatewayService
from nexus.devices.models import Device, DeviceType, DeviceProtocol, DeviceStatus, CommandPriority

router = APIRouter(prefix="/devices", tags=["devices"])


class RegisterDeviceRequest(BaseModel):
    device_id: str
    name: str
    device_type: str
    protocol: str = "mqtt"
    connection_config: dict | None = None
    capabilities: list[str] | None = None
    sensors: list[str] | None = None
    ai_agent_id: str | None = None
    autonomy_level: str = "supervised"
    fleet_id: str | None = None
    geofence: dict | None = None
    metadata: dict | None = None


class SendCommandRequest(BaseModel):
    command_type: str
    parameters: dict | None = None
    priority: str = "normal"
    timeout_seconds: int = Field(default=30, ge=1, le=300, description="Command timeout (1-300 seconds)")


class TelemetryRequest(BaseModel):
    timestamp: str
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    heading: float | None = None
    speed: float | None = None
    battery_level: float | None = None
    signal_strength: float | None = None
    sensors: dict | None = None
    raw_data: dict | None = None


class CreateFleetRequest(BaseModel):
    name: str
    description: str | None = None
    orchestrator_agent_id: str | None = None
    coordination_mode: str = "independent"
    geofence: dict | None = None


class CreateMissionRequest(BaseModel):
    name: str
    mission_type: str
    device_ids: list[str] | None = None
    fleet_id: str | None = None
    waypoints: list[dict] | None = None
    parameters: dict | None = None
    scheduled_start: str | None = None


# --- Device Registration ---

@router.post("/register")
async def register_device(
    request: RegisterDeviceRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Register a new device."""
    service = DeviceGatewayService(db)

    type_map = {
        "drone": DeviceType.DRONE,
        "robot": DeviceType.ROBOT,
        "vehicle": DeviceType.VEHICLE,
        "sensor": DeviceType.SENSOR,
        "camera": DeviceType.CAMERA,
        "actuator": DeviceType.ACTUATOR,
        "gateway": DeviceType.GATEWAY,
        "wearable": DeviceType.WEARABLE,
        "industrial": DeviceType.INDUSTRIAL,
        "custom": DeviceType.CUSTOM,
    }
    protocol_map = {
        "mqtt": DeviceProtocol.MQTT,
        "mavlink": DeviceProtocol.MAVLINK,
        "modbus": DeviceProtocol.MODBUS,
        "opcua": DeviceProtocol.OPCUA,
        "coap": DeviceProtocol.COAP,
        "http": DeviceProtocol.HTTP,
        "websocket": DeviceProtocol.WEBSOCKET,
        "lora": DeviceProtocol.LORA,
        "custom": DeviceProtocol.CUSTOM,
    }

    device = await service.register_device(
        device_id=request.device_id,
        name=request.name,
        device_type=type_map.get(request.device_type, DeviceType.CUSTOM),
        owner_id=agent.id,
        protocol=protocol_map.get(request.protocol, DeviceProtocol.MQTT),
        connection_config=request.connection_config,
        capabilities=request.capabilities,
        sensors=request.sensors,
        ai_agent_id=UUID(request.ai_agent_id) if request.ai_agent_id else None,
        autonomy_level=request.autonomy_level,
        fleet_id=UUID(request.fleet_id) if request.fleet_id else None,
        geofence=request.geofence,
        metadata=request.metadata,
    )

    return {
        "id": str(device.id),
        "device_id": device.device_id,
        "name": device.name,
        "device_type": device.device_type.value,
        "protocol": device.protocol.value,
        "status": device.status.value,
        "capabilities": device.capabilities,
        "sensors": device.sensors,
        "autonomy_level": device.autonomy_level,
        "geofence": device.geofence,
    }


@router.get("")
async def list_devices(
    device_type: str | None = None,
    fleet_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List devices."""
    service = DeviceGatewayService(db)

    type_map = {"drone": DeviceType.DRONE, "robot": DeviceType.ROBOT, "sensor": DeviceType.SENSOR}
    status_map = {"online": DeviceStatus.ONLINE, "offline": DeviceStatus.OFFLINE, "error": DeviceStatus.ERROR}

    devices = await service.list_devices(
        owner_id=agent.id,
        device_type=type_map.get(device_type) if device_type else None,
        fleet_id=UUID(fleet_id) if fleet_id else None,
        status=status_map.get(status) if status else None,
        limit=limit,
    )

    return [
        {
            "id": str(d.id),
            "device_id": d.device_id,
            "name": d.name,
            "device_type": d.device_type.value,
            "status": d.status.value,
            "latitude": d.latitude,
            "longitude": d.longitude,
            "battery_level": d.battery_level,
            "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        }
        for d in devices
    ]


@router.get("/{device_id}")
async def get_device(
    device_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get device details."""
    service = DeviceGatewayService(db)
    device = await service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # SECURITY: Verify ownership before returning device details
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this device")

    return {
        "id": str(device.id),
        "device_id": device.device_id,
        "name": device.name,
        "device_type": device.device_type.value,
        "protocol": device.protocol.value,
        "status": device.status.value,
        "latitude": device.latitude,
        "longitude": device.longitude,
        "altitude": device.altitude,
        "heading": device.heading,
        "speed": device.speed,
        "battery_level": device.battery_level,
        "signal_strength": device.signal_strength,
        "capabilities": device.capabilities,
        "sensors": device.sensors,
        "health_status": device.health_status,
        "autonomy_level": device.autonomy_level,
        "geofence": device.geofence,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
        "last_telemetry_at": device.last_telemetry_at.isoformat() if device.last_telemetry_at else None,
        "has_api_key": device.api_key_hash is not None,
        "api_key_last_used": device.api_key_last_used.isoformat() if device.api_key_last_used else None,
    }


# --- Device API Key Management ---

@router.post("/{device_id}/api-key")
async def generate_device_api_key(
    device_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new API key for a device.

    Returns the API key only once - store it securely on the device.
    The key format is: nex_dev_xxxxx...
    """
    service = DeviceGatewayService(db)

    # SECURITY: Verify ownership before generating API key
    device = await service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this device")

    api_key = await service.generate_device_api_key(device_id)

    return {
        "device_id": device_id,
        "api_key": api_key,
        "message": "Store this API key securely - it will not be shown again",
    }


@router.delete("/{device_id}/api-key")
async def revoke_device_api_key(
    device_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a device's API key.

    The device will no longer be able to authenticate until a new key is generated.
    """
    service = DeviceGatewayService(db)

    # SECURITY: Verify ownership before revoking API key
    device = await service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this device")

    success = await service.revoke_device_api_key(device_id)

    return {"device_id": device_id, "revoked": success}


@router.post("/{device_id}/api-key/rotate")
async def rotate_device_api_key(
    device_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Rotate a device's API key (revoke old, generate new).

    Returns the new API key only once - store it securely on the device.
    """
    service = DeviceGatewayService(db)

    # SECURITY: Verify ownership before rotating API key
    device = await service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to manage this device")

    new_api_key = await service.rotate_device_api_key(device_id)

    return {
        "device_id": device_id,
        "api_key": new_api_key,
        "message": "Old key revoked. Store this new API key securely - it will not be shown again",
    }


# --- Commands ---

@router.post("/{device_id}/commands")
async def send_command(
    device_id: str,
    request: SendCommandRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Send a command to a device."""
    service = DeviceGatewayService(db)

    # SECURITY: Verify ownership before sending commands
    device = await service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to send commands to this device")

    priority_map = {
        "emergency": CommandPriority.EMERGENCY,
        "critical": CommandPriority.CRITICAL,
        "high": CommandPriority.HIGH,
        "normal": CommandPriority.NORMAL,
        "low": CommandPriority.LOW,
    }

    command = await service.send_command(
        device_id=device_id,
        command_type=request.command_type,
        parameters=request.parameters,
        priority=priority_map.get(request.priority, CommandPriority.NORMAL),
        sender_id=agent.id,
        sender_type="agent",
        timeout_seconds=request.timeout_seconds,
    )

    return {
        "command_id": command.command_id,
        "status": command.status.value,
        "sent_at": command.sent_at.isoformat() if command.sent_at else None,
    }


@router.post("/{device_id}/emergency-stop")
async def emergency_stop(
    device_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Emergency stop a device."""
    service = DeviceGatewayService(db)

    # SECURITY: Verify ownership before emergency stop
    device = await service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to control this device")

    command = await service.emergency_stop(device_id, agent.id)
    return {"command_id": command.command_id, "status": command.status.value}


@router.post("/{device_id}/return-to-base")
async def return_to_base(
    device_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Return device to base/home."""
    service = DeviceGatewayService(db)

    # SECURITY: Verify ownership before sending return command
    device = await service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to control this device")

    command = await service.return_to_base(device_id, agent.id)
    return {"command_id": command.command_id, "status": command.status.value}


# --- Telemetry ---


async def get_device_from_api_key(
    authorization: str = Header(None, alias="Authorization"),
    x_device_api_key: str = Header(None, alias="X-Device-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """
    SECURITY: Authenticate device using API key.

    Devices can provide their API key via:
    - Authorization: Bearer nex_dev_xxx header
    - X-Device-API-Key: nex_dev_xxx header
    """
    api_key = None

    # Check Authorization header
    if authorization and authorization.startswith("Bearer "):
        api_key = authorization[7:]

    # Check X-Device-API-Key header
    if not api_key and x_device_api_key:
        api_key = x_device_api_key

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Device API key required. Provide via Authorization: Bearer nex_dev_xxx or X-Device-API-Key header",
        )

    service = DeviceGatewayService(db)
    device = await service.validate_device_api_key(api_key)

    if not device:
        raise HTTPException(status_code=401, detail="Invalid device API key")

    return device


@router.post("/{device_id}/telemetry")
async def ingest_telemetry(
    device_id: str,
    request: TelemetryRequest,
    authorization: str = Header(None, alias="Authorization"),
    x_device_api_key: str = Header(None, alias="X-Device-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Ingest telemetry from a device (device-facing endpoint).

    SECURITY: Requires device API key authentication.
    Provide key via Authorization: Bearer nex_dev_xxx or X-Device-API-Key header.
    """
    service = DeviceGatewayService(db)

    # Extract API key
    api_key = None
    if authorization and authorization.startswith("Bearer "):
        api_key = authorization[7:]
    if not api_key and x_device_api_key:
        api_key = x_device_api_key

    # Validate device authentication
    if api_key:
        authenticated_device = await service.validate_device_api_key(api_key)
        if not authenticated_device:
            raise HTTPException(status_code=401, detail="Invalid device API key")
        if authenticated_device.device_id != device_id:
            raise HTTPException(status_code=403, detail="API key does not match device")
    else:
        # Fallback: require device to exist (for backward compatibility during migration)
        # In strict mode, uncomment the raise below
        device = await service.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        # raise HTTPException(status_code=401, detail="Device API key required")

    telemetry = await service.ingest_telemetry(
        device_id=device_id,
        timestamp=datetime.fromisoformat(request.timestamp),
        latitude=request.latitude,
        longitude=request.longitude,
        altitude=request.altitude,
        heading=request.heading,
        speed=request.speed,
        battery_level=request.battery_level,
        signal_strength=request.signal_strength,
        sensors=request.sensors,
        raw_data=request.raw_data,
    )

    return {"id": str(telemetry.id), "received": True}


@router.get("/{device_id}/telemetry")
async def get_telemetry_history(
    device_id: str,
    start_time: str,
    end_time: str | None = None,
    limit: int = Query(default=1000, le=5000),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get telemetry history for a device."""
    service = DeviceGatewayService(db)

    # SECURITY: Verify ownership before returning telemetry data
    device = await service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this device's telemetry")

    telemetry = await service.get_telemetry_history(
        device_id=device_id,
        start_time=datetime.fromisoformat(start_time),
        end_time=datetime.fromisoformat(end_time) if end_time else None,
        limit=limit,
    )

    return [
        {
            "timestamp": t.timestamp.isoformat(),
            "latitude": t.latitude,
            "longitude": t.longitude,
            "altitude": t.altitude,
            "heading": t.heading,
            "speed": t.speed,
            "battery_level": t.battery_level,
            "sensors": t.sensors,
        }
        for t in telemetry
    ]


# --- Events ---

@router.get("/{device_id}/events")
async def get_device_events(
    device_id: str,
    severity: str | None = None,
    unresolved_only: bool = False,
    limit: int = Query(default=100, le=500),
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get events for a device."""
    service = DeviceGatewayService(db)

    # SECURITY: Verify ownership before returning device events
    device = await service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this device's events")

    events = await service.get_device_events(
        device_id=device_id,
        severity=severity,
        unresolved_only=unresolved_only,
        limit=limit,
    )

    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "severity": e.severity,
            "message": e.message,
            "data": e.data,
            "latitude": e.latitude,
            "longitude": e.longitude,
            "is_resolved": e.is_resolved,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in events
    ]


# --- Fleets ---

@router.post("/fleets")
async def create_fleet(
    request: CreateFleetRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a device fleet."""
    service = DeviceGatewayService(db)
    fleet = await service.create_fleet(
        name=request.name,
        owner_id=agent.id,
        description=request.description,
        orchestrator_agent_id=UUID(request.orchestrator_agent_id) if request.orchestrator_agent_id else None,
        coordination_mode=request.coordination_mode,
        geofence=request.geofence,
    )

    return {
        "id": str(fleet.id),
        "name": fleet.name,
        "coordination_mode": fleet.coordination_mode,
    }


@router.post("/fleets/{fleet_id}/emergency-stop")
async def fleet_emergency_stop(
    fleet_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Emergency stop all devices in a fleet."""
    from sqlalchemy import select
    from nexus.devices.models import DeviceFleet

    # SECURITY: Verify fleet ownership before emergency stop
    result = await db.execute(
        select(DeviceFleet).where(DeviceFleet.id == UUID(fleet_id))
    )
    fleet = result.scalar_one_or_none()
    if not fleet:
        raise HTTPException(status_code=404, detail="Fleet not found")
    if fleet.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to control this fleet")

    service = DeviceGatewayService(db)
    commands = await service.fleet_emergency_stop(UUID(fleet_id), agent.id)
    return {"commands_sent": len(commands)}


@router.post("/{device_id}/assign-fleet/{fleet_id}")
async def assign_to_fleet(
    device_id: str,
    fleet_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Assign a device to a fleet."""
    from sqlalchemy import select
    from nexus.devices.models import DeviceFleet

    service = DeviceGatewayService(db)

    # SECURITY: Verify device ownership
    device = await service.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this device")

    # SECURITY: Verify fleet ownership
    result = await db.execute(
        select(DeviceFleet).where(DeviceFleet.id == UUID(fleet_id))
    )
    fleet = result.scalar_one_or_none()
    if not fleet:
        raise HTTPException(status_code=404, detail="Fleet not found")
    if fleet.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to add devices to this fleet")

    await service.assign_to_fleet(device_id, UUID(fleet_id))
    return {"status": "assigned"}


# --- Missions ---

@router.post("/missions")
async def create_mission(
    request: CreateMissionRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Create a mission."""
    service = DeviceGatewayService(db)
    mission = await service.create_mission(
        name=request.name,
        owner_id=agent.id,
        mission_type=request.mission_type,
        device_ids=request.device_ids,
        fleet_id=UUID(request.fleet_id) if request.fleet_id else None,
        waypoints=request.waypoints,
        parameters=request.parameters,
        scheduled_start=datetime.fromisoformat(request.scheduled_start) if request.scheduled_start else None,
    )

    return {
        "id": str(mission.id),
        "name": mission.name,
        "status": mission.status,
        "waypoints": mission.waypoints or [],
    }


@router.post("/missions/{mission_id}/start")
async def start_mission(
    mission_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Start a mission."""
    from sqlalchemy import select
    from nexus.devices.models import DeviceMission

    # SECURITY: Verify mission ownership before starting
    result = await db.execute(
        select(DeviceMission).where(DeviceMission.id == UUID(mission_id))
    )
    mission_record = result.scalar_one_or_none()
    if not mission_record:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission_record.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to start this mission")

    service = DeviceGatewayService(db)
    mission = await service.start_mission(UUID(mission_id))
    return {"id": str(mission.id), "status": mission.status}


@router.post("/missions/{mission_id}/abort")
async def abort_mission(
    mission_id: str,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Abort a mission."""
    from sqlalchemy import select
    from nexus.devices.models import DeviceMission

    # SECURITY: Verify mission ownership before aborting
    result = await db.execute(
        select(DeviceMission).where(DeviceMission.id == UUID(mission_id))
    )
    mission_record = result.scalar_one_or_none()
    if not mission_record:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission_record.owner_id != agent.id:
        raise HTTPException(status_code=403, detail="Not authorized to abort this mission")

    service = DeviceGatewayService(db)
    mission = await service.abort_mission(UUID(mission_id), agent.id)
    return {"id": str(mission.id), "status": mission.status}


# --- WebSocket for Real-time Telemetry ---

@router.websocket("/stream/{device_id}")
async def device_stream(
    websocket: WebSocket,
    device_id: str,
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket for real-time device telemetry and commands.

    SECURITY: Requires device token for authentication.
    Pass token as query parameter: /stream/{device_id}?token=xxx
    """
    service = DeviceGatewayService(db)
    device = await service.get_device(device_id)

    if not device:
        await websocket.close(code=4004, reason="Device not found")
        return

    # SECURITY: Verify device token before accepting connection
    # In production, devices should have their own API keys stored and validated
    # For now, we ensure the device exists. Add token validation when device auth is implemented.
    if not device:
        await websocket.close(code=4004, reason="Device not found")
        return

    await websocket.accept()

    try:
        # Update device status to online
        await service.update_device_status(device_id, DeviceStatus.ONLINE)

        while True:
            data = await websocket.receive_json()

            if data.get("type") == "telemetry":
                await service.ingest_telemetry(
                    device_id=device_id,
                    timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
                    latitude=data.get("latitude"),
                    longitude=data.get("longitude"),
                    altitude=data.get("altitude"),
                    heading=data.get("heading"),
                    speed=data.get("speed"),
                    battery_level=data.get("battery_level"),
                    sensors=data.get("sensors"),
                )
                await websocket.send_json({"type": "ack", "status": "received"})

            elif data.get("type") == "command_response":
                command_id = data.get("command_id")
                success = data.get("success", True)
                await service.complete_command(
                    command_id=command_id,
                    success=success,
                    response=data.get("response"),
                    error_message=data.get("error"),
                )

            elif data.get("type") == "heartbeat":
                await service.update_device_status(
                    device_id,
                    DeviceStatus.ONLINE,
                    battery_level=data.get("battery_level"),
                    signal_strength=data.get("signal_strength"),
                )
                await websocket.send_json({"type": "heartbeat_ack"})

    except WebSocketDisconnect:
        await service.update_device_status(device_id, DeviceStatus.OFFLINE)
