import mongoose from "mongoose";
// NOTE INCASE WE NEED TO MIGRATE INCIDENTS TO A SEPARATE COLLECTION
const IncidentSchema = new mongoose.Schema(
  {
    deviceSerialNumber: String,
    imageUrl: String,

    coordinates: {
      type: { type: String, enum: ["Point"], required: true },
      coordinates: { type: [Number], required: true },
    },
    objectBBox: [Number],
  },
  {
    timestamps: true,
    toJSON: {
      virtuals: true,
    },
    toObject: {
      virtuals: true,
    },
  }
);

const IncidentModel = mongoose.model("Incident", IncidentSchema);

export default IncidentModel;
