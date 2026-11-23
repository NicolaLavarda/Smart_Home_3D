"""Idempotent downloader and verifier for Fase 0 biometric ONNX models.

Stores all Face Recognition (InsightFace ONNX) and ALPR (open-image-models +
fast-plate-ocr) artifacts under `spatial_server/models/biometrics/` and emits
a SHA-256 `manifest.json` plus ONNX graph tensor metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import onnxruntime as ort

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODELS_DIR = REPO_ROOT / "spatial_server" / "models" / "biometrics"

FACE_ARCHIVES: list[dict[str, Any]] = [
    {
        "pack": "buffalo_s",
        "urls": [
            "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip",
            "https://sourceforge.net/projects/insightface.mirror/files/v0.7/buffalo_s.zip/download",
        ],
        "extract_files": ["det_500m.onnx", "w600k_mbf.onnx"],
    },
    {
        "pack": "buffalo_l",
        "urls": [
            "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
            "https://sourceforge.net/projects/insightface.mirror/files/v0.7/buffalo_l.zip/download",
        ],
        "extract_files": ["w600k_r50.onnx"],
    },
]

ALPR_DET_MODELS = ["yolo-v9-t-384-license-plate-end2end"]
ALPR_OCR_MODELS = ["cct-xs-v2-global-model", "european-plates-mobile-vit-v2-model"]


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_file(urls: list[str], dest: Path, timeout_s: float = 120.0) -> str:
    last_err: Exception | None = None
    for url in urls:
        try:
            print(f"[download] Trying {url} -> {dest.name} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "SmartHome3D-ModelSetup/1.0"})
            with urllib.request.urlopen(req, timeout=timeout_s) as resp, dest.open("wb") as out:
                if resp.status >= 400:
                    raise urllib.error.HTTPError(url, resp.status, "HTTP error", resp.headers, None)
                shutil.copyfileobj(resp, out)
            if dest.stat().st_size < 1024:
                raise ValueError(f"Downloaded file {dest} looks unexpectedly small ({dest.stat().st_size} bytes)")
            return url
        except Exception as exc:
            last_err = exc
            print(f"[warn] Download failed from {url}: {exc}")
            if dest.exists():
                dest.unlink(missing_ok=True)
    raise RuntimeError(f"All download mirrors failed for {dest.name}: {last_err}")


def download_face_models(face_dir: Path, force: bool = False) -> list[Path]:
    """Download InsightFace ONNX packs and extract only the required .onnx models."""
    face_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []

    for spec in FACE_ARCHIVES:
        targets = [face_dir / name for name in spec["extract_files"]]
        if not force and all(p.is_file() and p.stat().st_size > 100_000 for p in targets):
            print(f"[skip] {spec['pack']} models already present: {[p.name for p in targets]}")
            saved_paths.extend(targets)
            continue

        with tempfile.TemporaryDirectory(prefix=f"sh3d_{spec['pack']}_") as tmp:
            zip_path = Path(tmp) / f"{spec['pack']}.zip"
            _download_file(spec["urls"], zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                members = zf.namelist()
                for wanted in spec["extract_files"]:
                    match = next((m for m in members if Path(m).name == wanted), None)
                    if match is None:
                        raise FileNotFoundError(
                            f"Expected {wanted} inside {spec['pack']}.zip; found: {members}"
                        )
                    out_file = face_dir / wanted
                    with zf.open(match) as src, out_file.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    print(f"[ok] Extracted {out_file.name} ({out_file.stat().st_size / (1024 * 1024):.2f} MB)")
                    saved_paths.append(out_file)

    return saved_paths


def download_alpr_models(alpr_dir: Path, force: bool = False) -> list[Path]:
    """Download ALPR detector and OCR ONNX models into `alpr_dir`."""
    from fast_plate_ocr.inference.hub import download_model as download_ocr_model
    from open_image_models.detection.core.hub import download_model as download_det_model

    alpr_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: list[Path] = []

    for det_name in ALPR_DET_MODELS:
        det_dir = alpr_dir / det_name
        det_path = download_det_model(det_name, save_directory=det_dir, force_download=force)
        print(f"[ok] ALPR detector ready: {det_path} ({det_path.stat().st_size / (1024 * 1024):.2f} MB)")
        saved_paths.append(det_path)

    for ocr_name in ALPR_OCR_MODELS:
        ocr_dir = alpr_dir / ocr_name
        model_path, cfg_path = download_ocr_model(ocr_name, save_directory=ocr_dir, force_download=force)
        print(
            f"[ok] ALPR OCR ready: {model_path.name} ({model_path.stat().st_size / (1024 * 1024):.2f} MB)"
            f" + {cfg_path.name}"
        )
        saved_paths.extend([model_path, cfg_path])

    return saved_paths


def inspect_onnx_io(onnx_path: Path) -> dict[str, Any]:
    """Inspect ONNX model input/output tensor names and shapes via ONNX Runtime."""
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    sess = ort.InferenceSession(str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"])
    return {
        "inputs": [
            {"name": inp.name, "shape": inp.shape, "type": inp.type}
            for inp in sess.get_inputs()
        ],
        "outputs": [
            {"name": out.name, "shape": out.shape, "type": out.type}
            for out in sess.get_outputs()
        ],
    }


def build_manifest(models_dir: Path, files: list[Path]) -> Path:
    """Write `manifest.json` recording sizes, SHA-256 digests, and ONNX tensor IO."""
    entries: dict[str, Any] = {}
    unique_files = sorted({p.resolve() for p in files}, key=lambda p: str(p))
    for path in unique_files:
        rel = path.relative_to(models_dir.resolve()).as_posix()
        info: dict[str, Any] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        if path.suffix.lower() == ".onnx":
            info["onnx_io"] = inspect_onnx_io(path)
        entries[rel] = info

    manifest_path = models_dir / "manifest.json"
    manifest_payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models_dir": str(models_dir),
        "files": entries,
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and verify biometric ONNX models.")
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--force", action="store_true", help="Re-download existing models.")
    args = parser.parse_args()

    models_dir: Path = args.models_dir
    face_files = download_face_models(models_dir / "face", force=args.force)
    alpr_files = download_alpr_models(models_dir / "alpr", force=args.force)
    manifest_path = build_manifest(models_dir, [*face_files, *alpr_files])

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print("\n=== ONNX MODEL INSPECTION SUMMARY ===")
    for rel, meta in manifest["files"].items():
        size_mb = meta["bytes"] / (1024 * 1024)
        print(f"- {rel} ({size_mb:.2f} MB, sha256={meta['sha256'][:12]}...)")
        if "onnx_io" in meta:
            print(f"    inputs : {meta['onnx_io']['inputs']}")
            print(f"    outputs: {meta['onnx_io']['outputs']}")
    print(f"\n[DONE] Manifest written to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
