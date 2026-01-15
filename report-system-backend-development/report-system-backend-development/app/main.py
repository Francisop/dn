"""
FastAPI Backend for Pipeline Report Generator

Main entry point for the Python backend service.
Handles report generation (PPTX, maps, photo annotation).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import get_settings
from app.api import routes
from app.utils.mongodb import connect_to_mongodb, close_mongodb_connection
import os

# Initialize settings
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="Pipeline Report Generator API",
    description="Python backend for generating pipeline surveillance reports",
    version="1.0.0",
    debug=settings.debug,
)

# CORS middleware (allow Next.js and external IPs to call this API)
# In development, allow all origins. In production, restrict to specific domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [settings.nextjs_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup/shutdown events
@app.on_event("startup")
async def startup():
    """Connect to MongoDB on startup"""
    try:
        await connect_to_mongodb()
    except Exception as e:
        print(f"⚠️  Warning: Could not connect to MongoDB: {e}")
        print("   API will work but database features will be disabled")


@app.on_event("shutdown")
async def shutdown():
    """Close MongoDB connection on shutdown"""
    await close_mongodb_connection()


# Include API routes
app.include_router(routes.router, prefix="/api")

# Mount static file serving for uploads (generated reports, maps, photos)
# Projects folder is inside Backend/report system/ for better organization
app_dir = os.path.dirname(__file__)  # app folder
backend_dir = os.path.dirname(app_dir)  # Backend/report system folder
root_dir = os.path.dirname(os.path.dirname(backend_dir))  # Root directory
projects_path = os.path.join(backend_dir, "projects")
global_assets_path = os.path.join(root_dir, "global_assets")

if not os.path.exists(projects_path):
    os.makedirs(projects_path, exist_ok=True)
    print(f"📁 Created projects directory: {projects_path}")

if not os.path.exists(global_assets_path):
    os.makedirs(global_assets_path, exist_ok=True)
    print(f"📁 Created global_assets directory: {global_assets_path}")

# Mount projects folder for reports/maps
app.mount("/uploads", StaticFiles(directory=projects_path), name="uploads")
print(f"✅ Serving project files from: {projects_path}")

# Mount global_assets folder for pipeline GeoJSON files
app.mount("/assets", StaticFiles(directory=global_assets_path), name="assets")
print(f"✅ Serving global assets from: {global_assets_path}")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "Pipeline Report Generator - Python Backend",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "mongodb": "connected",  # TODO: Add actual DB check
        "shapefile_dir": str(settings.shapefile_dir),
        "upload_dir": str(settings.upload_dir),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
