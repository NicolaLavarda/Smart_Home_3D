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
from typing import Any, Literal, Optional
import numpy as np
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from spatial_server.biometrics import (
    ExternalWebhookIdentityResolver,
    IIdentityResolver,
    NoOpIdentityResolver,
    OpenVINOInsightFaceResolver,
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


@dataclass
class _PersistAnchor:
    x: float
    y: float
    z: float
    timestamp: float
    class_label: str
    identity: Optional[str]


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
    ) -> None:
        self.config = config
        self.optical_models = optical_models
        self.raycaster = raycaster
        self.identity_resolver = identity_resolver
        self.tracker = tracker
        self.repository = repository
        self.calibration_solver = calibration_solver
        self.camera_manifest_meta: dict[str, dict[str, Any]] = dict(camera_manifest_meta or {})

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

    def get_optical_model(self, camera_id: str) -> Optional[ICameraOpticalModel]:
        return self.optical_models.get(camera_id)

    async def start(self) -> None:
        self._flush_task = asyncio.create_task(self._db_flush_loop())
        await self.set_ingestion_mode(self.ingestion_mode)

    async def stop(self) -> None:
        await self._stop_sources()
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
                active_tracks = self.tracker.update([], now_ts)
            self._prune_stale_persist_anchors(active_tracks)
            await self.broadcast_frame(active_tracks, now_ts)
            return active_tracks

        observations: list[TrackObservation3D] = []
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
            obs_range_m = float(math.dist(ray.origin, hit_pt))
            observations.append(
                TrackObservation3D(
                    camera_id=evt.camera_id,
                    timestamp=evt.timestamp,
                    class_label=evt.class_label,
                    position=hit_pt,
                    confidence=evt.confidence,
                    identity=identity,
                    identity_confidence=id_conf,
                    range_m=obs_range_m,
                )
            )

        async with self._pipeline_lock:
            active_tracks = self.tracker.update(observations, now_ts)

        persistable = self._select_tracks_to_persist(active_tracks)
        if persistable:
            async with self._persist_lock:
                self._pending_persist.extend(persistable)

        await self.broadcast_frame(active_tracks, now_ts)
        return active_tracks

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
                    cutoff = time.time() - self.config.db_retention_days * 86400
                    self.repository.prune_older_than(cutoff)
                    last_prune = time.monotonic()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("SQLite WAL flush warning: %s", exc)


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

    if cfg.face_webhook_url:
        identity_resolver: IIdentityResolver = ExternalWebhookIdentityResolver(cfg.face_webhook_url)
    elif (cfg.models_dir / "face_gallery").exists():
        identity_resolver = OpenVINOInsightFaceResolver(cfg.models_dir / "face_gallery")
    else:
        identity_resolver = NoOpIdentityResolver()

    tracker = Kalman3DMultiTracker()
    repository = SQLiteWALTrackRepository(cfg.sqlite_db_path)

    return SpatialPipelineService(
        config=cfg,
        optical_models=optical_models,
        raycaster=raycaster,
        identity_resolver=identity_resolver,
        tracker=tracker,
        repository=repository,
        calibration_solver=calib_solver,
        camera_manifest_meta=camera_manifest_meta,
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
        return {
            "status": "ok",
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
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        cls_list = [c.strip() for c in classes.split(",") if c.strip()] if classes else None
        zone_bbox = None
        if None not in (min_x, max_x, min_z, max_z):
            zone_bbox = (float(min_x), float(max_x), float(min_z), float(max_z))

        rows = service.repository.query_time_range(t_start, t_end, classes=cls_list, zone_bbox=zone_bbox, limit=limit)
        t_min = rows[0]["timestamp"] if rows else None
        t_max = rows[-1]["timestamp"] if rows else None
        return {
            "status": "ok",
            "count": len(rows),
            "t_min": t_min,
            "t_max": t_max,
            "detections": rows,
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

    @app.get("/api/v1/calibration/{camera_id}")
    async def get_camera_calibration(
        camera_id: str,
        _user: HAUserPrincipal = Depends(require_authenticated_user),
    ) -> dict[str, Any]:
        model = service.optical_models.get(camera_id)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not registered")
        return {"status": "ok", "calibration": model.to_metadata_dict()}

    @app.post("/api/v1/calibration/solve-pnp")
    async def solve_camera_pnp(
        req: SolvePnPRequest,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        model = service.optical_models.get(req.camera_id)
        if not isinstance(model, PinholeRadTanOpticalModel):
            raise HTTPException(status_code=400, detail=f"SolvePnPRansac requires pinhole camera; got {type(model).__name__}")

        result = service.calibration_solver.solve_pnp_ransac(model, req.correspondences)
        model.update_calibration(extrinsic_cv_to_world=result.extrinsic_cv_to_world)
        service.calibration_solver.save_override(req.camera_id, model.to_metadata_dict())
        return {
            "status": "ok",
            "reprojection_error_px": result.reprojection_error_px,
            "inliers_count": result.inliers_count,
            "extrinsic_cv_to_world": result.extrinsic_cv_to_world,
            "matrix_world_gl": result.matrix_world_gl,
        }

    @app.post("/api/v1/calibration/{camera_id}")
    async def update_camera_calibration(
        camera_id: str,
        payload: CalibrationOverridePayload,
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
        meta = model.to_metadata_dict()
        service.calibration_solver.save_override(camera_id, meta)
        return {"status": "ok", "calibration": meta}

    @app.post("/api/v1/ingestion/mode")
    async def switch_ingestion_mode(
        req: IngestionModeRequest,
        _admin: HAUserPrincipal = Depends(require_admin_user),
    ) -> dict[str, Any]:
        details = await service.set_ingestion_mode(req.mode)
        return {
            "status": "ok",
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
        except WebSocketDisconnect:
            service.ws_clients.discard(websocket)
        except Exception:
            service.ws_clients.discard(websocket)

    return app


app = create_app()

