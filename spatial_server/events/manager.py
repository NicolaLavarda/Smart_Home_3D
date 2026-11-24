from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Callable, Coroutine, Optional

import cv2
import httpx
import numpy as np

from spatial_server.domain.models import DetectionEvent, TrackedEntity3D
from spatial_server.persistence.interfaces import ITrackRepository
from .annotator import EventSnapshotStore
from .models import FrameBoxAnnotation, SceneEventRecord, SceneSubjectRecord, generate_event_id
from .narrator import build_scene_sentence_it, build_scene_title_it

logger = logging.getLogger("spatial_server.events.manager")

RELEVANT_EVENT_CLASSES = frozenset({"person", "car", "truck", "motorbike", "bicycle", "dog"})
_VEHICLE_CLASSES = frozenset({"car", "truck", "motorbike"})


def _friendly_camera_label(camera_id: str) -> str:
    clean = re.sub(r"^cam_", "", (camera_id or "").strip(), flags=re.IGNORECASE)
    return clean.replace("_", " ").strip() or camera_id


def _subject_label_and_category(subj: SceneSubjectRecord) -> tuple[str, str]:
    if subj.class_label == "person":
        if subj.identity and subj.identity.strip().lower() not in ("sconosciuto", "unknown", "none", "pending"):
            return subj.identity.strip(), "known"
        return "Sconosciuto", "unknown"

    if subj.class_label in _VEHICLE_CLASSES:
        plate = (subj.plate or "").strip().upper()
        owner = (subj.plate_owner or "").strip()
        if plate and subj.plate_whitelisted:
            label = f"{plate} · {owner}" if owner else plate
            return label, "plate_wl"
        if plate:
            return plate, "plate_guest"
        if subj.class_label == "motorbike":
            return "Moto", "object"
        if subj.class_label == "truck":
            return "Furgone", "object"
        return "Veicolo", "object"

    if subj.class_label == "dog":
        return "Animale", "object"
    if subj.class_label == "bicycle":
        return "Bicicletta", "object"
    return subj.class_label.title(), "object"


def _compute_importance(
    subjects: list[SceneSubjectRecord],
    *,
    existing_importance: str = "notable",
    alarm_state: Optional[str] = None,
) -> str:
    if existing_importance == "alert":
        return "alert"
    alarm_norm = (alarm_state or "").strip().lower()
    alarm_armed = bool(alarm_norm and alarm_norm not in ("off", "false", "0", "spento", "disarmed", "disarmato", "none"))
    has_unknown_person = any(
        s.class_label == "person"
        and (not s.identity or s.identity.strip().lower() in ("sconosciuto", "unknown", "none", "pending"))
        for s in subjects
    )
    if alarm_armed and has_unknown_person:
        return "alert"
    if has_unknown_person or any(s.plate and s.plate_whitelisted is False for s in subjects):
        return "notable"
    if any(s.identity or s.plate_whitelisted for s in subjects):
        return "routine"
    return "notable"


class SceneEventManager:
    """
    Aggregates multi-camera 3D tracks and biometric updates into unified `SceneEvent` episodes,
    ranks camera angles to capture the clearest cover frame, draws annotated boxes, and feeds
    the Daily Events UI + notification pipelines.
    """

    def __init__(
        self,
        repository: ITrackRepository,
        snapshot_store: EventSnapshotStore,
        *,
        inertia_s: float = 18.0,
        pre_roll_s: float = 3.0,
        go2rtc_http_base_url: str = "http://127.0.0.1:1984",
        stream_candidates_by_cam: Optional[dict[str, list[str]]] = None,
        panoramic_cameras: Optional[set[str]] = None,
        substream_frame_getter: Optional[Callable[[str], Optional[tuple[np.ndarray, float]]]] = None,
        broadcast_callback: Optional[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = None,
        on_snapshot_saved: Optional[Callable[[SceneEventRecord], Coroutine[Any, Any, None]]] = None,
        http_transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.repository = repository
        self.snapshot_store = snapshot_store
        self.inertia_s = max(2.0, float(inertia_s))
        self.pre_roll_s = max(0.0, float(pre_roll_s))
        self.go2rtc_http_base_url = (go2rtc_http_base_url or "http://127.0.0.1:1984").rstrip("/")
        self.stream_candidates_by_cam = dict(stream_candidates_by_cam or {})
        self.panoramic_cameras = set(panoramic_cameras or set())
        self.substream_frame_getter = substream_frame_getter
        self.broadcast_callback = broadcast_callback
        self.on_snapshot_saved = on_snapshot_saved

        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(2.0, connect=0.5),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            transport=http_transport,
        )
        self._active_event: Optional[SceneEventRecord] = None
        self._track_to_event_id: dict[int, str] = {}
        self._latest_cam_detections: dict[str, tuple[float, list[tuple[DetectionEvent, Optional[int]]]]] = {}
        self._last_snapshot_fetch_mono: float = 0.0
        self._pending_snapshot_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._pending_snapshot_task is not None and not self._pending_snapshot_task.done():
            self._pending_snapshot_task.cancel()
            try:
                await self._pending_snapshot_task
            except asyncio.CancelledError:
                pass
            self._pending_snapshot_task = None
        await self._http_client.aclose()

    def _is_panoramic(self, camera_id: str) -> bool:
        return camera_id in self.panoramic_cameras

    @staticmethod
    def compute_camera_frame_score(
        camera_id: str,
        is_panoramic: bool,
        dets_with_tracks: list[tuple[DetectionEvent, Optional[int]]],
        *,
        biometric_quality: float = 0.0,
        biometric_locked: bool = False,
    ) -> float:
        """
        Score how clear and informative a camera's current frame is as an episode cover.
        Prefers non-panoramic pinhole views, well-framed/centered subjects, multi-subject
        frames, and clear biometric reads.
        """
        if not dets_with_tracks:
            return 0.0

        cam_weight = 0.85 if is_panoramic else 1.35
        best_subj_score = 0.0

        for evt, _tid in dets_with_tracks:
            bw = max(0.0, float(evt.bbox.x_max - evt.bbox.x_min))
            bh = max(0.0, float(evt.bbox.y_max - evt.bbox.y_min))
            area = bw * bh
            u_center = 0.5 * (float(evt.bbox.x_min) + float(evt.bbox.x_max))

            # Ideal framing area around 0.04..0.28 of frame; penalize tiny or truncated
            area_score = min(1.5, area * 8.5)
            center_bonus = max(0.25, 1.0 - abs(u_center - 0.5) * 1.1)
            edge_penalty = 0.55 if (is_panoramic and (u_center < 0.12 or u_center > 0.88)) else 1.0
            clip_penalty = 0.7 if evt.bbox.y_max > 0.96 else 1.0

            subj_score = area_score * center_bonus * edge_penalty * clip_penalty * float(evt.confidence)
            if subj_score > best_subj_score:
                best_subj_score = subj_score

        multi_bonus = 0.35 * max(0, len(dets_with_tracks) - 1)
        bio_bonus = float(biometric_quality) * 2.5 + (1.0 if biometric_locked else 0.0)
        return round(cam_weight * (best_subj_score + multi_bonus) + bio_bonus, 4)

    def _build_boxes_for_camera(
        self,
        event: SceneEventRecord,
        camera_id: str,
        dets_with_tracks: list[tuple[DetectionEvent, Optional[int]]],
        *,
        bio_track_id: Optional[int] = None,
        bio_subject_bbox: Optional[tuple[float, float, float, float]] = None,
        bio_sub_bbox: Optional[tuple[float, float, float, float]] = None,
    ) -> list[FrameBoxAnnotation]:
        subj_by_tid = {s.track_id: s for s in event.subjects}
        boxes: list[FrameBoxAnnotation] = []
        seen_tids: set[int] = set()

        for evt, tid in dets_with_tracks:
            if tid is not None:
                seen_tids.add(tid)
            subj = subj_by_tid.get(tid) if tid is not None else None
            if subj is not None:
                label, category = _subject_label_and_category(subj)
            else:
                tmp = SceneSubjectRecord(
                    track_id=tid or 0,
                    class_label=evt.class_label,
                    identity=evt.sub_label,
                    plate=evt.plate,
                )
                label, category = _subject_label_and_category(tmp)

            sub_box = bio_sub_bbox if (tid is not None and tid == bio_track_id and bio_sub_bbox is not None) else None
            bbox_norm = (
                bio_subject_bbox
                if (tid is not None and tid == bio_track_id and bio_subject_bbox is not None)
                else (float(evt.bbox.x_min), float(evt.bbox.y_min), float(evt.bbox.x_max), float(evt.bbox.y_max))
            )
            boxes.append(
                FrameBoxAnnotation(
                    track_id=tid,
                    class_label=evt.class_label,
                    label=label,
                    category=category,  # type: ignore[arg-type]
                    bbox_norm=bbox_norm,
                    sub_bbox_norm=sub_box,
                )
            )

        if bio_track_id is not None and bio_track_id not in seen_tids and bio_subject_bbox is not None:
            subj = subj_by_tid.get(bio_track_id)
            if subj is not None:
                label, category = _subject_label_and_category(subj)
                boxes.append(
                    FrameBoxAnnotation(
                        track_id=bio_track_id,
                        class_label=subj.class_label,
                        label=label,
                        category=category,  # type: ignore[arg-type]
                        bbox_norm=bio_subject_bbox,
                        sub_bbox_norm=bio_sub_bbox,
                    )
                )
        return boxes

    @staticmethod
    def _refresh_boxes_labels(event: SceneEventRecord) -> list[FrameBoxAnnotation]:
        subj_by_tid = {s.track_id: s for s in event.subjects}
        updated: list[FrameBoxAnnotation] = []
        for box in event.best_frame_boxes:
            if box.track_id is not None and box.track_id in subj_by_tid:
                label, category = _subject_label_and_category(subj_by_tid[box.track_id])
                updated.append(box.model_copy(update={"label": label, "category": category}))
            else:
                updated.append(box)
        return updated

    @staticmethod
    def _refresh_narrative(event: SceneEventRecord, *, alarm_state: Optional[str] = None) -> None:
        event.duration_s = round(max(0.0, event.ended_at - event.started_at), 2)
        event.title = build_scene_title_it(
            event.subjects,
            zone_names=event.zones,
            camera_id=event.best_camera_id or (event.cameras[0] if event.cameras else None),
        )
        event.summary_it = build_scene_sentence_it(
            event.subjects,
            zone_names=event.zones,
            camera_id=event.best_camera_id or (event.cameras[0] if event.cameras else None),
        )
        event.importance = _compute_importance(  # type: ignore[assignment]
            event.subjects,
            existing_importance=event.importance,
            alarm_state=alarm_state or event.alarm_state,
        )

    async def on_detection_batch(
        self,
        events: list[DetectionEvent],
        active_tracks: list[TrackedEntity3D],
        obs_assignments: dict[int, int],
        now_ts: float,
        *,
        zones_by_track: Optional[dict[int, list[tuple[str, str]]]] = None,
        alarm_state: Optional[str] = None,
    ) -> Optional[SceneEventRecord]:
        relevant_events = [e for e in events if e.class_label in RELEVANT_EVENT_CLASSES]
        relevant_tracks = [t for t in active_tracks if t.class_label in RELEVANT_EVENT_CLASSES]
        if not relevant_events and not relevant_tracks:
            return self._active_event

        ts = float(now_ts)
        zones_map = zones_by_track or {}

        # Map each DetectionEvent in original batch order to assigned track_id if available
        event_to_tid: dict[int, int] = {}
        grounded_indices: list[int] = []
        for idx, evt in enumerate(events):
            if evt.class_label in RELEVANT_EVENT_CLASSES:
                grounded_indices.append(idx)
        for obs_idx, tid in obs_assignments.items():
            if 0 <= obs_idx < len(events):
                event_to_tid[id(events[obs_idx])] = tid

        by_cam: dict[str, list[tuple[DetectionEvent, Optional[int]]]] = {}
        for evt in relevant_events:
            tid = event_to_tid.get(id(evt))
            by_cam.setdefault(evt.camera_id, []).append((evt, tid))
        for cam_id, cam_dets in by_cam.items():
            self._latest_cam_detections[cam_id] = (ts, cam_dets)

        should_persist = False
        should_capture_cam: Optional[str] = None
        should_capture_score: float = 0.0
        should_capture_dets: list[tuple[DetectionEvent, Optional[int]]] = []

        async with self._lock:
            ev = self._active_event
            if ev is not None and (ts - ev.ended_at) > self.inertia_s:
                await self._close_active_event_locked()
                ev = None

            if ev is None:
                start_ts = min([ts, *[float(e.timestamp) for e in relevant_events]])
                ev = SceneEventRecord(
                    event_id=generate_event_id(start_ts),
                    status="active",
                    started_at=round(start_ts, 3),
                    ended_at=round(ts, 3),
                    replay_start_at=round(max(0.0, start_ts - self.pre_roll_s), 3),
                    alarm_state=alarm_state,
                )
                self._active_event = ev
                should_persist = True

            if ts > ev.ended_at:
                ev.ended_at = round(ts, 3)
            if alarm_state is not None:
                ev.alarm_state = alarm_state

            # Merge cameras from events & tracks
            cam_set = set(ev.cameras)
            for evt in relevant_events:
                cam_set.add(evt.camera_id)
            for tr in relevant_tracks:
                for c in tr.state.camera_sources:
                    cam_set.add(c)
            ev.cameras = sorted(cam_set)

            # Merge zones
            zname_set = list(ev.zones)
            zid_set = list(ev.zone_ids)
            for tid, z_pairs in zones_map.items():
                for zid, zname in z_pairs:
                    if zid and zid not in zid_set:
                        zid_set.append(zid)
                    if zname and zname not in zname_set:
                        zname_set.append(zname)
            ev.zone_ids = zid_set
            ev.zones = zname_set

            # Merge subjects by track_id
            subj_by_tid = {s.track_id: s for s in ev.subjects}
            for tr in relevant_tracks:
                self._track_to_event_id[tr.track_id] = ev.event_id
                tr_zones = [zname for _zid, zname in zones_map.get(tr.track_id, []) if zname]
                existing = subj_by_tid.get(tr.track_id)
                if existing is None:
                    subj = SceneSubjectRecord(
                        track_id=tr.track_id,
                        class_label=tr.class_label,
                        identity=tr.identity,
                        identity_confidence=float(tr.identity_confidence or 0.0),
                        plate=tr.plate,
                        plate_whitelisted=tr.plate_whitelisted,
                        plate_owner=tr.plate_owner,
                        biometric_status=tr.biometric_status,
                        best_crop_id=tr.best_crop_id,
                        first_seen=round(tr.last_seen, 3),
                        last_seen=round(tr.last_seen, 3),
                        cameras=list(tr.state.camera_sources),
                        zones=tr_zones,
                    )
                    subj_by_tid[tr.track_id] = subj
                    should_persist = True
                else:
                    changed = (
                        existing.identity != tr.identity
                        or existing.plate != tr.plate
                        or existing.plate_whitelisted != tr.plate_whitelisted
                        or existing.biometric_status != tr.biometric_status
                        or existing.best_crop_id != tr.best_crop_id
                    )
                    existing.last_seen = round(max(existing.last_seen, tr.last_seen), 3)
                    if tr.identity is not None:
                        existing.identity = tr.identity
                        existing.identity_confidence = max(existing.identity_confidence, float(tr.identity_confidence or 0.0))
                    if tr.plate is not None:
                        existing.plate = tr.plate
                        existing.plate_whitelisted = tr.plate_whitelisted
                        existing.plate_owner = tr.plate_owner
                    if tr.biometric_status != "none":
                        existing.biometric_status = tr.biometric_status
                    if tr.best_crop_id:
                        existing.best_crop_id = tr.best_crop_id
                    for c in tr.state.camera_sources:
                        if c not in existing.cameras:
                            existing.cameras.append(c)
                    for zn in tr_zones:
                        if zn not in existing.zones:
                            existing.zones.append(zn)
                    if changed:
                        should_persist = True

            ev.subjects = list(subj_by_tid.values())
            ev.track_ids = sorted(subj_by_tid.keys())
            self._refresh_narrative(ev, alarm_state=alarm_state)

            # Evaluate best camera angle for cover snapshot
            best_cam = None
            best_score = -1.0
            best_dets: list[tuple[DetectionEvent, Optional[int]]] = []
            for cam_id, cam_dets in by_cam.items():
                sc = self.compute_camera_frame_score(cam_id, self._is_panoramic(cam_id), cam_dets)
                if sc > best_score:
                    best_score = sc
                    best_cam = cam_id
                    best_dets = cam_dets

            now_mono = time.monotonic()
            needs_cover = ev.cover_raw_relpath is None
            improved_significantly = best_score > (ev.best_frame_score + 0.25)
            rate_ok = (now_mono - self._last_snapshot_fetch_mono) >= (0.4 if needs_cover else 1.8)

            if best_cam is not None and (needs_cover or improved_significantly) and rate_ok:
                if self._pending_snapshot_task is None or self._pending_snapshot_task.done():
                    self._last_snapshot_fetch_mono = now_mono
                    should_capture_cam = best_cam
                    should_capture_score = best_score
                    should_capture_dets = best_dets
                    if ev.best_camera_id is None:
                        ev.best_camera_id = best_cam

            if should_persist:
                self._persist_event(ev)

        if should_persist and ev is not None:
            await self._broadcast_event(ev)

        if should_capture_cam is not None and ev is not None:
            self._pending_snapshot_task = asyncio.create_task(
                self._capture_and_save_cover_async(
                    ev.event_id,
                    should_capture_cam,
                    should_capture_score,
                    should_capture_dets,
                    ts,
                )
            )
        return ev

    async def _capture_frame_bgr(self, camera_id: str) -> Optional[np.ndarray]:
        """Fetch JPEG from go2rtc HTTP API, or fall back to substream RAM frame."""
        streams = self.stream_candidates_by_cam.get(camera_id)
        if not streams:
            slug = re.sub(r"^cam_", "", camera_id, flags=re.IGNORECASE).lower()
            streams = [f"{slug}_snap", f"{slug}_main", f"{slug}_sub"]

        for stream_name in streams:
            try:
                resp = await self._http_client.get(
                    f"{self.go2rtc_http_base_url}/api/frame.jpeg",
                    params={"src": stream_name},
                )
                ctype = (resp.headers.get("content-type") or "").lower()
                if resp.status_code == 200 and ("image" in ctype or resp.content.startswith(b"\xff\xd8")):
                    buf = np.frombuffer(resp.content, dtype=np.uint8)
                    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                    if img is not None and img.size > 0:
                        return img
            except Exception:
                continue

        if self.substream_frame_getter is not None:
            res = self.substream_frame_getter(camera_id)
            if res is not None:
                frame, frame_ts = res
                if frame is not None and frame.size > 0 and (time.time() - frame_ts) <= 5.0:
                    return frame.copy()
        return None

    async def _capture_and_save_cover_async(
        self,
        event_id: str,
        camera_id: str,
        score: float,
        dets_with_tracks: list[tuple[DetectionEvent, Optional[int]]],
        ts: float,
    ) -> None:
        try:
            frame_bgr = await self._capture_frame_bgr(camera_id)
            if frame_bgr is None:
                return
            async with self._lock:
                ev = self._active_event
                if ev is None or ev.event_id != event_id:
                    return
                if ev.cover_raw_relpath is not None and score <= ev.best_frame_score:
                    return
                boxes = self._build_boxes_for_camera(ev, camera_id, dets_with_tracks)
                raw_rel, ann_rel = self.snapshot_store.save_event_snapshots(
                    ev.event_id,
                    frame_bgr,
                    boxes,
                    camera_label=_friendly_camera_label(camera_id),
                    timestamp=ts,
                )
                ev.best_camera_id = camera_id
                ev.best_frame_score = score
                ev.best_frame_ts = round(ts, 3)
                ev.best_frame_boxes = boxes
                ev.cover_raw_relpath = raw_rel
                ev.cover_ann_relpath = ann_rel
                self._refresh_narrative(ev)
                self._persist_event(ev)
            await self._broadcast_event(ev)
            if self.on_snapshot_saved is not None:
                await self.on_snapshot_saved(ev)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Snapshot capture failed for event %s (%s): %s", event_id, camera_id, exc)

    async def on_biometric_frame(
        self,
        *,
        track_id: int,
        camera_id: str,
        timestamp: float,
        full_frame_bgr: Optional[np.ndarray] = None,
        subject_bbox_norm: Optional[tuple[float, float, float, float]] = None,
        sub_bbox_norm: Optional[tuple[float, float, float, float]] = None,
        quality_score: float = 0.0,
        identity: Optional[str] = None,
        identity_confidence: float = 0.0,
        plate: Optional[str] = None,
        plate_whitelisted: Optional[bool] = None,
        plate_owner: Optional[str] = None,
        biometric_status: str = "pending",
        biometric_locked: bool = False,
        biometric_event_id: Optional[int] = None,
    ) -> Optional[SceneEventRecord]:
        """
        Zero-extra-fetch update triggered by BiometricWorkerService when face/ALPR completes.
        Upgrades cover frame if score improves AND re-annotates labels when identity locks.
        """
        notify_snap_ev: Optional[SceneEventRecord] = None
        updated_ev: Optional[SceneEventRecord] = None

        async with self._lock:
            ev = self._active_event
            if ev is None or track_id not in ev.track_ids:
                target_id = self._track_to_event_id.get(track_id)
                if ev is None or (target_id and ev.event_id != target_id):
                    ev = None

            if ev is None:
                return None

            subj = next((s for s in ev.subjects if s.track_id == track_id), None)
            if subj is None:
                return None

            if identity is not None:
                subj.identity = identity
                subj.identity_confidence = max(subj.identity_confidence, float(identity_confidence or 0.0))
            if plate is not None:
                subj.plate = plate
                subj.plate_whitelisted = plate_whitelisted
                subj.plate_owner = plate_owner
            subj.biometric_status = biometric_status
            if biometric_event_id is not None:
                subj.biometric_event_id = biometric_event_id

            recent = self._latest_cam_detections.get(camera_id)
            cam_dets = recent[1] if recent and (timestamp - recent[0]) <= 3.5 else []
            new_score = self.compute_camera_frame_score(
                camera_id,
                self._is_panoramic(camera_id),
                cam_dets,
                biometric_quality=quality_score,
                biometric_locked=biometric_locked,
            )
            if not cam_dets and full_frame_bgr is not None:
                cam_w = 0.85 if self._is_panoramic(camera_id) else 1.35
                new_score = round(cam_w + quality_score * 2.5 + (1.0 if biometric_locked else 0.0), 4)

            if full_frame_bgr is not None and (ev.cover_raw_relpath is None or new_score > ev.best_frame_score):
                boxes = self._build_boxes_for_camera(
                    ev,
                    camera_id,
                    cam_dets,
                    bio_track_id=track_id,
                    bio_subject_bbox=subject_bbox_norm,
                    bio_sub_bbox=sub_bbox_norm,
                )
                raw_rel, ann_rel = self.snapshot_store.save_event_snapshots(
                    ev.event_id,
                    full_frame_bgr,
                    boxes,
                    camera_label=_friendly_camera_label(camera_id),
                    timestamp=timestamp,
                )
                ev.best_camera_id = camera_id
                ev.best_frame_score = new_score
                ev.best_frame_ts = round(timestamp, 3)
                ev.best_frame_boxes = boxes
                ev.cover_raw_relpath = raw_rel
                ev.cover_ann_relpath = ann_rel
                notify_snap_ev = ev
            elif ev.cover_raw_relpath:
                ev.best_frame_boxes = self._refresh_boxes_labels(ev)
                ann_rel = self.snapshot_store.reannotate_event(
                    ev.event_id,
                    ev.cover_raw_relpath,
                    ev.best_frame_boxes,
                    camera_label=_friendly_camera_label(ev.best_camera_id or camera_id),
                    timestamp=ev.best_frame_ts or timestamp,
                )
                if ann_rel:
                    ev.cover_ann_relpath = ann_rel
                    notify_snap_ev = ev

            self._refresh_narrative(ev)
            self._persist_event(ev)
            updated_ev = ev

        if updated_ev is not None:
            await self._broadcast_event(updated_ev)
        if notify_snap_ev is not None and self.on_snapshot_saved is not None:
            await self.on_snapshot_saved(notify_snap_ev)
        return updated_ev

    async def on_hitl_review_updated(
        self,
        *,
        track_id: int,
        identity: Optional[str] = None,
        plate: Optional[str] = None,
        plate_whitelisted: Optional[bool] = None,
        plate_owner: Optional[str] = None,
        biometric_event_id: Optional[int] = None,
    ) -> Optional[SceneEventRecord]:
        """Update and re-annotate a SceneEvent (active or persisted) after Admin HITL review."""
        updated_ev: Optional[SceneEventRecord] = None
        async with self._lock:
            ev = self._active_event if (self._active_event and track_id in self._active_event.track_ids) else None
            if ev is None:
                row = self.repository.find_scene_event_by_track_id(track_id)
                if row is not None:
                    ev = SceneEventRecord.model_validate(row)
            if ev is None:
                return None

            for s in ev.subjects:
                if s.track_id == track_id:
                    if identity is not None:
                        s.identity = identity
                        s.identity_confidence = 1.0
                    if plate is not None:
                        s.plate = plate
                        s.plate_whitelisted = plate_whitelisted
                        s.plate_owner = plate_owner
                    s.biometric_status = "locked"
                    if biometric_event_id is not None:
                        s.biometric_event_id = biometric_event_id

            ev.reviewed = True
            ev.best_frame_boxes = self._refresh_boxes_labels(ev)
            if ev.cover_raw_relpath:
                ann_rel = self.snapshot_store.reannotate_event(
                    ev.event_id,
                    ev.cover_raw_relpath,
                    ev.best_frame_boxes,
                    camera_label=_friendly_camera_label(ev.best_camera_id or (ev.cameras[0] if ev.cameras else "")),
                    timestamp=ev.best_frame_ts or ev.started_at,
                )
                if ann_rel:
                    ev.cover_ann_relpath = ann_rel
            self._refresh_narrative(ev)
            self._persist_event(ev)
            updated_ev = ev

        if updated_ev is not None:
            await self._broadcast_event(updated_ev)
        return updated_ev

    async def mark_automation_triggered(
        self,
        event_id: Optional[str],
        rule_id: str,
        *,
        escalate_importance: Optional[str] = None,
    ) -> Optional[SceneEventRecord]:
        if not event_id:
            return None
        updated_ev: Optional[SceneEventRecord] = None
        async with self._lock:
            ev = self._active_event if (self._active_event and self._active_event.event_id == event_id) else None
            if ev is None:
                row = self.repository.get_scene_event(event_id)
                if row is not None:
                    ev = SceneEventRecord.model_validate(row)
            if ev is None:
                return None

            if rule_id and rule_id not in ev.automation_rule_ids:
                ev.automation_rule_ids.append(rule_id)
            if escalate_importance == "alert":
                ev.importance = "alert"
            self._persist_event(ev)
            updated_ev = ev

        if updated_ev is not None:
            await self._broadcast_event(updated_ev)
        return updated_ev

    async def tick(self, now_ts: Optional[float] = None) -> Optional[SceneEventRecord]:
        ts = float(now_ts if now_ts is not None else time.time())
        closed_ev: Optional[SceneEventRecord] = None
        async with self._lock:
            ev = self._active_event
            if ev is not None and (ts - ev.ended_at) >= self.inertia_s:
                closed_ev = await self._close_active_event_locked()
        if closed_ev is not None:
            await self._broadcast_event(closed_ev)
        return closed_ev

    async def _close_active_event_locked(self) -> Optional[SceneEventRecord]:
        ev = self._active_event
        if ev is None:
            return None
        ev.status = "closed"
        self._refresh_narrative(ev)
        self._persist_event(ev)
        self._active_event = None
        # Keep recent track->event mappings bounded
        if len(self._track_to_event_id) > 500:
            for k in list(self._track_to_event_id.keys())[:-200]:
                self._track_to_event_id.pop(k, None)
        return ev

    async def ensure_event_snapshot(
        self,
        event_id: str,
        *,
        preferred_camera_id: Optional[str] = None,
    ) -> Optional[SceneEventRecord]:
        """Ensure the event has a raw+annotated snapshot immediately (used right before notification dispatch)."""
        async with self._lock:
            ev = self._active_event if (self._active_event and self._active_event.event_id == event_id) else None
            if ev is None:
                row = self.repository.get_scene_event(event_id)
                if row is not None:
                    ev = SceneEventRecord.model_validate(row)
            if ev is None:
                return None
            if ev.cover_ann_relpath and ev.cover_raw_relpath:
                return ev
            cam_id = preferred_camera_id or ev.best_camera_id or (ev.cameras[0] if ev.cameras else None)
            if not cam_id:
                return ev
            recent = self._latest_cam_detections.get(cam_id)
            cam_dets = recent[1] if recent else []

        frame_bgr = await self._capture_frame_bgr(cam_id)
        if frame_bgr is None:
            return ev

        async with self._lock:
            target_ev = self._active_event if (self._active_event and self._active_event.event_id == event_id) else ev
            if target_ev.cover_raw_relpath:
                return target_ev
            boxes = self._build_boxes_for_camera(target_ev, cam_id, cam_dets)
            ts_val = target_ev.ended_at or time.time()
            raw_rel, ann_rel = self.snapshot_store.save_event_snapshots(
                target_ev.event_id,
                frame_bgr,
                boxes,
                camera_label=_friendly_camera_label(cam_id),
                timestamp=ts_val,
            )
            target_ev.best_camera_id = cam_id
            target_ev.best_frame_ts = round(ts_val, 3)
            target_ev.best_frame_boxes = boxes
            target_ev.cover_raw_relpath = raw_rel
            target_ev.cover_ann_relpath = ann_rel
            self._persist_event(target_ev)
        await self._broadcast_event(target_ev)
        if self.on_snapshot_saved is not None:
            await self.on_snapshot_saved(target_ev)
        return target_ev

    def get_active_scene_context(
        self,
        *,
        zone_id: Optional[str] = None,
        zone_name: Optional[str] = None,
        track: Optional[TrackedEntity3D] = None,
    ) -> dict[str, Any]:
        """Return live SceneEvent & subjects for AutomationEngineService templates and notifications."""
        ev = self._active_event
        if ev is None and track is not None:
            ev_id = self._track_to_event_id.get(track.track_id)
            if ev_id:
                row = self.repository.get_scene_event(ev_id)
                if row is not None:
                    ev = SceneEventRecord.model_validate(row)

        subjects: list[SceneSubjectRecord] = list(ev.subjects) if ev is not None else []
        if track is not None and not any(s.track_id == track.track_id for s in subjects):
            subjects.append(
                SceneSubjectRecord(
                    track_id=track.track_id,
                    class_label=track.class_label,
                    identity=track.identity,
                    identity_confidence=float(track.identity_confidence or 0.0),
                    plate=track.plate,
                    plate_whitelisted=track.plate_whitelisted,
                    plate_owner=track.plate_owner,
                    biometric_status=track.biometric_status,
                    best_crop_id=track.best_crop_id,
                    cameras=list(track.state.camera_sources),
                    zones=[zone_name] if zone_name else [],
                )
            )

        zone_subjects = subjects
        if zone_name:
            filtered = [s for s in subjects if any(z.lower() == zone_name.lower() for z in s.zones)]
            if filtered:
                zone_subjects = filtered

        best_cam = (
            (ev.best_camera_id if ev else None)
            or (track.state.camera_sources[0] if (track and track.state.camera_sources) else None)
            or (ev.cameras[0] if (ev and ev.cameras) else None)
        )
        return {
            "event": ev,
            "subjects": subjects,
            "zone_subjects": zone_subjects,
            "best_camera_id": best_cam,
        }

    def get_active_event(self) -> Optional[SceneEventRecord]:
        return self._active_event

    @staticmethod
    def enrich_with_nvr(events: list[dict[str, Any]], recording_archive: Any) -> list[dict[str, Any]]:
        """Annotate each SceneEvent API dict with `has_video_clip` / `has_hd_clip` if NVR archive is configured."""
        if not events or recording_archive is None or not getattr(recording_archive, "is_configured", False):
            return events

        for item in events:
            t0 = float(item.get("started_at") or 0.0)
            t1 = float(item.get("ended_at") or t0) + 1.0
            cams = item.get("cameras") or []
            has_sub = False
            has_hd = False
            for cam_id in cams:
                try:
                    segs = recording_archive.query_segments(cam_id, t0, t1)
                except Exception:
                    segs = []
                for s in segs:
                    has_sub = True
                    if getattr(s, "stream_tier", None) == "main" or getattr(s, "has_motion", False):
                        has_hd = True
                        break
                if has_hd:
                    break
            item["has_video_clip"] = has_sub or has_hd
            item["has_hd_clip"] = has_hd
        return events

    def _persist_event(self, ev: SceneEventRecord) -> None:
        self.repository.upsert_scene_event(ev.model_dump())

    async def _broadcast_event(self, ev: SceneEventRecord) -> None:
        if self.broadcast_callback is not None:
            try:
                await self.broadcast_callback(
                    {
                        "type": "scene_event_updated",
                        "event": ev.to_api_dict(),
                    }
                )
            except Exception as exc:
                logger.debug("SceneEvent broadcast error: %s", exc)
