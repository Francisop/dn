export default class AppError extends Error {
  status: "fail" | "error";
  isOperational: boolean;

  constructor(public message: string, public statusCode: number) {
    super(message);

    this.status = statusCode >= 400 && statusCode < 500 ? "fail" : "error";

    this.isOperational = true;

    Error.captureStackTrace(this, this.constructor);
  }
}
