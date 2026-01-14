from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from .schemas import (
    ArtifactRef,
    LoadSnapshotOutput,
    LoadStaticOutput,
    VehiclePosition,
    NearbyVehiclesOutput,
    NearbyVehicle,
    RouteVehiclesOutput,
    SnapshotStatsOutput,
    FetchRealtimeOutput,
    EnrichedVehiclesOutput,
)

# Expected to exist in your repo:
#   - src/sources/repository.py (TransitRepository)
#   - src/utils/yaml.py (load_yaml + resolve_path support)
from src.sources.repository import TransitRepository
from src.utils.yaml import load_yaml
from src.sources.gtfs_realtime.fetch import main as fetch_realtime_main


def _artifact_dir() -> Path:
    """Where the server writes table artifacts."""
    cfg = load_yaml("src/config/paths.yaml")
    out = cfg.get("paths.artifacts.execution_dir", "dataset/artifacts/execution")
    p = cfg.resolve_path(out)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_df(df: pd.DataFrame, name: str, description: Optional[str] = None) -> ArtifactRef:
    out_dir = _artifact_dir()
    path = out_dir / f"{name}.csv"
    df.to_csv(path, index=False)
    return ArtifactRef(
        path=str(path),
        format="csv",
        rows=int(len(df)),
        columns=[str(c) for c in df.columns],
        description=description,
    )


def _ensure_latest_snapshot_dir(repo: TransitRepository) -> Path:
    latest = repo.latest_snapshot_dir()
    if latest is None:
        raise FileNotFoundError("No snapshot directories found under dataset/realtime")
    return Path(latest)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance on Earth in meters."""
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_latest_snapshot() -> LoadSnapshotOutput:
    """Load the latest realtime snapshot directory and export its tables as artifacts."""
    repo = TransitRepository.from_paths_yaml("src/config/paths.yaml")
    snap_dir = _ensure_latest_snapshot_dir(repo)
    frames = repo.load_realtime_snapshot(snap_dir)

    return LoadSnapshotOutput(
        feed_timestamp=getattr(frames, "feed_timestamp", None),
        vehicle_positions=_write_df(frames.vehicle_positions, "vehicle_positions", "GTFS-RT vehicle positions"),
        trip_updates=_write_df(frames.trip_updates, "trip_updates", "GTFS-RT trip updates"),
        trip_update_stop_times=_write_df(frames.trip_update_stop_times, "trip_update_stop_times", "GTFS-RT stop time updates"),
        alerts=_write_df(frames.alerts, "alerts", "GTFS-RT alerts"),
    )


def load_snapshot_dir(snapshot_dir: str) -> LoadSnapshotOutput:
    """Load a specific snapshot directory and export its tables as artifacts."""
    repo = TransitRepository.from_paths_yaml("src/config/paths.yaml")
    frames = repo.load_realtime_snapshot(snapshot_dir)

    return LoadSnapshotOutput(
        feed_timestamp=getattr(frames, "feed_timestamp", None),
        vehicle_positions=_write_df(frames.vehicle_positions, "vehicle_positions", "GTFS-RT vehicle positions"),
        trip_updates=_write_df(frames.trip_updates, "trip_updates", "GTFS-RT trip updates"),
        trip_update_stop_times=_write_df(frames.trip_update_stop_times, "trip_update_stop_times", "GTFS-RT stop time updates"),
        alerts=_write_df(frames.alerts, "alerts", "GTFS-RT alerts"),
    )


def load_static_tables() -> LoadStaticOutput:
    """Load static GTFS tables dynamically based on providers.yaml list and export as artifacts."""
    from src.sources.gtfs_static.tables import load_static_tables_from_yaml

    tables = load_static_tables_from_yaml("src/config/providers.yaml", "provider.static")
    out: Dict[str, ArtifactRef] = {}
    for name, df in tables.tables.items():
        out[name] = _write_df(df, f"static_{name}", f"Static GTFS table: {name}")
    return LoadStaticOutput(static_tables=out)


def snapshot_stats() -> SnapshotStatsOutput:
    """Quick realtime snapshot statistics."""
    repo = TransitRepository.from_paths_yaml("src/config/paths.yaml")
    snap_dir = _ensure_latest_snapshot_dir(repo)
    frames = repo.load_realtime_snapshot(snap_dir)

    vp = frames.vehicle_positions
    vehicles_active = int(vp["vehicle_id"].nunique()) if "vehicle_id" in vp.columns else int(len(vp))
    missing_gps = (
        int(vp[vp["lat"].isna() | vp["lon"].isna()].shape[0])
        if set(["lat", "lon"]).issubset(vp.columns)
        else 0
    )

    return SnapshotStatsOutput(
        feed_timestamp=getattr(frames, "feed_timestamp", None),
        vehicles_active=vehicles_active,
        trip_updates=int(len(frames.trip_updates)),
        alerts=int(len(frames.alerts)),
        vehicles_with_missing_gps=missing_gps,
    )


def get_vehicle_position(vehicle_id: str) -> VehiclePosition:
    """Return current position for a vehicle from latest snapshot."""
    repo = TransitRepository.from_paths_yaml("src/config/paths.yaml")
    snap_dir = _ensure_latest_snapshot_dir(repo)
    frames = repo.load_realtime_snapshot(snap_dir)

    vp = frames.vehicle_positions
    if vp.empty or "vehicle_id" not in vp.columns:
        raise ValueError("vehicle_positions is empty or missing vehicle_id column")

    row = vp[vp["vehicle_id"].astype(str) == str(vehicle_id)]
    if row.empty:
        raise KeyError(f"Vehicle not found in snapshot: {vehicle_id}")

    r0 = row.iloc[0]
    if pd.isna(r0.get("lat")) or pd.isna(r0.get("lon")):
        raise ValueError(f"Vehicle {vehicle_id} has missing lat/lon in snapshot")

    return VehiclePosition(
        vehicle_id=str(vehicle_id),
        lat=float(r0["lat"]),
        lon=float(r0["lon"]),
        route_id=str(r0.get("route_id")) if pd.notna(r0.get("route_id")) else None,
        trip_id=str(r0.get("trip_id")) if pd.notna(r0.get("trip_id")) else None,
        feed_timestamp=getattr(frames, "feed_timestamp", None),
        vehicle_timestamp=int(r0.get("vehicle_timestamp")) if pd.notna(r0.get("vehicle_timestamp")) else None,
    )


def vehicles_on_route(route_id: str) -> RouteVehiclesOutput:
    """List vehicle IDs currently on a given route from latest snapshot."""
    repo = TransitRepository.from_paths_yaml("src/config/paths.yaml")
    snap_dir = _ensure_latest_snapshot_dir(repo)
    frames = repo.load_realtime_snapshot(snap_dir)

    vp = frames.vehicle_positions
    if vp.empty:
        return RouteVehiclesOutput(route_id=str(route_id), vehicle_ids=[])

    if "route_id" not in vp.columns or "vehicle_id" not in vp.columns:
        raise ValueError("vehicle_positions missing required columns route_id/vehicle_id")

    ids = (
        vp[vp["route_id"].astype(str) == str(route_id)]["vehicle_id"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )
    return RouteVehiclesOutput(route_id=str(route_id), vehicle_ids=ids)


def vehicles_near_vehicle(vehicle_id: str, radius_m: float, limit: int = 50) -> NearbyVehiclesOutput:
    """Find vehicles within radius of the given vehicle (latest snapshot)."""
    repo = TransitRepository.from_paths_yaml("src/config/paths.yaml")
    snap_dir = _ensure_latest_snapshot_dir(repo)
    frames = repo.load_realtime_snapshot(snap_dir)
    vp = frames.vehicle_positions

    if vp.empty or not set(["vehicle_id", "lat", "lon"]).issubset(vp.columns):
        raise ValueError("vehicle_positions missing required columns vehicle_id/lat/lon")

    center = get_vehicle_position(vehicle_id)
    valid = vp.dropna(subset=["lat", "lon", "vehicle_id"]).copy()
    count_considered = int(len(valid))

    nearby = []
    for _, r in valid.iterrows():
        vid = str(r["vehicle_id"])
        if vid == str(vehicle_id):
            continue
        d = _haversine_m(center.lat, center.lon, float(r["lat"]), float(r["lon"]))
        if d <= float(radius_m):
            nearby.append((vid, d))

    nearby.sort(key=lambda x: x[1])
    nearby = nearby[: int(limit)]

    return NearbyVehiclesOutput(
        center_vehicle=center,
        nearby=[NearbyVehicle(vehicle_id=v, distance_m=float(d)) for v, d in nearby],
        count_considered=count_considered,
    )


def build_enriched_vehicle_view() -> EnrichedVehiclesOutput:
    """Build an enriched vehicle view by joining realtime positions with static trips/routes."""
    repo = TransitRepository.from_paths_yaml("src/config/paths.yaml")
    snap_dir = _ensure_latest_snapshot_dir(repo)
    frames = repo.load_realtime_snapshot(snap_dir)

    from src.sources.gtfs_static.tables import load_static_tables_from_yaml
    static = load_static_tables_from_yaml("src/config/providers.yaml", "provider.static")

    vp = frames.vehicle_positions.copy()
    trips = static.tables.get("trips", pd.DataFrame())
    routes = static.tables.get("routes", pd.DataFrame())

    notes = []
    df = vp

    if not trips.empty and "trip_id" in df.columns and "trip_id" in trips.columns:
        df = df.merge(trips, on="trip_id", how="left", suffixes=("", "_trip"))
        notes.append("joined trips on trip_id")
    else:
        notes.append("skipped trips join (missing trips or trip_id)")

    if not routes.empty and "route_id" in df.columns and "route_id" in routes.columns:
        df = df.merge(routes, on="route_id", how="left", suffixes=("", "_route"))
        notes.append("joined routes on route_id")
    else:
        notes.append("skipped routes join (missing routes or route_id)")

    artifact = _write_df(df, "enriched_vehicle_view", "Realtime vehicle positions enriched with static trips/routes")
    return EnrichedVehiclesOutput(artifact=artifact, join_notes="; ".join(notes))


def fetch_realtime() -> FetchRealtimeOutput:
    """Fetch a new realtime GTFS-RT snapshot into the configured realtime directory."""
    try:
        rc = fetch_realtime_main()
        if rc != 0:
            return FetchRealtimeOutput(ok=False, snapshot_dir=None, message=f"Realtime fetch failed with exit code {rc}.")
        # Determine latest snapshot dir via repository paths
        from src.sources.repository import TransitRepository
        repo = TransitRepository.from_paths_yaml("src/config/paths.yaml")
        snap_dir = repo.latest_snapshot_dir()
        if not snap_dir:
            return FetchRealtimeOutput(ok=False, snapshot_dir=None, message="Realtime fetch completed but no snapshot directory was found.")
        return FetchRealtimeOutput(ok=True, snapshot_dir=str(snap_dir), message="Realtime snapshot fetched.")
    except Exception as e:
        return FetchRealtimeOutput(ok=False, snapshot_dir=None, message=f"Realtime fetch failed: {e!r}")
