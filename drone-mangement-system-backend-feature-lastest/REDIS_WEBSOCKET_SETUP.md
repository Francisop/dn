# Redis + WebSocket Integration Setup Guide

This guide will help you set up real-time event broadcasting for your Drone Management System using Redis Pub/Sub and WebSocket.

## What Was Added

### 1. **Redis Manager** (`src/services/redisManager.ts`)
- Manages Redis Pub/Sub connections
- Handles automatic reconnection
- Publishes events to Redis channels
- Subscribes to Redis channels for event broadcasting

### 2. **WebSocket Server** (`src/services/websocketServer.ts`)
- Socket.IO server for WebSocket connections
- Bridges Redis events to connected WebSocket clients
- Supports client subscriptions (all drones or specific drone)
- Endpoint: `ws://localhost:5000/ws/events`

### 3. **Event Publisher** (`src/services/eventPublisher.ts`)
- Helper functions to publish drone events
- Automatic change detection
- Event types:
  - `drone.created` - New drone registered
  - `drone.updated` - Drone data changed
  - `drone.deleted` - Drone removed
  - `drone.stream.status` - Stream on/off toggled
  - `drone.ai.detection.toggled` - AI detection toggled
  - `drone.detection.classes.changed` - Detection classes updated

### 4. **Controller Integration**
- Modified `droneController.ts` to publish events after CRUD operations
- Automatic event publishing on:
  - Drone creation
  - Drone updates (with change detection)
  - Drone deletion
  - Stream status changes
  - AI detection toggles

### 5. **Server Initialization**
- Updated `server.ts` to initialize Redis and WebSocket on startup
- Graceful shutdown handling

---

## Installation Steps

### Step 1: Install Dependencies

```bash
cd "/home/indepth-earth/jydestudios/End to End Survelience Software/Backend/drone-mangement-system-backend"

# Install Redis client and Socket.IO
npm install redis socket.io

# Install type definitions
npm install --save-dev @types/redis @types/socket.io
```

### Step 2: Configure Environment Variables

Add to your `.env` file:

```bash
# Redis Configuration
REDIS_URL=redis://localhost:6379

# Optional: If Redis requires authentication
# REDIS_URL=redis://username:password@localhost:6379
```

### Step 3: Verify Redis is Running

```bash
# Test Redis connection
redis-cli -h localhost -p 6379 ping

# Should return: PONG
```

If Redis is not running, it's already available in your Docker container:
```bash
docker ps | grep redis
# You should see: cloud_api_sample_redis_1
```

### Step 4: Start the Server

```bash
# Development mode
npm run dev

# Production mode
npm start
```

You should see:
```
✓ Server running on PORT: 5000
[Redis] Connecting to Redis at redis://localhost:6379...
✓ Redis Manager initialized successfully
[WebSocket] Initializing WebSocket server...
✓ WebSocket server initialized at /ws/events
============================================================
✓ All services initialized successfully
  - MongoDB: Connected
  - Redis: Connected
  - WebSocket: Running at /ws/events
  - HTTP API: Running at http://localhost:5000
============================================================
```

---

## Testing the Integration

### Test 1: WebSocket Connection

Create a test file `test-websocket.html`:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Drone WebSocket Test</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
</head>
<body>
    <h1>Drone Event Monitor</h1>
    <div id="status">Connecting...</div>
    <div id="events" style="max-height: 400px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px;">
        <p><em>Waiting for events...</em></p>
    </div>

    <script>
        // Connect to WebSocket server
        const socket = io('http://localhost:5000', {
            path: '/ws/events'
        });

        socket.on('connected', (data) => {
            document.getElementById('status').innerHTML = `✓ Connected: ${data.clientId}`;
            console.log('Connected:', data);

            // Subscribe to all drone events
            socket.emit('subscribe', { all: true });
        });

        socket.on('subscribed', (data) => {
            console.log('Subscribed:', data);
            addEvent('info', JSON.stringify(data, null, 2));
        });

        socket.on('drone:event', (event) => {
            console.log('Drone Event:', event);
            addEvent('drone', JSON.stringify(event, null, 2));
        });

        socket.on('system:event', (event) => {
            console.log('System Event:', event);
            addEvent('system', JSON.stringify(event, null, 2));
        });

        socket.on('disconnect', () => {
            document.getElementById('status').innerHTML = '✗ Disconnected';
            console.log('Disconnected');
        });

        function addEvent(type, message) {
            const eventsDiv = document.getElementById('events');
            const time = new Date().toLocaleTimeString();
            const color = type === 'drone' ? '#28a745' : type === 'system' ? '#ffc107' : '#17a2b8';

            eventsDiv.innerHTML += `
                <div style="margin: 10px 0; padding: 10px; background: ${color}22; border-left: 3px solid ${color}">
                    <strong>[${time}] ${type.toUpperCase()}</strong>
                    <pre style="margin: 5px 0;">${message}</pre>
                </div>
            `;
            eventsDiv.scrollTop = eventsDiv.scrollHeight;
        }
    </script>
</body>
</html>
```

Open this file in your browser and watch for events!

### Test 2: Create a Drone (Should Trigger Event)

```bash
curl -X POST http://localhost:5000/api/v1/drones/register \
  -H "Content-Type: application/json" \
  -d '{
    "deviceSerialNumber": "TEST123",
    "deviceName": "Test Drone",
    "deviceCategory": "Surveillance",
    "streamIsOn": false,
    "isUsingAiDetection": false,
    "detectionClasses": [0, 1, 2]
  }'
```

**Expected in WebSocket client:**
```json
{
  "event": "drone.created",
  "timestamp": "2025-12-04T12:00:00.000Z",
  "data": {
    "serialNumber": "TEST123",
    "droneId": "507f1f77bcf86cd799439011",
    "full": { /* full drone object */ }
  }
}
```

### Test 3: Update Drone Stream Status

```bash
curl -X PATCH http://localhost:5000/api/v1/drones/sn/TEST123 \
  -H "Content-Type: application/json" \
  -d '{
    "streamIsOn": true
  }'
```

**Expected events:**
1. `drone.updated` - General update event
2. `drone.stream.status` - Specific stream status change event

### Test 4: Subscribe to Specific Drone

In your WebSocket client JavaScript:

```javascript
// Subscribe to specific drone only
socket.emit('subscribe', { droneSerial: 'TEST123' });
```

Now you'll only receive events for drone TEST123.

---

## Redis Channels

Events are published to these Redis channels:

| Channel Pattern | Description | Example |
|----------------|-------------|---------|
| `drone:{serial}:created` | Drone created | `drone:TEST123:created` |
| `drone:{serial}:updated` | Drone updated | `drone:TEST123:updated` |
| `drone:{serial}:deleted` | Drone deleted | `drone:TEST123:deleted` |
| `drone:{serial}:stream` | Stream status | `drone:TEST123:stream` |
| `drone:{serial}:ai` | AI detection toggle | `drone:TEST123:ai` |
| `drone:{serial}:config` | Detection classes | `drone:TEST123:config` |
| `drone:{serial}:incident` | Incident detected | `drone:TEST123:incident` |
| `drone:all:created` | Global: new drone | `drone:all:created` |
| `drone:all:deleted` | Global: drone deleted | `drone:all:deleted` |
| `incidents:all` | All incidents | `incidents:all` |
| `system:broadcast` | System messages | `system:broadcast` |

---

## WebSocket Client API

### Connection

```javascript
const socket = io('http://localhost:5000', {
    path: '/ws/events'
});
```

### Events to Listen

```javascript
// Connection confirmed
socket.on('connected', (data) => {
    console.log('Connected:', data.clientId);
});

// Subscription confirmed
socket.on('subscribed', (data) => {
    console.log('Subscribed:', data);
});

// Drone events
socket.on('drone:event', (event) => {
    console.log('Drone event:', event);
});

// System events
socket.on('system:event', (event) => {
    console.log('System event:', event);
});

// Disconnection
socket.on('disconnect', () => {
    console.log('Disconnected');
});
```

### Events to Emit

```javascript
// Subscribe to all drone events
socket.emit('subscribe', { all: true });

// Subscribe to specific drone
socket.emit('subscribe', { droneSerial: 'TEST123' });

// Unsubscribe
socket.emit('unsubscribe');

// Ping (health check)
socket.emit('ping');
socket.on('pong', (data) => console.log('Pong:', data));
```

---

## Kubernetes Deployment

When deploying to Kubernetes with multiple replicas, Redis ensures all instances stay synchronized.

### Redis Deployment (if not using existing Redis)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:6.2
        ports:
        - containerPort: 6379
---
apiVersion: v1
kind: Service
metadata:
  name: redis
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
```

### Drone Management System Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: drone-management
spec:
  replicas: 3  # Multiple instances
  selector:
    matchLabels:
      app: drone-management
  template:
    metadata:
      labels:
        app: drone-management
    spec:
      containers:
      - name: drone-management
        image: your-registry/drone-management:latest
        env:
        - name: REDIS_URL
          value: "redis://redis:6379"  # Use Kubernetes service name
        - name: MONGODB_URI
          valueFrom:
            secretKeyRef:
              name: drone-secrets
              key: mongodb-uri
        ports:
        - containerPort: 5000
```

All 3 replicas will receive Redis events and broadcast to their connected WebSocket clients!

---

## Troubleshooting

### Redis Connection Failed

**Error:** `[Redis] Initialization failed`

**Solution:**
1. Check Redis is running: `redis-cli ping`
2. Verify REDIS_URL in `.env`
3. Check Docker container: `docker ps | grep redis`

### WebSocket Not Connecting

**Error:** WebSocket connection fails in browser

**Solution:**
1. Check server logs for WebSocket initialization
2. Verify path is `/ws/events`
3. Check CORS settings in `app.ts`
4. Ensure firewall allows port 5000

### Events Not Being Published

**Error:** No events received after drone update

**Solution:**
1. Check server logs for Redis publish messages
2. Verify controller has event publisher imports
3. Test Redis directly:
   ```bash
   redis-cli
   > SUBSCRIBE drone:*
   # Then update a drone in another terminal
   ```

### Multiple Event Duplicates

**Issue:** Receiving same event multiple times

**Reason:** Multiple detector instances or WebSocket clients subscribed

**Expected Behavior:** Each instance/client receives one copy

---

## Architecture Diagram

```
┌─────────────────┐
│   Frontend /    │
│   Detector      │◄──────┐
└─────────────────┘       │
                          │
┌─────────────────┐       │ WebSocket
│   Frontend /    │◄──────┤ (Socket.IO)
│   Detector      │       │
└─────────────────┘       │
                          │
┌─────────────────────────┴──────┐
│  Drone Management Server       │
│  ┌──────────────────────────┐  │
│  │  HTTP API (Express)      │  │
│  │  /api/v1/drones          │  │
│  └───────────┬──────────────┘  │
│              │                  │
│  ┌───────────▼──────────────┐  │
│  │  Controller (CRUD)       │  │
│  │  - Create/Update/Delete  │  │
│  └───────────┬──────────────┘  │
│              │                  │
│  ┌───────────▼──────────────┐  │
│  │  Event Publisher         │  │
│  │  - publishDroneCreated() │  │
│  │  - publishDroneUpdated() │  │
│  └───────────┬──────────────┘  │
│              │                  │
│  ┌───────────▼──────────────┐  │
│  │  Redis Manager           │  │
│  │  - publish()             │  │
│  │  - subscribe()           │  │
│  └───────────┬──────────────┘  │
│              │                  │
└──────────────┼──────────────────┘
               │
        ┌──────▼──────┐
        │   Redis     │
        │  Pub/Sub    │
        └──────┬──────┘
               │
        ┌──────▼──────────────────┐
        │  WebSocket Server       │
        │  - Subscribes to Redis  │
        │  - Broadcasts to clients│
        └─────────────────────────┘
```

---

## Next Steps

1. **Install dependencies**: `npm install redis socket.io`
2. **Configure Redis URL** in `.env`
3. **Start server**: `npm run dev`
4. **Test with HTML client** (test-websocket.html)
5. **Integrate with detector** (coming next!)

---

## Questions?

If you encounter issues:
1. Check server logs for errors
2. Verify Redis connection with `redis-cli ping`
3. Test WebSocket with the HTML test client
4. Check firewall rules for ports 5000 and 6379
