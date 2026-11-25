from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spatial_server.research.telemetry import generate_research_summary_markdown


def export_research_bundle(
    source_dir: Path,
    *,
    output_zip: Path | None = None,
    include_crops: bool = True,
) -> Path:
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Telemetry directory not found: {source_dir}")

    if output_zip is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        exports_dir = source_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        output_zip = exports_dir / f"sh3d_research_bundle_{stamp}.zip"
    else:
        output_zip = Path(output_zip)
        output_zip.parent.mkdir(parents=True, exist_ok=True)

    summary_md = generate_research_summary_markdown(source_dir)

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr("REPORT_SUMMARY.md", summary_md.encode("utf-8"))
        for file_path in sorted(source_dir.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(source_dir)
            if rel.parts and rel.parts[0] == "exports":
                continue
            if not include_crops and "crops" in rel.parts:
                continue
            zf.write(file_path, arcname=rel.as_posix())

    return output_zip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export Smart Home 3D production research telemetry into a single ZIP bundle.")
    parser.add_argument(
        "--source",
        type=Path,
        default=REPO_ROOT / "spatial_server" / "data" / "research_telemetry",
        help="Path to telemetry directory (default: spatial_server/data/research_telemetry)",
    )
    parser.add_argument("--out", type=Path, default=None, help="Output ZIP file path")
    parser.add_argument("--no-crops", action="store_true", help="Exclude JPEG crops for a lightweight JSONL-only bundle")
    args = parser.parse_args(argv)

    out_path = export_research_bundle(args.source, output_zip=args.out, include_crops=not args.no_crops)
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Research bundle exported: {out_path} ({size_mb:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
