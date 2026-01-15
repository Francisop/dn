/**
 * Event Publisher
 * Helper functions to publish drone events to Redis
 * Simplifies event publishing in controllers
 */

import { redisManager, RedisEvent } from './redisManager';

/**
 * Detect changes between old and new drone data
 */
function detectChanges(oldData: any, newData: any): Record<string, any> {
  const changes: Record<string, any> = {};

  // Compare top-level fields
  for (const key in newData) {
    if (newData[key] !== undefined && newData[key] !== oldData?.[key]) {
      // Handle nested objects
      if (typeof newData[key] === 'object' && newData[key] !== null && !Array.isArray(newData[key])) {
        const nestedChanges = detectChanges(oldData?.[key], newData[key]);
        if (Object.keys(nestedChanges).length > 0) {
          changes[key] = nestedChanges;
        }
      } else {
        changes[key] = newData[key];
      }
    }
  }

  return changes;
}

/**
 * Publish drone created event
 */
export async function publishDroneCreated(droneData: any): Promise<void> {
  const event: RedisEvent = {
    event: 'drone.created',
    timestamp: new Date().toISOString(),
    data: {
      serialNumber: droneData.deviceSerialNumber,
      droneId: droneData._id?.toString(),
      full: droneData
    }
  };

  // Publish to specific drone channel
  await redisManager.publish(`drone:${droneData.deviceSerialNumber}:created`, event);

  // Also publish to general channel for new drones
  await redisManager.publish('drone:all:created', event);
}

/**
 * Publish drone updated event
 */
export async function publishDroneUpdated(oldData: any, newData: any): Promise<void> {
  const changes = detectChanges(oldData, newData);

  const event: RedisEvent = {
    event: 'drone.updated',
    timestamp: new Date().toISOString(),
    data: {
      serialNumber: newData.deviceSerialNumber,
      droneId: newData._id?.toString(),
      changes,
      full: newData
    }
  };

  // Publish to specific drone channel
  await redisManager.publish(`drone:${newData.deviceSerialNumber}:updated`, event);
}

/**
 * Publish stream status change event
 */
export async function publishStreamStatusChanged(droneData: any, oldStatus: boolean, newStatus: boolean): Promise<void> {
  const event: RedisEvent = {
    event: 'drone.stream.status',
    timestamp: new Date().toISOString(),
    data: {
      serialNumber: droneData.deviceSerialNumber,
      droneId: droneData._id?.toString(),
      streamIsOn: newStatus,
      previousStatus: oldStatus,
      streamUrl: droneData.streamUrl,
      full: droneData  // Include full drone data for frontend
    }
  };

  // Publish to specific drone channel
  await redisManager.publish(`drone:${droneData.deviceSerialNumber}:stream`, event);
}

/**
 * Publish AI detection toggle event
 */
export async function publishAIDetectionToggled(droneData: any, oldStatus: boolean, newStatus: boolean): Promise<void> {
  const event: RedisEvent = {
    event: 'drone.ai.detection.toggled',
    timestamp: new Date().toISOString(),
    data: {
      serialNumber: droneData.deviceSerialNumber,
      droneId: droneData._id?.toString(),
      isUsingAiDetection: newStatus,
      previousStatus: oldStatus,
      detectionClasses: droneData.detectionClasses,
      full: droneData  // Include full drone data for frontend
    }
  };

  // Publish to specific drone channel
  await redisManager.publish(`drone:${droneData.deviceSerialNumber}:ai`, event);
}

/**
 * Publish detection classes changed event
 */
export async function publishDetectionClassesChanged(droneData: any, oldClasses: number[], newClasses: number[]): Promise<void> {
  const event: RedisEvent = {
    event: 'drone.detection.classes.changed',
    timestamp: new Date().toISOString(),
    data: {
      serialNumber: droneData.deviceSerialNumber,
      droneId: droneData._id?.toString(),
      detectionClasses: newClasses,
      previousClasses: oldClasses,
      full: droneData  // Include full drone data for frontend
    }
  };

  // Publish to specific drone channel
  await redisManager.publish(`drone:${droneData.deviceSerialNumber}:config`, event);
}

/**
 * Publish drone deleted event
 */
export async function publishDroneDeleted(droneData: any): Promise<void> {
  const event: RedisEvent = {
    event: 'drone.deleted',
    timestamp: new Date().toISOString(),
    data: {
      serialNumber: droneData.deviceSerialNumber,
      droneId: droneData._id?.toString(),
      deviceName: droneData.deviceName
    }
  };

  // Publish to specific drone channel
  await redisManager.publish(`drone:${droneData.deviceSerialNumber}:deleted`, event);

  // Also publish to general channel
  await redisManager.publish('drone:all:deleted', event);
}

/**
 * Publish incident detected event
 */
export async function publishIncidentDetected(droneData: any, incident: any): Promise<void> {
  const event: RedisEvent = {
    event: 'drone.incident.detected',
    timestamp: new Date().toISOString(),
    data: {
      serialNumber: droneData.deviceSerialNumber,
      droneId: droneData._id?.toString(),
      incident: {
        imageUrl: incident.imageUrl,
        coordinates: incident.coordinates,
        objectBBox: incident.objectBBox,
        createdAt: incident.createdAt
      }
    }
  };

  // Publish to specific drone channel
  await redisManager.publish(`drone:${droneData.deviceSerialNumber}:incident`, event);

  // Also publish to incidents channel (for incident monitoring dashboard)
  await redisManager.publish('incidents:all', event);
}

/**
 * Publish system-wide broadcast message
 */
export async function publishSystemBroadcast(message: string, data?: any): Promise<void> {
  const event: RedisEvent = {
    event: 'system.broadcast',
    timestamp: new Date().toISOString(),
    data: {
      message,
      ...data
    }
  };

  await redisManager.publish('system:broadcast', event);
}
