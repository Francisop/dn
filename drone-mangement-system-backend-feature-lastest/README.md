# Drone System Backend

A Node.js backend system for managing and monitoring registered drones, tracking incidents, and handling AI-powered detection events.

## Features

- ✅ Drone registration and management
- ✅ MongoDB integration with Mongoose ODM
- ✅ RESTful API architecture
- 🚧 Incident tracking and reporting
- 🚧 AI detection integration
- 🚧 Authentication and authorization (coming soon)

## Tech Stack

- **Runtime:** Node.js v22.9.0
- **Framework:** Express 5.x
- **Database:** MongoDB with Mongoose
- **Language:** TypeScript
- **Dev Tools:** tsx, nodemon

## Project Structure

```
src/
├── app.ts              # Express app configuration
├── server.ts           # Server entry point
├── config/
│   └── db.ts          # Database connection
├── controllers/
│   └── droneController.ts
├── models/
│   ├── droneModel.ts
│   └── incidentModel.ts
├── routes/
│   └── droneRoutes.ts
├── types/
│   ├── drone.d.ts
│   └── index.d.ts
└── utils/
    ├── appError.ts
    └── catchAsync.ts
```

## Getting Started

### Prerequisites

- Node.js v22.x or higher
- MongoDB (local or Atlas)
- npm or yarn

### Installation

1. Clone the repository:

```bash
git clone <your-repo-url>
cd drone-system-backend
```

2. Install dependencies:

```bash
npm install
```

3. Create a `.env` file in the root directory:

```env
PORT=5000
MONGO_URI=mongodb://localhost:27017/droneSystem
NODE_ENV=development
```

4. Start the development server:

```bash
npm run dev
```

The server will start on `http://localhost:5000`

## Available Scripts

- `npm run dev` - Start development server with hot reload
- `npm run build` - Build TypeScript to JavaScript
- `npm start` - Run the app with tsx
- `npm run start:prod` - Run production build

## API Endpoints

### Drones

| Method | Endpoint                  | Description          |
| ------ | ------------------------- | -------------------- |
| POST   | `/api/v1/drones/register` | Register a new drone |
| GET    | `/api/v1/drones/:id`      | Get drone by ID      |

See [API Documentation](https://documenter.getpostman.com/view/46098536/2sB3WsR1HQ) for detailed endpoint information.

## Environment Variables

| Variable                       | Description                          | Default       |
| ------------------------------ | ------------------------------------ | ------------- |
| `PORT`                         | Server port                          | `5000`        |
| `DATABASE & DATABASE_PASSWORD` | MongoDB connection string            | Required      |
| `NODE_ENV`                     | Environment (development/production) | `development` |

## Data Models

### Drone

- Device serial number (unique)
- Device name and category
- Metadata (alias, description)
- AI detection status
- Stream URL
- Incidents array

### Incident

- Image URL
- GPS coordinates (GeoJSON Point)
- Object bounding box
- Timestamp

## Security Features (Planned)

- Helmet.js for security headers
- Rate limiting
- XSS sanitization
- NoSQL injection prevention
- HPP (HTTP Parameter Pollution) protection
- JWT authentication

## Development Status

**Current Version:** 1.0.0 (Beta)

This project is under active development. Breaking changes may occur.

---

**Note:** MongoDB unique index is enforced on `deviceSerialNumber` - attempting to register a drone with an existing serial number will result in a duplicate key error.
