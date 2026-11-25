from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import time
from typing import Any

import cv2
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
    SpatialZoneDefinition,
    SubjectFilterSpec,
    TriggerSpec,
    VirtualEntityDefinition,
)
from spatial_server.config import SpatialServerConfig
from spatial_server.domain.models import BoundingBox2D, DetectionEvent, SpatialPoint3D, TrackedEntity3D
from spatial_server.events import (
    EventSnapshotStore,
    FrameBoxAnnotation,
    SceneEventManager,
    SceneEventRecord,
    SceneSubjectRecord,
    SignedMediaTokenService,
    build_scene_sentence_it,
)
from spatial_server.integrations import HomeAssistantBridgeService
from spatial_server.main import create_app
from spatial_server.persistence.repository import SQLiteWALTrackRepository
from spatial_server.tracking.interfaces import TrackObservation3D
from spatial_server.tracking.kalman_tracker import Kalman3DMultiTracker


def _encode_test_jpeg(width: int = 640, height: int = 360) -> bytes:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = (42, 58, 74)
    cv2.rectangle(img, (180, 60), (420, 320), (160, 190, 210), -1)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _make_track(
    track_id: int = 1,
    x: float = 1.5,
    z: float = 1.5,
    *,
    class_label: str = "person",
    identity: str | None = None,
    plate: str | None = None,
    plate_whitelisted: bool | None = None,
    plate_owner: str | None = None,
    biometric_status: str = "none",
    camera_sources: list[str] | None = None,
    ts: float = 2000.0,
) -> TrackedEntity3D:
    return TrackedEntity3D(
        track_id=track_id,
        class_label=class_label,
        identity=identity,
        identity_confidence=0.94 if identity else 0.0,
        plate=plate,
        plate_whitelisted=plate_whitelisted,
        plate_owner=plate_owner,
        biometric_locked=biometric_status == "locked",
        biometric_status=biometric_status,  # type: ignore[arg-type]
        state=SpatialPoint3D(
            x=x,
            y=0.0,
            z=z,
            vx=0.2,
            vy=0.0,
            vz=0.1,
            camera_sources=camera_sources or ["Cam_Cancelletto"],
        ),
        last_seen=ts,
    )


def test_narrator_natural_italian_multi_subject_sentences() -> None:
    assert (
        build_scene_sentence_it(
            [SceneSubjectRecord(track_id=1, class_label="person")],
            location_label="al cancelletto",
        )
        == "C'è una persona al cancelletto."
    )
    assert (
        build_scene_sentence_it(
            [
                SceneSubjectRecord(track_id=1, class_label="person"),
                SceneSubjectRecord(track_id=2, class_label="person"),
            ],
            location_label="Cancelletto",
        )
        == "Ci sono 2 persone al cancelletto."
    )
    assert (
        build_scene_sentence_it(
            [SceneSubjectRecord(track_id=1, class_label="person", identity="Nicola")],
            location_label="al cancelletto",
        )
        == "C'è Nicola al cancelletto."
    )
    assert (
        build_scene_sentence_it(
            [
                SceneSubjectRecord(track_id=1, class_label="person", identity="Nicola"),
                SceneSubjectRecord(track_id=2, class_label="person"),
            ],
            location_label="al cancelletto",
        )
        == "Ci sono Nicola e un'altra persona al cancelletto."
    )
    assert (
        build_scene_sentence_it(
            [
                SceneSubjectRecord(track_id=1, class_label="person", identity="Nicola"),
                SceneSubjectRecord(track_id=2, class_label="person", identity="Maria"),
                SceneSubjectRecord(track_id=3, class_label="person"),
                SceneSubjectRecord(track_id=4, class_label="person"),
            ],
            location_label="al cancelletto",
        )
        == "Ci sono Nicola, Maria e altre 2 persone al cancelletto."
    )
    assert (
        build_scene_sentence_it(
            [SceneSubjectRecord(track_id=5, class_label="car", plate="AB123CD", plate_whitelisted=True, plate_owner="Marco")],
            camera_id="Cam_Carraio",
        )
        == "Auto di Marco (AB123CD) al carraio."
    )


def test_event_snapshot_store_and_signed_media(tmp_path: Path) -> None:
    store = EventSnapshotStore(tmp_path)
    frame = np.full((360, 640, 3), 80, dtype=np.uint8)
    boxes = [
        FrameBoxAnnotation(
            track_id=1,
            class_label="person",
            label="Sconosciuto",
            category="unknown",
            bbox_norm=(0.2, 0.15, 0.55, 0.9),
            sub_bbox_norm=(0.3, 0.18, 0.44, 0.42),
        )
    ]
    ev_id = "evt_1700000000000_ab12"
    raw_rel, ann_rel = store.save_event_snapshots(ev_id, frame, boxes, camera_label="Cancelletto", timestamp=1700000000.0)
    raw_path = store.resolve_snapshot_path(ev_id, "raw", known_relpath=raw_rel)
    ann_path = store.resolve_snapshot_path(ev_id, "annotated", known_relpath=ann_rel)
    assert raw_path is not None and raw_path.read_bytes().startswith(b"\xff\xd8")
    assert ann_path is not None and ann_path.read_bytes().startswith(b"\xff\xd8")
    assert ann_path.read_bytes() != raw_path.read_bytes()

    # Re-annotate after biometric lock without re-fetching raw image
    boxes[0] = boxes[0].model_copy(update={"label": "Nicola", "category": "known"})
    new_ann_rel = store.reannotate_event(ev_id, raw_rel, boxes, camera_label="Cancelletto", timestamp=1700000001.0)
    assert new_ann_rel == ann_rel
    assert store.resolve_snapshot_path("../../../etc/passwd", "raw") is None

    # HMAC signing checks
    signer = SignedMediaTokenService(lambda: b"test-secret-key", default_ttl_s=300)
    exp, sig = signer.sign_media_path(ev_id, "annotated", now_ts=1000.0)
    assert signer.verify_media_signature(ev_id, "annotated", exp, sig, now_ts=1200.0) is True
    assert signer.verify_media_signature(ev_id, "raw", exp, sig, now_ts=1200.0) is False
    assert signer.verify_media_signature(ev_id, "annotated", exp, sig, now_ts=1500.0) is False
    url = signer.build_signed_url("https://casa.ts.net", ev_id, "annotated", now_ts=1000.0)
    assert url.startswith(f"https://casa.ts.net/api/v1/events/{ev_id}/media/annotated.jpg?exp=")


def test_scene_event_manager_camera_ranking_capture_and_hitl(tmp_path: Path) -> None:
    jpeg_bytes = _encode_test_jpeg()

    def _mock_go2rtc(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/frame.jpeg":
            return httpx.Response(200, content=jpeg_bytes, headers={"content-type": "image/jpeg"})
        return httpx.Response(404)

    async def _run() -> None:
        repo = SQLiteWALTrackRepository(tmp_path / "events.db")
        store = EventSnapshotStore(tmp_path)
        broadcasts: list[dict[str, Any]] = []

        async def _on_bc(msg: dict[str, Any]) -> None:
            broadcasts.append(msg)

        mgr = SceneEventManager(
            repository=repo,
            snapshot_store=store,
            inertia_s=15.0,
            pre_roll_s=3.0,
            panoramic_cameras={"Cam_Pano"},
            broadcast_callback=_on_bc,
            http_transport=httpx.MockTransport(_mock_go2rtc),
        )

        # Pinhole well-framed subject must outscore edge panoramic subject
        pin_det = DetectionEvent(
            camera_id="Cam_Cancelletto",
            timestamp=2000.0,
            class_label="person",
            confidence=0.92,
            bbox=BoundingBox2D(x_min=0.32, y_min=0.18, x_max=0.62, y_max=0.82),
        )
        pano_det = DetectionEvent(
            camera_id="Cam_Pano",
            timestamp=2000.0,
            class_label="person",
            confidence=0.90,
            bbox=BoundingBox2D(x_min=0.02, y_min=0.25, x_max=0.12, y_max=0.65),
        )
        tr = _make_track(7, camera_sources=["Cam_Cancelletto", "Cam_Pano"], ts=2000.0)
        ev = await mgr.on_detection_batch(
            [pano_det, pin_det],
            [tr],
            {0: 7, 1: 7},
            2000.0,
            zones_by_track={7: [("zone_cancelletto", "Cancelletto")]},
            alarm_state="Acceso",
        )
        assert ev is not None
        assert ev.replay_start_at == pytest.approx(1997.0)
        assert ev.importance == "alert"  # Unknown person + Acceso alarm

        ensured = await mgr.ensure_event_snapshot(ev.event_id)
        assert ensured is not None
        assert ensured.best_camera_id == "Cam_Cancelletto"
        assert ensured.cover_raw_relpath is not None
        assert ensured.cover_ann_relpath is not None

        # Biometric lock re-annotates cover and relaxes importance to routine
        bio_ev = await mgr.on_biometric_frame(
            track_id=7,
            camera_id="Cam_Cancelletto",
            timestamp=2002.0,
            identity="Nicola",
            identity_confidence=0.96,
            biometric_status="locked",
            biometric_event_id=42,
        )
        assert bio_ev is not None
        assert "Nicola" in bio_ev.summary_it

        # Admin HITL update
        hitl_ev = await mgr.on_hitl_review_updated(track_id=7, identity="Maria", biometric_event_id=42)
        assert hitl_ev is not None
        assert hitl_ev.reviewed is True
        assert "Maria" in hitl_ev.summary_it

        await mgr.close()
        repo.close()

    asyncio.run(_run())


def test_ha_bridge_and_send_notification_with_late_biometric_update(tmp_path: Path) -> None:
    ha_calls: list[tuple[str, str, dict[str, Any]]] = []

    def _mock_ha(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/services/"):
            parts = request.url.path.split("/")
            ha_calls.append((parts[3], parts[4], json.loads(request.content.decode("utf-8"))))
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    async def _run() -> None:
        cfg = replace(
            SpatialServerConfig.from_env(),
            ha_local_url="http://ha.local:8123",
            ha_token="backend_secret_token",
            public_app_url="https://casa.tailnet.ts.net",
        )

        repo = SQLiteWALTrackRepository(tmp_path / "notif.db")
        store = EventSnapshotStore(tmp_path)
        jpeg_bytes = _encode_test_jpeg()

        def _mock_go2rtc(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=jpeg_bytes, headers={"content-type": "image/jpeg"})

        mgr = SceneEventManager(
            repository=repo,
            snapshot_store=store,
            http_transport=httpx.MockTransport(_mock_go2rtc),
        )
        signer = SignedMediaTokenService(lambda: b"notif-hmac-key", default_ttl_s=600)
        bridge = HomeAssistantBridgeService(
            cfg,
            http_transport=httpx.MockTransport(_mock_ha),
        )
        bridge.parse_services_and_states(
            {
                "notify": {
                    "mobile_app_pixel_8a": {"name": "Pixel 8a"},
                    "lg_tv_cucina": {"name": "LG TV Cucina"},
                }
            },
            [
                {"entity_id": "media_player.nest_hub_cucina", "state": "idle", "attributes": {"friendly_name": "Nest Hub"}},
                {"entity_id": "media_player.lg_tv_cucina", "state": "on", "attributes": {"friendly_name": "LG TV"}},
                {"entity_id": "tts.google_translate_en_com", "state": "unknown", "attributes": {"friendly_name": "Google TTS"}},
                {"entity_id": "switch.cancelletto", "state": "off", "attributes": {"friendly_name": "Cancelletto"}},
            ],
        )
        disc = bridge.get_discovery_summary()
        kinds = {item["service"]: item["kind"] for item in disc["notify_services"]}
        assert kinds["notify.mobile_app_pixel_8a"] == "mobile_app"
        assert kinds["notify.lg_tv_cucina"] == "tv"

        broadcasts: list[dict[str, Any]] = []

        async def _on_bc(msg: dict[str, Any]) -> None:
            broadcasts.append(msg)

        engine = AutomationEngineService(
            config=cfg,
            repository=repo,
            broadcast_callback=_on_bc,
            scene_event_manager=mgr,
            ha_bridge=bridge,
            signed_media_service=signer,
        )
        bridge.on_notification_action = engine.on_ha_notification_action

        # Create 3-state alarm entity
        await engine.upsert_virtual_entity(
            VirtualEntityDefinition(
                entity_id="sh3d.allarme",
                name="Allarme Casa",
                domain="select",
                state="Silenzioso",
                options=["Spento", "Silenzioso", "Acceso"],
            )
        )
        await engine.upsert_zone(
            SpatialZoneDefinition(
                zone_id="zone_cancelletto",
                name="Cancelletto",
                geometry_type="polygon",
                vertices=[Point2D(x=0.0, z=0.0), Point2D(x=4.0, z=0.0), Point2D(x=4.0, z=4.0), Point2D(x=0.0, z=4.0)],
            )
        )
        await engine.upsert_rule(
            AutomationRuleDefinition(
                rule_id="rule_cancelletto_push",
                name="Notifica Cancelletto",
                cooldown_s=0.0,
                triggers=[
                    TriggerSpec(
                        type="zone_presence",
                        subject_filter=SubjectFilterSpec(classes=["person"], face_mode="any", biometric_grace_s=0.0),
                        params={"zone_id": "zone_cancelletto", "event": "enter", "min_dwell_s": 0.0},
                    )
                ],
                condition=ConditionSpec(
                    type="entity_state",
                    params={"entity_id": "sh3d.allarme", "operator": "in", "value": ["Silenzioso", "Acceso"]},
                ),
                actions=[
                    ActionSpec(
                        type="send_notification",
                        params={
                            "mobile_targets": ["notify.mobile_app_pixel_8a"],
                            "tv_targets": ["notify.lg_tv_cucina"],
                            "tts_targets": ["media_player.nest_hub_cucina"],
                            "tts_entity": "tts.google_translate_en_com",
                            "priority": "normal",
                            "image_mode": "annotated",
                            "message_mode": "auto_scene",
                            "location_label": "al cancelletto",
                            "tag": "notifica_cancelletto",
                            "update_on_biometrics": True,
                            "display_show_image": False,
                            "tv_only_when_on": True,
                            "actions": [
                                {"action": "SH3D_CALL_SERVICE:switch.turn_on:switch.cancelletto", "title": "Apri cancelletto"}
                            ],
                        },
                    )
                ],
            )
        )

        det = DetectionEvent(
            camera_id="Cam_Cancelletto",
            timestamp=3000.0,
            class_label="person",
            confidence=0.95,
            bbox=BoundingBox2D(x_min=0.3, y_min=0.2, x_max=0.55, y_max=0.85),
        )
        tr_unknown = _make_track(21, x=2.0, z=2.0, ts=3000.0)
        scene_ev = await mgr.on_detection_batch(
            [det], [tr_unknown], {0: 21}, 3000.0, zones_by_track={21: [("zone_cancelletto", "Cancelletto")]}, alarm_state="Silenzioso"
        )
        assert scene_ev is not None
        logs = await engine.on_tracks_updated([tr_unknown], 3000.0)
        assert len(logs) == 1

        # Verify mobile push, LG TV, and Nest Hub TTS were executed cleanly via backend bridge (zero duplicate WS browser calls)
        assert not any(m.get("type") == "automation_ha_service_call" for m in broadcasts)
        mobile_call = next(c for c in ha_calls if c[1] == "mobile_app_pixel_8a")
        assert mobile_call[2]["message"] == "C'è una persona al cancelletto."
        assert mobile_call[2]["data"]["tag"] == "notifica_cancelletto"
        assert mobile_call[2]["data"]["clickAction"] == f"https://casa.tailnet.ts.net/?event={scene_ev.event_id}"
        assert "/media/annotated.jpg?exp=" in mobile_call[2]["data"]["image"]
        assert mobile_call[2]["data"]["actions"][0]["action"] == "SH3D_CALL_SERVICE:switch.turn_on:switch.cancelletto"

        assert any(c[1] == "lg_tv_cucina" for c in ha_calls)
        assert any(c[0] == "tts" and c[1] == "speak" for c in ha_calls)

        # Late biometric recognition locks Nicola -> scene re-annotates + silent tag update sent
        ha_calls.clear()
        await mgr.on_biometric_frame(
            track_id=21,
            camera_id="Cam_Cancelletto",
            timestamp=3002.0,
            identity="Nicola",
            identity_confidence=0.97,
            biometric_status="locked",
        )
        await engine.on_biometric_update(
            {"track_id": 21, "identity": "Nicola", "biometric_locked": True},
            [_make_track(21, x=2.0, z=2.0, identity="Nicola", biometric_status="locked", ts=3002.0)],
            3002.0,
        )
        silent_updates = [c for c in ha_calls if c[1] == "mobile_app_pixel_8a"]
        assert len(silent_updates) == 1
        assert silent_updates[0][2]["message"] == "C'è Nicola al cancelletto."
        assert silent_updates[0][2]["data"]["alert_once"] is True
        assert silent_updates[0][2]["data"]["tag"] == "notifica_cancelletto"

        # Interactive notification action buttons
        ha_calls.clear()
        await bridge.handle_notification_action_event({"action": "SH3D_CALL_SERVICE:switch.turn_on:switch.cancelletto"})
        assert any(c == ("switch", "turn_on", {"entity_id": "switch.cancelletto"}) for c in ha_calls)

        await bridge.handle_notification_action_event({"action": "SH3D_ALARM_ACCESO"})
        assert engine.virtual_entities["sh3d.allarme"].state == "Acceso"
        await bridge.handle_notification_action_event({"action": "SH3D_ALARM_SPENTO"})
        assert engine.virtual_entities["sh3d.allarme"].state == "Spento"

        await bridge.stop()
        await mgr.close()
        repo.close()

    asyncio.run(_run())


def test_events_api_routes_and_hmac_media(tmp_path: Path) -> None:
    cfg = replace(
        SpatialServerConfig.from_env(),
        dev_mode=True,
        auth_required=False,
        biometrics_enabled=False,
        default_ingestion_mode="synthetic",
        sqlite_db_path=tmp_path / "api_events.db",
        data_dir=tmp_path,
    )
    app = create_app(cfg)

    with TestClient(app) as client:
        service = app.state.pipeline
        ev_id = "evt_1700000100000_cafe"
        frame = np.full((360, 640, 3), 65, dtype=np.uint8)
        raw_rel, ann_rel = service.event_snapshot_store.save_event_snapshots(
            ev_id,
            frame,
            [FrameBoxAnnotation(track_id=1, class_label="person", label="Nicola", category="known", bbox_norm=(0.2, 0.2, 0.5, 0.9))],
            camera_label="Ingresso",
            timestamp=1700000100.0,
        )
        service.repository.upsert_scene_event(
            SceneEventRecord(
                event_id=ev_id,
                status="closed",
                started_at=1700000100.0,
                ended_at=1700000112.0,
                duration_s=12.0,
                replay_start_at=1700000097.0,
                importance="routine",
                title="Nicola · Ingresso",
                summary_it="C'è Nicola all'ingresso.",
                best_camera_id="Cam_Ingresso",
                cameras=["Cam_Ingresso"],
                zones=["Ingresso"],
                zone_ids=["zone_ingresso"],
                track_ids=[1],
                subjects=[SceneSubjectRecord(track_id=1, class_label="person", identity="Nicola", biometric_status="locked")],
                cover_raw_relpath=raw_rel,
                cover_ann_relpath=ann_rel,
            ).model_dump()
        )

        res_list = client.get("/api/v1/events")
        assert res_list.status_code == 200
        by_id = {e["event_id"]: e for e in res_list.json()["events"]}
        assert ev_id in by_id
        assert by_id[ev_id]["annotated_url"] == f"/api/v1/events/{ev_id}/annotated.jpg"

        res_window = client.get("/api/v1/events?t_start=1700000090&t_end=1700000120")
        assert res_window.status_code == 200 and res_window.json()["count"] == 1

        res_detail = client.get(f"/api/v1/events/{ev_id}")
        assert res_detail.status_code == 200
        assert res_detail.json()["event"]["summary_it"] == "C'è Nicola all'ingresso."

        res_ann = client.get(f"/api/v1/events/{ev_id}/annotated.jpg")
        assert res_ann.status_code == 200 and res_ann.content.startswith(b"\xff\xd8")

        signed_url = service.signed_media_service.build_signed_url("", ev_id, "annotated")
        res_signed = client.get(signed_url)
        assert res_signed.status_code == 200 and res_signed.content.startswith(b"\xff\xd8")

        res_bad_sig = client.get(f"/api/v1/events/{ev_id}/media/annotated.jpg?exp=9999999999&sig=invalid")
        assert res_bad_sig.status_code == 403

        res_disc = client.get("/api/v1/automations/ha-discovery")
        assert res_disc.status_code == 200
        assert "notify_services" in res_disc.json()

        res_del = client.delete(f"/api/v1/events/{ev_id}")
        assert res_del.status_code == 200
        assert client.get(f"/api/v1/events/{ev_id}").status_code == 404


def test_parked_vehicle_reid_and_subject_consolidation(tmp_path: Path) -> None:
    """Stationary IR-flickering parked cars must keep 1 track_id across gaps and never spawn 25 fake vehicles or endless episodes."""
    tracker = Kalman3DMultiTracker(track_ttl_s=4.5, stationary_vehicle_reid_s=120.0)
    obs1 = TrackObservation3D(
        camera_id="Cam_Carraio",
        class_label="car",
        confidence=0.88,
        position=(5.0, 0.0, 8.0),
        timestamp=1000.0,
    )
    tracks1, _ = tracker.update_with_assignments([obs1], 1000.0)
    assert len(tracks1) == 1
    initial_tid = tracks1[0].track_id

    # Flicker gap > track_ttl_s (12s empty frames)
    empty_tracks, _ = tracker.update_with_assignments([], 1012.0)
    assert empty_tracks == []

    # Parked car reappears at essentially the same spot -> same track_id revived (no new track 2..25)
    obs2 = TrackObservation3D(
        camera_id="Cam_Carraio",
        class_label="car",
        confidence=0.86,
        position=(5.15, 0.0, 8.1),
        timestamp=1013.0,
    )
    tracks2, assign2 = tracker.update_with_assignments([obs2], 1013.0)
    assert len(tracks2) == 1
    assert tracks2[0].track_id == initial_tid
    assert assign2[0] == initial_tid

    # Narrator collapses duplicate subjects sharing normalized plate
    s1 = SceneSubjectRecord(track_id=10, class_label="car", plate="HD858PK", plate_whitelisted=True, plate_owner="Papà")
    s2 = SceneSubjectRecord(track_id=11, class_label="car", plate="HD858PK", plate_whitelisted=True, plate_owner="Papà")
    assert build_scene_sentence_it([s1, s2], camera_id="Cam_Carraio") == "Auto di Papà (HD858PK) al carraio."

    # SceneEventManager parked vehicle suppression & physical consolidation
    async def _run() -> None:
        repo = SQLiteWALTrackRepository(tmp_path / "parked.db")
        store = EventSnapshotStore(tmp_path)
        mgr = SceneEventManager(
            repository=repo,
            snapshot_store=store,
            inertia_s=8.0,
            stationary_vehicle_s=20.0,
            max_episode_duration_s=120.0,
        )
        car_det = DetectionEvent(
            camera_id="Cam_Carraio",
            timestamp=2000.0,
            class_label="car",
            confidence=0.90,
            bbox=BoundingBox2D(x_min=0.4, y_min=0.2, x_max=0.9, y_max=0.9),
        )
        parked_tr = _make_track(101, x=5.0, z=8.0, class_label="car", ts=2000.0).model_copy(
            update={"state": SpatialPoint3D(x=5.0, y=0.0, z=8.0, vx=0.0, vy=0.0, vz=0.0, camera_sources=["Cam_Carraio"])}
        )
        ev1 = await mgr.on_detection_batch([car_det], [parked_tr], {0: 101}, 2000.0)
        assert ev1 is not None and len(ev1.subjects) == 1

        # After 25s stationary, car becomes background-parked -> does NOT extend ev1.ended_at forever
        parked_tr_later = parked_tr.model_copy(update={"last_seen": 2025.0})
        car_det_later = car_det.model_copy(update={"timestamp": 2025.0})
        await mgr.on_detection_batch([car_det_later], [parked_tr_later], {0: 101}, 2025.0)
        assert mgr.get_active_event() is None  # closed due to inertia without foreground activity

        # Another detection of that already-parked car does NOT open a new episode
        ev2 = await mgr.on_detection_batch(
            [car_det.model_copy(update={"timestamp": 2040.0})],
            [parked_tr.model_copy(update={"track_id": 102, "last_seen": 2040.0})],
            {0: 102},
            2040.0,
        )
        assert ev2 is None

        # When a real foreground car enters & flickers across non-simultaneous track IDs, subjects stay consolidated to 1
        fg_det = car_det.model_copy(update={"timestamp": 2100.0})
        fg1 = _make_track(201, x=15.0, z=12.0, class_label="car", ts=2100.0)
        fg_ev = await mgr.on_detection_batch([fg_det], [fg1], {0: 201}, 2100.0)
        assert fg_ev is not None and len(fg_ev.subjects) == 1
        fg2 = _make_track(202, x=15.4, z=12.3, class_label="car", ts=2104.0)
        fg_ev2 = await mgr.on_detection_batch([fg_det.model_copy(update={"timestamp": 2104.0})], [fg2], {0: 202}, 2104.0)
        assert fg_ev2 is not None and len(fg_ev2.subjects) == 1
        assert 202 in fg_ev2.subjects[0].merged_track_ids

        await mgr.close()
        repo.close()

    asyncio.run(_run())


def test_person_cover_photo_strict_priority_and_alpr_protection(tmp_path: Path) -> None:
    """Frames with people must strictly outscore giant parked-car frames, upgrade over rate limits, and never be overwritten by ALPR."""
    big_car_det = DetectionEvent(
        camera_id="Cam_Carraio",
        timestamp=3000.0,
        class_label="car",
        confidence=0.95,
        bbox=BoundingBox2D(x_min=0.1, y_min=0.1, x_max=0.95, y_max=0.95),
    )
    small_person_det = DetectionEvent(
        camera_id="Cam_Ingresso",
        timestamp=3000.0,
        class_label="person",
        confidence=0.72,
        bbox=BoundingBox2D(x_min=0.42, y_min=0.35, x_max=0.52, y_max=0.75),
    )
    two_people_dets = [
        (small_person_det, 11),
        (
            DetectionEvent(
                camera_id="Cam_Pano",
                timestamp=3000.0,
                class_label="person",
                confidence=0.70,
                bbox=BoundingBox2D(x_min=0.20, y_min=0.30, x_max=0.30, y_max=0.70),
            ),
            12,
        ),
    ]
    car_score = SceneEventManager.compute_camera_frame_score("Cam_Carraio", False, [(big_car_det, 1)], biometric_quality=1.0, biometric_locked=True)
    one_person_score = SceneEventManager.compute_camera_frame_score("Cam_Ingresso", False, [(small_person_det, 11)])
    two_people_score = SceneEventManager.compute_camera_frame_score("Cam_Pano", True, two_people_dets)
    assert car_score <= 50.0
    assert 100.0 <= one_person_score < 200.0
    assert 200.0 <= two_people_score < 300.0
    assert two_people_score > one_person_score > car_score

    jpeg_car = _encode_test_jpeg(640, 360)
    img_person = np.full((360, 640, 3), 180, dtype=np.uint8)
    ok_p, buf_p = cv2.imencode(".jpg", img_person)
    assert ok_p
    jpeg_person = buf_p.tobytes()

    def _mock_go2rtc(request: httpx.Request) -> httpx.Response:
        src = request.url.params.get("src", "")
        if "ingresso" in src:
            return httpx.Response(200, content=jpeg_person, headers={"content-type": "image/jpeg"})
        return httpx.Response(200, content=jpeg_car, headers={"content-type": "image/jpeg"})

    async def _run() -> None:
        repo = SQLiteWALTrackRepository(tmp_path / "cover.db")
        store = EventSnapshotStore(tmp_path)
        mgr = SceneEventManager(
            repository=repo,
            snapshot_store=store,
            http_transport=httpx.MockTransport(_mock_go2rtc),
        )
        car_tr = _make_track(50, x=5.0, z=8.0, class_label="car", camera_sources=["Cam_Carraio"], ts=3000.0)
        ev = await mgr.on_detection_batch([big_car_det], [car_tr], {0: 50}, 3000.0, alarm_state="Acceso")
        assert ev is not None
        await asyncio.sleep(0.05)
        assert ev.best_camera_id == "Cam_Carraio"
        assert ev.best_frame_score <= 50.0

        # Immediate person arrival within <1.8s rate limit MUST still upgrade cover from car to person
        p_det = small_person_det.model_copy(update={"timestamp": 3000.5})
        p_tr = _make_track(51, x=2.0, z=3.0, class_label="person", camera_sources=["Cam_Ingresso"], ts=3000.5)
        ev2 = await mgr.on_detection_batch([big_car_det.model_copy(update={"timestamp": 3000.5}), p_det], [car_tr, p_tr], {0: 50, 1: 51}, 3000.5, alarm_state="Acceso")
        assert ev2 is not None
        await asyncio.sleep(0.05)
        assert ev2.best_camera_id == "Cam_Ingresso"
        assert ev2.best_frame_score >= 100.0
        person_raw_path = store.resolve_snapshot_path(ev2.event_id, "raw", known_relpath=ev2.cover_raw_relpath)
        person_raw_bytes = person_raw_path.read_bytes()

        # ALPR biometric frame on Cam_Carraio (e.g. locked plate with huge crop score) MUST NOT overwrite person cover
        alpr_frame = np.full((360, 640, 3), 25, dtype=np.uint8)
        bio_car_ev = await mgr.on_biometric_frame(
            track_id=50,
            camera_id="Cam_Carraio",
            timestamp=3001.2,
            full_frame_bgr=alpr_frame,
            subject_bbox_norm=(0.1, 0.1, 0.95, 0.95),
            quality_score=0.98,
            plate="HD858PK",
            plate_whitelisted=True,
            plate_owner="Papà",
            biometric_status="locked",
            biometric_locked=True,
        )
        assert bio_car_ev is not None
        assert bio_car_ev.best_camera_id == "Cam_Ingresso"
        assert bio_car_ev.best_frame_score >= 100.0
        assert person_raw_path.read_bytes() == person_raw_bytes

        # Also check ensure_event_snapshot upgrades a car cover if a person is now in the episode
        car_only_ev = SceneEventRecord(
            event_id="evt_3000000000000_upgr",
            status="active",
            started_at=3000.0,
            ended_at=3001.0,
            best_camera_id="Cam_Carraio",
            cameras=["Cam_Carraio", "Cam_Ingresso"],
            track_ids=[50, 51],
            subjects=[
                SceneSubjectRecord(track_id=50, class_label="car"),
                SceneSubjectRecord(track_id=51, class_label="person"),
            ],
            best_frame_score=8.0,
            cover_raw_relpath=ev2.cover_raw_relpath,
            cover_ann_relpath=ev2.cover_ann_relpath,
        )
        repo.upsert_scene_event(car_only_ev.model_dump())
        mgr._active_event = car_only_ev
        upgraded = await mgr.ensure_event_snapshot(car_only_ev.event_id)
        assert upgraded is not None
        assert upgraded.best_camera_id == "Cam_Ingresso"
        assert upgraded.best_frame_score >= 100.0

        await mgr.close()
        repo.close()

    asyncio.run(_run())


def test_alarm_three_states_and_no_forced_escalation(tmp_path: Path) -> None:
    """Enforce sh3d.allarme 3-state semantics: Acceso+person->alert, Silenzioso+person->silent_alert, vehicle-only or Spento->not alert/silent_alert."""
    async def _run() -> None:
        repo = SQLiteWALTrackRepository(tmp_path / "alarm3.db")
        store = EventSnapshotStore(tmp_path)
        mgr = SceneEventManager(repository=repo, snapshot_store=store, inertia_s=10.0)

        car_det = DetectionEvent(camera_id="Cam_Carraio", timestamp=4000.0, class_label="car", confidence=0.9, bbox=BoundingBox2D(x_min=0.2, y_min=0.2, x_max=0.6, y_max=0.7))
        car_tr = _make_track(1, class_label="car", ts=4000.0)

        # 1. Vehicle only even with Acceso must NOT be alert or silent_alert
        ev_car_armed = await mgr.on_detection_batch([car_det], [car_tr], {0: 1}, 4000.0, alarm_state="Acceso")
        assert ev_car_armed is not None and ev_car_armed.importance == "notable"
        # Automation escalation cannot force 'alert' without person + Acceso
        after_auto = await mgr.mark_automation_triggered(ev_car_armed.event_id, "r1", escalate_importance="alert")
        assert after_auto is not None and after_auto.importance == "notable"

        # Close episode and test Silenzioso + person (including known person!) -> silent_alert
        await mgr.tick(4020.0)
        p_det = DetectionEvent(camera_id="Cam_Ingresso", timestamp=4100.0, class_label="person", confidence=0.92, bbox=BoundingBox2D(x_min=0.3, y_min=0.2, x_max=0.5, y_max=0.8))
        p_tr = _make_track(2, class_label="person", ts=4100.0)
        ev_silent = await mgr.on_detection_batch([p_det], [p_tr], {0: 2}, 4100.0, alarm_state="Silenzioso")
        assert ev_silent is not None and ev_silent.importance == "silent_alert"
        ev_silent_known = await mgr.on_biometric_frame(
            track_id=2, camera_id="Cam_Ingresso", timestamp=4101.0, identity="Nicola", identity_confidence=0.95, biometric_status="locked"
        )
        assert ev_silent_known is not None and ev_silent_known.importance == "silent_alert"
        await mgr.mark_automation_triggered(ev_silent.event_id, "r_silent", escalate_importance="alert")
        assert mgr.get_active_event().importance == "silent_alert"  # stays silent_alert under Silenzioso

        # Close episode and test Acceso + person -> alert
        await mgr.tick(4120.0)
        p_tr3 = _make_track(3, class_label="person", ts=4200.0)
        ev_armed = await mgr.on_detection_batch([p_det.model_copy(update={"timestamp": 4200.0})], [p_tr3], {0: 3}, 4200.0, alarm_state="Acceso")
        assert ev_armed is not None and ev_armed.importance == "alert"

        # Close and test Spento + unknown person -> notable (never alert/silent_alert)
        await mgr.tick(4220.0)
        p_tr4 = _make_track(4, class_label="person", ts=4300.0)
        ev_off = await mgr.on_detection_batch([p_det.model_copy(update={"timestamp": 4300.0})], [p_tr4], {0: 4}, 4300.0, alarm_state="Spento")
        assert ev_off is not None and ev_off.importance == "notable"

        # Repository comma-separated query returns both alert & silent_alert
        rows_alarms = repo.query_scene_events(importance="alert,silent_alert")
        ids_alarms = {r["event_id"] for r in rows_alarms}
        assert ev_silent.event_id in ids_alarms
        assert ev_armed.event_id in ids_alarms
        assert ev_car_armed.event_id not in ids_alarms
        assert ev_off.event_id not in ids_alarms

        await mgr.close()
        repo.close()

    asyncio.run(_run())
