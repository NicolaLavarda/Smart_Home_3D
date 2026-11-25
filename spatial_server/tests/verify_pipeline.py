from __future__ import annotations

import json
import math
import tempfile
import time
from pathlib import Path
import numpy as np
from fastapi.testclient import TestClient

from spatial_server.config import REPO_ROOT, SpatialServerConfig
from spatial_server.domain.models import BoundingBox2D, DetectionEvent, PnPCorrespondence
from spatial_server.geometry import TrimeshGroundRaycaster
from spatial_server.main import create_app
from spatial_server.optics import (
    EquirectangularPanoramicOpticalModel,
    PinholeRadTanOpticalModel,
    create_optical_model_from_manifest,
)
from spatial_server.persistence import SQLiteWALTrackRepository
from spatial_server.tracking import Kalman3DMultiTracker, TrackObservation3D


def test_optics_pinhole_and_panoramic() -> None:
    manifest_path = REPO_ROOT / "public" / "models" / "scene_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cam_entry = manifest["cameras"]["Cam_Carraio"]

    pinhole = create_optical_model_from_manifest("Cam_Carraio", cam_entry)
    assert isinstance(pinhole, PinholeRadTanOpticalModel)

    ray = pinhole.pixel_to_world_ray(0.5, 0.5)
    assert math.isclose(np.linalg.norm(ray.direction), 1.0, rel_tol=1e-5)
    assert abs(ray.origin[0] - (-11.29)) < 1e-3

    # Round-trip check at off-center pixel (with Brown-Conrady distortion)
    for u, v in [(0.5, 0.5), (0.3, 0.7), (0.78, 0.62)]:
        r = pinhole.pixel_to_world_ray(u, v)
        p_test = (
            r.origin[0] + 8.0 * r.direction[0],
            r.origin[1] + 8.0 * r.direction[1],
            r.origin[2] + 8.0 * r.direction[2],
        )
        uv_back = pinhole.world_point_to_pixel(p_test)
        assert uv_back is not None
        assert abs(uv_back[0] - u) < 1e-3 and abs(uv_back[1] - v) < 1e-3, f"Roundtrip mismatch: {(u, v)} -> {uv_back}"

    # Equirectangular panoramic 180-deg strategy (future Reolink Duo 3 PoE)
    pano = EquirectangularPanoramicOpticalModel(
        camera_id="Cam_Duo3",
        extrinsic_cv_to_world=cam_entry["gltf_transform"]["extrinsic_cv_to_world"],
        fov_h_deg=180.0,
        fov_v_deg=55.0,
    )
    r_left = pano.pixel_to_world_ray(0.1, 0.6)
    r_right = pano.pixel_to_world_ray(0.9, 0.6)
    dot = float(np.dot(r_left.direction, r_right.direction))
    assert dot < 0.0, "180-deg panoramic edge rays should span wide hemisphere"

    p_pano = (
        r_left.origin[0] + 6.0 * r_left.direction[0],
        r_left.origin[1] + 6.0 * r_left.direction[1],
        r_left.origin[2] + 6.0 * r_left.direction[2],
    )
    uv_pano = pano.world_point_to_pixel(p_pano)
    assert uv_pano is not None and abs(uv_pano[0] - 0.1) < 1e-3 and abs(uv_pano[1] - 0.6) < 1e-3
    print("[PASS] Optics unit tests (PinholeRadTan + EquirectangularPanoramic 180-deg)")


def test_openvino_letterbox_and_ovdict_parsing() -> None:
    from types import SimpleNamespace
    from unittest.mock import patch
    from spatial_server.ingestion.openvino_rtsp_source import OpenVINORtspDetectionSource

    src = OpenVINORtspDetectionSource.__new__(OpenVINORtspDetectionSource)
    src.camera_id = "Cam_Carraio"
    src.conf_threshold = 0.35

    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    canvas, pad_l, pad_t, new_w, new_h = src._letterbox_bgr(frame, 640)
    assert canvas.shape == (640, 640, 3)
    assert (pad_l, pad_t, new_w, new_h) == (0, 140, 640, 360)

    # Synthetic (1, 84, 8400) OpenVINO output containing a car box near right edge
    # Placed in 640x640 letterbox coords: center (512, 320), size (160, 180)
    # -> normalized original 640x360 coords: x=[0.675, 0.925], y=[(320-90-140)/360, (320+90-140)/360] = [0.25, 0.75]
    raw_out = np.zeros((1, 84, 8400), dtype=np.float32)
    raw_out[0, 0, 10] = 512.0  # cx
    raw_out[0, 1, 10] = 320.0  # cy
    raw_out[0, 2, 10] = 160.0  # bw
    raw_out[0, 3, 10] = 180.0  # bh
    raw_out[0, 4 + 2, 10] = 0.39  # COCO class 2 = 'car' (below old 0.45, above 0.35)

    out_port = object()

    class _MockCompiled:
        def output(self, idx: int):
            assert idx == 0
            return out_port

        def __call__(self, inputs):
            assert inputs[0].shape == (1, 3, 640, 640)
            return {out_port: SimpleNamespace(data=raw_out)}

    src._compiled_ov = _MockCompiled()
    events = src._infer_openvino_yolo(frame, ts=1234.5)
    assert len(events) == 1
    ev = events[0]
    assert ev.class_label == "car"
    assert abs(ev.confidence - 0.39) < 1e-4
    assert abs(ev.bbox.x_min - 0.675) < 1e-3 and abs(ev.bbox.x_max - 0.925) < 1e-3
    assert abs(ev.bbox.y_min - 0.25) < 1e-3 and abs(ev.bbox.y_max - 0.75) < 1e-3

    # Verify compile/warmup automatic fallback from AUTO to CPU if primary device raises
    class _FakeCore:
        def read_model(self, _p: str):
            return object()

        def compile_model(self, _m, device_name: str):
            if device_name == "AUTO":
                raise RuntimeError("Skylake HD 530 OpenCL unsupported kernel")
            return _MockCompiled()

    src_fb = OpenVINORtspDetectionSource.__new__(OpenVINORtspDetectionSource)
    src_fb.openvino_device = "AUTO"
    src_fb.model_path = Path("fake_model.xml")
    src_fb._yolo_model = None
    src_fb._compiled_ov = None
    src_fb._hog = None
    src_fb._bg_sub = None
    src_fb._rtsp_connected = False
    src_fb._frames_inferred = 0
    src_fb._raw_detections_total = 0
    src_fb._last_error = None
    with tempfile.TemporaryDirectory() as tmp_ov:
        fake_xml = Path(tmp_ov) / "yolov8n.xml"
        fake_xml.write_text("<net/>", encoding="utf-8")
        src_fb.model_path = fake_xml
        fake_ov_mod = SimpleNamespace(Core=lambda: _FakeCore())
        with patch.dict("sys.modules", {"openvino": fake_ov_mod}):
            src_fb._init_detector()
    assert src_fb._compiled_ov is not None
    assert "CPU<-AUTO" in src_fb._backend_name
    assert "rtsp=waiting" in src_fb.status_details()
    print("[PASS] OpenVINO letterbox geometry, OVDict unwrapping & AUTO->CPU warmup fallback")


def test_stationary_persistence_anchor_and_slow_drift() -> None:
    from spatial_server.domain.models import SpatialPoint3D, TrackedEntity3D
    from spatial_server.main import build_pipeline_service

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cfg = SpatialServerConfig(
            host="127.0.0.1",
            port=8765,
            manifest_path=REPO_ROOT / "public" / "models" / "scene_manifest.json",
            glb_path=REPO_ROOT / "public" / "models" / "house_optimized.glb",
            sqlite_db_path=tmp_dir / "anchor_test.db",
            calibration_override_path=tmp_dir / "calibs.json",
            data_dir=tmp_dir,
            models_dir=tmp_dir,
            default_ingestion_mode="synthetic",
            go2rtc_rtsp_url="",
            mqtt_host="",
            mqtt_port=1883,
            mqtt_user="",
            mqtt_password="",
            mqtt_topic_prefix="",
            openvino_device="CPU",
            openvino_model_path="",
            db_retention_days=30,
            face_webhook_url="",
            persist_min_displacement_m=0.15,
            persist_heartbeat_s=10.0,
        )
        svc = build_pipeline_service(cfg)
        try:
            def mk_track(x: float, z: float, ts: float, identity=None) -> TrackedEntity3D:
                return TrackedEntity3D(
                    track_id=47,
                    class_label="car",
                    confidence=0.85,
                    identity=identity,
                    identity_confidence=0.9 if identity else 0.0,
                    state=SpatialPoint3D(x=x, y=0.0, z=z, camera_sources=["Cam_Carraio"]),
                    last_seen=ts,
                )

            # 1. First detection always persists
            assert len(svc._select_tracks_to_persist([mk_track(-10.0, 10.0, 1000.0)])) == 1
            # 2. Small jitter (< 0.15m) is skipped
            assert len(svc._select_tracks_to_persist([mk_track(-10.05, 10.04, 1001.0)])) == 0
            # 3. Slow drift (+0.04m per frame): each step < 0.15m vs t-1, but saves once >= 0.15m vs anchor
            assert len(svc._select_tracks_to_persist([mk_track(-10.08, 10.0, 1002.0)])) == 0
            assert len(svc._select_tracks_to_persist([mk_track(-10.12, 10.0, 1003.0)])) == 0
            assert len(svc._select_tracks_to_persist([mk_track(-10.16, 10.0, 1004.0)])) == 1
            # 4. Stationary heartbeat fires after >= 10s
            assert len(svc._select_tracks_to_persist([mk_track(-10.16, 10.0, 1013.9)])) == 0
            assert len(svc._select_tracks_to_persist([mk_track(-10.16, 10.0, 1014.1)])) == 1
            # 5. Identity upgrade persists immediately even at 0m displacement
            assert len(svc._select_tracks_to_persist([mk_track(-10.16, 10.0, 1015.0, identity="Nicola")])) == 1
            assert svc.persist_saved_count == 4 and svc.persist_skipped_count == 4
            # 6. Expired track clears anchor from RAM
            assert svc._select_tracks_to_persist([]) == []
            assert svc._persist_anchors == {}
            print("[PASS] Stationary persistence anchor, slow-drift capture & checkpoint heartbeat")
        finally:
            svc.repository.close()


def test_trimesh_ground_raycaster() -> None:
    manifest_path = REPO_ROOT / "public" / "models" / "scene_manifest.json"
    glb_path = REPO_ROOT / "public" / "models" / "house_optimized.glb"
    raycaster = TrimeshGroundRaycaster(glb_path, manifest_path)

    assert raycaster.ground_mesh is not None, "Expected TrimeshGroundRaycaster to load ground colliders from GLB"
    assert len(raycaster.matched_nodes) >= 5, f"Matched too few ground nodes: {raycaster.matched_nodes}"
    assert len(raycaster.ground_mesh.faces) > 0

    # Cast a downward ray from Cam_Carraio toward Driveway_Gravel (+Z South in Three.js)
    from spatial_server.domain.models import Ray3D

    target = np.array([-13.0, 0.0, 12.0], dtype=np.float64)
    origin = np.array([-11.29, 1.68, 6.28], dtype=np.float64)
    d = target - origin
    d = d / np.linalg.norm(d)
    hit = raycaster.intersect_ground_detailed(Ray3D(origin=tuple(origin.tolist()), direction=tuple(d.tolist())))
    assert hit is not None
    assert not hit.used_fallback_plane, "Expected direct hit against GLB ground collider mesh, not plane fallback"
    assert abs(hit.point[0] - (-13.0)) < 0.25 and abs(hit.point[2] - 12.0) < 0.25 and abs(hit.point[1]) < 0.25
    print(f"[PASS] TrimeshGroundRaycaster loaded {len(raycaster.matched_nodes)} nodes ({len(raycaster.ground_mesh.faces)} tris) & hit {hit.point}")


def test_kalman_tracker_and_multicam_fusion() -> None:
    tracker = Kalman3DMultiTracker()
    base_t = 1000.0
    tracks = []
    for step in range(12):
        ts = base_t + step * 0.1
        px = -3.0 + 1.2 * (step * 0.1)
        pz = 8.0 + 0.5 * (step * 0.1)
        obs = [
            TrackObservation3D("Cam_Carraio", ts, "person", (px, 0.0, pz), 0.92, identity="Nicola", identity_confidence=0.95),
            TrackObservation3D("Cam_Duo3", ts + 0.01, "person", (px + 0.05, 0.0, pz - 0.05), 0.89),
            TrackObservation3D("Cam_Carraio", ts, "car", (-2.0, 0.0, 15.0 - 2.0 * (step * 0.1)), 0.94),
        ]
        tracks = tracker.update(obs, ts)

    assert len(tracks) == 2, f"Expected 2 fused tracks (1 person + 1 car), got {len(tracks)}"
    person_tr = next(t for t in tracks if t.class_label == "person")
    assert person_tr.identity == "Nicola"
    assert set(person_tr.state.camera_sources) == {"Cam_Carraio", "Cam_Duo3"}
    assert person_tr.state.vx > 0.5, f"Expected positive vx velocity estimate, got {person_tr.state.vx}"
    print("[PASS] Kalman3DMultiTracker 6D kinematics & multi-camera covariance fusion")


def test_sqlite_wal_repository() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test_spatial.db"
        repo = SQLiteWALTrackRepository(db_path)
        assert repo.get_journal_mode() == "wal"

        tracker = Kalman3DMultiTracker()
        t0 = time.time() - 30.0
        batch = []
        for i in range(10):
            ts = t0 + i * 2.0
            batch.extend(
                tracker.update(
                    [TrackObservation3D("Cam_Carraio", ts, "person", (-3.5 + i * 0.2, 0.0, 6.0 + i * 0.4), 0.9, "Nicola", 0.91)],
                    ts,
                )
            )
        inserted = repo.append_batch(batch)
        assert inserted == 10

        rows = repo.query_time_range(t0 - 1.0, t0 + 25.0, classes=["person"], zone_bbox=(-5.0, 0.0, 4.0, 12.0))
        assert len(rows) == 10
        assert rows[0]["identity"] == "Nicola"

        bins = repo.query_timeline_density(t0 - 5.0, t0 + 25.0, buckets=10)
        assert len(bins) == 10 and sum(b["count"] for b in bins) == 10

        deleted = repo.prune_older_than(t0 + 9.0)
        assert deleted == 5
        repo.close()
        print(f"[PASS] SQLiteWALTrackRepository WAL + {'R-Tree' if repo.has_rtree else 'B-Tree'} queries & pruning")


def test_fastapi_rest_and_websocket() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cfg = SpatialServerConfig(
            host="127.0.0.1",
            port=8000,
            manifest_path=REPO_ROOT / "public" / "models" / "scene_manifest.json",
            glb_path=REPO_ROOT / "public" / "models" / "house_optimized.glb",
            sqlite_db_path=tmp_dir / "spatial_test.db",
            calibration_override_path=tmp_dir / "calibs.json",
            data_dir=tmp_dir,
            models_dir=tmp_dir,
            default_ingestion_mode="synthetic",
            go2rtc_rtsp_url="rtsp://127.0.0.1:8554/carraio_sub",
            mqtt_host="127.0.0.1",
            mqtt_port=1883,
            mqtt_user="",
            mqtt_password="",
            mqtt_topic_prefix="frigate/events",
            openvino_device="CPU",
            openvino_model_path="",
            db_retention_days=30,
            face_webhook_url="",
            auth_required=False,
        )
        app = create_app(cfg)

        try:
            with TestClient(app) as client:
                st = client.get("/api/v1/status")
                assert st.status_code == 200
                st_json = st.json()
                assert "Cam_Carraio" in st_json["active_cameras"]
                assert st_json["sqlite_journal_mode"] == "wal"
                assert st_json["ground_triangles_count"] > 0

                # Flip Cam_Carraio 180 deg in test calibration so it points at Driveway_Gravel (+Z)
                cam_calib = client.get("/api/v1/calibration/Cam_Carraio").json()["calibration"]
                T_gl = np.array(cam_calib["matrix_world_gl"], dtype=np.float64).reshape((4, 4))
                R_flip_y = np.diag([-1.0, 1.0, -1.0, 1.0])
                T_flipped = T_gl @ R_flip_y

                post_cal = client.post(
                    "/api/v1/calibration/Cam_Carraio",
                    json={
                        "camera_id": "Cam_Carraio",
                        "fov_v_deg": 42.0,
                        "fov_h_deg": 80.0,
                        "distortion_coeffs": [-0.18, 0.04, 0.0, 0.0, 0.0],
                        "calibrated_matrix_world_gl": T_flipped.reshape(-1).tolist(),
                    },
                )
                assert post_cal.status_code == 200

                # Test SolvePnPRansac with 6 valid world points in front of calibrated camera
                pinhole = app.state.pipeline.optical_models["Cam_Carraio"]
                pts_w = [(-13.0, 0.0, 10.0), (-10.0, 0.0, 12.0), (-13.5, 0.0, 15.0), (-9.5, 0.0, 17.0), (-12.0, 1.2, 13.0), (-11.0, 0.5, 9.5)]
                corrs = []
                for p in pts_w:
                    uv = pinhole.world_point_to_pixel(p)
                    assert uv is not None
                    corrs.append(PnPCorrespondence(world_point=p, pixel_uv=uv).model_dump())

                pnp_resp = client.post("/api/v1/calibration/solve-pnp", json={"camera_id": "Cam_Carraio", "correspondences": corrs})
                assert pnp_resp.status_code == 200
                assert pnp_resp.json()["reprojection_error_px"] < 2.0

                # WebSocket live frame check + HTTP detection injection
                with client.websocket_connect("/ws/spatial") as ws:
                    hello = json.loads(ws.receive_text())
                    assert hello["type"] == "server_status"

                    now_ts = time.time()
                    det_resp = client.post(
                        "/api/v1/detections",
                        json=DetectionEvent(
                            camera_id="Cam_Carraio",
                            timestamp=now_ts,
                            class_label="person",
                            confidence=0.95,
                            bbox=BoundingBox2D(x_min=0.45, y_min=0.55, x_max=0.55, y_max=0.80),
                            sub_label="Nicola",
                            face_confidence=0.92,
                        ).model_dump(),
                    )
                    assert det_resp.status_code == 200
                    frame = json.loads(ws.receive_text())
                    assert frame["type"] == "spatial_frame"
                    assert len(frame["active_tracks"]) >= 1

                time.sleep(0.6)  # Allow batch writer to flush WAL
                tracks_resp = client.get(f"/api/v1/tracks?t_start={now_ts - 60}&t_end={now_ts + 60}")
                assert tracks_resp.status_code == 200 and tracks_resp.json()["count"] >= 1

                dens_resp = client.get(f"/api/v1/timeline-density?t_start={now_ts - 60}&t_end={now_ts + 60}&buckets=20")
                assert dens_resp.status_code == 200 and len(dens_resp.json()["bins"]) == 20

                mode_resp = client.post("/api/v1/ingestion/mode", json={"mode": "synthetic"})
                assert mode_resp.status_code == 200 and mode_resp.json()["ingestion_mode"] == "synthetic"
                print("[PASS] FastAPI REST endpoints, SolvePnPRansac & WS /ws/spatial integration")
        finally:
            app.state.pipeline.repository.close()


def test_multicam_portico_raycast_openvino_and_overlap_fusion() -> None:
    from spatial_server.main import build_pipeline_service

    manifest_path = REPO_ROOT / "public" / "models" / "scene_manifest.json"
    glb_path = REPO_ROOT / "public" / "models" / "house_optimized.glb"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 1. Manifest SSoT + Pinhole optical model for Cam_Portico (Reolink RLC-811A)
    assert "Cam_Portico" in manifest["cameras"], "Cam_Portico missing from scene_manifest.json"
    portico_entry = manifest["cameras"]["Cam_Portico"]
    assert portico_entry["is_real_security_camera"] is True
    assert portico_entry["ha_camera_entity"] == "camera.portico"
    assert portico_entry["stream_id"] == "portico_main"
    assert portico_entry["sub_stream_id"] == "portico_sub"
    assert portico_entry["camera_ip"] == "192.168.86.51"
    assert abs(float(portico_entry["fov_h_deg"]) - 105.0) < 0.2
    assert abs(float(portico_entry["fov_v_deg"]) - 72.49) < 0.2

    portico_model = create_optical_model_from_manifest("Cam_Portico", portico_entry)
    assert isinstance(portico_model, PinholeRadTanOpticalModel)

    center_ray = portico_model.pixel_to_world_ray(0.5, 0.5)
    assert abs(center_ray.origin[0] - 13.24) < 1e-3
    assert abs(center_ray.origin[1] - 2.15) < 1e-3
    assert abs(center_ray.origin[2] - 8.22) < 1e-3
    assert math.isclose(np.linalg.norm(center_ray.direction), 1.0, rel_tol=1e-5)

    for u, v in [(0.5, 0.5), (0.25, 0.65), (0.8, 0.7)]:
        r = portico_model.pixel_to_world_ray(u, v)
        p_test = (
            r.origin[0] + 6.0 * r.direction[0],
            r.origin[1] + 6.0 * r.direction[1],
            r.origin[2] + 6.0 * r.direction[2],
        )
        uv_back = portico_model.world_point_to_pixel(p_test)
        assert uv_back is not None
        assert abs(uv_back[0] - u) < 1e-3 and abs(uv_back[1] - v) < 1e-3

    # 2. Ground raycast from Cam_Portico hits actual GLB portico/garden collider (not fallback plane)
    raycaster = TrimeshGroundRaycaster(glb_path, manifest_path)
    hit = raycaster.intersect_ground_detailed(center_ray)
    assert hit is not None
    assert not hit.used_fallback_plane, "Cam_Portico center ray should hit GLB ground collider mesh"
    assert 0.0 <= hit.point[0] <= 14.0 and 8.0 <= hit.point[2] <= 22.0 and abs(hit.point[1]) < 0.25

    # 3. Multi-camera OpenVINO target resolution, FPS budget split & MQTT camera aliasing
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cfg = SpatialServerConfig(
            host="127.0.0.1",
            port=8765,
            manifest_path=manifest_path,
            glb_path=glb_path,
            sqlite_db_path=tmp_dir / "multicam_test.db",
            calibration_override_path=tmp_dir / "calibs.json",
            data_dir=tmp_dir,
            models_dir=tmp_dir,
            default_ingestion_mode="synthetic",
            go2rtc_rtsp_url="rtsp://127.0.0.1:8554/carraio_sub",
            mqtt_host="127.0.0.1",
            mqtt_port=1883,
            mqtt_user="",
            mqtt_password="",
            mqtt_topic_prefix="frigate/events",
            openvino_device="CPU",
            openvino_model_path="",
            db_retention_days=7,
            face_webhook_url="",
            openvino_target_fps=7.0,
            auth_required=False,
        )
        svc = build_pipeline_service(cfg)
        try:
            assert {"Cam_Carraio", "Cam_Portico"}.issubset(set(svc.optical_models.keys()))
            targets = dict(svc._resolve_openvino_camera_targets())
            assert targets["Cam_Carraio"].endswith("/carraio_sub")
            assert targets["Cam_Portico"].endswith("/portico_sub")

            ov_sources = svc._build_openvino_sources()
            assert len(ov_sources) >= 2
            by_cam = {s.camera_id: s for s in ov_sources}
            assert "Cam_Carraio" in by_cam and "Cam_Portico" in by_cam
            assert by_cam["Cam_Carraio"]._infer_lock is by_cam["Cam_Portico"]._infer_lock
            assert by_cam["Cam_Carraio"].frame_interval_s > (1.0 / 7.0)  # FPS budget split across cameras
            assert "openvino:Cam_Portico" in by_cam["Cam_Portico"].status_details()

            mqtt_src = svc._build_mqtt_source()
            evt_portico = mqtt_src._parse_payload(
                json.dumps({
                    "type": "new",
                    "after": {
                        "label": "person",
                        "camera": "portico",
                        "box": [0.4, 0.4, 0.5, 0.8],
                        "score": 0.91,
                    },
                })
            )
            assert evt_portico is not None and evt_portico.camera_id == "Cam_Portico"
        finally:
            svc.repository.close()

    # 4. Intelligent overlap fusion: out-of-order async frames + range-weighted covariance
    tracker = Kalman3DMultiTracker()
    tracks_1 = tracker.update(
        [
            TrackObservation3D(
                camera_id="Cam_Carraio",
                timestamp=2000.0,
                class_label="person",
                position=(6.0, 0.0, 14.0),
                confidence=0.88,
                range_m=18.5,
            )
        ],
        now_ts=2000.0,
    )
    assert len(tracks_1) == 1
    tracks_2 = tracker.update(
        [
            TrackObservation3D(
                camera_id="Cam_Portico",
                timestamp=1999.94,  # slightly older async RTSP frame from closer camera
                class_label="person",
                position=(6.8, 0.0, 14.2),
                confidence=0.90,
                range_m=3.8,
            )
        ],
        now_ts=1999.94,
    )
    assert len(tracks_2) == 1, f"Overlapping cameras must fuse into 1 track_id, got {len(tracks_2)}"
    fused = tracks_2[0]
    assert set(fused.state.camera_sources) == {"Cam_Carraio", "Cam_Portico"}
    assert fused.last_seen >= 2000.0, "Out-of-order frame must not move track timestamp backwards"
    assert fused.state.x > 6.45, f"Closer camera (Cam_Portico) should pull fused estimate closer to 6.8, got {fused.state.x}"
    print("[PASS] Cam_Portico SSoT optics, GLB raycast, multi-camera OpenVINO & range-weighted overlap fusion")


def test_multicam_ingresso_180_equirectangular_raycast_and_3cam_fusion() -> None:
    from spatial_server.main import build_pipeline_service

    manifest_path = REPO_ROOT / "public" / "models" / "scene_manifest.json"
    glb_path = REPO_ROOT / "public" / "models" / "house_optimized.glb"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "Cam_Ingresso" in manifest["cameras"], "Cam_Ingresso missing from scene_manifest.json"
    ing_entry = manifest["cameras"]["Cam_Ingresso"]
    assert ing_entry["is_real_security_camera"] is True
    assert ing_entry["ha_camera_entity"] == "camera.ingresso"
    assert ing_entry["stream_id"] == "ingresso_main"
    assert ing_entry["sub_stream_id"] == "ingresso_sub"
    assert ing_entry["camera_ip"] == "192.168.86.53"
    assert ing_entry["optical_model"] == "equirectangular_180"
    assert ing_entry["is_panoramic_180"] is True
    assert math.isclose(ing_entry["fov_h_deg"], 180.0, abs_tol=0.1)
    assert math.isclose(ing_entry["fov_v_deg"], 55.0, abs_tol=0.1)
    assert math.isclose(ing_entry["aspect_ratio"], 32.0 / 9.0, abs_tol=0.01)

    # 1. Optical model factory builds EquirectangularPanoramicOpticalModel at (-0.1, 3.5, 5.936) looking West (-X) -25 deg
    ing_model = create_optical_model_from_manifest("Cam_Ingresso", ing_entry)
    assert isinstance(ing_model, EquirectangularPanoramicOpticalModel)
    center_ray = ing_model.pixel_to_world_ray(0.5, 0.5)
    assert abs(center_ray.origin[0] - (-0.10)) < 1e-3
    assert abs(center_ray.origin[1] - 3.50) < 1e-3
    assert abs(center_ray.origin[2] - 5.936) < 1e-3
    assert math.isclose(center_ray.direction[0], -math.cos(math.radians(25.0)), abs_tol=1e-3)
    assert math.isclose(center_ray.direction[1], -math.sin(math.radians(25.0)), abs_tol=1e-3)
    assert abs(center_ray.direction[2]) < 1e-3

    # Wide 180-deg azimuth span: left ray points South (+Z glTF), right ray points North (-Z glTF)
    ray_left = ing_model.pixel_to_world_ray(0.15, 0.65)
    ray_right = ing_model.pixel_to_world_ray(0.85, 0.65)
    assert ray_left.direction[2] > 0.5 and ray_right.direction[2] < -0.5

    for u, v in [(0.5, 0.5), (0.15, 0.65), (0.85, 0.65)]:
        r = ing_model.pixel_to_world_ray(u, v)
        p_test = (
            r.origin[0] + 6.0 * r.direction[0],
            r.origin[1] + 6.0 * r.direction[1],
            r.origin[2] + 6.0 * r.direction[2],
        )
        uv_back = ing_model.world_point_to_pixel(p_test)
        assert uv_back is not None
        assert abs(uv_back[0] - u) < 1e-3 and abs(uv_back[1] - v) < 1e-3

    # 2. Ground raycast across west yard hits real GLB ground collider meshes (not fallback plane)
    raycaster = TrimeshGroundRaycaster(glb_path, manifest_path)
    hit_center = raycaster.intersect_ground_detailed(center_ray)
    assert hit_center is not None
    assert not hit_center.used_fallback_plane, "Cam_Ingresso center ray should hit GLB west yard collider"
    assert hit_center.point[0] < -5.0 and abs(hit_center.point[1]) < 0.25 and 4.5 <= hit_center.point[2] <= 7.5

    hit_south = raycaster.intersect_ground_detailed(ray_left)
    assert hit_south is not None and not hit_south.used_fallback_plane
    assert hit_south.point[0] < 0.0 and hit_south.point[2] > 8.0

    # 3. 3-camera OpenVINO shared-model target resolution, FPS budget split & MQTT camera aliasing
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cfg = SpatialServerConfig(
            host="127.0.0.1",
            port=8765,
            manifest_path=manifest_path,
            glb_path=glb_path,
            sqlite_db_path=tmp_dir / "multicam3_test.db",
            calibration_override_path=tmp_dir / "calibs.json",
            data_dir=tmp_dir,
            models_dir=tmp_dir,
            default_ingestion_mode="synthetic",
            go2rtc_rtsp_url="rtsp://127.0.0.1:8554/carraio_sub",
            mqtt_host="127.0.0.1",
            mqtt_port=1883,
            mqtt_user="",
            mqtt_password="",
            mqtt_topic_prefix="frigate/events",
            openvino_device="CPU",
            openvino_model_path="",
            db_retention_days=7,
            face_webhook_url="",
            openvino_target_fps=7.0,
            auth_required=False,
        )
        svc = build_pipeline_service(cfg)
        try:
            assert {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso"}.issubset(set(svc.optical_models.keys()))
            assert isinstance(svc.optical_models["Cam_Ingresso"], EquirectangularPanoramicOpticalModel)

            targets = dict(svc._resolve_openvino_camera_targets())
            assert targets["Cam_Carraio"].endswith("/carraio_sub")
            assert targets["Cam_Portico"].endswith("/portico_sub")
            assert targets["Cam_Ingresso"].endswith("/ingresso_sub")

            ov_sources = svc._build_openvino_sources()
            assert len(ov_sources) >= 3
            by_cam = {s.camera_id: s for s in ov_sources}
            assert {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso"}.issubset(by_cam.keys())
            assert by_cam["Cam_Carraio"]._infer_lock is by_cam["Cam_Ingresso"]._infer_lock
            assert by_cam["Cam_Portico"]._infer_lock is by_cam["Cam_Ingresso"]._infer_lock
            # FPS budget split across 3 cameras (target ~2.33 FPS each -> interval >= 0.40s)
            assert by_cam["Cam_Ingresso"].frame_interval_s >= (3.0 / 7.0) - 0.02
            assert "openvino:Cam_Ingresso" in by_cam["Cam_Ingresso"].status_details()

            mqtt_src = svc._build_mqtt_source()
            evt_ing = mqtt_src._parse_payload(
                json.dumps({
                    "type": "new",
                    "after": {
                        "label": "person",
                        "camera": "ingresso",
                        "box": [0.45, 0.4, 0.55, 0.78],
                        "score": 0.93,
                    },
                })
            )
            assert evt_ing is not None and evt_ing.camera_id == "Cam_Ingresso"
        finally:
            svc.repository.close()

    # 4. Intelligent west-yard overlap fusion: Cam_Carraio + Cam_Ingresso observing same person near walkway
    tracker = Kalman3DMultiTracker()
    t1 = tracker.update(
        [
            TrackObservation3D(
                camera_id="Cam_Carraio",
                timestamp=3000.0,
                class_label="person",
                position=(-4.2, 0.0, 8.2),
                confidence=0.87,
                range_m=7.4,
            )
        ],
        now_ts=3000.0,
    )
    assert len(t1) == 1
    t2 = tracker.update(
        [
            TrackObservation3D(
                camera_id="Cam_Ingresso",
                timestamp=3000.08,
                class_label="person",
                position=(-4.0, 0.0, 8.0),
                confidence=0.92,
                range_m=5.8,
            )
        ],
        now_ts=3000.08,
    )
    assert len(t2) == 1, f"Cam_Carraio + Cam_Ingresso west-yard overlap must fuse into 1 track_id, got {len(t2)}"
    assert set(t2[0].state.camera_sources) == {"Cam_Carraio", "Cam_Ingresso"}
    print("[PASS] Cam_Ingresso 180-deg equirectangular SSoT optics, GLB raycast, 3-cam OpenVINO & overlap fusion")


def test_multicam_stradina_180_equirectangular_4cam_openvino_and_overlap() -> None:
    from spatial_server.main import build_pipeline_service

    manifest_path = REPO_ROOT / "public" / "models" / "scene_manifest.json"
    glb_path = REPO_ROOT / "public" / "models" / "house_optimized.glb"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "Cam_Stradina" in manifest["cameras"], "Cam_Stradina missing from scene_manifest.json"
    str_entry = manifest["cameras"]["Cam_Stradina"]
    assert str_entry["is_real_security_camera"] is True
    assert str_entry["ha_camera_entity"] == "camera.stradina"
    assert str_entry["stream_id"] == "stradina_main"
    assert str_entry["sub_stream_id"] == "stradina_sub"
    assert str_entry["camera_ip"] == "192.168.86.55"
    assert str_entry["optical_model"] == "equirectangular_180"
    assert str_entry["is_panoramic_180"] is True
    assert math.isclose(str_entry["fov_h_deg"], 180.0, abs_tol=0.1)
    assert math.isclose(str_entry["fov_v_deg"], 55.0, abs_tol=0.1)
    assert math.isclose(str_entry["aspect_ratio"], 32.0 / 9.0, abs_tol=0.01)

    # 1. Optical model factory builds EquirectangularPanoramicOpticalModel at glTF (13.41, 2.77, -0.12)
    #    looking North (-Z glTF) rotated 10 deg West (-X) and pitched 30 deg down (-Y)
    str_model = create_optical_model_from_manifest("Cam_Stradina", str_entry)
    assert isinstance(str_model, EquirectangularPanoramicOpticalModel)
    center_ray = str_model.pixel_to_world_ray(0.5, 0.5)
    assert abs(center_ray.origin[0] - 13.41) < 1e-3
    assert abs(center_ray.origin[1] - 2.77) < 1e-3
    assert abs(center_ray.origin[2] - (-0.12)) < 1e-3
    exp_dx = -math.cos(math.radians(30.0)) * math.sin(math.radians(10.0))
    exp_dy = -math.sin(math.radians(30.0))
    exp_dz = -math.cos(math.radians(30.0)) * math.cos(math.radians(10.0))
    assert math.isclose(center_ray.direction[0], exp_dx, abs_tol=1e-3)
    assert math.isclose(center_ray.direction[1], exp_dy, abs_tol=1e-3)
    assert math.isclose(center_ray.direction[2], exp_dz, abs_tol=1e-3)

    # Wide 180-deg span: left ray points West (-X), right ray points East (+X)
    ray_left = str_model.pixel_to_world_ray(0.15, 0.65)
    ray_right = str_model.pixel_to_world_ray(0.85, 0.65)
    assert ray_left.direction[0] < -0.5 and ray_right.direction[0] > 0.5

    for u, v in [(0.5, 0.5), (0.15, 0.65), (0.85, 0.65)]:
        r = str_model.pixel_to_world_ray(u, v)
        p_test = (
            r.origin[0] + 6.0 * r.direction[0],
            r.origin[1] + 6.0 * r.direction[1],
            r.origin[2] + 6.0 * r.direction[2],
        )
        uv_back = str_model.world_point_to_pixel(p_test)
        assert uv_back is not None
        assert abs(uv_back[0] - u) < 1e-3 and abs(uv_back[1] - v) < 1e-3

    # 2. Ground raycast hits northern lane (Z_gltf < -3.5 via infinite ground plane)
    #    and west-along-wall ray (u=0.08, v=0.85) hits real GLB Site_Foundation_Earth collider
    raycaster = TrimeshGroundRaycaster(glb_path, manifest_path)
    hit_center = raycaster.intersect_ground_detailed(center_ray)
    assert hit_center is not None
    assert 11.0 <= hit_center.point[0] <= 14.0 and abs(hit_center.point[1]) < 0.25 and hit_center.point[2] < -3.5

    along_wall_ray = str_model.pixel_to_world_ray(0.08, 0.85)
    hit_near = raycaster.intersect_ground_detailed(along_wall_ray)
    assert hit_near is not None
    assert not hit_near.used_fallback_plane, "West-along-wall ray from Cam_Stradina should hit GLB ground collider"

    # 3. 4-camera OpenVINO shared-model target resolution, FPS budget split & MQTT aliasing
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cfg = SpatialServerConfig(
            host="127.0.0.1",
            port=8765,
            manifest_path=manifest_path,
            glb_path=glb_path,
            sqlite_db_path=tmp_dir / "multicam4_test.db",
            calibration_override_path=tmp_dir / "calibs.json",
            data_dir=tmp_dir,
            models_dir=tmp_dir,
            default_ingestion_mode="synthetic",
            go2rtc_rtsp_url="rtsp://127.0.0.1:8554/carraio_sub",
            mqtt_host="127.0.0.1",
            mqtt_port=1883,
            mqtt_user="",
            mqtt_password="",
            mqtt_topic_prefix="frigate/events",
            openvino_device="CPU",
            openvino_model_path="",
            db_retention_days=7,
            face_webhook_url="",
            openvino_target_fps=7.0,
            auth_required=False,
        )
        svc = build_pipeline_service(cfg)
        try:
            expected_cams = {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso", "Cam_Stradina"}
            assert expected_cams.issubset(set(svc.optical_models.keys()))
            assert isinstance(svc.optical_models["Cam_Stradina"], EquirectangularPanoramicOpticalModel)

            targets = dict(svc._resolve_openvino_camera_targets())
            assert targets["Cam_Carraio"].endswith("/carraio_sub")
            assert targets["Cam_Portico"].endswith("/portico_sub")
            assert targets["Cam_Ingresso"].endswith("/ingresso_sub")
            assert targets["Cam_Stradina"].endswith("/stradina_sub")

            ov_sources = svc._build_openvino_sources()
            assert len(ov_sources) >= 4
            by_cam = {s.camera_id: s for s in ov_sources}
            assert expected_cams.issubset(by_cam.keys())
            for cam_id in expected_cams:
                assert by_cam[cam_id]._infer_lock is by_cam["Cam_Carraio"]._infer_lock
            # 7.0 FPS split across 4 cameras -> 1.75 FPS each (interval ~0.571s)
            assert by_cam["Cam_Stradina"].frame_interval_s >= (4.0 / 7.0) - 0.02
            assert "openvino:Cam_Stradina" in by_cam["Cam_Stradina"].status_details()

            mqtt_src = svc._build_mqtt_source()
            evt_str = mqtt_src._parse_payload(
                json.dumps({
                    "type": "new",
                    "after": {
                        "label": "person",
                        "camera": "stradina",
                        "box": [0.45, 0.4, 0.55, 0.78],
                        "score": 0.92,
                    },
                })
            )
            assert evt_str is not None and evt_str.camera_id == "Cam_Stradina"
        finally:
            svc.repository.close()

    # 4. Intelligent multi-camera overlap fusion (Cam_Ingresso + Cam_Stradina near NW corner)
    tracker = Kalman3DMultiTracker()
    t1 = tracker.update(
        [
            TrackObservation3D(
                camera_id="Cam_Ingresso",
                timestamp=4000.0,
                class_label="person",
                position=(-1.5, 0.0, -1.2),
                confidence=0.88,
                range_m=7.5,
            )
        ],
        now_ts=4000.0,
    )
    assert len(t1) == 1
    t2 = tracker.update(
        [
            TrackObservation3D(
                camera_id="Cam_Stradina",
                timestamp=4000.06,
                class_label="person",
                position=(-1.3, 0.0, -1.3),
                confidence=0.86,
                range_m=14.9,
            )
        ],
        now_ts=4000.06,
    )
    assert len(t2) == 1, f"Cam_Ingresso + Cam_Stradina NW overlap must fuse into 1 track_id, got {len(t2)}"
    assert set(t2[0].state.camera_sources) == {"Cam_Ingresso", "Cam_Stradina"}
    print("[PASS] Cam_Stradina 180-deg equirectangular SSoT optics, 4-cam OpenVINO & overlap fusion")


def test_multicam_anti_cloning_cardinality_and_miscalibration_fusion() -> None:
    from spatial_server.ingestion.openvino_rtsp_source import deduplicate_2d_detections

    # 1. 2D Coarse-class NMS suppresses simultaneous 'car' + 'truck' boxes on the same vehicle
    dup_2d = deduplicate_2d_detections(
        [
            DetectionEvent(
                camera_id="Cam_Carraio",
                timestamp=5000.0,
                class_label="car",
                confidence=0.82,
                bbox=BoundingBox2D(x_min=0.30, y_min=0.40, x_max=0.62, y_max=0.82),
            ),
            DetectionEvent(
                camera_id="Cam_Carraio",
                timestamp=5000.0,
                class_label="truck",
                confidence=0.46,
                bbox=BoundingBox2D(x_min=0.31, y_min=0.38, x_max=0.63, y_max=0.83),
            ),
            DetectionEvent(
                camera_id="Cam_Carraio",
                timestamp=5000.0,
                class_label="person",
                confidence=0.88,
                bbox=BoundingBox2D(x_min=0.10, y_min=0.45, x_max=0.18, y_max=0.80),
            ),
        ]
    )
    assert len(dup_2d) == 2
    assert {e.class_label for e in dup_2d} == {"car", "person"}

    # 2. Anti-ping-pong across 3 miscalibrated cameras observing 1 stationary person asynchronously
    tracker = Kalman3DMultiTracker()
    base_ts = 5100.0
    first_tid = None
    for step in range(18):
        ts = base_ts + step * 0.08
        cam_cycle = step % 3
        if cam_cycle == 0:
            # Close pinhole camera at (-3.0, 0, 9.0)
            obs = TrackObservation3D(
                camera_id="Cam_Carraio",
                timestamp=ts,
                class_label="person",
                position=(-3.0, 0.0, 9.0),
                confidence=0.92,
                range_m=5.2,
                is_panoramic=False,
                uv_contact=(0.50, 0.78),
                ray_grazing_sin=0.35,
            )
        elif cam_cycle == 1:
            # Second pinhole camera miscalibrated by ~2.5m at (-1.1, 0, 10.6)
            obs = TrackObservation3D(
                camera_id="Cam_Portico",
                timestamp=ts,
                class_label="person",
                position=(-1.1, 0.0, 10.6),
                confidence=0.85,
                range_m=11.0,
                is_panoramic=False,
                uv_contact=(0.35, 0.72),
                ray_grazing_sin=0.24,
            )
        else:
            # 180-deg panoramic camera miscalibrated by ~3.1m near right edge at (-5.2, 0, 6.8)
            obs = TrackObservation3D(
                camera_id="Cam_Ingresso",
                timestamp=ts,
                class_label="person",
                position=(-5.2, 0.0, 6.8),
                confidence=0.80,
                range_m=8.5,
                is_panoramic=True,
                uv_contact=(0.86, 0.75),
                ray_grazing_sin=0.22,
            )

        active = tracker.update([obs], now_ts=ts)
        assert len(active) == 1, f"Expected 1 fused person track at step {step}, got {len(active)}"
        if first_tid is None:
            first_tid = active[0].track_id
        else:
            assert active[0].track_id == first_tid, "Track ID must remain stable without spawning clones"

    final_person = tracker.get_active_tracks()[0]
    assert set(final_person.state.camera_sources) == {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso"}
    speed_person = math.hypot(final_person.state.vx, final_person.state.vz)
    assert speed_person < 0.25, f"Stationary person across miscalibrated cams must not have fake ping-pong speed: {speed_person}"
    # Close pinhole Cam_Carraio (-3.0, 9.0) must have stronger pull than far/panoramic edge Cam_Ingresso (-5.2, 6.8)
    dist_to_carraio = math.hypot(final_person.state.x - (-3.0), final_person.state.z - 9.0)
    dist_to_ingresso = math.hypot(final_person.state.x - (-5.2), final_person.state.z - 6.8)
    assert dist_to_carraio < dist_to_ingresso

    # 3. Logical cardinality cap + intra-camera vehicle dedup + large 6.2m cross-camera car miscalibration
    v_tracker = Kalman3DMultiTracker()
    v_tracks_1, v_assign_1 = v_tracker.update_with_assignments(
        [
            TrackObservation3D(
                camera_id="Cam_Carraio",
                timestamp=5200.0,
                class_label="car",
                position=(-3.5, 0.0, 12.0),
                confidence=0.91,
                range_m=7.0,
                bbox_2d=(0.30, 0.40, 0.60, 0.82),
            ),
            # Duplicate 'truck' detection of the same vehicle in the same camera batch
            TrackObservation3D(
                camera_id="Cam_Carraio",
                timestamp=5200.0,
                class_label="truck",
                position=(-3.2, 0.0, 12.4),
                confidence=0.52,
                range_m=7.3,
                bbox_2d=(0.31, 0.39, 0.61, 0.83),
            ),
        ],
        now_ts=5200.0,
    )
    assert len(v_tracks_1) == 1, f"Intra-camera car+truck duplicate must yield 1 track, got {len(v_tracks_1)}"
    assert v_assign_1[0] == v_assign_1[1]

    # Cam_Portico sees 1 car in the shared zone, but projected 6.2m away due to bumper parallax + miscalibration
    v_tracks_2 = v_tracker.update(
        [
            TrackObservation3D(
                camera_id="Cam_Portico",
                timestamp=5200.12,
                class_label="car",
                position=(2.5, 0.0, 13.5),
                confidence=0.89,
                range_m=11.5,
            )
        ],
        now_ts=5200.12,
    )
    assert len(v_tracks_2) == 1, f"Logical cardinality (1 car in Cam_Carraio, 1 in Cam_Portico) must fuse into 1 track, got {len(v_tracks_2)}"
    assert set(v_tracks_2[0].state.camera_sources) == {"Cam_Carraio", "Cam_Portico"}

    # 4. Multi-person cardinality: 2 real people seen by Cam_Carraio & 2 seen by miscalibrated Cam_Ingresso -> exactly 2 tracks
    p2_tracker = Kalman3DMultiTracker()
    p2_t1 = p2_tracker.update(
        [
            TrackObservation3D("Cam_Carraio", 5300.0, "person", (-4.5, 0.0, 8.0), 0.93, range_m=6.0),
            TrackObservation3D("Cam_Carraio", 5300.0, "person", (-1.5, 0.0, 8.5), 0.90, range_m=7.2),
        ],
        now_ts=5300.0,
    )
    assert len(p2_t1) == 2

    # Cam_Ingresso sees both people shifted by ~1.8m -> must associate 1-to-1 and keep strictly 2 tracks (never 3 or 4)
    p2_t2 = p2_tracker.update(
        [
            TrackObservation3D("Cam_Ingresso", 5300.1, "person", (-3.1, 0.0, 9.1), 0.86, range_m=7.5, is_panoramic=True),
            TrackObservation3D("Cam_Ingresso", 5300.1, "person", (-0.1, 0.0, 9.6), 0.85, range_m=8.8, is_panoramic=True),
        ],
        now_ts=5300.1,
    )
    assert len(p2_t2) == 2, f"Expected strictly 2 tracks for 2 people seen by 2 cameras, got {len(p2_t2)}"
    for tr in p2_t2:
        assert set(tr.state.camera_sources) == {"Cam_Carraio", "Cam_Ingresso"}

    print("[PASS] Multi-camera anti-cloning, 2D/3D coarse-class NMS, anti-ping-pong & logical zone cardinality cap")


if __name__ == "__main__":
    test_optics_pinhole_and_panoramic()
    test_openvino_letterbox_and_ovdict_parsing()
    test_stationary_persistence_anchor_and_slow_drift()
    test_trimesh_ground_raycaster()
    test_kalman_tracker_and_multicam_fusion()
    test_sqlite_wal_repository()
    test_fastapi_rest_and_websocket()
    test_multicam_portico_raycast_openvino_and_overlap_fusion()
    test_multicam_ingresso_180_equirectangular_raycast_and_3cam_fusion()
    test_multicam_stradina_180_equirectangular_4cam_openvino_and_overlap()
    test_multicam_anti_cloning_cardinality_and_miscalibration_fusion()
    print("\nALL SPATIAL SERVER PIPELINE CHECKS PASSED!")

