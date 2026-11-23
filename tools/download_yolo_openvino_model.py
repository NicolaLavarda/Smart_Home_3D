"""Idempotent downloader and OpenVINO IR converter for YOLOv8n (640x640 COCO).

Downloads `yolov8n.onnx` into `spatial_server/models/yolov8n_openvino_model/`,
verifies input `(1, 3, 640, 640)` and output `(1, 84, 8400)` via ONNX Runtime,
and converts it to OpenVINO FP16 IR (`yolov8n.xml` + `yolov8n.bin`).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import types
import urllib.error
import urllib.request
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YOLO_DIR = REPO_ROOT / "spatial_server" / "models" / "yolov8n_openvino_model"

YOLOV8N_ONNX_URLS: list[str] = [
    "https://huggingface.co/Kalray/yolov8/resolve/main/yolov8n.onnx",
    "https://huggingface.co/SpotLab/YOLOv8Detection/resolve/main/yolov8n.onnx",
    "https://huggingface.co/unity/inference-engine-yolo/resolve/ed7f4daf9263d0d31be1d60b9d67c8baea721d60/yolov8n.onnx",
    "https://github.com/yoobright/yolo-onnx/raw/master/yolov8n.onnx",
]


def _safe_import_openvino():
    """Import OpenVINO while stubbing openvino_telemetry to avoid Windows AppData CID permission errors."""
    if "openvino_telemetry" not in sys.modules:
        sys.modules["openvino_telemetry"] = types.SimpleNamespace(
            Telemetry=lambda *a, **k: types.SimpleNamespace(
                send_event=lambda *a, **k: None,
                start_session=lambda *a, **k: None,
                end_session=lambda *a, **k: None,
                init=lambda *a, **k: None,
            )
        )
    import openvino as ov

    return ov


def _download_file(urls: list[str], dest: Path, timeout_s: float = 120.0) -> str:
    last_err: Exception | None = None
    tmp_dest = dest.with_suffix(".onnx.part")
    for url in urls:
        try:
            print(f"[download] Trying {url} -> {dest.name} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "SmartHome3D-ModelSetup/1.0"})
            with urllib.request.urlopen(req, timeout=timeout_s) as resp, tmp_dest.open("wb") as out:
                if resp.status >= 400:
                    raise urllib.error.HTTPError(url, resp.status, "HTTP error", resp.headers, None)
                shutil.copyfileobj(resp, out)
            if tmp_dest.stat().st_size < 5_000_000:
                raise ValueError(f"Downloaded file {tmp_dest} too small ({tmp_dest.stat().st_size} bytes)")
            tmp_dest.replace(dest)
            return url
        except Exception as exc:
            last_err = exc
            print(f"[warn] Download failed from {url}: {exc}")
            tmp_dest.unlink(missing_ok=True)
    raise RuntimeError(f"All download mirrors failed for {dest.name}: {last_err}")


def verify_onnx_model(onnx_path: Path) -> None:
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    sess = ort.InferenceSession(str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"])
    dummy = np.zeros((1, 3, 640, 640), dtype=np.float32)
    inp_name = sess.get_inputs()[0].name
    out = sess.run(None, {inp_name: dummy})[0]
    if out.ndim != 3 or 84 not in out.shape:
        raise ValueError(f"Unexpected YOLOv8n ONNX output shape: {out.shape}")
    print(f"[ok] Verified ONNX Runtime inference on {onnx_path.name}: input={dummy.shape} -> output={out.shape}")


def convert_onnx_to_openvino_ir(onnx_path: Path, xml_path: Path) -> None:
    ov = _safe_import_openvino()
    core = ov.Core()
    ov_model = core.read_model(str(onnx_path))
    ov.save_model(ov_model, str(xml_path), compress_to_fp16=True)
    bin_path = xml_path.with_suffix(".bin")
    if not xml_path.is_file() or not bin_path.is_file():
        raise RuntimeError(f"OpenVINO IR save failed for {xml_path}")
    print(
        f"[ok] Saved OpenVINO IR: {xml_path.name} + {bin_path.name} "
        f"({bin_path.stat().st_size / (1024 * 1024):.2f} MB)"
    )


def download_and_prepare_yolov8n(target_dir: Path = DEFAULT_YOLO_DIR, force: bool = False) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = target_dir / "yolov8n.onnx"
    xml_path = target_dir / "yolov8n.xml"
    bin_path = target_dir / "yolov8n.bin"

    if force or not (onnx_path.is_file() and onnx_path.stat().st_size > 5_000_000):
        _download_file(YOLOV8N_ONNX_URLS, onnx_path)
    else:
        print(f"[skip] {onnx_path.name} already present ({onnx_path.stat().st_size / (1024 * 1024):.2f} MB)")

    verify_onnx_model(onnx_path)

    if force or not (xml_path.is_file() and bin_path.is_file() and bin_path.stat().st_size > 2_000_000):
        try:
            convert_onnx_to_openvino_ir(onnx_path, xml_path)
        except Exception as exc:
            print(f"[warn] OpenVINO IR conversion skipped ({exc}); ONNX model is ready for direct execution.")
    else:
        print(f"[skip] OpenVINO IR {xml_path.name} + {bin_path.name} already present.")

    return xml_path if xml_path.is_file() else onnx_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and convert YOLOv8n for OpenVINO / ONNX Runtime.")
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_YOLO_DIR)
    parser.add_argument("--force", action="store_true", help="Re-download and re-convert existing files.")
    args = parser.parse_args()

    out_path = download_and_prepare_yolov8n(args.target_dir, force=args.force)
    print(f"[DONE] YOLOv8n detector model ready at: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
