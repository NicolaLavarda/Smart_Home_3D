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
