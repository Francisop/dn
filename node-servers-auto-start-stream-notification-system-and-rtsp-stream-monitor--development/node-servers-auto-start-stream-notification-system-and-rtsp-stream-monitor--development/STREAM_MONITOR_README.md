# Stream Monitor Server

A production-ready Node.js server that monitors RTSP/RTMP streams for BodyCam and CCTV devices, automatically updating database status when streams go online or offline.

## Features

✅ **Automatic Stream Health Monitoring** - Continuously checks RTSP/RTMP streams using FFmpeg
✅ **Database Integration** - Fetches devices from API and updates `streamIsOn` status
✅ **Device Type Filtering** - Only monitors BodyCam and CCTV devices (excludes drones)
✅ **Retry Logic** - Exponential backoff for failed API calls and stream checks
✅ **Smart Updates** - Only updates database when status actually changes
✅ **Production Logging** - Winston-based logging with file rotation and console output
✅ **Error Recovery** - Gracefully handles database disconnections and stream failures
✅ **Parallel Processing** - Checks all streams concurrently for efficiency
✅ **Graceful Shutdown** - Handles SIGINT/SIGTERM signals properly

## How It Works

1. **Loads Devices**: Fetches all devices from the Drone Management API
2. **Filters Devices**: Only monitors devices with `deviceCategory` = "BodyCam" or "CCTV"
3. **Checks Streams**: Uses FFmpeg to probe each device's `streamUrl` (RTSP/RTMP)
4. **Updates Database**: Sets `streamIsOn` to `true` (online) or `false` (offline)
5. **Repeats**: Runs health checks every 30 seconds (configurable)

## Configuration

The server can be configured using environment variables or a `.env` file.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONITOR_PORT` | `4001` | Server port (not used for HTTP, just for identification) |
| `DRONE_API_URL` | `http://127.0.0.1:5000/api/v1/drones` | Database API endpoint |
| `CHECK_INTERVAL_MS` | `30000` | How often to check streams (milliseconds) |
| `STREAM_TIMEOUT_MS` | `10000` | Stream probe timeout (milliseconds) |
| `MAX_RETRY_ATTEMPTS` | `3` | Max retries for API calls |
| `RETRY_DELAY_MS` | `5000` | Delay between retries (milliseconds) |
| `LOG_LEVEL` | `info` | Logging level (error, warn, info, debug) |

### Setup Configuration

1. Copy the example configuration:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your settings (optional, defaults work for most cases)

## Installation

All required dependencies are already in `package.json`:

- `fluent-ffmpeg` - FFmpeg wrapper for stream probing
- `@ffmpeg-installer/ffmpeg` - FFmpeg binaries
- `axios` - HTTP client for API calls
- `winston` - Production-grade logging

No additional installation needed if you've already run `npm install` in the node server folder.

## Usage

### Start Manually

```bash
cd "Backend/node server"
node stream_monitor_server.js
```

### Start with All Servers

The stream monitor is automatically included when you run:

```bash
start_all_servers.bat
```

This will open a dedicated terminal window titled "Backend - Stream Monitor".

## Output

### Console Output

```
2025-11-20 14:30:00 [INFO]: ============================================================
2025-11-20 14:30:00 [INFO]: 🎥 Stream Monitoring Service for BodyCam & CCTV Devices
2025-11-20 14:30:00 [INFO]: ============================================================
2025-11-20 14:30:00 [INFO]: API URL: http://127.0.0.1:5000/api/v1/drones
2025-11-20 14:30:00 [INFO]: Check Interval: 30s
2025-11-20 14:30:00 [INFO]: Stream Timeout: 10s
2025-11-20 14:30:00 [INFO]: Monitored Device Types: BodyCam, CCTV, bodycam, cctv
2025-11-20 14:30:00 [INFO]: ============================================================

2025-11-20 14:30:01 [INFO]: 📡 Fetching devices from API... (Attempt 1/3)
2025-11-20 14:30:01 [INFO]: ✅ Loaded 5 devices (Total: 12, Filtered: BodyCam/CCTV only)
2025-11-20 14:30:01 [INFO]:    - Officer Smith BodyCam (BodyCam) - SN: BC001
2025-11-20 14:30:01 [INFO]:    - Entrance Camera (CCTV) - SN: CCTV001
2025-11-20 14:30:01 [INFO]:    - Parking Lot Camera (CCTV) - SN: CCTV002

2025-11-20 14:30:02 [INFO]: 🔍 Starting stream health check cycle...
2025-11-20 14:30:03 [INFO]: ✅ Officer Smith BodyCam (BC001): Stream ONLINE - rtsp (2 streams)
2025-11-20 14:30:03 [INFO]: 📝 Updated database: BC001 - streamIsOn: true
2025-11-20 14:30:04 [ERROR]: ❌ Entrance Camera (CCTV001): Stream OFFLINE - Connection timeout
2025-11-20 14:30:04 [INFO]: 📝 Updated database: CCTV001 - streamIsOn: false
2025-11-20 14:30:05 [INFO]: 📊 Check cycle completed in 3.45s - Online: 3, Offline: 2, Errors: 0
```

### Log Files

- `stream-monitor.log` - All logs (info, warn, error)
- `stream-monitor-error.log` - Error logs only
- Automatic rotation at 5MB, keeps last 5 files

## API Integration

### Required API Endpoints

The server uses these endpoints from the Drone Management API:

1. **GET** `/api/v1/drones` - Fetch all devices
2. **PATCH** `/api/v1/drones/sn/:serialNumber` - Update device status

### Expected Device Schema

```json
{
  "deviceSerialNumber": "BC001",
  "deviceName": "Officer Smith BodyCam",
  "deviceCategory": "BodyCam",
  "streamUrl": "rtsp://username:password@192.168.1.100:554/stream1",
  "streamIsOn": false,
  "metadata": {
    "alias": "Officer Smith BodyCam"
  }
}
```

## Stream URL Formats

Supports RTSP and RTMP protocols:

### RTSP Examples
```
rtsp://192.168.1.100:554/stream1
rtsp://username:password@192.168.1.100:554/stream1
rtsp://admin:pass123@camera.local:8554/live/main
```

### RTMP Examples
```
rtmp://192.168.1.100:1935/live/stream1
rtmp://server.com/live/camera1
```

## Monitoring Behavior

### Stream Online Detection
- FFmpeg successfully probes the stream
- At least one valid video or audio stream detected
- Database updated: `streamIsOn = true`

### Stream Offline Detection
- Connection timeout (>10 seconds)
- FFmpeg probe fails
- No valid streams found
- Empty or invalid stream URL
- Database updated: `streamIsOn = false`

### Status Change Only Updates
The server only updates the database when status **actually changes**:
- Avoids unnecessary database writes
- Reduces API load
- Uses in-memory cache to track previous status

## Troubleshooting

### No devices found
- Check that devices have `deviceCategory` set to "BodyCam" or "CCTV"
- Verify database API is running on port 5000
- Check `DRONE_API_URL` environment variable

### Stream check timeout
- Increase `STREAM_TIMEOUT_MS` (default: 10000ms)
- Verify stream URL is correct and accessible
- Check network connectivity to stream source

### Database update failures
- Ensure Drone Management API is running
- Check MongoDB connection
- Verify API endpoint `/api/v1/drones/sn/:sn` exists

### FFmpeg errors
- FFmpeg is automatically installed via `@ffmpeg-installer/ffmpeg`
- If issues persist, check `ffmpeg -version` manually

## Performance

- **Parallel Processing**: All streams checked concurrently using `Promise.allSettled`
- **Typical Check Time**: 3-5 seconds for 10 devices
- **Memory Usage**: ~50-100MB for 20-30 devices
- **CPU Usage**: Minimal (mostly I/O bound)

## Graceful Shutdown

Press `Ctrl+C` to stop the server:

```
📴 Received SIGINT. Gracefully shutting down...
✅ Stream monitoring service stopped
```

The server waits 2 seconds for ongoing checks to complete before exiting.

## Production Deployment

### Recommended Settings

```env
CHECK_INTERVAL_MS=60000      # Check every 60 seconds
STREAM_TIMEOUT_MS=15000      # 15 second timeout
MAX_RETRY_ATTEMPTS=5         # More retries for reliability
LOG_LEVEL=info              # Balance between detail and noise
```

### Process Management

Use PM2 for production:

```bash
npm install -g pm2
pm2 start stream_monitor_server.js --name "stream-monitor"
pm2 save
pm2 startup
```

## Architecture

```
┌─────────────────────────────────────────┐
│   Stream Monitor Server (Node.js)      │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │  Device Loader                    │ │
│  │  - Fetches from API               │ │
│  │  - Filters BodyCam/CCTV           │ │
│  │  - Retry logic                    │ │
│  └───────────────────────────────────┘ │
│            ↓                            │
│  ┌───────────────────────────────────┐ │
│  │  Stream Health Checker            │ │
│  │  - FFmpeg probe (parallel)        │ │
│  │  - Timeout handling               │ │
│  │  - Status caching                 │ │
│  └───────────────────────────────────┘ │
│            ↓                            │
│  ┌───────────────────────────────────┐ │
│  │  Database Updater                 │ │
│  │  - Update streamIsOn              │ │
│  │  - Change detection               │ │
│  │  - Retry mechanism                │ │
│  └───────────────────────────────────┘ │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │  Winston Logger                   │ │
│  │  - Console + File                 │ │
│  │  - Log rotation                   │ │
│  └───────────────────────────────────┘ │
└─────────────────────────────────────────┘
        ↓                    ↑
        ↓                    ↑
┌────────────────┐   ┌──────────────────┐
│  RTSP/RTMP     │   │  Drone Mgmt API  │
│  Streams       │   │  (Port 5000)     │
│  (BodyCam/CCTV)│   │  + MongoDB       │
└────────────────┘   └──────────────────┘
```

## License

Part of the End to End Surveillance Software system.