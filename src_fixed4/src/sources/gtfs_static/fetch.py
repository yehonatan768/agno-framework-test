from __future__ import annotations

import logging
from pathlib import Path
import zipfile
from typing import Iterable, Set, Tuple, Optional

import requests

from src.utils.provider_config_loader import load_config


logger = logging.getLogger(__name__)


def download_file(url: str, out_path: Path, timeout_s: int = 60, verify_tls: bool = True) -> Tuple[int, Optional[str]]:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True, timeout=timeout_s, verify=verify_tls) as r:
        r.raise_for_status()
        content_type = r.headers.get("Content-Type")
        total = 0
        with out_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
    return total, content_type


def extract_zip_include_only(zip_path: Path, out_dir: Path, allowed_files: Set[str]) -> Tuple[int, int]:
    """
    Extract ONLY allowed_files, matching by base filename (Path(member).name).
    Output is flattened into out_dir/<base_filename>.
    Returns (extracted_count, skipped_count)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted = 0
    skipped = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        logger.info("ZIP opened | path=%s | members=%d", zip_path, len(members))

        for m in members:
            if m.is_dir():
                continue

            base_name = Path(m.filename).name
            if not base_name:
                skipped += 1
                continue

            if base_name not in allowed_files:
                skipped += 1
                continue

            target_path = out_dir / base_name
            with zf.open(m, "r") as src, target_path.open("wb") as dst:
                dst.write(src.read())

            extracted += 1

    return extracted, skipped



def cleanup_out_dir(out_dir: Path, allowed_files: Set[str]) -> Tuple[int, int]:
    """Remove previously-extracted files that are not in the current allow-list.

    This solves the common confusion where the allow-list is changed, but old files
    remain in the folder, making it look like we "extracted everything".
    Returns (deleted_count, kept_count).
    """
    deleted = 0
    kept = 0
    # only manage top-level files we extract (flattened)
    for p in out_dir.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if name in allowed_files:
            kept += 1
            continue
        # be conservative: only delete typical GTFS artifacts
        if name.endswith((".txt", ".csv", ".json", ".pb", ".pbf", ".zip")):
            try:
                p.unlink()
                deleted += 1
            except Exception:
                logger.warning("Failed to delete stale file | path=%s", p, exc_info=True)
        else:
            kept += 1
    return deleted, kept

def main() -> int:
    cfg = load_config()

    static_type = cfg.get("provider.static.type")
    if static_type != "gtfs_static_zip":
        raise ValueError(f"Unsupported provider.static.type: {static_type}")

    url = cfg.get("provider.static.url")
    out_dir = cfg.resolve_path(cfg.get("provider.static.out_dir", "dataset/static"))
    filename = cfg.get("provider.static.filename", "gtfs_static.zip")
    timeout_s = int(cfg.get("provider.static.timeout_s", 60))
    verify_tls = bool(cfg.get("provider.static.verify_tls", True))

    if not url:
        raise RuntimeError("Missing provider.static.url in YAML")

    # include-only allow-list
    files_list = cfg.get("provider.static.extract.files", []) or []
    allowed = {str(x).strip() for x in files_list if str(x).strip()}

    if not allowed:
        raise RuntimeError(
            "provider.static.extract.files is empty. "
            "You must explicitly list which GTFS files to extract."
        )

    # warn about likely mistakes (e.g., 'calendar' instead of 'calendar.txt')
    suspicious = [f for f in allowed if "." not in f]
    if suspicious:
        logger.warning("Some allowed filenames have no extension (likely typo): %s", suspicious)

    # Ensure the output directory reflects *only* the current allow-list.
    # Without this, old files remain and it can look like we extracted everything.
    clean = bool(cfg.get("provider.static.extract.clean_out_dir", True))
    if clean:
        deleted, kept = cleanup_out_dir(out_dir=out_dir, allowed_files=allowed)
        if deleted:
            logger.info("Cleaned static out_dir | deleted=%d | kept=%d | out_dir=%s", deleted, kept, out_dir)

    zip_path = out_dir / filename
    bytes_written, content_type = download_file(url=url, out_path=zip_path, timeout_s=timeout_s, verify_tls=verify_tls)
    logger.info("Downloaded static GTFS ZIP | bytes=%d | content_type=%s | path=%s", bytes_written, content_type, zip_path)

    extracted, skipped = extract_zip_include_only(zip_path=zip_path, out_dir=out_dir, allowed_files=allowed)
    logger.info(
        "Extracted static GTFS files (allow-list) | extracted=%d | skipped=%d | out_dir=%s",
        extracted,
        skipped,
        out_dir,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())