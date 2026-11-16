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
    test_trimesh_ground_raycaster()
    test_kalman_tracker_and_multicam_fusion()
    test_sqlite_wal_repository()
    test_fastapi_rest_and_websocket()
    print("\nALL SPATIAL SERVER PIPELINE CHECKS PASSED!")

