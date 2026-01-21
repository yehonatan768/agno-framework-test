from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, List

import pandas as pd
from google.transit import gtfs_realtime_pb2

from .pb_reader import parse_feed, feed_timestamp


@dataclass(frozen=True)
class SnapshotFrames:
    snapshot_dir: Path
    feed_timestamp: Optional[int]
    vehicle_positions: pd.DataFrame
    trip_updates: pd.DataFrame
    trip_update_stop_times: pd.DataFrame
    alerts: pd.DataFrame


class SnapshotLoader:
    def __init__(
        self,
        vehicle_positions_filename: str = "vehicle_positions.pb",
        trip_updates_filename: str = "trip_updates.pb",
        alerts_filename: str = "alerts.pb",
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.vehicle_positions_filename = vehicle_positions_filename
        self.trip_updates_filename = trip_updates_filename
        self.alerts_filename = alerts_filename
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _vehicle_positions_df(feed: gtfs_realtime_pb2.FeedMessage, feed_ts: Optional[int]) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        for e in feed.entity:
            if not e.HasField("vehicle"):
                continue
            v = e.vehicle
            # VehicleDescriptor commonly contains id, label (a human-friendly identifier),
            # and license_plate. We capture these so downstream tools can render nicer output.
            veh_id = None
            veh_label = None
            veh_plate = None
            if v.HasField("vehicle"):
                veh_id = v.vehicle.id if v.vehicle.id else None
                veh_label = v.vehicle.label if v.vehicle.label else None
                veh_plate = v.vehicle.license_plate if v.vehicle.license_plate else None
            row: Dict[str, Any] = {
                "feed_timestamp": feed_ts,
                "entity_id": e.id or None,
                "vehicle_id": veh_id,
                "vehicle_label": veh_label,
                "vehicle_license_plate": veh_plate,
                "trip_id": v.trip.trip_id if v.HasField("trip") and v.trip.trip_id else None,
                "route_id": v.trip.route_id if v.HasField("trip") and v.trip.route_id else None,
                "direction_id": int(v.trip.direction_id) if v.HasField("trip") and v.trip.HasField("direction_id") else None,
                "stop_id": v.stop_id if v.HasField("stop_id") and v.stop_id else None,
                "vehicle_timestamp": int(v.timestamp) if v.HasField("timestamp") else None,
                "current_status": int(v.current_status) if v.HasField("current_status") else None,
                "current_stop_sequence": int(v.current_stop_sequence) if v.HasField("current_stop_sequence") else None,
            }
            if v.HasField("position"):
                row.update(
                    {
                        "lat": float(v.position.latitude),
                        "lon": float(v.position.longitude),
                        "bearing": float(v.position.bearing) if v.position.HasField("bearing") else None,
                        "speed": float(v.position.speed) if v.position.HasField("speed") else None,
                    }
                )
            else:
                row.update({"lat": None, "lon": None, "bearing": None, "speed": None})

            rows.append(row)
        return pd.DataFrame(rows)

    @staticmethod
    def _trip_updates_df(feed: gtfs_realtime_pb2.FeedMessage, feed_ts: Optional[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
        trip_rows: List[Dict[str, Any]] = []
        stu_rows: List[Dict[str, Any]] = []

        for e in feed.entity:
            if not e.HasField("trip_update"):
                continue

            tu = e.trip_update
            trip_row: Dict[str, Any] = {
                "feed_timestamp": feed_ts,
                "entity_id": e.id or None,
                "trip_id": tu.trip.trip_id if tu.trip.trip_id else None,
                "route_id": tu.trip.route_id if tu.trip.route_id else None,
                "direction_id": int(tu.trip.direction_id) if tu.trip.HasField("direction_id") else None,
                "timestamp": int(tu.timestamp) if tu.HasField("timestamp") else None,
                "delay": int(tu.delay) if tu.HasField("delay") else None,
                "vehicle_id": tu.vehicle.id if tu.HasField("vehicle") and tu.vehicle.id else None,
            }
            trip_rows.append(trip_row)

            for stu in tu.stop_time_update:
                stu_rows.append(
                    {
                        "feed_timestamp": feed_ts,
                        "entity_id": e.id or None,
                        "trip_id": trip_row["trip_id"],
                        "route_id": trip_row["route_id"],
                        "stop_sequence": int(stu.stop_sequence) if stu.HasField("stop_sequence") else None,
                        "stop_id": stu.stop_id if stu.stop_id else None,
                        "arrival_time": int(stu.arrival.time) if stu.HasField("arrival") and stu.arrival.HasField("time") else None,
                        "arrival_delay": int(stu.arrival.delay) if stu.HasField("arrival") and stu.arrival.HasField("delay") else None,
                        "departure_time": int(stu.departure.time) if stu.HasField("departure") and stu.departure.HasField("time") else None,
                        "departure_delay": int(stu.departure.delay) if stu.HasField("departure") and stu.departure.HasField("delay") else None,
                    }
                )

        return pd.DataFrame(trip_rows), pd.DataFrame(stu_rows)

    @staticmethod
    def _alerts_df(feed: gtfs_realtime_pb2.FeedMessage, feed_ts: Optional[int]) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        for e in feed.entity:
            if not e.HasField("alert"):
                continue
            a = e.alert
            rows.append(
                {
                    "feed_timestamp": feed_ts,
                    "entity_id": e.id or None,
                    "cause": int(a.cause) if a.HasField("cause") else None,
                    "effect": int(a.effect) if a.HasField("effect") else None,
                    "header_text": a.header_text.translation[0].text if a.HasField("header_text") and a.header_text.translation else None,
                    "description_text": a.description_text.translation[0].text if a.HasField("description_text") and a.description_text.translation else None,
                }
            )
        return pd.DataFrame(rows)

    def load_snapshot_dir(self, snapshot_dir: str | Path) -> SnapshotFrames:
        snapshot_dir = Path(snapshot_dir)

        vp_path = snapshot_dir / self.vehicle_positions_filename
        tu_path = snapshot_dir / self.trip_updates_filename
        al_path = snapshot_dir / self.alerts_filename

        self.logger.info("Loading snapshot | dir=%s", snapshot_dir)

        feed_ts: Optional[int] = None

        if vp_path.exists():
            vp_feed = parse_feed(vp_path)
            feed_ts = feed_timestamp(vp_feed)
            vp_df = self._vehicle_positions_df(vp_feed, feed_ts)
            self.logger.info("Parsed VehiclePositions | path=%s | rows=%d | feed_ts=%s", vp_path, len(vp_df), feed_ts)
        else:
            self.logger.warning("Missing VehiclePositions file | expected=%s", vp_path)
            vp_df = pd.DataFrame()

        if tu_path.exists():
            tu_feed = parse_feed(tu_path)
            feed_ts = feed_ts or feed_timestamp(tu_feed)
            tu_df, stu_df = self._trip_updates_df(tu_feed, feed_ts)
            self.logger.info(
                "Parsed TripUpdates | path=%s | trips=%d | stop_time_updates=%d | feed_ts=%s",
                tu_path, len(tu_df), len(stu_df), feed_ts
            )
        else:
            self.logger.warning("Missing TripUpdates file | expected=%s", tu_path)

            tu_df = pd.DataFrame()
            stu_df = pd.DataFrame()

        if al_path.exists():
            al_feed = parse_feed(al_path)
            feed_ts = feed_ts or feed_timestamp(al_feed)
            al_df = self._alerts_df(al_feed, feed_ts)
            self.logger.info("Parsed Alerts | path=%s | rows=%d | feed_ts=%s", al_path, len(al_df), feed_ts)
        else:
            self.logger.warning("Missing Alerts file | expected=%s", al_path)
            al_df = pd.DataFrame()

        return SnapshotFrames(
            snapshot_dir=snapshot_dir,
            feed_timestamp=feed_ts,
            vehicle_positions=vp_df,
            trip_updates=tu_df,
            trip_update_stop_times=stu_df,
            alerts=al_df,
        )