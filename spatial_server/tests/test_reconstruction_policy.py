from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from spatial_server.config import REPO_ROOT, SpatialServerConfig
from spatial_server.domain.models import (
    BoundingBox2D,
    ClassReconstructionRule,
    DetectionEvent,
    SpatialReconstructionPolicy,
)
from spatial_server.ingestion.openvino_rtsp_source import OpenVINORtspDetectionSource
from spatial_server.main import build_pipeline_service
from spatial_server.tracking import Kalman3DMultiTracker, TrackObservation3D


def _make_policy(
    *,
    person: ClassReconstructionRule | None = None,
    vehicle: ClassReconstructionRule | None = None,
    animal: ClassReconstructionRule | None = None,
    fallback: float = 0.62,
) -> SpatialReconstructionPolicy:
    return SpatialReconstructionPolicy(
        person=person or ClassReconstructionRule(True, 0.78, 0.62, 0.25),
        vehicle=vehicle or ClassReconstructionRule(True, 0.72, 0.62, 0.35),
        animal=animal or ClassReconstructionRule(True, 0.75, 0.62, 0.20),
        fallback_conf_threshold=fallback,
    )


def test_config_from_env_parses_reconstruction_policy_and_fallbacks(monkeypatch) -> None:
    for var in (
        "SPATIAL_RECONSTRUCT_PERSON",
        "SPATIAL_PERSON_STATIONARY_CONF_THRESHOLD",
        "SPATIAL_PERSON_MOVING_CONF_THRESHOLD",
        "SPATIAL_PERSON_MIN_SPEED_MPS",
        "SPATIAL_RECONSTRUCT_VEHICLE",
        "SPATIAL_VEHICLE_STATIONARY_CONF_THRESHOLD",
        "SPATIAL_VEHICLE_MOVING_CONF_THRESHOLD",
        "SPATIAL_VEHICLE_MIN_SPEED_MPS",
        "SPATIAL_RECONSTRUCT_ANIMAL",
        "SPATIAL_ANIMAL_STATIONARY_CONF_THRESHOLD",
        "SPATIAL_ANIMAL_MOVING_CONF_THRESHOLD",
        "SPATIAL_ANIMAL_MIN_SPEED_MPS",
    ):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("OPENVINO_CONF_THRESHOLD", "0.62")
    cfg_default = SpatialServerConfig.from_env()
    pol_default = cfg_default.get_reconstruction_policy()
    assert pol_default.person.enabled is True
    assert pol_default.person.stationary_conf_threshold == pytest.approx(0.62)
    assert pol_default.person.moving_conf_threshold == pytest.approx(0.62)
    assert pol_default.person.min_speed_mps == pytest.approx(0.25)

    monkeypatch.setenv("SPATIAL_RECONSTRUCT_PERSON", "true")
    monkeypatch.setenv("SPATIAL_PERSON_STATIONARY_CONF_THRESHOLD", "0.80")
    monkeypatch.setenv("SPATIAL_PERSON_MOVING_CONF_THRESHOLD", "0.62")
    monkeypatch.setenv("SPATIAL_PERSON_MIN_SPEED_MPS", "0")
    monkeypatch.setenv("SPATIAL_RECONSTRUCT_VEHICLE", "true")
    monkeypatch.setenv("SPATIAL_VEHICLE_STATIONARY_CONF_THRESHOLD", "0.74")
    monkeypatch.setenv("SPATIAL_VEHICLE_MOVING_CONF_THRESHOLD", "0.58")
    monkeypatch.setenv("SPATIAL_VEHICLE_MIN_SPEED_MPS", "0.40")
    monkeypatch.setenv("SPATIAL_RECONSTRUCT_ANIMAL", "false")
    monkeypatch.setenv("SPATIAL_ANIMAL_STATIONARY_CONF_THRESHOLD", "0.85")
    monkeypatch.setenv("SPATIAL_ANIMAL_MOVING_CONF_THRESHOLD", "0.68")
    monkeypatch.setenv("SPATIAL_ANIMAL_MIN_SPEED_MPS", "0.18")

    cfg = SpatialServerConfig.from_env()
    pol = cfg.get_reconstruction_policy()
    assert pol.person == ClassReconstructionRule(True, 0.80, 0.62, 0.0)
    assert pol.vehicle == ClassReconstructionRule(True, 0.74, 0.58, 0.40)
    assert pol.animal == ClassReconstructionRule(False, 0.85, 0.68, 0.18)
    assert pol.rule_for("car") == pol.vehicle
    assert pol.rule_for("truck") == pol.vehicle
    assert pol.rule_for("motorbike") == pol.vehicle
    assert pol.rule_for("dog") == pol.animal
    assert pol.min_detection_conf_floor() == pytest.approx(0.58)


def test_openvino_source_uses_per_class_2d_floor_and_disabled_filter() -> None:
    policy = _make_policy(
        person=ClassReconstructionRule(True, 0.80, 0.62, 0.25),
        vehicle=ClassReconstructionRule(True, 0.72, 0.55, 0.35),
        animal=ClassReconstructionRule(False, 0.75, 0.62, 0.20),
    )

    src = OpenVINORtspDetectionSource.__new__(OpenVINORtspDetectionSource)
    src.camera_id = "Cam_Carraio"
    src.conf_threshold = 0.62
    src.reconstruction_policy = policy

    raw_out = np.zeros((1, 84, 8400), dtype=np.float32)
    # Index 10: person at conf=0.64 (>= 0.62 moving floor, < 0.80 stationary -> kept in 2D for tracker)
    raw_out[0, 0, 10] = 200.0
    raw_out[0, 1, 10] = 320.0
    raw_out[0, 2, 10] = 60.0
    raw_out[0, 3, 10] = 140.0
    raw_out[0, 4 + 0, 10] = 0.64

    # Index 20: person at conf=0.59 (< 0.62 floor -> dropped in 2D)
    raw_out[0, 0, 20] = 320.0
    raw_out[0, 1, 20] = 320.0
    raw_out[0, 2, 20] = 60.0
    raw_out[0, 3, 20] = 140.0
    raw_out[0, 4 + 0, 20] = 0.59

    # Index 30: car at conf=0.57 (>= 0.55 vehicle floor -> kept in 2D)
    raw_out[0, 0, 30] = 480.0
    raw_out[0, 1, 30] = 320.0
    raw_out[0, 2, 30] = 120.0
    raw_out[0, 3, 30] = 90.0
    raw_out[0, 4 + 2, 30] = 0.57

    # Index 40: dog (COCO 16) at conf=0.95 (animal disabled -> dropped in 2D)
    raw_out[0, 0, 40] = 100.0
    raw_out[0, 1, 40] = 360.0
    raw_out[0, 2, 40] = 50.0
    raw_out[0, 3, 40] = 50.0
    raw_out[0, 4 + 16, 40] = 0.95

    out_port = object()

    class _MockCompiled:
        def output(self, idx: int):
            return out_port

        def __call__(self, _inputs):
            return {out_port: SimpleNamespace(data=raw_out)}

    src._compiled_ov = _MockCompiled()
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    events = src._infer_openvino_yolo(frame, ts=1000.0)
    labels_confs = [(e.class_label, round(e.confidence, 2)) for e in events]
    assert labels_confs == [("person", 0.64), ("car", 0.57)]


def test_tracker_blocks_rain_stationary_person_ghost_for_30s_but_allows_moving_or_high_conf() -> None:
    policy = _make_policy(
        person=ClassReconstructionRule(True, 0.78, 0.62, 0.25),
    )
    tracker = Kalman3DMultiTracker(reconstruction_policy=policy)

    # 1. Stationary rain ghost oscillating ±0.10m around (-4.0, 9.0) at conf=0.65 for 30s -> NEVER reconstructed
    for step in range(60):
        ts = 1000.0 + step * 0.5
        jitter_x = 0.10 if (step % 2 == 0) else -0.10
        jitter_z = 0.06 if (step % 3 == 0) else -0.06
        tracks, assign = tracker.update_with_assignments(
            [TrackObservation3D("Cam_Carraio", ts, "person", (-4.0 + jitter_x, 0.0, 9.0 + jitter_z), 0.65)],
            now_ts=ts,
        )
        assert tracks == [], f"Rain ghost must not be reconstructed at step {step}"
        assert assign == {}

    # 2. Real moving person walking at 1.1 m/s with conf=0.65 (>= 0.62 moving threshold) -> gets track_id=1
    tracks_1, assign_1 = tracker.update_with_assignments(
        [TrackObservation3D("Cam_Carraio", 1040.0, "person", (0.0, 0.0, 8.0), 0.65)],
        now_ts=1040.0,
    )
    assert tracks_1 == []  # 1st frame has no velocity yet and 0.65 < 0.78 stationary
    assert assign_1 == {}

    tracks_2, assign_2 = tracker.update_with_assignments(
        [TrackObservation3D("Cam_Carraio", 1040.5, "person", (0.55, 0.0, 8.0), 0.65)],
        now_ts=1040.5,
    )
    assert len(tracks_2) == 1
    assert tracks_2[0].track_id == 1  # Tentative rain ghosts never burned positive track IDs
    assert assign_2 == {0: 1}

    # 3. Stationary person with high confidence (0.85 >= 0.78) -> reconstructed immediately on frame 1
    tracks_3, assign_3 = tracker.update_with_assignments(
        [
            TrackObservation3D("Cam_Carraio", 1041.0, "person", (1.10, 0.0, 8.0), 0.65),
            TrackObservation3D("Cam_Ingresso", 1041.0, "person", (-8.0, 0.0, 5.0), 0.85),
        ],
        now_ts=1041.0,
    )
    assert len(tracks_3) == 2
    assert set(assign_3.values()) == {1, 2}


def test_min_speed_zero_vs_nonzero_tolerance_for_person_vehicle_and_animal() -> None:
    # A. Zero min_speed_mps ("mettendola a zero non tollera"): even 0.05 m/s counts as moving
    pol_zero = _make_policy(
        person=ClassReconstructionRule(True, 0.80, 0.62, 0.0),
        vehicle=ClassReconstructionRule(True, 0.78, 0.60, 0.0),
        animal=ClassReconstructionRule(True, 0.80, 0.60, 0.0),
    )
    tr_zero = Kalman3DMultiTracker(reconstruction_policy=pol_zero)

    # Purely stationary at 0.65 < 0.80 -> NOT reconstructed
    for step in range(4):
        ts = 2000.0 + step * 1.0
        tracks = tr_zero.update(
            [TrackObservation3D("Cam_Carraio", ts, "person", (2.0, 0.0, 6.0), 0.65)],
            now_ts=ts,
        )
        assert tracks == []

    # Very slow drift (0.06 m/s) at 0.65 -> WITH min_speed=0.0, it IS reconstructed
    tracks_slow = tr_zero.update(
        [TrackObservation3D("Cam_Carraio", 2004.0, "person", (2.06, 0.0, 6.0), 0.65)],
        now_ts=2004.0,
    )
    assert len(tracks_slow) == 1

    # B. Positive min_speed_mps: tolerates slow drift (0.06 m/s <= 0.25) as stationary
    pol_tol = _make_policy(
        person=ClassReconstructionRule(True, 0.80, 0.62, 0.25),
        vehicle=ClassReconstructionRule(True, 0.78, 0.60, 0.40),
        animal=ClassReconstructionRule(True, 0.80, 0.60, 0.25),
    )
    tr_tol = Kalman3DMultiTracker(reconstruction_policy=pol_tol)

    for step in range(5):
        ts = 3000.0 + step * 1.0
        tracks = tr_tol.update(
            [
                TrackObservation3D("Cam_Carraio", ts, "person", (2.0 + step * 0.06, 0.0, 6.0), 0.65),
                TrackObservation3D("Cam_Carraio", ts, "car", (-5.0 + step * 0.15, 0.0, 10.0), 0.65),
                TrackObservation3D("Cam_Carraio", ts, "dog", (4.0 + step * 0.08, 0.0, 7.0), 0.65),
            ],
            now_ts=ts,
        )
        assert tracks == [], f"Slow drift below min_speed must be treated as stationary at step {step}"

    # When vehicle speeds up above 0.40 m/s (e.g. 1.5 m/s) at 0.65 (>= 0.60), it reconstructs
    tr_tol.update(
        [TrackObservation3D("Cam_Carraio", 3005.0, "car", (-2.5, 0.0, 10.0), 0.65)],
        now_ts=3005.0,
    )
    car_tracks = tr_tol.update(
        [TrackObservation3D("Cam_Carraio", 3005.5, "car", (-1.5, 0.0, 10.0), 0.65)],
        now_ts=3005.5,
    )
    assert any(t.class_label == "car" for t in car_tracks)


def test_pipeline_prevents_scene_event_and_alarm_for_stationary_rain_ghost(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPATIAL_RECONSTRUCT_PERSON", "true")
    monkeypatch.setenv("SPATIAL_PERSON_STATIONARY_CONF_THRESHOLD", "0.78")
    monkeypatch.setenv("SPATIAL_PERSON_MOVING_CONF_THRESHOLD", "0.62")
    monkeypatch.setenv("SPATIAL_PERSON_MIN_SPEED_MPS", "0.25")
    monkeypatch.setenv("OPENVINO_CONF_THRESHOLD", "0.62")

    cfg = SpatialServerConfig(
        host="127.0.0.1",
        port=8765,
        manifest_path=REPO_ROOT / "public" / "models" / "scene_manifest.json",
        glb_path=REPO_ROOT / "public" / "models" / "house_optimized.glb",
        sqlite_db_path=tmp_path / "rain_test.db",
        calibration_override_path=tmp_path / "calibs.json",
        data_dir=tmp_path,
        models_dir=tmp_path,
        default_ingestion_mode="synthetic",
        go2rtc_rtsp_url="",
        mqtt_host="",
        mqtt_port=1883,
        mqtt_user="",
        mqtt_password="",
        mqtt_topic_prefix="",
        openvino_device="CPU",
        openvino_model_path="",
        db_retention_days=7,
        face_webhook_url="",
        openvino_conf_threshold=0.62,
        reconstruct_person=True,
        person_stationary_conf_threshold=0.78,
        person_moving_conf_threshold=0.62,
        person_min_speed_mps=0.25,
        auth_required=False,
    )
    svc = build_pipeline_service(cfg)

    async def _run() -> None:
        await svc.automation_engine.set_virtual_entity_state(
            "sh3d.allarme",
            "Acceso",
            operation="set",
            trigger_automations=False,
        )
        # Send 20s of stationary/jittering person detections at conf=0.65 (below 0.78)
        for i in range(20):
            ts = 5000.0 + i * 1.0
            du = 0.003 if (i % 2 == 0) else -0.003
            evt = DetectionEvent(
                camera_id="Cam_Portico",
                timestamp=ts,
                class_label="person",
                confidence=0.65,
                bbox=BoundingBox2D(
                    x_min=0.45 + du,
                    y_min=0.40,
                    x_max=0.55 + du,
                    y_max=0.80,
                ),
            )
            tracks = await svc.process_detection_batch([evt])
            assert tracks == []
            assert svc.scene_event_manager.get_active_event() is None

        await svc.flush_pending_to_db()
        assert svc.repository.query_time_range(4990.0, 5030.0) == []

        # Now send a high-confidence stationary detection (0.86 >= 0.78) -> reconstructed & creates alert SceneEvent
        real_evt = DetectionEvent(
            camera_id="Cam_Portico",
            timestamp=5025.0,
            class_label="person",
            confidence=0.86,
            bbox=BoundingBox2D(x_min=0.45, y_min=0.40, x_max=0.55, y_max=0.80),
        )
        real_tracks = await svc.process_detection_batch([real_evt])
        assert len(real_tracks) == 1
        active_ev = svc.scene_event_manager.get_active_event()
        assert active_ev is not None
        assert active_ev.importance == "alert"
        await svc.scene_event_manager.close()

    try:
        asyncio.run(_run())
    finally:
        svc.repository.close()
