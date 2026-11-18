from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from typing import Any, Literal, Optional
import numpy as np
from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from spatial_server.biometrics import (
    ExternalWebhookIdentityResolver,
    IIdentityResolver,
    NoOpIdentityResolver,
    OpenVINOInsightFaceResolver,
)
from spatial_server.config import SpatialServerConfig
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
from spatial_server.tracking import IMultiTargetTracker3D, Kalman3DMultiTracker, TrackObservation3D

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("spatial_server")


class IngestionModeRequest(BaseModel):
    mode: Literal["synthetic", "openvino", "mqtt", "hybrid"]


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
    ) -> None:
        self.config = config
        self.optical_models = optical_models
        self.raycaster = raycaster
        self.identity_resolver = identity_resolver
        self.tracker = tracker
        self.repository = repository
        self.calibration_solver = calibration_solver

        self.ingestion_mode: str = config.default_ingestion_mode
        self.active_sources: list[IDetectionSource] = []
        self.ws_clients: set[WebSocket] = set()
        self._pending_persist: list[TrackedEntity3D] = []
        self._persist_lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task[None]] = None
        self._pipeline_lock = asyncio.Lock()

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
            next_sources = [
                OpenVINORtspDetectionSource(
                    rtsp_url=self.config.go2rtc_rtsp_url,
                    camera_id="Cam_Carraio",
                    openvino_device=self.config.openvino_device,
                    model_path=self.config.openvino_model_path,
                    target_fps=7.0,
                )
            ]
        elif mode == "mqtt":
            next_sources = [
                MqttFrigateDetectionSource(
                    host=self.config.mqtt_host,
                    port=self.config.mqtt_port,
                    username=self.config.mqtt_user,
                    password=self.config.mqtt_password,
                    topic=self.config.mqtt_topic_prefix,
                )
            ]
        elif mode == "hybrid":
            next_sources = [
                OpenVINORtspDetectionSource(
                    rtsp_url=self.config.go2rtc_rtsp_url,
                    camera_id="Cam_Carraio",
                    openvino_device=self.config.openvino_device,
                    model_path=self.config.openvino_model_path,
                    target_fps=7.0,
                ),
                MqttFrigateDetectionSource(
                    host=self.config.mqtt_host,
                    port=self.config.mqtt_port,
                    username=self.config.mqtt_user,
                    password=self.config.mqtt_password,
                    topic=self.config.mqtt_topic_prefix,
                ),
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
        return details

    async def process_detection_batch(self, events: list[DetectionEvent]) -> list[TrackedEntity3D]:
        if not events:
            return []

        observations: list[TrackObservation3D] = []
        now_ts = max(e.timestamp for e in events)

        for evt in events:
            model = self.optical_models.get(evt.camera_id)
            if model is None:
                continue

            u, v = evt.bbox.get_ground_contact_uv()
            ray = model.pixel_to_world_ray(u, v)
            hit_pt = self.raycaster.intersect_ground(ray)
            if hit_pt is None:
                continue

            identity, id_conf = await self.identity_resolver.resolve_identity(evt)
            observations.append(
                TrackObservation3D(
                    camera_id=evt.camera_id,
                    timestamp=evt.timestamp,
                    class_label=evt.class_label,
                    position=hit_pt,
                    confidence=evt.confidence,
                    identity=identity,
                    identity_confidence=id_conf,
                )
            )

        async with self._pipeline_lock:
            active_tracks = self.tracker.update(observations, now_ts)

        if active_tracks:
            async with self._persist_lock:
                self._pending_persist.extend(active_tracks)

        await self.broadcast_frame(active_tracks, now_ts)
        return active_tracks

    async def broadcast_frame(self, active_tracks: list[TrackedEntity3D], timestamp: float) -> None:
        if not self.ws_clients:
            return
        payload = json.dumps(
            {
                "type": "spatial_frame",
                "timestamp": timestamp,
                "ingestion_mode": self.ingestion_mode,
                "active_tracks": [tr.model_dump() for tr in active_tracks],
            }
        )
        dead: list[WebSocket] = []
        for ws in list(self.ws_clients):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ws_clients.discard(ws)

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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.pipeline = service

    @app.get("/api/v1/status")
    async def get_status() -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        bins = service.repository.query_timeline_density(t_start, t_end, buckets=buckets)
        return {"status": "ok", "bins": bins}

    @app.get("/api/v1/calibration/{camera_id}")
    async def get_camera_calibration(camera_id: str) -> dict[str, Any]:
        model = service.optical_models.get(camera_id)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not registered")
        return {"status": "ok", "calibration": model.to_metadata_dict()}

    @app.post("/api/v1/calibration/solve-pnp")
    async def solve_camera_pnp(req: SolvePnPRequest) -> dict[str, Any]:
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
    async def update_camera_calibration(camera_id: str, payload: CalibrationOverridePayload) -> dict[str, Any]:
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
    async def switch_ingestion_mode(req: IngestionModeRequest) -> dict[str, Any]:
        details = await service.set_ingestion_mode(req.mode)
        return {
            "status": "ok",
            "ingestion_mode": service.ingestion_mode,
            "source_details": details,
        }

    @app.post("/api/v1/detections")
    async def ingest_http_detection(events: list[DetectionEvent] | DetectionEvent) -> dict[str, Any]:
        batch = events if isinstance(events, list) else [events]
        tracks = await service.process_detection_batch(batch)
        return {"status": "ok", "active_tracks": [t.model_dump() for t in tracks]}

    @app.get("/api/v1/ha-camera/snapshot/{entity_id}")
    async def proxy_ha_camera_snapshot(
        entity_id: str,
        ha_url: Optional[str] = Query(default=None),
    ) -> Response:
        if not re.fullmatch(r"[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+", entity_id):
            raise HTTPException(status_code=400, detail="entity_id non valido")

        token = service.config.ha_token
        if not token:
            raise HTTPException(status_code=503, detail="VITE_HA_TOKEN non configurato")

        raw_candidates = [
            ha_url or "",
            service.config.ha_tailscale_url,
            service.config.ha_local_url,
        ]
        candidates: list[str] = []
        for raw in raw_candidates:
            clean = raw.strip().rstrip("/")
            if clean.lower().startswith(("http://", "https://")) and clean not in candidates:
                candidates.append(clean)

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

