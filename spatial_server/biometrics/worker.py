from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable, Optional

from spatial_server.domain.models import BoundingBox2D
from .consensus import TrackBiometricConsensusManager
from .interfaces import (
    IBiometricCoordinator,
    IFaceRecognizer,
    IFrameSnapshotProvider,
    IPlateRecognizer,
)
from .models import BiometricJob, TrackBiometricUpdate

logger = logging.getLogger("spatial_server.biometrics.worker")

ResultCallback = Callable[[TrackBiometricUpdate], Awaitable[None]]

VEHICLE_CLASSES = frozenset({"car", "truck", "motorbike"})


class TrackCoalescingQueue:
    """
    Bounded async queue keyed by `(track_id, modality)`.
    Coalesces newer observations for an already-queued track in-place and applies
    drop-oldest backpressure when distinct track demand exceeds `maxsize`.
    """

    def __init__(self, maxsize: int = 8) -> None:
        self.maxsize = max(1, int(maxsize))
        self._items: OrderedDict[tuple[int, str], BiometricJob] = OrderedDict()
        self._event = asyncio.Event()
        self.enqueued_count: int = 0
        self.coalesced_count: int = 0
        self.dropped_count: int = 0

    def __len__(self) -> int:
        return len(self._items)

    def put_nowait(self, job: BiometricJob) -> bool:
        key = (job.track_id, job.modality)
        if key in self._items:
            self._items[key] = job
            self._items.move_to_end(key, last=True)
            self.coalesced_count += 1
            self._event.set()
            return True

        if len(self._items) >= self.maxsize:
            self._items.popitem(last=False)
            self.dropped_count += 1

        self._items[key] = job
        self.enqueued_count += 1
        self._event.set()
        return True

    async def get(self) -> BiometricJob:
        while not self._items:
            self._event.clear()
            if self._items:
                break
            await self._event.wait()
        _key, job = self._items.popitem(last=False)
        if not self._items:
            self._event.clear()
        return job

    def clear(self) -> None:
        self._items.clear()
        self._event.clear()


class BiometricEligibilityGate:
    """Determines whether a tracked 3D entity should trigger an on-demand high-res snapshot."""

    def __init__(
        self,
        *,
        face_enabled: bool = True,
        alpr_enabled: bool = True,
        face_max_range_m: float = 8.0,
        alpr_max_range_m: float = 13.0,
        panoramic_edge_margin_u: float = 0.15,
        camera_rules: Optional[dict[str, dict[str, float]]] = None,
    ) -> None:
        self.face_enabled = bool(face_enabled)
        self.alpr_enabled = bool(alpr_enabled)
        self.face_max_range_m = float(face_max_range_m)
        self.alpr_max_range_m = float(alpr_max_range_m)
        self.panoramic_edge_margin_u = max(0.0, min(0.45, float(panoramic_edge_margin_u)))
        self.camera_rules = dict(camera_rules or {})

    def _max_range_for(self, camera_id: str, modality: str) -> float:
        cam_cfg = self.camera_rules.get(camera_id)
        if cam_cfg and modality in cam_cfg:
            return float(cam_cfg[modality])
        return self.face_max_range_m if modality == "face" else self.alpr_max_range_m

    def evaluate(
        self,
        job: BiometricJob,
        consensus: TrackBiometricConsensusManager,
    ) -> tuple[bool, float]:
        if job.class_label == "person":
            if not self.face_enabled:
                return False, 0.0
            modality = "face"
            min_w, min_h = 0.015, 0.035
        elif job.class_label in VEHICLE_CLASSES:
            if not self.alpr_enabled:
                return False, 0.0
            modality = "alpr"
            min_w, min_h = 0.035, 0.025
        else:
            return False, 0.0

        if consensus.is_locked(job.track_id, modality):
            return False, 0.0
        if not consensus.can_attempt(job.track_id, modality, now_ts=job.timestamp):
            return False, 0.0

        if job.obs_range_m > self._max_range_for(job.camera_id, modality):
            return False, 0.0

        bw = float(job.bbox.x_max - job.bbox.x_min)
        bh = float(job.bbox.y_max - job.bbox.y_min)
        if bw < min_w or bh < min_h:
            return False, 0.0

        u_center = 0.5 * (float(job.bbox.x_min) + float(job.bbox.x_max))
        if job.is_panoramic_180:
            if u_center < self.panoramic_edge_margin_u or u_center > (1.0 - self.panoramic_edge_margin_u):
                return False, 0.0
            return True, min(job.camera_weight, 0.75)

        return True, job.camera_weight


class BiometricWorkerService(IBiometricCoordinator):
    """
    Single-worker bounded background coordinator decoupling RTSP/Kalman tracking
    from snapshot fetch and Face/ALPR ONNX inference.
    """

    def __init__(
        self,
        *,
        snapshot_provider: IFrameSnapshotProvider,
        consensus: TrackBiometricConsensusManager,
        gate: BiometricEligibilityGate,
        face_recognizer: Optional[IFaceRecognizer] = None,
        plate_recognizer: Optional[IPlateRecognizer] = None,
        on_result: Optional[ResultCallback] = None,
        queue_maxsize: int = 8,
        executor: Optional[ThreadPoolExecutor] = None,
    ) -> None:
        self.snapshot_provider = snapshot_provider
        self.consensus = consensus
        self.gate = gate
        self.face_recognizer = face_recognizer
        self.plate_recognizer = plate_recognizer
        self.on_result = on_result

        self.queue = TrackCoalescingQueue(maxsize=queue_maxsize)
        self._owns_executor = executor is None
        self._executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="biometric-onnx")
        if hasattr(self.snapshot_provider, "_decode_executor") and getattr(self.snapshot_provider, "_decode_executor") is None:
            setattr(self.snapshot_provider, "_decode_executor", self._executor)

        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._face_latencies_ms: deque[float] = deque(maxlen=50)
        self._alpr_latencies_ms: deque[float] = deque(maxlen=50)
        self.evaluated_jobs_count: int = 0
        self.locked_tracks_count: int = 0
        self.snapshot_misses_count: int = 0

    def is_modality_ready(self, modality: str) -> bool:
        if modality == "face":
            return bool(self.gate.face_enabled and self.face_recognizer and self.face_recognizer.is_ready())
        if modality == "alpr":
            return bool(self.gate.alpr_enabled and self.plate_recognizer and self.plate_recognizer.is_ready())
        return False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker_loop(), name="biometric-worker")
        logger.info(
            "BiometricWorkerService started (face_ready=%s, alpr_ready=%s, queue_maxsize=%d)",
            self.is_modality_ready("face"),
            self.is_modality_ready("alpr"),
            self.queue.maxsize,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.queue.clear()
        await self.snapshot_provider.close()
        if self._owns_executor:
            self._executor.shutdown(wait=False)

    def enqueue_candidate(self, job: BiometricJob) -> bool:
        if not self._running:
            return False
        if not self.is_modality_ready(job.modality):
            return False

        eligible, cam_weight = self.gate.evaluate(job, self.consensus)
        if not eligible:
            return False

        job.camera_weight = cam_weight
        self.consensus.mark_dispatched(job.track_id, job.modality, now_ts=job.timestamp)
        return self.queue.put_nowait(job)

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                job = await self.queue.get()
                await self._process_job(job)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Biometric worker error: %s", exc)

    async def _process_job(self, job: BiometricJob) -> None:
        modality = job.modality
        if self.consensus.is_locked(job.track_id, modality):
            return

        if modality == "face":
            expand = (0.20, 0.15, 0.20, 0.10)
            upper_frac: Optional[float] = 0.60
        else:
            expand = (0.18, 0.18, 0.18, 0.18)
            upper_frac = None

        crop_payload = await self.snapshot_provider.fetch_crop(
            job.camera_id,
            job.bbox,
            expand_ratio=expand,
            prefer_upper_fraction=upper_frac,
            is_panoramic_180=job.is_panoramic_180,
        )
        if crop_payload is None:
            self.snapshot_misses_count += 1
            return

        loop = asyncio.get_running_loop()
        t_inf0 = time.perf_counter()
        update: Optional[TrackBiometricUpdate] = None
        box_crop_px: Optional[tuple[int, int, int, int]] = None

        if modality == "face" and self.face_recognizer is not None:
            face_eval = await loop.run_in_executor(
                self._executor,
                self.face_recognizer.recognize_crop,
                crop_payload.crop_bgr,
            )
            elapsed_ms = (time.perf_counter() - t_inf0) * 1000.0
            self._face_latencies_ms.append(elapsed_ms)
            self.evaluated_jobs_count += 1
            if face_eval is not None:
                box_crop_px = face_eval.box_crop_px
            update = self.consensus.record_face_evaluation(
                job.track_id,
                face_eval,
                camera_id=job.camera_id,
                timestamp=job.timestamp,
                camera_weight=job.camera_weight,
            )
        elif modality == "alpr" and self.plate_recognizer is not None:
            plate_eval = await loop.run_in_executor(
                self._executor,
                self.plate_recognizer.recognize_crop,
                crop_payload.crop_bgr,
            )
            elapsed_ms = (time.perf_counter() - t_inf0) * 1000.0
            self._alpr_latencies_ms.append(elapsed_ms)
            self.evaluated_jobs_count += 1
            if plate_eval is not None:
                box_crop_px = plate_eval.box_crop_px
            update = self.consensus.record_plate_evaluation(
                job.track_id,
                plate_eval,
                camera_id=job.camera_id,
                timestamp=job.timestamp,
                camera_weight=job.camera_weight,
            )

        if update is not None:
            sub_bbox_norm: Optional[tuple[float, float, float, float]] = None
            if box_crop_px is not None and crop_payload.full_width > 0 and crop_payload.full_height > 0:
                cx1, cy1, _cx2, _cy2 = crop_payload.crop_bbox_px
                bx1, by1, bx2, by2 = box_crop_px
                fw = float(crop_payload.full_width)
                fh = float(crop_payload.full_height)
                sub_bbox_norm = (
                    max(0.0, min(1.0, (cx1 + bx1) / fw)),
                    max(0.0, min(1.0, (cy1 + by1) / fh)),
                    max(0.0, min(1.0, (cx1 + bx2) / fw)),
                    max(0.0, min(1.0, (cy1 + by2) / fh)),
                )
            update = update.model_copy(
                update={
                    "subject_bbox_norm": (
                        float(job.bbox.x_min),
                        float(job.bbox.y_min),
                        float(job.bbox.x_max),
                        float(job.bbox.y_max),
                    ),
                    "sub_bbox_norm": sub_bbox_norm,
                    "full_frame_bgr": crop_payload.preview_frame_bgr,
                }
            )
            if update.biometric_locked:
                self.locked_tracks_count += 1
            if self.on_result is not None:
                await self.on_result(update)

    @staticmethod
    def _latency_summary(buf: deque[float]) -> dict[str, float]:
        if not buf:
            return {"count": 0, "mean_ms": 0.0, "p95_ms": 0.0}
        arr = sorted(buf)
        p95_idx = min(len(arr) - 1, int(0.95 * (len(arr) - 1)))
        return {
            "count": len(arr),
            "mean_ms": round(sum(arr) / len(arr), 2),
            "p95_ms": round(arr[p95_idx], 2),
        }

    def get_diagnostics(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "face_ready": self.is_modality_ready("face"),
            "alpr_ready": self.is_modality_ready("alpr"),
            "queue_depth": len(self.queue),
            "queue_maxsize": self.queue.maxsize,
            "enqueued_total": self.queue.enqueued_count,
            "coalesced_total": self.queue.coalesced_count,
            "dropped_total": self.queue.dropped_count,
            "evaluated_total": self.evaluated_jobs_count,
            "locked_total": self.locked_tracks_count,
            "snapshot_misses_total": self.snapshot_misses_count,
            "face_latency": self._latency_summary(self._face_latencies_ms),
            "alpr_latency": self._latency_summary(self._alpr_latencies_ms),
        }
