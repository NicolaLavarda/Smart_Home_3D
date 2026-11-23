"""Fase 0 Standalone Benchmark: Reolink CGI Snap + Face ONNX + ALPR ONNX.

Measures real-world latency (p50/mean/p95 ms), decode overhead (including 16MP
Reolink Duo 3 PoE 32:9 downscaling), memory footprint (RSS MB), and compares
ONNX Runtime (`CPUExecutionProvider` threads=1/2/4) against native OpenVINO
(`CPU` threads=2, optional `GPU`) on local hardware with zero temporary files.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import statistics
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Callable

import cv2
import httpx
import numpy as np
import onnxruntime as ort
import psutil
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tools"))

from enroll_faces import (  # noqa: E402
    DEFAULT_INPUT_DIR,
    align_and_embed,
    detect_with_tight_crop_fallback,
    load_image_unicode,
    make_ort_session,
)

DEFAULT_MODELS_DIR = REPO_ROOT / "spatial_server" / "models" / "biometrics"
DEFAULT_DATA_DIR = REPO_ROOT / "spatial_server" / "data" / "biometrics"

CAMERA_SPECS: list[dict[str, Any]] = [
    {
        "camera_id": "Cam_Carraio",
        "env_prefix": "REOLINK_CARRAIO",
        "default_ip": "192.168.86.47",
        "panoramic": False,
    },
    {
        "camera_id": "Cam_Portico",
        "env_prefix": "REOLINK_PORTICO",
        "default_ip": "192.168.86.51",
        "panoramic": False,
    },
    {
        "camera_id": "Cam_Ingresso",
        "env_prefix": "REOLINK_INGRESSO",
        "default_ip": "192.168.86.53",
        "panoramic": True,
    },
    {
        "camera_id": "Cam_Stradina",
        "env_prefix": "REOLINK_STRADINA",
        "default_ip": "192.168.86.55",
        "panoramic": True,
    },
]


def get_rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024.0 * 1024.0)


def measure_stats(fn: Callable[[], Any], warmup: int = 5, iters: int = 25) -> dict[str, float]:
    for _ in range(warmup):
        fn()
    times_ms: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        times_ms.append((time.perf_counter() - t0) * 1000.0)
    times_ms.sort()
    p50 = float(statistics.median(times_ms))
    mean = float(statistics.mean(times_ms))
    p95 = float(np.percentile(times_ms, 95))
    return {
        "p50_ms": round(p50, 2),
        "mean_ms": round(mean, 2),
        "p95_ms": round(p95, 2),
        "min_ms": round(times_ms[0], 2),
    }


def _env_password(prefix: str) -> str:
    val = os.getenv(f"{prefix}_PASS", "").strip()
    if not val and prefix == "REOLINK_CARRAIO":
        val = os.getenv("REOLINK_CARRAIO_PASSWORD", "").strip()
    return val


_SAFE_REOLINK_QUERY_CHARS = "!$'()*+,;:@~-"


def _build_reolink_query_url(ip: str, params: dict[str, str]) -> str:
    """Build Reolink CGI URL preserving `!` and RFC 3986 sub-delims in query values."""
    encoded_pairs = [
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe=_SAFE_REOLINK_QUERY_CHARS)}"
        for k, v in params.items()
    ]
    return f"http://{ip}:80/cgi-bin/api.cgi?{'&'.join(encoded_pairs)}"


def _parse_reolink_error(raw_bytes: bytes) -> tuple[int | None, str | None]:
    """Extract Reolink CGI (rspCode, detail) if body is JSON error instead of JPEG."""
    try:
        payload = json.loads(raw_bytes.decode("utf-8", errors="replace"))
        item = payload[0] if isinstance(payload, list) and payload else payload
        if isinstance(item, dict) and item.get("code") == 1:
            err = item.get("error") or {}
            return err.get("rspCode"), str(err.get("detail") or "reolink_error")
    except Exception:
        pass
    return None, None


def _reolink_token_login(client: httpx.Client, ip: str, user: str, pwd: str) -> tuple[str | None, int | None, str | None]:
    """Authenticate via POST cmd=Login JSON body (immune to URL special-char parsing)."""
    body = [{"cmd": "Login", "param": {"User": {"userName": user, "password": pwd}}}]
    resp = client.post(f"http://{ip}:80/cgi-bin/api.cgi?cmd=Login", json=body)
    if resp.status_code != 200:
        return None, None, f"login_http_{resp.status_code}"
    try:
        payload = resp.json()
        item = payload[0] if isinstance(payload, list) and payload else payload
        if isinstance(item, dict) and item.get("code") == 0:
            token = ((item.get("value") or {}).get("Token") or {}).get("name")
            if token:
                return str(token), None, None
        rsp_code, detail = _parse_reolink_error(resp.content)
        return None, rsp_code, detail or "login_failed"
    except Exception as exc:
        return None, None, type(exc).__name__


def benchmark_reolink_snap(
    iters: int = 3,
    timeout_s: float = 3.0,
) -> tuple[list[dict[str, Any]], dict[str, np.ndarray]]:
    """Probe Reolink CGI `cmd=Snap` in RAM (never logging credentials/URLs)."""
    results: list[dict[str, Any]] = []
    sample_frames: dict[str, np.ndarray] = {}

    with httpx.Client(timeout=timeout_s) as client:
        for spec in CAMERA_SPECS:
            cam_id = spec["camera_id"]
            prefix = spec["env_prefix"]
            ip = os.getenv(f"{prefix}_IP", "").strip() or spec["default_ip"]
            user = os.getenv(f"{prefix}_USER", "").strip() or "admin"
            pwd = _env_password(prefix)

            if not pwd:
                results.append({"camera_id": cam_id, "ip": ip, "status": "skipped_no_password"})
                continue

            auth_mode = "raw_query"
            session_token: str | None = None
            auth_locked_out = False

            variants: list[tuple[str, dict[str, str]]] = [
                ("native", {"cmd": "Snap", "channel": "0"}),
            ]
            if spec["panoramic"]:
                variants.append(("requested_3840x1080", {"cmd": "Snap", "channel": "0", "width": "3840", "height": "1080"}))

            for variant_name, base_params in variants:
                if auth_locked_out:
                    results.append({"camera_id": cam_id, "ip": ip, "variant": variant_name, "error": "aborted_auth_failed"})
                    continue

                fetch_ms: list[float] = []
                decode_ms: list[float] = []
                decode_reduced_ms: list[float] = []
                payload_kb: list[float] = []
                shape_hw: tuple[int, int] | None = None
                reduced_hw: tuple[int, int] | None = None
                last_status: int | str = "error"
                err_msg: str | None = None

                for i in range(iters):
                    try:
                        if auth_mode == "token_login" and session_token:
                            url = _build_reolink_query_url(
                                ip,
                                {**base_params, "rs": uuid.uuid4().hex[:10], "token": session_token},
                            )
                        else:
                            url = _build_reolink_query_url(
                                ip,
                                {**base_params, "rs": uuid.uuid4().hex[:10], "user": user, "password": pwd},
                            )

                        t0 = time.perf_counter()
                        resp = client.get(url)
                        t_fetch = (time.perf_counter() - t0) * 1000.0
                        last_status = resp.status_code
                        ctype = (resp.headers.get("content-type") or "").lower()

                        if (resp.status_code != 200 or "image" not in ctype) and auth_mode == "raw_query":
                            rsp_code, detail = _parse_reolink_error(resp.content)
                            # Single fallback to POST JSON cmd=Login -> token_login (never retry -502 loops)
                            tok, login_rsp, login_err = _reolink_token_login(client, ip, user, pwd)
                            if tok:
                                auth_mode = "token_login"
                                session_token = tok
                                url = _build_reolink_query_url(
                                    ip,
                                    {**base_params, "rs": uuid.uuid4().hex[:10], "token": session_token},
                                )
                                t0 = time.perf_counter()
                                resp = client.get(url)
                                t_fetch = (time.perf_counter() - t0) * 1000.0
                                last_status = resp.status_code
                                ctype = (resp.headers.get("content-type") or "").lower()
                            else:
                                if login_rsp == -502 or rsp_code == -502:
                                    auth_locked_out = True
                                err_msg = f"raw({rsp_code}:{detail})_login({login_rsp}:{login_err})"
                                break

                        if resp.status_code != 200 or "image" not in ctype:
                            rsp_code, detail = _parse_reolink_error(resp.content)
                            if rsp_code == -502:
                                auth_locked_out = True
                            err_msg = f"http_{resp.status_code}_{rsp_code or ctype[:24]}_{detail or ''}".strip("_")
                            break

                        raw_bytes = resp.content
                        payload_kb.append(len(raw_bytes) / 1024.0)
                        fetch_ms.append(t_fetch)

                        buf = np.frombuffer(raw_bytes, dtype=np.uint8)
                        t1 = time.perf_counter()
                        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                        t_dec = (time.perf_counter() - t1) * 1000.0
                        if img is None:
                            err_msg = "imdecode_failed"
                            break
                        decode_ms.append(t_dec)
                        shape_hw = (int(img.shape[0]), int(img.shape[1]))

                        if cam_id not in sample_frames and variant_name == "native":
                            sample_frames[cam_id] = img

                        if spec["panoramic"] and variant_name == "native":
                            t2 = time.perf_counter()
                            img_red = cv2.imdecode(buf, cv2.IMREAD_REDUCED_COLOR_2)
                            t_red = (time.perf_counter() - t2) * 1000.0
                            if img_red is not None:
                                decode_reduced_ms.append(t_red)
                                reduced_hw = (int(img_red.shape[0]), int(img_red.shape[1]))
                            del img_red

                        if i > 0 or variant_name != "native":
                            del img
                    except Exception as exc:
                        # Never include httpx URL/params in logs to avoid credential exposure
                        err_msg = type(exc).__name__
                        break

                entry: dict[str, Any] = {
                    "camera_id": cam_id,
                    "ip": ip,
                    "variant": variant_name,
                    "auth_mode": auth_mode,
                    "http_status": last_status,
                }
                if err_msg:
                    entry["error"] = err_msg
                if fetch_ms and shape_hw:
                    h, w = shape_hw
                    entry.update(
                        {
                            "resolution": f"{w}x{h}",
                            "raw_bgr_mb": round((h * w * 3) / (1024.0 * 1024.0), 2),
                            "jpeg_kb_mean": round(statistics.mean(payload_kb), 1),
                            "fetch_ms_mean": round(statistics.mean(fetch_ms), 1),
                            "decode_ms_mean": round(statistics.mean(decode_ms), 1),
                        }
                    )
                if decode_reduced_ms and reduced_hw:
                    rh, rw = reduced_hw
                    entry["reduced_2_decode"] = {
                        "resolution": f"{rw}x{rh}",
                        "raw_bgr_mb": round((rh * rw * 3) / (1024.0 * 1024.0), 2),
                        "decode_ms_mean": round(statistics.mean(decode_reduced_ms), 1),
                    }
                results.append(entry)

    return results, sample_frames


def _make_ort_opts(threads: int) -> ort.SessionOptions:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = max(1, int(threads))
    opts.inter_op_num_threads = 1
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return opts


def _make_synthetic_plate_scene() -> tuple[np.ndarray, np.ndarray]:
    """Generate a realistic 640x480 vehicle-rear crop + clean 240x64 Italian plate crop."""
    scene = np.full((480, 640, 3), (65, 72, 78), dtype=np.uint8)
    # Car bumper / trunk silhouette
    cv2.rectangle(scene, (90, 90), (550, 410), (42, 48, 56), -1)
    cv2.rectangle(scene, (120, 120), (520, 210), (30, 34, 38), -1)
    # Italian plate centered inside car rear: 240x56 px
    px1, py1, px2, py2 = 200, 265, 440, 321
    cv2.rectangle(scene, (px1, py1), (px2, py2), (242, 244, 246), -1)
    cv2.rectangle(scene, (px1, py1), (px1 + 24, py2), (165, 65, 18), -1)  # EU blue band
    cv2.putText(scene, "I", (px1 + 6, py2 - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(scene, "AB123CD", (px1 + 34, py2 - 14), cv2.FONT_HERSHEY_SIMPLEX, 1.05, (15, 15, 18), 3, cv2.LINE_AA)
    cv2.rectangle(scene, (px1, py1), (px2, py2), (20, 20, 20), 2)
    plate_crop = scene[py1:py2, px1:px2].copy()
    return scene, plate_crop


def _pick_sample_face_image(faces_dir: Path) -> np.ndarray:
    if faces_dir.is_dir():
        for img_path in sorted(faces_dir.rglob("*")):
            if img_path.is_file() and img_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                img = load_image_unicode(img_path)
                if img is not None:
                    return img
    # Fallback synthetic 512x512 BGR tensor
    return np.full((512, 512, 3), 128, dtype=np.uint8)


def benchmark_face_pipeline(
    models_dir: Path,
    gallery_mbf_path: Path,
    gallery_r50_path: Path,
    faces_dir: Path,
    sample_frames: dict[str, np.ndarray],
    warmup: int,
    iters: int,
) -> dict[str, Any]:
    import openvino as ov

    face_dir = models_dir / "face"
    det_path = face_dir / "det_500m.onnx"
    mbf_path = face_dir / "w600k_mbf.onnx"
    r50_path = face_dir / "w600k_r50.onnx"

    # Build a 512x512 person crop (from live camera if available, else synthetic) + a real face photo
    if sample_frames:
        first_frame = next(iter(sample_frames.values()))
        fh, fw = first_frame.shape[:2]
        cx, cy = fw // 2, fh // 2
        half = min(256, cx, cy)
        cam_crop = cv2.resize(first_frame[cy - half : cy + half, cx - half : cx + half], (512, 512))
    else:
        cam_crop = np.full((512, 512, 3), 128, dtype=np.uint8)

    real_face = _pick_sample_face_image(faces_dir)
    det_blob = cv2.dnn.blobFromImage(cv2.resize(cam_crop, (640, 640)), 1.0 / 128.0, (640, 640), (127.5, 127.5, 127.5), swapRB=True)
    rec_blob = np.random.default_rng(42).uniform(-1.0, 1.0, size=(1, 3, 112, 112)).astype(np.float32)

    report: dict[str, Any] = {"det_500m": {}, "w600k_mbf": {}, "w600k_r50": {}, "gallery_search": {}}

    # 1. SCRFD det_500m benchmarks (ORT CPU 1/2/4 + OpenVINO CPU/GPU)
    for t in (1, 2, 4):
        gc.collect()
        rss_before = get_rss_mb()
        sess = make_ort_session(det_path, threads=t)
        in_name = sess.get_inputs()[0].name
        stats = measure_stats(lambda: sess.run(None, {in_name: det_blob}), warmup=warmup, iters=iters)
        rss_after = get_rss_mb()
        report["det_500m"][f"ort_cpu_t{t}"] = {**stats, "rss_delta_mb": round(max(0.0, rss_after - rss_before), 1)}
        del sess

    ov_core = ov.Core()
    avail_devices = list(ov_core.available_devices)
    report["openvino_devices"] = avail_devices
    for dev in ([d for d in ("CPU", "GPU") if d in avail_devices]):
        try:
            gc.collect()
            rss_before = get_rss_mb()
            t_c0 = time.perf_counter()
            ov_model = ov_core.read_model(str(det_path))
            ov_in = ov_model.inputs[0].get_any_name()
            ov_model.reshape({ov_in: [1, 3, 640, 640]})
            cfg = {"INFERENCE_NUM_THREADS": 2} if dev == "CPU" else {}
            compiled = ov_core.compile_model(ov_model, dev, cfg)
            compile_ms = (time.perf_counter() - t_c0) * 1000.0
            stats = measure_stats(lambda: compiled([det_blob]), warmup=warmup, iters=iters)
            rss_after = get_rss_mb()
            report["det_500m"][f"openvino_{dev.lower()}"] = {
                **stats,
                "compile_ms": round(compile_ms, 1),
                "rss_delta_mb": round(max(0.0, rss_after - rss_before), 1),
            }
            del compiled, ov_model
        except Exception as exc:
            report["det_500m"][f"openvino_{dev.lower()}"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 2. Recognition models: w600k_mbf vs w600k_r50
    for label, path in (("w600k_mbf", mbf_path), ("w600k_r50", r50_path)):
        for t in (1, 2, 4):
            gc.collect()
            rss_before = get_rss_mb()
            sess = make_ort_session(path, threads=t)
            in_name = sess.get_inputs()[0].name
            stats = measure_stats(lambda: sess.run(None, {in_name: rec_blob}), warmup=warmup, iters=iters)
            rss_after = get_rss_mb()
            report[label][f"ort_cpu_t{t}"] = {**stats, "rss_delta_mb": round(max(0.0, rss_after - rss_before), 1)}
            del sess

        for dev in ([d for d in ("CPU", "GPU") if d in avail_devices]):
            try:
                gc.collect()
                rss_before = get_rss_mb()
                t_c0 = time.perf_counter()
                ov_model = ov_core.read_model(str(path))
                ov_in = ov_model.inputs[0].get_any_name()
                ov_model.reshape({ov_in: [1, 3, 112, 112]})
                cfg = {"INFERENCE_NUM_THREADS": 2} if dev == "CPU" else {}
                compiled = ov_core.compile_model(ov_model, dev, cfg)
                compile_ms = (time.perf_counter() - t_c0) * 1000.0
                stats = measure_stats(lambda: compiled([rec_blob]), warmup=warmup, iters=iters)
                rss_after = get_rss_mb()
                report[label][f"openvino_{dev.lower()}"] = {
                    **stats,
                    "compile_ms": round(compile_ms, 1),
                    "rss_delta_mb": round(max(0.0, rss_after - rss_before), 1),
                }
                del compiled, ov_model
            except Exception as exc:
                report[label][f"openvino_{dev.lower()}"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 3. End-to-end single-face pipeline + gallery search
    det_sess = make_ort_session(det_path, threads=2)
    mbf_sess = make_ort_session(mbf_path, threads=2)

    def _run_e2e_face():
        boxes, kps, _ = detect_with_tight_crop_fallback(det_sess, real_face)
        if len(boxes) > 0:
            _ = align_and_embed(mbf_sess, real_face, kps[0])

    report["e2e_real_face_mbf_ort_t2"] = measure_stats(_run_e2e_face, warmup=3, iters=15)

    for g_name, g_path in (("mbf", gallery_mbf_path), ("r50", gallery_r50_path)):
        if g_path.is_file():
            data = np.load(g_path)
            centroids = data["centroids"]
            reps = data["rep_embeddings"]
            probe = reps[0]
            g_stats = measure_stats(lambda: (centroids @ probe, reps @ probe), warmup=20, iters=500)
            report["gallery_search"][g_name] = {
                "people": int(len(data["person_names"])),
                "reps": int(len(reps)),
                **g_stats,
            }

    del det_sess, mbf_sess
    return report


def benchmark_alpr_pipeline(
    models_dir: Path,
    warmup: int,
    iters: int,
) -> dict[str, Any]:
    from fast_plate_ocr import LicensePlateRecognizer
    from open_image_models.detection.factory import create_detector

    alpr_dir = models_dir / "alpr"
    det_onnx = alpr_dir / "yolo-v9-t-384-license-plate-end2end" / "yolo-v9-t-384-license-plates-end2end.onnx"
    cct_onnx = alpr_dir / "cct-xs-v2-global-model" / "cct_xs_v2_global.onnx"
    cct_cfg = alpr_dir / "cct-xs-v2-global-model" / "cct_xs_v2_global_plate_config.yaml"
    mvit_onnx = alpr_dir / "european-plates-mobile-vit-v2-model" / "european_mobile_vit_v2_ocr.onnx"
    mvit_cfg = alpr_dir / "european-plates-mobile-vit-v2-model" / "european_mobile_vit_v2_ocr_config.yaml"

    vehicle_crop, plate_crop_bgr = _make_synthetic_plate_scene()
    plate_crop_rgb = cv2.cvtColor(plate_crop_bgr, cv2.COLOR_BGR2RGB)
    plate_crop_gray = cv2.cvtColor(plate_crop_bgr, cv2.COLOR_BGR2GRAY)

    report: dict[str, Any] = {}
    opts = _make_ort_opts(threads=2)

    gc.collect()
    rss_before = get_rss_mb()
    detector = create_detector(
        det_onnx,
        backend="yolo_v9",
        class_labels=("License Plate",),
        conf_thresh=0.25,
        providers=["CPUExecutionProvider"],
        sess_options=opts,
    )
    det_preds = detector.predict(vehicle_crop)
    det_stats = measure_stats(lambda: detector.predict(vehicle_crop), warmup=warmup, iters=iters)
    rss_after_det = get_rss_mb()
    report["plate_detector_yolov9_t_384_ort_t2"] = {
        **det_stats,
        "rss_delta_mb": round(max(0.0, rss_after_det - rss_before), 1),
        "synthetic_plate_detections": len(det_preds),
        "synthetic_top_conf": round(float(det_preds[0].confidence), 3) if det_preds else 0.0,
    }
    del detector

    # OCR 1: cct-xs-v2-global-model (RGB)
    gc.collect()
    rss_before = get_rss_mb()
    ocr_cct = LicensePlateRecognizer(
        onnx_model_path=cct_onnx,
        plate_config_path=cct_cfg,
        providers=["CPUExecutionProvider"],
        sess_options=opts,
    )
    cct_pred = ocr_cct.run(plate_crop_rgb, return_confidence=True)
    cct_stats = measure_stats(lambda: ocr_cct.run(plate_crop_rgb, return_confidence=True), warmup=warmup, iters=iters)
    rss_after_cct = get_rss_mb()
    report["ocr_cct_xs_v2_global_ort_t2"] = {
        **cct_stats,
        "rss_delta_mb": round(max(0.0, rss_after_cct - rss_before), 1),
        "synthetic_text": cct_pred[0].plate if cct_pred else "",
        "synthetic_region": getattr(cct_pred[0], "region", None) if cct_pred else None,
    }
    del ocr_cct

    # OCR 2: european-plates-mobile-vit-v2-model (Grayscale)
    gc.collect()
    rss_before = get_rss_mb()
    ocr_mvit = LicensePlateRecognizer(
        onnx_model_path=mvit_onnx,
        plate_config_path=mvit_cfg,
        providers=["CPUExecutionProvider"],
        sess_options=opts,
    )
    mvit_pred = ocr_mvit.run(plate_crop_gray, return_confidence=True)
    mvit_stats = measure_stats(lambda: ocr_mvit.run(plate_crop_gray, return_confidence=True), warmup=warmup, iters=iters)
    rss_after_mvit = get_rss_mb()
    report["ocr_european_mobilevit_v2_ort_t2"] = {
        **mvit_stats,
        "rss_delta_mb": round(max(0.0, rss_after_mvit - rss_before), 1),
        "synthetic_text": mvit_pred[0].plate if mvit_pred else "",
    }
    del ocr_mvit

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Fase 0 Biometric & Reolink Snapshot Benchmark.")
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--faces-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--gallery-mbf", type=Path, default=DEFAULT_DATA_DIR / "face_gallery_mbf.npz")
    parser.add_argument("--gallery-r50", type=Path, default=DEFAULT_DATA_DIR / "face_gallery_r50.npz")
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--iters", type=int, default=25)
    parser.add_argument("--skip-cameras", action="store_true")
    parser.add_argument("--only-cameras", action="store_true")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    vm = psutil.virtual_memory()
    freq = psutil.cpu_freq()
    host_info = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "cpu_freq_mhz": round(freq.max or freq.current, 0) if freq else None,
        "ram_total_gb": round(vm.total / (1024.0 ** 3), 2),
        "baseline_rss_mb": round(get_rss_mb(), 1),
    }

    if args.skip_cameras:
        snap_results, sample_frames = [], {}
    else:
        snap_results, sample_frames = benchmark_reolink_snap()

    if args.only_cameras:
        sample_frames.clear()
        print(json.dumps({"host": host_info, "reolink_cgi_snap": snap_results}, indent=2))
        return 0

    face_results = benchmark_face_pipeline(
        models_dir=args.models_dir,
        gallery_mbf_path=args.gallery_mbf,
        gallery_r50_path=args.gallery_r50,
        faces_dir=args.faces_dir,
        sample_frames=sample_frames,
        warmup=args.warmup,
        iters=args.iters,
    )
    sample_frames.clear()
    gc.collect()

    alpr_results = benchmark_alpr_pipeline(
        models_dir=args.models_dir,
        warmup=args.warmup,
        iters=args.iters,
    )

    final_report = {
        "host": host_info,
        "reolink_cgi_snap": snap_results,
        "face_pipeline": face_results,
        "alpr_pipeline": alpr_results,
        "final_rss_mb": round(get_rss_mb(), 1),
    }
    print(json.dumps(final_report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
