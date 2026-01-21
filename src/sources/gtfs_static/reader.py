from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

from src.utils.yaml import load_yaml, YamlConfig


@dataclass(frozen=True)
class StaticReadResult:
    static_dir: Path
    tables: Dict[str, pd.DataFrame]


def _table_key_from_filename(filename: str) -> str:
    """
    agency.txt -> agency
    stop_times.txt -> stop_times
    """
    name = Path(filename).name
    return Path(name).stem.strip().lower()


def _resolve_table_filename(static_dir: Path, entry: str) -> str:
    """Resolve a config entry to an on-disk filename.

    providers.yaml is allowed to list either:
      - an exact filename ("stops.txt", "stops.csv", ...)
      - or a stem ("stops") in which case we select the matching file
        regardless of extension.
    """
    entry = (entry or "").strip()
    if not entry:
        return entry

    # Exact filename specified.
    if "." in Path(entry).name:
        return Path(entry).name

    stem = Path(entry).stem
    candidates = [p for p in static_dir.iterdir() if p.is_file() and p.stem == stem]
    if not candidates:
        raise FileNotFoundError(
            f"Static table '{stem}' not found in {static_dir}. "
            f"Expected a file named '{stem}.*'."
        )

    # Deterministic selection: prefer common GTFS extensions first.
    ext_priority = {".txt": 0, ".csv": 1}
    candidates.sort(key=lambda p: (ext_priority.get(p.suffix.lower(), 9), p.suffix.lower(), p.name.lower()))
    return candidates[0].name


def read_gtfs_table(static_dir: str | Path, filename: str, **read_csv_kwargs) -> pd.DataFrame:
    p = Path(static_dir) / filename
    if not p.exists():
        return pd.DataFrame()
    # GTFS often contains empty strings and mixed types; low_memory=False avoids dtype fragmentation warnings.
    return pd.read_csv(p, low_memory=False, **read_csv_kwargs)


def read_static_dir_from_yaml(
    providers_yaml: str | Path = "src/config/providers.yaml",
    provider_path: str = "provider.static",
) -> StaticReadResult:
    """
    Loads static GTFS tables dynamically based on the list of files in providers.yaml:
      - <provider_path>.out_dir
      - <provider_path>.extract.files

    Returns:
      tables: Dict[table_name, DataFrame]
    """
    cfg = load_yaml(providers_yaml)

    static_dir = cfg.resolve_path(cfg.get(f"{provider_path}.out_dir", "dataset/static"))
    files: Iterable[str] = cfg.get(f"{provider_path}.extract.files", []) or []

    d = Path(static_dir)
    tables: Dict[str, pd.DataFrame] = {}

    for entry in files:
        resolved = _resolve_table_filename(d, str(entry))
        key = _table_key_from_filename(resolved)
        tables[key] = read_gtfs_table(d, resolved)

    return StaticReadResult(static_dir=d, tables=tables)
