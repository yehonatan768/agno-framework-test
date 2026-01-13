from __future__ import annotations

from pathlib import Path
from typing import Optional

from google.transit import gtfs_realtime_pb2


def parse_feed(pb_path: str | Path) -> gtfs_realtime_pb2.FeedMessage:
    p = Path(pb_path)
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(p.read_bytes())
    return feed


def feed_timestamp(feed: gtfs_realtime_pb2.FeedMessage) -> Optional[int]:
    try:
        ts = int(feed.header.timestamp)
        return ts if ts > 0 else None
    except Exception:
        return None
