# Real-Time Event Broadcasting Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Drone Management System                          │
│                     (Node.js + TypeScript)                          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         HTTP API Layer                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Express Routes: /api/v1/drones                              │  │
│  │  - POST   /register            (Create drone)                │  │
│  │  - GET    /                    (Get all drones)              │  │
│  │  - GET    /:id                 (Get drone by ID)             │  │
│  │  - GET    /sn/:sn              (Get drone by serial)         │  │
│  │  - PATCH  /:id                 (Update drone by ID)          │  │
│  │  - PATCH  /sn/:sn              (Update drone by serial)      │  │
│  │  - DELETE /:id                 (Delete drone)                │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Controller Layer                                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  droneController.ts                                          │  │
│  │                                                              │  │
│  │  1. Receive HTTP request                                    │  │
│  │  2. Fetch old data (for updates)                            │  │
│  │  3. Perform MongoDB operation                               │  │
│  │  4. Publish event to Redis ─────────┐                       │  │
│  │  5. Return HTTP response            │                       │  │
│  └─────────────────────────────────────┼───────────────────────┘  │
└─────────────────────────────────────────┼───────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Event Publisher Layer                             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  eventPublisher.ts                                           │  │
│  │                                                              │  │
│  │  • publishDroneCreated()         ─► drone:{sn}:created      │  │
│  │  • publishDroneUpdated()         ─► drone:{sn}:updated      │  │
│  │  • publishDroneDeleted()         ─► drone:{sn}:deleted      │  │
│  │  • publishStreamStatusChanged()  ─► drone:{sn}:stream       │  │
│  │  • publishAIDetectionToggled()   ─► drone:{sn}:ai           │  │
│  │  • publishDetectionClasses...()  ─► drone:{sn}:config       │  │
│  │                                                              │  │
│  │  Change Detection:                                           │  │
│  │  - Compares old vs new data                                 │  │
│  │  - Only publishes what changed                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Redis Manager                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  redisManager.ts                                             │  │
│  │                                                              │  │
│  │  Publisher Client  ──► publish(channel, event)              │  │
│  │  Subscriber Client ──► subscribe(channel, callback)         │  │
│  │                                                              │  │
│  │  Features:                                                   │  │
│  │  • Auto-reconnect                                            │  │
│  │  • Error handling                                            │  │
│  │  • Pattern matching (drone:*)                               │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       Redis Pub/Sub                                  │
│           (Message Broker - cloud_api_sample_redis_1)               │
│                                                                      │
│  Channels:                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  drone:SERIAL123:created    ──► Drone created               │   │
│  │  drone:SERIAL123:updated    ──► Drone updated               │   │
│  │  drone:SERIAL123:stream     ──► Stream toggled              │   │
│  │  drone:SERIAL123:ai         ──► AI detection toggled        │   │
│  │  drone:SERIAL123:config     ──► Detection classes changed   │   │
│  │  drone:SERIAL123:deleted    ──► Drone deleted               │   │
│  │  drone:all:*                ──► Global events               │   │
│  │  system:broadcast           ──► System messages             │   │
│  └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              │                                   │
              ▼                                   ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│    WebSocket Server          │  │   Other Subscribers          │
│  (Socket.IO)                 │  │   (Future: Detector, etc.)   │
│                              │  │                              │
│  websocketServer.ts          │  │  Python Detector Client      │
│                              │  │  Frontend Dashboard          │
│  • Subscribe to drone:*      │  │  Monitoring Services         │
│  • Subscribe to system:*     │  │                              │
│  • Broadcast to clients      │  │                              │
└──────────────┬───────────────┘  └──────────────────────────────┘
               │
               │  Emit: 'drone:event'
               │  Emit: 'system:event'
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      WebSocket Clients                               │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │  Browser Client  │  │  Python Detector │  │  Frontend App    │ │
│  │  (Test HTML)     │  │  (Coming Soon)   │  │  (Dashboard)     │ │
│  │                  │  │                  │  │                  │ │
│  │  Subscribe:      │  │  Subscribe:      │  │  Subscribe:      │ │
│  │  • All drones    │  │  • Specific SN   │  │  • All drones    │ │
│  │                  │  │                  │  │                  │ │
│  │  Receive:        │  │  React to:       │  │  Display:        │ │
│  │  • Real-time     │  │  • Stream toggle │  │  • Live status   │ │
│  │    events        │  │  • Config change │  │  • Incidents     │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Example: Update Drone Stream Status

```
1. HTTP Request:
   PATCH /api/v1/drones/sn/DRONE123
   { "streamIsOn": true }
         │
         ▼
2. Controller (droneController.ts):
   • Fetch old drone data (streamIsOn: false)
   • Update MongoDB
   • Detect change: streamIsOn changed from false to true
         │
         ▼
3. Event Publisher:
   • publishDroneUpdated(oldData, newData)
   • publishStreamStatusChanged(drone, false, true)
         │
         ▼
4. Redis Manager:
   • publish('drone:DRONE123:updated', {...})
   • publish('drone:DRONE123:stream', {...})
         │
         ▼
5. Redis Pub/Sub:
   • Distributes to all subscribers
         │
         ├──────────────────────┬──────────────────────┐
         ▼                      ▼                      ▼
6a. WebSocket Server     6b. Detector Instance  6c. Future Services
    • Receives from Redis    • Subscribes to       • Monitoring
    • Broadcasts to clients    drone:DRONE123:*    • Analytics
                              • Starts streaming    • Logging
         │
         ▼
7. Browser Client:
   • Receives: drone:event
   • Displays: "DRONE123 stream started"
```

---

## Multi-Instance Architecture (Kubernetes)

```
┌────────────────────────────────────────────────────────────────────┐
│                         Load Balancer                               │
│                      (Kubernetes Service)                           │
└───────────┬────────────────────────────────────────────────────────┘
            │
            │  HTTP Requests distributed
            │
    ┌───────┴────────┬────────────────┬────────────────┐
    │                │                │                │
    ▼                ▼                ▼                ▼
┌────────┐      ┌────────┐      ┌────────┐      ┌────────┐
│ API    │      │ API    │      │ API    │      │ API    │
│ Pod 1  │      │ Pod 2  │      │ Pod 3  │      │ Pod N  │
└───┬────┘      └───┬────┘      └───┬────┘      └───┬────┘
    │               │               │               │
    │  Publish      │  Publish      │  Publish      │  Publish
    │  Events       │  Events       │  Events       │  Events
    │               │               │               │
    └───────┬───────┴───────┬───────┴───────┬───────┘
            │               │               │
            ▼               ▼               ▼
    ┌───────────────────────────────────────────────┐
    │           Redis Pub/Sub (Shared)              │
    │      (Single Instance or Cluster)             │
    └───────────────────────────────────────────────┘
            │               │               │
            │  Subscribe    │  Subscribe    │  Subscribe
            │               │               │
    ┌───────┴───────┬───────┴───────┬───────┴───────┐
    │               │               │               │
    ▼               ▼               ▼               ▼
┌────────┐      ┌────────┐      ┌────────┐      ┌────────┐
│Detector│      │Detector│      │Detector│      │Detector│
│ Pod 1  │      │ Pod 2  │      │ Pod 3  │      │ Pod N  │
│(DRONE1)│      │(DRONE2)│      │(DRONE3)│      │(DRONEN)│
└────────┘      └────────┘      └────────┘      └────────┘

• Each API pod publishes to Redis when database changes
• Each Detector pod subscribes to its specific drone channel
• Redis ensures all subscribers receive events
• No polling needed - everything is push-based
```

---

## Event Lifecycle

```
User Action                Database Change           Event Published
    │                            │                         │
    ▼                            ▼                         ▼
┌─────────┐                 ┌─────────┐             ┌───────────┐
│ Create  │ ─────────────► │ MongoDB │ ──────────► │   Redis   │
│  Drone  │                 │ INSERT  │             │  PUBLISH  │
└─────────┘                 └─────────┘             └─────┬─────┘
                                                          │
                                                          │
    User Action                Database Change            │
        │                            │                    │
        ▼                            ▼                    │
    ┌─────────┐                 ┌─────────┐              │
    │ Update  │ ─────────────► │ MongoDB │ ─────────────┤
    │  Drone  │                 │ UPDATE  │              │
    └─────────┘                 └─────────┘              │
                                                          │
                                                          │
    User Action                Database Change            │
        │                            │                    │
        ▼                            ▼                    │
    ┌─────────┐                 ┌─────────┐              │
    │ Delete  │ ─────────────► │ MongoDB │ ─────────────┤
    │  Drone  │                 │ DELETE  │              │
    └─────────┘                 └─────────┘              │
                                                          │
                                                          ▼
                                                    All Subscribers
                                                    Receive Event
                                                          │
                                    ┌─────────────────────┼─────────────────────┐
                                    │                     │                     │
                                    ▼                     ▼                     ▼
                              WebSocket Clients    Detector Instances    Other Services
```

---

## Change Detection Flow

```
User Updates Drone:
PATCH /drones/sn/DRONE123
{
  "streamIsOn": true,
  "detectionClasses": [0, 1, 2, 3]
}

Controller Flow:
┌──────────────────────────────────────────────────────────────┐
│ 1. Fetch Old Data:                                           │
│    oldDrone = { streamIsOn: false, detectionClasses: [0, 1] }│
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. Update MongoDB:                                           │
│    newDrone = { streamIsOn: true, detectionClasses: [0,1,2,3]}│
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. Detect Changes:                                           │
│    • streamIsOn: false → true (CHANGED)                      │
│    • detectionClasses: [0,1] → [0,1,2,3] (CHANGED)          │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. Publish Multiple Events:                                 │
│    ✓ drone.updated (general update with all changes)        │
│    ✓ drone.stream.status (specific: stream toggled)         │
│    ✓ drone.detection.classes.changed (specific: classes)    │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    All Subscribers Notified
```

---

## Benefits of This Architecture

### 1. Real-Time Updates
- No polling
- Instant notification
- Sub-second latency

### 2. Scalability
- Supports unlimited clients
- Works with multiple instances
- Redis handles distribution

### 3. Reliability
- Auto-reconnect
- Error handling
- Graceful degradation

### 4. Flexibility
- Subscribe to all or specific drones
- Multiple event types
- Extensible for future needs

### 5. Performance
- Efficient Pub/Sub
- Only publishes changes
- Minimal overhead

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| API | Express + TypeScript | HTTP endpoints |
| Database | MongoDB + Mongoose | Data persistence |
| Message Broker | Redis Pub/Sub | Event distribution |
| WebSocket | Socket.IO | Real-time client connections |
| Protocol | WebSocket + Polling fallback | Browser compatibility |

---

## Security Considerations

### Current (MVP)
- CORS enabled for all origins
- No WebSocket authentication
- Redis without password

### Production Recommendations
1. **WebSocket Auth:**
   ```javascript
   socket.on('connection', (socket) => {
       const token = socket.handshake.auth.token;
       if (!verifyToken(token)) {
           socket.disconnect();
       }
   });
   ```

2. **Redis Password:**
   ```bash
   REDIS_URL=redis://username:password@host:6379
   ```

3. **Rate Limiting:**
   ```javascript
   // Limit events per client
   const limiter = rateLimit({ windowMs: 60000, max: 100 });
   ```

4. **Channel Filtering:**
   ```javascript
   // Only allow subscribing to owned drones
   if (!userOwnsDrone(user, droneSerial)) {
       socket.emit('error', 'Unauthorized');
   }
   ```

---

This architecture provides a solid foundation for real-time event broadcasting that scales with your needs!
