/**
 * Redis Manager
 * Handles Redis Pub/Sub for real-time event broadcasting across multiple instances
 * Ensures all detector instances and WebSocket clients receive database updates
 */

import { createClient, RedisClientType } from 'redis';

export interface RedisEvent {
  event: string;
  timestamp: string;
  data: {
    serialNumber?: string;
    droneId?: string;
    changes?: Record<string, any>;
    full?: Record<string, any>;
    [key: string]: any;
  };
}

class RedisManager {
  private publisher: RedisClientType | null = null;
  private subscriber: RedisClientType | null = null;
  private isConnected: boolean = false;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;
  private reconnectDelay: number = 3000; // 3 seconds

  /**
   * Initialize Redis clients (publisher and subscriber)
   */
  async initialize(): Promise<void> {
    const redisUrl = process.env.REDIS_URL || 'redis://localhost:6379';

    try {
      console.log(`[Redis] Connecting to Redis at ${redisUrl}...`);

      // Create publisher client
      this.publisher = createClient({ url: redisUrl });

      // Create subscriber client (separate connection required for pub/sub)
      this.subscriber = createClient({ url: redisUrl });

      // Error handlers
      this.publisher.on('error', (err) => {
        console.error('[Redis Publisher] Error:', err);
        this.handleReconnect();
      });

      this.subscriber.on('error', (err) => {
        console.error('[Redis Subscriber] Error:', err);
        this.handleReconnect();
      });

      // Connection event handlers
      this.publisher.on('connect', () => {
        console.log('[Redis Publisher] Connected');
      });

      this.subscriber.on('connect', () => {
        console.log('[Redis Subscriber] Connected');
      });

      // Connect both clients
      await Promise.all([
        this.publisher.connect(),
        this.subscriber.connect()
      ]);

      this.isConnected = true;
      this.reconnectAttempts = 0;
      console.log('✓ Redis Manager initialized successfully');

    } catch (error) {
      console.error('[Redis] Initialization failed:', error);
      this.handleReconnect();
      throw error;
    }
  }

  /**
   * Handle reconnection logic
   */
  private async handleReconnect(): Promise<void> {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[Redis] Max reconnection attempts reached. Giving up.');
      return;
    }

    this.reconnectAttempts++;
    this.isConnected = false;

    console.log(`[Redis] Attempting reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${this.reconnectDelay}ms...`);

    setTimeout(async () => {
      try {
        await this.initialize();
      } catch (error) {
        console.error('[Redis] Reconnection failed:', error);
      }
    }, this.reconnectDelay);
  }

  /**
   * Publish an event to Redis channel
   * @param channel - Redis channel name (e.g., 'drone:SERIAL123:updated')
   * @param event - Event object containing event type and data
   */
  async publish(channel: string, event: RedisEvent): Promise<void> {
    if (!this.isConnected || !this.publisher) {
      console.warn('[Redis] Publisher not connected. Event not published:', channel);
      return;
    }

    try {
      const message = JSON.stringify(event);
      await this.publisher.publish(channel, message);
      console.log(`[Redis] Published event to channel: ${channel}`);
    } catch (error) {
      console.error('[Redis] Failed to publish event:', error);
    }
  }

  /**
   * Subscribe to a Redis channel
   * @param channel - Channel name or pattern (supports wildcards like 'drone:*')
   * @param callback - Function to call when message received
   */
  async subscribe(channel: string, callback: (message: RedisEvent, channel: string) => void): Promise<void> {
    if (!this.isConnected || !this.subscriber) {
      console.warn('[Redis] Subscriber not connected. Cannot subscribe to:', channel);
      return;
    }

    try {
      // Subscribe to channel
      if (channel.includes('*')) {
        // Pattern-based subscription
        await this.subscriber.pSubscribe(channel, (message, channelName) => {
          try {
            const event = JSON.parse(message) as RedisEvent;
            callback(event, channelName);
          } catch (error) {
            console.error('[Redis] Failed to parse message:', error);
          }
        });
        console.log(`[Redis] Subscribed to pattern: ${channel}`);
      } else {
        // Exact channel subscription
        await this.subscriber.subscribe(channel, (message, channelName) => {
          try {
            const event = JSON.parse(message) as RedisEvent;
            callback(event, channelName);
          } catch (error) {
            console.error('[Redis] Failed to parse message:', error);
          }
        });
        console.log(`[Redis] Subscribed to channel: ${channel}`);
      }
    } catch (error) {
      console.error('[Redis] Failed to subscribe:', error);
    }
  }

  /**
   * Unsubscribe from a channel
   */
  async unsubscribe(channel: string): Promise<void> {
    if (!this.subscriber) return;

    try {
      if (channel.includes('*')) {
        await this.subscriber.pUnsubscribe(channel);
      } else {
        await this.subscriber.unsubscribe(channel);
      }
      console.log(`[Redis] Unsubscribed from: ${channel}`);
    } catch (error) {
      console.error('[Redis] Failed to unsubscribe:', error);
    }
  }

  /**
   * Graceful shutdown
   */
  async disconnect(): Promise<void> {
    console.log('[Redis] Disconnecting...');

    try {
      if (this.publisher) {
        await this.publisher.quit();
      }
      if (this.subscriber) {
        await this.subscriber.quit();
      }
      this.isConnected = false;
      console.log('✓ Redis disconnected');
    } catch (error) {
      console.error('[Redis] Error during disconnect:', error);
    }
  }

  /**
   * Check if Redis is connected
   */
  get connected(): boolean {
    return this.isConnected;
  }
}

// Export singleton instance
export const redisManager = new RedisManager();
