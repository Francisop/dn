import mongoose from "mongoose";
import { IDrone } from "../types";

const DroneSchema = new mongoose.Schema(
  {
    deviceSerialNumber: String,
    deviceName: String,
    deviceCategory: String,
    metadata: {
      alias: String,
      description: String,
    },
    isUsingAiDetection: Boolean,
    streamIsOn: Boolean,
    streamUrl: String,
    webRTCUrl: String,
    // Streaming credentials
    streamCredentials: {
      userName: String,
      password: String,
      port: String,
    },
    cameras: [String], // Array of camera IDs
    detectionClasses: [Number], // Array of YOLO class IDs for AI detection (0-79)
    incidents: [
      {
        imageUrl: String,
        coordinates: {
          type: { type: String, enum: ["Point"] },
          coordinates: { type: [Number] },
        },
        objectBBox: [Number],
        createdAt: {
          type: Date,
          default: Date.now,
        },
      },
    ],
  },
  {
    timestamps: true,
    toJSON: { virtuals: true },
    toObject: { virtuals: true },
  }
);

DroneSchema.index({ deviceSerialNumber: 1 }, { unique: true });

const DroneModel = mongoose.model<IDrone>("Drone", DroneSchema);

export default DroneModel;
