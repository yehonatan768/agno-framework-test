from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import requests

from src.utils.config_loader import load_config, build_auth_headers_and_params


def snapshot_timestamp() -> str:
    # Folder name: UTC timestamp
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fetch_to_path(
    url: str,
    out_path: Path,
    headers: dict,
    params: dict,
    timeout_s: int,
    verify_tls: bool,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, headers=headers, params=params, stream=True, timeout=timeout_s, verify=verify_tls) as r:
        r.raise_for_status()
        with out_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def main() -> int:
    cfg = load_config()

    rt_type = cfg.get("provider.realtime.type")
    if rt_type != "gtfs_realtime":
        raise ValueError(f"Unsupported provider.realtime.type: {rt_type}")

    endpoints = cfg.get("provider.realtime.endpoints", [])
    if not endpoints:
        raise RuntimeError("No provider.realtime.endpoints configured")

    timeout_s = int(cfg.get("provider.realtime.timeout_s", 60))
    verify_tls = bool(cfg.get("provider.realtime.verify_tls", True))

    # Auth (universal)
    headers, params = build_auth_headers_and_params(cfg, "provider.realtime.auth")

    base_out_dir = cfg.resolve_path(cfg.get("provider.realtime.out_dir", "data/realtime"))
    ts = snapshot_timestamp()
    snapshot_dir = base_out_dir / ts
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for ep in endpoints:
        name = ep.get("name", "endpoint")
        url = ep.get("url")
        fmt = (ep.get("format", "protobuf") or "protobuf").lower()
        filename = ep.get("filename")

        if not url:
            raise RuntimeError(f"Endpoint '{name}' missing url")

        if not filename:
            ext = "pb" if fmt == "protobuf" else "json"
            filename = f"{name}.{ext}"

        out_path = snapshot_dir / filename

        fetch_to_path(
            url=url,
            out_path=out_path,
            headers=headers,
            params=params,
            timeout_s=timeout_s,
            verify_tls=verify_tls,
        )

        print(f"[OK] Snapshot '{ts}' | '{name}' saved: {out_path}")

    print(f"[OK] Snapshot folder created: {snapshot_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
