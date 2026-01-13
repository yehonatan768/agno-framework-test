from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.utils.yaml import load_yaml

from .gtfs_static.tables import StaticTables, load_static_tables_from_yaml
from .gtfs_realtime.snapshot_loader import SnapshotLoader, SnapshotFrames


@dataclass(frozen=True)
class RepoPaths:
    static_dir: Path
    realtime_dir: Path


class TransitRepository:
    def __init__(self, paths: RepoPaths) -> None:
        self.paths = paths

    @classmethod
    def from_paths_yaml(cls, paths_yaml: str | Path = "src/config/paths.yaml") -> "TransitRepository":
        cfg = load_yaml(paths_yaml)
        static_dir = cfg.resolve_path(cfg.get("paths.dataset.static_dir", "dataset/static"))
        realtime_dir = cfg.resolve_path(cfg.get("paths.dataset.realtime_dir", "dataset/realtime"))
        return cls(RepoPaths(static_dir=static_dir, realtime_dir=realtime_dir))

    @staticmethod
    def load_static() -> StaticTables:
        return load_static_tables_from_yaml("src/config/providers.yaml", "provider.static")

    def load_realtime_snapshot(self, snapshot_dir: str | Path) -> SnapshotFrames:
        loader = SnapshotLoader()
        return loader.load_snapshot_dir(snapshot_dir)

    def latest_snapshot_dir(self) -> Optional[Path]:
        d = self.paths.realtime_dir
        if not d.exists():
            return None
        candidates = [p for p in d.iterdir() if p.is_dir()]
        if not candidates:
            return None
        return sorted(candidates)[-1]
