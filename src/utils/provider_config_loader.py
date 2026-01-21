from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def _project_root() -> Path:
    """
    Resolves project root assuming this file lives at: <root>/src/utils/provider_config_loader.py
    """
    return Path(__file__).resolve().parents[2]


def _deep_get(d: Dict[str, Any], keys: str, default: Any = None) -> Any:
    cur: Any = d
    for k in keys.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _resolve_env_placeholders(value: Any) -> Any:
    """
    Simple env var substitution:
      "${ENV_VAR}" -> os.environ.get("ENV_VAR")
    Works recursively for dict/list/str.
    """
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            env_name = value[2:-1].strip()
            return os.environ.get(env_name)
        return value
    if isinstance(value, dict):
        return {k: _resolve_env_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_placeholders(v) for v in value]
    return value


@dataclass(frozen=True)
class ProviderConfig:
    raw: Dict[str, Any]
    root: Path

    def get(self, path: str, default: Any = None) -> Any:
        return _deep_get(self.raw, path, default)

    def resolve_path(self, p: str | Path) -> Path:
        p = Path(p)
        return p if p.is_absolute() else (self.root / p)


def load_config(config_path: str | Path = "src/config/providers.yaml") -> ProviderConfig:
    root = _project_root()
    cfg_path = root / config_path if not Path(config_path).is_absolute() else Path(config_path)

    if not cfg_path.exists():
        raise FileNotFoundError(f"Config not found: {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    raw = _resolve_env_placeholders(raw)
    return ProviderConfig(raw=raw, root=root)


def build_auth_headers_and_params(cfg: ProviderConfig, auth_path: str) -> tuple[Dict[str, str], Dict[str, str]]:
    """
    Builds (headers, params) based on:
      <auth_path>.mode in {none, header, query}
      <auth_path>.env_var
      <auth_path>.header_name
      <auth_path>.query_param
    """
    mode = (cfg.get(f"{auth_path}.mode", "none") or "none").lower()
    env_var = cfg.get(f"{auth_path}.env_var")
    api_key = os.environ.get(env_var) if env_var else None

    headers: Dict[str, str] = {}
    params: Dict[str, str] = {}

    if mode == "none":
        return headers, params

    if not api_key:
        raise RuntimeError(
            f"Auth mode is '{mode}' but no API key found. "
            f"Set env var '{env_var}' or change auth.mode to 'none'."
        )

    if mode == "header":
        header_name = cfg.get(f"{auth_path}.header_name", "x-api-key")
        headers[str(header_name)] = str(api_key)
        return headers, params

    if mode == "query":
        param = cfg.get(f"{auth_path}.query_param", "api_key")
        params[str(param)] = str(api_key)
        return headers, params

    raise ValueError(f"Unsupported auth mode: {mode}")