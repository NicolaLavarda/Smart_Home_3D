from __future__ import annotations

import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any, Optional

import cv2
import httpx
import numpy as np
from fastapi.testclient import TestClient

from spatial_server.biometrics import (
    BiometricCropStore,
    BiometricEligibilityGate,
    BiometricWorkerService,
    FaceEvaluation,
    FaceQualityMetrics,
    Go2RtcSnapshotProvider,
    IFaceRecognizer,
    IPlateRecognizer,
    NoOpIdentityResolver,
    PlateEvaluation,
    PlateQualityMetrics,
    PlateWhitelistMatcher,
    TrackBiometricConsensusManager,
)
from spatial_server.config import REPO_ROOT, SpatialServerConfig
from spatial_server.domain.models import BoundingBox2D, DetectionEvent, Ray3D
from spatial_server.geometry import ISpatialRaycaster, TrimeshGroundRaycaster
from spatial_server.ingestion import MqttFrigateDetectionSource
from spatial_server.main import SpatialPipelineService, build_pipeline_service, create_app
from spatial_server.optics import CameraCalibrationSolver, create_optical_model_from_manifest
from spatial_server.persistence import SQLiteWALTrackRepository
from spatial_server.tracking import Kalman3DMultiTracker, TrackObservation3D


def _make_jpeg_bytes(width: int = 1280, height: int = 720) -> bytes:
    img = np.full((height, width, 3), 120, dtype=np.uint8)
    ok, enc = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    assert ok
    return enc.tobytes()


class _FlatGroundRaycaster(ISpatialRaycaster):
    def intersect_ground(self, ray: Ray3D) -> Optional[tuple[float, float, float]]:
        dy = float(ray.direction[1])
        if abs(dy) < 1e-5:
            return None
        t = -float(ray.origin[1]) / dy
        if t <= 0.0:
            return None
        return (
            float(ray.origin[0] + t * ray.direction[0]),
            0.0,
            float(ray.origin[2] + t * ray.direction[2]),
        )


class _FakeFaceRecognizer(IFaceRecognizer):
    def __init__(self, identity: str = "Nicola", similarity: float = 0.78) -> None:
        self.identity = identity
        self.similarity = similarity
        self.calls = 0

    def is_ready(self) -> bool:
        return True

    def recognize_crop(self, person_crop_bgr: np.ndarray) -> Optional[FaceEvaluation]:
        self.calls += 1
        return FaceEvaluation(
            identity=self.identity,
            similarity=self.similarity,
            second_best_similarity=0.22,
            margin=self.similarity - 0.22,
            quality_score=0.86,
            metrics=FaceQualityMetrics(
                det_score=0.92,
                face_width_px=84.0,
                blur_laplacian=140.0,
                yaw_ratio=0.12,
                passed=True,
            ),
            crop_bgr=person_crop_bgr,
        )


class _FakePlateRecognizer(IPlateRecognizer):
    def __init__(self, plate: str = "AB123DC", raw: str = "AB123DC", conf: float = 0.91) -> None:
        self.plate = plate
        self.raw = raw
        self.conf = conf
        self.calls = 0

    def is_ready(self) -> bool:
        return True

    def recognize_crop(self, vehicle_crop_bgr: np.ndarray) -> Optional[PlateEvaluation]:
        self.calls += 1
        return PlateEvaluation(
            plate=self.plate,
            plate_raw=self.raw,
            plate_format="IT_STD",
            confidence=self.conf,
            quality_score=0.88,
            metrics=PlateQualityMetrics(
                det_score=0.89,
                plate_width_px=96.0,
                blur_laplacian=120.0,
                glare_ratio=0.02,
                mean_luma=135.0,
                passed=True,
            ),
            crop_bgr=vehicle_crop_bgr,
        )


class _RecordingWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send_text(self, payload: str) -> None:
        self.messages.append(json.loads(payload))


def _make_cfg(tmp_dir: Path, **overrides: Any) -> SpatialServerConfig:
    defaults: dict[str, Any] = dict(
        host="127.0.0.1",
        port=8765,
        manifest_path=REPO_ROOT / "public" / "models" / "scene_manifest.json",
        glb_path=REPO_ROOT / "public" / "models" / "house_optimized.glb",
        sqlite_db_path=tmp_dir / "bio_integ.db",
        calibration_override_path=tmp_dir / "calibs.json",
        data_dir=tmp_dir,
        models_dir=REPO_ROOT / "spatial_server" / "models",
        default_ingestion_mode="synthetic",
        go2rtc_rtsp_url="rtsp://127.0.0.1:8554/carraio_sub",
        mqtt_host="127.0.0.1",
        mqtt_port=1883,
        mqtt_user="",
        mqtt_password="",
        mqtt_topic_prefix="frigate/events",
        openvino_device="CPU",
        openvino_model_path="",
        db_retention_days=14,
        face_webhook_url="",
        auth_required=False,
        persist_min_displacement_m=0.5,
        persist_heartbeat_s=60.0,
    )
    defaults.update(overrides)
    return SpatialServerConfig(**defaults)


def _load_carraio_and_ingresso_models() -> dict[str, Any]:
    manifest = json.loads((REPO_ROOT / "public" / "models" / "scene_manifest.json").read_text(encoding="utf-8"))
    carraio = create_optical_model_from_manifest("Cam_Carraio", manifest["cameras"]["Cam_Carraio"])
    ingresso = create_optical_model_from_manifest("Cam_Ingresso", manifest["cameras"]["Cam_Ingresso"])
    return {"Cam_Carraio": carraio, "Cam_Ingresso": ingresso}


def _is_in_frame(model: Any, world_pt: tuple[float, float, float]) -> bool:
    uv = model.world_point_to_pixel(world_pt)
    if uv is None:
        return False
    u, v = uv
    return 0.08 <= u <= 0.92 and 0.25 <= v <= 0.96


def _find_visible_uv(
    model: Any,
    world_pt: tuple[float, float, float],
    bbox_w: float = 0.14,
    bbox_h: float = 0.30,
) -> BoundingBox2D:
    uv = model.world_point_to_pixel(world_pt)
    assert uv is not None, f"Point {world_pt} not visible from {model.camera_id}"
    u, v = uv
    assert 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0, f"UV out of bounds for {model.camera_id}: {(u, v)}"
    x_min = max(0.0, min(1.0 - 0.02, u - bbox_w * 0.5))
    x_max = min(1.0, max(x_min + 0.02, u + bbox_w * 0.5))
    y_max = min(1.0, max(0.05, v))
    y_min = max(0.0, y_max - bbox_h)
    return BoundingBox2D(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)


async def _wait_until(predicate, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("Timed out waiting for async biometric condition")


def test_integration_face_lock_persistence_ws_and_multicam_handover(tmp_path: Path) -> None:
    async def _run() -> None:
        jpeg_bytes = _make_jpeg_bytes()
        fetch_srcs: list[str] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            fetch_srcs.append(request.url.params.get("src", ""))
            return httpx.Response(200, content=jpeg_bytes, headers={"Content-Type": "image/jpeg"})

        crop_store = BiometricCropStore(tmp_path / "biometrics")
        consensus = TrackBiometricConsensusManager(
            crop_store=crop_store,
            face_consensus_k=2,
            min_eval_interval_s=0.1,
            max_fast_attempts=6,
        )
        gate = BiometricEligibilityGate(face_max_range_m=8.0, panoramic_edge_margin_u=0.05)
        snap_provider = Go2RtcSnapshotProvider(
            "http://127.0.0.1:1984",
            http_transport=httpx.MockTransport(_handler),
        )
        fake_face = _FakeFaceRecognizer("Nicola", similarity=0.81)
        worker = BiometricWorkerService(
            snapshot_provider=snap_provider,
            consensus=consensus,
            gate=gate,
            face_recognizer=fake_face,
            queue_maxsize=8,
        )

        optical_models = _load_carraio_and_ingresso_models()
        manifest = json.loads((REPO_ROOT / "public" / "models" / "scene_manifest.json").read_text(encoding="utf-8"))
        cfg = _make_cfg(tmp_path)
        repo = SQLiteWALTrackRepository(cfg.sqlite_db_path)
        service = SpatialPipelineService(
            config=cfg,
            optical_models=optical_models,
            raycaster=_FlatGroundRaycaster(),
            identity_resolver=NoOpIdentityResolver(),
            tracker=Kalman3DMultiTracker(),
            repository=repo,
            calibration_solver=CameraCalibrationSolver(cfg.calibration_override_path),
            camera_manifest_meta=manifest["cameras"],
            biometric_coordinator=worker,
        )
        ws = _RecordingWebSocket()
        service.ws_clients.add(ws)  # type: ignore[arg-type]

        await service.start()
        try:
            # Point right in front of Cam_Carraio within <= 6m
            r_car = optical_models["Cam_Carraio"].pixel_to_world_ray(0.5, 0.75)
            t_hit = -r_car.origin[1] / r_car.direction[1]
            p1 = (
                r_car.origin[0] + t_hit * r_car.direction[0],
                0.0,
                r_car.origin[2] + t_hit * r_car.direction[2],
            )
            assert math.dist(r_car.origin, p1) <= 8.0
            bbox1 = _find_visible_uv(optical_models["Cam_Carraio"], p1)

            base_t = time.time()
            # 1st observation -> pending
            tracks1 = await service.process_detection_batch(
                [DetectionEvent(camera_id="Cam_Carraio", timestamp=base_t, class_label="person", confidence=0.92, bbox=bbox1)]
            )
            assert len(tracks1) == 1
            await _wait_until(lambda: fake_face.calls >= 1)
            await asyncio.sleep(0.05)

            active_mid = service.tracker.get_active_tracks()
            assert active_mid[0].biometric_locked is False
            assert active_mid[0].biometric_status == "pending"
            assert active_mid[0].identity == "Nicola"

            # 2nd observation -> concordant K=2 -> locks Nicola and triggers immediate persist + WS biometric_event
            tracks2 = await service.process_detection_batch(
                [DetectionEvent(camera_id="Cam_Carraio", timestamp=base_t + 0.25, class_label="person", confidence=0.94, bbox=bbox1)]
            )
            assert len(tracks2) == 1
            await _wait_until(lambda: bool(service.tracker.get_active_tracks()[0].biometric_locked))
            await asyncio.sleep(0.05)

            locked_tr = service.tracker.get_active_tracks()[0]
            assert locked_tr.identity == "Nicola"
            assert locked_tr.biometric_locked is True
            assert locked_tr.biometric_status == "locked"
            assert locked_tr.best_crop_id is not None
            assert crop_store.resolve_crop_path(locked_tr.best_crop_id) is not None

            # Immediate DB flush without further movement must contain Nicola
            await service.flush_pending_to_db()
            rows = repo.query_time_range(base_t - 5.0, base_t + 5.0)
            assert any(r["identity"] == "Nicola" for r in rows)

            # Check WS events (no internal filesystem path leaked)
            bio_events = [m for m in ws.messages if m.get("type") == "biometric_event"]
            assert len(bio_events) == 1
            assert bio_events[0]["identity"] == "Nicola"
            assert bio_events[0]["biometric_locked"] is True
            assert "best_crop_relpath" not in bio_events[0]

            fetches_at_lock = len(fetch_srcs)
            assert fetches_at_lock == 2
            assert fetch_srcs == ["carraio_snap", "carraio_snap"]

            # 3rd observation + cross-camera handover to Cam_Ingresso (0 extra snapshot fetches!)
            p_shared = (-8.5, 0.0, 3.5)
            bbox_ing = _find_visible_uv(optical_models["Cam_Ingresso"], p_shared)
            num_steps = max(4, int(math.ceil(math.dist(p1, p_shared) / 1.0)))
            for step_i in range(1, num_steps + 1):
                frac = step_i / num_steps
                pt = (
                    p1[0] + (p_shared[0] - p1[0]) * frac,
                    0.0,
                    p1[2] + (p_shared[2] - p1[2]) * frac,
                )
                if step_i < num_steps and _is_in_frame(optical_models["Cam_Carraio"], pt):
                    bb = _find_visible_uv(optical_models["Cam_Carraio"], pt)
                    cam_use = "Cam_Carraio"
                elif _is_in_frame(optical_models["Cam_Ingresso"], pt):
                    bb = _find_visible_uv(optical_models["Cam_Ingresso"], pt)
                    cam_use = "Cam_Ingresso"
                else:
                    bb = bbox_ing
                    cam_use = "Cam_Ingresso"
                await service.process_detection_batch(
                    [DetectionEvent(camera_id=cam_use, timestamp=base_t + 0.5 + step_i * 0.15, class_label="person", confidence=0.91, bbox=bb)]
                )

            tracks_handed = await service.process_detection_batch(
                [DetectionEvent(camera_id="Cam_Ingresso", timestamp=base_t + 0.5 + (num_steps + 1) * 0.15, class_label="person", confidence=0.90, bbox=bbox_ing)]
            )
            await asyncio.sleep(0.05)

            assert len(tracks_handed) == 1
            assert tracks_handed[0].track_id == locked_tr.track_id
            assert tracks_handed[0].identity == "Nicola"
            assert tracks_handed[0].biometric_locked is True
            assert "Cam_Ingresso" in tracks_handed[0].state.camera_sources
            assert len(fetch_srcs) == fetches_at_lock, "Locked track must never fetch snapshots again"
        finally:
            await service.stop()
            repo.close()

    asyncio.run(_run())


def test_integration_alpr_whitelist_lock_and_persist(tmp_path: Path) -> None:
    async def _run() -> None:
        jpeg_bytes = _make_jpeg_bytes()
        wl_path = tmp_path / "biometrics" / "plates_whitelist.json"
        matcher = PlateWhitelistMatcher(wl_path)
        matcher.upsert("AB123CD", "Auto Nicola", vehicle_label="Audi A3")

        crop_store = BiometricCropStore(tmp_path / "biometrics")
        consensus = TrackBiometricConsensusManager(
            crop_store=crop_store,
            whitelist_matcher=matcher,
            alpr_consensus_k=2,
            min_eval_interval_s=0.1,
            whitelist_max_distance=1,
        )
        gate = BiometricEligibilityGate(alpr_max_range_m=13.0)
        snap_provider = Go2RtcSnapshotProvider(
            "http://127.0.0.1:1984",
            http_transport=httpx.MockTransport(
                lambda _req: httpx.Response(200, content=jpeg_bytes, headers={"Content-Type": "image/jpeg"})
            ),
        )
        fake_plate = _FakePlateRecognizer(plate="AB123GD", raw="AB123GD", conf=0.92)
        worker = BiometricWorkerService(
            snapshot_provider=snap_provider,
            consensus=consensus,
            gate=gate,
            plate_recognizer=fake_plate,
            queue_maxsize=8,
        )

        optical_models = _load_carraio_and_ingresso_models()
        cfg = _make_cfg(tmp_path)
        repo = SQLiteWALTrackRepository(cfg.sqlite_db_path)
        service = SpatialPipelineService(
            config=cfg,
            optical_models=optical_models,
            raycaster=_FlatGroundRaycaster(),
            identity_resolver=NoOpIdentityResolver(),
            tracker=Kalman3DMultiTracker(),
            repository=repo,
            calibration_solver=CameraCalibrationSolver(cfg.calibration_override_path),
            biometric_coordinator=worker,
        )
        ws = _RecordingWebSocket()
        service.ws_clients.add(ws)  # type: ignore[arg-type]

        await service.start()
        try:
            r_car = optical_models["Cam_Carraio"].pixel_to_world_ray(0.5, 0.75)
            t_hit = -r_car.origin[1] / r_car.direction[1]
            p_car = (
                r_car.origin[0] + t_hit * r_car.direction[0],
                0.0,
                r_car.origin[2] + t_hit * r_car.direction[2],
            )
            bbox_car = _find_visible_uv(optical_models["Cam_Carraio"], p_car, bbox_w=0.22, bbox_h=0.28)
            base_t = time.time()

            await service.process_detection_batch(
                [DetectionEvent(camera_id="Cam_Carraio", timestamp=base_t, class_label="car", confidence=0.95, bbox=bbox_car)]
            )
            await _wait_until(lambda: fake_plate.calls >= 1)

            await service.process_detection_batch(
                [DetectionEvent(camera_id="Cam_Carraio", timestamp=base_t + 0.25, class_label="car", confidence=0.96, bbox=bbox_car)]
            )
            await _wait_until(lambda: bool(service.tracker.get_active_tracks()[0].biometric_locked))
            await asyncio.sleep(0.05)

            car_tr = service.tracker.get_active_tracks()[0]
            assert car_tr.plate == "AB123CD"
            assert car_tr.plate_whitelisted is True
            assert car_tr.plate_owner == "Auto Nicola"
            assert car_tr.identity == "Auto Nicola"
            assert car_tr.biometric_locked is True

            await service.flush_pending_to_db()
            rows = repo.query_time_range(base_t - 5.0, base_t + 5.0)
            assert any(r["identity"] == "Auto Nicola" for r in rows)

            bio_events = [m for m in ws.messages if m.get("type") == "biometric_event"]
            assert len(bio_events) == 1
            assert bio_events[0]["plate"] == "AB123CD"
            assert bio_events[0]["plate_whitelisted"] is True
        finally:
            await service.stop()
            repo.close()

    asyncio.run(_run())


def test_integration_slow_go2rtc_does_not_block_tracking_and_trips_breaker(tmp_path: Path) -> None:
    async def _run() -> None:
        async def _slow_failing_handler(_request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(0.25)
            return httpx.Response(503, text="go2rtc unavailable")

        consensus = TrackBiometricConsensusManager(min_eval_interval_s=0.05)
        gate = BiometricEligibilityGate(face_max_range_m=8.0)
        snap_provider = Go2RtcSnapshotProvider(
            "http://127.0.0.1:1984",
            breaker_failure_threshold=3,
            breaker_cooldown_s=30.0,
            http_transport=httpx.MockTransport(_slow_failing_handler),
        )
        worker = BiometricWorkerService(
            snapshot_provider=snap_provider,
            consensus=consensus,
            gate=gate,
            face_recognizer=_FakeFaceRecognizer(),
            queue_maxsize=4,
        )

        optical_models = _load_carraio_and_ingresso_models()
        cfg = _make_cfg(tmp_path)
        repo = SQLiteWALTrackRepository(cfg.sqlite_db_path)
        service = SpatialPipelineService(
            config=cfg,
            optical_models=optical_models,
            raycaster=_FlatGroundRaycaster(),
            identity_resolver=NoOpIdentityResolver(),
            tracker=Kalman3DMultiTracker(),
            repository=repo,
            calibration_solver=CameraCalibrationSolver(cfg.calibration_override_path),
            biometric_coordinator=worker,
        )

        await service.start()
        try:
            r_car = optical_models["Cam_Carraio"].pixel_to_world_ray(0.5, 0.75)
            t_hit = -r_car.origin[1] / r_car.direction[1]
            p_hit = (r_car.origin[0] + t_hit * r_car.direction[0], 0.0, r_car.origin[2] + t_hit * r_car.direction[2])
            bbox = _find_visible_uv(optical_models["Cam_Carraio"], p_hit)

            # Enqueue 3 failures to trip circuit breaker, verify process_detection_batch returns immediately (<0.1s)
            base_t = time.time()
            for i in range(3):
                t0 = time.perf_counter()
                await service.process_detection_batch(
                    [DetectionEvent(camera_id="Cam_Carraio", timestamp=base_t + i * 0.6, class_label="person", confidence=0.9, bbox=bbox)]
                )
                dt = time.perf_counter() - t0
                assert dt < 0.1, f"process_detection_batch blocked for {dt:.3f}s on slow snapshot"
                await asyncio.sleep(0.55)

            diag = snap_provider.get_diagnostics()
            assert diag["Cam_Carraio"]["circuit_open"] is True
            assert worker.snapshot_misses_count >= 3
        finally:
            await service.stop()
            repo.close()

    asyncio.run(_run())


def test_integration_motorbike_mqtt_normalization_and_locked_track_protection() -> None:
    mqtt_src = MqttFrigateDetectionSource(host="127.0.0.1")
    evt = mqtt_src._parse_payload(
        json.dumps(
            {
                "type": "new",
                "after": {
                    "label": "motorcycle",
                    "camera": "carraio",
                    "box": [0.3, 0.4, 0.5, 0.8],
                    "score": 0.91,
                    "recognized_license_plate": ["ef12345", 0.88],
                },
            }
        )
    )
    assert evt is not None
    assert evt.class_label == "motorbike"
    assert evt.camera_id == "Cam_Carraio"
    assert evt.plate == "EF12345"
    assert evt.plate_confidence == 0.88

    # Tracker fuses car + motorbike via 'vehicle' coarse class and protects locked track from hijacks
    tracker = Kalman3DMultiTracker(initial_next_track_id=100)
    tracks, _assign = tracker.update_with_assignments(
        [TrackObservation3D("Cam_Carraio", 1000.0, "car", (-10.0, 0.0, 10.0), 0.9, identity="Auto Nicola", identity_confidence=0.95, plate="AB123CD", plate_confidence=0.95)],
        now_ts=1000.0,
    )
    assert len(tracks) == 1 and tracks[0].track_id == 100

    # Lock track via biometric update
    from spatial_server.biometrics import TrackBiometricUpdate

    updated = tracker.apply_biometric_result(
        TrackBiometricUpdate(
            track_id=100,
            modality="alpr",
            identity="Auto Nicola",
            identity_confidence=0.95,
            plate="AB123CD",
            plate_confidence=0.95,
            plate_whitelisted=True,
            plate_owner="Auto Nicola",
            biometric_locked=True,
            biometric_status="locked",
            camera_id="Cam_Carraio",
            timestamp=1000.1,
        )
    )
    assert updated is not None and updated.biometric_locked is True

    # Conflicting observation at exact same coords must NOT overwrite or hijack locked track
    tracks2 = tracker.update(
        [TrackObservation3D("Cam_Carraio", 1000.2, "car", (-10.0, 0.0, 10.0), 0.99, identity="Intruso", identity_confidence=0.99, plate="ZZ999ZZ", plate_confidence=0.99)],
        now_ts=1000.2,
    )
    assert len(tracks2) == 2
    locked = next(t for t in tracks2 if t.track_id == 100)
    assert locked.identity == "Auto Nicola"
    assert locked.plate == "AB123CD"

    # Also ensure downgrade to pending is ignored once locked
    assert (
        tracker.apply_biometric_result(
            TrackBiometricUpdate(
                track_id=100,
                modality="alpr",
                biometric_locked=False,
                biometric_status="pending",
                camera_id="Cam_Carraio",
                timestamp=1000.3,
            )
        )
        is None
    )


def test_integration_build_pipeline_and_status_endpoint(tmp_path: Path) -> None:
    cfg_off = _make_cfg(tmp_path / "off", biometrics_enabled=False)
    app_off = create_app(cfg_off)
    try:
        with TestClient(app_off) as client:
            st = client.get("/api/v1/status")
            assert st.status_code == 200
            bio = st.json()["biometrics"]
            assert bio["enabled"] is False
            assert bio["running"] is False
    finally:
        app_off.state.pipeline.repository.close()

    cfg_on = _make_cfg(
        tmp_path / "on",
        biometrics_enabled=True,
        biometrics_data_dir=tmp_path / "on" / "biometrics",
    )
    app_on = create_app(cfg_on)
    try:
        with TestClient(app_on) as client:
            st = client.get("/api/v1/status")
            assert st.status_code == 200
            bio = st.json()["biometrics"]
            assert bio["enabled"] is True
            assert bio["running"] is True
            assert "queue_depth" in bio
            assert "face_ready" in bio and "alpr_ready" in bio
    finally:
        app_on.state.pipeline.repository.close()
