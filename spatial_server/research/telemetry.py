from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import platform
import queue
import shutil
import threading
import time
from typing import Any, Optional

import cv2
import numpy as np

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

logger = logging.getLogger("spatial_server.research")


def _safe_pkg_version(name: str) -> Optional[str]:
    try:
        return importlib.metadata.version(name)
    except Exception:
        return None


def _day_str(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(float(ts if ts is not None else time.time()), tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d")


def _percentile(values: list[float], p: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return round(float(ordered[idx]), 2)


class ProductionResearchCollector:
    """
    Non-blocking asynchronous telemetry & benchmark collector for production evaluation.

    Writes compact JSONL logs + rate-limited subject crops under ``base_dir/<YYYY-MM-DD>/``,
    auto-prunes old data to respect ``max_disk_mb`` / ``retention_days``, and catches all
    I/O errors so it never degrades the live tracking/notification pipeline.
    """

    def __init__(
        self,
        base_dir: Path,
        *,
        max_disk_mb: float = 250.0,
        retention_days: int = 7,
        save_crops: bool = True,
        crop_interval_s: float = 4.0,
        max_crops_per_track: int = 6,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.max_disk_mb = max(20.0, float(max_disk_mb))
        self.retention_days = max(1, int(retention_days))
        self.save_crops = bool(save_crops)
        self.crop_interval_s = max(0.5, float(crop_interval_s))
        self.max_crops_per_track = max(1, int(max_crops_per_track))

        self._queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue(maxsize=512)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._dropped_count: int = 0
        self._written_count: int = 0
        self._crops_saved_count: int = 0
        self._anomalies_count: int = 0
        self._track_crop_state: dict[int, tuple[float, int]] = {}  # track_id -> (last_ts, saved_count)
        self._last_health_mono: float = 0.0
        self._last_prune_mono: float = 0.0
        self._prev_cam_reconnects: dict[str, int] = {}

    def start(self, session_meta: Optional[dict[str, Any]] = None) -> None:
        if self._running:
            return
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self._write_session_meta(session_meta or {})
        except Exception as exc:
            logger.debug("Research telemetry init warning: %s", exc)
        self._running = True
        self._thread = threading.Thread(target=self._writer_loop, name="research-telemetry", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        if not self._running:
            return
        self._running = False
        try:
            self._queue.put_nowait(("__stop__", {}))
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            self._thread = None

    def _write_session_meta(self, extra_meta: dict[str, Any]) -> None:
        mem_total_mb: Optional[float] = None
        mem_avail_mb: Optional[float] = None
        if psutil is not None:
            try:
                vm = psutil.virtual_memory()
                mem_total_mb = round(vm.total / (1024 * 1024), 1)
                mem_avail_mb = round(vm.available / (1024 * 1024), 1)
            except Exception:
                pass

        meta = {
            "started_at": round(time.time(), 3),
            "started_iso": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "host": {
                "platform": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "cpu_count_logical": os.cpu_count(),
                "ram_total_mb": mem_total_mb,
                "ram_available_mb": mem_avail_mb,
            },
            "runtime": {
                "python": platform.python_version(),
                "openvino": _safe_pkg_version("openvino"),
                "onnxruntime": _safe_pkg_version("onnxruntime"),
                "opencv": _safe_pkg_version("opencv-python") or _safe_pkg_version("opencv-python-headless"),
            },
            **extra_meta,
        }
        (self.base_dir / "session_meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _enqueue(self, stream_name: str, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        try:
            self._queue.put_nowait((stream_name, payload))
        except queue.Full:
            self._dropped_count += 1

    def _writer_loop(self) -> None:
        while True:
            try:
                stream_name, payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                if not self._running:
                    break
                continue
            if stream_name == "__stop__":
                break
            try:
                self._process_item(stream_name, payload)
                self._written_count += 1
            except Exception as exc:
                logger.debug("Research telemetry write skipped (%s): %s", stream_name, exc)

    def _process_item(self, stream_name: str, payload: dict[str, Any]) -> None:
        ts = float(payload.get("ts") or time.time())
        day_dir = self.base_dir / _day_str(ts)
        day_dir.mkdir(parents=True, exist_ok=True)

        if stream_name == "crop_sample":
            frame_crop = payload.pop("_crop_bgr", None)
            if isinstance(frame_crop, np.ndarray) and frame_crop.size > 0:
                crops_dir = day_dir / "crops"
                crops_dir.mkdir(parents=True, exist_ok=True)
                cam = str(payload.get("camera_id") or "cam").replace("/", "_")
                tid = int(payload.get("track_id") or 0)
                ms = int(round(ts * 1000))
                rel_name = f"{cam}_tr{tid}_{ms}.jpg"
                crop_path = crops_dir / rel_name
                h, w = frame_crop.shape[:2]
                max_side = max(h, w)
                img_out = frame_crop
                if max_side > 256:
                    scale = 256.0 / float(max_side)
                    img_out = cv2.resize(
                        frame_crop,
                        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                        interpolation=cv2.INTER_AREA,
                    )
                ok, buf = cv2.imencode(".jpg", img_out, [int(cv2.IMWRITE_JPEG_QUALITY), 78])
                if ok:
                    crop_path.write_bytes(buf.tobytes())
                    payload["crop_relpath"] = f"crops/{rel_name}"
                    self._crops_saved_count += 1
            target_file = day_dir / "biometrics_and_reid_samples.jsonl"
        else:
            target_file = day_dir / f"{stream_name}.jsonl"

        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with target_file.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def maybe_record_health(
        self,
        *,
        fps_snapshot: Optional[dict[str, Any]],
        camera_stats: list[dict[str, Any]],
        active_tracks_count: int,
        parked_slots_count: int,
        biometrics_diag: Optional[dict[str, Any]] = None,
        interval_s: float = 60.0,
        now_ts: Optional[float] = None,
    ) -> None:
        now_mono = time.monotonic()
        if self._last_health_mono > 0.0 and (now_mono - self._last_health_mono) < interval_s:
            return
        self._last_health_mono = now_mono
        ts = float(now_ts if now_ts is not None else time.time())

        cpu_pct: Optional[float] = None
        ram_pct: Optional[float] = None
        rss_mb: Optional[float] = None
        if psutil is not None:
            try:
                cpu_pct = round(float(psutil.cpu_percent(interval=None)), 1)
                vm = psutil.virtual_memory()
                ram_pct = round(float(vm.percent), 1)
                rss_mb = round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 1)
            except Exception:
                pass

        self._enqueue(
            "system_health",
            {
                "ts": round(ts, 3),
                "cpu_pct": cpu_pct,
                "ram_pct": ram_pct,
                "rss_mb": rss_mb,
                "active_tracks": active_tracks_count,
                "parked_slots": parked_slots_count,
                "fps_scheduler": fps_snapshot,
                "cameras": camera_stats,
                "biometrics": biometrics_diag,
            },
        )

        # Flag system/camera anomalies
        if ram_pct is not None and ram_pct > 85.0:
            self.record_anomaly("high_ram_usage_pct_gt_85", {"ram_pct": ram_pct, "rss_mb": rss_mb}, ts=ts)
        for st in camera_stats:
            cam_id = str(st.get("camera_id") or "")
            ema = float(st.get("infer_ms_ema") or 0.0)
            if ema > 250.0:
                self.record_anomaly("high_infer_latency_ms_gt_250", {"camera_id": cam_id, "infer_ms_ema": ema}, ts=ts)
            rec_cnt = int(st.get("reconnect_count") or 0)
            prev_rec = self._prev_cam_reconnects.get(cam_id, 0)
            if rec_cnt > prev_rec:
                self._prev_cam_reconnects[cam_id] = rec_cnt
                self.record_anomaly("rtsp_reconnect", {"camera_id": cam_id, "reconnect_count": rec_cnt}, ts=ts)

    def record_track_lifecycle(self, items: list[dict[str, Any]]) -> None:
        for item in items:
            row = dict(item)
            row.setdefault("ts", round(float(row.get("timestamp") or time.time()), 3))
            self._enqueue("track_lifecycle", row)

    def maybe_record_crop_sample(
        self,
        *,
        track_id: int,
        camera_id: str,
        class_label: str,
        bbox_norm: tuple[float, float, float, float],
        frame_bgr: Optional[np.ndarray],
        world_xyz: tuple[float, float, float],
        confidence: float,
        is_night_ir: bool,
        mean_luma: float,
        mean_saturation: float,
        timestamp: float,
    ) -> None:
        if not self.save_crops or frame_bgr is None or frame_bgr.size == 0:
            return
        if class_label not in ("person", "car", "truck", "motorbike"):
            return

        # Keep track map bounded
        if len(self._track_crop_state) > 300:
            self._track_crop_state = {
                k: v for k, v in self._track_crop_state.items()
                if abs(timestamp - v[0]) <= 3600.0
            }

        prev_ts, count = self._track_crop_state.get(track_id, (-1e18, 0))
        if count >= self.max_crops_per_track or (timestamp - prev_ts) < self.crop_interval_s:
            return

        fh, fw = frame_bgr.shape[:2]
        x1 = max(0, min(fw - 1, int(round(bbox_norm[0] * fw))))
        y1 = max(0, min(fh - 1, int(round(bbox_norm[1] * fh))))
        x2 = max(x1 + 1, min(fw, int(round(bbox_norm[2] * fw))))
        y2 = max(y1 + 1, min(fh, int(round(bbox_norm[3] * fh))))
        cw, ch = x2 - x1, y2 - y1
        if cw < 12 or ch < 16:
            return

        crop = frame_bgr[y1:y2, x1:x2].copy()
        self._track_crop_state[track_id] = (timestamp, count + 1)
        self._enqueue(
            "crop_sample",
            {
                "kind": "detection_crop",
                "ts": round(float(timestamp), 3),
                "track_id": track_id,
                "camera_id": camera_id,
                "class_label": class_label,
                "confidence": round(float(confidence), 3),
                "frame_wh": [fw, fh],
                "crop_wh": [cw, ch],
                "bbox_norm": [round(float(v), 4) for v in bbox_norm],
                "world_xyz": [round(float(v), 2) for v in world_xyz],
                "is_night_ir": bool(is_night_ir),
                "mean_luma": round(float(mean_luma), 1),
                "mean_saturation": round(float(mean_saturation), 1),
                "_crop_bgr": crop,
            },
        )

    def record_biometric_outcome(self, payload: dict[str, Any]) -> None:
        row = {"kind": "biometric_outcome", **payload}
        row.setdefault("ts", round(float(row.get("timestamp") or time.time()), 3))
        self._enqueue("biometrics_and_reid_samples", row)

    def record_scene_event(self, ev: Any, *, lifecycle: str = "closed") -> None:
        subjects = list(getattr(ev, "subjects", []) or [])
        vehicles = [s for s in subjects if getattr(s, "class_label", "") in ("car", "truck", "motorbike")]
        people = [s for s in subjects if getattr(s, "class_label", "") == "person"]
        duration_s = float(getattr(ev, "duration_s", 0.0) or 0.0)
        best_score = float(getattr(ev, "best_frame_score", 0.0) or 0.0)
        ts = float(getattr(ev, "ended_at", None) or getattr(ev, "started_at", None) or time.time())

        self._enqueue(
            "scene_events",
            {
                "ts": round(ts, 3),
                "lifecycle": lifecycle,
                "event_id": getattr(ev, "event_id", ""),
                "started_at": getattr(ev, "started_at", 0.0),
                "ended_at": getattr(ev, "ended_at", 0.0),
                "duration_s": round(duration_s, 2),
                "importance": getattr(ev, "importance", "notable"),
                "alarm_state": getattr(ev, "alarm_state", None),
                "best_camera_id": getattr(ev, "best_camera_id", None),
                "best_frame_score": round(best_score, 2),
                "cameras": list(getattr(ev, "cameras", []) or []),
                "zones": list(getattr(ev, "zones", []) or []),
                "people_count": len(people),
                "vehicles_count": len(vehicles),
                "subjects": [
                    {
                        "track_id": getattr(s, "track_id", 0),
                        "class_label": getattr(s, "class_label", ""),
                        "identity": getattr(s, "identity", None),
                        "plate": getattr(s, "plate", None),
                        "plate_whitelisted": getattr(s, "plate_whitelisted", None),
                        "merged_track_ids": list(getattr(s, "merged_track_ids", []) or []),
                    }
                    for s in subjects
                ],
                "summary_it": getattr(ev, "summary_it", ""),
            },
        )

        if lifecycle == "closed":
            if duration_s > 180.0:
                self.record_anomaly("episode_duration_gt_180s", {"event_id": ev.event_id, "duration_s": duration_s}, ts=ts)
            if len(vehicles) > 2:
                self.record_anomaly("vehicle_count_gt_2", {"event_id": ev.event_id, "vehicles_count": len(vehicles)}, ts=ts)
            if people and getattr(ev, "cover_raw_relpath", None) and best_score < 100.0:
                self.record_anomaly("person_cover_score_lt_100", {"event_id": ev.event_id, "best_frame_score": best_score}, ts=ts)

    def record_anomaly(self, kind: str, details: dict[str, Any], *, ts: Optional[float] = None) -> None:
        self._anomalies_count += 1
        self._enqueue(
            "anomalies",
            {
                "ts": round(float(ts if ts is not None else time.time()), 3),
                "anomaly": kind,
                **details,
            },
        )

    def prune(self) -> int:
        """Delete oldest day folders/crops when exceeding retention days or max_disk_mb."""
        removed = 0
        try:
            if not self.base_dir.is_dir():
                return 0

            # 1. Retention days
            cutoff_day = _day_str(time.time() - self.retention_days * 86400)
            day_dirs = sorted(
                [p for p in self.base_dir.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == "-"],
                key=lambda p: p.name,
            )
            for d in list(day_dirs):
                if d.name < cutoff_day:
                    shutil.rmtree(d, ignore_errors=True)
                    day_dirs.remove(d)
                    removed += 1

            # 2. Total size quota
            max_bytes = self.max_disk_mb * 1024 * 1024

            def _dir_size(path: Path) -> int:
                return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())

            total_bytes = _dir_size(self.base_dir)
            if total_bytes <= max_bytes:
                return removed

            # First delete oldest crops, leaving JSONL diagnostics intact when possible
            crop_files = sorted(
                [f for d in day_dirs for f in (d / "crops").glob("*.jpg") if (d / "crops").is_dir()],
                key=lambda f: f.stat().st_mtime,
            )
            for f in crop_files:
                if total_bytes <= max_bytes:
                    break
                try:
                    sz = f.stat().st_size
                    f.unlink(missing_ok=True)
                    total_bytes -= sz
                    removed += 1
                except Exception:
                    continue

            # If still above quota, prune oldest day folders entirely
            for d in day_dirs[:-1]:
                if total_bytes <= max_bytes:
                    break
                sz = _dir_size(d)
                shutil.rmtree(d, ignore_errors=True)
                total_bytes -= sz
                removed += 1
        except Exception as exc:
            logger.debug("Research telemetry prune warning: %s", exc)
        return removed

    def get_status(self) -> dict[str, Any]:
        total_bytes = 0
        days: list[str] = []
        try:
            if self.base_dir.is_dir():
                days = sorted(
                    p.name for p in self.base_dir.iterdir()
                    if p.is_dir() and len(p.name) == 10 and p.name[4] == "-"
                )
                total_bytes = sum(f.stat().st_size for f in self.base_dir.rglob("*") if f.is_file())
        except Exception:
            pass
        return {
            "enabled": self._running,
            "base_dir": str(self.base_dir),
            "days_collected": days,
            "disk_usage_mb": round(total_bytes / (1024 * 1024), 2),
            "max_disk_mb": self.max_disk_mb,
            "retention_days": self.retention_days,
            "written_records": self._written_count,
            "crops_saved": self._crops_saved_count,
            "dropped_records": self._dropped_count,
            "anomalies_recorded": self._anomalies_count,
        }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def generate_research_summary_markdown(telemetry_dir: Path) -> str:
    """Aggregate collected JSONL diagnostics into a compact human/AI-readable Markdown report."""
    telemetry_dir = Path(telemetry_dir)
    lines: list[str] = ["# Smart Home 3D — Report Telemetria Produzione\n"]

    meta_path = telemetry_dir / "session_meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            host = meta.get("host") or {}
            lines.append("## 1. Ambiente & Host")
            lines.append(f"- Avvio raccolta: `{meta.get('started_iso', '?')}`")
            lines.append(f"- OS / CPU: `{host.get('platform', '?')}` | core logici: `{host.get('cpu_count_logical', '?')}` | `{host.get('processor', '')}`")
            lines.append(f"- RAM totale / libera all'avvio: `{host.get('ram_total_mb', '?')} MB` / `{host.get('ram_available_mb', '?')} MB`")
            rt = meta.get("runtime") or {}
            lines.append(f"- Runtime: Python `{rt.get('python')}`, OpenVINO `{rt.get('openvino')}`, ONNX Runtime `{rt.get('onnxruntime')}`\n")
        except Exception:
            pass

    day_dirs = sorted(
        [p for p in telemetry_dir.iterdir() if p.is_dir() and len(p.name) == 10 and p.name[4] == "-"],
        key=lambda p: p.name,
    ) if telemetry_dir.is_dir() else []

    if not day_dirs:
        lines.append("_Nessun giorno di telemetria presente._\n")
        return "\n".join(lines)

    health_rows: list[dict[str, Any]] = []
    lifecycle_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    anomaly_rows: list[dict[str, Any]] = []

    for d in day_dirs:
        health_rows.extend(_read_jsonl(d / "system_health.jsonl"))
        lifecycle_rows.extend(_read_jsonl(d / "track_lifecycle.jsonl"))
        event_rows.extend(_read_jsonl(d / "scene_events.jsonl"))
        sample_rows.extend(_read_jsonl(d / "biometrics_and_reid_samples.jsonl"))
        anomaly_rows.extend(_read_jsonl(d / "anomalies.jsonl"))

    lines.append(f"## 2. Copertura Temporale ({day_dirs[0].name} -> {day_dirs[-1].name})")
    lines.append(f"- Giorni raccolti: **{len(day_dirs)}** (`{', '.join(d.name for d in day_dirs)}`)")
    lines.append(f"- Campioni salute: **{len(health_rows)}** | Lifecycle tracce/slot: **{len(lifecycle_rows)}** | Episodi: **{len(event_rows)}** | Campioni crop/bio: **{len(sample_rows)}** | Anomalie: **{len(anomaly_rows)}**\n")

    # CPU/RAM & Camera latency
    cpus = [float(r["cpu_pct"]) for r in health_rows if r.get("cpu_pct") is not None]
    rams = [float(r["ram_pct"]) for r in health_rows if r.get("ram_pct") is not None]
    rss_vals = [float(r["rss_mb"]) for r in health_rows if r.get("rss_mb") is not None]
    lines.append("## 3. Risorse Sistema & Latenze Camere")
    if cpus:
        lines.append(f"- CPU %: p50=`{_percentile(cpus, 50)}%`, p95=`{_percentile(cpus, 95)}%`, max=`{round(max(cpus), 1)}%`")
    if rams:
        lines.append(f"- RAM %: p50=`{_percentile(rams, 50)}%`, max=`{round(max(rams), 1)}%` | RSS server p95=`{_percentile(rss_vals, 95)} MB`")

    cam_infer: dict[str, list[float]] = {}
    cam_tiers: dict[str, dict[str, int]] = {}
    for r in health_rows:
        for st in (r.get("cameras") or []):
            cid = str(st.get("camera_id") or "")
            if cid and st.get("last_infer_ms") is not None:
                cam_infer.setdefault(cid, []).append(float(st["last_infer_ms"]))
        sched = (r.get("fps_scheduler") or {}).get("cameras") or {}
        for cid, info in sched.items():
            tier = str(info.get("tier") or "idle")
            cam_tiers.setdefault(cid, {})
            cam_tiers[cid][tier] = cam_tiers[cid].get(tier, 0) + 1

    if cam_infer:
        lines.append("\n| Camera | Inferenza p50 (ms) | Inferenza p95 (ms) | Distribuzione tier FPS |")
        lines.append("|---|---:|---:|---|")
        for cid in sorted(cam_infer):
            vals = cam_infer[cid]
            tier_str = ", ".join(f"{k}:{v}" for k, v in sorted(cam_tiers.get(cid, {}).items())) or "-"
            lines.append(f"| `{cid}` | {_percentile(vals, 50)} | {_percentile(vals, 95)} | {tier_str} |")
    lines.append("")

    # Track lifecycle & Parked slots
    ev_counts: dict[str, int] = {}
    for r in lifecycle_rows:
        ev_k = str(r.get("event") or "unknown")
        ev_counts[ev_k] = ev_counts.get(ev_k, 0) + 1
    lines.append("## 4. Tracking, Re-ID & Posti Auto")
    if ev_counts:
        for k, v in sorted(ev_counts.items()):
            lines.append(f"- `{k}`: **{v}**")
    else:
        lines.append("- Nessuna transizione registrata.")
    lines.append("")

    # Crop statistics (Day vs Night IR, Person dimensions)
    crops = [r for r in sample_rows if r.get("kind") == "detection_crop"]
    person_crops = [r for r in crops if r.get("class_label") == "person"]
    day_p = [r for r in person_crops if not r.get("is_night_ir")]
    night_p = [r for r in person_crops if r.get("is_night_ir")]
    p_heights = [float((r.get("crop_wh") or [0, 0])[1]) for r in person_crops if r.get("crop_wh")]
    lines.append("## 5. Qualità Ritagli per Futura Re-ID (Giorno vs Notte IR)")
    lines.append(f"- Crop persona salvati: **{len(person_crops)}** (giorno RGB: **{len(day_p)}**, notte IR: **{len(night_p)}**)")
    if p_heights:
        ge64 = sum(1 for h in p_heights if h >= 64)
        lines.append(f"- Altezza ritaglio persona (substream): p50=`{_percentile(p_heights, 50)} px`, p95=`{_percentile(p_heights, 95)} px`, >=64px: **{ge64}/{len(p_heights)}** ({round(100.0 * ge64 / len(p_heights), 1)}%)")
    lines.append("")

    # Scene events & anomalies
    lines.append("## 6. Episodi Scena & Anomalie")
    imp_counts: dict[str, int] = {}
    durs: list[float] = []
    for r in event_rows:
        imp = str(r.get("importance") or "notable")
        imp_counts[imp] = imp_counts.get(imp, 0) + 1
        if r.get("lifecycle") == "closed":
            durs.append(float(r.get("duration_s") or 0.0))
    if imp_counts:
        lines.append("- Episodi per severità: " + ", ".join(f"`{k}`={v}" for k, v in sorted(imp_counts.items())))
    if durs:
        lines.append(f"- Durata episodi chiusi: p50=`{_percentile(durs, 50)}s`, p95=`{_percentile(durs, 95)}s`, max=`{round(max(durs), 1)}s`")
    anom_counts: dict[str, int] = {}
    for r in anomaly_rows:
        ak = str(r.get("anomaly") or "other")
        anom_counts[ak] = anom_counts.get(ak, 0) + 1
    if anom_counts:
        lines.append("- Anomalie rilevate: " + ", ".join(f"`{k}`={v}" for k, v in sorted(anom_counts.items())))
    else:
        lines.append("- Nessuna anomalia automatica rilevata.")
    lines.append("")
    return "\n".join(lines)
