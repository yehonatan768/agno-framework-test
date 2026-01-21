from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict


ArtifactFormat = Literal["csv"]


class ArtifactRef(BaseModel):
    """Reference to a table artifact written by the server."""
    path: str = Field(..., description="Absolute or project-relative path to the artifact file.")
    format: ArtifactFormat = Field("csv", description="Artifact serialization format.")
    rows: int = Field(..., ge=0, description="Number of rows in the table.")
    columns: List[str] = Field(..., description="Column names.")
    description: Optional[str] = Field(None, description="Human-readable description.")


class LoadSnapshotOutput(BaseModel):
    feed_timestamp: Optional[int] = Field(None, description="GTFS-RT feed header timestamp, if present.")
    vehicle_positions: ArtifactRef
    trip_updates: ArtifactRef
    trip_update_stop_times: ArtifactRef
    alerts: ArtifactRef


class LoadStaticOutput(BaseModel):
    static_tables: Dict[str, ArtifactRef] = Field(..., description="Mapping: table_name -> artifact ref")


class VehiclePosition(BaseModel):
    vehicle_id: str
    lat: float
    lon: float
    route_id: Optional[str] = None
    trip_id: Optional[str] = None
    feed_timestamp: Optional[int] = None
    vehicle_timestamp: Optional[int] = None


class NearbyVehicle(BaseModel):
    vehicle_id: str
    distance_m: float


class NearbyVehiclesOutput(BaseModel):
    center_vehicle: VehiclePosition
    nearby: List[NearbyVehicle]
    count_considered: int = Field(..., ge=0, description="How many vehicles were considered in the search.")


class RouteVehiclesOutput(BaseModel):
    route_id: str
    vehicle_ids: List[str]


class SnapshotStatsOutput(BaseModel):
    feed_timestamp: Optional[int] = None
    vehicles_active: int
    trip_updates: int
    alerts: int
    vehicles_with_missing_gps: int


class EnrichedVehiclesOutput(BaseModel):
    """An enriched realtime view written as an artifact."""
    artifact: ArtifactRef
    join_notes: Optional[str] = None


class FetchRealtimeOutput(BaseModel):
    ok: bool
    snapshot_dir: str | None = None
    message: str = ""


class ActiveRoute(BaseModel):
    """A route that currently has at least one active vehicle."""

    route_id: str
    route_short_name: Optional[str] = None
    route_long_name: Optional[str] = None
    vehicle_ids: List[str] = Field(default_factory=list)
    vehicles_active: int = Field(0, ge=0)


class ActiveRoutesOutput(BaseModel):
    """Active routes (from latest realtime snapshot) enriched with static route names."""

    feed_timestamp: Optional[int] = None
    routes: List[ActiveRoute] = Field(default_factory=list)
