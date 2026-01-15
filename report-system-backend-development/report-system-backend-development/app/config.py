"""
Configuration management for Python backend
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017/pipeline-reports"

    # Paths (relative to Backend/report system/)
    upload_dir: Path = Path("../pipeline-report-app/uploads")  # OLD - for backwards compatibility
    shapefile_dir: Path = Path("../../assets/shps")  # GeoJSON/Shapefile assets at root
    projects_dir: Path = Path("./projects")  # Project outputs in report system backend
    global_assets_dir: Path = Path("../../global_assets")  # Reusable assets at root

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # CORS
    nextjs_url: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        case_sensitive = False


def get_settings() -> Settings:
    """Get settings instance (cache disabled for Phase 1 testing)"""
    return Settings()


# Convenience functions
def get_upload_path(project_id: str, subdir: str = "") -> Path:
    """
    Get upload path for a project (OLD - for backwards compatibility)
    Use get_project_output_path() for new projects
    """
    settings = get_settings()
    base = settings.upload_dir / project_id
    if subdir:
        base = base / subdir
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_project_output_path(project_id: str, subdir: str = "") -> Path:
    """
    Get output path for a project in the new structure
    Saves to: projects/<project_id>/maps/ or projects/<project_id>/reports/
    """
    settings = get_settings()
    base = settings.projects_dir / str(project_id)
    if subdir:
        base = base / subdir
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_shapefile_path(filename: str) -> Path:
    """Get full path to shapefile"""
    settings = get_settings()
    return settings.shapefile_dir / filename


def get_asset_path(asset_id: str, subdir: str = "original") -> Path:
    """
    Get path for a global asset
    Structure: global_assets/<asset_id>/original/ or global_assets/<asset_id>/converted/
    """
    settings = get_settings()
    base = settings.global_assets_dir / str(asset_id) / subdir
    base.mkdir(parents=True, exist_ok=True)
    return base


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe storage
    Removes special characters, replaces spaces with underscores
    """
    import re
    # Keep only alphanumeric, dots, hyphens, underscores
    name = re.sub(r'[^\w\s.-]', '', filename)
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    # Remove multiple consecutive underscores
    name = re.sub(r'_+', '_', name)
    # Convert to lowercase
    return name.lower()
