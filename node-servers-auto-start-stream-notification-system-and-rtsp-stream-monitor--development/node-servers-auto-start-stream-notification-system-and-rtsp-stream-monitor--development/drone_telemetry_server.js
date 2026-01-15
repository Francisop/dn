const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const mqtt = require('mqtt');
const axios = require('axios');

// Configuration
const PORT = process.env.PORT || 4000;
// const mqttBrokerUrl = 'mqtt://192.168.1.89:1883';
// const BASE_URL = 'http://192.168.1.89:6789/manage/api/v1';
const mqttBrokerUrl = 'mqtt://34.56.113.254:1883';
const BASE_URL = 'http://34.56.113.254:6789/manage/api/v1';
const STREAM_API_URL = `${BASE_URL}/live/streams/start`;
const DRONE_API_BASE_URL = 'http://127.0.0.1:5000/api/v1/drones';

// Retry configuration
const MAX_RETRY_ATTEMPTS = 10;
const INITIAL_RETRY_DELAY_MS = 2000; // Start with 2 seconds
const MAX_RETRY_DELAY_MS = 30000; // Max 30 seconds between retries
const RETRY_CHECK_INTERVAL_MS = 60000; // Check every 60 seconds if database is still down

// Load drones from database API
let droneSNs = [];
let dronesConfig = [];
let databaseConnected = false;
let retryCount = 0;

// Calculate exponential backoff delay with jitter
function calculateRetryDelay(attempt) {
    const exponentialDelay = Math.min(
        INITIAL_RETRY_DELAY_MS * Math.pow(2, attempt),
        MAX_RETRY_DELAY_MS
    );
    // Add random jitter (±20%)
    const jitter = exponentialDelay * 0.2 * (Math.random() - 0.5);
    return Math.floor(exponentialDelay + jitter);
}

// Sleep helper function
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function loadDronesFromAPI(attempt = 0) {
    try {
        console.log(`📡 Fetching drones from database API... (Attempt ${attempt + 1}/${MAX_RETRY_ATTEMPTS})`);
        const response = await axios.get(DRONE_API_BASE_URL, {
            timeout: 5000 // 5 second timeout
        });
        const drones = response.data.data.drones;

        console.log(drones)
        // Transform database drones to the format expected by this server
        dronesConfig = drones.map(drone => ({
            sn: drone.deviceSerialNumber,
            name: drone.deviceName,
            alias: drone.metadata?.alias || drone.deviceName,
            userName: drone.streamCredentials?.userName || '',
            password: drone.streamCredentials?.password || '',
            port: drone.streamCredentials?.port || '8554',
            cameras: drone.cameras || []
        }));

        droneSNs = dronesConfig.map(drone => drone.sn);
        console.log(`✅ Loaded ${droneSNs.length} drones from database:`, droneSNs);
        databaseConnected = true;
        retryCount = 0; // Reset retry count on success
        return true;
    } catch (error) {
        console.error(`❌ Failed to load drones from database (Attempt ${attempt + 1}):`, error.message);

        if (attempt < MAX_RETRY_ATTEMPTS - 1) {
            const delay = calculateRetryDelay(attempt);
            console.log(`⏳ Retrying in ${Math.round(delay / 1000)} seconds...`);
            await sleep(delay);
            return loadDronesFromAPI(attempt + 1);
        } else {
            console.log('⚠️ Max retry attempts reached. Will continue checking periodically...');
            databaseConnected = false;
            retryCount = attempt + 1;
            return false;
        }
    }
}

// Helper function to get drone's first camera ID
function getDroneFirstCamera(droneSN) {
    const drone = dronesConfig.find(d => d.sn === droneSN);
    return drone?.cameras?.[0] || null;
}

// Update drone stream status in database
async function updateDroneStreamStatus(droneSN, streamIsOn, streamUrl = '') {
    try {
        const payload = {
            streamIsOn: streamIsOn,
            streamUrl: streamUrl
        };

        const response = await axios.patch(
            `${DRONE_API_BASE_URL}/sn/${droneSN}`,
            payload,
            { headers: { 'Content-Type': 'application/json' } }
        );

        if (response.status === 200) {
            console.log(`📝 Updated database: ${droneSN} - streamIsOn: ${streamIsOn}`);
            return true;
        }
    } catch (error) {
        console.error(`❌ Failed to update database for ${droneSN}:`, error.message);
        return false;
    }
}

// Authentication token cache
let cachedToken = null;
let tokenExpiry = null;

// Track drones that have already started streaming
const startedStreams = new Set();

// Track last message time for each drone
const droneLastMessageTime = new Map();

// Inactivity timeout in milliseconds (30 seconds)
const INACTIVITY_TIMEOUT_MS = 25000;
// Check interval (every 10 seconds)
const CHECK_INTERVAL_MS = 10000;

// Monitor drone MQTT activity and reset streams if inactive
setInterval(async () => {
    const now = Date.now();
    for (const [droneSN, lastMessageTime] of droneLastMessageTime.entries()) {
        const timeSinceLastMessage = now - lastMessageTime;
        if (timeSinceLastMessage > INACTIVITY_TIMEOUT_MS) {
            console.log(`⚠️ Drone ${droneSN} inactive for ${Math.round(timeSinceLastMessage / 1000)}s - no MQTT data received`);
            if (startedStreams.has(droneSN)) {
                startedStreams.delete(droneSN);
                console.log(`🔄 Removed ${droneSN} from startedStreams - will restart when MQTT data resumes`);

                // Update database: stream is OFF due to inactivity
                await updateDroneStreamStatus(droneSN, false, '');
            }
            droneLastMessageTime.delete(droneSN);
        }
    }
}, CHECK_INTERVAL_MS);

// Periodic database connection check - retry if connection was lost
setInterval(async () => {
    if (!databaseConnected) {
        console.log('🔄 Database connection lost. Attempting to reconnect...');
        const success = await loadDronesFromAPI();

        if (success) {
            console.log('✅ Database connection restored!');
            // Subscribe to any new drones that weren't subscribed before
            subscribeToAllDrones();
        } else {
            console.log('❌ Database still unavailable. Will retry later.');
        }
    }
}, RETRY_CHECK_INTERVAL_MS);

// Function to start streaming for a drone

async function getAcessToken() {
  try {
    if (cachedToken && (!tokenExpiry || Date.now() < tokenExpiry)) {
      return cachedToken;
    }

    const response = await axios.post(
      `${BASE_URL}/login`,
      {
        username: "adminPC",
        password: "adminPC",
        flag: 1
      },
      { headers: { "Content-Type": "application/json" } }
    );

    // ✅ FIX: Get token from response headers (NOT response.data)
    const token = response.data.data.access_token;

    if (token) {
      cachedToken = token;
      console.log("✅ Token refreshed successfully:", token.slice(0, 20) + "..."); // partial log
      return cachedToken;
    } else {
      throw new Error("x-auth-token not found in headers");
    }
  } catch (error) {
    console.error("❌ Login failed:", error.response?.data || error.message);
    return null;
  }
}




async function startStream(droneSN) {
    // Check if stream already started for this drone
    if (startedStreams.has(droneSN)) {
        return;
    }

    try {
        // Get authentication token first
        const token = await getAcessToken();
        if (!token) {
            console.error(`Failed to get access token for drone ${droneSN}`);
            return;
        }

        // Fetch drone data from database API
        let drone = dronesConfig.find(d => d.sn === droneSN);

        // If not in cache, try fetching from API directly
        if (!drone) {
            console.log(`Drone ${droneSN} not in cache, fetching from API...`);

            // Try to fetch individual drone with retries
            let fetchAttempts = 0;
            const maxFetchAttempts = 3;

            while (fetchAttempts < maxFetchAttempts && !drone) {
                try {
                    const response = await axios.get(`${DRONE_API_BASE_URL}/sn/${droneSN}`, {
                        timeout: 5000
                    });
                    const dbDrone = response.data.data.drone;

                    // Transform to expected format
                    drone = {
                        sn: dbDrone.deviceSerialNumber,
                        name: dbDrone.deviceName,
                        alias: dbDrone.metadata?.alias || dbDrone.deviceName,
                        userName: dbDrone.streamCredentials?.userName || '',
                        password: dbDrone.streamCredentials?.password || '',
                        port: dbDrone.streamCredentials?.port || '8554',
                        cameras: dbDrone.cameras || []
                    };

                    // Add to cache
                    dronesConfig.push(drone);
                    if (!droneSNs.includes(droneSN)) {
                        droneSNs.push(droneSN);
                    }
                    console.log(`✅ Successfully fetched drone ${droneSN} from API`);
                } catch (apiError) {
                    fetchAttempts++;
                    console.error(`❌ Failed to fetch drone ${droneSN} from API (Attempt ${fetchAttempts}/${maxFetchAttempts}):`, apiError.message);

                    if (fetchAttempts < maxFetchAttempts) {
                        const retryDelay = 1000 * fetchAttempts; // 1s, 2s
                        console.log(`⏳ Retrying in ${retryDelay / 1000} seconds...`);
                        await sleep(retryDelay);
                    } else {
                        console.error(`❌ Max attempts reached. Cannot fetch drone ${droneSN}`);
                        databaseConnected = false; // Mark database as potentially down
                        return;
                    }
                }
            }
        }

        if (!drone) {
            console.error(`Drone not found in registry: ${droneSN}`);
            return;
        }

        console.log(`Starting stream for ${drone.alias} (${droneSN})`);

        // Use only the first camera
        const cameraId = drone.cameras[0];

        if (!cameraId) {
            console.error(`No camera configured for drone ${droneSN}`);
            return;
        }

        // Construct the payload
        const payload = {
            url: `userName=${drone.userName}&password=${drone.password}&port=${drone.port}`,
            url_type: 2,
            video_id: `${droneSN}/${cameraId}/thermal-0`,
            video_quality: 0
        };

        console.log(`Sending stream start request for camera: ${cameraId}`);

        // Make POST request to start stream with authentication token using axios
        const response = await axios.post(STREAM_API_URL, payload, {
            headers: {
                'Content-Type': 'application/json',
                'x-auth-token': token
            }
        });

        console.log(`Stream start response status for camera (${cameraId}):`, response.status, response.data.data.url);

        if (response.status === 200 || response.status === 201) {
            const streamUrl = response.data.data.url;
            console.log(`✅ Stream started for ${drone.alias} - Camera (${cameraId}):\n`, streamUrl);

            // Update database: stream is ON
            await updateDroneStreamStatus(droneSN, true, streamUrl);

            // Mark this drone as started
            startedStreams.add(droneSN);
            console.log(`Stream initiated for ${drone.alias}`);
        } else {
            console.error(`❌ Failed to start stream for camera (${cameraId}):`, response.status, response.statusText);
        }

    } catch (error) {
        console.error(`Error starting stream for drone ${droneSN}:`, error.response?.data || error.message);
    }
}




// Express setup
const app = express();
app.use(express.json());

// Server and Socket.IO setup
const server = http.createServer(app);
const io = socketIo(server, {
    cors: {
        origin: "*",
        methods: ["GET", "POST"]
    }
});

// Detection endpoint for YOLO server
app.post('/detection', (req, res) => {
    const { object_type, confidence, track_id, timestamp } = req.body;
    console.log(`🔍 New Detection: ${object_type} (ID: ${track_id}, Confidence: ${confidence})`);

    io.emit('newDetection', { object_type, confidence, track_id, timestamp });
    res.status(200).json({ status: 'success', message: 'Detection received' });
});

// Socket.IO connection handling
io.on('connection', (socket) => {
    console.log('A user connected to the web server');
    socket.on('disconnect', () => console.log('A user disconnected'));
});

// MQTT client setup
const mqttClient = mqtt.connect(mqttBrokerUrl);

mqttClient.on('connect', async () => {
    console.log('✅ Connected to MQTT broker!');

    // Load drones from database on startup with retry logic
    const success = await loadDronesFromAPI();

    if (success) {
        // Subscribe to MQTT topics for all registered drones
        subscribeToAllDrones();
    } else {
        console.log('⚠️ Failed to load drones from database. Server will continue running.');
        console.log('💡 Drones will be fetched when MQTT messages arrive or during periodic checks.');
    }
});

// Helper function to subscribe to all drone topics
function subscribeToAllDrones() {
    if (droneSNs.length === 0) {
        console.log('⚠️ No drones to subscribe to.');
        return;
    }

    console.log(`📡 Subscribing to ${droneSNs.length} drone topics...`);
    droneSNs.forEach(sn => {
        const topic = `thing/product/${sn}/osd`;
        mqttClient.subscribe(topic, (err) => {
            if (err) {
                console.error(`❌ Subscription failed for topic ${topic}:`, err);
            } else {
                console.log(`✅ Subscribed to topic: ${topic}`);
            }
        });
    });
}


mqttClient.on('message', (topic, message) => {
    try {
        const droneData = JSON.parse(message.toString());
        const sn = topic.split('/')[2];
        
        // Update last message timestamp for this drone
        droneLastMessageTime.set(sn, Date.now());

        // Emit drone data to connected clients
        io.emit('droneDataUpdate', droneData, sn);

        if (!droneData.data || typeof droneData.data !== 'object') {
            console.log(`⚠️ Drone ${sn}: No "data" field found in payload.`);
        } else {
            const firstCamera = getDroneFirstCamera(sn);
            if (firstCamera && droneData.data[firstCamera]) {
                // Camera is online - start stream if not already started
                if (!startedStreams.has(sn)){
                    startStream(sn);
                }

            } else {
                // Camera went offline - stop stream
                if (startedStreams.has(sn)) {
                    startedStreams.delete(sn);
                    console.log(`📴 Camera offline for ${sn}, stream stopped`);

                    // Update database: stream is OFF
                    updateDroneStreamStatus(sn, false, '');
                }
            }
        }


        // Start streaming for this drone (only once)
        
    } catch (e) {
        console.error('Failed to parse MQTT message:', e);
    }
});

mqttClient.on('error', (err) => {
    console.error('MQTT error:', err);
});

// Start server
server.listen(PORT, () => {
    console.log(`Server listening on port ${PORT}`);
    console.log(`Detection endpoint available at http://localhost:${PORT}/detection`);
});
