const express = require('express');
const { createServer } = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const Database = require('better-sqlite3');
const { hash } = require('imghash');
const hammingDistance = require('hamming-distance');

const app = express();
const httpServer = createServer(app);
const io = new Server(httpServer, {
  cors: {
    origin: "*", // Allow all origins for development
    methods: ["GET", "POST"]
  }
});

// Initialize SQLite database
const db = new Database('detections.db');

// Create detections table
db.exec(`
  CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_class TEXT NOT NULL,
    track_id INTEGER NOT NULL,
    confidence REAL NOT NULL,
    timestamp TEXT NOT NULL,
    device_name TEXT NOT NULL,
    device_type TEXT NOT NULL,
    bbox_x1 INTEGER NOT NULL,
    bbox_y1 INTEGER NOT NULL,
    bbox_x2 INTEGER NOT NULL,
    bbox_y2 INTEGER NOT NULL,
    frame_base64 TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );

  CREATE INDEX IF NOT EXISTS idx_timestamp ON detections(timestamp);
  CREATE INDEX IF NOT EXISTS idx_device ON detections(device_name);
  CREATE INDEX IF NOT EXISTS idx_class ON detections(object_class);
`);

// Prepared statements for performance
const insertDetection = db.prepare(`
  INSERT INTO detections
  (object_class, track_id, confidence, timestamp, device_name, device_type,
   bbox_x1, bbox_y1, bbox_x2, bbox_y2, frame_base64)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);

const getRecentDetections = db.prepare(`
  SELECT * FROM detections
  ORDER BY created_at DESC
  LIMIT ?
`);

const getDetectionStats = db.prepare(`
  SELECT
    object_class,
    COUNT(*) as count,
    device_name
  FROM detections
  WHERE created_at >= datetime('now', '-24 hours')
  GROUP BY object_class, device_name
  ORDER BY count DESC
`);

// Store recent detections with image hashes
const recentDetections = new Map(); // { hash: { timestamp, data } }

// Configuration
const SIMILARITY_THRESHOLD = 5; // Hamming distance <= 5 = similar (out of 64 bits for 8-bit hash)
const DETECTION_WINDOW = 30000; // 30 seconds
const MAX_STORED_DETECTIONS = 100; // Prevent memory leak

console.log('📊 Database initialized: detections.db');

// Middleware
app.use(cors());
app.use((req, res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.url}`);
  next();
});
app.use(express.json({ limit: '50mb' }));

// Socket.IO connection handler
io.on('connection', (socket) => {
  console.log(`🔌 Client connected: ${socket.id}`);

  socket.on('disconnect', () => {
    console.log(`🔌 Client disconnected: ${socket.id}`);
  });
});

// Cleanup old detections periodically
setInterval(() => {
  const now = Date.now();
  let removed = 0;

  for (const [hash, detection] of recentDetections.entries()) {
    if (now - detection.timestamp > DETECTION_WINDOW) {
      recentDetections.delete(hash);
      removed++;
    }
  }

  if (removed > 0) {
    console.log(`🧹 Cleaned up ${removed} old detections`);
  }
}, 10000); // Every 10 seconds

// POST endpoint at /notify
app.post('/notify', async (req, res) => {
  try {
    const { object_class, track_id, frame_base64, bbox, device_name, device_type, confidence, timestamp } = req.body;

    console.log(`📥 Received: ${object_class}#${track_id} from ${device_name}`);

    if (!frame_base64) {
      console.log('⚠️  No frame_base64 provided, accepting without image filtering');
      return res.status(200).json({
        success: true,
        message: 'Notification accepted (no image filtering)',
        filtered: false
      });
    }

    // Decode base64 frame to buffer
    const imageBuffer = Buffer.from(frame_base64, 'base64');

    // Calculate perceptual hash (8-bit for speed)
    const currentHash = await hash(imageBuffer, 8);

    // Check against recent detections
    let isDuplicate = false;
    let minDistance = Infinity;
    const now = Date.now();

    for (const [storedHash, detection] of recentDetections.entries()) {
      // Only compare same object class and device
      if (detection.data.object_class !== object_class) continue;
      if (detection.data.device_name !== device_name) continue;

      // Calculate Hamming distance (lower = more similar)
      const distance = hammingDistance(currentHash, storedHash);

      if (distance < minDistance) {
        minDistance = distance;
      }

      if (distance <= SIMILARITY_THRESHOLD) {
        isDuplicate = true;
        console.log(`🚫 Duplicate filtered: ${object_class}#${track_id} (distance: ${distance})`);
        break;
      }
    }

    if (!isDuplicate) {
      // Limit stored detections to prevent memory leak
      if (recentDetections.size >= MAX_STORED_DETECTIONS) {
        const oldestKey = recentDetections.keys().next().value;
        recentDetections.delete(oldestKey);
      }

      // Store this detection
      recentDetections.set(currentHash, {
        timestamp: now,
        data: req.body
      });

      console.log(`✅ Unique detection accepted: ${object_class}#${track_id} (stored ${recentDetections.size})`);

      // Save to database
      try {
        insertDetection.run(
          object_class,
          track_id,
          confidence,
          timestamp,
          device_name,
          device_type,
          bbox.x1,
          bbox.y1,
          bbox.x2,
          bbox.y2,
          frame_base64
        );
        console.log(`💾 Detection saved to database`);
      } catch (dbError) {
        console.error(`❌ Database error:`, dbError);
      }

      // Emit to all connected Socket.IO clients
      io.emit('new-detection', {
        id: Date.now(), // Temporary ID until we fetch from DB
        object_class,
        track_id,
        confidence,
        timestamp,
        device_name,
        device_type,
        bbox,
        frame_base64,
        created_at: new Date().toISOString()
      });
      console.log(`📡 Detection broadcasted to ${io.engine.clientsCount} clients`);

      res.status(200).json({
        success: true,
        message: 'Unique detection accepted',
        filtered: false,
        hamming_distance: minDistance === Infinity ? 'N/A' : minDistance,
        stored_detections: recentDetections.size
      });
    } else {
      console.log(`⏭️  Skipped duplicate detection`);
      res.status(200).json({
        success: true,
        message: 'Duplicate filtered by image similarity',
        filtered: true,
        hamming_distance: minDistance
      });
    }

  } catch (error) {
    console.error('❌ Error processing detection:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Get recent detections
app.get('/detections', (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 50;
    const detections = getRecentDetections.all(limit);
    res.json({
      success: true,
      count: detections.length,
      detections
    });
  } catch (error) {
    console.error('❌ Error fetching detections:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Get detection statistics
app.get('/stats', (_req, res) => {
  try {
    const stats = getDetectionStats.all();
    res.json({
      success: true,
      stats
    });
  } catch (error) {
    console.error('❌ Error fetching stats:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// Health check endpoint
app.get('/health', (req, res) => {
  console.log('🏥 Health check');
  res.status(200).json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    stored_detections: recentDetections.size,
    connected_clients: io.engine.clientsCount,
    config: {
      hamming_threshold: SIMILARITY_THRESHOLD + ' (distance)',
      detection_window: DETECTION_WINDOW / 1000 + 's',
      max_stored: MAX_STORED_DETECTIONS
    }
  });
});

// Start server on port 9000, bind to all interfaces
const PORT = 9000;
const HOST = '0.0.0.0';
httpServer.listen(PORT, HOST, () => {
  console.log(`🚀 Notification server running on http://${HOST}:${PORT}`);
  console.log(`📍 POST http://192.168.1.89:${PORT}/notify - Submit detection`);
  console.log(`📊 GET http://192.168.1.89:${PORT}/detections - Get recent detections`);
  console.log(`📈 GET http://192.168.1.89:${PORT}/stats - Get detection statistics`);
  console.log(`🏥 GET http://192.168.1.89:${PORT}/health - Health check`);
  console.log(`🔌 Socket.IO running on port ${PORT}`);
  console.log(`📊 Hamming distance threshold: ${SIMILARITY_THRESHOLD} (lower = more similar)`);
  console.log(`⏱️  Detection window: ${DETECTION_WINDOW / 1000}s`);
});
