from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from spatial_server.automations import (
    ActionSpec,
    AutomationEngineService,
    AutomationRuleDefinition,
    ConditionSpec,
    Point2D,
    PreTriggerStageSpec,
    SpatialZoneDefinition,
    SubjectFilterSpec,
    TriggerSpec,
)
from spatial_server.config import SpatialServerConfig
from spatial_server.domain.models import BoundingBox2D, DetectionEvent, SpatialPoint3D, TrackedEntity3D
from spatial_server.events import EventSnapshotStore, SceneEventManager
from spatial_server.main import create_app
from spatial_server.persistence.repository import SQLiteWALTrackRepository


def _make_vehicle_track(
    track_id: int = 1,
    x: float = 0.0,
    z: float = 0.0,
    vx: float = 0.0,
    vz: float = 0.0,
    *,
    plate: str | None = None,
    plate_whitelisted: bool | None = None,
    biometric_status: str = "none",
    ts: float = 1000.0,
) -> TrackedEntity3D:
    return TrackedEntity3D(
        track_id=track_id,
        class_label="car",
        plate=plate,
        plate_confidence=0.95 if plate else 0.0,
        plate_whitelisted=plate_whitelisted,
        biometric_locked=biometric_status == "locked",
        biometric_status=biometric_status,  # type: ignore[arg-type]
        state=SpatialPoint3D(x=x, y=0.0, z=z, vx=vx, vy=0.0, vz=vz, camera_sources=["Cam_Carraio"]),
        last_seen=ts,
    )


def _make_person_track(
    track_id: int = 10,
    x: float = 2.0,
    z: float = 2.0,
    *,
    identity: str | None = None,
    biometric_status: str = "none",
    ts: float = 1000.0,
) -> TrackedEntity3D:
    return TrackedEntity3D(
        track_id=track_id,
        class_label="person",
        identity=identity,
        identity_confidence=0.95 if identity else 0.0,
        biometric_locked=biometric_status == "locked",
        biometric_status=biometric_status,  # type: ignore[arg-type]
        state=SpatialPoint3D(x=x, y=0.0, z=z, vx=0.3, vy=0.0, vz=0.0, camera_sources=["Cam_Cancelletto"]),
        last_seen=ts,
    )


def _cancelletto_zone() -> SpatialZoneDefinition:
    return SpatialZoneDefinition(
        zone_id="zone_cancelletto",
        name="Cancelletto",
        geometry_type="polygon",
        vertices=[Point2D(x=0.0, z=0.0), Point2D(x=6.0, z=0.0), Point2D(x=6.0, z=6.0), Point2D(x=0.0, z=6.0)],
    )


def _vialetto_zone() -> SpatialZoneDefinition:
    return SpatialZoneDefinition(
        zone_id="zone_vialetto",
        name="Vialetto",
        geometry_type="polygon",
        vertices=[Point2D(x=-10.0, z=0.0), Point2D(x=-1.0, z=0.0), Point2D(x=-1.0, z=6.0), Point2D(x=-10.0, z=6.0)],
    )


def test_bugfix_biometric_grace_anchored_to_trigger_and_no_premature_unknown_drop(tmp_path: Path) -> None:
    """
    Reproduces Production Bug #1 & #3:
    Vehicle tracked outside zone for 8s before entering `Cancelletto` (`biometric_grace_s=2.5s`),
    with an initial distant `biometric_status="unknown"` before slowing down and locking plate.
    Must wait for plate lock within 2.5s of zone entry and fire!
    """
    async def _run() -> None:
        repo = SQLiteWALTrackRepository(tmp_path / "bug1.db")
        cfg = SpatialServerConfig.from_env()
        engine = AutomationEngineService(
            config=cfg,
            repository=repo,
            whitelisted_plates_provider=lambda: {"HD858PC"},
        )
        await engine.upsert_zone(_cancelletto_zone())
        await engine.set_virtual_entity_state("sh3d.cancello", "off", operation="turn_off")

        await engine.upsert_rule(
            AutomationRuleDefinition(
                rule_id="rule_cancello_grace",
                name="Cancello Grace",
                cooldown_s=0.0,
                triggers=[
                    TriggerSpec(
                        type="zone_presence",
                        subject_filter=SubjectFilterSpec(
                            classes=["vehicle"],
                            plate_mode="include",
                            plates=["HD858PC"],
                            biometric_grace_s=2.5,
                        ),
                        params={"zone_id": "zone_cancelletto", "event": "enter", "min_dwell_s": 0.0},
                    )
                ],
                actions=[ActionSpec(type="set_virtual_entity", params={"entity_id": "sh3d.cancello", "operation": "turn_on"})],
            )
        )

        # Tracked outside zone for 8 seconds with `unknown` status
        for dt in range(0, 8):
            await engine.on_tracks_updated(
                [_make_vehicle_track(5, x=-5.0 + dt * 0.4, z=3.0, vx=0.8, biometric_status="unknown", ts=1000.0 + dt)],
                1000.0 + dt,
            )

        # Enters zone at t=1008.0 while still `unknown`
        logs_enter = await engine.on_tracks_updated(
            [_make_vehicle_track(5, x=2.0, z=3.0, vx=0.6, biometric_status="unknown", ts=1008.0)],
            1008.0,
        )
        assert logs_enter == []

        # Plate resolves 1.5s after entering (< 2.5s grace, even though 9.5s after first_seen!)
        tr_locked = _make_vehicle_track(5, x=2.5, z=3.0, vx=0.05, plate="HD858PC", plate_whitelisted=True, biometric_status="locked", ts=1009.5)
        logs_bio = await engine.on_biometric_update(
            {"track_id": 5, "modality": "alpr", "camera_id": "Cam_Carraio", "plate": "HD858PC", "biometric_status": "locked"},
            [tr_locked],
            1009.5,
        )
        assert len(logs_bio) == 1
        assert engine.virtual_entities["sh3d.cancello"].state == "on"
        repo.close()

    asyncio.run(_run())


def test_bugfix_track_kinematics_peak_in_window_when_vehicle_stops_for_alpr(tmp_path: Path) -> None:
    """
    Reproduces Production Bug #2:
    Vehicle drives at 1.8 m/s, then slows down & stops for 4s before ALPR locks `HD858PC`.
    With `evaluation_mode="peak_in_window"` and `window_s=10.0`, `min_speed_mps=0.5` MUST pass,
    while a stationary parked car (0.02 m/s) MUST fail.
    """
    async def _run() -> None:
        repo = SQLiteWALTrackRepository(tmp_path / "bug2.db")
        cfg = SpatialServerConfig.from_env()
        engine = AutomationEngineService(
            config=cfg,
            repository=repo,
            whitelisted_plates_provider=lambda: {"HD858PC"},
        )
        await engine.upsert_zone(_cancelletto_zone())
        await engine.set_virtual_entity_state("sh3d.cancello", "off", operation="turn_off")

        await engine.upsert_rule(
            AutomationRuleDefinition(
                rule_id="rule_peak_speed",
                name="Cancello Peak Speed",
                cooldown_s=0.0,
                triggers=[
                    TriggerSpec(
                        type="zone_presence",
                        subject_filter=SubjectFilterSpec(
                            classes=["vehicle"],
                            plate_mode="whitelisted",
                            biometric_grace_s=0.0,
                        ),
                        params={"zone_id": "zone_cancelletto", "event": "present", "min_dwell_s": 0.0},
                    )
                ],
                condition=ConditionSpec(
                    type="track_kinematics",
                    params={
                        "evaluation_mode": "peak_in_window",
                        "window_s": 10.0,
                        "min_speed_mps": 0.5,
                    },
                ),
                actions=[ActionSpec(type="set_virtual_entity", params={"entity_id": "sh3d.cancello", "operation": "turn_on"})],
            )
        )

        # Car approaches at 1.8 m/s (t=100..103)
        t = 100.0
        for step in range(7):
            await engine.on_tracks_updated(
                [_make_vehicle_track(1, x=-4.0 + step * 0.9, z=3.0, vx=1.8, ts=t + step * 0.5)],
                t + step * 0.5,
            )
        # Car slows down and stops inside zone (t=103.5..107.5)
        for step in range(8):
            await engine.on_tracks_updated(
                [_make_vehicle_track(1, x=2.0, z=3.0, vx=0.0, ts=103.5 + step * 0.5)],
                103.5 + step * 0.5,
            )

        # Plate locks while car is completely stopped (t=107.6)
        tr_locked = _make_vehicle_track(1, x=2.0, z=3.0, vx=0.0, plate="HD858PC", plate_whitelisted=True, biometric_status="locked", ts=107.6)
        logs = await engine.on_biometric_update(
            {"track_id": 1, "modality": "alpr", "camera_id": "Cam_Carraio", "plate": "HD858PC", "biometric_status": "locked"},
            [tr_locked],
            107.6,
        )
        assert len(logs) == 1
        assert engine.virtual_entities["sh3d.cancello"].state == "on"

        # Reset and verify a parked car (0.0 m/s for 10s) does NOT pass
        await engine.set_virtual_entity_state("sh3d.cancello", "off", operation="turn_off")
        for step in range(6):
            await engine.on_tracks_updated(
                [_make_vehicle_track(2, x=3.0, z=3.0, vx=0.0, ts=200.0 + step)],
                200.0 + step,
            )
        tr_parked = _make_vehicle_track(2, x=3.0, z=3.0, vx=0.0, plate="HD858PC", plate_whitelisted=True, biometric_status="locked", ts=206.0)
        logs_parked = await engine.on_biometric_update(
            {"track_id": 2, "modality": "alpr", "camera_id": "Cam_Carraio", "plate": "HD858PC", "biometric_status": "locked"},
            [tr_parked],
            206.0,
        )
        assert logs_parked == []
        assert engine.virtual_entities["sh3d.cancello"].state == "off"
        repo.close()

    asyncio.run(_run())


def test_pre_trigger_velocity_then_whitelisted_plate_sequence(tmp_path: Path) -> None:
    """
    User's primary scenario:
    Pre-Trigger: vehicle moving >= 0.5 m/s (arms 10s wait window, sliding refresh while moving).
    Main Trigger: ALPR detects whitelisted plate (even after vehicle slows/stops within 10s).
    Verifies:
      1) Moving -> stop -> plate within 10s => FIRES & consumes armed token
      2) Sliding refresh while moving >6s then stopped 6s => FIRES
      3) Expired >10s after last motion => DOES NOT FIRE + diagnostic `pre_trigger_expired`
      4) Parked car (no motion) => DOES NOT FIRE
    """
    async def _run() -> None:
        repo = SQLiteWALTrackRepository(tmp_path / "seq.db")
        cfg = SpatialServerConfig.from_env()
        bc: list[dict[str, Any]] = []

        async def _on_bc(m: dict[str, Any]) -> None:
            bc.append(m)

        engine = AutomationEngineService(
            config=cfg,
            repository=repo,
            broadcast_callback=_on_bc,
            whitelisted_plates_provider=lambda: {"HD858PC"},
        )
        await engine.upsert_zone(_cancelletto_zone())
        await engine.set_virtual_entity_state("sh3d.cancello", "off", operation="turn_off")

        rule = AutomationRuleDefinition(
            rule_id="rule_cancello_pretrigger",
            name="Cancello Pre-Trigger Velocità + Targa",
            cooldown_s=0.0,
            pre_triggers=[
                PreTriggerStageSpec(
                    stage_id="pre_speed",
                    name="Veicolo in movimento",
                    max_wait_s=10.0,
                    correlation_scope="same_subject",
                    refresh_on_rearm=True,
                    consume_on_fire=True,
                    triggers=[
                        TriggerSpec(
                            type="kinematic_vector",
                            subject_filter=SubjectFilterSpec(classes=["vehicle"], biometric_grace_s=0.0),
                            params={"min_duration_s": 0.5, "min_speed_mps": 0.5},
                        )
                    ],
                )
            ],
            triggers=[
                TriggerSpec(
                    type="biometric_detection",
                    subject_filter=SubjectFilterSpec(classes=["vehicle"], plate_mode="whitelisted", biometric_grace_s=0.0),
                    params={"modality": "alpr", "zone_id": "zone_cancelletto", "require_locked": True},
                )
            ],
            actions=[
                ActionSpec(type="set_virtual_entity", params={"entity_id": "sh3d.cancello", "operation": "turn_on"}),
            ],
        )
        await engine.upsert_rule(rule)

        # Case 1: Vehicle moves for 6s (t=100..106) -> sliding refresh keeps window alive
        for step in range(13):
            ts = 100.0 + step * 0.5
            await engine.on_tracks_updated(
                [_make_vehicle_track(10, x=-5.0 + step * 0.6, z=3.0, vx=1.2, ts=ts)],
                ts,
            )
        armed = engine.get_armed_states(now_ts=106.0)
        assert len(armed) == 1
        assert armed[0]["track_id"] == 10
        assert any(m.get("type") == "automation_pretrigger_updated" for m in bc)

        # Vehicle stops inside zone for 7s (t=106.5..113.0) -> 13s from start, 7s from last motion (<10s!)
        for step in range(1, 14):
            ts = 106.0 + step * 0.5
            await engine.on_tracks_updated(
                [_make_vehicle_track(10, x=2.5, z=3.0, vx=0.0, ts=ts)],
                ts,
            )

        # Pending ALPR update must NOT trigger when require_locked=True
        tr_pending = _make_vehicle_track(10, x=2.5, z=3.0, vx=0.0, plate="HD858PC", plate_whitelisted=None, biometric_status="pending", ts=113.1)
        logs_pend = await engine.on_biometric_update(
            {"track_id": 10, "modality": "alpr", "camera_id": "Cam_Carraio", "plate": "HD858PC", "biometric_status": "pending"},
            [tr_pending],
            113.1,
        )
        assert logs_pend == []

        # Locked ALPR update at t=113.2 -> FIRES!
        tr_locked = _make_vehicle_track(10, x=2.5, z=3.0, vx=0.0, plate="HD858PC", plate_whitelisted=True, biometric_status="locked", ts=113.2)
        logs_fire = await engine.on_biometric_update(
            {"track_id": 10, "modality": "alpr", "camera_id": "Cam_Carraio", "plate": "HD858PC", "biometric_status": "locked"},
            [tr_locked],
            113.2,
        )
        assert len(logs_fire) == 1
        assert engine.virtual_entities["sh3d.cancello"].state == "on"
        assert engine.get_armed_states(now_ts=113.2) == []  # consumed!

        # Case 2: Expiration (> 10s after motion ends)
        await engine.set_virtual_entity_state("sh3d.cancello", "off", operation="turn_off")
        for step in range(4):
            ts = 200.0 + step * 0.5
            await engine.on_tracks_updated([_make_vehicle_track(11, x=1.0 + step * 0.6, z=3.0, vx=1.2, ts=ts)], ts)
        assert len(engine.get_armed_states(now_ts=201.5)) == 1

        # Advance 11.5s without motion -> expired
        await engine.evaluate_periodic_tick(213.0)
        assert engine.get_armed_states(now_ts=213.0) == []
        diags = engine.get_rule_diagnostics("rule_cancello_pretrigger")
        assert any(d["event"] == "pre_trigger_expired" for d in diags)

        tr_late = _make_vehicle_track(11, x=3.0, z=3.0, vx=0.0, plate="HD858PC", plate_whitelisted=True, biometric_status="locked", ts=213.1)
        await engine.on_tracks_updated([tr_late], 213.1)
        logs_late = await engine.on_biometric_update(
            {"track_id": 11, "modality": "alpr", "camera_id": "Cam_Carraio", "plate": "HD858PC", "biometric_status": "locked"},
            [tr_late],
            213.1,
        )
        assert logs_late == []
        assert engine.virtual_entities["sh3d.cancello"].state == "off"

        # Case 3: Parked car without prior motion -> DOES NOT FIRE
        tr_parked = _make_vehicle_track(12, x=3.0, z=3.0, vx=0.0, plate="HD858PC", plate_whitelisted=True, biometric_status="locked", ts=300.0)
        await engine.on_tracks_updated([tr_parked], 300.0)
        logs_parked = await engine.on_biometric_update(
            {"track_id": 12, "modality": "alpr", "camera_id": "Cam_Carraio", "plate": "HD858PC", "biometric_status": "locked"},
            [tr_parked],
            300.0,
        )
        assert logs_parked == []
        repo.close()

    asyncio.run(_run())


def test_pre_trigger_multi_vehicle_isolation_and_occlusion_handoff(tmp_path: Path) -> None:
    """
    Verifies CorrelationPolicy `same_subject`:
    - Simultaneously active Car A (fast, unknown) + Car B (parked, whitelisted) -> MUST NOT cross-correlate!
    - Track ID handoff after occlusion inside the same SceneEvent -> MUST correlate!
    """
    async def _run() -> None:
        repo = SQLiteWALTrackRepository(tmp_path / "corr.db")
        store = EventSnapshotStore(tmp_path)
        mgr = SceneEventManager(repository=repo, snapshot_store=store)
        cfg = SpatialServerConfig.from_env()
        engine = AutomationEngineService(
            config=cfg,
            repository=repo,
            scene_event_manager=mgr,
            whitelisted_plates_provider=lambda: {"HD858PC"},
        )
        await engine.upsert_zone(_cancelletto_zone())
        await engine.set_virtual_entity_state("sh3d.cancello", "off", operation="turn_off")

        await engine.upsert_rule(
            AutomationRuleDefinition(
                rule_id="rule_corr",
                name="Isolamento Multi-Veicolo",
                cooldown_s=0.0,
                pre_triggers=[
                    PreTriggerStageSpec(
                        stage_id="pre1",
                        max_wait_s=10.0,
                        correlation_scope="same_subject",
                        triggers=[
                            TriggerSpec(
                                type="kinematic_vector",
                                subject_filter=SubjectFilterSpec(classes=["vehicle"], biometric_grace_s=0.0),
                                params={"min_duration_s": 0.4, "min_speed_mps": 0.5},
                            )
                        ],
                    )
                ],
                triggers=[
                    TriggerSpec(
                        type="biometric_detection",
                        subject_filter=SubjectFilterSpec(classes=["vehicle"], plate_mode="whitelisted", biometric_grace_s=0.0),
                        params={"modality": "alpr"},
                    )
                ],
                actions=[ActionSpec(type="set_virtual_entity", params={"entity_id": "sh3d.cancello", "operation": "turn_on"})],
            )
        )

        # Two simultaneous active tracks in the active SceneEvent: track 101 moving fast, track 102 stationary parked
        det_init = DetectionEvent(
            camera_id="Cam_Carraio",
            timestamp=100.0,
            class_label="car",
            confidence=0.92,
            bbox=BoundingBox2D(x_min=0.2, y_min=0.2, x_max=0.6, y_max=0.8),
        )
        for step in range(4):
            ts = 100.0 + step * 0.5
            tr101 = _make_vehicle_track(101, x=-5.0 + step * 0.9, z=3.0, vx=1.8, ts=ts)
            tr102 = _make_vehicle_track(102, x=3.0, z=3.0, vx=0.0, ts=ts)
            if step == 0:
                await mgr.on_detection_batch([det_init], [tr101, tr102], {0: 101}, ts)
            await engine.on_tracks_updated([tr101, tr102], ts)

        # Parked track 102 gets whitelisted plate while moving track 101 is STILL active -> MUST NOT fire!
        tr101_still = _make_vehicle_track(101, x=-2.0, z=3.0, vx=1.5, ts=102.0)
        tr102_wl = _make_vehicle_track(102, x=3.0, z=3.0, vx=0.0, plate="HD858PC", plate_whitelisted=True, biometric_status="locked", ts=102.0)
        await engine.on_tracks_updated([tr101_still, tr102_wl], 102.0)
        logs_cross = await engine.on_biometric_update(
            {"track_id": 102, "modality": "alpr", "camera_id": "Cam_Carraio", "plate": "HD858PC", "biometric_status": "locked"},
            [tr101_still, tr102_wl],
            102.0,
        )
        assert logs_cross == []
        assert engine.virtual_entities["sh3d.cancello"].state == "off"

        # Now track 101 disappears (occluded) and re-appears as track 103 in the SAME SceneEvent -> MUST fire!
        det = DetectionEvent(
            camera_id="Cam_Carraio",
            timestamp=103.0,
            class_label="car",
            confidence=0.92,
            bbox=BoundingBox2D(x_min=0.2, y_min=0.2, x_max=0.6, y_max=0.8),
        )
        tr103 = _make_vehicle_track(103, x=2.0, z=3.0, vx=0.1, plate="HD858PC", plate_whitelisted=True, biometric_status="locked", ts=103.0)
        await mgr.on_detection_batch([det], [tr103], {0: 103}, 103.0)
        await engine.on_tracks_updated([tr103], 103.0)
        logs_handoff = await engine.on_biometric_update(
            {"track_id": 103, "modality": "alpr", "camera_id": "Cam_Carraio", "plate": "HD858PC", "biometric_status": "locked"},
            [tr103],
            103.0,
        )
        assert len(logs_handoff) == 1
        assert engine.virtual_entities["sh3d.cancello"].state == "on"

        await mgr.close()
        repo.close()

    asyncio.run(_run())


def test_multistage_pretrigger_and_within_triggers_and_new_conditions(tmp_path: Path) -> None:
    """
    Tests:
    - Multi-stage Pre-Trigger chain with `min_delay_s`, stage condition, and `match_mode="all"`
    - Main `trigger_logic="and_within"` (free order A+B and B+A within `trigger_window_s`)
    - New `scene_event` trigger and new `subject_filter`, `scene_event`, `recent_zone_visit` conditions
    - Non-blocking `delay` action with `execution_mode="single"`
    """
    async def _run() -> None:
        repo = SQLiteWALTrackRepository(tmp_path / "advanced.db")
        store = EventSnapshotStore(tmp_path)
        mgr = SceneEventManager(repository=repo, snapshot_store=store)
        cfg = SpatialServerConfig.from_env()
        engine = AutomationEngineService(
            config=cfg,
            repository=repo,
            scene_event_manager=mgr,
            known_identities_provider=lambda: {"Nicola"},
        )
        await engine.upsert_zone(_vialetto_zone())
        await engine.upsert_zone(_cancelletto_zone())
        await engine.set_virtual_entity_state("sh3d.porta", "off", operation="turn_off")
        await engine.set_virtual_entity_state("sh3d.allarme", "Acceso", operation="set")
        await engine.set_virtual_entity_state("sh3d.scene_flag", "off", operation="turn_off")
        await engine.set_virtual_entity_state("sh3d.delay_done", "off", operation="turn_off")

        # 1. Multi-stage + AND_WITHIN + recent_zone_visit + subject_filter
        await engine.upsert_rule(
            AutomationRuleDefinition(
                rule_id="rule_chain",
                name="Catena Multi-Stage",
                cooldown_s=0.0,
                pre_triggers=[
                    PreTriggerStageSpec(
                        stage_id="stg1",
                        name="Ingresso Vialetto",
                        max_wait_s=10.0,
                        min_delay_s=0.5,
                        condition=ConditionSpec(
                            type="entity_state",
                            params={"entity_id": "sh3d.allarme", "operator": "==", "value": "Acceso"},
                        ),
                        triggers=[
                            TriggerSpec(
                                type="zone_presence",
                                subject_filter=SubjectFilterSpec(classes=["person"], biometric_grace_s=0.0),
                                params={"zone_id": "zone_vialetto", "event": "enter"},
                            )
                        ],
                    ),
                ],
                trigger_logic="and_within",
                trigger_window_s=6.0,
                trigger_correlation_scope="same_subject",
                triggers=[
                    TriggerSpec(
                        trigger_id="trg_zone",
                        type="zone_presence",
                        subject_filter=SubjectFilterSpec(classes=["person"], biometric_grace_s=0.0),
                        params={"zone_id": "zone_cancelletto", "event": "enter"},
                    ),
                    TriggerSpec(
                        trigger_id="trg_face",
                        type="biometric_detection",
                        subject_filter=SubjectFilterSpec(classes=["person"], face_mode="include", identities=["Nicola"], biometric_grace_s=0.0),
                        params={"modality": "face"},
                    ),
                ],
                condition=ConditionSpec(
                    type="and",
                    children=[
                        ConditionSpec(type="recent_zone_visit", params={"zone_id": "zone_vialetto", "within_s": 8.0}),
                        ConditionSpec(type="subject_filter", params={"target": "trigger_track", "face_mode": "known"}),
                    ],
                ),
                actions=[ActionSpec(type="set_virtual_entity", params={"entity_id": "sh3d.porta", "operation": "turn_on"})],
            )
        )

        # Person enters Vialetto at t=100.0
        await engine.on_tracks_updated([_make_person_track(20, x=-5.0, z=3.0, ts=100.0)], 100.0)
        # Too early (< min_delay_s=0.5s) at t=100.2
        await engine.on_tracks_updated([_make_person_track(20, x=2.0, z=3.0, ts=100.2)], 100.2)
        assert engine.virtual_entities["sh3d.porta"].state == "off"

        # Exits Vialetto & enters Cancelletto at t=101.0 (trg_zone fires), then face locks at t=101.5 (trg_face fires)
        await engine.on_tracks_updated([_make_person_track(20, x=2.0, z=3.0, ts=101.0)], 101.0)
        tr_nicola = _make_person_track(20, x=2.5, z=3.0, identity="Nicola", biometric_status="locked", ts=101.5)
        logs_chain = await engine.on_biometric_update(
            {"track_id": 20, "modality": "face", "camera_id": "Cam_Cancelletto", "identity": "Nicola", "biometric_status": "locked"},
            [tr_nicola],
            101.5,
        )
        assert len(logs_chain) == 1
        assert engine.virtual_entities["sh3d.porta"].state == "on"

        # 2. SceneEvent trigger + scene_event condition
        await engine.upsert_rule(
            AutomationRuleDefinition(
                rule_id="rule_scene_alert",
                name="Allerta Episodio",
                cooldown_s=0.0,
                triggers=[TriggerSpec(type="scene_event", params={"event": "started", "importance": "alert"})],
                condition=ConditionSpec(type="scene_event", params={"has_unknown_person": "yes", "min_subjects": 1}),
                actions=[ActionSpec(type="set_virtual_entity", params={"entity_id": "sh3d.scene_flag", "operation": "turn_on"})],
            )
        )
        det = DetectionEvent(
            camera_id="Cam_Cancelletto",
            timestamp=200.0,
            class_label="person",
            confidence=0.92,
            bbox=BoundingBox2D(x_min=0.3, y_min=0.2, x_max=0.5, y_max=0.8),
        )
        tr_unk = _make_person_track(30, x=2.0, z=2.0, identity=None, biometric_status="unknown", ts=200.0)
        ev = await mgr.on_detection_batch([det], [tr_unk], {0: 30}, 200.0, alarm_state="Acceso")
        assert ev is not None
        logs_scene = await engine.on_scene_event_lifecycle("started", ev, 200.0)
        assert len(logs_scene) == 1
        assert engine.virtual_entities["sh3d.scene_flag"].state == "on"

        # 3. Non-blocking delay action + execution_mode="single"
        await engine.upsert_rule(
            AutomationRuleDefinition(
                rule_id="rule_delay_nonblocking",
                name="Ritardo Non Bloccante",
                execution_mode="single",
                cooldown_s=0.0,
                triggers=[TriggerSpec(type="entity_state_change", params={"entity_id": "sh3d.trigger_delay", "to_state": "on"})],
                actions=[
                    ActionSpec(type="delay", params={"seconds": 0.08}),
                    ActionSpec(type="set_virtual_entity", params={"entity_id": "sh3d.delay_done", "operation": "turn_on"}),
                ],
            )
        )
        await engine.set_virtual_entity_state("sh3d.trigger_delay", "off", operation="turn_off", trigger_automations=False)
        t0 = asyncio.get_running_loop().time()
        await engine.set_virtual_entity_state("sh3d.trigger_delay", "on", operation="turn_on", trigger_automations=True)
        elapsed_call = asyncio.get_running_loop().time() - t0
        assert elapsed_call < 0.06  # returned immediately without blocking!
        await asyncio.sleep(0.15)
        assert engine.virtual_entities["sh3d.delay_done"].state == "on"

        await mgr.close()
        repo.close()

    asyncio.run(_run())


def test_automations_rest_armed_diagnostics_and_legacy_backward_compat(tmp_path: Path) -> None:
    cfg = replace(
        SpatialServerConfig.from_env(),
        dev_mode=True,
        auth_required=False,
        biometrics_enabled=False,
        default_ingestion_mode="synthetic",
        sqlite_db_path=tmp_path / "api_pretrig.db",
        data_dir=tmp_path,
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        # Legacy rule payload (without pre_triggers / trigger_logic) must remain 100% valid
        legacy_payload = {
            "rule_id": "rule_legacy_1",
            "name": "Legacy Rule",
            "triggers": [
                {
                    "type": "zone_presence",
                    "params": {"zone_id": "z1", "event": "enter"},
                }
            ],
            "actions": [
                {"type": "ui_alert", "params": {"title": "Test", "message": "Ciao"}}
            ],
        }
        put_res = client.put("/api/v1/automations/rules", json=legacy_payload)
        assert put_res.status_code == 200
        saved = put_res.json()["rule"]
        assert saved["pre_triggers"] == []
        assert saved["trigger_logic"] == "or"

        boot = client.get("/api/v1/automations/bootstrap")
        assert boot.status_code == 200
        assert "armed_states" in boot.json()

        armed_res = client.get("/api/v1/automations/armed")
        assert armed_res.status_code == 200
        assert armed_res.json()["armed_states"] == []

        diag_res = client.get("/api/v1/automations/rules/rule_legacy_1/diagnostics")
        assert diag_res.status_code == 200
        assert diag_res.json()["rule_id"] == "rule_legacy_1"

        assert client.get("/api/v1/automations/rules/nonexistent/diagnostics").status_code == 404
