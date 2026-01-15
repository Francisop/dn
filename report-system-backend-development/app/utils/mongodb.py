"""
MongoDB connection utilities
"""

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from bson import ObjectId
from app.config import get_settings
from typing import Optional

# Global MongoDB client
_mongodb_client: Optional[AsyncIOMotorClient] = None


async def connect_to_mongodb():
    """Connect to MongoDB"""
    global _mongodb_client
    settings = get_settings()

    try:
        _mongodb_client = AsyncIOMotorClient(settings.mongodb_uri)
        # Verify connection
        await _mongodb_client.admin.command('ping')
        print(f"✅ Connected to MongoDB: {settings.mongodb_uri}")
    except ConnectionFailure as e:
        print(f"❌ Failed to connect to MongoDB: {e}")
        raise


async def close_mongodb_connection():
    """Close MongoDB connection"""
    global _mongodb_client
    if _mongodb_client:
        _mongodb_client.close()
        print("✅ Closed MongoDB connection")


def get_database():
    """Get database instance"""
    if _mongodb_client is None:
        raise RuntimeError("MongoDB client not initialized. Call connect_to_mongodb() first.")

    settings = get_settings()
    db_name = settings.mongodb_uri.split("/")[-1].split("?")[0]
    return _mongodb_client[db_name]


async def get_project_by_id(project_id: str):
    """Fetch project from MongoDB"""
    db = get_database()
    # Convert string ID to ObjectId for MongoDB query
    project = await db.projects.find_one({"_id": ObjectId(project_id)})
    return project


async def get_incidents_by_project_id(project_id: str):
    """Fetch all incidents for a project"""
    db = get_database()
    incidents = []
    # Convert string ID to ObjectId for MongoDB query
    async for incident in db.incidents.find({"projectId": ObjectId(project_id)}):
        incidents.append(incident)
    return incidents
