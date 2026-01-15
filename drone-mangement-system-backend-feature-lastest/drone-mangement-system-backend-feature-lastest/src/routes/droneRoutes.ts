import express from "express";
import {
  getDrone,
  registerDrone,
  getAllDrones,
  getDroneBySerialNumber,
  updateDrone,
  updateDroneBySerialNumber,
  deleteDrone,
  deleteAllDrones
} from "../controllers/droneController";

const router = express.Router();

// Registration
router.post("/register", registerDrone);

// Get operations
router.get("/", getAllDrones);
router.get("/sn/:sn", getDroneBySerialNumber);
router.get("/:id", getDrone);

// Update operations
router.patch("/:id", updateDrone);
router.patch("/sn/:sn", updateDroneBySerialNumber);

// Delete operations
router.delete("/all", deleteAllDrones); // ⚠️ DELETE ALL - use with caution
router.delete("/:id", deleteDrone);

export default router;
