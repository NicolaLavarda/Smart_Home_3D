from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional
import aiomqtt

from spatial_server.domain.models import BoundingBox2D, DetectionEvent
from .interfaces import DetectionBatchCallback, IDetectionSource

logger = logging.getLogger(__name__)

VALID_LABELS = {"person", "car", "truck", "bicycle", "dog"}


class MqttFrigateDetectionSource(IDetectionSource):
    """
    Async MQTT subscriber for external object detections (Frigate NVR `frigate/events`
    or custom Home Assistant / YOLO JSON messages).
    """

    mode_name = "mqtt"

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str = "",
        password: str = "",
        topic: str = "frigate/events",
        default_camera_id: str = "Cam_Carraio",
        camera_alias_map: Optional[dict[str, str]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username or None
        self.password = password or None
        self.topic = topic
        self.default_camera_id = default_camera_id
        self.camera_alias_map = camera_alias_map or {
            "carraio": "Cam_Carraio",
            "camera.carraio": "Cam_Carraio",
            "camera.carraio_scorrevole": "Cam_Carraio",
            "carraio_scorrevole": "Cam_Carraio",
            "carraio_main": "Cam_Carraio",
            "carraio_sub": "Cam_Carraio",
            "Cam_Carraio": "Cam_Carraio",
            "portico": "Cam_Portico",
            "camera.portico": "Cam_Portico",
            "camera.portico_scorrevole": "Cam_Portico",
            "portico_scorrevole": "Cam_Portico",
            "portico_main": "Cam_Portico",
            "portico_sub": "Cam_Portico",
            "Cam_Portico": "Cam_Portico",
        }
        self._alias_map_lower = {k.lower(): v for k, v in self.camera_alias_map.items()}
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._last_status = "idle"

    def _resolve_camera_id(self, raw_camera: str) -> str:
        key = str(raw_camera or "").strip()
        if not key:
            return self.default_camera_id
        if key in self.camera_alias_map:
            return self.camera_alias_map[key]
        return self._alias_map_lower.get(key.lower(), self.default_camera_id)

    def status_details(self) -> str:
        return f"mqtt ({self._last_status})"

    async def start(self, on_batch: DetectionBatchCallback) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._consume_loop(on_batch))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _consume_loop(self, on_batch: DetectionBatchCallback) -> None:
        backoff = 2.0
        while self._running:
            try:
                self._last_status = f"connecting {self.host}:{self.port}"
                async with aiomqtt.Client(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                ) as client:
                    await client.subscribe(self.topic)
                    self._last_status = f"connected {self.topic}"
                    backoff = 2.0

                    async for message in client.messages:
                        if not self._running:
                            break
                        evt = self._parse_payload(message.payload)
                        if evt is not None:
                            await on_batch([evt])
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._last_status = f"reconnecting ({exc})"
                logger.warning("MQTT connection error on %s:%s: %s", self.host, self.port, exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.8, 30.0)

    def _parse_payload(self, raw: bytes | str) -> Optional[DetectionEvent]:
        try:
            data = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
        except Exception:
            return None

        # Frigate NVR `frigate/events` structure
        if "after" in data and isinstance(data["after"], dict):
            after = data["after"]
            if data.get("type") == "end":
                return None
            label = str(after.get("label", "")).lower()
            if label not in VALID_LABELS:
                return None
            box = after.get("box") or []
            if len(box) != 4:
                return None
            cam_raw = str(after.get("camera", self.default_camera_id))
            cam_id = self._resolve_camera_id(cam_raw)
            x1, y1, x2, y2 = [float(v) for v in box]
            if max(x1, y1, x2, y2) > 1.5:
                # Frigate relative vs pixel fallback
                w = float(after.get("frame_width", 1920))
                h = float(after.get("frame_height", 1080))
                x1, y1, x2, y2 = x1 / w, y1 / h, x2 / w, y2 / h

            sub_label = after.get("sub_label")
            if isinstance(sub_label, list) and sub_label:
                sub_label = str(sub_label[0])
            elif sub_label is not None:
                sub_label = str(sub_label)

            return DetectionEvent(
                camera_id=cam_id,
                timestamp=float(after.get("frame_time") or time.time()),
                class_label=label,  # type: ignore[arg-type]
                confidence=float(after.get("top_score") or after.get("score") or 0.8),
                bbox=BoundingBox2D(
                    x_min=min(max(x1, 0.0), 1.0),
                    y_min=min(max(y1, 0.0), 1.0),
                    x_max=min(max(x2, 0.0), 1.0),
                    y_max=min(max(y2, 0.0), 1.0),
                ),
                sub_label=sub_label,
            )

        # Generic flat detection schema
        label = str(data.get("class_label", "")).lower()
        box = data.get("bbox")
        if label in VALID_LABELS and isinstance(box, list) and len(box) == 4:
            x1, y1, x2, y2 = [min(max(float(v), 0.0), 1.0) for v in box]
            raw_cam = str(data.get("camera_id", self.default_camera_id))
            resolved_cam = self._resolve_camera_id(raw_cam) if raw_cam.lower() in self._alias_map_lower else raw_cam
            return DetectionEvent(
                camera_id=resolved_cam,
                timestamp=float(data.get("timestamp") or time.time()),
                class_label=label,  # type: ignore[arg-type]
                confidence=float(data.get("confidence", 0.85)),
                bbox=BoundingBox2D(x_min=x1, y_min=y1, x_max=x2, y_max=y2),
                sub_label=data.get("sub_label"),
                face_confidence=data.get("face_confidence"),
            )
        return None

