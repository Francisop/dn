"""
Test script for WGS84 map generation
Fetches real data from MongoDB cloud and generates map with incident legend
"""
import asyncio
from app.services.map_generator import MapGenerator
from app.config import get_settings
from app.utils.mongodb import connect_to_mongodb, close_mongodb_connection, get_project_by_id, get_incidents_by_project_id


async def main():
    settings = get_settings()

    # Connect to MongoDB (cloud)
    print("🔌 Connecting to MongoDB...")
    await connect_to_mongodb()

    # Fetch real project data
    project_id = "6921a48e15014d207fba65dc"

    print(f"📦 Fetching project: {project_id}")
    project_data = await get_project_by_id(project_id)

    if not project_data:
        print(f"❌ Project not found: {project_id}")
        await close_mongodb_connection()
        return

    print(f"✅ Project found: {project_data.get('projectName')}")

    # Fetch real incidents from MongoDB
    print(f"📍 Fetching incidents for project...")
    incidents = await get_incidents_by_project_id(project_id)

    if not incidents:
        print(f"⚠️  No incidents found for project")
        await close_mongodb_connection()
        return

    print(f"✅ Found {len(incidents)} incidents")

    # Create MapGenerator instance
    map_gen = MapGenerator(
        shapefile_dir=str(settings.shapefile_dir),
        project_data=project_data,
        incidents=incidents
    )

    print("\n🧪 Testing Map Generation")
    print(f"   Shapefile dir: {settings.shapefile_dir}")
    print(f"   Output dir: test_output/")
    print()

    # Generate overview map
    overview_path = 'test_output/overview_map_wgs84.png'
    result = map_gen.generate_overview_map(overview_path)

    # Generate satellite overview map
    satellite_path = 'test_output/satellite_map_wgs84.png'
    satellite_result = map_gen.generate_satellite_overview_map(satellite_path)

    # Generate incident legend map
    legend_path = 'test_output/incident_legend.png'
    legend_result = map_gen.generate_incident_legend_map(legend_path)

    print(f"\n✅ All maps generated successfully!")
    print(f"   Overview Map: {result}")
    print(f"   Satellite Map: {satellite_result}")
    print(f"   Legend Map: {legend_result}")

    # Close MongoDB connection
    print("\n🔌 Closing MongoDB connection...")
    await close_mongodb_connection()

if __name__ == "__main__":
    asyncio.run(main())
