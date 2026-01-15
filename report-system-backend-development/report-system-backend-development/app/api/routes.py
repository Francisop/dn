"""
API Routes for report generation
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from app.models.project import GenerateReportRequest, GenerateReportResponse
from app.utils.mongodb import get_project_by_id, get_incidents_by_project_id, get_database
from app.services.pptx_generator import generate_pptx_report
from app.services.map_generator import generate_overview_map, MapGenerator
from app.services.photo_annotator import annotate_incident_photos
from app.services.pdf_converter import convert_pptx_to_pdf_async
from app.config import get_settings, get_upload_path, get_project_output_path, get_shapefile_path, get_asset_path, sanitize_filename
import time
import os
from datetime import datetime
from typing import List, Dict
from bson import ObjectId
from pathlib import Path
import aiofiles

router = APIRouter()


@router.post("/projects")
async def create_project(project_data: dict):
    """
    Create a new project in the database
    Returns the created project with its MongoDB _id
    """
    try:
        db = get_database()

        # Add timestamps
        project_data["createdAt"] = datetime.now()
        project_data["updatedAt"] = datetime.now()
        project_data["selectedPipelineAssetId"] = None
        project_data["selectedPipelineFilename"] = None

        # Insert into database
        result = await db.projects.insert_one(project_data)
        project_id = str(result.inserted_id)

        # Fetch the created project
        created_project = await db.projects.find_one({"_id": result.inserted_id})
        created_project["_id"] = project_id  # Convert ObjectId to string

        print(f"\n✅ Created project: {project_data.get('projectName')} (ID: {project_id})")

        return {
            "success": True,
            "data": created_project
        }

    except Exception as e:
        print(f"❌ Failed to create project: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")


@router.post("/generate-report", response_model=GenerateReportResponse)
async def generate_report(request: GenerateReportRequest):
    """
    Generate complete report (PPTX + annotated photos + map)

    Flow:
    1. Fetch project and incidents from MongoDB
    2. Generate overview map from shapefiles
    3. Annotate photos
    4. Generate PPTX with all content
    5. Return file paths
    """
    start_time = time.time()
    settings = get_settings()

    try:
        # 1. Fetch data from MongoDB
        project_id = request.project_id
        project = await get_project_by_id(project_id)

        if not project:
            raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

        incidents = await get_incidents_by_project_id(project_id)

        if not incidents:
            raise HTTPException(status_code=400, detail="No incidents found for this project")

        print(f"\n🚀 Starting report generation for project: {project_id}")
        print(f"   Project: {project.get('projectName')}")
        print(f"   Incidents: {len(incidents)}")

        # Prepare output paths - using new projects folder structure
        report_dir = get_project_output_path(project_id, "reports")
        maps_dir = get_project_output_path(project_id, "maps")

        map_output_path = str(maps_dir / "overview_map.png")
        pptx_output_path = str(report_dir / f"report_{project.get('projectCode', 'RPT')}.pptx")



        # HERE IS WHERE THE PAGES CONTENT ARE BEING GENERATED 


        # !!!!!!!!!! GENERATE MAPS !!!!!!!!!!
        # 2. Generate overview map from shapefiles
        print("\n📍 Step 1/4: Generating overview map...")

        # RESUME THIS PART BELLOW !!!!!!!!
        try:
            map_path = await generate_overview_map(
                shapefile_dir=str(settings.shapefile_dir),
                global_assets_dir=str(settings.global_assets_dir),
                project_data=project,
                incidents=incidents,
                output_path=map_output_path
            )
            print(f"   ✅ Map generated: {os.path.basename(map_path)}")
        except Exception as e:
            print(f"   ⚠️  Map generation failed: {e}")
            map_path = None

        # 2.5. Generate satellite imagery maps and legend
        print("\n🛰️  Step 2/4: Generating satellite imagery maps and legend...")
        satellite_overview_map = None
        satellite_incident_groups = []
        satellite_thumbnails = []
        incident_legend_map = None
        try:
            # Create MapGenerator instance
            map_gen = MapGenerator(
                global_assets_dir=str(settings.global_assets_dir),
                shapefile_dir=str(settings.shapefile_dir),
                project_data=project,
                incidents=incidents
            )

            # Generate large satellite overview - now returns tuple (map_paths, incident_groups)
            satellite_overview_path = str(maps_dir)
            print(f"   Generating satellite overview map at zoom level 12...")
            satellite_overview_map, satellite_incident_groups = map_gen.generate_satellite_overview_map(
                output_path=satellite_overview_path
            )
            print("!!!!!!!!!!!!! yeah yeah yeah")
            print(f"   ✅ Satellite overview generated: {len(satellite_overview_map)} maps with {len(satellite_incident_groups)} incident groups")

            # Generate incident legend map
            legend_path = str(maps_dir / "incident_legend.png")
            incident_legend_map = map_gen.generate_incident_legend_map(
                output_path=legend_path
            )
            if incident_legend_map:
                print(f"   ✅ Incident legend generated: {os.path.basename(incident_legend_map)}")

            # Generate thumbnails for each incident (reduced zoom for faster loading)
            # thumbnails_dir = get_upload_path(project_id, "maps/thumbnails")
            # for idx, incident in enumerate(incidents):
            #     thumbnail_path = str(thumbnails_dir / f"incident_{idx+1}_thumbnail.png")
            #     thumb = map_gen.generate_satellite_thumbnail(
            #         incident=incident,
            #         output_path=thumbnail_path,
            #         zoom_level=14  # Reduced from 16 to 14 for faster tile fetching
            #     )
            #     satellite_thumbnails.append(thumb)
            # print(f"   ✅ Generated {len(satellite_thumbnails)} incident thumbnails")

        except Exception as e:
            print(f"   ⚠️  Satellite map/legend generation failed: {e}")
            print(f"       Continuing without satellite imagery...")

        # 3. Annotate photos
        # print("\n📸 Step 3/4: Annotating incident photos...")
        # try:
        #     annotated_incidents = await annotate_incident_photos(
        #         pipeline_name=project.get('routeInspected', 'Pipeline'),
        #         incidents=incidents,
        #         upload_dir=str(get_upload_path(project_id))
        #     )
        #     print(f"   ✅ Photos annotated")
        # except Exception as e:
        #     print(f"   ⚠️  Photo annotation failed: {e}")
        #     annotated_incidents = incidents





        annotated_incidents = incidents  # Skipping annotation for now
        # 4. Generate PPTX with all content
        print("\n📄 Step 4/4: Generating PPTX report...")
        try:
            pptx_path = await generate_pptx_report(
                project_data=project,
                incidents=annotated_incidents,
                overview_map_path=map_path,
                output_path=pptx_output_path,
                satellite_overview_map=satellite_overview_map,
                satellite_incident_groups=satellite_incident_groups,
                satellite_thumbnails=satellite_thumbnails,
                incident_legend_map=incident_legend_map
            )
            print("!!!!!!!!!!!!! yeah yeah yeah worked worked worked")
            print(f"   ✅ PPTX generated: {os.path.basename(pptx_path)}")
        except Exception as e:
            print(f"   ❌ PPTX generation failed: {e}")
            raise

        # 5. Convert PPTX to PDF
        print("\n📄 Step 5/5: Converting PPTX to PDF...")
        pdf_path = None
        pdf_url = None
        try:
            # Generate PDF in same directory as PPTX
            pdf_output_path = Path(pptx_path).with_suffix('.pdf')
            pdf_path = await convert_pptx_to_pdf_async(pptx_path, str(pdf_output_path))

            pdf_filename = os.path.basename(pdf_path)
            pdf_url = f"/uploads/{project_id}/reports/{pdf_filename}"

            print(f"   ✅ PDF generated: {pdf_filename}")
        except Exception as e:
            print(f"   ⚠️ PDF conversion failed (PPTX still available): {e}")
            # Don't fail the whole process if PDF conversion fails
            # User will still get the PPTX file

        processing_time = time.time() - start_time

        pptx_filename = os.path.basename(pptx_path)
        map_filename = os.path.basename(map_path) if map_path else None

        # Create web URLs for static file serving
        # Backend serves projects folder at /uploads endpoint (see main.py line 66)
        report_url = f"/uploads/{project_id}/reports/{pptx_filename}"
        map_url = f"/uploads/{project_id}/maps/{map_filename}" if map_path else None

        print(f"\n✅ Report generation complete! ({processing_time:.2f}s)")
        print(f"   PPTX URL: {report_url}")
        print(f"   PDF URL: {pdf_url if pdf_url else 'N/A'}")
        print(f"   Map URL: {map_url}")

        return GenerateReportResponse(
            success=True,
            data={
                "project_id": project_id,
                "report_url": report_url,
                "pdf_url": pdf_url,
                "map_url": map_url,
                "incident_count": len(incidents),
                "filename": os.path.basename(pptx_path),
                "pdf_filename": os.path.basename(pdf_path) if pdf_path else None
            },
            processing_time_seconds=round(processing_time, 2)
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"\n❌ Report generation failed: {e}")
        import traceback
        traceback.print_exc()

        return GenerateReportResponse(
            success=False,
            error=str(e)
        )


# ========== ASSET MANAGEMENT ENDPOINTS ==========

@router.post("/assets/upload")
async def upload_asset(
    file: UploadFile = File(...),
    name: str = None
):
    """
    Upload a new pipeline GeoJSON asset

    Flow:
    1. Validate file is .geojson
    2. Insert asset metadata into MongoDB (gets auto-generated _id)
    3. Create folder structure: global_assets/<asset_id>/original/
    4. Save file with sanitized filename
    5. Update asset record with file path
    """
    try:
        # Validate file type
        if not file.filename.endswith('.geojson'):
            raise HTTPException(status_code=400, detail="Only .geojson files are allowed")

        # Sanitize filename
        original_filename = file.filename
        sanitized_filename = sanitize_filename(original_filename)

        # Use provided name or derive from filename
        asset_name = name if name else original_filename.replace('.geojson', '').replace('_', ' ').title()

        # 1. Insert asset metadata into MongoDB (get auto-generated _id)
        db = get_database()
        asset_doc = {
            "name": asset_name,
            "type": "pipeline",
            "originalFilename": original_filename,
            "sanitizedFilename": sanitized_filename,
            "uploadedAt": datetime.now(),
            "usedByProjects": []
        }

        result = await db.assets.insert_one(asset_doc)
        asset_id = str(result.inserted_id)

        print(f"\n📁 Uploading asset: {asset_name}")
        print(f"   Asset ID: {asset_id}")
        print(f"   Original filename: {original_filename}")
        print(f"   Sanitized filename: {sanitized_filename}")

        # 2. Create folder structure
        asset_path = get_asset_path(asset_id, "original")
        file_path = asset_path / sanitized_filename

        # 3. Save uploaded file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)

        print(f"   ✅ File saved to: {file_path}")

        # 4. Update asset record with path info
        relative_path = f"global_assets/{asset_id}/original/"
        await db.assets.update_one(
            {"_id": result.inserted_id},
            {"$set": {
                "path": relative_path,
                "fullPath": str(file_path),
                "fileSize": len(content)
            }}
        )

        return {
            "success": True,
            "data": {
                "assetId": asset_id,
                "name": asset_name,
                "filename": sanitized_filename,
                "path": relative_path,
                "uploadedAt": asset_doc["uploadedAt"].isoformat()
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Asset upload failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Asset upload failed: {str(e)}")


@router.get("/assets")
async def list_assets():
    """
    Get all pipeline assets from database
    Returns list of assets with metadata
    """
    try:
        print("\n🔍 GET /api/assets - Fetching assets from MongoDB...")
        db = get_database()

        # Fetch all assets, sorted by upload date (newest first)
        assets_cursor = db.assets.find({"type": "pipeline"}).sort("uploadedAt", -1)
        assets = await assets_cursor.to_list(length=None)

        # Convert ObjectId to string for JSON serialization
        asset_list = []
        for asset in assets:
            asset_data = {
                "id": str(asset["_id"]),
                "name": asset.get("name"),
                "filename": asset.get("sanitizedFilename"),
                "originalFilename": asset.get("originalFilename"),
                "path": asset.get("path"),
                "uploadedAt": asset.get("uploadedAt").isoformat() if asset.get("uploadedAt") else None,
                "usedByProjects": asset.get("usedByProjects", [])
            }
            asset_list.append(asset_data)
            print(f"   - {asset_data['name']} (ID: {asset_data['id']})")

        print(f"\n✅ Returning {len(asset_list)} assets to client")

        return {
            "success": True,
            "data": asset_list,
            "count": len(asset_list)
        }

    except Exception as e:
        print(f"❌ Failed to fetch assets: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch assets: {str(e)}")


@router.delete("/assets/{asset_id}")
async def delete_asset(asset_id: str):
    """
    Delete a specific asset by ID
    Removes both the database record and the file from disk
    """
    try:
        from bson import ObjectId
        from pathlib import Path
        import shutil

        db = get_database()

        # 1. Fetch asset from database
        try:
            asset = await db.assets.find_one({"_id": ObjectId(asset_id)})
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid asset ID format: {str(e)}")

        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")

        print(f"\n🗑️  Deleting asset: {asset.get('name')}")

        # 2. Delete entire asset folder from disk
        full_path = asset.get("fullPath")
        if full_path:
            file_path = Path(full_path)
            # Delete the entire asset folder: global_assets/<asset_id>
            asset_folder = file_path.parent.parent  # global_assets/<asset_id>

            if asset_folder.exists() and asset_folder.is_dir():
                try:
                    shutil.rmtree(asset_folder)
                    print(f"   ✅ Deleted asset folder and all contents: {asset_folder}")
                except Exception as e:
                    print(f"   ⚠️  Warning: Could not delete asset folder: {e}")
                    # Try to at least delete the file
                    try:
                        if file_path.exists():
                            file_path.unlink()
                            print(f"   ✅ Deleted file: {file_path}")
                    except Exception as e2:
                        print(f"   ⚠️  Warning: Could not delete file: {e2}")

        # 3. Delete from database
        delete_result = await db.assets.delete_one({"_id": ObjectId(asset_id)})

        if delete_result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Asset not found in database")

        print(f"   ✅ Asset deleted from database")

        return {
            "success": True,
            "message": f"Asset '{asset.get('name')}' deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to delete asset: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to delete asset: {str(e)}")


@router.get("/assets/{asset_id}")
async def get_asset(asset_id: str):
    """
    Get a specific asset by ID
    """
    try:
        db = get_database()

        # Fetch asset from database
        asset = await db.assets.find_one({"_id": ObjectId(asset_id)})

        if not asset:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")

        return {
            "success": True,
            "data": {
                "id": str(asset["_id"]),
                "name": asset.get("name"),
                "filename": asset.get("sanitizedFilename"),
                "originalFilename": asset.get("originalFilename"),
                "path": asset.get("path"),
                "fullPath": asset.get("fullPath"),
                "uploadedAt": asset.get("uploadedAt").isoformat() if asset.get("uploadedAt") else None,
                "usedByProjects": asset.get("usedByProjects", []),
                "fileSize": asset.get("fileSize")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to fetch asset: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch asset: {str(e)}")


@router.get("/assets/{asset_id}/geojson")
async def get_asset_geojson(asset_id: str):
    """
    Get the GeoJSON content of a specific asset
    Returns the actual GeoJSON data for map display
    """
    try:
        import json

        db = get_database()

        # Fetch asset from database
        asset = await db.assets.find_one({"_id": ObjectId(asset_id)})

        if not asset:
            raise HTTPException(status_code=404, detail=f"Asset not found: {asset_id}")

        # Read GeoJSON file from disk
        full_path = asset.get("fullPath")
        if not full_path:
            raise HTTPException(status_code=500, detail="Asset file path not found")

        file_path = Path(full_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Asset file not found on disk: {full_path}")

        # Read and parse GeoJSON
        with open(file_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)

        print(f"📍 Loaded GeoJSON for asset: {asset.get('name')}")

        return {
            "success": True,
            "data": geojson_data
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to fetch asset GeoJSON: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch asset GeoJSON: {str(e)}")
