from __future__ import annotations

import asyncio
import math
import time
from typing import Callable, Optional

from spatial_server.domain.models import BoundingBox2D, DetectionEvent
from spatial_server.optics.interfaces import ICameraOpticalModel
from .interfaces import DetectionBatchCallback, IDetectionSource


class SyntheticWalkSimulatorSource(IDetectionSource):
    """
    Emits realistic 10 Hz DetectionEvent batches (person + vehicle) through the configured
    optical model so raycasting, Kalman 3D tracking, SQLite WAL & 60fps UI can be tested live
    without physical movement in front of the camera.
    """

    mode_name = "synthetic"

    def __init__(
        self,
        camera_id: str = "Cam_Carraio",
        optical_model_getter: Optional[Callable[[str], Optional[ICameraOpticalModel]]] = None,
        rate_hz: float = 10.0,
    ) -> None:
        self.camera_id = camera_id
        self.optical_model_getter = optical_model_getter
        self.interval_s = 1.0 / max(rate_hz, 1.0)
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self, on_batch: DetectionBatchCallback) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(on_batch))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _project_or_uv(
        self,
        world_pt: tuple[float, float, float],
        fallback_uv: tuple[float, float],
    ) -> tuple[float, float]:
        if self.optical_model_getter is not None:
            model = self.optical_model_getter(self.camera_id)
            if model is not None:
                uv = model.world_point_to_pixel(world_pt)
                if uv is not None and 0.05 <= uv[0] <= 0.95 and 0.15 <= uv[1] <= 0.95:
                    return uv
        return fallback_uv

    async def _run_loop(self, on_batch: DetectionBatchCallback) -> None:
        t0 = time.monotonic()
        while self._running:
            now_unix = time.time()
            elapsed = time.monotonic() - t0
            phase = elapsed * 0.35

            # Entity 1: Person ("Nicola") walking smoothly back and forth
            person_u_fb = 0.50 + 0.24 * math.sin(phase)
            person_v_fb = 0.72 + 0.11 * math.cos(phase * 0.7)
            px_w = -3.0 + 1.8 * math.sin(phase)
            pz_w = 8.5 - 5.5 * math.cos(phase * 0.7)
            pu, pv = self._project_or_uv((px_w, 0.0, pz_w), (person_u_fb, person_v_fb))

            pw, ph = 0.055, 0.18
            person_evt = DetectionEvent(
                camera_id=self.camera_id,
                timestamp=now_unix,
                class_label="person",
                confidence=0.94,
                bbox=BoundingBox2D(
                    x_min=max(0.0, pu - pw * 0.5),
                    y_min=max(0.0, pv - ph),
                    x_max=min(1.0, pu + pw * 0.5),
                    y_max=min(1.0, pv),
                ),
                sub_label="Nicola",
                face_confidence=0.91,
            )

            batch: list[DetectionEvent] = [person_evt]

            # Entity 2: Car entering periodically
            car_cycle = (elapsed % 30.0) / 30.0
            if 0.15 <= car_cycle <= 0.85:
                prog = (car_cycle - 0.15) / 0.70
                cu_fb = 0.28 + 0.35 * prog
                cv_fb = 0.82 - 0.18 * math.sin(prog * math.pi)
                cx_w = -2.6 - 0.8 * prog
                cz_w = 17.5 - 12.0 * prog
                cu, cv = self._project_or_uv((cx_w, 0.0, cz_w), (cu_fb, cv_fb))
                cw, ch = 0.18, 0.22
                batch.append(
                    DetectionEvent(
                        camera_id=self.camera_id,
                        timestamp=now_unix,
                        class_label="car",
                        confidence=0.91,
                        bbox=BoundingBox2D(
                            x_min=max(0.0, cu - cw * 0.5),
                            y_min=max(0.0, cv - ch),
                            x_max=min(1.0, cu + cw * 0.5),
                            y_max=min(1.0, cv),
                        ),
                    )
                )

            await on_batch(batch)
            await asyncio.sleep(self.interval_s)

