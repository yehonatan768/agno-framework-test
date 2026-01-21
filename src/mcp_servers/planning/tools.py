from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .schemas import (
    ArtifactRef,
    TableInfo,
    ListStaticTablesOutput,
    DescribeTableOutput,
    AgenciesOutput,
    RoutesOutput,
    StopsOutput,
    StopsBBoxOutput,
    BBox,
    RouteTripCountsOutput,
    TripStopSequenceOutput,
    RouteStopsOutput,
    StopRoutesOutput,
    IntegrityReportOutput,
    DataQualityReportOutput,
)

from src.utils.yaml import load_yaml
from src.sources.gtfs_static.fetch import main as fetch_static_main
from src.sources.gtfs_static.reader import read_static_dir_from_yaml


def _artifact_dir() -> Path:
    cfg = load_yaml("src/config/paths.yaml")
    out = cfg.get("paths.artifacts.planning_dir", "dataset/artifacts/planning")
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


def _load_static_tables() -> tuple[Path, Dict[str, pd.DataFrame], List[str]]:
    """Loads static GTFS tables dynamically using providers.yaml list."""
    from src.sources.gtfs_static.reader import read_static_dir_from_yaml

    res = read_static_dir_from_yaml("src/config/providers.yaml", "provider.static")
    cfg = load_yaml("src/config/providers.yaml")
    files = cfg.get("provider.static.extract.files", []) or []
    return Path(res.static_dir), dict(res.tables), [str(f) for f in files]


def list_static_tables() -> ListStaticTablesOutput:
    static_dir, tables, files = _load_static_tables()
    stem_to_file = {}
    for f in files:
        stem = Path(f).name
        stem = stem[:-4] if stem.lower().endswith(".txt") else Path(stem).stem
        stem_to_file[stem.lower()] = f

    infos: List[TableInfo] = []
    for name, df in tables.items():
        infos.append(
            TableInfo(
                name=str(name),
                filename=stem_to_file.get(str(name).lower()),
                rows=int(len(df)),
                columns=[str(c) for c in df.columns],
            )
        )
    infos.sort(key=lambda x: x.name)
    return ListStaticTablesOutput(static_dir=str(static_dir), tables=infos)


def describe_table(table: str, max_unique: int = 20, sample_rows: int = 5) -> DescribeTableOutput:
    _, tables, _ = _load_static_tables()
    if table not in tables:
        raise KeyError(f"Unknown static table: {table}. Available: {sorted(tables.keys())}")

    df = tables[table]
    columns = []
    for c in df.columns:
        s = df[c]
        summary = {
            "column": str(c),
            "dtype": str(s.dtype),
            "non_null": int(s.notna().sum()),
            "nulls": int(s.isna().sum()),
        }
        if max_unique > 0:
            try:
                summary["unique"] = int(s.nunique(dropna=True))
                summary["examples"] = s.dropna().astype(str).unique().tolist()[:max_unique]
            except Exception:
                pass
        columns.append(summary)

    preview = []
    if sample_rows > 0 and not df.empty:
        preview = df.head(sample_rows).fillna("").to_dict(orient="records")

    return DescribeTableOutput(table=table, rows=int(len(df)), columns=columns, preview=preview)


def list_agencies() -> AgenciesOutput:
    _, tables, _ = _load_static_tables()
    agency = tables.get("agency", pd.DataFrame())
    if agency.empty:
        return AgenciesOutput(agencies=[])

    cols = [c for c in ["agency_id", "agency_name", "agency_url", "agency_timezone"] if c in agency.columns]
    out = agency[cols].fillna("").to_dict(orient="records") if cols else agency.fillna("").to_dict(orient="records")
    return AgenciesOutput(agencies=out)


def export_routes() -> RoutesOutput:
    _, tables, _ = _load_static_tables()
    df = tables.get("routes", pd.DataFrame())
    return RoutesOutput(routes=_write_df(df, "routes", "Static GTFS routes table"))


def export_stops() -> StopsOutput:
    _, tables, _ = _load_static_tables()
    df = tables.get("stops", pd.DataFrame())
    return StopsOutput(stops=_write_df(df, "stops", "Static GTFS stops table"))


def stops_bbox() -> StopsBBoxOutput:
    _, tables, _ = _load_static_tables()
    stops = tables.get("stops", pd.DataFrame())
    if stops.empty or not set(["stop_lat", "stop_lon"]).issubset(stops.columns):
        return StopsBBoxOutput(bbox=None, missing_coords=int(len(stops)) if not stops.empty else 0)

    lat = pd.to_numeric(stops["stop_lat"], errors="coerce")
    lon = pd.to_numeric(stops["stop_lon"], errors="coerce")
    missing = int((lat.isna() | lon.isna()).sum())
    valid_lat = lat.dropna()
    valid_lon = lon.dropna()
    if valid_lat.empty or valid_lon.empty:
        return StopsBBoxOutput(bbox=None, missing_coords=missing)

    bbox = BBox(
        min_lat=float(valid_lat.min()),
        max_lat=float(valid_lat.max()),
        min_lon=float(valid_lon.min()),
        max_lon=float(valid_lon.max()),
    )
    return StopsBBoxOutput(bbox=bbox, missing_coords=missing)


def route_trip_counts(top_n: Optional[int] = None) -> RouteTripCountsOutput:
    _, tables, _ = _load_static_tables()
    trips = tables.get("trips", pd.DataFrame())
    if trips.empty or "route_id" not in trips.columns:
        df = pd.DataFrame(columns=["route_id", "trip_count"])
        return RouteTripCountsOutput(counts=_write_df(df, "route_trip_counts", "Trips per route_id"))

    df = trips.groupby("route_id", dropna=False).size().reset_index(name="trip_count")
    df["route_id"] = df["route_id"].astype(str)
    df = df.sort_values("trip_count", ascending=False)
    if top_n is not None:
        df = df.head(int(top_n))
    return RouteTripCountsOutput(counts=_write_df(df, "route_trip_counts", "Trips per route_id"))


def trip_stop_sequence(trip_id: str) -> TripStopSequenceOutput:
    _, tables, _ = _load_static_tables()
    st = tables.get("stop_times", pd.DataFrame())
    if st.empty or "trip_id" not in st.columns:
        raise ValueError("stop_times table missing or has no trip_id column")

    df = st[st["trip_id"].astype(str) == str(trip_id)].copy()
    if df.empty:
        raise KeyError(f"trip_id not found in stop_times: {trip_id}")

    if "stop_sequence" in df.columns:
        df["stop_sequence"] = pd.to_numeric(df["stop_sequence"], errors="coerce")
        df = df.sort_values("stop_sequence")

    keep = [c for c in ["trip_id", "stop_sequence", "stop_id", "arrival_time", "departure_time"] if c in df.columns]
    df = df[keep] if keep else df
    return TripStopSequenceOutput(trip_id=str(trip_id), stop_sequence=_write_df(df, f"trip_{trip_id}_stop_sequence", "Stop sequence for trip"))


def route_stops(route_id: str) -> RouteStopsOutput:
    """Stops served by a route based on stop_times + trips (static)."""
    _, tables, _ = _load_static_tables()
    trips = tables.get("trips", pd.DataFrame())
    st = tables.get("stop_times", pd.DataFrame())
    if trips.empty or st.empty:
        df = pd.DataFrame(columns=["stop_id"])
        return RouteStopsOutput(route_id=str(route_id), stops=_write_df(df, f"route_{route_id}_stops", "Stops for route"))

    if "route_id" not in trips.columns or "trip_id" not in trips.columns or "trip_id" not in st.columns:
        raise ValueError("Required columns missing for route->stops mapping")

    trip_ids = trips[trips["route_id"].astype(str) == str(route_id)]["trip_id"].dropna().astype(str).unique().tolist()
    df = st[st["trip_id"].astype(str).isin(trip_ids)][["stop_id"]].dropna().drop_duplicates()
    return RouteStopsOutput(route_id=str(route_id), stops=_write_df(df, f"route_{route_id}_stops", "Stops served by route (static)"))


def stop_routes(stop_id: str) -> StopRoutesOutput:
    """Routes serving a stop based on stop_times + trips (static)."""
    _, tables, _ = _load_static_tables()
    trips = tables.get("trips", pd.DataFrame())
    st = tables.get("stop_times", pd.DataFrame())
    if trips.empty or st.empty:
        df = pd.DataFrame(columns=["route_id"])
        return StopRoutesOutput(stop_id=str(stop_id), routes=_write_df(df, f"stop_{stop_id}_routes", "Routes for stop"))

    if "trip_id" not in trips.columns or "trip_id" not in st.columns or "route_id" not in trips.columns:
        raise ValueError("Required columns missing for stop->routes mapping")

    trip_ids = st[st["stop_id"].astype(str) == str(stop_id)]["trip_id"].dropna().astype(str).unique().tolist()
    df = trips[trips["trip_id"].astype(str).isin(trip_ids)][["route_id"]].dropna().drop_duplicates()
    return StopRoutesOutput(stop_id=str(stop_id), routes=_write_df(df, f"stop_{stop_id}_routes", "Routes serving stop (static)"))


def integrity_report() -> IntegrityReportOutput:
    """Basic static referential integrity checks."""
    _, tables, _ = _load_static_tables()
    trips = tables.get("trips", pd.DataFrame())
    routes = tables.get("routes", pd.DataFrame())
    st = tables.get("stop_times", pd.DataFrame())

    details: Dict[str, ArtifactRef] = {}

    missing_route_refs = 0
    if not trips.empty and not routes.empty and "route_id" in trips.columns and "route_id" in routes.columns:
        bad = trips[~trips["route_id"].astype(str).isin(routes["route_id"].dropna().astype(str).unique())].copy()
        missing_route_refs = int(len(bad))
        if not bad.empty:
            details["trips_with_missing_route"] = _write_df(bad[["trip_id", "route_id"]].dropna(), "trips_missing_routes", "Trips referencing missing routes")

    missing_trip_refs = 0
    if not st.empty and not trips.empty and "trip_id" in st.columns and "trip_id" in trips.columns:
        bad = st[~st["trip_id"].astype(str).isin(trips["trip_id"].dropna().astype(str).unique())].copy()
        missing_trip_refs = int(len(bad))
        if not bad.empty:
            keep = [c for c in ["trip_id", "stop_id", "stop_sequence"] if c in bad.columns]
            details["stop_times_with_missing_trip"] = _write_df(bad[keep], "stop_times_missing_trips", "Stop times referencing missing trips")

    return IntegrityReportOutput(
        missing_route_refs_in_trips=missing_route_refs,
        missing_trip_refs_in_stop_times=missing_trip_refs,
        details=details or None,
    )


def data_quality_report() -> DataQualityReportOutput:
    """A concise static-only quality report aligned with planning questions."""
    static_dir, tables, _ = _load_static_tables()
    artifacts: Dict[str, ArtifactRef] = {}

    stops = tables.get("stops", pd.DataFrame())
    missing_coords = 0
    if not stops.empty and set(["stop_lat", "stop_lon"]).issubset(stops.columns):
        lat = pd.to_numeric(stops["stop_lat"], errors="coerce")
        lon = pd.to_numeric(stops["stop_lon"], errors="coerce")
        bad = stops[lat.isna() | lon.isna()].copy()
        missing_coords = int(len(bad))
        if not bad.empty:
            keep = [c for c in ["stop_id", "stop_name", "stop_lat", "stop_lon"] if c in bad.columns]
            artifacts["stops_missing_coords"] = _write_df(bad[keep], "stops_missing_coords", "Stops with missing/invalid coordinates")

    integ = integrity_report()
    if integ.details:
        artifacts.update(integ.details)

    summary = {
        "static_dir": str(static_dir),
        "tables_loaded": sorted(list(tables.keys())),
        "stops_missing_coords": missing_coords,
        "missing_route_refs_in_trips": integ.missing_route_refs_in_trips,
        "missing_trip_refs_in_stop_times": integ.missing_trip_refs_in_stop_times,
    }
    return DataQualityReportOutput(summary=summary, artifacts=artifacts)
