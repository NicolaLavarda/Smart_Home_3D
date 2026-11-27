from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Optional

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

from .gpu_probe import GpuSample, IGpuMetricsProbe, create_default_gpu_probe

logger = logging.getLogger("spatial_server.telemetry.metrics")


@dataclass
class SystemMetricsSnapshot:
    """Single point-in-time snapshot of PC Fisso hardware & Spatial CV/Recognition throughput."""

    timestamp: float
    cpu_percent: float = 0.0
    gpu_percent: Optional[float] = None
    gpu_memory_mb: Optional[float] = None
    ram_percent: float = 0.0
    ram_used_mb: float = 0.0
    ram_total_mb: float = 0.0
    process_cpu_percent: float = 0.0
    process_rss_mb: float = 0.0
    cv_fps_total: float = 0.0
    cv_fps_target_total: float = 0.0
    cv_fps_person: float = 0.0
    cv_fps_vehicle: float = 0.0
    cv_fps_idle: float = 0.0
    cv_read_fps_total: float = 0.0
    cv_infer_ms_avg: float = 0.0
    cv_infer_ms_max: float = 0.0
    person_det_fps: float = 0.0
    vehicle_det_fps: float = 0.0
    animal_det_fps: float = 0.0
    biometrics_fps: float = 0.0
    biometrics_face_ms: float = 0.0
    biometrics_alpr_ms: float = 0.0
    biometrics_queue_depth: int = 0
    active_tracks_total: int = 0
    active_persons: int = 0
    active_vehicles: int = 0
    active_animals: int = 0
    nvr_ram_buffer_mb: float = 0.0
    ws_clients_count: int = 0
    ingestion_mode: str = "synthetic"
    openvino_backend: str = "unknown"
    gpu_backend: str = "unavailable"
    cameras: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "t": round(self.timestamp, 3),
            "timestamp": round(self.timestamp, 3),
            "cpu_pct": round(self.cpu_percent, 1),
            "gpu_pct": round(self.gpu_percent, 1) if self.gpu_percent is not None else None,
            "gpu_mem_mb": round(self.gpu_memory_mb, 1) if self.gpu_memory_mb is not None else None,
            "ram_pct": round(self.ram_percent, 1),
            "ram_used_mb": round(self.ram_used_mb, 1),
            "ram_total_mb": round(self.ram_total_mb, 1),
            "proc_cpu_pct": round(self.process_cpu_percent, 1),
            "proc_rss_mb": round(self.process_rss_mb, 1),
            "cv_fps_total": round(self.cv_fps_total, 2),
            "cv_fps_target": round(self.cv_fps_target_total, 2),
            "cv_fps_person": round(self.cv_fps_person, 2),
            "cv_fps_vehicle": round(self.cv_fps_vehicle, 2),
            "cv_fps_idle": round(self.cv_fps_idle, 2),
            "cv_read_fps": round(self.cv_read_fps_total, 2),
            "cv_infer_ms": round(self.cv_infer_ms_avg, 2),
            "cv_infer_ms_max": round(self.cv_infer_ms_max, 2),
            "person_det_fps": round(self.person_det_fps, 2),
            "vehicle_det_fps": round(self.vehicle_det_fps, 2),
            "animal_det_fps": round(self.animal_det_fps, 2),
            "bio_fps": round(self.biometrics_fps, 2),
            "bio_face_ms": round(self.biometrics_face_ms, 2),
            "bio_alpr_ms": round(self.biometrics_alpr_ms, 2),
            "bio_queue": int(self.biometrics_queue_depth),
            "tracks_total": int(self.active_tracks_total),
            "tracks_person": int(self.active_persons),
            "tracks_vehicle": int(self.active_vehicles),
            "tracks_animal": int(self.active_animals),
            "nvr_ram_mb": round(self.nvr_ram_buffer_mb, 1),
            "ws_clients": int(self.ws_clients_count),
            "ingestion_mode": self.ingestion_mode,
            "openvino_backend": self.openvino_backend,
            "gpu_backend": self.gpu_backend,
            "cameras": self.cameras,
        }


def _downsample_points(points: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    bucket_size = len(points) / float(max_points)
    out: list[dict[str, Any]] = []
    numeric_keys = (
        "cpu_pct",
        "gpu_pct",
        "gpu_mem_mb",
        "ram_pct",
        "ram_used_mb",
        "proc_cpu_pct",
        "proc_rss_mb",
        "cv_fps_total",
        "cv_fps_target",
        "cv_fps_person",
        "cv_fps_vehicle",
        "cv_fps_idle",
        "cv_read_fps",
        "cv_infer_ms",
        "cv_infer_ms_max",
        "person_det_fps",
        "vehicle_det_fps",
        "animal_det_fps",
        "bio_fps",
        "bio_face_ms",
        "bio_alpr_ms",
        "nvr_ram_mb",
    )
    int_keys = ("bio_queue", "tracks_total", "tracks_person", "tracks_vehicle", "tracks_animal", "ws_clients")

    for i in range(max_points):
        lo = int(i * bucket_size)
        hi = int((i + 1) * bucket_size) if i < max_points - 1 else len(points)
        chunk = points[lo:max(lo + 1, hi)]
        last = chunk[-1]
        agg: dict[str, Any] = {
            "t": round(sum(float(c["t"]) for c in chunk) / len(chunk), 3),
            "timestamp": round(sum(float(c["t"]) for c in chunk) / len(chunk), 3),
            "ingestion_mode": last.get("ingestion_mode"),
            "openvino_backend": last.get("openvino_backend"),
            "gpu_backend": last.get("gpu_backend"),
            "cameras": last.get("cameras") or {},
        }
        for k in numeric_keys:
            vals = [float(c[k]) for c in chunk if c.get(k) is not None]
            if not vals:
                agg[k] = None
            elif k in ("cv_infer_ms_max",):
                agg[k] = round(max(vals), 2)
            else:
                agg[k] = round(sum(vals) / len(vals), 2)
        for k in int_keys:
            vals = [int(c[k]) for c in chunk if c.get(k) is not None]
            agg[k] = round(sum(vals) / len(vals), 1) if vals else 0
        agg["ram_total_mb"] = last.get("ram_total_mb", 0.0)
        out.append(agg)
    return out


class TelemetryMetricsService:
    """
    Lightweight, low-RAM system & CV performance collector:
    - Samples CPU, GPU (Windows PDH / D3DKMT), RAM, process usage, per-camera CV FPS,
      per-category detection rates, biometrics latency/throughput, and NVR buffer usage.
    - Stores high-resolution recent samples in a bounded RAM deque (`ram_window_s` @ `sample_interval_s`).
    - Persists downsampled rollups every `persist_interval_s` into SQLite WAL (`system_metrics_history`)
      supporting multi-hour / multi-day queries (`1m`..`7d`+) with negligible disk & CPU footprint.
    - Builds standardized `sensor.sh3d_*` entity payloads for Home Assistant & AutomationEngine.
    """

    def __init__(
        self,
        *,
        sample_interval_s: float = 2.0,
        persist_interval_s: float = 15.0,
        ram_window_s: float = 3600.0,
        retention_days: int = 7,
        ha_publish_interval_s: float = 15.0,
        gpu_probe: Optional[IGpuMetricsProbe] = None,
        state_provider: Optional[Callable[[], dict[str, Any]]] = None,
        repository: Any = None,
        on_entities_updated: Optional[Callable[[list[dict[str, Any]], bool], Any]] = None,
    ) -> None:
        self.sample_interval_s = max(1.0, float(sample_interval_s))
        self.persist_interval_s = max(self.sample_interval_s, float(persist_interval_s))
        self.ram_window_s = max(60.0, float(ram_window_s))
        self.retention_days = max(1, int(retention_days))
        self.ha_publish_interval_s = max(0.0, float(ha_publish_interval_s))

        self.gpu_probe = gpu_probe or create_default_gpu_probe()
        self.state_provider = state_provider
        self.repository = repository
        self.on_entities_updated = on_entities_updated

        max_samples = max(60, int(round(self.ram_window_s / self.sample_interval_s)))
        self._ram_buffer: deque[SystemMetricsSnapshot] = deque(maxlen=max_samples)
        self._persist_accum: list[SystemMetricsSnapshot] = []
        self._lock = threading.RLock()

        self._proc = psutil.Process(os.getpid()) if psutil is not None else None
        self._cpu_count = max(1, os.cpu_count() or 1)
        if psutil is not None:
            try:
                psutil.cpu_percent(interval=None)
                if self._proc is not None:
                    self._proc.cpu_percent(interval=None)
            except Exception:
                pass

        self._last_sample_mono: float = 0.0
        self._last_persist_mono: float = 0.0
        self._last_ha_pub_mono: float = 0.0
        self._prev_counts: Optional[dict[str, int]] = None
        self._prev_counts_mono: float = 0.0
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        self._db_samples_written: int = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.collect_sample_once()
        self._task = asyncio.create_task(self._loop(), name="telemetry-metrics")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        try:
            await self.flush_rollup_to_db(force=True)
        except Exception:
            pass
        try:
            self.gpu_probe.close()
        except Exception:
            pass

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.sample_interval_s)
                if not self._running:
                    break
                snap = self.collect_sample_once()
                now_mono = time.monotonic()
                if now_mono - self._last_persist_mono >= self.persist_interval_s:
                    self._last_persist_mono = now_mono
                    await self.flush_rollup_to_db()
                if self.on_entities_updated is not None:
                    should_pub_ha = (
                        self.ha_publish_interval_s > 0.0
                        and (self._last_ha_pub_mono <= 0.0 or (now_mono - self._last_ha_pub_mono) >= self.ha_publish_interval_s)
                    )
                    if should_pub_ha:
                        self._last_ha_pub_mono = now_mono
                    entities = self.build_entities(snap)
                    res = self.on_entities_updated(entities, should_pub_ha)
                    if asyncio.iscoroutine(res):
                        await res
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("TelemetryMetricsService loop warning: %s", exc)

    def collect_sample_once(self, now_ts: Optional[float] = None) -> SystemMetricsSnapshot:
        ts = float(now_ts if now_ts is not None else time.time())
        now_mono = time.monotonic()

        cpu_pct = 0.0
        ram_pct = 0.0
        ram_used_mb = 0.0
        ram_total_mb = 0.0
        proc_cpu_pct = 0.0
        proc_rss_mb = 0.0

        if psutil is not None:
            try:
                cpu_pct = float(psutil.cpu_percent(interval=None))
                vm = psutil.virtual_memory()
                ram_pct = float(vm.percent)
                ram_total_mb = vm.total / (1024.0 * 1024.0)
                ram_used_mb = (vm.total - vm.available) / (1024.0 * 1024.0)
                if self._proc is not None:
                    raw_proc_cpu = float(self._proc.cpu_percent(interval=None))
                    proc_cpu_pct = max(0.0, min(100.0, raw_proc_cpu / float(self._cpu_count)))
                    proc_rss_mb = self._proc.memory_info().rss / (1024.0 * 1024.0)
            except Exception:
                pass

        gpu_sample: GpuSample = self.gpu_probe.sample()
        ext = self.state_provider() if self.state_provider is not None else {}

        cameras_stats = ext.get("camera_stats") or []
        fps_sched = ext.get("fps_snapshot") or {}
        sched_cams = fps_sched.get("cameras") or {}

        cam_map: dict[str, dict[str, Any]] = {}
        cv_fps_total = 0.0
        cv_read_fps_total = 0.0
        cv_fps_person = 0.0
        cv_fps_vehicle = 0.0
        cv_fps_idle = 0.0
        infer_vals: list[float] = []
        ov_backends: list[str] = []

        for st in cameras_stats:
            cam_id = str(st.get("camera_id") or "")
            if not cam_id:
                continue
            actual_fps = float(st.get("actual_infer_fps") or 0.0)
            read_fps = float(st.get("actual_read_fps") or 0.0)
            target_fps = float(st.get("target_fps") or (sched_cams.get(cam_id, {}).get("target_fps") or 0.0))
            tier = str((sched_cams.get(cam_id) or {}).get("tier") or "idle")
            infer_ema = float(st.get("infer_ms_ema") or st.get("last_infer_ms") or 0.0)
            backend = str(st.get("backend") or "")
            if backend and backend not in ov_backends:
                ov_backends.append(backend)

            cv_fps_total += actual_fps
            cv_read_fps_total += read_fps
            if tier == "person":
                cv_fps_person += actual_fps
            elif tier == "vehicle":
                cv_fps_vehicle += actual_fps
            else:
                cv_fps_idle += actual_fps

            if infer_ema > 0.0:
                infer_vals.append(infer_ema)

            last_err = str(st.get("last_error") or "").strip()
            if "://" in last_err and "@" in last_err:
                last_err = re.sub(r"://[^/@\s]+@", "://***@", last_err)

            cam_map[cam_id] = {
                "actual_fps": round(actual_fps, 2),
                "target_fps": round(target_fps, 2),
                "read_fps": round(read_fps, 2),
                "infer_ms": round(infer_ema, 2),
                "tier": tier,
                "rtsp_connected": bool(st.get("rtsp_connected", False)),
                "frames_read": int(st.get("frames_read") or 0),
                "frames_inferred": int(st.get("frames_inferred") or 0),
                "last_error": last_err[:140] if last_err else None,
                "backend": backend,
            }

        # Synthetic / MQTT fallback FPS when no OpenVINO RTSP camera source is active
        counts = ext.get("counters") or {}
        det_person_total = int(counts.get("person_detections", 0))
        det_vehicle_total = int(counts.get("vehicle_detections", 0))
        det_animal_total = int(counts.get("animal_detections", 0))
        bio_eval_total = int(counts.get("biometrics_evaluated", 0))
        batches_total = int(counts.get("batches_processed", 0))

        person_det_fps = 0.0
        vehicle_det_fps = 0.0
        animal_det_fps = 0.0
        bio_fps = 0.0
        batch_fps = 0.0

        dt_cnt = now_mono - self._prev_counts_mono if self._prev_counts_mono > 0.0 else 0.0
        if dt_cnt >= 0.25 and self._prev_counts is not None:
            dp = max(0, det_person_total - self._prev_counts.get("person_detections", 0))
            dv = max(0, det_vehicle_total - self._prev_counts.get("vehicle_detections", 0))
            da = max(0, det_animal_total - self._prev_counts.get("animal_detections", 0))
            db = max(0, bio_eval_total - self._prev_counts.get("biometrics_evaluated", 0))
            dbatch = max(0, batches_total - self._prev_counts.get("batches_processed", 0))
            person_det_fps = dp / dt_cnt
            vehicle_det_fps = dv / dt_cnt
            animal_det_fps = da / dt_cnt
            bio_fps = db / dt_cnt
            batch_fps = dbatch / dt_cnt

        self._prev_counts = {
            "person_detections": det_person_total,
            "vehicle_detections": det_vehicle_total,
            "animal_detections": det_animal_total,
            "biometrics_evaluated": bio_eval_total,
            "batches_processed": batches_total,
        }
        self._prev_counts_mono = now_mono

        if not cam_map and batch_fps > 0.0:
            cv_fps_total = batch_fps

        ingestion_mode = str(ext.get("ingestion_mode") or "synthetic")
        if ov_backends:
            openvino_backend = ", ".join(ov_backends)
        else:
            openvino_backend = ingestion_mode

        bio_diag = ext.get("biometrics_diag") or {}
        face_lat = bio_diag.get("face_latency") or {}
        alpr_lat = bio_diag.get("alpr_latency") or {}
        tracks_by_cat = ext.get("tracks_by_category") or {}

        snap = SystemMetricsSnapshot(
            timestamp=ts,
            cpu_percent=cpu_pct,
            gpu_percent=gpu_sample.gpu_percent,
            gpu_memory_mb=gpu_sample.gpu_memory_mb,
            ram_percent=ram_pct,
            ram_used_mb=ram_used_mb,
            ram_total_mb=ram_total_mb,
            process_cpu_percent=proc_cpu_pct,
            process_rss_mb=proc_rss_mb,
            cv_fps_total=cv_fps_total,
            cv_fps_target_total=float(fps_sched.get("total_allocated_fps") or 0.0),
            cv_fps_person=cv_fps_person,
            cv_fps_vehicle=cv_fps_vehicle,
            cv_fps_idle=cv_fps_idle,
            cv_read_fps_total=cv_read_fps_total,
            cv_infer_ms_avg=(sum(infer_vals) / len(infer_vals)) if infer_vals else 0.0,
            cv_infer_ms_max=max(infer_vals) if infer_vals else 0.0,
            person_det_fps=person_det_fps,
            vehicle_det_fps=vehicle_det_fps,
            animal_det_fps=animal_det_fps,
            biometrics_fps=bio_fps,
            biometrics_face_ms=float(face_lat.get("mean_ms") or 0.0),
            biometrics_alpr_ms=float(alpr_lat.get("mean_ms") or 0.0),
            biometrics_queue_depth=int(bio_diag.get("queue_depth") or 0),
            active_tracks_total=int(ext.get("active_tracks_count") or 0),
            active_persons=int(tracks_by_cat.get("person") or 0),
            active_vehicles=int(tracks_by_cat.get("vehicle") or 0),
            active_animals=int(tracks_by_cat.get("animal") or 0),
            nvr_ram_buffer_mb=float(ext.get("nvr_ram_buffer_mb") or 0.0),
            ws_clients_count=int(ext.get("ws_clients_count") or 0),
            ingestion_mode=ingestion_mode,
            openvino_backend=openvino_backend,
            gpu_backend=gpu_sample.backend_name,
            cameras=cam_map,
        )
        with self._lock:
            self._ram_buffer.append(snap)
            self._persist_accum.append(snap)
            self._last_sample_mono = now_mono
        return snap

    async def flush_rollup_to_db(self, *, force: bool = False) -> int:
        if self.repository is None or not hasattr(self.repository, "append_system_metrics_sample"):
            with self._lock:
                self._persist_accum.clear()
            return 0
        with self._lock:
            if not self._persist_accum:
                return 0
            if not force and len(self._persist_accum) == 0:
                return 0
            chunk = list(self._persist_accum)
            self._persist_accum.clear()

        dicts = [s.to_dict() for s in chunk]
        agg = _downsample_points(dicts, 1)[0]
        loop = asyncio.get_running_loop()
        row_id = await loop.run_in_executor(None, self.repository.append_system_metrics_sample, agg)
        self._db_samples_written += 1
        return int(row_id or 0)

    def get_latest_snapshot(self) -> SystemMetricsSnapshot:
        with self._lock:
            if self._ram_buffer:
                return self._ram_buffer[-1]
        return self.collect_sample_once()

    def build_entities(self, snap: Optional[SystemMetricsSnapshot] = None) -> list[dict[str, Any]]:
        s = snap or self.get_latest_snapshot()
        ts = round(s.timestamp, 3)
        cam_attrs = {
            cid: {
                "fps": c.get("actual_fps", 0.0),
                "target_fps": c.get("target_fps", 0.0),
                "tier": c.get("tier", "idle"),
                "infer_ms": c.get("infer_ms", 0.0),
                "rtsp_connected": c.get("rtsp_connected", False),
            }
            for cid, c in (s.cameras or {}).items()
        }
        person_cams = [cid for cid, c in (s.cameras or {}).items() if c.get("tier") == "person"]
        vehicle_cams = [cid for cid, c in (s.cameras or {}).items() if c.get("tier") == "vehicle"]

        return [
            {
                "entity_id": "sensor.sh3d_pc_cpu",
                "slug": "pc_cpu",
                "name": "PC Fisso CPU",
                "domain": "sensor",
                "state": round(s.cpu_percent, 1),
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "icon": "mdi:cpu-64-bit",
                "category": "hardware",
                "attributes": {
                    "cpu_count_logical": self._cpu_count,
                    "process_cpu_pct": round(s.process_cpu_percent, 1),
                },
                "updated_at": ts,
            },
            {
                "entity_id": "sensor.sh3d_pc_gpu",
                "slug": "pc_gpu",
                "name": "PC Fisso GPU",
                "domain": "sensor",
                "state": round(s.gpu_percent, 1) if s.gpu_percent is not None else "unavailable",
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "icon": "mdi:expansion-card",
                "category": "hardware",
                "attributes": {
                    "gpu_memory_mb": round(s.gpu_memory_mb, 1) if s.gpu_memory_mb is not None else None,
                    "gpu_backend": s.gpu_backend,
                    "openvino_backend": s.openvino_backend,
                },
                "updated_at": ts,
            },
            {
                "entity_id": "sensor.sh3d_pc_ram",
                "slug": "pc_ram",
                "name": "PC Fisso RAM",
                "domain": "sensor",
                "state": round(s.ram_percent, 1),
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "icon": "mdi:memory",
                "category": "hardware",
                "attributes": {
                    "ram_used_mb": round(s.ram_used_mb, 1),
                    "ram_total_mb": round(s.ram_total_mb, 1),
                    "nvr_ram_buffer_mb": round(s.nvr_ram_buffer_mb, 1),
                },
                "updated_at": ts,
            },
            {
                "entity_id": "sensor.sh3d_server_cpu",
                "slug": "server_cpu",
                "name": "Spatial Server CPU",
                "domain": "sensor",
                "state": round(s.process_cpu_percent, 1),
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "icon": "mdi:application-cog",
                "category": "hardware",
                "attributes": {
                    "ingestion_mode": s.ingestion_mode,
                    "openvino_backend": s.openvino_backend,
                },
                "updated_at": ts,
            },
            {
                "entity_id": "sensor.sh3d_server_ram",
                "slug": "server_ram",
                "name": "Spatial Server RAM",
                "domain": "sensor",
                "state": round(s.process_rss_mb, 1),
                "unit_of_measurement": "MB",
                "state_class": "measurement",
                "icon": "mdi:memory",
                "category": "hardware",
                "attributes": {
                    "nvr_ram_buffer_mb": round(s.nvr_ram_buffer_mb, 1),
                },
                "updated_at": ts,
            },
            {
                "entity_id": "sensor.sh3d_cv_fps_totale",
                "slug": "cv_fps_totale",
                "name": "CV FPS Totale",
                "domain": "sensor",
                "state": round(s.cv_fps_total, 2),
                "unit_of_measurement": "FPS",
                "state_class": "measurement",
                "icon": "mdi:speedometer",
                "category": "cv",
                "attributes": {
                    "target_fps_total": round(s.cv_fps_target_total, 2),
                    "read_fps_total": round(s.cv_read_fps_total, 2),
                    "idle_fps": round(s.cv_fps_idle, 2),
                    "openvino_backend": s.openvino_backend,
                    "cameras": cam_attrs,
                },
                "updated_at": ts,
            },
            {
                "entity_id": "sensor.sh3d_cv_fps_persone",
                "slug": "cv_fps_persone",
                "name": "CV FPS Persone",
                "domain": "sensor",
                "state": round(s.cv_fps_person, 2),
                "unit_of_measurement": "FPS",
                "state_class": "measurement",
                "icon": "mdi:account-eye",
                "category": "cv",
                "attributes": {
                    "active_persons": s.active_persons,
                    "person_det_fps": round(s.person_det_fps, 2),
                    "person_cameras": person_cams,
                },
                "updated_at": ts,
            },
            {
                "entity_id": "sensor.sh3d_cv_fps_veicoli",
                "slug": "cv_fps_veicoli",
                "name": "CV FPS Veicoli",
                "domain": "sensor",
                "state": round(s.cv_fps_vehicle, 2),
                "unit_of_measurement": "FPS",
                "state_class": "measurement",
                "icon": "mdi:car-search",
                "category": "cv",
                "attributes": {
                    "active_vehicles": s.active_vehicles,
                    "vehicle_det_fps": round(s.vehicle_det_fps, 2),
                    "animal_det_fps": round(s.animal_det_fps, 2),
                    "vehicle_cameras": vehicle_cams,
                },
                "updated_at": ts,
            },
            {
                "entity_id": "sensor.sh3d_cv_inferenza_ms",
                "slug": "cv_inferenza_ms",
                "name": "CV Latenza Inferenza",
                "domain": "sensor",
                "state": round(s.cv_infer_ms_avg, 1),
                "unit_of_measurement": "ms",
                "state_class": "measurement",
                "icon": "mdi:timer-outline",
                "category": "cv",
                "attributes": {
                    "max_infer_ms": round(s.cv_infer_ms_max, 1),
                    "openvino_backend": s.openvino_backend,
                },
                "updated_at": ts,
            },
            {
                "entity_id": "sensor.sh3d_biometria_fps",
                "slug": "biometria_fps",
                "name": "Biometria Volti/Targhe FPS",
                "domain": "sensor",
                "state": round(s.biometrics_fps, 2),
                "unit_of_measurement": "FPS",
                "state_class": "measurement",
                "icon": "mdi:face-recognition",
                "category": "biometrics",
                "attributes": {
                    "face_latency_ms": round(s.biometrics_face_ms, 1),
                    "alpr_latency_ms": round(s.biometrics_alpr_ms, 1),
                    "queue_depth": s.biometrics_queue_depth,
                },
                "updated_at": ts,
            },
            {
                "entity_id": "sensor.sh3d_tracce_attive",
                "slug": "tracce_attive",
                "name": "Soggetti Tracciati Attivi",
                "domain": "sensor",
                "state": int(s.active_tracks_total),
                "unit_of_measurement": "soggetti",
                "state_class": "measurement",
                "icon": "mdi:radar",
                "category": "tracking",
                "attributes": {
                    "persone": s.active_persons,
                    "veicoli": s.active_vehicles,
                    "animali": s.active_animals,
                    "ws_clients": s.ws_clients_count,
                },
                "updated_at": ts,
            },
        ]

    def query_timeseries(
        self,
        *,
        window_s: int = 300,
        max_points: int = 180,
        now_ts: Optional[float] = None,
    ) -> dict[str, Any]:
        t_end = float(now_ts if now_ts is not None else time.time())
        eff_window = max(30, min(int(window_s), self.retention_days * 86400))
        t_start = t_end - eff_window
        eff_max_pts = max(20, min(int(max_points), 500))

        with self._lock:
            ram_points = [
                s.to_dict()
                for s in self._ram_buffer
                if s.timestamp >= t_start and s.timestamp <= t_end
            ]
            latest = self._ram_buffer[-1] if self._ram_buffer else None

        if latest is None:
            latest = self.collect_sample_once(t_end)
            ram_points = [latest.to_dict()]

        ram_oldest_ts = ram_points[0]["t"] if ram_points else t_end
        needs_db = eff_window > self.ram_window_s or (ram_oldest_ts - t_start) > (self.sample_interval_s * 3.0)

        source = "memory"
        series: list[dict[str, Any]] = []
        if needs_db and self.repository is not None and hasattr(self.repository, "query_system_metrics"):
            db_points = self.repository.query_system_metrics(t_start, t_end, max_points=eff_max_pts)
            if db_points and ram_points:
                # Merge older SQLite buckets with higher-res RAM samples in tail if window <= 3600s
                if eff_window <= self.ram_window_s:
                    cutoff = db_points[-1]["t"]
                    tail = [p for p in ram_points if p["t"] > cutoff]
                    series = _downsample_points(db_points + tail, eff_max_pts)
                    source = "mixed"
                else:
                    series = db_points
                    source = "sqlite"
            elif db_points:
                series = db_points
                source = "sqlite"
            else:
                series = _downsample_points(ram_points, eff_max_pts)
        else:
            series = _downsample_points(ram_points, eff_max_pts)

        # Summary stats over returned series
        cpus = [float(p["cpu_pct"]) for p in series if p.get("cpu_pct") is not None]
        gpus = [float(p["gpu_pct"]) for p in series if p.get("gpu_pct") is not None]
        rams = [float(p["ram_pct"]) for p in series if p.get("ram_pct") is not None]
        fps_tot = [float(p["cv_fps_total"]) for p in series if p.get("cv_fps_total") is not None]
        inf_ms = [float(p["cv_infer_ms"]) for p in series if p.get("cv_infer_ms") is not None]

        db_count = 0
        if self.repository is not None and hasattr(self.repository, "get_system_metrics_count"):
            try:
                db_count = int(self.repository.get_system_metrics_count())
            except Exception:
                db_count = 0

        resolution_s = round(eff_window / max(1, len(series)), 1) if series else self.sample_interval_s

        return {
            "status": "ok",
            "window_s": eff_window,
            "t_start": round(t_start, 3),
            "t_end": round(t_end, 3),
            "source": source,
            "resolution_s": resolution_s,
            "current": latest.to_dict(),
            "entities": self.build_entities(latest),
            "series": series,
            "summary": {
                "samples_count": len(series),
                "ram_samples_count": len(self._ram_buffer),
                "db_samples_count": db_count,
                "sample_interval_s": self.sample_interval_s,
                "persist_interval_s": self.persist_interval_s,
                "retention_days": self.retention_days,
                "db_size_estimate_mb": round((db_count * 260) / (1024.0 * 1024.0), 2),
                "cpu_avg": round(sum(cpus) / len(cpus), 1) if cpus else 0.0,
                "cpu_max": round(max(cpus), 1) if cpus else 0.0,
                "gpu_avg": round(sum(gpus) / len(gpus), 1) if gpus else None,
                "gpu_max": round(max(gpus), 1) if gpus else None,
                "ram_avg": round(sum(rams) / len(rams), 1) if rams else 0.0,
                "cv_fps_avg": round(sum(fps_tot) / len(fps_tot), 2) if fps_tot else 0.0,
                "cv_fps_max": round(max(fps_tot), 2) if fps_tot else 0.0,
                "infer_ms_avg": round(sum(inf_ms) / len(inf_ms), 1) if inf_ms else 0.0,
            },
        }
