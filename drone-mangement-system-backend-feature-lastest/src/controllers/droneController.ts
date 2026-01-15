import { Model } from "mongoose";
import DroneModel from "../models/droneModel";
import AppError from "../utils/appError";
import catchAsync from "../utils/catchAsync";
import {
  publishDroneCreated,
  publishDroneUpdated,
  publishDroneDeleted,
  publishStreamStatusChanged,
  publishAIDetectionToggled,
  publishDetectionClassesChanged
} from "../services/eventPublisher";

export const registerDrone = catchAsync(async (req, res, next) => {
  const body = req.body;
  console.log("registering")
  const drone = await DroneModel.create({
    deviceSerialNumber: body?.deviceSerialNumber,
    deviceName: body?.deviceName,
    deviceCategory: body?.deviceCategory,
    metadata: {
      alias: body?.metadata?.alias,
      description: body?.metadata?.description,
    },
    isUsingAiDetection: body?.isUsingAiDetection || false,
    streamIsOn: body?.streamIsOn || false,
    streamUrl: body?.streamUrl || '',
    webRTCUrl: body?.webRTCUrl || '',
    streamCredentials: {
      userName: body?.streamCredentials?.userName || '',
      password: body?.streamCredentials?.password || '',
      port: body?.streamCredentials?.port || '8554',
    },
    cameras: body?.cameras || [],
    detectionClasses: body?.detectionClasses || [],
  });

  // Publish drone created event to Redis
  await publishDroneCreated(drone.toObject());

  res.status(201).json({
    status: "success",
    data: {
      drone,
    },
  });
});

export const getDrone = catchAsync(async (req, res, next) => {
  const id = req.params.id;

  const drone = await DroneModel.findById(id);

  if (!drone)
    next(new AppError(`Could not find drone with ${id} serial number`, 404));

  res.status(200).json({
    status: "success",
    data: {
      drone,
    },
  });
});


interface DroneQueryParams {
  deviceCategory?: string;
  streamIsOn?: string;
  // Add other query params as needed
}

export const getAllDrones = catchAsync(async (req, res, next) => {
  const queryParams = req.query as DroneQueryParams;
  
  // Build query object based on query parameters
  const query: any = {};
  
  // Filter by deviceCategory if provided
  if (queryParams.deviceCategory) {
    query.deviceCategory = queryParams.deviceCategory;
  }
  
  const drones = await DroneModel.find(query);

  res.status(200).json({
    status: "success",
    results: drones.length,
    data: {
      drones,
    },
  });
});


// Get drone by serial number
export const getDroneBySerialNumber = catchAsync(async (req, res, next) => {
  const sn = req.params.sn;

  const drone = await DroneModel.findOne({ deviceSerialNumber: sn });

  if (!drone) {
    return next(new AppError(`Could not find drone with serial number: ${sn}`, 404));
  }

  res.status(200).json({
    status: "success",
    data: {
      drone,
    },
  });
});

// Update drone by ID
export const updateDrone = catchAsync(async (req, res, next) => {
  const id = req.params.id;
  const body = req.body;

  // Fetch old drone data BEFORE update (for change detection)
  const oldDrone = await DroneModel.findById(id);

  if (!oldDrone) {
    return next(new AppError(`Could not find drone with ID: ${id}`, 404));
  }

  const drone = await DroneModel.findByIdAndUpdate(
    id,
    {
      deviceSerialNumber: body?.deviceSerialNumber,
      deviceName: body?.deviceName,
      deviceCategory: body?.deviceCategory,
      metadata: {
        alias: body?.metadata?.alias,
        description: body?.metadata?.description,
      },
      isUsingAiDetection: body?.isUsingAiDetection,
      streamIsOn: body?.streamIsOn,
      streamUrl: body?.streamUrl,
      webRTCUrl: body?.webRTCUrl,
      streamCredentials: {
        userName: body?.streamCredentials?.userName,
        password: body?.streamCredentials?.password,
        port: body?.streamCredentials?.port,
      },
      cameras: body?.cameras,
      detectionClasses: body?.detectionClasses,
    },
    {
      new: true, // Return updated document
      runValidators: true, // Run model validators
    }
  );

  if (!drone) {
    return next(new AppError(`Could not find drone with ID: ${id}`, 404));
  }

  // Publish update events to Redis
  await publishDroneUpdated(oldDrone.toObject(), drone.toObject());

  // Publish specific events for important changes
  if (body?.streamIsOn !== undefined && oldDrone.streamIsOn !== body.streamIsOn) {
    await publishStreamStatusChanged(drone.toObject(), oldDrone.streamIsOn, body.streamIsOn);
  }

  if (body?.isUsingAiDetection !== undefined && oldDrone.isUsingAiDetection !== body.isUsingAiDetection) {
    await publishAIDetectionToggled(drone.toObject(), oldDrone.isUsingAiDetection, body.isUsingAiDetection);
  }

  if (body?.detectionClasses !== undefined && JSON.stringify(oldDrone.detectionClasses) !== JSON.stringify(body.detectionClasses)) {
    await publishDetectionClassesChanged(drone.toObject(), oldDrone.detectionClasses, body.detectionClasses);
  }

  res.status(200).json({
    status: "success",
    data: {
      drone,
    },
  });
});

// Update drone by serial number
export const updateDroneBySerialNumber = catchAsync(async (req, res, next) => {
  const sn = req.params.sn;
  const body = req.body;

  // Fetch old drone data BEFORE update (for change detection)
  const oldDrone = await DroneModel.findOne({ deviceSerialNumber: sn });

  if (!oldDrone) {
    return next(new AppError(`Could not find drone with serial number: ${sn}`, 404));
  }

  const drone = await DroneModel.findOneAndUpdate(
    { deviceSerialNumber: sn },
    {
      deviceName: body?.deviceName,
      deviceCategory: body?.deviceCategory,
      metadata: {
        alias: body?.metadata?.alias,
        description: body?.metadata?.description,
      },
      isUsingAiDetection: body?.isUsingAiDetection,
      streamIsOn: body?.streamIsOn,
      streamUrl: body?.streamUrl,
      webRTCUrl: body?.webRTCUrl,
      streamCredentials: {
        userName: body?.streamCredentials?.userName,
        password: body?.streamCredentials?.password,
        port: body?.streamCredentials?.port,
      },
      cameras: body?.cameras,
      detectionClasses: body?.detectionClasses,
    },
    {
      new: true,
      runValidators: true,
    }
  );

  if (!drone) {
    return next(new AppError(`Could not find drone with serial number: ${sn}`, 404));
  }

  // Publish update events to Redis
  await publishDroneUpdated(oldDrone.toObject(), drone.toObject());

  // Publish specific events for important changes
  if (body?.streamIsOn !== undefined && oldDrone.streamIsOn !== body.streamIsOn) {
    await publishStreamStatusChanged(drone.toObject(), oldDrone.streamIsOn, body.streamIsOn);
  }

  if (body?.isUsingAiDetection !== undefined && oldDrone.isUsingAiDetection !== body.isUsingAiDetection) {
    await publishAIDetectionToggled(drone.toObject(), oldDrone.isUsingAiDetection, body.isUsingAiDetection);
  }

  if (body?.detectionClasses !== undefined && JSON.stringify(oldDrone.detectionClasses) !== JSON.stringify(body.detectionClasses)) {
    await publishDetectionClassesChanged(drone.toObject(), oldDrone.detectionClasses, body.detectionClasses);
  }

  res.status(200).json({
    status: "success",
    data: {
      drone,
    },
  });
});

// Delete drone by ID
export const deleteDrone = catchAsync(async (req, res, next) => {
  const id = req.params.id;

  const drone = await DroneModel.findByIdAndDelete(id);

  if (!drone) {
    return next(new AppError(`Could not find drone with ID: ${id}`, 404));
  }

  // Publish drone deleted event to Redis
  await publishDroneDeleted(drone.toObject());

  res.status(204).json({
    status: "success",
    data: null,
  });
});

// Delete all drones (USE WITH CAUTION!)
export const deleteAllDrones = catchAsync(async (req, res, next) => {
  const result = await DroneModel.deleteMany({});

  res.status(200).json({
    status: "success",
    message: `Deleted ${result.deletedCount} drones`,
    data: {
      deletedCount: result.deletedCount,
    },
  });
});
