"""
MongoDB Seeding Script with New Project Structure
This will create project folders automatically
"""

import asyncio
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv
import os
from pathlib import Path
import sys

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.utils.project_folders import create_project_folders

# Load environment variables
load_dotenv()

# MongoDB connection
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/pipeline-reports")


async def seed_database():
    """Seed the database with dummy data and create project folders"""

    # Connect to MongoDB
    client = AsyncIOMotorClient(MONGODB_URI)
    db_name = MONGODB_URI.split("/")[-1].split("?")[0]
    db = client[db_name]

    print(f"🔌 Connected to MongoDB: {db_name}")

    # Base directories
    base_dir = Path(__file__).parent.parent
    projects_dir = base_dir / 'projects'
    global_assets_dir = base_dir / 'global_assets'

    # Ensure directories exist
    projects_dir.mkdir(exist_ok=True)
    global_assets_dir.mkdir(exist_ok=True)

    # Create project from STB-FLB-AITEO report (04-10-2024)
    project_data = {
        "projectName": "STB-FLB-AITEO Surveillance Project",
        "projectCode": "STB-FLB-AITEO",
        "baseLocation": "STB",
        "routeInspected": "FLB-AITEO Pipeline Route",
        "inspectionDate": "2024-10-04",
        "pipelineLengthKm": 5.0,
        "closestFlowStation": "AITEO Flow Station",
        "preparedBy": "Brown Joshua (IEGS)",
        "checkedBy": "Frank Nnaji",
        "approvedBy": "Ernest I. Tomwapre",
        "selectedPipelineAssetId": None,  # Will be set when user selects a pipeline
        "selectedPipelineFilename": None,  # Denormalized for easy access
        "assets": {
            "pipeline": {
                "assetId": "default-assets",
                "name": "Nengiftom Pipeline RoW",
                "type": "pipeline",
                "format": "geojson",
                "path": f"global_assets/default-assets/converted/Nengiftom Pipeline RoW.geojson"
            },
            "settlements": {
                "assetId": "default-assets",
                "name": "Bayelsa Settlements",
                "type": "point",
                "format": "geojson",
                "path": "global_assets/default-assets/converted/BAYELSA_SETTLEMENT.geojson"
            },
            "rivers": {
                "assetId": "default-assets",
                "name": "Bayelsa Rivers",
                "type": "line",
                "format": "geojson",
                "path": "global_assets/default-assets/converted/Bayelsa_Rivers.geojson"
            },
            "boundaries": {
                "assetId": "default-assets",
                "name": "LGA Boundaries",
                "type": "polygon",
                "format": "geojson",
                "path": "global_assets/default-assets/converted/LGA_BOUNDARY_84.geojson"
            }
        },
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow()
    }

    print("\n📝 Creating project...")
    project_result = await db.projects.insert_one(project_data)
    project_id = project_result.inserted_id
    print(f"   ✅ Project created with ID: {project_id}")

    # Create project folder structure
    print(f"\n📁 Creating project folders...")
    maps_dir, reports_dir = create_project_folders(project_id, projects_dir)

    # Update project with output paths
    await db.projects.update_one(
        {"_id": project_id},
        {"$set": {
            "outputPaths": {
                "mapsDir": f"projects/{project_id}/maps/",
                "reportsDir": f"projects/{project_id}/reports/"
            }
        }}
    )
    print(f"   ✅ Updated project with output paths")

    # Create incidents from STB report (04-10-2024 coords.txt)
    incidents = [
        {
            "projectId": project_id,
            "incidentId": "STB/OCT24/001",
            "sequenceNumber": 1,
            "description": "Suspicious boat detected in pipeline area",
            "latitude": 4.479578,
            "longitude": 6.482570,
            "status": "NEW",
            "chainage": "N/A",
            "severity": "High",
            "annotatedPhotos": [],
            "originalPhotos": [],
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        },
        {
            "projectId": project_id,
            "incidentId": "STB/OCT24/002",
            "sequenceNumber": 2,
            "description": "Insertion point detected on pipeline route",
            "latitude": 4.491752,
            "longitude": 6.492959,
            "status": "NEW",
            "chainage": "N/A",
            "severity": "Critical",
            "annotatedPhotos": [],
            "originalPhotos": [],
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        },
        {
            "projectId": project_id,
            "incidentId": "STB/OCT24/003",
            "sequenceNumber": 3,
            "description": "Insertion point detected on pipeline route",
            "latitude": 4.517912,
            "longitude": 6.495946,
            "status": "NEW",
            "chainage": "N/A",
            "severity": "Critical",
            "annotatedPhotos": [],
            "originalPhotos": [],
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
    ]

    print("\n📍 Creating incidents...")
    incidents_result = await db.incidents.insert_many(incidents)
    print(f"   ✅ Created {len(incidents_result.inserted_ids)} incidents")

    # Print summary
    print("\n" + "="*60)
    print("✅ DATABASE SEEDING COMPLETE!")
    print("="*60)
    print(f"\n📊 Summary:")
    print(f"   - Project ID: {project_id}")
    print(f"   - Project Code: {project_data['projectCode']}")
    print(f"   - Incidents: {len(incidents)}")
    print(f"   - Maps Dir: projects/{project_id}/maps/")
    print(f"   - Reports Dir: projects/{project_id}/reports/")
    print(f"\n🚀 Test report generation with:")
    print(f'   curl -X POST http://localhost:8000/api/generate-report \\')
    print(f'        -H "Content-Type: application/json" \\')
    print(f'        -d \'{{"projectId": "{project_id}"}}\'')
    print("\n" + "="*60 + "\n")

    # Close connection
    client.close()


if __name__ == "__main__":
    print("\n🌱 Starting database seeding with new structure...\n")
    asyncio.run(seed_database())
