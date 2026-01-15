/**
 * Seed Script: Populate MongoDB with drones from drones.json
 *
 * This script migrates your existing drones from the JSON file to MongoDB
 *
 * Usage: node seed-drones.cjs
 */

const fs = require('fs');
const path = require('path');

const API_BASE_URL = 'http://127.0.0.1:5000/api/v1/drones';
const DRONES_JSON_PATH = path.join(__dirname, '..', 'node server', 'drones.json');

async function seedDrones() {
    try {
        // Read drones from JSON file
        console.log('📖 Reading drones from drones.json...');
        const dronesData = fs.readFileSync(DRONES_JSON_PATH, 'utf-8');
        const drones = JSON.parse(dronesData);

        console.log(`Found ${drones.length} drones to migrate\n`);

        // Register each drone
        let successCount = 0;
        let failCount = 0;

        for (const drone of drones) {
            try {
                const payload = {
                    deviceSerialNumber: drone.sn,
                    deviceName: drone.name,
                    deviceCategory: 'Drone',
                    metadata: {
                        alias: drone.alias,
                        description: `Migrated from drones.json - ${drone.name}`
                    },
                    isUsingAiDetection: true,
                    streamIsOn: false,
                    streamUrl: '',
                    webRTCUrl: '',
                    streamCredentials: {
                        userName: drone.userName,
                        password: drone.password,
                        port: drone.port
                    },
                    cameras: drone.cameras
                };

                console.log(`📡 Registering: ${drone.alias} (${drone.sn})...`);

                const response = await fetch(`${API_BASE_URL}/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                const data = await response.json();

                if (response.status === 201) {
                    console.log(`✅ Success: ${drone.alias} registered`);
                    successCount++;
                } else if (response.status === 400 || response.status === 500) {
                    // Check if it's a duplicate key error
                    if (data.errorMessage?.includes('duplicate key') || data.errorMessage?.includes('E11000')) {
                        console.log(`⚠️ Skipped: ${drone.alias} (already exists - duplicate serial number)`);
                    } else {
                        console.error(`❌ Failed: ${drone.alias} - ${data.errorMessage || 'Unknown error'}`);
                        failCount++;
                    }
                } else {
                    console.log(`⚠️ Unexpected response: ${response.status}`);
                    failCount++;
                }

            } catch (error) {
                console.error(`❌ Failed: ${drone.alias} - ${error.message}`);
                failCount++;
            }
            console.log(''); // Empty line for readability
        }

        // Summary
        console.log('═══════════════════════════════════════');
        console.log('📊 MIGRATION SUMMARY');
        console.log('═══════════════════════════════════════');
        console.log(`✅ Successfully registered: ${successCount}`);
        console.log(`❌ Failed: ${failCount}`);
        console.log(`📝 Total processed: ${drones.length}`);
        console.log('═══════════════════════════════════════\n');

        if (successCount > 0) {
            console.log('🎉 Database seeded successfully!');
            console.log('\nNext steps:');
            console.log('1. Start the telemetry server: cd "../node server" && node drone_telemetry_server.js');
            console.log('2. The server will automatically load drones from the database');
        } else if (failCount === 0 && successCount === 0) {
            console.log('ℹ️ All drones already exist in the database.');
            console.log('The telemetry server can use them directly.');
        }

    } catch (error) {
        console.error('❌ Seeding failed:', error.message);
        console.log('\n⚠️ Make sure:');
        console.log('1. MongoDB backend is running (npm run dev)');
        console.log('2. Database connection is configured (.env file)');
        console.log('3. drones.json exists in the node server folder');
        console.log('4. The backend server is accessible at http://127.0.0.1:5000');
        process.exit(1);
    }
}

// Run seeder
console.log('🌱 Starting database seeding...\n');
seedDrones();
