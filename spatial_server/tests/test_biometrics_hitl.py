from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi.testclient import TestClient

from spatial_server.biometrics import BiometricCropStore, FaceGalleryIndex, FaceQualityMetrics
from spatial_server.config import REPO_ROOT, SpatialServerConfig
from spatial_server.domain.models import SpatialPoint3D, TrackedEntity3D
from spatial_server.main import create_app
from spatial_server.security import HAUserPrincipal


def _make_cfg(tmp_dir: Path, **overrides: Any) -> SpatialServerConfig:
    defaults: dict[str, Any] = dict(
        host="127.0.0.1",
        port=8765,
        manifest_path=REPO_ROOT / "public" / "models" / "scene_manifest.json",
        glb_path=REPO_ROOT / "public" / "models" / "house_optimized.glb",
        sqlite_db_path=tmp_dir / "spatial_tracks.db",
        calibration_override_path=tmp_dir / "camera_calibrations.json",
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
        db_retention_days=30,
        face_webhook_url="",
        auth_required=False,
        biometrics_enabled=False,
        biometrics_data_dir=tmp_dir / "biometrics",
        biometrics_plates_whitelist_file=tmp_dir / "biometrics" / "plates_whitelist.json",
    )
    defaults.update(overrides)
    return SpatialServerConfig(**defaults)


def _sample_bgr() -> np.ndarray:
    img = np.full((160, 200, 3), 110, dtype=np.uint8)
    cv2.circle(img, (100, 75), 32, (220, 200, 180), -1)
    return img


class _StubFaceRecognizer:
    def __init__(self, vec: np.ndarray) -> None:
        self._vec = vec.astype(np.float32)

    def is_ready(self) -> bool:
        return True

    def extract_face_embedding(
        self,
        image_bgr: np.ndarray,
        *,
        bypass_quality_gate: bool = False,
    ) -> tuple[np.ndarray, FaceQualityMetrics, np.ndarray]:
        metrics = FaceQualityMetrics(det_score=0.92, face_width_px=72.0, blur_laplacian=95.0, yaw_ratio=0.1, passed=True)
        return self._vec, metrics, image_bgr


def test_hitl_face_assign_enrolls_crop_updates_gallery_db_and_backfills_history(tmp_path: Path) -> None:
    bio_dir = tmp_path / "biometrics"
    crop_store = BiometricCropStore(bio_dir)
    ts = time.time()
    crop_id, crop_rel = crop_store.save_best_crop("1700001000_21_face_2", _sample_bgr(), timestamp=ts)

    cfg = _make_cfg(tmp_path, biometrics_data_dir=bio_dir)
    app = create_app(cfg)
    svc = app.state.pipeline

    unit_vec = np.zeros(512, dtype=np.float32)
    unit_vec[0] = 1.0
    svc.get_face_recognizer = lambda: _StubFaceRecognizer(unit_vec)  # type: ignore[method-assign]

    try:
        svc.repository.append_batch(
            [
                TrackedEntity3D(
                    track_id=21,
                    class_label="person",
                    confidence=0.91,
                    state=SpatialPoint3D(x=-5.0, y=0.0, z=4.5, camera_sources=["Cam_Carraio"]),
                    last_seen=ts - 3.0,
                )
            ]
        )
        ev_id = svc.repository.record_biometric_event(
            {
                "track_id": 21,
                "modality": "face",
                "camera_id": "Cam_Carraio",
                "timestamp": ts,
                "biometric_locked": False,
                "biometric_status": "unknown",
                "attempts_count": 3,
                "quality_score": 0.78,
                "best_crop_id": crop_id,
                "best_crop_relpath": crop_rel,
            }
        )

        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/biometrics/events/{ev_id}/assign",
                json={"identity": "Nicola", "enroll_crop": True},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["enrolled_sample"] is True
            assert data["backfilled_rows"] == 1
            assert data["event"]["identity"] == "Nicola"
            assert data["event"]["biometric_locked"] is True
            assert data["event"]["biometric_status"] == "locked"
            assert data["event"]["reviewed_by"]

            # Gallery .npz saved on disk & SQLite face_embeddings populated
            gal_file = bio_dir / "face_gallery.npz"
            assert gal_file.is_file()
            reloaded = FaceGalleryIndex(gal_file)
            match = reloaded.match(unit_vec)
            assert match.passed is True and match.identity == "Nicola"

            emb_count = svc.repository._conn.execute(
                "SELECT COUNT(*) FROM face_embeddings WHERE person_name = 'Nicola';"
            ).fetchone()[0]
            assert emb_count == 1

            # track_history backfilled & filterable
            tr_rows = client.get(f"/api/v1/tracks?t_start={ts - 20}&t_end={ts + 20}&identity=Nicola").json()["detections"]
            assert len(tr_rows) == 1
            assert tr_rows[0]["identity"] == "Nicola"
            assert tr_rows[0]["biometric_locked"] is True

            # Bad empty identity rejected
            bad = client.post(f"/api/v1/biometrics/events/{ev_id}/assign", json={"identity": "   "})
            assert bad.status_code == 400
    finally:
        svc.repository.close()


def test_hitl_face_assign_graceful_when_recognizer_inactive(tmp_path: Path) -> None:
    bio_dir = tmp_path / "biometrics"
    crop_store = BiometricCropStore(bio_dir)
    ts = time.time()
    crop_id, crop_rel = crop_store.save_best_crop("1700002000_31_face_1", _sample_bgr(), timestamp=ts)

    cfg = _make_cfg(tmp_path, biometrics_enabled=False, biometrics_data_dir=bio_dir)
    app = create_app(cfg)
    svc = app.state.pipeline
    try:
        svc.repository.append_batch(
            [
                TrackedEntity3D(
                    track_id=31,
                    class_label="person",
                    confidence=0.90,
                    state=SpatialPoint3D(x=-4.0, y=0.0, z=5.0, camera_sources=["Cam_Portico"]),
                    last_seen=ts - 2.0,
                )
            ]
        )
        ev_id = svc.repository.record_biometric_event(
            {
                "track_id": 31,
                "modality": "face",
                "camera_id": "Cam_Portico",
                "timestamp": ts,
                "biometric_locked": False,
                "biometric_status": "unknown",
                "best_crop_id": crop_id,
                "best_crop_relpath": crop_rel,
            }
        )
        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/biometrics/events/{ev_id}/assign",
                json={"identity": "Giulia", "enroll_crop": True},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["enrolled_sample"] is False
            assert data["enroll_note"]
            assert data["event"]["identity"] == "Giulia"
            assert data["event"]["biometric_locked"] is True
            assert data["backfilled_rows"] == 1
    finally:
        svc.repository.close()


def test_hitl_alpr_assign_and_whitelist_crud_sync(tmp_path: Path) -> None:
    bio_dir = tmp_path / "biometrics"
    wl_path = bio_dir / "plates_whitelist.json"
    cfg = _make_cfg(tmp_path, biometrics_data_dir=bio_dir, biometrics_plates_whitelist_file=wl_path)
    app = create_app(cfg)
    svc = app.state.pipeline
    ts = time.time()

    try:
        svc.repository.append_batch(
            [
                TrackedEntity3D(
                    track_id=44,
                    class_label="car",
                    confidence=0.94,
                    state=SpatialPoint3D(x=-10.0, y=0.0, z=9.0, camera_sources=["Cam_Carraio"]),
                    last_seen=ts - 1.0,
                )
            ]
        )
        ev_id = svc.repository.record_biometric_event(
            {
                "track_id": 44,
                "modality": "alpr",
                "camera_id": "Cam_Carraio",
                "timestamp": ts,
                "plate": None,
                "plate_raw": "ab123cd",
                "biometric_locked": False,
                "biometric_status": "unknown",
            }
        )

        with TestClient(app) as client:
            # Assign & add to whitelist
            r_assign = client.post(
                f"/api/v1/biometrics/events/{ev_id}/assign",
                json={
                    "plate": "ab-123-cd",
                    "add_to_whitelist": True,
                    "owner_name": "Auto Nicola",
                    "vehicle_label": "Audi A3",
                },
            )
            assert r_assign.status_code == 200
            d_assign = r_assign.json()
            assert d_assign["event"]["plate"] == "AB123CD"
            assert d_assign["event"]["plate_whitelisted"] is True
            assert d_assign["event"]["plate_owner"] == "Auto Nicola"
            assert d_assign["backfilled_rows"] == 1

            # JSON whitelist file and DB are synced
            assert wl_path.is_file()
            wl_json = json.loads(wl_path.read_text(encoding="utf-8"))
            assert any(p["plate"] == "AB123CD" and p["owner_name"] == "Auto Nicola" for p in wl_json["plates"])

            # Direct PUT & DELETE whitelist
            r_put = client.put(
                "/api/v1/biometrics/plates",
                json={"plate": "fg 789 kl", "owner_name": "Auto Giulia", "vehicle_label": "Yaris"},
            )
            assert r_put.status_code == 200
            assert r_put.json()["count"] == 2
            assert r_put.json()["entry"]["plate"] == "FG789KL"

            r_bad_put = client.put("/api/v1/biometrics/plates", json={"plate": "12", "owner_name": "X"})
            assert r_bad_put.status_code == 400

            r_del = client.delete("/api/v1/biometrics/plates/FG789KL")
            assert r_del.status_code == 200
            assert r_del.json()["deleted"] == "FG789KL"
            assert r_del.json()["count"] == 1

            assert client.delete("/api/v1/biometrics/plates/ZZZZ999").status_code == 404
    finally:
        svc.repository.close()


def test_admin_identities_reload_delete_and_crops_prune(tmp_path: Path) -> None:
    bio_dir = tmp_path / "biometrics"
    gal_path = bio_dir / "face_gallery.npz"
    crop_store = BiometricCropStore(bio_dir)

    cfg = _make_cfg(tmp_path, biometrics_data_dir=bio_dir, biometrics_crop_retention_days=7)
    app = create_app(cfg)
    svc = app.state.pipeline

    try:
        # Write gallery externally and add DB sample
        vec = np.ones(512, dtype=np.float32)
        vec /= np.linalg.norm(vec)
        ext_gallery = FaceGalleryIndex(gal_path)
        ext_gallery.add_embedding("Marco", vec, quality=0.9, persist=True)
        svc.repository.add_face_embedding("Marco", "w600k_mbf.onnx", vec.tobytes(), quality_score=0.9, source="enroll")

        # Expired crop + event
        old_ts = time.time() - 20 * 86400
        old_id, old_rel = crop_store.save_best_crop("1000_88_face_1", _sample_bgr(), timestamp=old_ts)
        old_path = crop_store.resolve_crop_path(old_id, known_relpath=old_rel)
        assert old_path is not None
        os.utime(old_path, (old_ts, old_ts))
        svc.repository.record_biometric_event(
            {
                "track_id": 88,
                "modality": "face",
                "camera_id": "Cam_Carraio",
                "timestamp": old_ts,
                "biometric_locked": False,
                "biometric_status": "unknown",
                "best_crop_id": old_id,
                "best_crop_relpath": old_rel,
            }
        )

        with TestClient(app) as client:
            r_rel = client.post("/api/v1/biometrics/identities/reload")
            assert r_rel.status_code == 200
            assert any(item["name"] == "Marco" and item["enrolled"] is True for item in r_rel.json()["identities"])

            r_del = client.delete("/api/v1/biometrics/identities/marco")
            assert r_del.status_code == 200
            assert r_del.json()["removed_from_gallery"] is True
            assert r_del.json()["removed_db_embeddings"] == 1

            assert client.delete("/api/v1/biometrics/identities/NonEsiste").status_code == 404

            r_prune = client.post("/api/v1/biometrics/crops/prune")
            assert r_prune.status_code == 200
            d_prune = r_prune.json()
            assert d_prune["deleted_events"] == 1
            assert d_prune["deleted_files"] >= 1
            assert not old_path.exists()
    finally:
        svc.repository.close()
