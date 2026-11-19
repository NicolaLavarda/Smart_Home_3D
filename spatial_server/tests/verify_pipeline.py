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


if __name__ == "__main__":
    test_optics_pinhole_and_panoramic()
    test_openvino_letterbox_and_ovdict_parsing()
    test_stationary_persistence_anchor_and_slow_drift()
    test_trimesh_ground_raycaster()
    test_kalman_tracker_and_multicam_fusion()
    test_sqlite_wal_repository()
    test_fastapi_rest_and_websocket()
    print("\nALL SPATIAL SERVER PIPELINE CHECKS PASSED!")

