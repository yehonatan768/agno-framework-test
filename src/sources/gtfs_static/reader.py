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
    stem = name[:-4] if name.lower().endswith(".txt") else Path(name).stem
    return stem.strip().lower()


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

    for fn in files:
        key = _table_key_from_filename(str(fn))
        tables[key] = read_gtfs_table(d, str(fn))

    return StaticReadResult(static_dir=d, tables=tables)
