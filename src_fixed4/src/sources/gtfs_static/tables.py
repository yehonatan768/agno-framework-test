from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Mapping, MutableMapping, Optional

import pandas as pd

from .reader import read_static_dir_from_yaml


@dataclass(frozen=True)
class StaticTables:
    static_dir: Path
    tables: Dict[str, pd.DataFrame]

    def __getitem__(self, key: str) -> pd.DataFrame:
        return self.tables[key]

    def get(self, key: str, default: Optional[pd.DataFrame] = None) -> Optional[pd.DataFrame]:
        return self.tables.get(key, default)

    def keys(self):
        return self.tables.keys()

    def items(self):
        return self.tables.items()


def load_static_tables_from_yaml(
    providers_yaml: str | Path = "src/config/providers.yaml",
    provider_path: str = "provider.static",
) -> StaticTables:
    res = read_static_dir_from_yaml(providers_yaml=providers_yaml, provider_path=provider_path)
    return StaticTables(static_dir=res.static_dir, tables=res.tables)
