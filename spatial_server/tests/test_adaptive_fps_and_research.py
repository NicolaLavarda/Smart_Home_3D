from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import time
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from spatial_server.config import SpatialServerConfig
from spatial_server.domain.models import BoundingBox2D, DetectionEvent, SpatialPoint3D, TrackedEntity3D
from spatial_server.events import EventSnapshotStore, SceneEventManager, SceneEventRecord, SceneSubjectRecord
from spatial_server.ingestion import AdaptiveFpsScheduler
from spatial_server.main import create_app
from spatial_server.persistence.repository import SQLiteWALTrackRepository
from spatial_server.research import ProductionResearchCollector, generate_research_summary_markdown
from tools.export_research_bundle import export_research_bundle


def _make_car_track(tid: int, x: float, z: float, vx: float = 0.0, vz: float = 0.0, ts: float = 1000.0) -> TrackedEntity3D:
    return TrackedEntity3D(
        track_id=tid,
        class_label="car",
        state=SpatialPoint3D(x=x, y=0.0, z=z, vx=vx, vy=0.0, vz=vz, camera_sources=["Cam_Carraio"]),
        last_seen=ts,
    )


def test_adaptive_fps_scheduler_priorities_and_hysteresis() -> None:
    sched = AdaptiveFpsScheduler(
        ["Cam_Carraio", "Cam_Portico", "Cam_Ingresso", "Cam_Stradina"],
        total_budget_fps=7.0,
        idle_fps=1.2,
        min_idle_fps=1.0,
        max_person_fps=5.0,
        max_vehicle_fps=3.5,
        boost_hold_s=5.0,
        enabled=True,
    )

    # All idle -> ~1.2 fps per camera (saving CPU/iGPU vs fixed 1.75)
    idle_alloc = sched.update_camera_activity(set(), set(), now_ts=100.0)
    assert all(fps == pytest.approx(1.2, abs=0.05) for fps in idle_alloc.values())
    assert sum(idle_alloc.values()) == pytest.approx(4.8, abs=0.1)

    # Single person on Cam_Ingresso -> boosts Cam_Ingresso well above idle (~4.0 fps), idle cams stay >= 1.0
    p_alloc = sched.update_camera_activity({"Cam_Ingresso"}, set(), now_ts=101.0)
    assert p_alloc["Cam_Ingresso"] == pytest.approx(4.0, abs=0.1)
    assert p_alloc["Cam_Carraio"] == pytest.approx(1.0, abs=0.05)
    assert sum(p_alloc.values()) <= 7.05

    # Person on Cam_Ingresso + active vehicle on Cam_Carraio -> person strictly > vehicle > idle
    pv_alloc = sched.update_camera_activity({"Cam_Ingresso"}, {"Cam_Carraio"}, now_ts=102.0)
    assert pv_alloc["Cam_Ingresso"] > pv_alloc["Cam_Carraio"] > pv_alloc["Cam_Portico"]
    assert pv_alloc["Cam_Portico"] >= 1.0
    assert sum(pv_alloc.values()) <= 7.05

    # Two people -> vehicle dropped when empty, both people share budget cleanly
    two_p = sched.update_camera_activity({"Cam_Ingresso", "Cam_Portico"}, set(), now_ts=108.0)
    assert two_p["Cam_Ingresso"] == pytest.approx(2.5, abs=0.15)
    assert two_p["Cam_Portico"] == pytest.approx(2.5, abs=0.15)
    assert two_p["Cam_Carraio"] == pytest.approx(1.0, abs=0.05)

    # Hysteresis: within boost_hold_s=5s stays boosted, after 5s returns cleanly to 1.2 fps
    hold_alloc = sched.update_camera_activity(set(), set(), now_ts=111.0)
    assert hold_alloc["Cam_Ingresso"] > 1.5
    cooled_alloc = sched.refresh(now_ts=115.0)
    assert all(fps == pytest.approx(1.2, abs=0.05) for fps in cooled_alloc.values())


def test_parked_vehicle_visual_slot_survives_long_gap_and_jitter(tmp_path: Path) -> None:
    """Visual 2D IoU + thumbnail NCC keeps parked car quiet across >15min IR outage and 0.9m 3D jitter, waking only on true exit."""
    frame_parked = np.full((360, 640, 3), 25, dtype=np.uint8)
    # Textured car silhouette inside bbox (0.35, 0.25) -> (0.85, 0.85)
    for x in range(224, 544, 16):
        color = (210, 210, 210) if ((x // 16) % 2 == 0) else (60, 60, 60)
        frame_parked[90:306, x : x + 16] = color

    frame_state = {"img": frame_parked, "ts": 1000.0}

    def _get_sub(_cam_id: str):
        return frame_state["img"], frame_state["ts"]

    async def _run() -> None:
        repo = SQLiteWALTrackRepository(tmp_path / "slots.db")
        store = EventSnapshotStore(tmp_path)
        mgr = SceneEventManager(
            repository=repo,
            snapshot_store=store,
            inertia_s=8.0,
            stationary_vehicle_s=20.0,
            substream_frame_getter=_get_sub,
        )

        det = DetectionEvent(
            camera_id="Cam_Carraio",
            timestamp=1000.0,
            class_label="car",
            confidence=0.9,
            bbox=BoundingBox2D(x_min=0.35, y_min=0.25, x_max=0.85, y_max=0.85),
        )
        tr1 = _make_car_track(10, 4.0, 8.0, ts=1000.0)
        ev_arrive = await mgr.on_detection_batch([det], [tr1], {0: 10}, 1000.0)
        assert ev_arrive is not None

        # Car stays parked -> after 25s registers visual slot & becomes background
        frame_state["ts"] = 1025.0
        await mgr.on_detection_batch(
            [det.model_copy(update={"timestamp": 1025.0})],
            [tr1.model_copy(update={"last_seen": 1025.0})],
            {0: 10},
            1025.0,
        )
        assert mgr.get_parked_slots_count() == 1
        assert 10 in mgr.get_background_parked_track_ids()
        assert mgr.get_active_event() is None  # closed once inertia elapsed with only parked car

        # Arrival episode is already closed in DB
        closed_row = repo.get_scene_event(ev_arrive.event_id)
        assert closed_row is not None and closed_row["status"] == "closed"

        # Simulate periodic visual check during 15-minute IR detection dropout
        frame_state["ts"] = 1950.0
        await mgr.tick(1950.0)
        assert mgr.get_parked_slots_count() == 1

        # After 15 minutes (925s > 180s anchor window!), a NEW track_id appears at the same spot with 0.9m 3D jitter
        frame_state["ts"] = 1960.0
        tr2_jitter = _make_car_track(99, 4.85, 8.15, vx=0.05, vz=0.05, ts=1960.0)
        det_same_spot = det.model_copy(
            update={"timestamp": 1960.0, "bbox": BoundingBox2D(x_min=0.36, y_min=0.26, x_max=0.84, y_max=0.85)}
        )
        ev_spurious = await mgr.on_detection_batch([det_same_spot], [tr2_jitter], {0: 99}, 1960.0)
        assert ev_spurious is None
        assert 99 in mgr.get_background_parked_track_ids()

        # Now the car ACTUALLY leaves: bbox shifts away & 3D position moves > 1.5m -> opens departure episode!
        frame_state["img"] = np.full((360, 640, 3), 25, dtype=np.uint8)
        frame_state["ts"] = 1980.0
        tr_depart = _make_car_track(99, 7.5, 11.0, vx=1.5, vz=1.2, ts=1980.0)
        det_depart = det.model_copy(
            update={"timestamp": 1980.0, "bbox": BoundingBox2D(x_min=0.02, y_min=0.30, x_max=0.30, y_max=0.70)}
        )
        ev_depart = await mgr.on_detection_batch([det_depart], [tr_depart], {0: 99}, 1980.0)
        assert ev_depart is not None
        assert mgr.get_parked_slots_count() == 0

        await mgr.close()
        repo.close()

    asyncio.run(_run())


def test_research_collector_export_and_dev_mode_defaults(tmp_path: Path) -> None:
    # Default auto behavior: dev_mode=True -> disabled; dev_mode=False -> enabled
    dev_cfg = replace(SpatialServerConfig.from_env(), dev_mode=True, research_telemetry_enabled=None)
    assert (not dev_cfg.dev_mode if dev_cfg.research_telemetry_enabled is None else dev_cfg.research_telemetry_enabled) is False

    prod_cfg = replace(
        SpatialServerConfig.from_env(),
        dev_mode=False,
        auth_required=False,
        biometrics_enabled=False,
        default_ingestion_mode="synthetic",
        sqlite_db_path=tmp_path / "prod.db",
        data_dir=tmp_path,
        research_telemetry_enabled=None,
    )
    app = create_app(prod_cfg)
    with TestClient(app) as client:
        st_res = client.get("/api/v1/research/status")
        assert st_res.status_code == 200
        body = st_res.json()
        assert body["research_telemetry"]["enabled"] is True
        assert body["fps_scheduler"]["enabled"] is True

    # Direct collector test: JSONL logs, rate-limited crops, anomalies, prune & ZIP export
    tel_dir = tmp_path / "telemetry_unit"
    collector = ProductionResearchCollector(
        tel_dir,
        max_disk_mb=20.0,
        retention_days=7,
        save_crops=True,
        crop_interval_s=4.0,
        max_crops_per_track=2,
    )
    collector.start({"cameras": ["Cam_Carraio", "Cam_Ingresso"]})

    frame = np.full((360, 640, 3), 100, dtype=np.uint8)
    ts_base = time.time()
    for offset in (0.0, 1.0, 5.0, 10.0):
        collector.maybe_record_crop_sample(
            track_id=7,
            camera_id="Cam_Ingresso",
            class_label="person",
            bbox_norm=(0.3, 0.2, 0.5, 0.8),
            frame_bgr=frame,
            world_xyz=(2.0, 0.0, 3.0),
            confidence=0.88,
            is_night_ir=True,
            mean_luma=55.0,
            mean_saturation=4.0,
            timestamp=ts_base + offset,
        )

    collector.maybe_record_health(
        fps_snapshot={"enabled": True, "cameras": {"Cam_Ingresso": {"tier": "person", "target_fps": 4.0}}},
        camera_stats=[{"camera_id": "Cam_Ingresso", "last_infer_ms": 42.0, "infer_ms_ema": 40.0, "reconnect_count": 0}],
        active_tracks_count=1,
        parked_slots_count=1,
        interval_s=0.0,
        now_ts=ts_base,
    )
    collector.record_track_lifecycle([{"event": "reid_revived", "track_id": 7, "class_label": "person", "timestamp": ts_base}])
    collector.record_scene_event(
        SceneEventRecord(
            event_id="evt_test_long",
            status="closed",
            started_at=ts_base,
            ended_at=ts_base + 210.0,
            duration_s=210.0,
            importance="silent_alert",
            best_camera_id="Cam_Ingresso",
            best_frame_score=112.0,
            subjects=[SceneSubjectRecord(track_id=7, class_label="person")],
        ),
        lifecycle="closed",
    )
    collector.stop(timeout_s=2.0)

    status = collector.get_status()
    assert status["crops_saved"] == 2  # max_crops_per_track=2 & interval=4s enforced
    assert status["anomalies_recorded"] >= 1  # episode_duration_gt_180s flagged
    assert (tel_dir / "session_meta.json").is_file()

    summary = generate_research_summary_markdown(tel_dir)
    assert "Report Telemetria Produzione" in summary
    assert "episode_duration_gt_180s" in summary

    zip_path = export_research_bundle(tel_dir)
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "REPORT_SUMMARY.md" in names
        assert "session_meta.json" in names
        assert any(n.endswith("anomalies.jsonl") for n in names)
