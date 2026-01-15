import mongoose from "mongoose";

const DB = process.env.DATABASE!.replace(
  "<db_password>",
  process.env.DATABASE_PASSWORD!
);

export default async function connectDB() {
  try {
    await mongoose.connect(DB);

    console.log(`MongoDB connected: 🛜`);
  } catch (error: unknown) {
    if (error instanceof Error) {
      console.log(`Failed to connect to MongoDB ${error.message}`);
    }
  }
}
