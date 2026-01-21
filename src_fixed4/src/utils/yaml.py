from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


def project_root() -> Path:
    """
    Resolves project root assuming this file lives at: <root>/src/utils/yaml.py
    """
    return Path(__file__).resolve().parents[2]


def deep_get(d: Dict[str, Any], keys: str, default: Any = None) -> Any:
    cur: Any = d
    for k in keys.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def resolve_env_placeholders(value: Any) -> Any:
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
        return {k: resolve_env_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_env_placeholders(v) for v in value]
    return value


@dataclass(frozen=True)
class YamlConfig:
    raw: Dict[str, Any]
    root: Path

    def get(self, path: str, default: Any = None) -> Any:
        return deep_get(self.raw, path, default)

    def resolve_path(self, p: str | Path) -> Path:
        p = Path(p)
        return p if p.is_absolute() else (self.root / p)


def load_yaml(path: str | Path) -> YamlConfig:
    root = project_root()
    p = Path(path)
    cfg_path = p if p.is_absolute() else (root / p)

    if not cfg_path.exists():
        raise FileNotFoundError(f"YAML not found: {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    raw = resolve_env_placeholders(raw)
    return YamlConfig(raw=raw, root=root)


def build_auth_headers_and_params(cfg: YamlConfig, auth_path: str) -> tuple[dict[str, str], dict[str, str]]:
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

    headers: dict[str, str] = {}
    params: dict[str, str] = {}

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
