from __future__ import annotations

from pathlib import Path
import zipfile
import requests

from src.utils.config_loader import load_config


def download_file(url: str, out_path: Path, timeout_s: int = 60, verify_tls: bool = True) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True, timeout=timeout_s, verify=verify_tls) as r:
        r.raise_for_status()
        with out_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def extract_zip_filtered(zip_path: Path, out_dir: Path, mode: str, files: set[str]) -> tuple[int, int]:
    """
    Extract a GTFS zip into out_dir using either:
      - mode == "exclude": extract everything except names in `files`
      - mode == "include": extract only names in `files`

    Returns (extracted_count, skipped_count)

    Notes:
    - We decide based on the *base filename* (Path(member).name), so both
      "static/stops.txt" and "stops.txt" match "stops.txt".
    - We flatten output: always write to out_dir/<base_filename>.
      This avoids creating out_dir/static/... and keeps your folder clean.
    """
    mode = (mode or "exclude").lower().strip()
    if mode not in {"exclude", "include"}:
        raise ValueError(f"Unsupported extract.mode: {mode} (expected 'exclude' or 'include')")

    out_dir.mkdir(parents=True, exist_ok=True)

    extracted = 0
    skipped = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue

            base_name = Path(member.filename).name  # e.g., "stops.txt"
            if not base_name:
                continue

            if mode == "exclude":
                should_extract = base_name not in files
            else:  # include
                should_extract = base_name in files

            if not should_extract:
                skipped += 1
                continue

            # Extract content and write flattened to out_dir/base_name
            target_path = out_dir / base_name
            with zf.open(member, "r") as src, target_path.open("wb") as dst:
                dst.write(src.read())

            extracted += 1

    return extracted, skipped


def main() -> int:
    cfg = load_config()

    static_type = cfg.get("provider.static.type")
    if static_type != "gtfs_static_zip":
        raise ValueError(f"Unsupported provider.static.type: {static_type}")

    url = cfg.get("provider.static.url")
    out_dir = cfg.resolve_path(cfg.get("provider.static.out_dir", "data/static"))
    filename = cfg.get("provider.static.filename", "gtfs_static.zip")
    timeout_s = int(cfg.get("provider.static.timeout_s", 60))
    verify_tls = bool(cfg.get("provider.static.verify_tls", True))

    if not url:
        raise RuntimeError("Missing provider.static.url in YAML")

    zip_path = out_dir / filename

    # 1) download zip
    download_file(url=url, out_path=zip_path, timeout_s=timeout_s, verify_tls=verify_tls)
    print(f"[OK] Static GTFS zip downloaded: {zip_path}")

    # 2) extract zip (allow-list based on YAML)
    files_list = cfg.get("provider.static.extract.files", []) or []
    file_set = {str(x).strip() for x in files_list if str(x).strip()}

    if not file_set:
        raise RuntimeError(
            "provider.static.extract.files is empty. "
            "You must explicitly list which GTFS files to extract."
        )

    print(f"[INFO] Static extraction allow-list size: {len(file_set)}")

    extracted, skipped = extract_zip_filtered(
        zip_path=zip_path,
        out_dir=out_dir,
        mode="include",
        files=file_set,
    )
    print(f"[OK] Static GTFS extracted into: {out_dir} | extracted={extracted} skipped={skipped}")

    # 3) delete zip
    try:
        zip_path.unlink()
        print(f"[OK] Deleted zip: {zip_path}")
    except Exception as e:
        raise RuntimeError(f"Failed to delete zip '{zip_path}': {e}") from e

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
