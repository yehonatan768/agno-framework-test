from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple

import requests

from src.utils.config_loader import load_config, build_auth_headers_and_params


logger = logging.getLogger(__name__)


def snapshot_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fetch_to_path(
    url: str,
    out_path: Path,
    headers: dict,
    params: dict,
    timeout_s: int,
    verify_tls: bool,
) -> Tuple[int, Optional[str]]:
    """
    Returns: (bytes_written, content_type)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, headers=headers, params=params, stream=True, timeout=timeout_s, verify=verify_tls) as r:
        r.raise_for_status()
        content_type = r.headers.get("Content-Type")
        total = 0

        with out_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)

    return total, content_type


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

    headers, params = build_auth_headers_and_params(cfg, "provider.realtime.auth")

    base_out_dir = cfg.resolve_path(cfg.get("provider.realtime.out_dir", "dataset/realtime"))
    ts = snapshot_timestamp()
    snapshot_dir = base_out_dir / ts
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Realtime snapshot started | ts=%s | out_dir=%s | endpoints=%d", ts, snapshot_dir, len(endpoints))
    if headers:
        logger.info("Auth enabled via headers (keys=%s)", list(headers.keys()))
    elif params:
        logger.info("Auth enabled via query params (keys=%s)", list(params.keys()))
    else:
        logger.info("Auth mode: none")

    ok = 0
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

        try:
            logger.info("Fetching endpoint | name=%s | format=%s | url=%s", name, fmt, url)
            bytes_written, content_type = fetch_to_path(
                url=url,
                out_path=out_path,
                headers=headers,
                params=params,
                timeout_s=timeout_s,
                verify_tls=verify_tls,
            )
            logger.info(
                "Saved endpoint | name=%s | path=%s | bytes=%d | content_type=%s",
                name, out_path, bytes_written, content_type,
            )
            ok += 1
        except requests.HTTPError as e:
            # Provide status code + body snippet if possible
            resp = getattr(e, "response", None)
            status = getattr(resp, "status_code", None)
            text_snip = None
            try:
                if resp is not None and resp.text:
                    text_snip = resp.text[:300]
            except Exception:
                pass

            logger.error(
                "HTTP error fetching endpoint | name=%s | url=%s | status=%s | snippet=%s",
                name, url, status, text_snip,
                exc_info=True,
            )
            raise
        except Exception:
            logger.error("Failed fetching endpoint | name=%s | url=%s", name, url, exc_info=True)
            raise

    logger.info("Realtime snapshot completed | ts=%s | success=%d/%d | folder=%s", ts, ok, len(endpoints), snapshot_dir)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    raise SystemExit(main())
