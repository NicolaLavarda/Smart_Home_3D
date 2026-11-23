from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional
import numpy as np
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from spatial_server.automations import (
    AutomationEngineService,
    AutomationRuleDefinition,
    SpatialZoneDefinition,
    VirtualEntityDefinition,
)
from spatial_server.biometrics import (
    BiometricCropStore,
    BiometricEligibilityGate,
    BiometricJob,
    BiometricWorkerService,
    ExternalWebhookIdentityResolver,
    FaceGalleryIndex,
    Go2RtcSnapshotProvider,
    IBiometricCoordinator,
    IIdentityResolver,
    NoOpIdentityResolver,
    OnnxAlprRecognizer,
    OnnxInsightFaceRecognizer,
    OpenVINOInsightFaceResolver,
    PlateWhitelistEntry,
    PlateWhitelistMatcher,
    TrackBiometricConsensusManager,
    TrackBiometricUpdate,
)
from spatial_server.config import SpatialServerConfig, _normalize_ha_url
from spatial_server.security import (
    AuthError,
    HAUserPrincipal,
    HomeAssistantAuthVerifier,
    authenticate_websocket,
    clear_session_cookie,
    extract_bearer_token,
    require_admin_user,
    require_authenticated_user,
    set_session_cookie,
)
from spatial_server.domain.models import (
    CalibrationOverridePayload,
    DetectionEvent,
    SolvePnPRequest,
    TrackedEntity3D,
)
from spatial_server.geometry import ISpatialRaycaster, TrimeshGroundRaycaster
from spatial_server.ingestion import (
    IDetectionSource,
    MqttFrigateDetectionSource,
    OpenVINORtspDetectionSource,
    SyntheticWalkSimulatorSource,
)
from spatial_server.optics import (
    CameraCalibrationSolver,
    EquirectangularPanoramicOpticalModel,
    ICameraOpticalModel,
    PinholeRadTanOpticalModel,
    create_optical_model_from_manifest,
)
from spatial_server.optics.pinhole_model import matrix_gl_to_cv
from spatial_server.persistence import ITrackRepository, SQLiteWALTrackRepository
from spatial_server.recordings import FilesystemNvrArchiveRepository, IVideoArchiveRepository
from spatial_server.tracking import IMultiTargetTracker3D, Kalman3DMultiTracker, TrackObservation3D

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("spatial_server")


class IngestionModeRequest(BaseModel):
    mode: Literal["synthetic", "openvino", "mqtt", "hybrid"]


class AuthSessionRequest(BaseModel):
    token: Optional[str] = None


class BiometricEventAssignRequest(BaseModel):
    identity: Optional[str] = None
    enroll_crop: bool = True
    plate: Optional[str] = None
    add_to_whitelist: bool = False
    owner_name: Optional[str] = None
    vehicle_label: Optional[str] = None
    notes: Optional[str] = None


class PlateWhitelistUpsertRequest(BaseModel):
    plate: str
    owner_name: str
    vehicle_label: Optional[str] = None
    notes: Optional[str] = None


class VirtualEntityStateChangeRequest(BaseModel):
    state: Optional[str] = None
    operation: str = "set"
    attributes: Optional[dict[str, Any]] = None


class AutomationRuleToggleRequest(BaseModel):
    enabled: bool


class HaStatesSyncRequest(BaseModel):
    entities: dict[str, dict[str, Any]]
    trigger_on_diff: bool = True


@dataclass
class _PersistAnchor:
    x: float
    y: float
    z: float
    timestamp: float
    class_label: str
    identity: Optional[str]
    plate: Optional[str] = None
    biometric_locked: bool = False


class SpatialPipelineService:
    """Central SOLID orchestrator injecting optical, raycasting, biometric, tracking & storage strategies."""

    def __init__(
        self,
        config: SpatialServerConfig,
        optical_models: dict[str, ICameraOpticalModel],
        raycaster: ISpatialRaycaster,
        identity_resolver: IIdentityResolver,
        tracker: IMultiTargetTracker3D,
        repository: ITrackRepository,
        calibration_solver: CameraCalibrationSolver,
        camera_manifest_meta: Optional[dict[str, dict[str, Any]]] = None,
        saved_calibration_overrides: Optional[dict[str, dict[str, Any]]] = None,
        biometric_coordinator: Optional[IBiometricCoordinator] = None,
    ) -> None:
        self.config = config
        self.optical_models = optical_models
        self.raycaster = raycaster
        self.identity_resolver = identity_resolver
        self.tracker = tracker
        if hasattr(self.tracker, "camera_visibility_fn") and getattr(self.tracker, "camera_visibility_fn", None) is None:
            setattr(self.tracker, "camera_visibility_fn", self.is_world_point_visible_in_camera)
        self.repository = repository
        self.calibration_solver = calibration_solver
        self.camera_manifest_meta: dict[str, dict[str, Any]] = dict(camera_manifest_meta or {})
        self.saved_calibration_overrides: dict[str, dict[str, Any]] = {
            cam_id: dict(ov)
            for cam_id, ov in (saved_calibration_overrides or {}).items()
            if isinstance(ov, dict)
        }
        self.biometric_coordinator = biometric_coordinator
        if self.biometric_coordinator is not None:
            if getattr(self.biometric_coordinator, "on_result", None) is None:
                setattr(self.biometric_coordinator, "on_result", self._handle_biometric_update)
            snap_provider = getattr(self.biometric_coordinator, "snapshot_provider", None)
            if (
                snap_provider is not None
                and hasattr(snap_provider, "_substream_fallback_getter")
                and getattr(snap_provider, "_substream_fallback_getter", None) is None
            ):
                setattr(snap_provider, "_substream_fallback_getter", self.get_latest_substream_frame)

        self.ingestion_mode: str = config.default_ingestion_mode
        self.active_sources: list[IDetectionSource] = []
        self.ws_clients: set[WebSocket] = set()
        self._pending_persist: list[TrackedEntity3D] = []
        self._persist_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task[None]] = None
        self._pipeline_lock = asyncio.Lock()
        self.raw_detections_count: int = 0
        self.raycast_misses_count: int = 0
        self.last_detection_info: Optional[dict[str, Any]] = None
        self._last_miss_warn_ts: float = 0.0
        self._persist_anchors: dict[int, _PersistAnchor] = {}
        self.persist_saved_count: int = 0
        self.persist_skipped_count: int = 0
        self._lazy_crop_store: Optional[BiometricCropStore] = None
        self._lazy_face_gallery: Optional[FaceGalleryIndex] = None
        self._lazy_whitelist_matcher: Optional[PlateWhitelistMatcher] = None
        self.automation_engine = AutomationEngineService(
            config=self.config,
            repository=self.repository,
            broadcast_callback=self._broadcast_json,
            known_identities_provider=lambda: {str(x["name"]) for x in self.get_biometric_gallery_summary()},
            whitelisted_plates_provider=lambda: {str(x["plate"]) for x in self.repository.list_plate_whitelist()},
        )

    def get_optical_model(self, camera_id: str) -> Optional[ICameraOpticalModel]:
        return self.optical_models.get(camera_id)

    @staticmethod
    def _sanitize_ui_state(raw_state: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not isinstance(raw_state, dict):
            return None
        numeric_keys = (
            "offsetX",
            "offsetY",
            "offsetZ",
            "yawDeg",
            "pitchDeg",
            "rollDeg",
            "fovV",
            "fovH",
            "k1",
            "k2",
        )
        cleaned: dict[str, Any] = {}
        for key in numeric_keys:
            if key in raw_state:
                try:
                    val = float(raw_state[key])
                except (TypeError, ValueError):
                    continue
                if math.isfinite(val):
                    cleaned[key] = val
        if "flip180" in raw_state:
            cleaned["flip180"] = bool(raw_state["flip180"])
        return cleaned if cleaned else None

    def get_camera_calibration_metadata(self, camera_id: str) -> dict[str, Any]:
        model = self.optical_models[camera_id]
        meta = dict(model.to_metadata_dict())
        ov = self.saved_calibration_overrides.get(camera_id)
        if ov is not None:
            meta["is_calibrated"] = True
            if ov.get("updated_at") is not None:
                meta["updated_at"] = ov["updated_at"]
            ui_state = self._sanitize_ui_state(ov.get("ui_state"))
            if ui_state is not None:
                meta["ui_state"] = ui_state
        else:
            meta["is_calibrated"] = False
        return meta

    def get_all_camera_calibrations(self) -> dict[str, dict[str, Any]]:
        return {
            cam_id: self.get_camera_calibration_metadata(cam_id)
            for cam_id in self.optical_models
        }

    def save_camera_calibration_override(
        self,
        camera_id: str,
        ui_state: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        model = self.optical_models[camera_id]
        meta: dict[str, Any] = {
            **model.to_metadata_dict(),
            "is_calibrated": True,
            "updated_at": round(time.time(), 3),
        }
        cleaned_ui = self._sanitize_ui_state(ui_state)
        if cleaned_ui is not None:
            meta["ui_state"] = cleaned_ui
        self.calibration_solver.save_override(camera_id, meta)
        self.saved_calibration_overrides[camera_id] = dict(meta)
        return meta

    def reset_camera_calibration(self, camera_id: str) -> dict[str, Any]:
        cam_data = self.camera_manifest_meta.get(camera_id, {})
        self.optical_models[camera_id] = create_optical_model_from_manifest(camera_id, cam_data)
        self.saved_calibration_overrides.pop(camera_id, None)
        self.calibration_solver.delete_override(camera_id)
        return self.get_camera_calibration_metadata(camera_id)

    async def start(self) -> None:
        if self.config.dev_mode:
            logger.warning(
                "SH3D_DEV_MODE=true attivo (sviluppo locale: CORS localhost abilitato, auth_required=%s) — "
                "imposta SH3D_DEV_MODE=false in produzione!",
                self.config.auth_required,
            )
        if self.biometric_coordinator is not None:
            await self.biometric_coordinator.start()
        await self.automation_engine.start()
        self._flush_task = asyncio.create_task(self._db_flush_loop())
        await self.set_ingestion_mode(self.ingestion_mode)

    async def stop(self) -> None:
        await self._stop_sources()
        await self.automation_engine.stop()
        if self.biometric_coordinator is not None:
            try:
                await self.biometric_coordinator.stop()
            except Exception as exc:
                logger.warning("Error stopping biometric coordinator: %s", exc)
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        await self.flush_pending_to_db()

    async def _stop_sources(self) -> None:
        for src in self.active_sources:
            try:
                await src.stop()
            except Exception as exc:
                logger.warning("Error stopping source %s: %s", src.mode_name, exc)
        self.active_sources.clear()

    def _resolve_openvino_camera_targets(self) -> list[tuple[str, str]]:
        if self.config.openvino_camera_streams:
            configured = [
                (cam_id, url)
                for cam_id, url in self.config.openvino_camera_streams
                if not self.optical_models or cam_id in self.optical_models
            ]
            if configured:
                return configured

        base_rtsp = (self.config.go2rtc_rtsp_base_url or "rtsp://127.0.0.1:8554").rstrip("/")
        cam_ids = list(self.optical_models.keys()) or ["Cam_Carraio"]
        targets: list[tuple[str, str]] = []
        for cam_id in cam_ids:
            if cam_id == "Cam_Carraio":
                rtsp_url = self.config.go2rtc_rtsp_url or f"{base_rtsp}/carraio_sub"
                targets.append((cam_id, rtsp_url))
                continue

            meta = self.camera_manifest_meta.get(cam_id) or {}
            slug = re.sub(r"^cam_", "", cam_id, flags=re.IGNORECASE).lower()
            env_override = os.getenv(f"GO2RTC_RTSP_{slug.upper()}_SUB", "").strip()
            if env_override:
                rtsp_url = env_override
            else:
                sub_stream_id = (
                    str(meta.get("sub_stream_id") or "").strip()
                    or str(meta.get("stream_id") or "").strip()
                    or f"{slug}_sub"
                )
                rtsp_url = f"{base_rtsp}/{sub_stream_id}"
            targets.append((cam_id, rtsp_url))
        return targets

    def _build_openvino_sources(self) -> list[OpenVINORtspDetectionSource]:
        targets = self._resolve_openvino_camera_targets()
        if not targets:
            return []

        per_cam_fps = max(1.5, float(self.config.openvino_target_fps) / max(len(targets), 1))
        shared_lock = threading.Lock() if len(targets) > 1 else None
        sources: list[OpenVINORtspDetectionSource] = []
        shared_ov = None
        shared_backend: Optional[str] = None

        for idx, (cam_id, rtsp_url) in enumerate(targets):
            src = OpenVINORtspDetectionSource(
                rtsp_url=rtsp_url,
                camera_id=cam_id,
                openvino_device=self.config.openvino_device,
                model_path=self.config.openvino_model_path,
                target_fps=per_cam_fps,
                conf_threshold=self.config.openvino_conf_threshold,
                shared_compiled_ov=shared_ov if idx > 0 else None,
                shared_backend_name=shared_backend if idx > 0 else None,
                infer_lock=shared_lock,
                cpu_threads=self.config.openvino_cpu_threads,
            )
            if idx == 0 and src._compiled_ov is not None:
                shared_ov = src._compiled_ov
                shared_backend = src._backend_name
            sources.append(src)
        return sources

    def _build_openvino_source(self) -> OpenVINORtspDetectionSource:
        sources = self._build_openvino_sources()
        if sources:
            return sources[0]
        return OpenVINORtspDetectionSource(
            rtsp_url=self.config.go2rtc_rtsp_url,
            camera_id="Cam_Carraio",
            openvino_device=self.config.openvino_device,
            model_path=self.config.openvino_model_path,
            target_fps=self.config.openvino_target_fps,
            conf_threshold=self.config.openvino_conf_threshold,
            cpu_threads=self.config.openvino_cpu_threads,
        )

    def _build_mqtt_camera_alias_map(self) -> dict[str, str]:
        aliases: dict[str, str] = {
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
            "ingresso": "Cam_Ingresso",
            "camera.ingresso": "Cam_Ingresso",
            "camera.ingresso_scorrevole": "Cam_Ingresso",
            "ingresso_scorrevole": "Cam_Ingresso",
            "ingresso_main": "Cam_Ingresso",
            "ingresso_sub": "Cam_Ingresso",
            "Cam_Ingresso": "Cam_Ingresso",
            "stradina": "Cam_Stradina",
            "camera.stradina": "Cam_Stradina",
            "camera.stradina_scorrevole": "Cam_Stradina",
            "stradina_scorrevole": "Cam_Stradina",
            "stradina_main": "Cam_Stradina",
            "stradina_sub": "Cam_Stradina",
            "Cam_Stradina": "Cam_Stradina",
        }
        for cam_id in self.optical_models:
            aliases[cam_id] = cam_id
            slug = re.sub(r"^cam_", "", cam_id, flags=re.IGNORECASE).lower()
            if slug:
                aliases[slug] = cam_id
                aliases[f"camera.{slug}"] = cam_id
            meta = self.camera_manifest_meta.get(cam_id) or {}
            for key in ("ha_camera_entity", "stream_id", "sub_stream_id"):
                val = str(meta.get(key) or "").strip()
                if val:
                    aliases[val] = cam_id
                    if val.startswith("camera."):
                        aliases[val[len("camera."):]] = cam_id
        return aliases

    def _build_mqtt_source(self) -> MqttFrigateDetectionSource:
        return MqttFrigateDetectionSource(
            host=self.config.mqtt_host,
            port=self.config.mqtt_port,
            username=self.config.mqtt_user,
            password=self.config.mqtt_password,
            topic=self.config.mqtt_topic_prefix,
            camera_alias_map=self._build_mqtt_camera_alias_map(),
        )

    async def set_ingestion_mode(self, mode: str) -> list[str]:
        mode = mode.lower()
        next_sources: list[IDetectionSource]

        if mode == "synthetic":
            next_sources = [
                SyntheticWalkSimulatorSource(
                    camera_id="Cam_Carraio",
                    optical_model_getter=self.get_optical_model,
                    rate_hz=10.0,
                )
            ]
        elif mode == "openvino":
            next_sources = list(self._build_openvino_sources())
        elif mode == "mqtt":
            next_sources = [self._build_mqtt_source()]
        elif mode == "hybrid":
            next_sources = [
                *self._build_openvino_sources(),
                self._build_mqtt_source(),
            ]
        else:
            raise ValueError(f"Unsupported ingestion mode: {mode}")

        await self._stop_sources()
        self.ingestion_mode = mode
        self.active_sources = next_sources

        for src in self.active_sources:
            await src.start(self.process_detection_batch)

        details = [src.status_details() for src in self.active_sources]
        logger.info("Ingestion mode switched to '%s': %s", self.ingestion_mode, details)
        await self.broadcast_status()
        return details

    def get_latest_substream_frame(self, camera_id: str) -> Optional[tuple[np.ndarray, float]]:
        for src in self.active_sources:
            if getattr(src, "camera_id", None) == camera_id and hasattr(src, "get_latest_frame"):
                res = src.get_latest_frame()
                if res is not None:
                    return res
        return None

    def _is_camera_panoramic_180(self, camera_id: str) -> bool:
        model = self.optical_models.get(camera_id)
        if isinstance(model, EquirectangularPanoramicOpticalModel):
            return True
        meta = self.camera_manifest_meta.get(camera_id) or {}
        return bool(meta.get("is_panoramic_180") or meta.get("optical_model") == "equirectangular_180")

    def is_world_point_visible_in_camera(
        self,
        camera_id: str,
        point_3d: tuple[float, float, float],
    ) -> bool:
        model = self.optical_models.get(camera_id)
        if model is None:
            return False
        uv = model.world_point_to_pixel(point_3d)
        if uv is None:
            return False
        u, v = float(uv[0]), float(uv[1])
        return -0.05 <= u <= 1.05 and -0.05 <= v <= 1.05

    @staticmethod
    def _apply_vehicle_footprint_center_offset(
        class_label: str,
        hit_pt: tuple[float, float, float],
        ray_direction: tuple[float, float, float],
        v_norm: float,
    ) -> tuple[float, float, float]:
        """
        Shift the near-edge ground contact point (bottom-center of 2D bbox) slightly inward
        along the horizontal line-of-sight toward the 3D vehicle footprint centroid.
        Reduces cross-camera parallax when two cameras view opposite bumpers/sides of a car.
        """
        if class_label not in ("car", "truck", "motorbike"):
            return hit_pt
        if v_norm >= 0.965:
            return hit_pt
        dx, _dy, dz = float(ray_direction[0]), float(ray_direction[1]), float(ray_direction[2])
        horiz_norm = math.hypot(dx, dz)
        if horiz_norm < 1e-6:
            return hit_pt
        base_offset = 0.65 if class_label in ("car", "truck") else 0.25
        edge_taper = 1.0 if v_norm <= 0.88 else max(0.0, (0.965 - v_norm) / 0.085)
        shift = base_offset * edge_taper
        return (
            float(hit_pt[0] + (dx / horiz_norm) * shift),
            float(hit_pt[1]),
            float(hit_pt[2] + (dz / horiz_norm) * shift),
        )

    def _prune_biometric_consensus(self, active_tracks: list[TrackedEntity3D]) -> None:
        if self.biometric_coordinator is None:
            return
        consensus = getattr(self.biometric_coordinator, "consensus", None)
        if consensus is not None and hasattr(consensus, "prune_inactive_tracks"):
            consensus.prune_inactive_tracks({tr.track_id for tr in active_tracks})

    def _prune_stale_persist_anchors(self, active_tracks: list[TrackedEntity3D]) -> None:
        active_ids = {tr.track_id for tr in active_tracks}
        for tid in list(self._persist_anchors):
            if tid not in active_ids:
                del self._persist_anchors[tid]

    def _select_tracks_to_persist(self, active_tracks: list[TrackedEntity3D]) -> list[TrackedEntity3D]:
        """Deduplicate stationary targets against last persisted anchor (preventing slow drift loss)."""
        self._prune_stale_persist_anchors(active_tracks)
        if not active_tracks:
            return []

        min_disp = max(0.0, float(self.config.persist_min_displacement_m))
        heartbeat_s = max(0.0, float(self.config.persist_heartbeat_s))
        persistable: list[TrackedEntity3D] = []

        for tr in active_tracks:
            st = tr.state
            anchor = self._persist_anchors.get(tr.track_id)
            if anchor is None:
                should_save = True
            else:
                disp = math.dist((st.x, st.y, st.z), (anchor.x, anchor.y, anchor.z))
                dt = tr.last_seen - anchor.timestamp
                should_save = (
                    disp >= min_disp
                    or (heartbeat_s > 0.0 and (dt >= heartbeat_s or dt < 0.0))
                    or tr.identity != anchor.identity
                    or tr.plate != anchor.plate
                    or tr.biometric_locked != anchor.biometric_locked
                    or tr.class_label != anchor.class_label
                )

            if should_save:
                self._persist_anchors[tr.track_id] = _PersistAnchor(
                    x=st.x,
                    y=st.y,
                    z=st.z,
                    timestamp=tr.last_seen,
                    class_label=tr.class_label,
                    identity=tr.identity,
                    plate=tr.plate,
                    biometric_locked=tr.biometric_locked,
                )
                persistable.append(tr)
                self.persist_saved_count += 1
            else:
                self.persist_skipped_count += 1

        return persistable

    async def process_detection_batch(self, events: list[DetectionEvent]) -> list[TrackedEntity3D]:
        if not events:
            now_ts = time.time()
            async with self._pipeline_lock:
                active_tracks, _ = self.tracker.update_with_assignments([], now_ts)
            self._prune_biometric_consensus(active_tracks)
            self._prune_stale_persist_anchors(active_tracks)
            await self.broadcast_frame(active_tracks, now_ts)
            return active_tracks

        observations: list[TrackObservation3D] = []
        obs_meta: list[tuple[DetectionEvent, float]] = []
        now_ts = max(e.timestamp for e in events)
        self.raw_detections_count += len(events)

        for evt in events:
            model = self.optical_models.get(evt.camera_id)
            if model is None:
                continue

            u, v = evt.bbox.get_ground_contact_uv()
            ray = model.pixel_to_world_ray(u, v)
            hit_pt = self.raycaster.intersect_ground(ray)
            if hit_pt is None:
                self.raycast_misses_count += 1
                self.last_detection_info = {
                    "camera_id": evt.camera_id,
                    "class_label": evt.class_label,
                    "confidence": round(evt.confidence, 3),
                    "uv": [round(u, 3), round(v, 3)],
                    "hit_ground": False,
                    "timestamp": evt.timestamp,
                }
                now_mono = time.monotonic()
                if now_mono - self._last_miss_warn_ts >= 5.0:
                    self._last_miss_warn_ts = now_mono
                    logger.warning(
                        "Detection %s (conf=%.2f) at uv=(%.3f, %.3f) from %s missed ground mesh/plane (ray_dir=(%.3f, %.3f, %.3f))",
                        evt.class_label,
                        evt.confidence,
                        u,
                        v,
                        evt.camera_id,
                        ray.direction[0],
                        ray.direction[1],
                        ray.direction[2],
                    )
                continue

            self.last_detection_info = {
                "camera_id": evt.camera_id,
                "class_label": evt.class_label,
                "confidence": round(evt.confidence, 3),
                "uv": [round(u, 3), round(v, 3)],
                "hit_ground": True,
                "world_xyz": [round(hit_pt[0], 2), round(hit_pt[1], 2), round(hit_pt[2], 2)],
                "timestamp": evt.timestamp,
            }
            identity, id_conf = await self.identity_resolver.resolve_identity(evt)
            plate_val = evt.plate.strip().upper() if isinstance(evt.plate, str) and evt.plate.strip() else None
            plate_conf = (
                float(evt.plate_confidence)
                if evt.plate_confidence is not None
                else (0.85 if plate_val else 0.0)
            )
            obs_range_m = float(math.dist(ray.origin, hit_pt))
            is_pano = self._is_camera_panoramic_180(evt.camera_id)
            ray_grazing_sin = float(abs(ray.direction[1]))
            obs_pos = self._apply_vehicle_footprint_center_offset(
                evt.class_label,
                hit_pt,
                ray.direction,
                v,
            )
            observations.append(
                TrackObservation3D(
                    camera_id=evt.camera_id,
                    timestamp=evt.timestamp,
                    class_label=evt.class_label,
                    position=obs_pos,
                    confidence=evt.confidence,
                    identity=identity,
                    identity_confidence=id_conf,
                    plate=plate_val,
                    plate_confidence=plate_conf,
                    range_m=obs_range_m,
                    is_panoramic=is_pano,
                    uv_contact=(u, v),
                    bbox_2d=(evt.bbox.x_min, evt.bbox.y_min, evt.bbox.x_max, evt.bbox.y_max),
                    ray_grazing_sin=ray_grazing_sin,
                )
            )
            obs_meta.append((evt, obs_range_m))

        async with self._pipeline_lock:
            active_tracks, obs_assignments = self.tracker.update_with_assignments(observations, now_ts)

        self._prune_biometric_consensus(active_tracks)

        if self.biometric_coordinator is not None and obs_assignments:
            tracks_by_id = {tr.track_id: tr for tr in active_tracks}
            for obs_idx, track_id in obs_assignments.items():
                evt, obs_range_m = obs_meta[obs_idx]
                tr = tracks_by_id.get(track_id)
                if tr is None or tr.biometric_locked:
                    continue
                if evt.class_label not in ("person", "car", "truck", "motorbike"):
                    continue
                is_pano = self._is_camera_panoramic_180(evt.camera_id)
                job = BiometricJob(
                    track_id=track_id,
                    camera_id=evt.camera_id,
                    class_label=evt.class_label,
                    timestamp=evt.timestamp,
                    bbox=evt.bbox,
                    obs_range_m=obs_range_m,
                    world_xyz=(tr.state.x, tr.state.y, tr.state.z),
                    velocity_xyz=(tr.state.vx, tr.state.vy, tr.state.vz),
                    is_panoramic_180=is_pano,
                    camera_weight=0.75 if is_pano else 1.0,
                )
                self.biometric_coordinator.enqueue_candidate(job)

        persistable = self._select_tracks_to_persist(active_tracks)
        if persistable:
            async with self._persist_lock:
                self._pending_persist.extend(persistable)

        await self.broadcast_frame(active_tracks, now_ts)
        try:
            await self.automation_engine.on_tracks_updated(active_tracks, now_ts)
        except Exception as exc:
            logger.warning("Automation evaluation warning on tracks update: %s", exc)
        return active_tracks

    async def broadcast_biometric_event(
        self,
        update: TrackBiometricUpdate,
        *,
        event_id: Optional[int] = None,
    ) -> None:
        await self._broadcast_json(
            {
                "type": "biometric_event",
                "event_id": event_id,
                "timestamp": update.timestamp,
                "track_id": update.track_id,
                "modality": update.modality,
                "camera_id": update.camera_id,
                "identity": update.identity,
                "identity_confidence": update.identity_confidence,
                "plate": update.plate,
                "plate_raw": update.plate_raw,
                "plate_confidence": update.plate_confidence,
                "plate_format": update.plate_format,
                "plate_whitelisted": update.plate_whitelisted,
                "plate_owner": update.plate_owner,
                "biometric_locked": update.biometric_locked,
                "biometric_status": update.biometric_status,
                "attempts_count": update.attempts_count,
                "best_crop_id": update.best_crop_id,
                "crop_url": f"/api/v1/biometrics/crops/{update.best_crop_id}" if update.best_crop_id else None,
                "quality_score": update.quality_score,
            }
        )

    def _get_biometrics_data_dir(self) -> Path:
        return self.config.biometrics_data_dir or (self.config.data_dir / "biometrics")

    def get_biometric_crop_store(self) -> Optional[BiometricCropStore]:
        if self.biometric_coordinator is not None:
            consensus = getattr(self.biometric_coordinator, "consensus", None)
            store = getattr(consensus, "crop_store", None)
            if store is not None:
                return store
        bio_dir = self._get_biometrics_data_dir()
        if (bio_dir / "crops").is_dir():
            if self._lazy_crop_store is None or self._lazy_crop_store.base_dir != bio_dir:
                self._lazy_crop_store = BiometricCropStore(bio_dir)
            return self._lazy_crop_store
        return None

    def get_face_recognizer(self) -> Optional[OnnxInsightFaceRecognizer]:
        if self.biometric_coordinator is not None:
            face_rec = getattr(self.biometric_coordinator, "face_recognizer", None)
            if face_rec is not None and hasattr(face_rec, "is_ready") and face_rec.is_ready():
                return face_rec
        return None

    def get_face_gallery(self) -> FaceGalleryIndex:
        if self.biometric_coordinator is not None:
            face_rec = getattr(self.biometric_coordinator, "face_recognizer", None)
            gallery = getattr(face_rec, "gallery", None)
            if gallery is not None:
                return gallery
        gal_path = _resolve_face_gallery_path(
            self._get_biometrics_data_dir(),
            self.config.biometrics_face_rec_model,
        )
        if self._lazy_face_gallery is None or self._lazy_face_gallery.gallery_path != gal_path:
            self._lazy_face_gallery = FaceGalleryIndex(gal_path)
        return self._lazy_face_gallery

    def reload_face_gallery(self) -> FaceGalleryIndex:
        gal_path = _resolve_face_gallery_path(
            self._get_biometrics_data_dir(),
            self.config.biometrics_face_rec_model,
        )
        gallery = self.get_face_gallery()
        gallery.gallery_path = gal_path
        if gal_path.is_file():
            gallery.load(gal_path)
        else:
            with gallery._lock:
                gallery._clear_locked()
        return gallery

    def get_plate_whitelist_matcher(self) -> PlateWhitelistMatcher:
        if self.biometric_coordinator is not None:
            consensus = getattr(self.biometric_coordinator, "consensus", None)
            matcher = getattr(consensus, "whitelist_matcher", None)
            if matcher is not None:
                return matcher
        whitelist_path = self.config.biometrics_plates_whitelist_file or (
            self._get_biometrics_data_dir() / "plates_whitelist.json"
        )
        if self._lazy_whitelist_matcher is None or self._lazy_whitelist_matcher.json_path != whitelist_path:
            self._lazy_whitelist_matcher = PlateWhitelistMatcher(whitelist_path)
        return self._lazy_whitelist_matcher

    def sync_plate_whitelist_to_matcher_and_json(self) -> list[dict[str, Any]]:
        rows = self.repository.list_plate_whitelist()
        matcher = self.get_plate_whitelist_matcher()
        matcher.replace_all(
            [
                PlateWhitelistEntry(
                    plate=str(r["plate"]),
                    owner_name=str(r["owner_name"]),
                    vehicle_label=r.get("vehicle_label"),
                    notes=r.get("notes"),
                    updated_at=float(r.get("updated_at") or 0.0),
                )
                for r in rows
            ]
        )
        matcher.save_json()
        return rows

    @staticmethod
    def sanitize_biometric_event_row(row: dict[str, Any]) -> dict[str, Any]:
        item = {k: v for k, v in row.items() if k != "best_crop_relpath"}
        crop_id = item.get("best_crop_id")
        item["crop_url"] = f"/api/v1/biometrics/crops/{crop_id}" if crop_id else None
        return item

    async def propagate_biometric_review(
        self,
        *,
        track_id: int,
        modality: Literal["face", "alpr"],
        camera_id: str,
        event_id: int,
        event_ts: float,
        review_ts: float,
        identity: Optional[str] = None,
        identity_confidence: Optional[float] = None,
        plate: Optional[str] = None,
        plate_raw: Optional[str] = None,
        plate_confidence: Optional[float] = None,
        plate_format: Optional[str] = None,
        plate_whitelisted: Optional[bool] = None,
        plate_owner: Optional[str] = None,
        best_crop_id: Optional[str] = None,
        quality_score: float = 0.0,
    ) -> int:
        backfilled = self.repository.backfill_track_biometrics(
            track_id,
            min_timestamp=event_ts - 600.0,
            identity=identity,
            identity_confidence=identity_confidence,
            plate=plate,
            plate_confidence=plate_confidence,
            plate_whitelisted=plate_whitelisted,
            plate_owner=plate_owner,
            biometric_locked=True,
            best_crop_id=best_crop_id,
        )

        patch_fields: dict[str, Any] = {"biometric_locked": True, "biometric_status": "locked"}
        if identity is not None:
            patch_fields["identity"] = identity
        if identity_confidence is not None:
            patch_fields["identity_confidence"] = float(identity_confidence)
        if plate is not None:
            patch_fields["plate"] = plate
        if plate_confidence is not None:
            patch_fields["plate_confidence"] = float(plate_confidence)
        if plate_whitelisted is not None:
            patch_fields["plate_whitelisted"] = plate_whitelisted
        if plate_owner is not None:
            patch_fields["plate_owner"] = plate_owner
        if best_crop_id is not None:
            patch_fields["best_crop_id"] = best_crop_id

        async with self._persist_lock:
            self._pending_persist = [
                item.model_copy(update=patch_fields) if item.track_id == track_id else item
                for item in self._pending_persist
            ]

        manual_update = TrackBiometricUpdate(
            track_id=track_id,
            modality=modality,
            identity=identity,
            identity_confidence=float(identity_confidence or 0.0),
            plate=plate,
            plate_raw=plate_raw,
            plate_confidence=float(plate_confidence or 0.0),
            plate_format=plate_format,
            plate_whitelisted=plate_whitelisted,
            plate_owner=plate_owner,
            biometric_locked=True,
            biometric_status="locked",
            attempts_count=0,
            best_crop_id=best_crop_id,
            quality_score=quality_score,
            camera_id=camera_id,
            timestamp=review_ts,
        )

        async with self._pipeline_lock:
            updated_track = self.tracker.apply_biometric_result(manual_update)
            active_tracks = self.tracker.get_active_tracks()

        if updated_track is not None:
            await self.broadcast_frame(active_tracks, review_ts)
            await self.broadcast_biometric_event(manual_update, event_id=event_id)
            try:
                await self.automation_engine.on_biometric_update(
                    {
                        "track_id": track_id,
                        "modality": modality,
                        "camera_id": camera_id,
                        "identity": identity,
                        "plate": plate,
                        "plate_whitelisted": plate_whitelisted,
                    },
                    active_tracks,
                    review_ts,
                )
            except Exception as exc:
                logger.warning("Automation evaluation warning on HITL review: %s", exc)

        return backfilled

    def get_biometric_gallery_summary(self) -> list[dict[str, Any]]:
        gallery_items = self.get_face_gallery().list_identities()

        db_meta = {
            str(item["name"]).lower(): item
            for item in self.repository.list_face_identities_meta()
        }
        merged_by_key: dict[str, dict[str, Any]] = {}
        for g in gallery_items:
            name = str(g["name"])
            key = name.lower()
            meta = db_meta.get(key, {})
            merged_by_key[key] = {
                "name": name,
                "samples_count": int(g.get("samples_count", 0)),
                "events_count": int(meta.get("events_count", 0)),
                "last_seen": meta.get("last_seen"),
                "enrolled": True,
            }
        for key, meta in db_meta.items():
            if key not in merged_by_key:
                merged_by_key[key] = {
                    "name": str(meta["name"]),
                    "samples_count": int(meta.get("samples_count", 0)),
                    "events_count": int(meta.get("events_count", 0)),
                    "last_seen": meta.get("last_seen"),
                    "enrolled": int(meta.get("samples_count", 0)) > 0,
                }
        return sorted(merged_by_key.values(), key=lambda x: str(x["name"]).lower())

    def get_biometric_status_summary(self) -> dict[str, Any]:
        diag: dict[str, Any] = {"enabled": False, "running": False}
        if self.biometric_coordinator is not None:
            diag = {"enabled": True, **self.biometric_coordinator.get_diagnostics()}
            snap = getattr(self.biometric_coordinator, "snapshot_provider", None)
            if snap is not None and hasattr(snap, "get_diagnostics"):
                diag["snapshot_breakers"] = snap.get_diagnostics()
        identities = self.get_biometric_gallery_summary()
        plates = self.repository.list_plate_whitelist()
        crop_store = self.get_biometric_crop_store()
        crop_stats = crop_store.get_usage_stats() if crop_store is not None else {"files_count": 0, "total_mb": 0.0}
        diag["gallery_identities_count"] = len(identities)
        diag["gallery_samples_count"] = sum(int(item.get("samples_count", 0)) for item in identities)
        diag["plates_whitelist_count"] = len(plates)
        diag["crop_storage"] = {
            **crop_stats,
            "retention_days": self.config.biometrics_crop_retention_days,
            "max_disk_mb": self.config.biometrics_crop_max_mb,
        }
        return diag

    async def _handle_biometric_update(self, update: TrackBiometricUpdate) -> None:
        async with self._pipeline_lock:
            updated_track = self.tracker.apply_biometric_result(update)
            active_tracks = self.tracker.get_active_tracks()

        if updated_track is None:
            return

        event_id: Optional[int] = None
        if update.biometric_status in ("locked", "unknown"):
            loop = asyncio.get_running_loop()
            ev_payload = {
                "track_id": update.track_id,
                "modality": update.modality,
                "camera_id": update.camera_id,
                "timestamp": update.timestamp,
                "identity": update.identity,
                "identity_confidence": update.identity_confidence,
                "plate": update.plate,
                "plate_raw": update.plate_raw,
                "plate_confidence": update.plate_confidence,
                "plate_format": update.plate_format,
                "plate_whitelisted": update.plate_whitelisted,
                "plate_owner": update.plate_owner,
                "biometric_locked": update.biometric_locked,
                "biometric_status": update.biometric_status,
                "attempts_count": update.attempts_count,
                "quality_score": update.quality_score,
                "best_crop_id": update.best_crop_id,
                "best_crop_relpath": update.best_crop_relpath,
            }
            event_id = await loop.run_in_executor(None, self.repository.record_biometric_event, ev_payload)
            async with self._persist_lock:
                patch_fields = {
                    "identity": updated_track.identity,
                    "identity_confidence": updated_track.identity_confidence,
                    "plate": updated_track.plate,
                    "plate_confidence": updated_track.plate_confidence,
                    "plate_whitelisted": updated_track.plate_whitelisted,
                    "plate_owner": updated_track.plate_owner,
                    "biometric_locked": updated_track.biometric_locked,
                    "biometric_status": updated_track.biometric_status,
                    "best_crop_id": updated_track.best_crop_id,
                }
                self._pending_persist = [
                    item.model_copy(update=patch_fields) if item.track_id == update.track_id else item
                    for item in self._pending_persist
                ]
            await loop.run_in_executor(
                None,
                lambda: self.repository.backfill_track_biometrics(
                    update.track_id,
                    min_timestamp=update.timestamp - 600.0,
                    identity=updated_track.identity,
                    identity_confidence=updated_track.identity_confidence,
                    plate=updated_track.plate,
                    plate_confidence=updated_track.plate_confidence,
                    plate_whitelisted=updated_track.plate_whitelisted,
                    plate_owner=updated_track.plate_owner,
                    biometric_locked=updated_track.biometric_locked,
                    best_crop_id=updated_track.best_crop_id,
                ),
            )

        persistable = self._select_tracks_to_persist(active_tracks)
        if persistable:
            async with self._persist_lock:
                self._pending_persist.extend(persistable)

        await self.broadcast_frame(active_tracks, update.timestamp)
        if update.biometric_status in ("locked", "unknown"):
            await self.broadcast_biometric_event(update, event_id=event_id)
            try:
                await self.automation_engine.on_biometric_update(
                    {
                        "track_id": update.track_id,
                        "modality": update.modality,
                        "camera_id": update.camera_id,
                        "identity": update.identity,
                        "plate": update.plate,
                        "plate_whitelisted": update.plate_whitelisted,
                    },
                    active_tracks,
                    update.timestamp,
                )
            except Exception as exc:
                logger.warning("Automation evaluation warning on biometric update: %s", exc)

    async def _broadcast_json(self, message: dict[str, Any]) -> None:
        if not self.ws_clients:
            return
        payload = json.dumps(message)
        dead: list[WebSocket] = []
        for ws in list(self.ws_clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ws_clients.discard(ws)

    async def broadcast_status(self) -> None:
        await self._broadcast_json(
            {
                "type": "server_status",
                "ingestion_mode": self.ingestion_mode,
                "active_cameras": list(self.optical_models.keys()),
            }
        )

    async def broadcast_calibration_update(self, camera_id: str, calibration: dict[str, Any]) -> None:
        await self._broadcast_json(
            {
                "type": "calibration_updated",
                "camera_id": camera_id,
                "calibration": calibration,
            }
        )

    async def broadcast_frame(self, active_tracks: list[TrackedEntity3D], timestamp: float) -> None:
        await self._broadcast_json(
            {
                "type": "spatial_frame",
                "timestamp": timestamp,
                "ingestion_mode": self.ingestion_mode,
                "active_tracks": [tr.model_dump() for tr in active_tracks],
            }
        )

    async def flush_pending_to_db(self) -> int:
        async with self._persist_lock:
            if not self._pending_persist:
                return 0
            batch = self._pending_persist
            self._pending_persist = []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.repository.append_batch, batch)

    async def _db_flush_loop(self) -> None:
        last_prune = time.monotonic()
        while True:
            await asyncio.sleep(0.5)
            try:
                await self.flush_pending_to_db()
                if time.monotonic() - last_prune > 3600:
                    loop = asyncio.get_running_loop()
                    cutoff_tracks = time.time() - self.config.db_retention_days * 86400
                    await loop.run_in_executor(None, self.repository.prune_older_than, cutoff_tracks)

                    cutoff_bio = time.time() - self.config.biometrics_crop_retention_days * 86400
                    _del_events, relpaths = await loop.run_in_executor(
                        None, self.repository.prune_biometric_events_older_than, cutoff_bio
                    )
                    crop_store = self.get_biometric_crop_store()
                    if crop_store is not None:
                        await loop.run_in_executor(
                            None,
                            lambda: crop_store.prune(
                                retention_days=self.config.biometrics_crop_retention_days,
                                max_disk_mb=self.config.biometrics_crop_max_mb,
                                extra_relpaths=relpaths,
                            ),
                        )
                    last_prune = time.monotonic()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("SQLite WAL flush warning: %s", exc)


def _resolve_face_gallery_path(bio_data_dir: Path, rec_model_name: str) -> Path:
    default_path = bio_data_dir / "face_gallery.npz"
    if default_path.is_file():
        return default_path
    if "r50" in (rec_model_name or "").lower():
        r50_path = bio_data_dir / "face_gallery_r50.npz"
        if r50_path.is_file():
            return r50_path
    mbf_path = bio_data_dir / "face_gallery_mbf.npz"
    if mbf_path.is_file():
        return mbf_path
    return default_path


def _resolve_alpr_model_files(alpr_dir: Path, det_name: str, ocr_name: str) -> tuple[Path, Path, Path]:
    det_direct = alpr_dir / det_name
    if det_direct.is_file():
        det_path = det_direct
    else:
        det_sub = alpr_dir / det_name
        det_named = det_sub / f"{det_name}.onnx"
        if det_named.is_file():
            det_path = det_named
        else:
            onnx_cands = sorted(det_sub.glob("*.onnx")) if det_sub.is_dir() else []
            det_path = onnx_cands[0] if onnx_cands else det_named

    ocr_sub = alpr_dir / ocr_name
    ocr_onnx_cands = sorted(ocr_sub.glob("*.onnx")) if ocr_sub.is_dir() else []
    ocr_yaml_cands = sorted(list(ocr_sub.glob("*.yaml")) + list(ocr_sub.glob("*.yml"))) if ocr_sub.is_dir() else []
    ocr_path = ocr_onnx_cands[0] if ocr_onnx_cands else (ocr_sub / f"{ocr_name}.onnx")
    ocr_cfg_path = ocr_yaml_cands[0] if ocr_yaml_cands else (ocr_sub / f"{ocr_name}.yaml")
    return det_path, ocr_path, ocr_cfg_path


def _build_biometric_coordinator(
    cfg: SpatialServerConfig,
    optical_models: dict[str, ICameraOpticalModel],
    camera_manifest_meta: dict[str, dict[str, Any]],
    *,
    repository: Optional[ITrackRepository] = None,
) -> BiometricWorkerService:
    bio_data_dir = cfg.biometrics_data_dir or (cfg.data_dir / "biometrics")
    bio_data_dir.mkdir(parents=True, exist_ok=True)
    bio_models_dir = cfg.models_dir / "biometrics"

    stream_candidates_by_cam: dict[str, list[str]] = {}
    for cam_id in optical_models:
        meta = camera_manifest_meta.get(cam_id) or {}
        slug = re.sub(r"^cam_", "", cam_id, flags=re.IGNORECASE).lower()
        snap_stream = str(meta.get("snap_stream_id") or "").strip() or f"{slug}_snap"
        main_stream = str(meta.get("stream_id") or "").strip() or f"{slug}_main"
        cands = [snap_stream]
        if main_stream and main_stream != snap_stream:
            cands.append(main_stream)
        stream_candidates_by_cam[cam_id] = cands

    snapshot_provider = Go2RtcSnapshotProvider(
        cfg.go2rtc_http_base_url,
        stream_candidates_by_cam=stream_candidates_by_cam,
        timeout_s=cfg.biometrics_snapshot_timeout_s,
        panoramic_max_decode_width=cfg.biometrics_panoramic_max_width,
    )
    crop_store = BiometricCropStore(bio_data_dir)
    whitelist_path = cfg.biometrics_plates_whitelist_file or (bio_data_dir / "plates_whitelist.json")
    whitelist_matcher = PlateWhitelistMatcher(whitelist_path)
    if repository is not None:
        db_plates = {row["plate"]: row for row in repository.list_plate_whitelist()}
        for entry in whitelist_matcher.list_entries():
            if entry.plate not in db_plates:
                row = repository.upsert_plate_whitelist(
                    entry.plate,
                    entry.owner_name,
                    vehicle_label=entry.vehicle_label,
                    notes=entry.notes,
                    updated_at=entry.updated_at or time.time(),
                )
                db_plates[entry.plate] = row
        if db_plates:
            whitelist_matcher.replace_all(
                [
                    PlateWhitelistEntry(
                        plate=str(r["plate"]),
                        owner_name=str(r["owner_name"]),
                        vehicle_label=r.get("vehicle_label"),
                        notes=r.get("notes"),
                        updated_at=float(r.get("updated_at") or 0.0),
                    )
                    for r in db_plates.values()
                ]
            )
    consensus = TrackBiometricConsensusManager(
        crop_store=crop_store,
        whitelist_matcher=whitelist_matcher,
        face_consensus_k=cfg.biometrics_face_consensus_k,
        alpr_consensus_k=cfg.biometrics_alpr_consensus_k,
        min_eval_interval_s=cfg.biometrics_min_eval_interval_s,
        max_fast_attempts=cfg.biometrics_max_attempts_per_track,
        unknown_backoff_s=cfg.biometrics_unknown_backoff_s,
        whitelist_max_distance=cfg.biometrics_alpr_whitelist_max_dist,
    )

    cam_rules: dict[str, dict[str, float]] = {}
    for cam_id, modality, max_range_m in cfg.biometrics_camera_rules:
        cam_rules.setdefault(cam_id, {})[modality] = max_range_m

    gate = BiometricEligibilityGate(
        face_enabled=cfg.biometrics_face_enabled,
        alpr_enabled=cfg.biometrics_alpr_enabled,
        face_max_range_m=cfg.biometrics_face_max_range_m,
        alpr_max_range_m=cfg.biometrics_alpr_max_range_m,
        panoramic_edge_margin_u=cfg.biometrics_panoramic_edge_margin_u,
        camera_rules=cam_rules,
    )

    face_recognizer: Optional[OnnxInsightFaceRecognizer] = None
    if cfg.biometrics_face_enabled:
        gallery_path = _resolve_face_gallery_path(bio_data_dir, cfg.biometrics_face_rec_model)
        gallery = FaceGalleryIndex(gallery_path)
        face_dir = bio_models_dir / "face"
        face_recognizer = OnnxInsightFaceRecognizer(
            face_dir / cfg.biometrics_face_det_model,
            face_dir / cfg.biometrics_face_rec_model,
            gallery,
            provider_name=cfg.biometrics_onnx_provider,
            intra_threads=cfg.biometrics_onnx_intra_threads,
            inter_threads=cfg.biometrics_onnx_inter_threads,
            min_face_width_px=cfg.biometrics_face_min_width_px,
            min_laplacian=cfg.biometrics_face_min_laplacian,
            max_yaw_ratio=cfg.biometrics_face_max_yaw_ratio,
            match_threshold=cfg.biometrics_face_match_threshold,
            margin_threshold=cfg.biometrics_face_margin_threshold,
        )

    plate_recognizer: Optional[OnnxAlprRecognizer] = None
    if cfg.biometrics_alpr_enabled:
        det_path, ocr_path, ocr_cfg_path = _resolve_alpr_model_files(
            bio_models_dir / "alpr",
            cfg.biometrics_alpr_det_model,
            cfg.biometrics_alpr_ocr_model,
        )
        plate_recognizer = OnnxAlprRecognizer(
            det_path,
            ocr_path,
            ocr_cfg_path,
            provider_name=cfg.biometrics_onnx_provider,
            intra_threads=cfg.biometrics_onnx_intra_threads,
            inter_threads=cfg.biometrics_onnx_inter_threads,
            min_plate_width_px=cfg.biometrics_alpr_min_plate_width_px,
        )

    return BiometricWorkerService(
        snapshot_provider=snapshot_provider,
        consensus=consensus,
        gate=gate,
        face_recognizer=face_recognizer,
        plate_recognizer=plate_recognizer,
        queue_maxsize=cfg.biometrics_queue_maxsize,
    )


def build_pipeline_service(config: Optional[SpatialServerConfig] = None) -> SpatialPipelineService:
    cfg = config or SpatialServerConfig.from_env()
    manifest = json.loads(cfg.manifest_path.read_text(encoding="utf-8")) if cfg.manifest_path.exists() else {}

    calib_solver = CameraCalibrationSolver(cfg.calibration_override_path)
    saved_overrides = calib_solver.load_all_overrides()

    optical_models: dict[str, ICameraOpticalModel] = {}
    camera_manifest_meta: dict[str, dict[str, Any]] = {}
    for cam_id, cam_data in manifest.get("cameras", {}).items():
        if cam_data.get("is_real_security_camera") or cam_data.get("ha_camera_entity") or cam_id == "Cam_Carraio":
            model = create_optical_model_from_manifest(cam_id, cam_data)
            if cam_id in saved_overrides:
                ov = saved_overrides[cam_id]
                model.update_calibration(
                    extrinsic_cv_to_world=ov.get("extrinsic_cv_to_world"),
                    fov_h_deg=ov.get("fov_h_deg"),
                    fov_v_deg=ov.get("fov_v_deg"),
                    distortion_coeffs=ov.get("distortion_coeffs"),
                )
            optical_models[cam_id] = model
            camera_manifest_meta[cam_id] = cam_data

    raycaster = TrimeshGroundRaycaster(cfg.glb_path, cfg.manifest_path)
    repository = SQLiteWALTrackRepository(cfg.sqlite_db_path)

    biometric_coordinator: Optional[IBiometricCoordinator] = None
    if cfg.biometrics_enabled:
        biometric_coordinator = _build_biometric_coordinator(
            cfg,
            optical_models,
            camera_manifest_meta,
            repository=repository,
        )

    if cfg.face_webhook_url:
        identity_resolver: IIdentityResolver = ExternalWebhookIdentityResolver(cfg.face_webhook_url)
    elif not cfg.biometrics_enabled and (cfg.models_dir / "face_gallery").exists():
        identity_resolver = OpenVINOInsightFaceResolver(cfg.models_dir / "face_gallery")
    else:
        identity_resolver = NoOpIdentityResolver()

    tracker = Kalman3DMultiTracker(initial_next_track_id=repository.get_max_track_id() + 1)

    return SpatialPipelineService(
        config=cfg,
        optical_models=optical_models,
        raycaster=raycaster,
        identity_resolver=identity_resolver,
        tracker=tracker,
        repository=repository,
        calibration_solver=calib_solver,
        camera_manifest_meta=camera_manifest_meta,
        saved_calibration_overrides=saved_overrides,
        biometric_coordinator=biometric_coordinator,
    )


def create_app(config: Optional[SpatialServerConfig] = None) -> FastAPI:
    service = build_pipeline_service(config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await service.start()
        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(
        title="Smart Home 3D Spatial CV Microservice",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(service.config.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.pipeline = service
    app.state.config = service.config
    app.state.auth_verifier = HomeAssistantAuthVerifier.from_config(service.config)
    app.state.recording_archive: IVideoArchiveRepository = FilesystemNvrArchiveRepository(
        storage_dir=service.config.nvr_storage_dir
    )

    @app.post("/api/v1/auth/session")
    async def create_auth_session(
        request: Request,
        response: Response,
        payload: Optional[AuthSessionRequest] = Body(default=None),
    ) -> dict[str, Any]:
        token = extract_bearer_token(request.headers) or (
            payload.token.strip() if payload and payload.token else ""
        )
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Token Home Assistant mancante",
                headers={"WWW-Authenticate": "Bearer"},
            )

        verifier: HomeAssistantAuthVerifier = request.app.state.auth_verifier
        try:
            principal = await verifier.verify_token(token)
        except AuthError as exc:
            raise HTTPException(
                status_code=401,
                detail="Token Home Assistant non valido",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        cookie_value, session_expires_at = verifier.create_session_token(principal)
        max_age_s = max(1, int(session_expires_at - time.time()))
        set_session_cookie(response, request, cookie_value, max_age_s)
        response.headers["Cache-Control"] = "no-store"
        return {
            "authenticated": True,
            "user": principal.to_user_dict(),
            "expires_at": session_expires_at,
        }

    @app.get("/api/v1/auth/verify")
    async def verify_auth_session(
        response: Response,
        user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        safe_user_id = re.sub(r"[\r\n]+", "", user.user_id)
        response.headers["X-SH3D-User"] = safe_user_id
        response.headers["X-SH3D-Admin"] = "true" if user.is_privileged else "false"
        response.headers["Cache-Control"] = "no-store"
        return {
            "authenticated": True,
            "user": user.to_user_dict(),
            "expires_at": user.expires_at,
        }

    @app.post("/api/v1/auth/logout")
    async def logout_auth_session(
        request: Request,
        response: Response,
    ) -> dict[str, Any]:
        clear_session_cookie(response, request)
        response.headers["Cache-Control"] = "no-store"
        return {"authenticated": False, "logged_out": True}

    @app.get("/api/v1/status")
    async def get_status(
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        rc = service.raycaster
        repo = service.repository
        bio_diag: dict[str, Any] = {"enabled": False, "running": False}
        if service.biometric_coordinator is not None:
            bio_diag = {"enabled": True, **service.biometric_coordinator.get_diagnostics()}
        return {
            "status": "ok",
            "dev_mode": service.config.dev_mode,
            "ingestion_mode": service.ingestion_mode,
            "source_details": [s.status_details() for s in service.active_sources],
            "active_cameras": list(service.optical_models.keys()),
            "ground_colliders_count": len(getattr(rc, "matched_nodes", [])),
            "ground_triangles_count": len(rc.ground_mesh.faces) if getattr(rc, "ground_mesh", None) is not None else 0,
            "sqlite_journal_mode": repo.get_journal_mode() if isinstance(repo, SQLiteWALTrackRepository) else "custom",
            "sqlite_has_rtree": bool(getattr(repo, "has_rtree", False)),
            "active_tracks_count": len(service.tracker.get_active_tracks()),
            "connected_clients": len(service.ws_clients),
            "raw_detections_count": service.raw_detections_count,
            "raycast_misses_count": service.raycast_misses_count,
            "persist_saved_count": service.persist_saved_count,
            "persist_skipped_count": service.persist_skipped_count,
            "last_detection": service.last_detection_info,
            "biometrics": bio_diag,
        }

    @app.get("/api/v1/tracks")
    async def get_tracks(
        t_start: float = Query(...),
        t_end: float = Query(...),
        classes: Optional[str] = Query(default=None),
        min_x: Optional[float] = Query(default=None),
        max_x: Optional[float] = Query(default=None),
        min_z: Optional[float] = Query(default=None),
        max_z: Optional[float] = Query(default=None),
        limit: int = Query(default=5000, ge=1, le=20000),
        identity: Optional[str] = Query(default=None),
        plate: Optional[str] = Query(default=None),
        unknown_only: bool = Query(default=False),
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        cls_list = [c.strip() for c in classes.split(",") if c.strip()] if classes else None
        zone_bbox = None
        if None not in (min_x, max_x, min_z, max_z):
            zone_bbox = (float(min_x), float(max_x), float(min_z), float(max_z))

        rows = service.repository.query_time_range(
            t_start,
            t_end,
            classes=cls_list,
            zone_bbox=zone_bbox,
            limit=limit,
            identity=identity,
            plate=plate,
            unknown_only=unknown_only,
        )
        t_min = rows[0]["timestamp"] if rows else None
        t_max = rows[-1]["timestamp"] if rows else None
        return {
            "status": "ok",
            "count": len(rows),
            "t_min": t_min,
            "t_max": t_max,
            "detections": rows,
        }

    @app.get("/api/v1/biometrics/status")
    async def get_biometrics_status(
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", **service.get_biometric_status_summary()}

    @app.get("/api/v1/biometrics/events")
    async def get_biometrics_events(
        response: Response,
        t_start: Optional[float] = Query(default=None),
        t_end: Optional[float] = Query(default=None),
        modality: Optional[str] = Query(default=None),
        status: Optional[str] = Query(default=None),
        identity: Optional[str] = Query(default=None),
        plate: Optional[str] = Query(default=None),
        track_id: Optional[int] = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        rows = service.repository.query_biometric_events(
            t_start,
            t_end,
            modality=modality,
            status=status,
            identity=identity,
            plate=plate,
            track_id=track_id,
            limit=limit,
        )
        sanitized = [service.sanitize_biometric_event_row(row) for row in rows]
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "count": len(sanitized), "events": sanitized}

    @app.get("/api/v1/biometrics/crops/{crop_id}")
    async def get_biometrics_crop_image(
        crop_id: str,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> FileResponse:
        if not BiometricCropStore.is_valid_crop_id(crop_id):
            raise HTTPException(status_code=400, detail="crop_id non valido")
        crop_store = service.get_biometric_crop_store()
        if crop_store is None:
            raise HTTPException(status_code=404, detail="Crop biometrico non trovato")
        known_relpath = service.repository.get_crop_relpath(crop_id)
        crop_path = crop_store.resolve_crop_path(crop_id, known_relpath=known_relpath)
        if crop_path is None or not crop_path.is_file():
            raise HTTPException(status_code=404, detail="Crop biometrico non trovato")
        return FileResponse(
            path=crop_path,
            media_type="image/jpeg",
            filename=crop_path.name,
            headers={
                "Cache-Control": "private, max-age=300",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/v1/biometrics/identities")
    async def get_biometrics_identities(
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        identities = service.get_biometric_gallery_summary()
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "count": len(identities), "identities": identities}

    @app.get("/api/v1/biometrics/plates")
    async def get_biometrics_plates(
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        plates = service.repository.list_plate_whitelist()
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "count": len(plates), "plates": plates}

    @app.post("/api/v1/biometrics/events/{event_id}/assign")
    async def assign_biometric_event_hitl(
        event_id: int,
        payload: BiometricEventAssignRequest,
        response: Response,
        admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        ev = service.repository.get_biometric_event(event_id)
        if ev is None:
            raise HTTPException(status_code=404, detail="Evento biometrico non trovato")

        reviewer = re.sub(r"[\r\n]+", " ", (admin.name or admin.user_id or "admin")).strip() or "admin"
        now_ts = time.time()
        modality = str(ev["modality"]).lower()
        enrolled_sample = False
        enroll_note: Optional[str] = None
        backfilled_rows = 0

        if modality == "face":
            clean_identity = re.sub(r"[\r\n\t]+", " ", (payload.identity or "")).strip()
            if not clean_identity or len(clean_identity) > 64:
                raise HTTPException(status_code=400, detail="identity non valida")

            if payload.enroll_crop:
                crop_id = ev.get("best_crop_id")
                crop_store = service.get_biometric_crop_store()
                face_rec = service.get_face_recognizer()
                if face_rec is None:
                    enroll_note = "Riconoscitore volti non attivo; etichetta evento salvata senza embedding"
                elif not crop_id or crop_store is None:
                    enroll_note = "Crop non disponibile; etichetta evento salvata senza embedding"
                else:
                    crop_path = crop_store.resolve_crop_path(
                        str(crop_id),
                        known_relpath=ev.get("best_crop_relpath"),
                    )
                    if crop_path is None or not crop_path.is_file():
                        enroll_note = "File crop non trovato; etichetta evento salvata senza embedding"
                    else:
                        import cv2

                        raw_bytes = crop_path.read_bytes()
                        crop_bgr = cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if crop_bgr is None or crop_bgr.size == 0:
                            enroll_note = "Crop JPEG non decodificabile; etichetta evento salvata senza embedding"
                        else:
                            loop = asyncio.get_running_loop()
                            extracted = await loop.run_in_executor(
                                None,
                                lambda: face_rec.extract_face_embedding(crop_bgr, bypass_quality_gate=True),
                            )
                            if extracted is not None:
                                emb, _metrics, _thumb = extracted
                                quality = max(0.5, float(ev.get("quality_score") or 0.7))
                                service.get_face_gallery().add_embedding(
                                    clean_identity,
                                    emb,
                                    quality=quality,
                                    persist=True,
                                )
                                service.repository.add_face_embedding(
                                    clean_identity,
                                    service.config.biometrics_face_rec_model,
                                    emb.astype(np.float32).tobytes(),
                                    quality_score=quality,
                                    source="hitl",
                                    created_at=now_ts,
                                )
                                enrolled_sample = True
                            else:
                                enroll_note = "Volto non rilevabile nel crop; etichetta evento salvata senza embedding"

            updated = service.repository.update_biometric_event_review(
                event_id,
                identity=clean_identity,
                identity_confidence=1.0,
                biometric_locked=True,
                biometric_status="locked",
                reviewed_by=reviewer,
                reviewed_at=now_ts,
            )
            backfilled_rows = await service.propagate_biometric_review(
                track_id=int(ev["track_id"]),
                modality="face",
                camera_id=str(ev["camera_id"]),
                event_id=event_id,
                event_ts=float(ev["timestamp"]),
                review_ts=now_ts,
                identity=clean_identity,
                identity_confidence=1.0,
                best_crop_id=ev.get("best_crop_id"),
                quality_score=float(ev.get("quality_score") or 0.0),
            )
        elif modality == "alpr":
            raw_plate = payload.plate or ev.get("plate") or ev.get("plate_raw") or ""
            clean_plate = PlateWhitelistMatcher.normalize_key(raw_plate)
            if len(clean_plate) < 4 or len(clean_plate) > 12:
                raise HTTPException(status_code=400, detail="Targa non valida")

            if payload.add_to_whitelist:
                clean_owner = re.sub(r"[\r\n\t]+", " ", (payload.owner_name or "")).strip()
                if not clean_owner:
                    raise HTTPException(status_code=400, detail="owner_name obbligatorio per aggiungere alla whitelist")
                service.repository.upsert_plate_whitelist(
                    clean_plate,
                    clean_owner,
                    vehicle_label=payload.vehicle_label,
                    notes=payload.notes,
                    updated_at=now_ts,
                )
                service.sync_plate_whitelist_to_matcher_and_json()
                wl_whitelisted = True
                wl_owner = clean_owner
            else:
                matcher = service.get_plate_whitelist_matcher()
                if not matcher.list_entries() and service.repository.list_plate_whitelist():
                    service.sync_plate_whitelist_to_matcher_and_json()
                wl_entry, _dist = matcher.match(clean_plate, max_distance=0)
                wl_whitelisted = bool(wl_entry is not None)
                wl_owner = wl_entry.owner_name if wl_entry is not None else None

            updated = service.repository.update_biometric_event_review(
                event_id,
                identity=wl_owner,
                identity_confidence=1.0 if wl_owner else None,
                plate=clean_plate,
                plate_confidence=1.0,
                plate_whitelisted=wl_whitelisted,
                plate_owner=wl_owner,
                biometric_locked=True,
                biometric_status="locked",
                reviewed_by=reviewer,
                reviewed_at=now_ts,
            )
            backfilled_rows = await service.propagate_biometric_review(
                track_id=int(ev["track_id"]),
                modality="alpr",
                camera_id=str(ev["camera_id"]),
                event_id=event_id,
                event_ts=float(ev["timestamp"]),
                review_ts=now_ts,
                identity=wl_owner,
                identity_confidence=1.0 if wl_owner else None,
                plate=clean_plate,
                plate_raw=ev.get("plate_raw") or clean_plate,
                plate_confidence=1.0,
                plate_format=ev.get("plate_format"),
                plate_whitelisted=wl_whitelisted,
                plate_owner=wl_owner,
                best_crop_id=ev.get("best_crop_id"),
                quality_score=float(ev.get("quality_score") or 0.0),
            )
        else:
            raise HTTPException(status_code=400, detail=f"Modalita evento non supportata: {modality}")

        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "event": service.sanitize_biometric_event_row(updated or ev),
            "enrolled_sample": enrolled_sample,
            "enroll_note": enroll_note,
            "backfilled_rows": backfilled_rows,
        }

    @app.post("/api/v1/biometrics/identities/reload")
    async def reload_biometrics_identities(
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        service.reload_face_gallery()
        identities = service.get_biometric_gallery_summary()
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "count": len(identities), "identities": identities}

    @app.delete("/api/v1/biometrics/identities/{person_name}")
    async def delete_biometrics_identity(
        person_name: str,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        clean_name = re.sub(r"[\r\n\t]+", " ", person_name or "").strip()
        if not clean_name:
            raise HTTPException(status_code=400, detail="Nome persona non valido")

        gallery = service.get_face_gallery()
        with gallery._lock:
            target_name = next((n for n in gallery.person_names if n.lower() == clean_name.lower()), clean_name)
        removed_gallery = gallery.remove_person(target_name, persist=True)
        removed_db = service.repository.delete_face_embeddings(clean_name)
        if not removed_gallery and removed_db == 0:
            raise HTTPException(status_code=404, detail=f"Identita '{clean_name}' non trovata")

        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "deleted": target_name if removed_gallery else clean_name,
            "removed_from_gallery": removed_gallery,
            "removed_db_embeddings": removed_db,
        }

    @app.put("/api/v1/biometrics/plates")
    async def upsert_biometrics_plate(
        payload: PlateWhitelistUpsertRequest,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        try:
            entry = service.repository.upsert_plate_whitelist(
                payload.plate,
                payload.owner_name,
                vehicle_label=payload.vehicle_label,
                notes=payload.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        plates = service.sync_plate_whitelist_to_matcher_and_json()
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "entry": entry, "count": len(plates), "plates": plates}

    @app.delete("/api/v1/biometrics/plates/{plate}")
    async def delete_biometrics_plate(
        plate: str,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        key = PlateWhitelistMatcher.normalize_key(plate)
        if len(key) < 4:
            raise HTTPException(status_code=400, detail="Formato targa non valido")
        deleted = service.repository.delete_plate_whitelist(key)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Targa '{key}' non presente in whitelist")
        plates = service.sync_plate_whitelist_to_matcher_and_json()
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "deleted": key, "count": len(plates), "plates": plates}

    @app.post("/api/v1/biometrics/crops/prune")
    async def prune_biometrics_crops(
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        cutoff_bio = time.time() - service.config.biometrics_crop_retention_days * 86400
        deleted_events, relpaths = service.repository.prune_biometric_events_older_than(cutoff_bio)
        crop_store = service.get_biometric_crop_store()
        if crop_store is not None:
            deleted_files = crop_store.prune(
                retention_days=service.config.biometrics_crop_retention_days,
                max_disk_mb=service.config.biometrics_crop_max_mb,
                extra_relpaths=relpaths,
            )
            stats = crop_store.get_usage_stats()
        else:
            deleted_files = 0
            stats = {"files_count": 0, "total_mb": 0.0}
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "deleted_events": deleted_events,
            "deleted_files": deleted_files,
            "crop_storage": stats,
        }

    @app.get("/api/v1/timeline-density")
    async def get_timeline_density(
        t_start: float = Query(...),
        t_end: float = Query(...),
        buckets: int = Query(default=60, ge=5, le=360),
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        bins = service.repository.query_timeline_density(t_start, t_end, buckets=buckets)
        return {"status": "ok", "bins": bins}

    @app.get("/api/v1/recordings/status")
    async def get_recordings_status(
        request: Request,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        archive: IVideoArchiveRepository = request.app.state.recording_archive
        return {
            "status": "ok",
            "configured": archive.is_configured,
            "storage_type": archive.storage_type,
            "storage_dir": str(getattr(archive, "storage_dir", "") or ""),
            "cameras": archive.list_cameras(),
        }

    @app.get("/api/v1/recordings/{camera_id}/segments")
    async def get_camera_recording_segments(
        request: Request,
        camera_id: str,
        t_start: float = Query(...),
        t_end: float = Query(...),
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        archive: IVideoArchiveRepository = request.app.state.recording_archive
        segments = archive.query_segments(camera_id, t_start, t_end)
        return {
            "status": "ok",
            "camera_id": camera_id,
            "configured": archive.is_configured,
            "count": len(segments),
            "segments": [s.to_api_dict() for s in segments],
        }

    @app.get("/api/v1/recordings/{camera_id}/resolve")
    async def resolve_camera_recording(
        request: Request,
        camera_id: str,
        t: float = Query(...),
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        archive: IVideoArchiveRepository = request.app.state.recording_archive
        resolution = archive.resolve_timestamp(camera_id, t)
        return {
            "status": "ok",
            **resolution.to_api_dict(),
        }

    @app.get("/api/v1/recordings/{camera_id}/file/{filename}")
    async def stream_camera_recording_file(
        request: Request,
        camera_id: str,
        filename: str,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> FileResponse:
        archive: IVideoArchiveRepository = request.app.state.recording_archive
        file_path = archive.resolve_segment_file(camera_id, filename)
        if file_path is None or not file_path.exists():
            raise HTTPException(status_code=404, detail="Segmento video non trovato")
        media_type = "video/mp4"
        suffix = file_path.suffix.lower()
        if suffix == ".webm":
            media_type = "video/webm"
        elif suffix == ".mkv":
            media_type = "video/x-matroska"
        return FileResponse(path=file_path, media_type=media_type, filename=file_path.name)

    @app.get("/api/v1/calibrations")
    async def get_all_camera_calibrations(
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "calibrations": service.get_all_camera_calibrations()}

    @app.get("/api/v1/calibration/{camera_id}")
    async def get_camera_calibration(
        camera_id: str,
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        if camera_id not in service.optical_models:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not registered")
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "calibration": service.get_camera_calibration_metadata(camera_id)}

    @app.post("/api/v1/calibration/solve-pnp")
    async def solve_camera_pnp(
        req: SolvePnPRequest,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        model = service.optical_models.get(req.camera_id)
        if not isinstance(model, PinholeRadTanOpticalModel):
            raise HTTPException(status_code=400, detail=f"SolvePnPRansac requires pinhole camera; got {type(model).__name__}")

        result = service.calibration_solver.solve_pnp_ransac(model, req.correspondences)
        model.update_calibration(extrinsic_cv_to_world=result.extrinsic_cv_to_world)
        meta = service.save_camera_calibration_override(req.camera_id, ui_state=None)
        await service.broadcast_calibration_update(req.camera_id, meta)
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "reprojection_error_px": result.reprojection_error_px,
            "inliers_count": result.inliers_count,
            "extrinsic_cv_to_world": result.extrinsic_cv_to_world,
            "matrix_world_gl": result.matrix_world_gl,
            "calibration": meta,
        }

    @app.post("/api/v1/calibration/{camera_id}")
    async def update_camera_calibration(
        camera_id: str,
        payload: CalibrationOverridePayload,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        model = service.optical_models.get(camera_id)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not registered")

        extrinsic_cv: Optional[list[float]] = None
        if payload.calibrated_matrix_world_gl is not None:
            mat_gl = np.array(payload.calibrated_matrix_world_gl, dtype=np.float64).reshape((4, 4))
            extrinsic_cv = matrix_gl_to_cv(mat_gl).reshape(-1).tolist()

        model.update_calibration(
            extrinsic_cv_to_world=extrinsic_cv,
            fov_h_deg=payload.fov_h_deg,
            fov_v_deg=payload.fov_v_deg,
            distortion_coeffs=payload.distortion_coeffs,
        )
        meta = service.save_camera_calibration_override(camera_id, ui_state=payload.ui_state)
        await service.broadcast_calibration_update(camera_id, meta)
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "calibration": meta}

    @app.delete("/api/v1/calibration/{camera_id}")
    async def delete_camera_calibration(
        camera_id: str,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        if camera_id not in service.optical_models:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not registered")
        meta = service.reset_camera_calibration(camera_id)
        await service.broadcast_calibration_update(camera_id, meta)
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "camera_id": camera_id, "calibration": meta}

    # ========================================================================
    # SPATIAL AUTOMATIONS, 2.5D ZONES & VIRTUAL ENTITIES ENDPOINTS
    # ========================================================================

    @app.get("/api/v1/automations/bootstrap")
    async def get_automations_bootstrap(
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        eng = service.automation_engine
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "zones": [z.model_dump() for z in eng.list_zones()],
            "virtual_entities": [e.model_dump() for e in eng.list_virtual_entities()],
            "rules": [r.model_dump() for r in eng.list_rules()],
            "logs": service.repository.query_automation_logs(limit=60),
            "sun": eng.astronomical_clock.get_sun_summary(time.time()),
            "identities": service.get_biometric_gallery_summary(),
            "plates": service.repository.list_plate_whitelist(),
            "cameras": list(service.optical_models.keys()),
        }

    @app.get("/api/v1/automations/zones")
    async def get_automation_zones(
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        zones = [z.model_dump() for z in service.automation_engine.list_zones()]
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "count": len(zones), "zones": zones}

    @app.put("/api/v1/automations/zones")
    async def upsert_automation_zone(
        payload: SpatialZoneDefinition,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        zone = await service.automation_engine.upsert_zone(payload)
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "zone": zone.model_dump(),
            "zones": [z.model_dump() for z in service.automation_engine.list_zones()],
        }

    @app.delete("/api/v1/automations/zones/{zone_id}")
    async def delete_automation_zone(
        zone_id: str,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        deleted = await service.automation_engine.delete_zone(zone_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Area/perimetro '{zone_id}' non trovato")
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "deleted": zone_id,
            "zones": [z.model_dump() for z in service.automation_engine.list_zones()],
        }

    @app.get("/api/v1/automations/virtual-entities")
    async def get_virtual_entities(
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        entities = [e.model_dump() for e in service.automation_engine.list_virtual_entities()]
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "count": len(entities), "virtual_entities": entities}

    @app.put("/api/v1/automations/virtual-entities")
    async def upsert_virtual_entity_endpoint(
        payload: VirtualEntityDefinition,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        entity = await service.automation_engine.upsert_virtual_entity(payload)
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "entity": entity.model_dump(),
            "virtual_entities": [e.model_dump() for e in service.automation_engine.list_virtual_entities()],
        }

    @app.post("/api/v1/automations/virtual-entities/{entity_id}/state")
    async def change_virtual_entity_state(
        entity_id: str,
        payload: VirtualEntityStateChangeRequest,
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        try:
            updated = await service.automation_engine.set_virtual_entity_state(
                entity_id,
                payload.state,
                operation=payload.operation,
                attributes_patch=payload.attributes,
                trigger_automations=True,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "entity": updated.model_dump(),
            "virtual_entities": [e.model_dump() for e in service.automation_engine.list_virtual_entities()],
        }

    @app.delete("/api/v1/automations/virtual-entities/{entity_id}")
    async def delete_virtual_entity_endpoint(
        entity_id: str,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        deleted = await service.automation_engine.delete_virtual_entity(entity_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Entità virtuale '{entity_id}' non trovata")
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "deleted": entity_id,
            "virtual_entities": [e.model_dump() for e in service.automation_engine.list_virtual_entities()],
        }

    @app.get("/api/v1/automations/rules")
    async def get_automation_rules(
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        rules = [r.model_dump() for r in service.automation_engine.list_rules()]
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "count": len(rules), "rules": rules}

    @app.put("/api/v1/automations/rules")
    async def upsert_automation_rule_endpoint(
        payload: AutomationRuleDefinition,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        rule = await service.automation_engine.upsert_rule(payload)
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "rule": rule.model_dump(),
            "rules": [r.model_dump() for r in service.automation_engine.list_rules()],
        }

    @app.post("/api/v1/automations/rules/{rule_id}/toggle")
    async def toggle_automation_rule_endpoint(
        rule_id: str,
        payload: AutomationRuleToggleRequest,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        existing = service.automation_engine.rules.get(rule_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Automazione '{rule_id}' non trovata")
        updated = existing.model_copy(update={"enabled": bool(payload.enabled)})
        saved = await service.automation_engine.upsert_rule(updated)
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "rule": saved.model_dump(),
            "rules": [r.model_dump() for r in service.automation_engine.list_rules()],
        }

    @app.post("/api/v1/automations/rules/{rule_id}/trigger")
    async def trigger_automation_rule_manually(
        rule_id: str,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        try:
            log_entry = await service.automation_engine.trigger_rule_manually(rule_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "log": log_entry.model_dump(),
            "rules": [r.model_dump() for r in service.automation_engine.list_rules()],
        }

    @app.delete("/api/v1/automations/rules/{rule_id}")
    async def delete_automation_rule_endpoint(
        rule_id: str,
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        deleted = await service.automation_engine.delete_rule(rule_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Automazione '{rule_id}' non trovata")
        response.headers["Cache-Control"] = "no-store"
        return {
            "status": "ok",
            "deleted": rule_id,
            "rules": [r.model_dump() for r in service.automation_engine.list_rules()],
        }

    @app.get("/api/v1/automations/logs")
    async def get_automation_logs(
        response: Response,
        rule_id: Optional[str] = Query(default=None),
        limit: int = Query(default=80, ge=1, le=500),
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        logs = service.repository.query_automation_logs(rule_id=rule_id, limit=limit)
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "count": len(logs), "logs": logs}

    @app.delete("/api/v1/automations/logs")
    async def clear_automation_logs_endpoint(
        response: Response,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        deleted = service.repository.clear_automation_logs()
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "deleted": deleted}

    @app.post("/api/v1/automations/ha-states")
    async def sync_ha_states_to_automations(
        payload: HaStatesSyncRequest,
        response: Response,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        changed = await service.automation_engine.sync_ha_states_batch(
            payload.entities,
            trigger_on_diff=payload.trigger_on_diff,
        )
        response.headers["Cache-Control"] = "no-store"
        return {"status": "ok", "changed_count": changed}

    @app.post("/api/v1/ingestion/mode")
    async def switch_ingestion_mode(
        req: IngestionModeRequest,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        details = await service.set_ingestion_mode(req.mode)
        return {
            "status": "ok",
            "dev_mode": service.config.dev_mode,
            "ingestion_mode": service.ingestion_mode,
            "source_details": details,
        }

    @app.post("/api/v1/detections")
    async def ingest_http_detection(
        events: list[DetectionEvent] | DetectionEvent,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        batch = events if isinstance(events, list) else [events]
        tracks = await service.process_detection_batch(batch)
        return {"status": "ok", "active_tracks": [t.model_dump() for t in tracks]}

    @app.get("/api/v1/ha-camera/snapshot/{entity_id}")
    async def proxy_ha_camera_snapshot(
        request: Request,
        entity_id: str,
        ha_url: Optional[str] = Query(default=None),
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> Response:
        if not re.fullmatch(r"camera\.[a-zA-Z0-9_]+", entity_id):
            raise HTTPException(status_code=400, detail="entity_id non valido")

        caller_token = extract_bearer_token(request.headers)
        token = service.config.ha_token or caller_token
        if not token:
            raise HTTPException(status_code=503, detail="Token Home Assistant non disponibile")

        configured_bases: list[str] = []
        for raw in (
            service.config.ha_local_url,
            service.config.ha_tailscale_url,
            service.config.ha_public_url,
        ):
            clean = _normalize_ha_url(raw)
            if clean.lower().startswith(("http://", "https://")) and clean not in configured_bases:
                configured_bases.append(clean)

        allowed_origins = {
            (parsed.scheme.lower(), parsed.netloc.lower())
            for base in configured_bases
            for parsed in (urllib.parse.urlsplit(base),)
            if parsed.scheme and parsed.netloc
        }

        candidates: list[str] = []
        if service.config.ha_local_url:
            local_clean = _normalize_ha_url(service.config.ha_local_url)
            if local_clean.lower().startswith(("http://", "https://")):
                candidates.append(local_clean)

        if ha_url and ha_url.strip():
            requested = _normalize_ha_url(ha_url)
            req_parsed = urllib.parse.urlsplit(requested)
            req_origin = (req_parsed.scheme.lower(), req_parsed.netloc.lower())
            if not requested.lower().startswith(("http://", "https://")) or req_origin not in allowed_origins:
                raise HTTPException(status_code=400, detail="ha_url non consentito")
            if requested not in candidates:
                candidates.append(requested)

        for base in configured_bases:
            if base not in candidates:
                candidates.append(base)

        if not candidates:
            raise HTTPException(status_code=503, detail="Nessun URL Home Assistant configurato")

        def _fetch_sync() -> tuple[bytes, str]:
            last_status = 502
            last_err = "Home Assistant non raggiungibile"
            encoded_id = urllib.parse.quote(entity_id, safe=".")
            for base in candidates:
                target = f"{base}/api/camera_proxy/{encoded_id}"
                req = urllib.request.Request(
                    target,
                    headers={"Authorization": f"Bearer {token}"},
                )
                try:
                    with urllib.request.urlopen(req, timeout=3.5) as resp:
                        content_type = resp.headers.get("Content-Type") or "image/jpeg"
                        return resp.read(), content_type
                except urllib.error.HTTPError as exc:
                    last_status = exc.code
                    last_err = f"Home Assistant HTTP {exc.code} su {base}"
                except Exception as exc:
                    last_err = f"{exc} ({base})"
            raise HTTPException(status_code=last_status, detail=last_err)

        loop = asyncio.get_running_loop()
        payload_bytes, content_type = await loop.run_in_executor(None, _fetch_sync)
        return Response(
            content=payload_bytes,
            media_type=content_type,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    @app.websocket("/ws/spatial")
    async def ws_spatial(websocket: WebSocket) -> None:
        if service.config.auth_required:
            principal = await authenticate_websocket(websocket)
            if principal is None:
                await websocket.close(code=4401, reason="Unauthorized")
                return
        await websocket.accept()
        service.ws_clients.add(websocket)
        try:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "server_status",
                        "ingestion_mode": service.ingestion_mode,
                        "active_cameras": list(service.optical_models.keys()),
                    }
                )
            )
            while True:
                # Keepalive receive loop (clients may optionally ping or request snapshots)
                msg = await websocket.receive_text()
                if msg == "ping":
                    await websocket.send_text("pong")
                elif msg.startswith("{"):
                    try:
                        parsed_msg = json.loads(msg)
                        if parsed_msg.get("type") == "ha_states_sync" and isinstance(parsed_msg.get("entities"), dict):
                            await service.automation_engine.sync_ha_states_batch(
                                parsed_msg["entities"],
                                trigger_on_diff=bool(parsed_msg.get("trigger_on_diff", True)),
                            )
                    except Exception:
                        pass
        except WebSocketDisconnect:
            service.ws_clients.discard(websocket)
        except Exception:
            service.ws_clients.discard(websocket)

    return app


app = create_app()

