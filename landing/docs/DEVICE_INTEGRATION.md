# Connecting Physical Devices to Nexus

This guide explains how to connect robots, drones, sensors, and other IoT devices to the Nexus platform.

---

## Quick Start

### 1. Register Your Device

```bash
curl -X POST https://your-nexus-instance/api/v1/devices/register \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "drone-001",
    "name": "Delivery Drone Alpha",
    "device_type": "drone",
    "protocol": "mavlink",
    "capabilities": ["fly", "hover", "deliver"],
    "sensors": ["gps", "camera", "barometer"],
    "connection_config": {
      "connection_string": "udp:192.168.1.100:14550"
    }
  }'
```

### 2. Send Telemetry

```bash
curl -X POST https://your-nexus-instance/api/v1/devices/drone-001/telemetry \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2024-01-15T10:30:00Z",
    "latitude": 37.7749,
    "longitude": -122.4194,
    "altitude": 100.5,
    "battery_level": 85,
    "sensors": {
      "temperature": 22.5
    }
  }'
```

### 3. Receive Commands

Connect via WebSocket for real-time commands:

```javascript
const ws = new WebSocket('wss://your-nexus-instance/api/v1/devices/stream/drone-001');

ws.onmessage = (event) => {
  const command = JSON.parse(event.data);

  switch(command.type) {
    case 'takeoff':
      executeeTakeoff(command.parameters.altitude);
      break;
    case 'goto':
      navigateTo(command.parameters.latitude, command.parameters.longitude);
      break;
    case 'emergency_stop':
      emergencyLand();
      break;
  }

  // Acknowledge command
  ws.send(JSON.stringify({
    type: 'ack',
    command_id: command.command_id
  }));
};
```

---

## Supported Device Types

| Type | Description | Common Protocols |
|------|-------------|-----------------|
| `drone` | UAVs, quadcopters | MAVLink, HTTP |
| `robot` | Ground robots, arms | MQTT, Modbus |
| `vehicle` | Autonomous cars, AGVs | HTTP, WebSocket |
| `sensor` | Temperature, pressure, etc. | MQTT, CoAP |
| `camera` | IP cameras, vision systems | HTTP, RTSP |
| `actuator` | Motors, servos, relays | Modbus, MQTT |
| `gateway` | IoT hubs | MQTT, HTTP |
| `industrial` | PLCs, CNC machines | OPC-UA, Modbus |
| `wearable` | Smartwatches, trackers | Bluetooth, HTTP |

---

## Communication Protocols

### MAVLink (Drones)

Best for: Ardupilot, PX4, drone fleets

```python
# Python example - Device side
from pymavlink import mavutil

# Connect to Nexus MAVLink proxy
conn = mavutil.mavlink_connection('udp:nexus-host:14550')

# Send heartbeat
conn.mav.heartbeat_send(
    mavutil.mavlink.MAV_TYPE_QUADROTOR,
    mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
    0, 0, 0
)

# Send GPS position
conn.mav.global_position_int_send(
    int(time.time() * 1000),  # timestamp
    int(37.7749 * 1e7),       # lat
    int(-122.4194 * 1e7),     # lon
    int(100 * 1000),          # alt (mm)
    int(100 * 1000),          # relative alt
    0, 0, 0, 0                # velocities, heading
)
```

**Supported MAVLink Commands:**
- `arm` / `disarm` - Arm/disarm motors
- `takeoff` - Take off to specified altitude
- `land` - Land at current position
- `rtl` - Return to launch/home
- `goto` - Navigate to coordinates
- `emergency_stop` - Immediate flight termination
- `set_mode` - Change flight mode (GUIDED, AUTO, etc.)
- `load_mission` - Upload waypoint mission

### MQTT (IoT Devices)

Best for: Sensors, robots, distributed systems

```python
# Python example - Device side
import paho.mqtt.client as mqtt
import json

client = mqtt.Client()
client.connect("nexus-host", 1883)

# Subscribe to commands
client.subscribe("nexus/devices/robot-001/commands")

def on_message(client, userdata, msg):
    command = json.loads(msg.payload)
    execute_command(command)

    # Send acknowledgment
    client.publish(
        "nexus/devices/robot-001/ack",
        json.dumps({"command_id": command["command_id"], "status": "completed"})
    )

client.on_message = on_message

# Publish telemetry
client.publish(
    "nexus/devices/robot-001/telemetry",
    json.dumps({
        "timestamp": "2024-01-15T10:30:00Z",
        "battery_level": 75,
        "sensors": {"temperature": 25.5}
    })
)

client.loop_forever()
```

**MQTT Topics:**
- `nexus/devices/{device_id}/telemetry` - Send sensor data
- `nexus/devices/{device_id}/commands` - Receive commands
- `nexus/devices/{device_id}/ack` - Acknowledge commands
- `nexus/devices/{device_id}/events` - Send alerts/events

### HTTP/REST (Simple Devices)

Best for: Simple integrations, web-connected devices

```python
# Python example - Device side
import requests
import time

NEXUS_URL = "https://your-nexus-instance"
API_KEY = "your-api-key"
DEVICE_ID = "sensor-001"

headers = {"Authorization": f"Bearer {API_KEY}"}

# Send telemetry every 10 seconds
while True:
    requests.post(
        f"{NEXUS_URL}/api/v1/devices/{DEVICE_ID}/telemetry",
        headers=headers,
        json={
            "timestamp": datetime.utcnow().isoformat(),
            "sensors": {
                "temperature": read_temperature(),
                "humidity": read_humidity()
            }
        }
    )
    time.sleep(10)
```

### WebSocket (Real-time)

Best for: Low-latency control, streaming telemetry

```javascript
// JavaScript example - Device side
const WebSocket = require('ws');

const ws = new WebSocket('wss://nexus-host/api/v1/devices/stream/robot-001', {
  headers: { 'Authorization': 'Bearer YOUR_API_KEY' }
});

// Send heartbeat every 5 seconds
setInterval(() => {
  ws.send(JSON.stringify({ type: 'heartbeat' }));
}, 5000);

// Send telemetry
function sendTelemetry(data) {
  ws.send(JSON.stringify({
    type: 'telemetry',
    data: {
      timestamp: new Date().toISOString(),
      ...data
    }
  }));
}

// Handle incoming commands
ws.on('message', (data) => {
  const msg = JSON.parse(data);
  if (msg.type === 'command') {
    handleCommand(msg);
  }
});
```

---

## Fleet Management

### Create a Fleet

```bash
curl -X POST https://your-nexus-instance/api/v1/devices/fleets \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Warehouse Robots",
    "coordination_mode": "swarm",
    "geofence": {
      "type": "rectangle",
      "bounds": {
        "min_lat": 37.77,
        "max_lat": 37.78,
        "min_lon": -122.42,
        "max_lon": -122.41
      }
    }
  }'
```

### Assign Devices to Fleet

```bash
curl -X POST https://your-nexus-instance/api/v1/devices/robot-001/assign-fleet/FLEET_ID \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Fleet Emergency Stop

Stops all devices in a fleet immediately:

```bash
curl -X POST https://your-nexus-instance/api/v1/devices/fleets/FLEET_ID/emergency-stop \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## Mission Planning

### Create a Waypoint Mission

```bash
curl -X POST https://your-nexus-instance/api/v1/devices/missions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Delivery Route A",
    "mission_type": "delivery",
    "device_ids": ["drone-001"],
    "waypoints": [
      {"latitude": 37.7749, "longitude": -122.4194, "altitude": 50},
      {"latitude": 37.7849, "longitude": -122.4094, "altitude": 50},
      {"latitude": 37.7949, "longitude": -122.3994, "altitude": 30}
    ],
    "parameters": {
      "speed": 10,
      "hover_time": 5
    }
  }'
```

### Start Mission

```bash
curl -X POST https://your-nexus-instance/api/v1/devices/missions/MISSION_ID/start \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Abort Mission

```bash
curl -X POST https://your-nexus-instance/api/v1/devices/missions/MISSION_ID/abort \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## Safety Features

### Geofencing

Define operational boundaries. Devices trigger alerts if they breach:

```json
{
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
```

### Battery Monitoring

Automatic alerts when battery drops:
- **Warning:** Below 20%
- **Critical:** Below 10%

### Emergency Commands

| Command | Priority | Description |
|---------|----------|-------------|
| `emergency_stop` | EMERGENCY | Immediate halt/landing |
| `return_to_base` | CRITICAL | Return to home position |

---

## AI Agent Control

Assign an AI agent to control a device:

```bash
curl -X POST https://your-nexus-instance/api/v1/devices/register \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "robot-001",
    "name": "Warehouse Robot",
    "device_type": "robot",
    "protocol": "mqtt",
    "ai_agent_id": "AGENT_UUID",
    "autonomy_level": "autonomous"
  }'
```

**Autonomy Levels:**
- `manual` - Human operator controls directly
- `supervised` - AI suggests, human approves
- `autonomous` - AI controls independently

---

## Telemetry Schema

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "latitude": 37.7749,
  "longitude": -122.4194,
  "altitude": 100.5,
  "heading": 45.0,
  "speed": 12.5,
  "battery_level": 85.0,
  "signal_strength": 95.0,
  "sensors": {
    "temperature": 22.5,
    "pressure": 1013.25,
    "humidity": 45.0
  },
  "raw_data": {}
}
```

---

## Example Integrations

### ROS Integration

```python
#!/usr/bin/env python3
import rospy
from sensor_msgs.msg import NavSatFix
from geometry_msgs.msg import Twist
import requests

class NexusBridge:
    def __init__(self):
        rospy.init_node('nexus_bridge')
        self.device_id = rospy.get_param('~device_id')
        self.nexus_url = rospy.get_param('~nexus_url')
        self.api_key = rospy.get_param('~api_key')

        rospy.Subscriber('/gps/fix', NavSatFix, self.gps_callback)
        self.cmd_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=10)

    def gps_callback(self, msg):
        requests.post(
            f"{self.nexus_url}/api/v1/devices/{self.device_id}/telemetry",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "latitude": msg.latitude,
                "longitude": msg.longitude,
                "altitude": msg.altitude
            }
        )

if __name__ == '__main__':
    bridge = NexusBridge()
    rospy.spin()
```

### Arduino/ESP32

```cpp
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* ssid = "your-wifi";
const char* password = "your-password";
const char* nexusUrl = "https://your-nexus-instance";
const char* apiKey = "your-api-key";
const char* deviceId = "sensor-001";

void setup() {
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);
}

void sendTelemetry(float temperature, float humidity) {
  HTTPClient http;
  String url = String(nexusUrl) + "/api/v1/devices/" + deviceId + "/telemetry";

  http.begin(url);
  http.addHeader("Authorization", String("Bearer ") + apiKey);
  http.addHeader("Content-Type", "application/json");

  StaticJsonDocument<200> doc;
  doc["sensors"]["temperature"] = temperature;
  doc["sensors"]["humidity"] = humidity;

  String json;
  serializeJson(doc, json);

  http.POST(json);
  http.end();
}

void loop() {
  float temp = readTemperature();
  float humidity = readHumidity();
  sendTelemetry(temp, humidity);
  delay(10000);
}
```

---

## Troubleshooting

### Device Not Connecting

1. Check API key is valid
2. Verify device_id is unique
3. Check network connectivity
4. Ensure protocol matches device capabilities

### Commands Not Received

1. Check WebSocket connection is active
2. Verify device is registered
3. Check command priority isn't being throttled
4. Review device events for errors

### Telemetry Not Showing

1. Verify timestamp format (ISO 8601)
2. Check authentication headers
3. Ensure device is registered
4. Review rate limits

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/devices/register` | POST | Register new device |
| `/devices` | GET | List devices |
| `/devices/{id}` | GET | Get device details |
| `/devices/{id}/telemetry` | POST | Send telemetry |
| `/devices/{id}/telemetry` | GET | Get telemetry history |
| `/devices/{id}/commands` | POST | Send command |
| `/devices/{id}/emergency-stop` | POST | Emergency stop |
| `/devices/{id}/return-to-base` | POST | Return to home |
| `/devices/{id}/events` | GET | Get device events |
| `/devices/fleets` | POST | Create fleet |
| `/devices/fleets/{id}/emergency-stop` | POST | Fleet emergency stop |
| `/devices/missions` | POST | Create mission |
| `/devices/missions/{id}/start` | POST | Start mission |
| `/devices/missions/{id}/abort` | POST | Abort mission |
| `/devices/stream/{id}` | WebSocket | Real-time stream |
