process.on("uncaughtException", (err) => {
  console.log("UNCAUGHT EXCEPTION! shutting down! 🤯");
  console.log(err.name, err.message);
  process.exit(1);
});

import app from "./app";
import connectDB from "./config/db";
import { redisManager } from "./services/redisManager";
import { websocketServer } from "./services/websocketServer";

const port = process.env.PORT || 5000;

// Initialize services
async function initializeServices() {
  try {
    // Connect to MongoDB
    await connectDB();

    // Initialize Redis Manager
    await redisManager.initialize();

    // Start HTTP server
    const server = app.listen(port, () => {
      console.log(`✓ Server running on PORT: ${port}`);
    });

    // Initialize WebSocket server (must be after HTTP server starts)
    websocketServer.initialize(server);

    console.log("="*60);
    console.log("✓ All services initialized successfully");
    console.log("  - MongoDB: Connected");
    console.log("  - Redis: Connected");
    console.log("  - WebSocket: Running at /ws/events");
    console.log("  - HTTP API: Running at http://localhost:" + port);
    console.log("="*60);

    // Graceful shutdown handlers
    const gracefulShutdown = async (signal: string) => {
      console.log(`\n${signal} received. Starting graceful shutdown...`);

      try {
        // Shutdown WebSocket server
        await websocketServer.shutdown();

        // Disconnect Redis
        await redisManager.disconnect();

        // Close HTTP server
        server.close(() => {
          console.log("✓ HTTP server closed");
          process.exit(0);
        });

        // Force exit if graceful shutdown takes too long
        setTimeout(() => {
          console.error("Forceful shutdown due to timeout");
          process.exit(1);
        }, 10000); // 10 seconds timeout

      } catch (error) {
        console.error("Error during shutdown:", error);
        process.exit(1);
      }
    };

    // Handle shutdown signals
    process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));
    process.on("SIGINT", () => gracefulShutdown("SIGINT"));

    // Handle unhandled rejections
    process.on("unhandledRejection", (err) => {
      console.log("UNHANDLED REJECTION! shutting down! 🤯");
      console.log(err);
      gracefulShutdown("UNHANDLED_REJECTION");
    });

  } catch (error) {
    console.error("Failed to initialize services:", error);
    process.exit(1);
  }
}

// Start the application
initializeServices();
