const axios = require('axios');
const ffmpeg = require('fluent-ffmpeg');
const ffmpegPath = require('@ffmpeg-installer/ffmpeg').path;
const ffprobePath = require('@ffprobe-installer/ffprobe').path;
const winston = require('winston');

// Set ffmpeg path
ffmpeg.setFfmpegPath(ffmpegPath);
ffmpeg.setFfprobePath(ffprobePath);

// ============================================================
// Configuration
// ============================================================
const PORT = process.env.MONITOR_PORT || 4001;
const DRONE_API_BASE_URL = process.env.DRONE_API_URL || 'http://127.0.0.1:5000/api/v1/drones';
const CHECK_INTERVAL_MS = parseInt(process.env.CHECK_INTERVAL_MS) || 30000; // 30 seconds
const STREAM_TIMEOUT_MS = parseInt(process.env.STREAM_TIMEOUT_MS) || 10000; // 10 seconds
const MAX_RETRY_ATTEMPTS = parseInt(process.env.MAX_RETRY_ATTEMPTS) || 3;
const RETRY_DELAY_MS = parseInt(process.env.RETRY_DELAY_MS) || 5000; // 5 seconds

// Device types to monitor (exclude drones)
const MONITORED_DEVICE_TYPES = ['BODY CAM', "CCTV"];

// ============================================================
// Logging Setup
// ============================================================
const logger = winston.createLogger({
    level: process.env.LOG_LEVEL || 'info',
    format: winston.format.combine(
        winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }), 
        winston.format.errors({ stack: true }),
        winston.format.printf(({ timestamp, level, message, stack }) => {
            return `${timestamp} [${level.toUpperCase()}]: ${message}${stack ? '\n' + stack : ''}`;
        })
    ),
    transports: [
        new winston.transports.Console({
            format: winston.format.combine(
                winston.format.colorize(),
                winston.format.printf(({ timestamp, level, message }) => {
                    return `${timestamp} [${level}]: ${message}`;
                })
            )
        }),
        new winston.transports.File({
            filename: 'stream-monitor-error.log',
            level: 'error',
            maxsize: 5242880, // 5MB
            maxFiles: 5
        }),
        new winston.transports.File({
            filename: 'stream-monitor.log',
            maxsize: 5242880, // 5MB
            maxFiles: 5
        })
    ]
});

// ============================================================
// State Management
// ============================================================
let devices = [];
let deviceStatusCache = new Map(); // Track previous status to avoid unnecessary updates
let isMonitoring = false;
let databaseConnected = false;

// ============================================================
// Utility Functions
// ============================================================

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function isMonitoredDeviceType(deviceCategory) {
    return MONITORED_DEVICE_TYPES.some(type =>
        deviceCategory && deviceCategory.toLowerCase() === type.toLowerCase()
    );
}

// ============================================================
// Database Functions
// ============================================================

async function loadDevicesFromAPI(attempt = 0) {
    try {
        logger.info(`📡 Fetching devices from API... (Attempt ${attempt + 1}/${MAX_RETRY_ATTEMPTS})`);

        const response = await axios.get(DRONE_API_BASE_URL, {
            timeout: 5000
        });

        if (!response.data || !response.data.data || !response.data.data.drones) {
            throw new Error('Invalid API response structure');
        }

        const allDevices = response.data.data.drones;

        // Filter only body cams and CCTV devices
        devices = allDevices.filter(device => isMonitoredDeviceType(device.deviceCategory));

        logger.info(`✅ Loaded ${devices.length} devices (Total: ${allDevices.length}, Filtered: BodyCam/CCTV only)`);

        if (devices.length > 0) {
            devices.forEach(device => {
                logger.info(`   - ${device.deviceName} (${device.deviceCategory}) - SN: ${device.deviceSerialNumber}`);
            });
        } else {
            logger.warn('⚠️ No BodyCam or CCTV devices found in database');
        }

        databaseConnected = true;
        return true;

    } catch (error) {
        logger.error(`❌ Failed to load devices (Attempt ${attempt + 1}): ${error.message}`);

        if (attempt < MAX_RETRY_ATTEMPTS - 1) {
            const delay = RETRY_DELAY_MS * (attempt + 1);
            logger.info(`⏳ Retrying in ${delay / 1000} seconds...`);
            await sleep(delay);
            return loadDevicesFromAPI(attempt + 1);
        } else {
            logger.error('⚠️ Max retry attempts reached. Will continue checking periodically...');
            databaseConnected = false;
            return false;
        }
    }
}

async function updateDeviceStreamStatus(serialNumber, streamIsOn, retryAttempt = 0) {
    try {
        const payload = {
            streamIsOn: streamIsOn
        };

        const response = await axios.patch(
            `${DRONE_API_BASE_URL}/sn/${serialNumber}`,
            payload,
            {
                headers: { 'Content-Type': 'application/json' },
                timeout: 5000
            }
        );

        if (response.status === 200) {
            logger.info(`📝 Updated database: ${serialNumber} - streamIsOn: ${streamIsOn}`);
            return true;
        }

        return false;

    } catch (error) {
        logger.error(`❌ Failed to update device ${serialNumber}: ${error.message}`);

        // Retry logic for database updates
        if (retryAttempt < 2) {
            logger.info(`⏳ Retrying database update (attempt ${retryAttempt + 2}/3)...`);
            await sleep(2000);
            return updateDeviceStreamStatus(serialNumber, streamIsOn, retryAttempt + 1);
        }

        databaseConnected = false;
        return false;
    }
}

// ============================================================
// Stream Health Check Functions
// ============================================================

function checkStreamHealth(streamUrl) {
    return new Promise((resolve, reject) => {
        if (!streamUrl || streamUrl.trim() === '') {
            reject(new Error('Empty or invalid stream URL'));
            return;
        }

        const timeoutHandle = setTimeout(() => {
            reject(new Error('Stream check timeout'));
        }, STREAM_TIMEOUT_MS);

        ffmpeg.ffprobe(streamUrl, { timeout: STREAM_TIMEOUT_MS / 1000 }, (err, metadata) => {
            clearTimeout(timeoutHandle);

            if (err) {
                reject(err);
                return;
            }

            // Check if stream has valid video or audio streams
            if (!metadata.streams || metadata.streams.length === 0) {
                reject(new Error('No streams found in media'));
                return;
            }

            // Check for video or audio stream
            const hasVideoOrAudio = metadata.streams.some(
                stream => stream.codec_type === 'video' || stream.codec_type === 'audio'
            );

            if (hasVideoOrAudio) {
                resolve({
                    isOnline: true,
                    format: metadata.format?.format_name,
                    duration: metadata.format?.duration,
                    bitrate: metadata.format?.bit_rate,
                    streams: metadata.streams.length
                });
            } else {
                reject(new Error('No valid video or audio streams found'));
            }
        });
    });
}

async function checkDeviceStream(device) {
    const serialNumber = device.deviceSerialNumber;
    const deviceName = device.metadata?.alias || device.deviceName;
    const streamUrl = device.streamUrl;

    // Skip if no stream URL configured
    if (!streamUrl || streamUrl.trim() === '') {
        // If device was previously online, mark it offline
        if (device.streamIsOn) {
            logger.warn(`⚠️ ${deviceName} (${serialNumber}): No stream URL configured, marking offline`);
            await updateDeviceStreamStatus(serialNumber, false);
        }
        return { serialNumber, isOnline: false, reason: 'No stream URL configured' };
    }

    try {
        // Attempt to check stream health
        const streamInfo = await checkStreamHealth(streamUrl);

        logger.info(`✅ ${deviceName} (${serialNumber}): Stream ONLINE - ${streamInfo.format} (${streamInfo.streams} streams)`);

        // Update database if status changed
        const previousStatus = deviceStatusCache.get(serialNumber);
        if (previousStatus !== true || !device.streamIsOn) {
            await updateDeviceStreamStatus(serialNumber, true);
        }
        deviceStatusCache.set(serialNumber, true);

        return {
            serialNumber,
            isOnline: true,
            streamInfo,
            deviceName
        };

    } catch (error) {
        logger.error(`❌ ${deviceName} (${serialNumber}): Stream OFFLINE - ${error.message}`);

        // Update database if status changed
        const previousStatus = deviceStatusCache.get(serialNumber);
        if (previousStatus !== false || device.streamIsOn) {
            await updateDeviceStreamStatus(serialNumber, false);
        }
        deviceStatusCache.set(serialNumber, false);

        return {
            serialNumber,
            isOnline: false,
            reason: error.message,
            deviceName
        };
    }
}

// ============================================================
// Monitoring Loop
// ============================================================

async function monitorAllStreams() {
    if (devices.length === 0) {
        logger.warn('⚠️ No devices to monitor. Waiting for devices...');
        return;
    }

    logger.info('🔍 Starting stream health check cycle...');
    const startTime = Date.now();

    // Check all devices in parallel with Promise.allSettled
    const results = await Promise.allSettled(
        devices.map(device => checkDeviceStream(device))
    );

    // Process results
    let onlineCount = 0;
    let offlineCount = 0;
    let errorCount = 0;

    results.forEach((result, index) => {
        if (result.status === 'fulfilled') {
            if (result.value.isOnline) {
                onlineCount++;
            } else {
                offlineCount++;
            }
        } else {
            errorCount++;
            logger.error(`❌ Unexpected error checking device: ${result.reason}`);
        }
    });

    const duration = ((Date.now() - startTime) / 1000).toFixed(2);
    logger.info(`📊 Check cycle completed in ${duration}s - Online: ${onlineCount}, Offline: ${offlineCount}, Errors: ${errorCount}`);
}

async function startMonitoring() {
    if (isMonitoring) {
        logger.warn('⚠️ Monitoring already running');
        return;
    }

    isMonitoring = true;
    logger.info('🚀 Starting stream monitoring service...');

    // Initial device load
    const success = await loadDevicesFromAPI();

    if (!success) {
        logger.error('❌ Failed to load devices on startup. Will retry periodically...');
    }

    // Initial check
    if (devices.length > 0) {
        await monitorAllStreams();
    }

    // Periodic monitoring loop
    setInterval(async () => {
        try {
            // Reload devices periodically to catch new devices
            if (databaseConnected) {
                await loadDevicesFromAPI();
            }

            // Monitor all streams
            await monitorAllStreams();

        } catch (error) {
            logger.error(`❌ Error in monitoring loop: ${error.message}`);
        }
    }, CHECK_INTERVAL_MS);

    // Periodic database reconnection check
    setInterval(async () => {
        if (!databaseConnected) {
            logger.info('🔄 Database disconnected. Attempting to reconnect...');
            const success = await loadDevicesFromAPI();
            if (success) {
                logger.info('✅ Database connection restored!');
            }
        }
    }, 60000); // Check every 60 seconds

    logger.info(`✅ Monitoring service started (Check interval: ${CHECK_INTERVAL_MS / 1000}s)`);
}

// ============================================================
// Graceful Shutdown
// ============================================================

function gracefulShutdown(signal) {
    logger.info(`\n📴 Received ${signal}. Gracefully shutting down...`);
    isMonitoring = false;

    // Give time for ongoing checks to complete
    setTimeout(() => {
        logger.info('✅ Stream monitoring service stopped');
        process.exit(0);
    }, 2000);
}

// Handle shutdown signals
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));

// Handle uncaught errors
process.on('uncaughtException', (error) => {
    logger.error(`❌ Uncaught Exception: ${error.message}`, { stack: error.stack });
    process.exit(1);
});

process.on('unhandledRejection', (reason, promise) => {
    logger.error(`❌ Unhandled Rejection at: ${promise}, reason: ${reason}`);
});

// ============================================================
// Startup
// ============================================================

logger.info('============================================================');
logger.info('🎥 Stream Monitoring Service for BodyCam & CCTV Devices');
logger.info('============================================================');
logger.info(`API URL: ${DRONE_API_BASE_URL}`);
logger.info(`Check Interval: ${CHECK_INTERVAL_MS / 1000}s`);
logger.info(`Stream Timeout: ${STREAM_TIMEOUT_MS / 1000}s`);
logger.info(`Monitored Device Types: ${MONITORED_DEVICE_TYPES.join(', ')}`);
logger.info('============================================================');
logger.info('');

// Start the monitoring service
startMonitoring().catch(error => {
    logger.error(`❌ Failed to start monitoring service: ${error.message}`);
    process.exit(1);
});
