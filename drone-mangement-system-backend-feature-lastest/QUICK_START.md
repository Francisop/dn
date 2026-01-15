# Quick Start Guide - Redis + WebSocket Integration

## 🚀 In 5 Minutes

### 1. Install (30 seconds)

```bash
cd "/home/indepth-earth/jydestudios/End to End Survelience Software/Backend/drone-mangement-system-backend"
./install-redis-websocket.sh
```

### 2. Configure (30 seconds)

Edit `.env`:
```bash
REDIS_URL=redis://localhost:6379
```

### 3. Start Server (10 seconds)

```bash
npm run dev
```

### 4. Test (3 minutes)

Open `test-websocket-client.html` in browser → Click "Subscribe to All Drones"

Test API:
```bash
curl -X POST http://localhost:5000/api/v1/drones/register \
  -H "Content-Type: application/json" \
  -d '{"deviceSerialNumber":"TEST123","deviceName":"Test","deviceCategory":"Drone"}'
```

Watch event appear in browser! 🎉

---

## 📋 Files Added

```
src/services/
├── redisManager.ts          # Redis Pub/Sub client
├── websocketServer.ts       # WebSocket server
└── eventPublisher.ts        # Event publishing helpers

Modified:
├── src/controllers/droneController.ts    # + Event publishing
└── src/server.ts                         # + Init Redis & WebSocket

Test/Docs:
├── test-websocket-client.html           # Browser test client
├── REDIS_WEBSOCKET_SETUP.md             # Full guide
├── INTEGRATION_SUMMARY.md               # Architecture
├── QUICK_START.md                        # This file
└── install-redis-websocket.sh            # Auto installer
```

---

## 🔥 Key Commands

```bash
# Install dependencies
npm install redis socket.io

# Test Redis
redis-cli ping

# Start server
npm run dev

# Watch Redis events (debugging)
redis-cli
> SUBSCRIBE drone:*
```

---

## 📡 Event Types

| Event | Trigger |
|-------|---------|
| `drone.created` | POST /drones/register |
| `drone.updated` | PATCH /drones/:id or /drones/sn/:sn |
| `drone.deleted` | DELETE /drones/:id |
| `drone.stream.status` | Update streamIsOn field |
| `drone.ai.detection.toggled` | Update isUsingAiDetection field |
| `drone.detection.classes.changed` | Update detectionClasses field |

---

## 💡 WebSocket Client (JavaScript)

```javascript
const socket = io('http://localhost:5000', { path: '/ws/events' });

socket.on('connected', () => {
    socket.emit('subscribe', { all: true });  // or { droneSerial: 'DRONE123' }
});

socket.on('drone:event', (event) => {
    console.log(event.event, event.data);
});
```

---

## ✅ Testing Checklist

- [ ] `redis-cli ping` returns PONG
- [ ] Server starts without errors
- [ ] Test client connects
- [ ] Creating drone shows event in browser
- [ ] Updating drone shows event in browser

---

## 🐛 Troubleshooting

**Redis Error?**
```bash
docker ps | grep redis  # Check container running
```

**WebSocket Won't Connect?**
- Check server logs
- Verify path: `/ws/events`
- Check port 5000 is not blocked

**No Events?**
- Click "Subscribe to All Drones" in test client
- Check server logs for `[Redis] Published event...`

---

## 📚 Full Documentation

- **Setup:** `REDIS_WEBSOCKET_SETUP.md`
- **Architecture:** `INTEGRATION_SUMMARY.md`
- **Test Client:** Open `test-websocket-client.html`

---

## 🎯 What's Next?

### For Detector Integration:
- Add WebSocket client to Python detector
- Subscribe to drone events by serial number
- React to config changes in real-time

### For Frontend:
- Add Socket.IO to React/Vue/Angular app
- Display real-time drone status updates
- Show incident alerts instantly

---

**Need Help?** Check the full guides in `REDIS_WEBSOCKET_SETUP.md` and `INTEGRATION_SUMMARY.md`
