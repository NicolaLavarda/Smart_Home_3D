from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from spatial_server.config import SpatialServerConfig
from spatial_server.domain.models import BoundingBox2D, DetectionEvent
from spatial_server.ingestion.openvino_rtsp_source import OpenVINORtspDetectionSource
from spatial_server.integrations.ha_bridge import HomeAssistantBridgeService
from spatial_server.integrations.mqtt_bridge import HomeAssistantMqttBridge
from spatial_server.main import create_app
from spatial_server.persistence.repository import SQLiteWALTrackRepository
from spatial_server.telemetry import GpuSample, TelemetryMetricsService
from spatial_server.telemetry.gpu_probe import IGpuMetricsProbe


class _FakeGpuProbe(IGpuMetricsProbe):
    def __init__(self, pct: float = 34.5, mem_mb: float = 412.0) -> None:
        self.pct = pct
        self.mem_mb = mem_mb

    def sample(self) -> GpuSample:
        return GpuSample(
            gpu_percent=self.pct,
            gpu_memory_mb=self.mem_mb,
            backend_name="fake_gpu",
        )


def test_openvino_source_rolling_fps_window() -> None:
    from collections import deque

    dq: deque[float] = deque(maxlen=64)
    now = 100.0
    for i in range(6):
        dq.append(now - 5.0 + i * 1.0)
    fps = OpenVINORtspDetectionSource._compute_window_fps(dq, now_mono=now)
    assert fps == pytest.approx(1.0, abs=0.05)

    dq_fast: deque[float] = deque(maxlen=64)
    for i in range(13):
        dq_fast.append(now - 3.0 + i * 0.25)
    fps_fast = OpenVINORtspDetectionSource._compute_window_fps(dq_fast, now_mono=now)
    assert fps_fast == pytest.approx(4.0, abs=0.1)

    # Stalled stream decays to 0 after window expires
    assert OpenVINORtspDetectionSource._compute_window_fps(dq_fast, now_mono=now + 10.0) == 0.0


def test_sqlite_system_metrics_persistence_downsampling_and_pruning(tmp_path: Path) -> None:
    repo = SQLiteWALTrackRepository(tmp_path / "metrics.db")
    base_ts = 1_700_000_000.0
    # Insert 2 days worth of 1-minute samples = 2,880 rows
    for i in range(600):
        ts = base_ts + i * 60.0
        repo.append_system_metrics_sample(
            {
                "t": ts,
                "cpu_pct": 20.0 + (i % 15),
                "gpu_pct": 15.0 + (i % 10),
                "gpu_mem_mb": 256.0,
                "ram_pct": 62.0,
                "ram_used_mb": 4900.0,
                "proc_cpu_pct": 6.5,
                "proc_rss_mb": 280.0,
                "cv_fps_total": 4.8 + (i % 3) * 0.5,
                "cv_fps_target": 7.0,
                "cv_fps_person": 3.0 if (i % 10 == 0) else 0.0,
                "cv_fps_vehicle": 1.5 if (i % 10 == 1) else 0.0,
                "cv_fps_idle": 4.8,
                "cv_read_fps": 60.0,
                "cv_infer_ms": 42.0,
                "cv_infer_ms_max": 55.0 + (i % 5),
                "person_det_fps": 1.2,
                "vehicle_det_fps": 0.4,
                "animal_det_fps": 0.0,
                "bio_fps": 0.3,
                "bio_face_ms": 38.0,
                "bio_alpr_ms": 49.0,
                "bio_queue": 0,
                "tracks_total": 2,
                "tracks_person": 1,
                "tracks_vehicle": 1,
                "tracks_animal": 0,
                "nvr_ram_mb": 0.0,
                "ws_clients": 1,
                "cameras": {"Cam_Carraio": {"actual_fps": 1.2}},
            }
        )

    assert repo.get_system_metrics_count() == 600
    rows_ds = repo.query_system_metrics(base_ts, base_ts + 600 * 60.0, max_points=120)
    assert 80 <= len(rows_ds) <= 125
    assert all("cpu_pct" in r and "cv_fps_total" in r and "gpu_pct" in r for r in rows_ds)

    deleted = repo.prune_system_metrics_older_than(base_ts + 300 * 60.0)
    assert deleted == 300
    assert repo.get_system_metrics_count() == 300
    repo.close()


def test_telemetry_service_entities_and_ha_mqtt_publishing(tmp_path: Path) -> None:
    repo = SQLiteWALTrackRepository(tmp_path / "svc_metrics.db")
    counters = {
        "person_detections": 0,
        "vehicle_detections": 0,
        "animal_detections": 0,
        "biometrics_evaluated": 0,
        "batches_processed": 0,
    }

    def _state_provider():
        return {
            "ingestion_mode": "openvino",
            "camera_stats": [
                {
                    "camera_id": "Cam_Carraio",
                    "actual_infer_fps": 4.0,
                    "actual_read_fps": 15.0,
                    "target_fps": 4.0,
                    "infer_ms_ema": 44.0,
                    "rtsp_connected": True,
                    "backend": "openvino_ir(GPU)",
                },
                {
                    "camera_id": "Cam_Portico",
                    "actual_infer_fps": 1.2,
                    "actual_read_fps": 15.0,
                    "target_fps": 1.2,
                    "infer_ms_ema": 36.0,
                    "rtsp_connected": True,
                    "backend": "openvino_ir(GPU)",
                },
            ],
            "fps_snapshot": {
                "total_allocated_fps": 5.2,
                "cameras": {
                    "Cam_Carraio": {"tier": "person", "target_fps": 4.0},
                    "Cam_Portico": {"tier": "idle", "target_fps": 1.2},
                },
            },
            "active_tracks_count": 2,
            "tracks_by_category": {"person": 1, "vehicle": 1, "animal": 0},
            "biometrics_diag": {
                "queue_depth": 1,
                "face_latency": {"mean_ms": 41.5},
                "alpr_latency": {"mean_ms": 58.0},
            },
            "nvr_ram_buffer_mb": 24.5,
            "ws_clients_count": 2,
            "counters": counters,
        }

    svc = TelemetryMetricsService(
        sample_interval_s=1.0,
        persist_interval_s=5.0,
        ram_window_s=600.0,
        retention_days=7,
        gpu_probe=_FakeGpuProbe(pct=28.4, mem_mb=380.0),
        state_provider=_state_provider,
        repository=repo,
    )

    snap = svc.collect_sample_once()
    assert snap.gpu_percent == pytest.approx(28.4)
    assert snap.cv_fps_total == pytest.approx(5.2, abs=0.05)
    assert snap.cv_fps_person == pytest.approx(4.0, abs=0.05)
    assert snap.cv_fps_idle == pytest.approx(1.2, abs=0.05)
    assert snap.openvino_backend == "openvino_ir(GPU)"

    entities = svc.build_entities(snap)
    by_id = {e["entity_id"]: e for e in entities}
    assert "sensor.sh3d_pc_cpu" in by_id
    assert by_id["sensor.sh3d_pc_gpu"]["state"] == pytest.approx(28.4)
    assert by_id["sensor.sh3d_cv_fps_totale"]["state"] == pytest.approx(5.2)
    assert by_id["sensor.sh3d_cv_fps_persone"]["state"] == pytest.approx(4.0)
    assert by_id["sensor.sh3d_cv_inferenza_ms"]["state"] == pytest.approx(40.0)
    assert by_id["sensor.sh3d_tracce_attive"]["state"] == 2

    async def _test_bridges() -> None:
        # Flush rollup into SQLite
        row_id = await svc.flush_rollup_to_db(force=True)
        assert row_id > 0

        # MQTT Discovery publishing test
        published_msgs: list[tuple[str, str]] = []

        class _FakeMqttClient:
            async def publish(self, topic, payload=None, qos=0, retain=False):
                published_msgs.append((str(topic), str(payload)))

        cfg = SpatialServerConfig.from_env()
        mqtt_bridge = HomeAssistantMqttBridge(cfg)
        mqtt_bridge._client = _FakeMqttClient()
        mqtt_bridge._connected = True
        cnt_mqtt = await mqtt_bridge.publish_telemetry_entities(entities)
        assert cnt_mqtt == len(entities)
        assert any(t.startswith("homeassistant/sensor/smart_home_3d/pc_gpu/config") for t, _ in published_msgs)
        assert any(t == "sh3d/telemetry/cv_fps_totale/state" and p == "5.2" for t, p in published_msgs)

        # HA REST Bridge publishing test
        ha_posts: list[tuple[str, dict]] = []

        def _ha_handler(request: httpx.Request) -> httpx.Response:
            ha_posts.append((request.url.path, json.loads(request.content.decode("utf-8"))))
            return httpx.Response(200, json={"entity_id": request.url.path.split("/")[-1]})

        cfg_ha = replace(cfg, ha_local_url="http://127.0.0.1:8123", ha_token="test-ha-tok")
        ha_bridge = HomeAssistantBridgeService(cfg_ha, http_transport=httpx.MockTransport(_ha_handler))
        ha_bridge._connected = True
        ha_bridge._active_base_url = "http://127.0.0.1:8123"
        cnt_ha = await ha_bridge.publish_sensor_states(entities)
        assert cnt_ha == len(entities)
        assert any(path == "/api/states/sensor.sh3d_pc_gpu" and body["state"] == "28.4" for path, body in ha_posts)
        await ha_bridge.stop()

    asyncio.run(_test_bridges())
    repo.close()


def test_metrics_rest_endpoints_auth_and_history(tmp_path: Path) -> None:
    base_cfg = SpatialServerConfig.from_env()
    authed_cfg = replace(
        base_cfg,
        dev_mode=False,
        auth_required=True,
        biometrics_enabled=False,
        default_ingestion_mode="synthetic",
        sqlite_db_path=tmp_path / "metrics_auth.db",
        data_dir=tmp_path,
    )
    app_auth = create_app(authed_cfg)
    with TestClient(app_auth) as client_auth:
        assert client_auth.get("/api/v1/metrics/entities").status_code == 401
        assert client_auth.get("/api/v1/metrics/history").status_code == 401

    open_cfg = replace(
        authed_cfg,
        auth_required=False,
    )
    app = create_app(open_cfg)
    with TestClient(app) as client:
        # Inject a detection so counters & tracks increment cleanly
        det_res = client.post(
            "/api/v1/detections",
            json=[
                {
                    "camera_id": "Cam_Carraio",
                    "timestamp": time.time(),
                    "class_label": "person",
                    "confidence": 0.92,
                    "bbox": {"x_min": 0.4, "y_min": 0.3, "x_max": 0.5, "y_max": 0.75},
                }
            ],
        )
        assert det_res.status_code == 200

        ent_res = client.get("/api/v1/metrics/entities")
        assert ent_res.status_code == 200
        ent_body = ent_res.json()
        assert ent_body["status"] == "ok"
        eids = {e["entity_id"] for e in ent_body["entities"]}
        assert {"sensor.sh3d_pc_cpu", "sensor.sh3d_pc_gpu", "sensor.sh3d_cv_fps_totale", "sensor.sh3d_cv_fps_persone"} <= eids

        hist_res = client.get("/api/v1/metrics/history?window_s=300&max_points=120")
        assert hist_res.status_code == 200
        hist_body = hist_res.json()
        assert hist_body["status"] == "ok"
        assert len(hist_body["series"]) >= 1
        assert "cpu_pct" in hist_body["series"][-1]
        assert "cv_fps_total" in hist_body["series"][-1]

        # Automation virtual_entities endpoint remains unaffected by telemetry sensors
        ve_res = client.get("/api/v1/automations/virtual-entities")
        assert ve_res.status_code == 200
        assert ve_res.json()["virtual_entities"] == []

        status_res = client.get("/api/v1/status")
        assert status_res.status_code == 200
        assert "system_metrics" in status_res.json()
