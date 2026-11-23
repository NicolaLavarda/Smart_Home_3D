from __future__ import annotations

import asyncio
from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient

from spatial_server.automations import (
    ActionSpec,
    AstronomicalClock,
    AutomationEngineService,
    AutomationRuleDefinition,
    ConditionEvaluator,
    ConditionSpec,
    Point2D,
    SpatialGeometryEngine,
    SpatialZoneDefinition,
    SubjectFilterSpec,
    TrackKinematicHistoryBuffer,
    TriggerSpec,
    VirtualEntityDefinition,
)
from spatial_server.config import SpatialServerConfig
from spatial_server.domain.models import SpatialPoint3D, TrackedEntity3D
from spatial_server.main import create_app
from spatial_server.persistence.repository import SQLiteWALTrackRepository


def _make_track(
    track_id: int = 1,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    vx: float = 0.0,
    vz: float = 0.0,
    *,
    class_label: str = "person",
    identity: str | None = None,
    plate: str | None = None,
    plate_whitelisted: bool | None = None,
    biometric_status: str = "locked",
    ts: float = 1000.0,
) -> TrackedEntity3D:
    return TrackedEntity3D(
        track_id=track_id,
        class_label=class_label,
        identity=identity,
        identity_confidence=0.95 if identity else 0.0,
        plate=plate,
        plate_whitelisted=plate_whitelisted,
        biometric_locked=biometric_status == "locked",
        biometric_status=biometric_status,  # type: ignore[arg-type]
        state=SpatialPoint3D(x=x, y=y, z=z, vx=vx, vy=0.0, vz=vz),
        last_seen=ts,
    )


def test_geometry_polygon_and_oriented_perimeter_crossing() -> None:
    poly = SpatialZoneDefinition(
        zone_id="zone_giardino",
        name="Giardino",
        geometry_type="polygon",
        vertices=[
            Point2D(x=0.0, z=0.0),
            Point2D(x=4.0, z=0.0),
            Point2D(x=4.0, z=4.0),
            Point2D(x=0.0, z=4.0),
        ],
        y_min=-1.0,
        y_max=3.0,
        hysteresis_m=0.2,
    )
    assert SpatialGeometryEngine.is_point_in_zone_25d(2.0, 0.0, 2.0, poly) is True
    assert SpatialGeometryEngine.is_point_in_zone_25d(5.0, 0.0, 2.0, poly) is False
    # Out of vertical bounds (e.g. upper floor y=4.5)
    assert SpatialGeometryEngine.is_point_in_zone_25d(2.0, 4.5, 2.0, poly) is False
    # Spatial hysteresis keeps track inside if slightly outside edge by <= 0.2m
    assert SpatialGeometryEngine.is_point_in_zone_25d(4.12, 0.0, 2.0, poly, currently_inside=True) is True
    assert SpatialGeometryEngine.is_point_in_zone_25d(4.12, 0.0, 2.0, poly, currently_inside=False) is False

    # Oriented perimeter line from (0, 0) to (4, 0) -> normal is (0, +1) (+Z)
    perim = SpatialZoneDefinition(
        zone_id="perim_cancello",
        name="Soglia Cancello",
        geometry_type="perimeter",
        vertices=[Point2D(x=0.0, z=0.0), Point2D(x=4.0, z=0.0)],
    )
    cross_enter = SpatialGeometryEngine.check_perimeter_crossing((2.0, 0.0, -1.0), (2.0, 0.0, 1.0), perim)
    assert cross_enter is not None
    assert cross_enter.direction == "a_to_b"

    cross_exit = SpatialGeometryEngine.check_perimeter_crossing((2.0, 0.0, 1.0), (2.0, 0.0, -1.0), perim)
    assert cross_exit is not None
    assert cross_exit.direction == "b_to_a"


def test_kinematics_sliding_window_direction_speed_and_zone_transition() -> None:
    buf = TrackKinematicHistoryBuffer()
    zone_a = SpatialZoneDefinition(
        zone_id="zone_a",
        name="Vialetto",
        geometry_type="polygon",
        vertices=[Point2D(x=0, z=0), Point2D(x=2, z=0), Point2D(x=2, z=2), Point2D(x=0, z=2)],
    )
    zone_b = SpatialZoneDefinition(
        zone_id="zone_b",
        name="Portico",
        geometry_type="polygon",
        vertices=[Point2D(x=3, z=0), Point2D(x=5, z=0), Point2D(x=5, z=2), Point2D(x=3, z=2)],
    )
    zones = {"zone_a": zone_a, "zone_b": zone_b}

    # Move strictly East (+X, azimuth = 0 deg) at 2.0 m/s from x=1 (in zone_a) to x=4 (in zone_b)
    t0 = 100.0
    ev0 = buf.update_tracks([_make_track(1, x=1.0, z=1.0, vx=2.0, vz=0.0, ts=t0)], zones, t0)
    assert ev0[0].entered_zones == ["zone_a"]

    t1 = 101.0
    buf.update_tracks([_make_track(1, x=2.5, z=1.0, vx=2.0, vz=0.0, ts=t1)], zones, t1)

    t2 = 101.5
    ev2 = buf.update_tracks([_make_track(1, x=3.5, z=1.0, vx=2.0, vz=0.0, ts=t2)], zones, t2)
    assert ev2[0].entered_zones == ["zone_b"]
    assert len(ev2[0].zone_transitions) == 1
    trans = ev2[0].zone_transitions[0]
    assert trans.from_zone_id == "zone_a"
    assert trans.to_zone_id == "zone_b"
    assert trans.avg_speed_mps == pytest.approx(1.83, rel=0.2)

    metrics = buf.compute_window_kinematics(1, window_s=2.0, now_ts=t2)
    assert metrics is not None
    assert metrics.mean_speed_mps == pytest.approx(1.83, rel=0.2)
    assert metrics.mean_azimuth_deg == pytest.approx(0.0, abs=5.0)
    assert metrics.directional_consistency > 0.9


def test_automation_engine_end_to_end_rules_and_if_else_actions(tmp_path: Path) -> None:
    async def _run() -> None:
        db_path = tmp_path / "test_auto.db"
        repo = SQLiteWALTrackRepository(db_path)
        cfg = SpatialServerConfig.from_env()
        broadcasted: list[dict] = []

        async def _on_broadcast(msg: dict) -> None:
            broadcasted.append(msg)

        engine = AutomationEngineService(
            config=cfg,
            repository=repo,
            broadcast_callback=_on_broadcast,
            known_identities_provider=lambda: {"Nicola", "Maria"},
            whitelisted_plates_provider=lambda: {"AB123CD"},
        )

        # 1. Create a polygon zone
        zone = await engine.upsert_zone(
            SpatialZoneDefinition(
                zone_id="zone_ingresso",
                name="Zona Ingresso",
                geometry_type="polygon",
                vertices=[
                    Point2D(x=0.0, z=0.0),
                    Point2D(x=4.0, z=0.0),
                    Point2D(x=4.0, z=4.0),
                    Point2D(x=0.0, z=4.0),
                ],
            )
        )
        assert zone.zone_id in engine.zones

        # 2. Arm the internal alarm entity (`sh3d.allarme_perimetrale` = 'on')
        await engine.set_virtual_entity_state("sh3d.allarme_perimetrale", "on", operation="turn_on")
        assert engine.virtual_entities["sh3d.allarme_perimetrale"].state == "on"

        # 3. Create an automation rule:
        # WHEN person (anyone EXCEPT Nicola) enters zone_ingresso
        # AND (sh3d.allarme_perimetrale == 'on')
        # THEN IF sh3d.modalita_sicurezza == 'disarmed' -> turn_on sh3d.sirena_allarme + ui_alert
        rule = AutomationRuleDefinition(
            rule_id="rule_allarme_intruso",
            name="Allarme Intruso Ingresso",
            cooldown_s=0.0,
            triggers=[
                TriggerSpec(
                    type="zone_presence",
                    subject_filter=SubjectFilterSpec(
                        classes=["person"],
                        face_mode="exclude",
                        identities=["Nicola"],
                        biometric_grace_s=0.0,
                    ),
                    params={"zone_id": "zone_ingresso", "event": "enter", "min_dwell_s": 0.0},
                )
            ],
            condition=ConditionSpec(
                type="and",
                children=[
                    ConditionSpec(
                        type="entity_state",
                        params={"entity_id": "sh3d.allarme_perimetrale", "operator": "==", "value": "on"},
                    )
                ],
            ),
            actions=[
                ActionSpec(
                    type="if_then_else",
                    if_condition=ConditionSpec(
                        type="entity_state",
                        params={"entity_id": "sh3d.allarme_perimetrale", "operator": "==", "value": "on"},
                    ),
                    then_actions=[
                        ActionSpec(
                            type="set_virtual_entity",
                            params={"entity_id": "sh3d.sirena_allarme", "operation": "turn_on"},
                        ),
                        ActionSpec(
                            type="ui_alert",
                            params={
                                "title": "Intruso in {{ trigger.zone_name }}",
                                "message": "Soggetto: {{ track.identity }}",
                                "severity": "critical",
                            },
                        ),
                    ],
                )
            ],
        )
        await engine.upsert_rule(rule)

        # 4a. Excluded family member ("Nicola") enters -> must NOT trigger alarm!
        logs_nicola = await engine.on_tracks_updated(
            [_make_track(10, x=2.0, z=2.0, identity="Nicola", ts=2000.0)],
            2000.0,
        )
        assert len(logs_nicola) == 0
        assert engine.virtual_entities["sh3d.sirena_allarme"].state == "off"

        # 4b. Unknown person enters -> MUST trigger alarm and turn on sh3d.sirena_allarme!
        logs_intruder = await engine.on_tracks_updated(
            [_make_track(11, x=2.0, z=2.0, identity=None, biometric_status="unknown", ts=2005.0)],
            2005.0,
        )
        assert len(logs_intruder) == 1
        assert engine.virtual_entities["sh3d.sirena_allarme"].state == "on"
        alerts = [m for m in broadcasted if m.get("type") == "automation_ui_alert"]
        assert len(alerts) == 1
        assert "Zona Ingresso" in alerts[0]["title"]

        repo.close()

    asyncio.run(_run())


def test_automations_rest_endpoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SH3D_DEV_MODE", "true")
    monkeypatch.setenv("SPATIAL_AUTH_REQUIRED", "false")
    cfg = SpatialServerConfig.from_env()
    custom_cfg = SpatialServerConfig(
        **{
            **cfg.__dict__,
            "sqlite_db_path": tmp_path / "api_auto.db",
            "biometrics_enabled": False,
            "auth_required": False,
        }
    )
    app = create_app(custom_cfg)
    with TestClient(app) as client:
        boot = client.get("/api/v1/automations/bootstrap")
        assert boot.status_code == 200
        data = boot.json()
        assert data["status"] == "ok"
        assert len(data["virtual_entities"]) >= 3
        assert "sunrise_hhmm" in data["sun"]

        # Create a perimeter zone via PUT
        z_resp = client.put(
            "/api/v1/automations/zones",
            json={
                "zone_id": "perim_vialetto",
                "name": "Linea Vialetto",
                "geometry_type": "perimeter",
                "vertices": [{"x": -2.0, "z": 1.0}, {"x": 3.0, "z": 1.0}],
                "normal_flipped": True,
            },
        )
        assert z_resp.status_code == 200
        assert z_resp.json()["zone"]["zone_id"] == "perim_vialetto"

        # Toggle virtual entity state
        ve_resp = client.post(
            "/api/v1/automations/virtual-entities/sh3d.allarme_perimetrale/state",
            json={"operation": "turn_on"},
        )
        assert ve_resp.status_code == 200
        assert ve_resp.json()["entity"]["state"] == "on"
