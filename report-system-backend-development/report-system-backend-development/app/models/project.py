"""
Pydantic models for API requests/responses
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class IncidentData(BaseModel):
    """Incident data model"""
    incident_id: str = Field(..., alias="incidentId")
    sequence_number: int = Field(..., alias="sequenceNumber")
    description: str
    latitude: float
    longitude: float
    status: str  # "NEW" | "OLD" | "SUSPECTED"
    annotated_photos: List[str] = Field(default_factory=list, alias="annotatedPhotos")
    original_photos: List[str] = Field(default_factory=list, alias="originalPhotos")


class ProjectData(BaseModel):
    """Project data model"""
    project_name: str = Field(..., alias="projectName")
    project_code: str = Field(..., alias="projectCode")
    base_location: str = Field(..., alias="baseLocation")
    route_inspected: str = Field(..., alias="routeInspected")
    inspection_date: str = Field(..., alias="inspectionDate")
    pipeline_length_km: float = Field(..., alias="pipelineLengthKm")
    closest_flow_station: str = Field(..., alias="closestFlowStation")
    prepared_by: str = Field(..., alias="preparedBy")
    checked_by: str = Field(..., alias="checkedBy")
    approved_by: str = Field(..., alias="approvedBy")


class GenerateReportRequest(BaseModel):
    """Request to generate a report"""
    project_id: str = Field(..., alias="projectId")


class GenerateReportResponse(BaseModel):
    """Response after generating a report"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    processing_time_seconds: Optional[float] = None
