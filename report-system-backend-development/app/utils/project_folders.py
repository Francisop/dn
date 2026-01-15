"""
Utility functions for managing project folder structure
"""
from pathlib import Path
from typing import Tuple
import uuid


def create_project_folders(project_id: str, base_projects_dir: Path) -> Tuple[Path, Path]:
    """
    Create folder structure for a new project

    Args:
        project_id: The project ID (from MongoDB)
        base_projects_dir: Base projects directory path

    Returns:
        Tuple of (maps_dir, reports_dir)
    """
    project_dir = base_projects_dir / str(project_id)
    maps_dir = project_dir / 'maps'
    reports_dir = project_dir / 'reports'

    # Create directories
    maps_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    print(f"   ✅ Created project folders: {project_dir.name}/")

    return maps_dir, reports_dir


def get_project_paths(project_id: str, base_projects_dir: Path) -> dict:
    """
    Get all relevant paths for a project

    Args:
        project_id: The project ID
        base_projects_dir: Base projects directory

    Returns:
        Dictionary with paths: project_dir, maps_dir, reports_dir
    """
    project_dir = base_projects_dir / str(project_id)

    return {
        'project_dir': project_dir,
        'maps_dir': project_dir / 'maps',
        'reports_dir': project_dir / 'reports'
    }


def create_asset_folders(asset_id: str, base_assets_dir: Path) -> Tuple[Path, Path]:
    """
    Create folder structure for a new asset

    Args:
        asset_id: Unique asset identifier (UUID or hash)
        base_assets_dir: Base global_assets directory

    Returns:
        Tuple of (original_dir, converted_dir)
    """
    asset_dir = base_assets_dir / asset_id
    original_dir = asset_dir / 'original'
    converted_dir = asset_dir / 'converted'

    # Create directories
    original_dir.mkdir(parents=True, exist_ok=True)
    converted_dir.mkdir(parents=True, exist_ok=True)

    print(f"   ✅ Created asset folders: {asset_id}/")

    return original_dir, converted_dir


def generate_asset_id() -> str:
    """Generate a unique asset ID"""
    return str(uuid.uuid4())


def get_asset_paths(asset_id: str, base_assets_dir: Path) -> dict:
    """
    Get all relevant paths for an asset

    Args:
        asset_id: The asset ID
        base_assets_dir: Base global_assets directory

    Returns:
        Dictionary with paths: asset_dir, original_dir, converted_dir
    """
    asset_dir = base_assets_dir / asset_id

    return {
        'asset_dir': asset_dir,
        'original_dir': asset_dir / 'original',
        'converted_dir': asset_dir / 'converted'
    }


def resolve_asset_path(asset_reference: dict, base_assets_dir: Path) -> Path:
    """
    Resolve asset path from database reference

    Args:
        asset_reference: Asset reference from database
            {
                "assetId": "uuid",
                "path": "global_assets/.../file.geojson"
            }
        base_assets_dir: Base global_assets directory

    Returns:
        Full path to the asset file
    """
    # If path is relative, resolve from base_assets_dir
    if 'path' in asset_reference:
        # Remove 'global_assets/' prefix if present
        path_str = asset_reference['path']
        if path_str.startswith('global_assets/'):
            path_str = path_str.replace('global_assets/', '', 1)

        return base_assets_dir / path_str

    # Fallback: construct from assetId
    asset_id = asset_reference.get('assetId')
    filename = asset_reference.get('filename', 'unknown.geojson')

    return base_assets_dir / asset_id / 'converted' / filename
