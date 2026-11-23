from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np
from fastapi.testclient import TestClient

from spatial_server.biometrics import (
    BiometricCropStore,
    FaceGalleryIndex,
    TrackBiometricUpdate,
)
from spatial_server.config import REPO_ROOT, SpatialServerConfig
from spatial_server.domain.models import SpatialPoint3D, TrackedEntity3D
from spatial_server.main import build_pipeline_service, create_app
from spatial_server.persistence import SQLiteWALTrackRepository
from spatial_server.tracking import TrackObservation3D


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
    )
    defaults.update(overrides)
    return SpatialServerConfig(**defaults)


def _sample_jpeg_bgr() -> np.ndarray:
    img = np.full((180, 240, 3), 90, dtype=np.uint8)
    cv2.putText(img, "SH3D", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (230, 230, 230), 2)
    return img


def test_legacy_schema_idempotent_migration_and_wal_preservation(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE track_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL,
            timestamp REAL NOT NULL,
            class_label TEXT NOT NULL,
            identity TEXT,
            identity_confidence REAL DEFAULT 0.0,
            confidence REAL DEFAULT 0.9,
            x REAL NOT NULL,
            y REAL NOT NULL,
            z REAL NOT NULL,
            vx REAL DEFAULT 0.0,
            vy REAL DEFAULT 0.0,
            vz REAL DEFAULT 0.0,
            camera_sources TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE identities (
            name TEXT PRIMARY KEY,
            embedding_blob BLOB,
            updated_at REAL NOT NULL,
            notes TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO track_history (
            track_id, timestamp, class_label, identity, identity_confidence,
            confidence, x, y, z, vx, vy, vz, camera_sources
        ) VALUES (12, 1000.0, 'person', 'Nicola', 0.91, 0.95, -8.0, 0.0, 4.0, 0.1, 0.0, 0.2, '["Cam_Carraio"]');
        """
    )
    conn.execute(
        """
        INSERT INTO track_history (
            track_id, timestamp, class_label, identity, identity_confidence,
            confidence, x, y, z, vx, vy, vz, camera_sources
        ) VALUES (15, 1005.0, 'car', NULL, 0.0, 0.89, -10.0, 0.0, 8.0, 0.0, 0.0, -1.2, '["Cam_Carraio"]');
        """
    )
    conn.commit()
    conn.close()

    # 1st migration open
    repo1 = SQLiteWALTrackRepository(db_path)
    try:
        assert repo1.get_journal_mode() == "wal"
        cols = {
            str(r["name"])
            for r in repo1._conn.execute("PRAGMA table_info(track_history);").fetchall()
        }
        assert {
            "plate",
            "plate_confidence",
            "plate_whitelisted",
            "plate_owner",
            "biometric_locked",
            "best_crop_id",
        }.issubset(cols)
        tables = {
            str(r[0])
            for r in repo1._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        }
        assert {"biometric_events", "face_embeddings", "plate_whitelist"}.issubset(tables)

        rows = repo1.query_time_range(990.0, 1010.0)
        assert len(rows) == 2
        assert rows[0]["identity"] == "Nicola"
        assert rows[0]["plate"] is None
        assert rows[0]["plate_whitelisted"] is None
        assert rows[0]["biometric_locked"] is False
    finally:
        repo1.close()

    # 2nd migration open (strictly idempotent)
    repo2 = SQLiteWALTrackRepository(db_path)
    try:
        rows2 = repo2.query_time_range(990.0, 1010.0)
        assert len(rows2) == 2
        assert rows2[1]["track_id"] == 15
    finally:
        repo2.close()


def test_max_track_id_seed_and_kalman_restart(tmp_path: Path) -> None:
    cfg = _make_cfg(tmp_path)
    repo = SQLiteWALTrackRepository(cfg.sqlite_db_path)
    try:
        repo.append_batch(
            [
                TrackedEntity3D(
                    track_id=42,
                    class_label="person",
                    state=SpatialPoint3D(x=-5.0, y=0.0, z=5.0, camera_sources=["Cam_Carraio"]),
                    last_seen=1000.0,
                )
            ]
        )
        repo.record_biometric_event(
            {
                "track_id": 58,
                "modality": "face",
                "camera_id": "Cam_Carraio",
                "timestamp": 1005.0,
                "identity": "Nicola",
                "identity_confidence": 0.85,
                "biometric_locked": True,
                "biometric_status": "locked",
            }
        )
        assert repo.get_max_track_id() == 58
    finally:
        repo.close()

    service = build_pipeline_service(cfg)
    try:
        tracks = service.tracker.update(
            [TrackObservation3D("Cam_Carraio", 1010.0, "person", (-6.0, 0.0, 6.0), 0.9)],
            now_ts=1010.0,
        )
        assert len(tracks) == 1
        assert tracks[0].track_id == 59
    finally:
        service.repository.close()


def test_backfill_track_biometrics_and_query_filters(tmp_path: Path) -> None:
    repo = SQLiteWALTrackRepository(tmp_path / "filters.db")
    try:
        repo.append_batch(
            [
                TrackedEntity3D(
                    track_id=7,
                    class_label="person",
                    state=SpatialPoint3D(x=-4.0, y=0.0, z=6.0, camera_sources=["Cam_Ingresso"]),
                    last_seen=1000.0,
                ),
                TrackedEntity3D(
                    track_id=7,
                    class_label="person",
                    state=SpatialPoint3D(x=-4.5, y=0.0, z=6.2, camera_sources=["Cam_Ingresso"]),
                    last_seen=1002.0,
                ),
                TrackedEntity3D(
                    track_id=8,
                    class_label="car",
                    state=SpatialPoint3D(x=-10.0, y=0.0, z=10.0, camera_sources=["Cam_Carraio"]),
                    last_seen=1001.0,
                ),
                TrackedEntity3D(
                    track_id=8,
                    class_label="car",
                    state=SpatialPoint3D(x=-10.2, y=0.0, z=8.0, camera_sources=["Cam_Carraio"]),
                    last_seen=1003.0,
                ),
                TrackedEntity3D(
                    track_id=9,
                    class_label="person",
                    state=SpatialPoint3D(x=-1.0, y=0.0, z=2.0, camera_sources=["Cam_Portico"]),
                    last_seen=1004.0,
                ),
            ]
        )

        updated_person = repo.backfill_track_biometrics(
            7,
            min_timestamp=999.0,
            identity="Giulia",
            identity_confidence=0.88,
            biometric_locked=True,
            best_crop_id="1002_7_face_2",
        )
        assert updated_person == 2

        updated_car = repo.backfill_track_biometrics(
            8,
            min_timestamp=999.0,
            identity="Auto Famiglia",
            identity_confidence=0.91,
            plate="FG456HJ",
            plate_confidence=0.93,
            plate_whitelisted=True,
            plate_owner="Auto Famiglia",
            biometric_locked=True,
            best_crop_id="1003_8_alpr_2",
        )
        assert updated_car == 2

        by_id = repo.query_time_range(990.0, 1010.0, identity="giulia")
        assert len(by_id) == 2 and all(r["track_id"] == 7 and r["biometric_locked"] is True for r in by_id)

        by_plate = repo.query_time_range(990.0, 1010.0, plate="fg45")
        assert len(by_plate) == 2
        assert all(
            r["track_id"] == 8 and r["plate"] == "FG456HJ" and r["plate_whitelisted"] is True
            for r in by_plate
        )

        unknowns = repo.query_time_range(990.0, 1010.0, unknown_only=True)
        assert len(unknowns) == 1 and unknowns[0]["track_id"] == 9
    finally:
        repo.close()


def test_biometric_event_dedup_and_crop_pruning(tmp_path: Path) -> None:
    repo = SQLiteWALTrackRepository(tmp_path / "events.db")
    crop_store = BiometricCropStore(tmp_path / "biometrics")
    try:
        old_ts = time.time() - 20 * 86400
        old_id, old_rel = crop_store.save_best_crop("1000_5_face_1", _sample_jpeg_bgr(), timestamp=old_ts)
        old_path = crop_store.resolve_crop_path(old_id, known_relpath=old_rel)
        assert old_path is not None and old_path.is_file()
        os.utime(old_path, (old_ts, old_ts))

        new_ts = time.time()
        new_id, new_rel = crop_store.save_best_crop("2000_10_face_2", _sample_jpeg_bgr(), timestamp=new_ts)
        assert crop_store.resolve_crop_path(new_id, known_relpath=new_rel) is not None

        # Visit deduplication: unknown -> locked updates the SAME event id
        ev1_id = repo.record_biometric_event(
            {
                "track_id": 10,
                "modality": "face",
                "camera_id": "Cam_Carraio",
                "timestamp": new_ts - 1.0,
                "biometric_locked": False,
                "biometric_status": "unknown",
                "attempts_count": 3,
                "quality_score": 0.45,
                "best_crop_id": new_id,
                "best_crop_relpath": new_rel,
            }
        )
        ev2_id = repo.record_biometric_event(
            {
                "track_id": 10,
                "modality": "face",
                "camera_id": "Cam_Ingresso",
                "timestamp": new_ts,
                "identity": "Nicola",
                "identity_confidence": 0.87,
                "biometric_locked": True,
                "biometric_status": "locked",
                "attempts_count": 4,
                "quality_score": 0.88,
            }
        )
        assert ev2_id == ev1_id

        # Must never downgrade an already-locked event back to unknown
        ev3_id = repo.record_biometric_event(
            {
                "track_id": 10,
                "modality": "face",
                "camera_id": "Cam_Ingresso",
                "timestamp": new_ts + 1.0,
                "biometric_locked": False,
                "biometric_status": "unknown",
            }
        )
        assert ev3_id == ev1_id
        ev = repo.get_biometric_event(ev1_id)
        assert ev is not None
        assert ev["identity"] == "Nicola"
        assert ev["biometric_locked"] is True
        assert ev["best_crop_id"] == new_id
        assert repo.get_crop_relpath(new_id) == new_rel

        # Expired event & crop prune
        repo.record_biometric_event(
            {
                "track_id": 5,
                "modality": "face",
                "camera_id": "Cam_Carraio",
                "timestamp": old_ts,
                "biometric_locked": False,
                "biometric_status": "unknown",
                "best_crop_id": old_id,
                "best_crop_relpath": old_rel,
            }
        )
        deleted_cnt, expired_rels = repo.prune_biometric_events_older_than(time.time() - 14 * 86400)
        assert deleted_cnt == 1
        assert old_rel in expired_rels

        removed_files = crop_store.prune(retention_days=14, max_disk_mb=250.0, extra_relpaths=expired_rels)
        assert removed_files >= 1
        assert crop_store.resolve_crop_path(old_id, known_relpath=old_rel) is None
        assert crop_store.resolve_crop_path(new_id, known_relpath=new_rel) is not None
    finally:
        repo.close()


def test_whitelist_sync_backfill_race_and_read_endpoints(tmp_path: Path) -> None:
    bio_dir = tmp_path / "biometrics"
    bio_dir.mkdir(parents=True, exist_ok=True)
    wl_path = bio_dir / "plates_whitelist.json"
    wl_path.write_text(
        json.dumps(
            {
                "plates": [
                    {
                        "plate": "AB123CD",
                        "owner_name": "Auto Nicola",
                        "vehicle_label": "Audi A3",
                        "notes": "Famiglia",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    gallery = FaceGalleryIndex(bio_dir / "face_gallery.npz")
    vec = np.ones(512, dtype=np.float32)
    vec = vec / np.linalg.norm(vec)
    gallery.add_embedding("Nicola", vec, quality=0.9, persist=True)

    cfg = _make_cfg(
        tmp_path,
        biometrics_enabled=True,
        biometrics_data_dir=bio_dir,
        biometrics_plates_whitelist_file=wl_path,
    )
    app = create_app(cfg)
    svc = app.state.pipeline

    try:
        # 1. Whitelist synced from JSON into SQLite on startup
        with TestClient(app) as client:
            plates_resp = client.get("/api/v1/biometrics/plates")
            assert plates_resp.status_code == 200
            plates_data = plates_resp.json()
            assert plates_data["count"] == 1
            assert plates_data["plates"][0]["plate"] == "AB123CD"
            assert plates_data["plates"][0]["owner_name"] == "Auto Nicola"

            id_resp = client.get("/api/v1/biometrics/identities")
            assert id_resp.status_code == 200
            assert any(i["name"] == "Nicola" and i["enrolled"] is True for i in id_resp.json()["identities"])

        # 2. Simulate flushed track row + buffered _pending_persist row -> async biometric lock backfills BOTH!
        base_ts = time.time()
        crop_store = svc.get_biometric_crop_store()
        assert crop_store is not None
        crop_id, crop_rel = crop_store.save_best_crop("9000_77_face_2", _sample_jpeg_bgr(), timestamp=base_ts)

        svc.repository.append_batch(
            [
                TrackedEntity3D(
                    track_id=77,
                    class_label="person",
                    confidence=0.9,
                    state=SpatialPoint3D(x=-5.0, y=0.0, z=6.0, camera_sources=["Cam_Carraio"]),
                    last_seen=base_ts - 2.0,
                )
            ]
        )
        svc._pending_persist.append(
            TrackedEntity3D(
                track_id=77,
                class_label="person",
                confidence=0.92,
                state=SpatialPoint3D(x=-4.8, y=0.0, z=5.9, camera_sources=["Cam_Carraio"]),
                last_seen=base_ts - 0.5,
            )
        )
        # Seed track 77 directly into tracker
        svc.tracker.update(
            [TrackObservation3D("Cam_Carraio", base_ts, "person", (-4.6, 0.0, 5.8), 0.93)],
            now_ts=base_ts,
        )
        real_tid = svc.tracker.get_active_tracks()[0].track_id
        # Align seeded DB/pending track_id to real_tid
        svc.repository._conn.execute("UPDATE track_history SET track_id = ? WHERE track_id = 77;", (real_tid,))
        svc.repository._conn.commit()
        svc._pending_persist[0] = svc._pending_persist[0].model_copy(update={"track_id": real_tid})

        async def _apply_and_query() -> None:
            await svc._handle_biometric_update(
                TrackBiometricUpdate(
                    track_id=real_tid,
                    modality="face",
                    identity="Nicola",
                    identity_confidence=0.86,
                    biometric_locked=True,
                    biometric_status="locked",
                    attempts_count=2,
                    best_crop_id=crop_id,
                    best_crop_relpath=crop_rel,
                    quality_score=0.89,
                    camera_id="Cam_Carraio",
                    timestamp=base_ts + 0.1,
                )
            )
            await svc.flush_pending_to_db()

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as aclient:
                tr_resp = await aclient.get(
                    f"/api/v1/tracks?t_start={base_ts - 10}&t_end={base_ts + 10}&identity=Nicola"
                )
                assert tr_resp.status_code == 200
                tr_rows = tr_resp.json()["detections"]
                assert len(tr_rows) >= 2
                assert all(
                    r["identity"] == "Nicola"
                    and r["biometric_locked"] is True
                    and r["best_crop_id"] == crop_id
                    for r in tr_rows
                )

                ev_resp = await aclient.get(f"/api/v1/biometrics/events?modality=face&track_id={real_tid}")
                assert ev_resp.status_code == 200
                ev_data = ev_resp.json()
                assert ev_data["count"] == 1
                ev_item = ev_data["events"][0]
                assert ev_item["identity"] == "Nicola"
                assert ev_item["crop_url"] == f"/api/v1/biometrics/crops/{crop_id}"
                assert "best_crop_relpath" not in ev_item

                crop_resp = await aclient.get(ev_item["crop_url"])
                assert crop_resp.status_code == 200
                assert crop_resp.headers["content-type"].startswith("image/jpeg")
                assert crop_resp.headers.get("x-content-type-options") == "nosniff"
                assert crop_resp.content.startswith(b"\xff\xd8")

                st_resp = await aclient.get("/api/v1/biometrics/status")
                assert st_resp.status_code == 200
                st_data = st_resp.json()
                assert st_data["gallery_identities_count"] >= 1
                assert st_data["plates_whitelist_count"] == 1
                assert st_data["crop_storage"]["files_count"] >= 1

        asyncio.run(_apply_and_query())
    finally:
        svc.repository.close()
