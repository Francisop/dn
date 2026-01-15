import "dotenv/config";
import express from "express";
import morgan from "morgan";
import cors from "cors";
import AppError from "./utils/appError";
import droneRouter from "./routes/droneRoutes";

const app = express();

// Enable CORS for all origins (adjust in production)
app.use(cors({
  origin: '*', // Allow all origins for development
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
}));

// Parse request body
app.use(express.json());

if (!process.env.NODE_ENV) {
  throw new Error("NODE_ENV is not defined!");
}

if (process.env.NODE_ENV === "development") {
  app.use(morgan("dev"));
}

app.use("/api/v1/drones", droneRouter);

app.use((req, res, next) => {
  next(new AppError(`Can't find ${req.originalUrl} on this server!`, 404));
});

//Global error handler
app.use((err, req, res, next) => {
  res.status(500).json({
    errorMessage: err.message,
    err,
  });
});

export default app;
