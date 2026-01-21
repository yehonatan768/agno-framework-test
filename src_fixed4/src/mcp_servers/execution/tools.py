from __future__ import annotations

import math
import os
import logging
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
    ActiveRoutesOutput,
    ActiveRoute,
)

# Expected to exist in your repo:
#   - src/sources/repository.py (TransitRepository)
#   - src/utils/yaml.py (load_yaml + resolve_path support)
from src.sources.repository import TransitRepository
from src.utils.yaml import load_yaml
from src.sources.gtfs_realtime.fetch import main as fetch_realtime_main


logger = logging.getLogger(__name__)


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


def _ensure_snapshot_dir(repo: TransitRepository, snapshot_dir: Optional[str | Path] = None) -> Path:
    """Resolve a snapshot directory in a deterministic way.

    Precedence:
      1) explicit snapshot_dir argument
      2) TRANSIT_SNAPSHOT_DIR environment variable (set by the CLI/orchestrator per user question)
      3) repository.latest_snapshot_dir()
    """

    if snapshot_dir:
        p = Path(snapshot_dir)
        if not p.exists():
            raise FileNotFoundError(f"Snapshot dir does not exist: {p}")
        return p

    env_dir = (os.getenv("TRANSIT_SNAPSHOT_DIR") or "").strip()
    if env_dir:
        p = Path(env_dir)
        if not p.exists():
            raise FileNotFoundError(f"TRANSIT_SNAPSHOT_DIR points to missing path: {p}")
        return p

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
    snap_dir = _ensure_snapshot_dir(repo)
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
    snap_dir = _ensure_snapshot_dir(repo)
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
    snap_dir = _ensure_snapshot_dir(repo)
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
    snap_dir = _ensure_snapshot_dir(repo)
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
    snap_dir = _ensure_snapshot_dir(repo)
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
    snap_dir = _ensure_snapshot_dir(repo)
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


def active_routes_with_vehicles() -> ActiveRoutesOutput:
    """Return routes that currently have at least one active vehicle, enriched with static route names.

    This is the canonical answer-tool for questions like:
      - "Which routes currently have active vehicles and what are their names?"

    Notes:
    - Realtime source: latest snapshot's vehicle_positions table (route_id, vehicle_id).
    - Static enrichment: static routes table (route_id -> route_short_name/route_long_name).
    """

    repo = TransitRepository.from_paths_yaml("src/config/paths.yaml")
    snap_dir = _ensure_snapshot_dir(repo)
    frames = repo.load_realtime_snapshot(snap_dir)

    vp = frames.vehicle_positions
    if vp.empty:
        return ActiveRoutesOutput(feed_timestamp=getattr(frames, "feed_timestamp", None), routes=[])

    # We try hard not to fail when fields are missing.
    # route_id can be absent in VehiclePosition; when present, trip_id often exists and can be resolved via static trips.

    df = vp.copy()

    # Fall back for missing vehicle_id
    if "vehicle_id" not in df.columns:
        df["vehicle_id"] = None
    if "entity_id" in df.columns:
        df["vehicle_id"] = df["vehicle_id"].fillna(df["entity_id"])  # fallback

    # Load static routes/trips for enrichment + route_id recovery (if available)
    from src.sources.gtfs_static.tables import load_static_tables_from_yaml
    static = load_static_tables_from_yaml("src/config/providers.yaml", "provider.static")

    # Fall back for missing route_id via trips join
    if "route_id" not in df.columns:
        df["route_id"] = None
    if "trip_id" in df.columns and df["route_id"].isna().any():
        trips_df = static.tables.get("trips", pd.DataFrame()).copy()
        if not trips_df.empty and {"trip_id", "route_id"}.issubset(trips_df.columns):
            trips_df = trips_df[["trip_id", "route_id"]].dropna(subset=["trip_id", "route_id"]).copy()
            trips_df["trip_id"] = trips_df["trip_id"].astype(str)
            trips_df["route_id"] = trips_df["route_id"].astype(str)
            df["trip_id"] = df["trip_id"].astype(str)
            df = df.merge(trips_df, on="trip_id", how="left", suffixes=("", "_from_trips"))
            df["route_id"] = df["route_id"].fillna(df.get("route_id_from_trips"))
            if "route_id_from_trips" in df.columns:
                df = df.drop(columns=["route_id_from_trips"])

    # Aggregate realtime by route_id.
    # We keep both IDs and (if available) human-friendly labels/plates.
    df = df.dropna(subset=["route_id"]).copy()
    df["route_id"] = df["route_id"].astype(str)
    if "vehicle_id" in df.columns:
        df["vehicle_id"] = df["vehicle_id"].astype(str)
        df.loc[df["vehicle_id"].isin(["nan", "None"]), "vehicle_id"] = None

    # Optional vehicle fields from SnapshotLoader
    for c in ["vehicle_label", "vehicle_license_plate"]:
        if c not in df.columns:
            df[c] = None

    routes_df = static.tables.get("routes", pd.DataFrame()).copy()
    routes_map: Dict[str, dict] = {}
    if not routes_df.empty and "route_id" in routes_df.columns:
        # Keep only columns that are commonly present
        keep_cols = [c for c in ["route_id", "route_short_name", "route_long_name"] if c in routes_df.columns]
        routes_df = routes_df[keep_cols].dropna(subset=["route_id"]).copy()
        routes_df["route_id"] = routes_df["route_id"].astype(str)
        for _, r in routes_df.iterrows():
            routes_map[str(r["route_id"])] = {
                "route_short_name": str(r.get("route_short_name")) if pd.notna(r.get("route_short_name")) else None,
                "route_long_name": str(r.get("route_long_name")) if pd.notna(r.get("route_long_name")) else None,
            }

    out: List[ActiveRoute] = []
    for rid, sub in df.groupby("route_id"):
        # Deduplicate vehicles by (vehicle_id, vehicle_label, vehicle_license_plate)
        vehicles = []
        seen = set()
        for _, r in sub.iterrows():
            vid = r.get("vehicle_id")
            # If vehicle_id is missing, fall back to entity_id (already done above), but keep None-safe
            vid = None if pd.isna(vid) else str(vid)
            vlabel = r.get("vehicle_label")
            vlabel = None if pd.isna(vlabel) else str(vlabel)
            vplate = r.get("vehicle_license_plate")
            vplate = None if pd.isna(vplate) else str(vplate)

            key = (vid, vlabel, vplate)
            if key in seen:
                continue
            seen.add(key)
            if vid is None and vlabel is None and vplate is None:
                continue
            vehicles.append(ActiveRoute.VehicleRef(vehicle_id=vid, vehicle_label=vlabel, vehicle_license_plate=vplate))

        # Backward-compatible vehicle_ids (prefer id, else label, else plate)
        vehicle_ids: List[str] = []
        for v in vehicles:
            if v.vehicle_id:
                vehicle_ids.append(v.vehicle_id)
        vehicle_ids = sorted(set(vehicle_ids))

        meta = routes_map.get(str(rid), {})
        out.append(
            ActiveRoute(
                route_id=str(rid),
                route_short_name=meta.get("route_short_name"),
                route_long_name=meta.get("route_long_name"),
                vehicles=vehicles,
                vehicle_ids=vehicle_ids,
                vehicles_active=len(vehicles) if vehicles else len(vehicle_ids),
            )
        )

    # Stable ordering: most vehicles first, then route_id
    out.sort(key=lambda r: (-r.vehicles_active, r.route_id))
    res = ActiveRoutesOutput(feed_timestamp=getattr(frames, "feed_timestamp", None), routes=out)

    # Pre-render a human-friendly markdown view. This is intended for direct display
    # so the LLM can simply output it verbatim.
    def _route_title(r: ActiveRoute) -> str:
        name = r.route_long_name or r.route_short_name
        if name and name.strip():
            return f"{name} (route id: {r.route_id})"
        return f"route id: {r.route_id}"

    def _vehicle_line(v: ActiveRoute.VehicleRef) -> str:
        if v.vehicle_label and v.vehicle_id:
            return f"{v.vehicle_label} (vehicle id: {v.vehicle_id})"
        if v.vehicle_label:
            return f"{v.vehicle_label} (vehicle label)"
        if v.vehicle_id:
            return f"vehicle id: {v.vehicle_id}"
        if v.vehicle_license_plate:
            return f"vehicle plate: {v.vehicle_license_plate}"
        return "vehicle (unknown)"

    lines: List[str] = []
    ft = getattr(frames, "feed_timestamp", None)
    lines.append(f"Active routes with vehicles (feed_timestamp: {ft})")
    lines.append("")
    if not out:
        lines.append("No active routes were found in the current snapshot.")
    else:
        # Avoid overwhelming terminal output; show all up to a high but finite limit.
        max_routes = 100
        shown = 0
        for r in out:
            shown += 1
            if shown > max_routes:
                break
            lines.append(f"- **{_route_title(r)}** — {r.vehicles_active} active vehicle(s)")
            # Prefer rich vehicle objects if present; otherwise fall back to IDs
            if r.vehicles:
                for v in sorted(r.vehicles, key=lambda x: (x.vehicle_label or "", x.vehicle_id or "", x.vehicle_license_plate or "")):
                    # Only print non-empty fields; the formatter already labels IDs.
                    lines.append(f"  - {_vehicle_line(v)}")
            elif r.vehicle_ids:
                for vid in r.vehicle_ids:
                    lines.append(f"  - vehicle id: {vid}")
            else:
                lines.append("  - (no vehicle identifiers available)")
        if len(out) > max_routes:
            lines.append("")
            lines.append(f"(Output truncated: showing {max_routes} routes out of {len(out)}.)")

    res.human_readable = "\n".join(lines)

    # Log a JSON-compatible view (including nulls) to support debugging of missing fields.
    try:
        payload = res.model_dump(exclude_none=False)
        payload["snapshot_dir"] = str(snap_dir)
        if isinstance(payload.get("routes"), list) and len(payload["routes"]) > 50:
            payload["routes"] = payload["routes"][:50] + [{"_truncated": True, "shown": 50, "total": len(out)}]
        logger.info("active_routes_with_vehicles | result=%s", payload)
    except Exception:
        logger.info("active_routes_with_vehicles | routes=%d | feed_timestamp=%s", len(out), getattr(frames, "feed_timestamp", None))

    return res


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
