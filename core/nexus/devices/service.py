"""Device Gateway service for IoT, drones, and physical assets."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from uuid import UUID
import uuid as uuid_module
import asyncio
from typing import Callable

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.devices.models import (
    Device, DeviceFleet, DeviceTelemetry, DeviceCommand, DeviceEvent, DeviceMission,
    DeviceType, DeviceProtocol, DeviceStatus, CommandPriority, CommandStatus
)


def _hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def _generate_device_api_key() -> tuple[str, str, str]:
    """
    Generate a device API key.

    Returns:
        tuple: (full_key, prefix, hash)
        - full_key: The complete API key to give to device (e.g., "nex_dev_abc123...")
        - prefix: First 8 chars for DB lookup
        - hash: SHA-256 hash for storage
    """
    # Generate 32 random bytes = 64 hex chars
    random_part = secrets.token_hex(32)
    full_key = f"nex_dev_{random_part}"
    prefix = full_key[:12]  # "nex_dev_xxxx"
    key_hash = _hash_api_key(full_key)
    return full_key, prefix, key_hash


class DeviceGatewayService:
    """Service for device management and communication."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._protocol_handlers: dict[DeviceProtocol, Callable] = {}
        self._mqtt_client = None
        self._mavlink_connections = {}
        self._event_handlers: list[Callable] = []

    # --- Protocol Configuration ---

    def configure_mqtt(self, broker_url: str, username: str | None = None, password: str | None = None):
        """Configure MQTT broker connection."""
        import paho.mqtt.client as mqtt

        client = mqtt.Client()
        if username and password:
            client.username_pw_set(username, password)

        # Parse broker URL
        # mqtt://host:port or mqtts://host:port
        self._mqtt_client = client
        self._protocol_handlers[DeviceProtocol.MQTT] = self._handle_mqtt

    def configure_mavlink(self, connection_string: str):
        """Configure MAVLink connection for drones."""
        # connection_string like "udp:localhost:14550" or "serial:/dev/ttyUSB0:57600"
        self._protocol_handlers[DeviceProtocol.MAVLINK] = self._handle_mavlink

    # --- Device Management ---

    async def register_device(
        self,
        device_id: str,
        name: str,
        device_type: DeviceType,
        owner_id: UUID,
        protocol: DeviceProtocol = DeviceProtocol.MQTT,
        connection_config: dict | None = None,
        capabilities: list[str] | None = None,
        sensors: list[str] | None = None,
        ai_agent_id: UUID | None = None,
        autonomy_level: str = "supervised",
        fleet_id: UUID | None = None,
        geofence: dict | None = None,
        metadata: dict | None = None,
    ) -> Device:
        """Register a new device."""
        device = Device(
            device_id=device_id,
            name=name,
            device_type=device_type,
            owner_id=owner_id,
            protocol=protocol,
            connection_config=connection_config or {},
            capabilities=capabilities or [],
            sensors=sensors or [],
            ai_agent_id=ai_agent_id,
            autonomy_level=autonomy_level,
            fleet_id=fleet_id,
            geofence=geofence,
            metadata=metadata or {},
            status=DeviceStatus.UNKNOWN,
        )
        self.db.add(device)

        # Update fleet count if assigned
        if fleet_id:
            result = await self.db.execute(
                select(DeviceFleet).where(DeviceFleet.id == fleet_id)
            )
            fleet = result.scalar_one_or_none()
            if fleet:
                fleet.device_count += 1

        await self.db.commit()
        await self.db.refresh(device)
        return device

    async def update_device_status(
        self,
        device_id: str,
        status: DeviceStatus,
        latitude: float | None = None,
        longitude: float | None = None,
        altitude: float | None = None,
        battery_level: float | None = None,
        signal_strength: float | None = None,
        health_status: dict | None = None,
    ):
        """Update device status (called on heartbeat/telemetry)."""
        result = await self.db.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            return

        old_status = device.status
        device.status = status
        device.last_seen_at = datetime.utcnow()

        if latitude is not None:
            device.latitude = latitude
        if longitude is not None:
            device.longitude = longitude
        if altitude is not None:
            device.altitude = altitude
        if battery_level is not None:
            device.battery_level = battery_level
        if signal_strength is not None:
            device.signal_strength = signal_strength
        if health_status is not None:
            device.health_status = health_status

        # Update fleet active count if status changed
        if old_status != status and device.fleet_id:
            result = await self.db.execute(
                select(DeviceFleet).where(DeviceFleet.id == device.fleet_id)
            )
            fleet = result.scalar_one_or_none()
            if fleet:
                if status == DeviceStatus.ONLINE and old_status != DeviceStatus.ONLINE:
                    fleet.active_device_count += 1
                elif status != DeviceStatus.ONLINE and old_status == DeviceStatus.ONLINE:
                    fleet.active_device_count = max(0, fleet.active_device_count - 1)

        await self.db.commit()

    # --- Telemetry ---

    async def ingest_telemetry(
        self,
        device_id: str,
        timestamp: datetime,
        latitude: float | None = None,
        longitude: float | None = None,
        altitude: float | None = None,
        heading: float | None = None,
        speed: float | None = None,
        battery_level: float | None = None,
        signal_strength: float | None = None,
        sensors: dict | None = None,
        raw_data: dict | None = None,
    ) -> DeviceTelemetry:
        """Ingest telemetry data from a device."""
        result = await self.db.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            raise ValueError(f"Device {device_id} not found")

        telemetry = DeviceTelemetry(
            device_id=device.id,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            heading=heading,
            speed=speed,
            battery_level=battery_level,
            signal_strength=signal_strength,
            sensors=sensors or {},
            raw_data=raw_data,
        )
        self.db.add(telemetry)

        # Update device with latest position
        device.last_telemetry_at = datetime.utcnow()
        device.last_seen_at = datetime.utcnow()
        device.status = DeviceStatus.ONLINE
        if latitude is not None:
            device.latitude = latitude
        if longitude is not None:
            device.longitude = longitude
        if altitude is not None:
            device.altitude = altitude
        if heading is not None:
            device.heading = heading
        if speed is not None:
            device.speed = speed
        if battery_level is not None:
            device.battery_level = battery_level

        # Check geofence
        if device.geofence and latitude and longitude:
            await self._check_geofence(device, latitude, longitude)

        # Check battery level
        if battery_level is not None and battery_level < 20:
            await self._create_event(
                device.id,
                "low_battery",
                "warning" if battery_level >= 10 else "critical",
                f"Battery level at {battery_level}%",
                {"battery_level": battery_level},
                latitude, longitude, altitude
            )

        await self.db.commit()
        await self.db.refresh(telemetry)
        return telemetry

    async def _check_geofence(self, device: Device, lat: float, lon: float):
        """Check if device is within geofence."""
        geofence = device.geofence
        if not geofence:
            return

        # Simple rectangular geofence check
        if geofence.get("type") == "rectangle":
            bounds = geofence.get("bounds", {})
            if (lat < bounds.get("min_lat", -90) or lat > bounds.get("max_lat", 90) or
                lon < bounds.get("min_lon", -180) or lon > bounds.get("max_lon", 180)):
                await self._create_event(
                    device.id,
                    "geofence_breach",
                    "critical",
                    "Device has breached geofence boundary",
                    {"geofence": geofence, "position": {"lat": lat, "lon": lon}},
                    lat, lon, device.altitude
                )

    async def _create_event(
        self,
        device_id: UUID,
        event_type: str,
        severity: str,
        message: str,
        data: dict,
        lat: float | None = None,
        lon: float | None = None,
        alt: float | None = None,
    ):
        """Create a device event."""
        event = DeviceEvent(
            device_id=device_id,
            event_type=event_type,
            severity=severity,
            message=message,
            data=data,
            latitude=lat,
            longitude=lon,
            altitude=alt,
        )
        self.db.add(event)

        # Notify handlers
        for handler in self._event_handlers:
            try:
                await handler(event)
            except Exception:
                pass

    # --- Commands ---

    async def send_command(
        self,
        device_id: str,
        command_type: str,
        parameters: dict | None = None,
        priority: CommandPriority = CommandPriority.NORMAL,
        sender_id: UUID | None = None,
        sender_type: str = "system",
        timeout_seconds: int = 30,
    ) -> DeviceCommand:
        """Send a command to a device."""
        result = await self.db.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            raise ValueError(f"Device {device_id} not found")

        command = DeviceCommand(
            device_id=device.id,
            command_id=str(uuid_module.uuid4()),
            sender_id=sender_id,
            sender_type=sender_type,
            command_type=command_type,
            priority=priority,
            parameters=parameters or {},
            status=CommandStatus.PENDING,
            timeout_at=datetime.utcnow() + timedelta(seconds=timeout_seconds),
        )
        self.db.add(command)
        await self.db.flush()

        # Dispatch command via protocol
        await self._dispatch_command(device, command)

        await self.db.commit()
        await self.db.refresh(command)
        return command

    async def _dispatch_command(self, device: Device, command: DeviceCommand):
        """Dispatch command to device via appropriate protocol."""
        handler = self._protocol_handlers.get(device.protocol)
        if handler:
            try:
                await handler(device, command)
                command.status = CommandStatus.SENT
                command.sent_at = datetime.utcnow()
            except Exception as e:
                command.status = CommandStatus.FAILED
                command.error_message = str(e)
        else:
            # Queue for manual dispatch
            command.status = CommandStatus.PENDING

    async def _handle_mqtt(self, device: Device, command: DeviceCommand):
        """Send command via MQTT."""
        if not self._mqtt_client:
            raise RuntimeError("MQTT not configured")

        import json
        topic = f"nexus/devices/{device.device_id}/commands"
        payload = json.dumps({
            "command_id": command.command_id,
            "type": command.command_type,
            "priority": command.priority.value,
            "parameters": command.parameters,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self._mqtt_client.publish(topic, payload)

    async def _handle_mavlink(self, device: Device, command: DeviceCommand):
        """Send command via MAVLink (for drones)."""
        from pymavlink import mavutil

        connection_string = device.connection_config.get("connection_string", "udp:127.0.0.1:14550")

        # Get or create connection for this device
        if device.device_id not in self._mavlink_connections:
            try:
                conn = mavutil.mavlink_connection(connection_string)
                conn.wait_heartbeat(timeout=5)
                self._mavlink_connections[device.device_id] = conn
            except Exception as e:
                raise RuntimeError(f"Failed to connect to MAVLink: {e}")

        conn = self._mavlink_connections[device.device_id]
        params = command.parameters or {}

        # MAVLink command dispatch
        if command.command_type == "arm":
            conn.mav.command_long_send(
                conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0, 1, 0, 0, 0, 0, 0, 0  # 1 = arm
            )
        elif command.command_type == "disarm":
            conn.mav.command_long_send(
                conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0, 0, 0, 0, 0, 0, 0, 0  # 0 = disarm
            )
        elif command.command_type == "takeoff":
            altitude = params.get("altitude", 10)
            conn.mav.command_long_send(
                conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                0, 0, 0, 0, 0, 0, 0, altitude
            )
        elif command.command_type == "land":
            conn.mav.command_long_send(
                conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_CMD_NAV_LAND,
                0, 0, 0, 0, 0, 0, 0, 0
            )
        elif command.command_type == "rtl" or command.command_type == "return_to_base":
            conn.mav.command_long_send(
                conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
                0, 0, 0, 0, 0, 0, 0, 0
            )
        elif command.command_type == "goto":
            lat = params.get("latitude", 0)
            lon = params.get("longitude", 0)
            alt = params.get("altitude", 10)
            conn.mav.command_long_send(
                conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                0, 0, 0, 0, lat, lon, alt, 0
            )
        elif command.command_type == "emergency_stop":
            # Flight termination - emergency only
            conn.mav.command_long_send(
                conn.target_system, conn.target_component,
                mavutil.mavlink.MAV_CMD_DO_FLIGHTTERMINATION,
                0, 1, 0, 0, 0, 0, 0, 0  # 1 = terminate
            )
        elif command.command_type == "set_mode":
            mode = params.get("mode", "GUIDED")
            mode_id = conn.mode_mapping().get(mode, 0)
            conn.mav.set_mode_send(
                conn.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_id
            )
        elif command.command_type == "load_mission":
            # Upload waypoints as mission items
            waypoints = params.get("waypoints", [])
            await self._upload_mavlink_mission(conn, waypoints)
        else:
            raise ValueError(f"Unknown MAVLink command: {command.command_type}")

    async def _upload_mavlink_mission(self, conn, waypoints: list[dict]):
        """Upload mission waypoints to drone."""
        from pymavlink import mavutil

        # Clear existing mission
        conn.mav.mission_clear_all_send(conn.target_system, conn.target_component)

        # Send mission count
        conn.mav.mission_count_send(
            conn.target_system, conn.target_component, len(waypoints)
        )

        # Upload each waypoint
        for i, wp in enumerate(waypoints):
            conn.mav.mission_item_int_send(
                conn.target_system, conn.target_component,
                i,  # seq
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                0, 1,  # current, autocontinue
                0, 0, 0, 0,  # params 1-4
                int(wp.get("latitude", 0) * 1e7),
                int(wp.get("longitude", 0) * 1e7),
                wp.get("altitude", 10)
            )

    async def acknowledge_command(self, command_id: str):
        """Mark command as acknowledged by device."""
        result = await self.db.execute(
            select(DeviceCommand).where(DeviceCommand.command_id == command_id)
        )
        command = result.scalar_one_or_none()
        if command:
            command.status = CommandStatus.ACKNOWLEDGED
            command.acknowledged_at = datetime.utcnow()
            await self.db.commit()

    async def complete_command(
        self,
        command_id: str,
        success: bool = True,
        response: dict | None = None,
        error_message: str | None = None,
    ):
        """Mark command as completed."""
        result = await self.db.execute(
            select(DeviceCommand).where(DeviceCommand.command_id == command_id)
        )
        command = result.scalar_one_or_none()
        if command:
            command.status = CommandStatus.COMPLETED if success else CommandStatus.FAILED
            command.completed_at = datetime.utcnow()
            command.response = response
            if error_message:
                command.error_message = error_message
            await self.db.commit()

    # --- Emergency Commands ---

    async def emergency_stop(self, device_id: str, sender_id: UUID | None = None) -> DeviceCommand:
        """Send emergency stop command (highest priority)."""
        return await self.send_command(
            device_id=device_id,
            command_type="emergency_stop",
            priority=CommandPriority.EMERGENCY,
            sender_id=sender_id,
            sender_type="system",
            timeout_seconds=5,
        )

    async def return_to_base(self, device_id: str, sender_id: UUID | None = None) -> DeviceCommand:
        """Send return to base/home command."""
        return await self.send_command(
            device_id=device_id,
            command_type="rtl",
            priority=CommandPriority.CRITICAL,
            sender_id=sender_id,
            sender_type="system",
            timeout_seconds=30,
        )

    async def fleet_emergency_stop(self, fleet_id: UUID, sender_id: UUID | None = None) -> list[DeviceCommand]:
        """Emergency stop all devices in a fleet."""
        result = await self.db.execute(
            select(Device).where(
                and_(
                    Device.fleet_id == fleet_id,
                    Device.status == DeviceStatus.ONLINE,
                )
            )
        )
        devices = result.scalars().all()

        commands = []
        for device in devices:
            cmd = await self.emergency_stop(device.device_id, sender_id)
            commands.append(cmd)

        return commands

    # --- Fleets ---

    async def create_fleet(
        self,
        name: str,
        owner_id: UUID,
        description: str | None = None,
        orchestrator_agent_id: UUID | None = None,
        coordination_mode: str = "independent",
        geofence: dict | None = None,
    ) -> DeviceFleet:
        """Create a device fleet."""
        fleet = DeviceFleet(
            name=name,
            owner_id=owner_id,
            description=description,
            orchestrator_agent_id=orchestrator_agent_id,
            coordination_mode=coordination_mode,
            geofence=geofence,
        )
        self.db.add(fleet)
        await self.db.commit()
        await self.db.refresh(fleet)
        return fleet

    async def assign_to_fleet(self, device_id: str, fleet_id: UUID):
        """Assign a device to a fleet."""
        result = await self.db.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            raise ValueError("Device not found")

        # Remove from old fleet
        if device.fleet_id:
            result = await self.db.execute(
                select(DeviceFleet).where(DeviceFleet.id == device.fleet_id)
            )
            old_fleet = result.scalar_one_or_none()
            if old_fleet:
                old_fleet.device_count = max(0, old_fleet.device_count - 1)
                if device.status == DeviceStatus.ONLINE:
                    old_fleet.active_device_count = max(0, old_fleet.active_device_count - 1)

        # Add to new fleet
        device.fleet_id = fleet_id
        result = await self.db.execute(
            select(DeviceFleet).where(DeviceFleet.id == fleet_id)
        )
        new_fleet = result.scalar_one_or_none()
        if new_fleet:
            new_fleet.device_count += 1
            if device.status == DeviceStatus.ONLINE:
                new_fleet.active_device_count += 1

        await self.db.commit()

    # --- Missions ---

    async def create_mission(
        self,
        name: str,
        owner_id: UUID,
        mission_type: str,
        device_ids: list[str] | None = None,
        fleet_id: UUID | None = None,
        waypoints: list[dict] | None = None,
        parameters: dict | None = None,
        scheduled_start: datetime | None = None,
    ) -> DeviceMission:
        """Create a mission for devices."""
        mission = DeviceMission(
            name=name,
            owner_id=owner_id,
            mission_type=mission_type,
            device_ids=device_ids or [],
            fleet_id=fleet_id,
            waypoints=waypoints or [],
            parameters=parameters or {},
            scheduled_start=scheduled_start,
            status="draft" if not scheduled_start else "scheduled",
        )
        self.db.add(mission)
        await self.db.commit()
        await self.db.refresh(mission)
        return mission

    async def start_mission(self, mission_id: UUID) -> DeviceMission:
        """Start a mission."""
        result = await self.db.execute(
            select(DeviceMission).where(DeviceMission.id == mission_id)
        )
        mission = result.scalar_one_or_none()
        if not mission:
            raise ValueError("Mission not found")

        mission.status = "active"
        mission.actual_start = datetime.utcnow()

        # Send waypoints to devices
        for device_id in mission.device_ids:
            if mission.waypoints:
                await self.send_command(
                    device_id=device_id,
                    command_type="load_mission",
                    parameters={"waypoints": mission.waypoints},
                    priority=CommandPriority.HIGH,
                )

        await self.db.commit()
        await self.db.refresh(mission)
        return mission

    async def abort_mission(self, mission_id: UUID, sender_id: UUID | None = None) -> DeviceMission:
        """Abort a mission and recall devices."""
        result = await self.db.execute(
            select(DeviceMission).where(DeviceMission.id == mission_id)
        )
        mission = result.scalar_one_or_none()
        if not mission:
            raise ValueError("Mission not found")

        mission.status = "aborted"
        mission.actual_end = datetime.utcnow()

        # Return all devices to base
        for device_id in mission.device_ids:
            await self.return_to_base(device_id, sender_id)

        await self.db.commit()
        await self.db.refresh(mission)
        return mission

    # --- Queries ---

    async def list_devices(
        self,
        owner_id: UUID,
        device_type: DeviceType | None = None,
        fleet_id: UUID | None = None,
        status: DeviceStatus | None = None,
        limit: int = 100,
    ) -> list[Device]:
        """List devices."""
        query = select(Device).where(Device.owner_id == owner_id)
        if device_type:
            query = query.where(Device.device_type == device_type)
        if fleet_id:
            query = query.where(Device.fleet_id == fleet_id)
        if status:
            query = query.where(Device.status == status)
        query = query.order_by(Device.name.asc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_device(self, device_id: str) -> Device | None:
        """Get a device by its ID."""
        result = await self.db.execute(
            select(Device).where(Device.device_id == device_id)
        )
        return result.scalar_one_or_none()

    async def get_telemetry_history(
        self,
        device_id: str,
        start_time: datetime,
        end_time: datetime | None = None,
        limit: int = 1000,
    ) -> list[DeviceTelemetry]:
        """Get telemetry history for a device."""
        result = await self.db.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            return []

        query = select(DeviceTelemetry).where(
            and_(
                DeviceTelemetry.device_id == device.id,
                DeviceTelemetry.timestamp >= start_time,
            )
        )
        if end_time:
            query = query.where(DeviceTelemetry.timestamp <= end_time)
        query = query.order_by(DeviceTelemetry.timestamp.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_device_events(
        self,
        device_id: str,
        severity: str | None = None,
        unresolved_only: bool = False,
        limit: int = 100,
    ) -> list[DeviceEvent]:
        """Get events for a device."""
        result = await self.db.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            return []

        query = select(DeviceEvent).where(DeviceEvent.device_id == device.id)
        if severity:
            query = query.where(DeviceEvent.severity == severity)
        if unresolved_only:
            query = query.where(DeviceEvent.is_resolved == False)
        query = query.order_by(DeviceEvent.timestamp.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    def register_event_handler(self, handler: Callable):
        """Register a handler for device events."""
        self._event_handlers.append(handler)

    # --- Device API Key Authentication ---

    async def generate_device_api_key(self, device_id: str) -> str:
        """
        Generate a new API key for a device.

        Returns the full API key (only shown once). The device must store this
        securely and use it for authentication.
        """
        result = await self.db.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            raise ValueError(f"Device {device_id} not found")

        full_key, prefix, key_hash = _generate_device_api_key()

        device.api_key_hash = key_hash
        device.api_key_prefix = prefix
        device.api_key_created_at = datetime.utcnow()
        device.api_key_last_used = None

        await self.db.commit()

        return full_key

    async def validate_device_api_key(self, api_key: str) -> Device | None:
        """
        Validate a device API key and return the device if valid.

        This method is used for device authentication on telemetry/command endpoints.
        """
        if not api_key or not api_key.startswith("nex_dev_"):
            return None

        prefix = api_key[:12]
        key_hash = _hash_api_key(api_key)

        # Find device by prefix, then verify hash
        result = await self.db.execute(
            select(Device).where(
                and_(
                    Device.api_key_prefix == prefix,
                    Device.api_key_hash == key_hash,
                    Device.is_active == True,
                )
            )
        )
        device = result.scalar_one_or_none()

        if device:
            # Update last used timestamp
            device.api_key_last_used = datetime.utcnow()
            await self.db.commit()

        return device

    async def revoke_device_api_key(self, device_id: str) -> bool:
        """
        Revoke a device's API key.

        The device will no longer be able to authenticate until a new key is generated.
        """
        result = await self.db.execute(
            select(Device).where(Device.device_id == device_id)
        )
        device = result.scalar_one_or_none()
        if not device:
            return False

        device.api_key_hash = None
        device.api_key_prefix = None
        device.api_key_created_at = None
        device.api_key_last_used = None

        await self.db.commit()
        return True

    async def rotate_device_api_key(self, device_id: str) -> str:
        """
        Rotate a device's API key (revoke old, generate new).

        Returns the new API key.
        """
        await self.revoke_device_api_key(device_id)
        return await self.generate_device_api_key(device_id)
