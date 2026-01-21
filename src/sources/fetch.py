from src.sources.gtfs_static.fetch import main as fetch_static_main
from src.sources.gtfs_realtime.fetch import main as fetch_realtime_main

def fetch_static() -> None:
    rc = fetch_static_main()
    if rc != 0:
        raise RuntimeError(f"Static fetch failed (exit code {rc})")

def fetch_realtime() -> None:
    rc = fetch_realtime_main()
    if rc != 0:
        raise RuntimeError(f"Realtime fetch failed (exit code {rc})")

def fetch_all() -> None:
    fetch_static()
    fetch_realtime()
