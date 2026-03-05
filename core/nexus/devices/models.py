"""Device Gateway models for IoT, drones, and physical assets."""

from __future__ import annotations

import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, JSON, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from nexus.database import Base


class DeviceType(str, enum.Enum):
    """Types of physical devices."""
    DRONE = "drone"
    ROBOT = "robot"
    VEHICLE = "vehicle"
    SENSOR = "sensor"
    CAMERA = "camera"
    ACTUATOR = "actuator"
    GATEWAY = "gateway"
    WEARABLE = "wearable"
    INDUSTRIAL = "industrial"
    CUSTOM = "custom"


class DeviceProtocol(str, enum.Enum):
    """Communication protocols."""
    MQTT = "mqtt"
    MAVLINK = "mavlink"
    MODBUS = "modbus"
    OPCUA = "opcua"
    COAP = "coap"
    HTTP = "http"
    WEBSOCKET = "websocket"
    LORA = "lora"
    ZIGBEE = "zigbee"
    BLUETOOTH = "bluetooth"
    CUSTOM = "custom"


class DeviceStatus(str, enum.Enum):
    """Device connection status."""
    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ERROR = "error"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


class CommandPriority(str, enum.Enum):
    """Command priority levels."""
    EMERGENCY = "emergency"  # Abort, RTB, emergency stop
    CRITICAL = "critical"    # Safety-related
    HIGH = "high"            # Time-sensitive operations
    NORMAL = "normal"        # Standard commands
    LOW = "low"              # Background tasks


class CommandStatus(str, enum.Enum):
    """Command execution status."""
    PENDING = "pending"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class Device(Base):
    """A physical device (drone, robot, sensor, etc.)."""

    __tablename__ = "devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Device identification
    device_id = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    device_type = Column(Enum(DeviceType), nullable=False)

    # Hardware info
    manufacturer = Column(String(255), nullable=True)
    model = Column(String(255), nullable=True)
    serial_number = Column(String(255), nullable=True)
    firmware_version = Column(String(100), nullable=True)

    # Communication
    protocol = Column(Enum(DeviceProtocol), default=DeviceProtocol.MQTT)
    connection_config = Column(JSON, default=dict)  # Protocol-specific settings
    endpoint = Column(String(1024), nullable=True)  # Connection endpoint

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    fleet_id = Column(UUID(as_uuid=True), ForeignKey("device_fleets.id"), nullable=True)

    # AI agent controlling this device
    ai_agent_id = Column(UUID(as_uuid=True), nullable=True)
    autonomy_level = Column(String(50), default="supervised")  # manual, supervised, autonomous

    # Status
    status = Column(Enum(DeviceStatus), default=DeviceStatus.UNKNOWN)
    last_seen_at = Column(DateTime, nullable=True)
    last_telemetry_at = Column(DateTime, nullable=True)

    # Location (for mobile devices)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    heading = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)

    # Health
    battery_level = Column(Float, nullable=True)  # 0-100
    signal_strength = Column(Float, nullable=True)  # dBm or percentage
    health_status = Column(JSON, default=dict)  # Component health

    # Capabilities
    capabilities = Column(JSON, default=list)  # What this device can do
    sensors = Column(JSON, default=list)  # Available sensors
    actuators = Column(JSON, default=list)  # Available actuators

    # Configuration
    config = Column(JSON, default=dict)
    geofence = Column(JSON, nullable=True)  # Operating boundaries
    operating_limits = Column(JSON, default=dict)  # Max speed, altitude, etc.

    # Metadata
    tags = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)

    # Device API Key Authentication
    api_key_hash = Column(String(255), nullable=True)  # Hashed API key for device auth
    api_key_prefix = Column(String(12), nullable=True, index=True)  # First 8 chars for lookup
    api_key_last_used = Column(DateTime, nullable=True)
    api_key_created_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    fleet = relationship("DeviceFleet", back_populates="devices")
    telemetry = relationship("DeviceTelemetry", back_populates="device", cascade="all, delete-orphan")
    commands = relationship("DeviceCommand", back_populates="device", cascade="all, delete-orphan")


class DeviceFleet(Base):
    """A fleet/group of devices."""

    __tablename__ = "device_fleets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    # AI orchestrator for the fleet
    orchestrator_agent_id = Column(UUID(as_uuid=True), nullable=True)
    coordination_mode = Column(String(50), default="independent")  # independent, coordinated, swarm

    # Fleet configuration
    config = Column(JSON, default=dict)
    default_autonomy_level = Column(String(50), default="supervised")

    # Geofence for entire fleet
    geofence = Column(JSON, nullable=True)

    # Statistics
    device_count = Column(Integer, default=0)
    active_device_count = Column(Integer, default=0)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    devices = relationship("Device", back_populates="fleet")


class DeviceTelemetry(Base):
    """Telemetry data from a device."""

    __tablename__ = "device_telemetry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)

    # Timestamp
    timestamp = Column(DateTime, nullable=False, index=True)
    received_at = Column(DateTime, default=datetime.utcnow)

    # Location
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    heading = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)
    accuracy = Column(Float, nullable=True)

    # Status
    battery_level = Column(Float, nullable=True)
    signal_strength = Column(Float, nullable=True)

    # Sensor readings
    sensors = Column(JSON, default=dict)  # {sensor_name: value}

    # Raw data
    raw_data = Column(JSON, nullable=True)

    device = relationship("Device", back_populates="telemetry")


class DeviceCommand(Base):
    """A command sent to a device."""

    __tablename__ = "device_commands"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)

    # Command identification
    command_id = Column(String(255), nullable=False, unique=True, index=True)

    # Sender
    sender_id = Column(UUID(as_uuid=True), nullable=True)
    sender_type = Column(String(50), nullable=True)  # agent, human, system, ai

    # Command details
    command_type = Column(String(100), nullable=False)  # takeoff, land, move_to, etc.
    priority = Column(Enum(CommandPriority), default=CommandPriority.NORMAL)
    parameters = Column(JSON, default=dict)

    # Status
    status = Column(Enum(CommandStatus), default=CommandStatus.PENDING)
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    timeout_at = Column(DateTime, nullable=True)

    # Response
    response = Column(JSON, nullable=True)

    # Retry
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    device = relationship("Device", back_populates="commands")


class DeviceEvent(Base):
    """Events/alerts from devices."""

    __tablename__ = "device_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)

    # Event info
    event_type = Column(String(100), nullable=False)  # geofence_breach, low_battery, collision_warning
    severity = Column(String(50), default="info")  # info, warning, critical, emergency
    message = Column(Text, nullable=True)

    # Data
    data = Column(JSON, default=dict)

    # Location at time of event
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)

    # Handling
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(UUID(as_uuid=True), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)

    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(UUID(as_uuid=True), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    resolution_notes = Column(Text, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow)


class DeviceMission(Base):
    """A mission/task for one or more devices."""

    __tablename__ = "device_missions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Owner
    owner_id = Column(UUID(as_uuid=True), nullable=False)

    # Mission type
    mission_type = Column(String(100), nullable=False)  # survey, delivery, patrol, etc.

    # Assigned devices
    device_ids = Column(JSON, default=list)
    fleet_id = Column(UUID(as_uuid=True), nullable=True)

    # Mission plan
    waypoints = Column(JSON, default=list)  # [{lat, lon, alt, action, params}]
    parameters = Column(JSON, default=dict)

    # Status
    status = Column(String(50), default="draft")  # draft, scheduled, active, paused, completed, aborted
    progress = Column(Float, default=0)  # 0-100

    # Timing
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)

    # Conditions
    abort_conditions = Column(JSON, default=list)  # Conditions that trigger abort
    weather_constraints = Column(JSON, nullable=True)

    # Results
    results = Column(JSON, nullable=True)
    collected_data = Column(JSON, default=list)  # References to collected data

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
