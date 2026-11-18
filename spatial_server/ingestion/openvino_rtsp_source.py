from __future__ import annotations

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
import cv2
import numpy as np

from spatial_server.domain.models import BoundingBox2D, DetectionEvent
from .interfaces import DetectionBatchCallback, IDetectionSource

logger = logging.getLogger(__name__)

COCO_TO_DOMAIN = {
    0: "person",
    1: "bicycle",
    2: "car",
    7: "truck",
    16: "dog",
}


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
    ) -> None:
        self.rtsp_url = rtsp_url
        self.camera_id = camera_id
        self.openvino_device = openvino_device
        self.model_path = Path(model_path) if model_path else None
        self.frame_interval_s = 1.0 / max(target_fps, 1.0)

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rtsp-cv")
        self._backend_name = "initializing"
        self._compiled_ov = None
        self._yolo_model = None
        self._hog = None
        self._bg_sub = None
        self._mog2_warmup = 0
        self._init_detector()

    def _init_detector(self) -> None:
        # 1. Try native OpenVINO Runtime IR model
        xml_path = None
        if self.model_path:
            if self.model_path.is_file() and self.model_path.suffix == ".xml":
                xml_path = self.model_path
            elif self.model_path.is_dir():
                xml_candidates = list(self.model_path.glob("*.xml"))
                if xml_candidates:
                    xml_path = xml_candidates[0]

        if xml_path is not None:
            try:
                import openvino as ov

                core = ov.Core()
                ov_model = core.read_model(str(xml_path))
                self._compiled_ov = core.compile_model(ov_model, self.openvino_device)
                self._backend_name = f"openvino_ir({self.openvino_device})"
                logger.info("Compiled OpenVINO model %s on %s", xml_path.name, self.openvino_device)
                return
            except Exception as exc:
                logger.warning("OpenVINO IR load skipped (%s)", exc)

        # 2. Try Ultralytics YOLO wrapper if available
        if self.model_path and self.model_path.exists():
            try:
                from ultralytics import YOLO

                self._yolo_model = YOLO(str(self.model_path), task="detect")
                self._backend_name = "ultralytics_openvino"
                return
            except Exception:
                pass

        # 3. Lightweight built-in OpenCV HOG fallback (OpenCV 4.x)
        if hasattr(cv2, "HOGDescriptor"):
            self._hog = cv2.HOGDescriptor()
            self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self._backend_name = "opencv_hog_fallback"
            return

        # 4. OpenCV 5.x fallback: lightweight MOG2 motion detector until yolov8n_openvino_model is added
        self._bg_sub = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=36, detectShadows=False)
        self._backend_name = "opencv_mog2_fallback"
        logger.warning(
            "OpenVINO YOLO model not found at %s and cv2.HOGDescriptor unavailable; using MOG2 motion fallback.",
            self.model_path,
        )

    def status_details(self) -> str:
        return f"openvino [{self._backend_name}]"

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

    async def _capture_loop(self, on_batch: DetectionBatchCallback) -> None:
        loop = asyncio.get_running_loop()
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        cap: Optional[cv2.VideoCapture] = None

        while self._running:
            if cap is None or not cap.isOpened():
                cap = await loop.run_in_executor(self._executor, lambda: cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG))
                if not cap.isOpened():
                    logger.debug("RTSP stream unavailable at %s; retrying in 3s", self.rtsp_url)
                    cap.release()
                    cap = None
                    await asyncio.sleep(3.0)
                    continue

            t_start = time.monotonic()
            ok, frame = await loop.run_in_executor(self._executor, cap.read)
            if not ok or frame is None:
                cap.release()
                cap = None
                await asyncio.sleep(1.5)
                continue

            events = await loop.run_in_executor(self._executor, self._infer_frame, frame, time.time())
            if events:
                await on_batch(events)

            elapsed = time.monotonic() - t_start
            sleep_s = max(0.01, self.frame_interval_s - elapsed)
            await asyncio.sleep(sleep_s)

        if cap is not None:
            cap.release()

    def _infer_frame(self, frame: np.ndarray, ts: float) -> list[DetectionEvent]:
        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return []

        if self._yolo_model is not None:
            results = self._yolo_model.predict(frame, imgsz=640, conf=0.45, verbose=False)
            events: list[DetectionEvent] = []
            for r in results:
                for box in r.boxes:
                    cls_idx = int(box.cls[0])
                    label = COCO_TO_DOMAIN.get(cls_idx)
                    if not label:
                        continue
                    x1, y1, x2, y2 = [float(v) for v in box.xyxyn[0]]
                    events.append(
                        DetectionEvent(
                            camera_id=self.camera_id,
                            timestamp=ts,
                            class_label=label,  # type: ignore[arg-type]
                            confidence=float(box.conf[0]),
                            bbox=BoundingBox2D(
                                x_min=min(max(x1, 0.0), 1.0),
                                y_min=min(max(y1, 0.0), 1.0),
                                x_max=min(max(x2, 0.0), 1.0),
                                y_max=min(max(y2, 0.0), 1.0),
                            ),
                        )
                    )
            return events

        if self._compiled_ov is not None:
            return self._infer_openvino_yolo(frame, ts)

        if self._hog is not None:
            # OpenCV HOG fallback (persons)
            resized = cv2.resize(frame, (640, 360))
            rects, weights = self._hog.detectMultiScale(resized, winStride=(8, 8), padding=(8, 8), scale=1.08)
            events = []
            for (rx, ry, rw, rh), weight in zip(rects, weights):
                conf = float(min(0.95, max(0.45, float(weight) * 0.55)))
                if conf < 0.50:
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
        blob = cv2.resize(frame, (640, 640))
        img = cv2.cvtColor(blob, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        inp = np.transpose(img, (2, 0, 1))[None, ...]
        output = self._compiled_ov([inp])[0]  # Expected shape (1, 84, 8400) for YOLOv8/11
        preds = np.squeeze(output).T  # (8400, 84)
        if preds.ndim != 2 or preds.shape[1] < 84:
            return []

        scores_mat = preds[:, 4:]
        class_ids = np.argmax(scores_mat, axis=1)
        confs = scores_mat[np.arange(len(preds)), class_ids]
        mask = confs >= 0.45
        if not np.any(mask):
            return []

        boxes = preds[mask, :4]
        filt_ids = class_ids[mask]
        filt_confs = confs[mask]

        xyxy = []
        for cx, cy, bw, bh in boxes:
            xyxy.append([float(cx - bw * 0.5), float(cy - bh * 0.5), float(bw), float(bh)])
        keep = cv2.dnn.NMSBoxes(xyxy, filt_confs.tolist(), score_threshold=0.45, nms_threshold=0.50)

        events: list[DetectionEvent] = []
        for idx in (keep.flatten() if len(keep) > 0 else []):
            label = COCO_TO_DOMAIN.get(int(filt_ids[idx]))
            if not label:
                continue
            bx, by, bw, bh = xyxy[idx]
            events.append(
                DetectionEvent(
                    camera_id=self.camera_id,
                    timestamp=ts,
                    class_label=label,  # type: ignore[arg-type]
                    confidence=float(filt_confs[idx]),
                    bbox=BoundingBox2D(
                        x_min=min(max(bx / 640.0, 0.0), 1.0),
                        y_min=min(max(by / 640.0, 0.0), 1.0),
                        x_max=min(max((bx + bw) / 640.0, 0.0), 1.0),
                        y_max=min(max((by + bh) / 640.0, 0.0), 1.0),
                    ),
                )
            )
        return events

