/**
 * WebSocket Server
 * Provides real-time event broadcasting to connected clients
 * Bridges Redis Pub/Sub events to WebSocket connections
 */

import { Server as HTTPServer } from 'http';
import { Server as SocketIOServer, Socket } from 'socket.io';
import { redisManager, RedisEvent } from './redisManager';

interface ClientSubscriptions {
  droneSerial?: string;
  subscribeAll: boolean;
}

class WebSocketServer {
  private io: SocketIOServer | null = null;
  private connectedClients: Map<string, ClientSubscriptions> = new Map();

  /**
   * Initialize WebSocket server with HTTP server instance
   */
  initialize(httpServer: HTTPServer): void {
    console.log('[WebSocket] Initializing WebSocket server...');

    // Create Socket.IO server with CORS enabled
    this.io = new SocketIOServer(httpServer, {
      cors: {
        origin: '*', // Allow all origins (same as Express CORS config)
        methods: ['GET', 'POST']
      },
      path: '/ws/events', // WebSocket endpoint: ws://localhost:5000/ws/events
      transports: ['websocket', 'polling'], // Support both WebSocket and polling
    });

    // Handle client connections
    this.io.on('connection', (socket: Socket) => {
      this.handleClientConnection(socket);
    });

    // Subscribe to all Redis channels for broadcasting
    this.subscribeToRedisEvents();

    console.log('✓ WebSocket server initialized at /ws/events');
  }

  /**
   * Handle new WebSocket client connection
   */
  private handleClientConnection(socket: Socket): void {
    const clientId = socket.id;
    console.log(`[WebSocket] Client connected: ${clientId}`);

    // Initialize client subscription state
    this.connectedClients.set(clientId, {
      subscribeAll: false
    });

    // Send connection confirmation
    socket.emit('connected', {
      message: 'Connected to Drone Management WebSocket Server',
      clientId: clientId,
      timestamp: new Date().toISOString()
    });

    // Handle subscription requests
    socket.on('subscribe', (data: { droneSerial?: string; all?: boolean }) => {
      this.handleSubscribe(socket, data);
    });

    // Handle unsubscribe requests
    socket.on('unsubscribe', () => {
      this.handleUnsubscribe(socket);
    });

    // Handle ping (for connection health check)
    socket.on('ping', () => {
      socket.emit('pong', { timestamp: new Date().toISOString() });
    });

    // Handle disconnection
    socket.on('disconnect', () => {
      console.log(`[WebSocket] Client disconnected: ${clientId}`);
      this.connectedClients.delete(clientId);
    });

    // Handle errors
    socket.on('error', (error) => {
      console.error(`[WebSocket] Error for client ${clientId}:`, error);
    });
  }

  /**
   * Handle client subscription
   */
  private handleSubscribe(socket: Socket, data: { droneSerial?: string; all?: boolean }): void {
    const clientId = socket.id;
    const subscriptions = this.connectedClients.get(clientId);

    if (!subscriptions) return;

    if (data.all) {
      // Subscribe to all drone events
      subscriptions.subscribeAll = true;
      subscriptions.droneSerial = undefined;
      console.log(`[WebSocket] Client ${clientId} subscribed to ALL events`);
      socket.emit('subscribed', { type: 'all', message: 'Subscribed to all drone events' });
    } else if (data.droneSerial) {
      // Subscribe to specific drone
      subscriptions.subscribeAll = false;
      subscriptions.droneSerial = data.droneSerial;
      console.log(`[WebSocket] Client ${clientId} subscribed to drone: ${data.droneSerial}`);
      socket.emit('subscribed', {
        type: 'drone',
        droneSerial: data.droneSerial,
        message: `Subscribed to drone ${data.droneSerial} events`
      });
    }

    this.connectedClients.set(clientId, subscriptions);
  }

  /**
   * Handle client unsubscribe
   */
  private handleUnsubscribe(socket: Socket): void {
    const clientId = socket.id;
    const subscriptions = this.connectedClients.get(clientId);

    if (subscriptions) {
      subscriptions.subscribeAll = false;
      subscriptions.droneSerial = undefined;
      this.connectedClients.set(clientId, subscriptions);
      console.log(`[WebSocket] Client ${clientId} unsubscribed`);
      socket.emit('unsubscribed', { message: 'Unsubscribed from all events' });
    }
  }

  /**
   * Subscribe to Redis events and broadcast to WebSocket clients
   */
  private async subscribeToRedisEvents(): Promise<void> {
    // Subscribe to all drone-related events using wildcard pattern
    await redisManager.subscribe('drone:*', (event: RedisEvent, channel: string) => {
      this.broadcastEvent(event, channel);
    });

    // Subscribe to system-wide broadcast events
    await redisManager.subscribe('system:broadcast', (event: RedisEvent, channel: string) => {
      this.broadcastToAll(event);
    });

    console.log('[WebSocket] Subscribed to Redis channels: drone:*, system:broadcast');
  }

  /**
   * Broadcast event to relevant WebSocket clients based on subscriptions
   */
  private broadcastEvent(event: RedisEvent, channel: string): void {
    if (!this.io) return;

    // Extract drone serial number from channel (e.g., 'drone:SERIAL123:updated')
    const channelParts = channel.split(':');
    const droneSerial = channelParts[1]; // SERIAL123

    // Broadcast to all connected clients
    this.connectedClients.forEach((subscriptions, clientId) => {
      const socket = this.io?.sockets.sockets.get(clientId);
      if (!socket) return;

      // Check if client should receive this event
      const shouldReceive =
        subscriptions.subscribeAll || // Subscribed to all events
        subscriptions.droneSerial === droneSerial; // Subscribed to this specific drone

      if (shouldReceive) {
        socket.emit('drone:event', {
          channel,
          droneSerial,
          ...event
        });
      }
    });

    console.log(`[WebSocket] Broadcasted event from ${channel} to ${this.connectedClients.size} potential clients`);
  }

  /**
   * Broadcast to all connected clients (system-wide events)
   */
  private broadcastToAll(event: RedisEvent): void {
    if (!this.io) return;

    this.io.emit('system:event', event);
    console.log(`[WebSocket] System broadcast sent to all clients`);
  }

  /**
   * Get number of connected clients
   */
  getConnectedClientsCount(): number {
    return this.connectedClients.size;
  }

  /**
   * Graceful shutdown
   */
  async shutdown(): Promise<void> {
    console.log('[WebSocket] Shutting down...');

    if (this.io) {
      // Notify all clients of shutdown
      this.io.emit('server:shutdown', {
        message: 'Server is shutting down',
        timestamp: new Date().toISOString()
      });

      // Close all connections
      this.io.close();
      this.connectedClients.clear();
      console.log('✓ WebSocket server shut down');
    }
  }
}

// Export singleton instance
export const websocketServer = new WebSocketServer();
