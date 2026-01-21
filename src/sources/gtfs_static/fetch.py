from __future__ import annotations

import logging
from pathlib import Path
import zipfile
from typing import Set, Tuple, Optional

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


def _split_allowed(allowed: Set[str]) -> Tuple[Set[str], Set[str]]:
    """Return (allowed_exact_filenames, allowed_stems).

    - If an entry contains a dot, it is treated as an exact filename match.
    - Otherwise it is treated as a stem match (e.g. "stops" matches "stops.txt" or "stops.csv").
    """
    allowed_exact = {a for a in allowed if "." in Path(a).name}
    allowed_stems = {a for a in allowed if a and "." not in Path(a).name}
    return allowed_exact, allowed_stems


def _is_allowed(base_name: str, allowed_exact: Set[str], allowed_stems: Set[str]) -> bool:
    if base_name in allowed_exact:
        return True
    stem = Path(base_name).stem
    return stem in allowed_stems


def extract_zip_include_only(zip_path: Path, out_dir: Path, allowed_files: Set[str]) -> Tuple[int, int]:
    """
    Extract ONLY allowed_files, matching by base filename (Path(member).name).
    Output is flattened into out_dir/<base_filename>.
    Returns (extracted_count, skipped_count)
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted = 0
    skipped = 0

    allowed_exact, allowed_stems = _split_allowed(allowed_files)

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

            if not _is_allowed(base_name, allowed_exact, allowed_stems):
                skipped += 1
                continue

            target_path = out_dir / base_name
            with zf.open(m, "r") as src, target_path.open("wb") as dst:
                dst.write(src.read())

            extracted += 1

    return extracted, skipped


def _cleanup_out_dir_keep_only(out_dir: Path, allowed_files: Set[str]) -> None:
    """Best-effort cleanup so the static directory contains only the allow-listed tables.

    When allow-list entries are stems (no extension), we keep any file whose stem matches.
    """
    allowed_exact, allowed_stems = _split_allowed(allowed_files)

    for p in out_dir.iterdir():
        if not p.is_file():
            continue
        base = p.name
        if _is_allowed(base, allowed_exact, allowed_stems):
            continue
        try:
            p.unlink()
            logger.info("Removed non-allowlisted static file | path=%s", p)
        except Exception:
            logger.warning("Failed to remove non-allowlisted static file | path=%s", p, exc_info=True)


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

    # NOTE: allowed entries may intentionally be stems without extensions.

    zip_path = out_dir / filename

    logger.info("Static GTFS download started | url=%s | zip_path=%s", url, zip_path)
    bytes_written, content_type = download_file(url=url, out_path=zip_path, timeout_s=timeout_s, verify_tls=verify_tls)
    logger.info("Static GTFS downloaded | bytes=%d | content_type=%s | path=%s", bytes_written, content_type, zip_path)

    logger.info("Static extraction started | out_dir=%s | allow_list=%d", out_dir, len(allowed))
    extracted, skipped = extract_zip_include_only(zip_path=zip_path, out_dir=out_dir, allowed_files=allowed)

    # keep directory tidy (especially if previous runs extracted other files)
    _cleanup_out_dir_keep_only(out_dir=out_dir, allowed_files=allowed)

    # high-signal check: did we miss any requested stems/filenames?
    present_basenames = {p.name for p in out_dir.iterdir() if p.is_file()}
    present_stems = {p.stem for p in out_dir.iterdir() if p.is_file()}
    allowed_exact, allowed_stems = _split_allowed(allowed)
    missing_exact = sorted([f for f in allowed_exact if f not in present_basenames])
    missing_stems = sorted([s for s in allowed_stems if s not in present_stems])
    if missing_exact or missing_stems:
        logger.warning(
            "Some requested static tables were not found in the ZIP (not extracted) | missing_exact=%s | missing_stems=%s",
            missing_exact,
            missing_stems,
        )

    logger.info("Static extraction completed | extracted=%d | skipped=%d | out_dir=%s", extracted, skipped, out_dir)

    # Best-effort cleanup. If the ZIP is already gone (e.g., concurrent runs or manual cleanup),
    # do not fail the whole fetch.
    try:
        zip_path.unlink()
        logger.info("Deleted static zip | path=%s", zip_path)
    except FileNotFoundError:
        logger.warning("Static zip already deleted | path=%s", zip_path)
    except Exception:
        logger.error("Failed to delete static zip | path=%s", zip_path, exc_info=True)
        raise

    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    raise SystemExit(main())
