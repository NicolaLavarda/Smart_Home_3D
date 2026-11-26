from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
import cv2
import numpy as np

from spatial_server.domain.models import BoundingBox2D, DetectionEvent, SpatialReconstructionPolicy
from .interfaces import DetectionBatchCallback, IDetectionSource

logger = logging.getLogger(__name__)


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

COCO_TO_DOMAIN = {
    0: "person",
    1: "bicycle",
    2: "car",
    7: "truck",
    16: "dog",
    3: "motorbike",
}


def _coarse_detection_group(label: str) -> str:
    if label in ("car", "truck", "motorbike", "motorcycle", "bus"):
        return "vehicle"
    return label


def deduplicate_2d_detections(events: list[DetectionEvent]) -> list[DetectionEvent]:
    """
    Coarse-class 2D Non-Maximum & Containment Suppression within a single camera frame.
    Prevents the same physical vehicle (e.g. classified simultaneously as 'car' and 'truck'
    or split across a 180-deg panoramic stitching seam) or person from emitting multiple boxes.
    """
    if len(events) <= 1:
        return events

    ordered = sorted(events, key=lambda e: float(e.confidence), reverse=True)
    kept: list[DetectionEvent] = []

    for cand in ordered:
        c_grp = _coarse_detection_group(cand.class_label)
        cb = cand.bbox
        cw = max(1e-6, cb.x_max - cb.x_min)
        ch = max(1e-6, cb.y_max - cb.y_min)
        c_area = cw * ch
        c_cx = 0.5 * (cb.x_min + cb.x_max)

        is_dup = False
        for prev in kept:
            if _coarse_detection_group(prev.class_label) != c_grp:
                continue
            pb = prev.bbox
            pw = max(1e-6, pb.x_max - pb.x_min)
            ph = max(1e-6, pb.y_max - pb.y_min)
            p_area = pw * ph
            p_cx = 0.5 * (pb.x_min + pb.x_max)

            ix1 = max(cb.x_min, pb.x_min)
            iy1 = max(cb.y_min, pb.y_min)
            ix2 = min(cb.x_max, pb.x_max)
            iy2 = min(cb.y_max, pb.y_max)
            iw = max(0.0, ix2 - ix1)
            ih = max(0.0, iy2 - iy1)
            inter = iw * ih

            union = max(1e-6, c_area + p_area - inter)
            iou = inter / union
            containment = inter / max(1e-6, min(c_area, p_area))

            # Same ground contact point check (very close bottom-center UV)
            du_bottom = abs(c_cx - p_cx)
            dv_bottom = abs(cb.y_max - pb.y_max)
            close_bottom = (
                du_bottom <= 0.35 * max(cw, pw)
                and dv_bottom <= 0.22 * max(ch, ph)
            )

            iou_thresh = 0.38 if c_grp == "vehicle" else 0.45
            contain_thresh = 0.72 if c_grp == "vehicle" else 0.80
            if iou >= iou_thresh or containment >= contain_thresh or (close_bottom and inter > 0.0):
                is_dup = True
                break

        if not is_dup:
            kept.append(cand)

    return kept


class OpenVINORtspDetectionSource(IDetectionSource):
    """
    Local CPU/iGPU (Intel HD Graphics 530) CV detector reading go2rtc RTSP sub-stream
    (`rtsp://127.0.0.1:8554/carraio_sub`, 640x360) at ~7 fps.

    Backend inference chain:
    1. OpenVINO Runtime IR model (`yolov8n_openvino_model/*.xml`) with `device="AUTO"`
    2. Ultralytics YOLO OpenVINO/CPU fallback (if installed)
    3. OpenCV HOGDescriptor People Detector (always available zero-weight fallback)
    """

    mode_name = "openvino"

    def __init__(
        self,
        rtsp_url: str,
        camera_id: str = "Cam_Carraio",
        openvino_device: str = "AUTO",
        model_path: str = "",
        target_fps: float = 7.0,
        conf_threshold: float = 0.35,
        shared_compiled_ov=None,
        shared_backend_name: Optional[str] = None,
        infer_lock: Optional[threading.Lock] = None,
        cpu_threads: int = 2,
        reconstruction_policy: Optional[SpatialReconstructionPolicy] = None,
    ) -> None:
        self.rtsp_url = rtsp_url
        self.camera_id = camera_id
        self.openvino_device = openvino_device
        self.model_path = Path(model_path) if model_path else None
        self.frame_interval_s = 1.0 / max(target_fps, 1.0)
        self.conf_threshold = max(0.05, min(float(conf_threshold), 0.95))
        self.reconstruction_policy = reconstruction_policy
        self._infer_lock = infer_lock
        self.cpu_threads = max(1, int(cpu_threads))

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"rtsp-cv-{camera_id}")
        self._latest_frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_frame_ts: float = 0.0
        self._backend_name = "initializing"
        self._compiled_ov = None
        self._ort_session = None
        self._ort_input_name: Optional[str] = None
        self._yolo_model = None
        self._hog = None
        self._bg_sub = None
        self._mog2_warmup = 0
        self._rtsp_connected = False
        self._frames_read = 0
        self._frames_inferred = 0
        self._raw_detections_total = 0
        self._last_frame_ts = 0.0
        self._last_error: Optional[str] = None
        self._target_fps: float = max(0.25, float(target_fps))
        self._last_infer_ms: float = 0.0
        self._infer_ms_ema: float = 0.0
        self._reconnect_count: int = 0
        self._has_connected_once: bool = False
        self._mean_luma: float = 0.0
        self._mean_saturation: float = 0.0
        self._is_night_ir: bool = False
        if shared_compiled_ov is not None:
            if hasattr(shared_compiled_ov, "run") and hasattr(shared_compiled_ov, "get_inputs"):
                self._ort_session = shared_compiled_ov
                self._ort_input_name = shared_compiled_ov.get_inputs()[0].name
            else:
                self._compiled_ov = shared_compiled_ov
            self._backend_name = shared_backend_name or "openvino_ir(shared)"
            logger.info("Reusing shared detector model for %s (%s)", self.camera_id, self._backend_name)
        else:
            self._init_detector()

    @staticmethod
    def _extract_ov_output(compiled_ov, result) -> np.ndarray:
        if hasattr(compiled_ov, "output"):
            val = result[compiled_ov.output(0)]
        elif isinstance(result, dict):
            val = result[0] if 0 in result else next(iter(result.values()))
        else:
            val = result[0]
        return np.asarray(val.data if hasattr(val, "data") else val)

    @staticmethod
    def _letterbox_bgr(frame: np.ndarray, target_size: int = 640) -> tuple[np.ndarray, int, int, int, int]:
        h, w = frame.shape[:2]
        scale = min(target_size / max(w, 1), target_size / max(h, 1))
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        pad_x = (target_size - new_w) * 0.5
        pad_y = (target_size - new_h) * 0.5
        top = int(round(pad_y - 0.1))
        bottom = target_size - new_h - top
        left = int(round(pad_x - 0.1))
        right = target_size - new_w - left
        resized = (
            cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            if (new_w != w or new_h != h)
            else frame
        )
        canvas = cv2.copyMakeBorder(
            resized,
            top,
            bottom,
            left,
            right,
            cv2.BORDER_CONSTANT,
            value=(114, 114, 114),
        )
        return canvas, left, top, new_w, new_h

    def _compile_and_warmup_ov(self, core, ov_model, device_name: str):
        cpu_threads = max(1, int(getattr(self, "cpu_threads", 2)))
        if hasattr(core, "set_property"):
            try:
                core.set_property("CPU", {"INFERENCE_NUM_THREADS": cpu_threads})
            except Exception:
                pass
        if device_name.upper() == "CPU":
            try:
                compiled = core.compile_model(
                    ov_model,
                    device_name,
                    {"INFERENCE_NUM_THREADS": cpu_threads},
                )
            except TypeError:
                compiled = core.compile_model(ov_model, device_name)
        else:
            compiled = core.compile_model(ov_model, device_name)
        dummy = np.zeros((1, 3, 640, 640), dtype=np.float32)
        res = compiled([dummy])
        _ = self._extract_ov_output(compiled, res)
        exec_dev = device_name
        try:
            prop = compiled.get_property("EXECUTION_DEVICES")
            if isinstance(prop, (list, tuple)) and prop:
                exec_dev = "+".join(str(p) for p in prop)
            elif prop:
                exec_dev = str(prop)
        except Exception:
            pass
        return compiled, exec_dev

    def _resolve_model_candidate_paths(self) -> tuple[Optional[Path], Optional[Path]]:
        """Resolve (xml_path, onnx_path) from `self.model_path`."""
        xml_path: Optional[Path] = None
        onnx_path: Optional[Path] = None
        if not self.model_path:
            return None, None

        if self.model_path.is_file():
            suf = self.model_path.suffix.lower()
            if suf == ".xml":
                xml_path = self.model_path
                cand_onnx = self.model_path.with_suffix(".onnx")
                if cand_onnx.is_file():
                    onnx_path = cand_onnx
            elif suf == ".onnx":
                onnx_path = self.model_path
                cand_xml = self.model_path.with_suffix(".xml")
                if cand_xml.is_file():
                    xml_path = cand_xml
        elif self.model_path.is_dir():
            xml_candidates = sorted(self.model_path.glob("*.xml"))
            if xml_candidates:
                xml_path = xml_candidates[0]
            onnx_candidates = sorted(self.model_path.glob("*.onnx"))
            if onnx_candidates:
                onnx_path = onnx_candidates[0]
        else:
            # Check sibling .onnx if model_path points to non-existent dir `models/yolov8n_openvino_model`
            parent_onnx = self.model_path.parent / "yolov8n.onnx"
            if parent_onnx.is_file():
                onnx_path = parent_onnx

        return xml_path, onnx_path

    def _init_detector(self) -> None:
        # 1. Try native OpenVINO Runtime on .xml IR or .onnx model (with warmup & safe CPU fallback)
        xml_path, onnx_path = self._resolve_model_candidate_paths()
        ov_source_path = xml_path or onnx_path

        if ov_source_path is not None:
            try:
                ov = _safe_import_openvino()

                core = ov.Core()
                ov_model = core.read_model(str(ov_source_path))
                # If loaded from .onnx and .xml doesn't exist yet, cache FP16 OpenVINO IR on disk
                if xml_path is None and onnx_path is not None and hasattr(ov, "save_model"):
                    try:
                        target_xml = onnx_path.with_suffix(".xml")
                        ov.save_model(ov_model, str(target_xml), compress_to_fp16=True)
                    except Exception:
                        pass

                try:
                    compiled, exec_dev = self._compile_and_warmup_ov(core, ov_model, self.openvino_device)
                    self._compiled_ov = compiled
                    self._backend_name = f"openvino_ir({exec_dev})"
                    logger.info("Compiled & warmed up OpenVINO model %s on %s (requested=%s)", ov_source_path.name, exec_dev, self.openvino_device)
                    return
                except Exception as primary_exc:
                    if self.openvino_device.upper() != "CPU":
                        logger.warning(
                            "OpenVINO device '%s' failed compile/warmup (%s); falling back to CPU",
                            self.openvino_device,
                            primary_exc,
                        )
                        compiled, exec_dev = self._compile_and_warmup_ov(core, ov_model, "CPU")
                        self._compiled_ov = compiled
                        self._backend_name = f"openvino_ir({exec_dev}<-{self.openvino_device})"
                        logger.info("Compiled & warmed up OpenVINO model %s on fallback CPU", ov_source_path.name)
                        return
                    raise primary_exc
            except Exception as exc:
                self._last_error = f"init_ov: {type(exc).__name__}: {exc}"
                logger.warning("OpenVINO load skipped (%s)", exc)

        # 2. Try ONNX Runtime on .onnx model if available
        if onnx_path is not None and onnx_path.is_file():
            try:
                import onnxruntime as ort

                opts = ort.SessionOptions()
                opts.intra_op_num_threads = max(1, int(getattr(self, "cpu_threads", 2)))
                opts.inter_op_num_threads = 1
                sess = ort.InferenceSession(str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"])
                inp_name = sess.get_inputs()[0].name
                dummy = np.zeros((1, 3, 640, 640), dtype=np.float32)
                _ = sess.run(None, {inp_name: dummy})
                self._ort_session = sess
                self._ort_input_name = inp_name
                self._backend_name = "onnxruntime_cpu"
                self._last_error = None
                logger.info("Initialized ONNX Runtime YOLOv8n detector from %s", onnx_path.name)
                return
            except Exception as exc:
                self._last_error = f"init_ort: {type(exc).__name__}: {exc}"
                logger.warning("ONNX Runtime load skipped (%s)", exc)

        # 3. Try Ultralytics YOLO wrapper if available
        if self.model_path and self.model_path.exists():
            try:
                from ultralytics import YOLO

                self._yolo_model = YOLO(str(self.model_path), task="detect")
                self._backend_name = "ultralytics_openvino"
                return
            except Exception:
                pass

        # 4. Lightweight built-in OpenCV HOG fallback (OpenCV 4.x)
        if hasattr(cv2, "HOGDescriptor"):
            self._hog = cv2.HOGDescriptor()
            self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self._backend_name = "opencv_hog_fallback"
            return

        # Do NOT activate MOG2 background subtraction by default on real camera streams,
        # because IR night-vision noise and moving foliage generate dozens of fake 60% detections.
        self._bg_sub = None
        self._backend_name = "model_missing"
        logger.warning(
            "YOLOv8n OpenVINO/ONNX model not found at %s (run `python tools/download_yolo_openvino_model.py`). "
            "MOG2 motion fallback is disabled to prevent false-positive detections.",
            self.model_path,
        )

    def set_target_fps(self, fps: float) -> None:
        clamped = max(0.25, float(fps))
        self._target_fps = clamped
        self.frame_interval_s = 1.0 / clamped

    def get_target_fps(self) -> float:
        return float(getattr(self, "_target_fps", 1.0 / max(self.frame_interval_s, 1e-3)))

    def get_runtime_stats(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "rtsp_connected": self._rtsp_connected,
            "backend": self._backend_name,
            "target_fps": round(self.get_target_fps(), 3),
            "frames_read": self._frames_read,
            "frames_inferred": self._frames_inferred,
            "raw_detections_total": self._raw_detections_total,
            "last_infer_ms": round(self._last_infer_ms, 2),
            "infer_ms_ema": round(self._infer_ms_ema, 2),
            "reconnect_count": self._reconnect_count,
            "mean_luma": round(self._mean_luma, 1),
            "mean_saturation": round(self._mean_saturation, 1),
            "is_night_ir": self._is_night_ir,
            "last_error": self._last_error,
        }

    def status_details(self) -> str:
        rtsp_state = "rtsp=ok" if self._rtsp_connected else "rtsp=waiting"
        cam_id = getattr(self, "camera_id", None)
        prefix = f"openvino:{cam_id}" if cam_id else "openvino"
        base = f"{prefix} [{self._backend_name}] ({rtsp_state}, frames={self._frames_inferred}, raw_det={self._raw_detections_total})"
        if self._last_error:
            base += f" err={self._last_error[:80]}"
        return base

    def _open_capture(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def get_latest_frame(self) -> Optional[tuple[np.ndarray, float]]:
        """Return a copy of the latest decoded substream frame and timestamp, if available."""
        lock = getattr(self, "_latest_frame_lock", None)
        if lock is None:
            return None
        with lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy(), self._latest_frame_ts

    async def start(self, on_batch: DetectionBatchCallback) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._capture_loop(on_batch))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        lock = getattr(self, "_latest_frame_lock", None)
        if lock is not None:
            with lock:
                self._latest_frame = None
                self._latest_frame_ts = 0.0

    async def _capture_loop(self, on_batch: DetectionBatchCallback) -> None:
        loop = asyncio.get_running_loop()
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay")
        cap: Optional[cv2.VideoCapture] = None
        warned_unavailable = False
        last_infer_t = 0.0
        last_heartbeat_t = 0.0

        while self._running:
            try:
                if cap is None or not cap.isOpened():
                    cap = await loop.run_in_executor(self._executor, self._open_capture)
                    if not cap.isOpened():
                        self._rtsp_connected = False
                        self._last_error = f"RTSP unavailable at {self.rtsp_url}"
                        if not warned_unavailable:
                            logger.warning("RTSP stream unavailable at %s; retrying every 3s", self.rtsp_url)
                            warned_unavailable = True
                        cap.release()
                        cap = None
                        await asyncio.sleep(3.0)
                        continue
                    if self._has_connected_once:
                        self._reconnect_count += 1
                    self._has_connected_once = True
                    self._rtsp_connected = True
                    warned_unavailable = False
                    self._last_error = None
                    logger.info("RTSP stream connected at %s (backend=%s)", self.rtsp_url, self._backend_name)

                grabbed = await loop.run_in_executor(self._executor, cap.grab)
                if not grabbed:
                    self._rtsp_connected = False
                    logger.warning("RTSP stream read/grab failed at %s; reconnecting...", self.rtsp_url)
                    cap.release()
                    cap = None
                    await asyncio.sleep(1.5)
                    continue

                self._frames_read += 1
                self._last_frame_ts = time.time()
                now_mono = time.monotonic()
                if now_mono - last_infer_t < self.frame_interval_s:
                    await asyncio.sleep(0)
                    continue

                ok, frame = await loop.run_in_executor(self._executor, cap.retrieve)
                if not ok or frame is None:
                    self._rtsp_connected = False
                    cap.release()
                    cap = None
                    await asyncio.sleep(1.5)
                    continue

                now_frame_ts = time.time()
                lock = getattr(self, "_latest_frame_lock", None)
                if lock is not None:
                    with lock:
                        self._latest_frame = frame.copy()
                        self._latest_frame_ts = now_frame_ts

                t_infer_start = time.perf_counter()
                events = await loop.run_in_executor(self._executor, self._infer_frame, frame, now_frame_ts)
                infer_ms = (time.perf_counter() - t_infer_start) * 1000.0
                self._last_infer_ms = infer_ms
                self._infer_ms_ema = infer_ms if self._infer_ms_ema <= 0.0 else (0.8 * self._infer_ms_ema + 0.2 * infer_ms)
                self._frames_inferred += 1
                self._raw_detections_total += len(events)
                if self._frames_inferred == 1 or (self._frames_inferred % 10 == 0):
                    try:
                        small = cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA)
                        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                        self._mean_saturation = float(hsv[:, :, 1].mean())
                        self._mean_luma = float(hsv[:, :, 2].mean())
                        self._is_night_ir = self._mean_saturation < 14.0
                    except Exception:
                        pass
                self._last_error = None
                last_infer_t = time.monotonic()

                if events:
                    last_heartbeat_t = last_infer_t
                    await on_batch(events)
                elif last_infer_t - last_heartbeat_t >= 1.0:
                    last_heartbeat_t = last_infer_t
                    await on_batch([])

                await asyncio.sleep(0.005)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._rtsp_connected = False
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Error in OpenVINO RTSP capture/inference loop: %s", exc)
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                await asyncio.sleep(2.0)

        if cap is not None:
            cap.release()
            self._rtsp_connected = False

    def _effective_global_min_conf(self) -> float:
        policy = getattr(self, "reconstruction_policy", None)
        if policy is None:
            return float(self.conf_threshold)
        return float(policy.min_detection_conf_floor())

    def _allows_2d_detection(self, label: str, conf: float) -> bool:
        policy = getattr(self, "reconstruction_policy", None)
        if policy is None:
            return float(conf) >= float(self.conf_threshold)
        rule = policy.rule_for(label)
        return bool(rule.enabled and float(conf) >= float(rule.min_detection_conf_threshold))

    def _infer_frame(self, frame: np.ndarray, ts: float) -> list[DetectionEvent]:
        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return []

        if self._yolo_model is not None:
            min_conf = self._effective_global_min_conf()
            results = self._yolo_model.predict(frame, imgsz=640, conf=min_conf, verbose=False)
            events: list[DetectionEvent] = []
            for r in results:
                for box in r.boxes:
                    cls_idx = int(box.cls[0])
                    label = COCO_TO_DOMAIN.get(cls_idx)
                    if not label:
                        continue
                    conf_val = float(box.conf[0])
                    if not self._allows_2d_detection(label, conf_val):
                        continue
                    x1, y1, x2, y2 = [float(v) for v in box.xyxyn[0]]
                    events.append(
                        DetectionEvent(
                            camera_id=self.camera_id,
                            timestamp=ts,
                            class_label=label,  # type: ignore[arg-type]
                            confidence=conf_val,
                            bbox=BoundingBox2D(
                                x_min=min(max(x1, 0.0), 1.0),
                                y_min=min(max(y1, 0.0), 1.0),
                                x_max=min(max(x2, 0.0), 1.0),
                                y_max=min(max(y2, 0.0), 1.0),
                            ),
                        )
                    )
            return deduplicate_2d_detections(events)

        if self._compiled_ov is not None or getattr(self, "_ort_session", None) is not None:
            return deduplicate_2d_detections(self._infer_openvino_yolo(frame, ts))

        if self._hog is not None:
            # OpenCV HOG fallback (persons)
            resized = cv2.resize(frame, (640, 360))
            rects, weights = self._hog.detectMultiScale(resized, winStride=(8, 8), padding=(8, 8), scale=1.08)
            events = []
            for (rx, ry, rw, rh), weight in zip(rects, weights):
                conf = float(min(0.95, max(0.45, float(weight) * 0.55)))
                if conf < 0.50 or not self._allows_2d_detection("person", conf):
                    continue
                events.append(
                    DetectionEvent(
                        camera_id=self.camera_id,
                        timestamp=ts,
                        class_label="person",
                        confidence=conf,
                        bbox=BoundingBox2D(
                            x_min=max(0.0, rx / 640.0),
                            y_min=max(0.0, ry / 360.0),
                            x_max=min(1.0, (rx + rw) / 640.0),
                            y_max=min(1.0, (ry + rh) / 360.0),
                        ),
                    )
                )
            return events

        if self._bg_sub is not None:
            return self._infer_mog2_motion(frame, ts)

        return []

    def _infer_mog2_motion(self, frame: np.ndarray, ts: float) -> list[DetectionEvent]:
        resized = cv2.resize(frame, (640, 360))
        fg_mask = self._bg_sub.apply(resized)
        self._mog2_warmup += 1
        if self._mog2_warmup < 15:
            return []

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        cleaned = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        cleaned = cv2.dilate(cleaned, kernel, iterations=2)
        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        events: list[DetectionEvent] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 1200.0 or area > 120000.0:
                continue
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            if rw < 14 or rh < 24:
                continue
            label = "car" if (rw > rh * 1.35 and area > 4500.0) else "person"
            events.append(
                DetectionEvent(
                    camera_id=self.camera_id,
                    timestamp=ts,
                    class_label=label,  # type: ignore[arg-type]
                    confidence=0.60,
                    bbox=BoundingBox2D(
                        x_min=max(0.0, rx / 640.0),
                        y_min=max(0.0, ry / 360.0),
                        x_max=min(1.0, (rx + rw) / 640.0),
                        y_max=min(1.0, (ry + rh) / 360.0),
                    ),
                )
            )
        return events

    def _infer_openvino_yolo(self, frame: np.ndarray, ts: float) -> list[DetectionEvent]:
        blob, pad_left, pad_top, new_w, new_h = self._letterbox_bgr(frame, 640)
        img = cv2.cvtColor(blob, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        inp = np.ascontiguousarray(np.transpose(img, (2, 0, 1))[None, ...], dtype=np.float32)
        lock = getattr(self, "_infer_lock", None)
        ort_sess = getattr(self, "_ort_session", None)
        if self._compiled_ov is not None:
            if lock is not None:
                with lock:
                    raw_result = self._compiled_ov([inp])
            else:
                raw_result = self._compiled_ov([inp])
            output = self._extract_ov_output(self._compiled_ov, raw_result)  # Expected shape (1, 84, 8400) for YOLOv8/11
        elif ort_sess is not None:
            inp_name = getattr(self, "_ort_input_name", None) or ort_sess.get_inputs()[0].name
            if lock is not None:
                with lock:
                    raw_ort = ort_sess.run(None, {inp_name: inp})[0]
            else:
                raw_ort = ort_sess.run(None, {inp_name: inp})[0]
            output = np.asarray(raw_ort)
        else:
            return []
        if output.ndim == 3:
            raw = output[0]
            preds = raw.T if raw.shape[0] < raw.shape[1] else raw
        elif output.ndim == 2:
            preds = output.T if output.shape[0] < output.shape[1] else output
        else:
            return []
        if preds.ndim != 2 or preds.shape[1] < 84:
            return []

        min_conf = self._effective_global_min_conf()
        scores_mat = preds[:, 4:]
        class_ids = np.argmax(scores_mat, axis=1)
        confs = scores_mat[np.arange(len(preds)), class_ids]
        mask = confs >= min_conf
        if not np.any(mask):
            return []

        boxes = preds[mask, :4]
        filt_ids = class_ids[mask]
        filt_confs = confs[mask]

        xyxy = []
        for cx, cy, bw, bh in boxes:
            xyxy.append([float(cx - bw * 0.5), float(cy - bh * 0.5), float(bw), float(bh)])
        keep = cv2.dnn.NMSBoxes(xyxy, filt_confs.tolist(), score_threshold=min_conf, nms_threshold=0.45)

        events: list[DetectionEvent] = []
        for idx in (keep.flatten() if len(keep) > 0 else []):
            label = COCO_TO_DOMAIN.get(int(filt_ids[idx]))
            if not label:
                continue
            conf_val = float(filt_confs[idx])
            if not self._allows_2d_detection(label, conf_val):
                continue
            bx, by, bw, bh = xyxy[idx]
            x1 = min(max((bx - pad_left) / new_w, 0.0), 1.0)
            y1 = min(max((by - pad_top) / new_h, 0.0), 1.0)
            x2 = min(max((bx + bw - pad_left) / new_w, 0.0), 1.0)
            y2 = min(max((by + bh - pad_top) / new_h, 0.0), 1.0)
            if x2 <= x1 or y2 <= y1:
                continue
            events.append(
                DetectionEvent(
                    camera_id=self.camera_id,
                    timestamp=ts,
                    class_label=label,  # type: ignore[arg-type]
                    confidence=float(filt_confs[idx]),
                    bbox=BoundingBox2D(
                        x_min=x1,
                        y_min=y1,
                        x_max=x2,
                        y_max=y2,
                    ),
                )
            )
        return deduplicate_2d_detections(events)

