from __future__ import annotations

from typing import Dict, List, Optional, Literal, Any
from pydantic import BaseModel, Field


ArtifactFormat = Literal["csv"]


class ArtifactRef(BaseModel):
    """Reference to a table artifact written by the server."""
    path: str = Field(..., description="Absolute or project-relative path to the artifact file.")
    format: ArtifactFormat = Field("csv", description="Artifact serialization format.")
    rows: int = Field(..., ge=0, description="Number of rows in the table.")
    columns: List[str] = Field(..., description="Column names.")
    description: Optional[str] = Field(None, description="Human-readable description.")


class TableInfo(BaseModel):
    name: str
    filename: Optional[str] = None
    rows: int
    columns: List[str]


class ListStaticTablesOutput(BaseModel):
    static_dir: str
    tables: List[TableInfo]


class DescribeTableOutput(BaseModel):
    table: str
    rows: int
    columns: List[Dict[str, Any]]
    preview: List[Dict[str, Any]]


class AgenciesOutput(BaseModel):
    agencies: List[Dict[str, Any]]


class RoutesOutput(BaseModel):
    routes: ArtifactRef


class StopsOutput(BaseModel):
    stops: ArtifactRef


class BBox(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class StopsBBoxOutput(BaseModel):
    bbox: Optional[BBox] = None
    missing_coords: int = 0


class RouteTripCountsOutput(BaseModel):
    counts: ArtifactRef


class TripStopSequenceOutput(BaseModel):
    trip_id: str
    stop_sequence: ArtifactRef


class RouteStopsOutput(BaseModel):
    route_id: str
    stops: ArtifactRef


class StopRoutesOutput(BaseModel):
    stop_id: str
    routes: ArtifactRef


class IntegrityReportOutput(BaseModel):
    missing_route_refs_in_trips: int
    missing_trip_refs_in_stop_times: int
    details: Optional[Dict[str, ArtifactRef]] = None


class DataQualityReportOutput(BaseModel):
    summary: Dict[str, Any]
    artifacts: Dict[str, ArtifactRef] = Field(default_factory=dict)
