from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]


def _isolated_subprocess_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{REPO_ROOT}{os.pathsep}{existing_pp}" if existing_pp else str(REPO_ROOT)
    env.update(
        {
            "SPATIAL_SERVER_HOST": "127.0.0.1",
            "SPATIAL_AUTH_REQUIRED": "true",
            "SPATIAL_SESSION_SECRET": "e2e-subprocess-session-secret-0123456789abcdef",
            "SPATIAL_ALLOWED_ORIGINS": "https://smarthome.tailnet.ts.net,http://127.0.0.1:8080",
            "VITE_HA_TOKEN": "",
            "HA_TOKEN": "",
            "VITE_HA_PUBLIC_URL": "",
            "VITE_HA_TAILSCALE_URL": "",
            "VITE_HA_REMOTE_URL": "",
            "VITE_HA_LOCAL_URL": "",
            "VITE_HA_URL": "",
            "CV_INGESTION_MODE": "synthetic",
            "FACE_RECOGNITION_WEBHOOK_URL": "",
        }
    )
    if overrides:
        env.update(overrides)
    return env


@pytest.mark.tier1
def test_f5_t1_01_test_security_auth_file_exists_and_collects(repo_root: Path) -> None:
    target = repo_root / "spatial_server" / "tests" / "test_security_auth.py"
    assert target.is_file(), f"Missing {target}"

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(target)],
        cwd=repo_root,
        env=_isolated_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"Collect failed:\n{proc.stdout}\n{proc.stderr}"
    test_lines = [
        line for line in proc.stdout.splitlines() if "::test_" in line
    ]
    assert len(test_lines) >= 1


@pytest.mark.tier1
def test_f5_t1_02_test_security_auth_suite_passes_in_subprocess(
    repo_root: Path,
) -> None:
    target = repo_root / "spatial_server" / "tests" / "test_security_auth.py"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(target)],
        cwd=repo_root,
        env=_isolated_subprocess_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"test_security_auth.py failed:\n{proc.stdout}\n{proc.stderr}"


@pytest.mark.tier1
def test_f5_t1_03_auth_required_false_preserves_pipeline_compat_on_rest(
    isolated_app_factory,
) -> None:
    app = isolated_app_factory(auth_required=False)
    with TestClient(app) as tc:
        assert tc.get("/api/v1/status").status_code == 200
        assert (
            tc.post(
                "/api/v1/ingestion/mode", json={"mode": "synthetic"}
            ).status_code
            == 200
        )
        assert (
            tc.post(
                "/api/v1/detections",
                json={
                    "camera_id": "Cam_Carraio",
                    "timestamp": time.time(),
                    "class_label": "person",
                    "confidence": 0.9,
                    "bbox": {"x_min": 0.4, "y_min": 0.5, "x_max": 0.5, "y_max": 0.8},
                },
            ).status_code
            == 200
        )


@pytest.mark.tier1
def test_f5_t1_04_auth_required_false_preserves_pipeline_compat_on_ws(
    isolated_app_factory,
) -> None:
    import json

    app = isolated_app_factory(auth_required=False)
    with TestClient(app) as tc:
        with tc.websocket_connect("/ws/spatial") as ws:
            hello = json.loads(ws.receive_text())
            assert hello["type"] == "server_status"
            ws.send_text("ping")
            assert ws.receive_text() == "pong"


@pytest.mark.tier1
def test_f5_t1_05_verify_pipeline_fastapi_rest_and_ws_test_passes() -> None:
    from spatial_server.tests.verify_pipeline import test_fastapi_rest_and_websocket

    test_fastapi_rest_and_websocket()


@pytest.mark.tier2
def test_f5_t2_01_auth_required_true_cannot_be_bypassed_by_dev_headers(
    client: TestClient,
) -> None:
    spoofed = {
        "X-SH3D-User": "admin",
        "X-SH3D-Admin": "true",
        "X-Forwarded-User": "admin",
    }
    assert client.get("/api/v1/status", headers=spoofed).status_code == 401
    assert (
        client.post(
            "/api/v1/ingestion/mode", json={"mode": "synthetic"}, headers=spoofed
        ).status_code
        == 401
    )


@pytest.mark.tier2
def test_f5_t2_02_auth_required_false_still_rejects_malformed_payloads(
    isolated_app_factory,
) -> None:
    app = isolated_app_factory(auth_required=False)
    with TestClient(app) as tc:
        bad_det = tc.post("/api/v1/detections", json={"camera_id": "Cam_Carraio"})
        assert bad_det.status_code == 422

        missing_cam = tc.get("/api/v1/calibration/Cam_DoesNotExist")
        assert missing_cam.status_code == 404


@pytest.mark.tier2
def test_f5_t2_03_test_security_auth_does_not_require_live_ha_or_env_file(
    repo_root: Path,
) -> None:
    target = repo_root / "spatial_server" / "tests" / "test_security_auth.py"
    env = _isolated_subprocess_env(
        {
            "VITE_HA_TOKEN": "",
            "HA_TOKEN": "",
            "VITE_HA_LOCAL_URL": "http://127.0.0.1:1",
            "VITE_HA_TAILSCALE_URL": "",
            "VITE_HA_PUBLIC_URL": "",
        }
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(target)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"Offline test_security_auth failed:\n{proc.stdout}\n{proc.stderr}"


@pytest.mark.tier2
def test_f5_t2_04_verify_pipeline_does_not_mutate_repo_calibrations(
    repo_root: Path,
) -> None:
    from spatial_server.tests.verify_pipeline import test_fastapi_rest_and_websocket

    calib_file = repo_root / "spatial_server" / "data" / "camera_calibrations.json"
    existed_before = calib_file.exists()
    content_before = calib_file.read_bytes() if existed_before else None

    test_fastapi_rest_and_websocket()

    existed_after = calib_file.exists()
    content_after = calib_file.read_bytes() if existed_after else None
    assert existed_after == existed_before
    assert content_after == content_before


@pytest.mark.tier2
def test_f5_t2_05_default_config_enforces_auth_required_true(
    monkeypatch, isolated_app_factory
) -> None:
    from spatial_server.config import SpatialServerConfig

    monkeypatch.delenv("SPATIAL_AUTH_REQUIRED", raising=False)
    default_cfg = SpatialServerConfig.from_env()
    assert default_cfg.auth_required is True

    app = isolated_app_factory(auth_required=default_cfg.auth_required)
    with TestClient(app) as tc:
        assert tc.get("/api/v1/status").status_code == 401
