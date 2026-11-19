from __future__ import annotations

import asyncio
import json
import socket
import tempfile
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pytest
import websockets
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from spatial_server.config import REPO_ROOT, SpatialServerConfig
from spatial_server.domain.models import BoundingBox2D, DetectionEvent, PnPCorrespondence
from spatial_server.main import create_app
from spatial_server.security import (
    HAUserPrincipal,
    HomeAssistantAuthVerifier,
    HomeAssistantUnavailableError,
    InvalidAuthTokenError,
    InvalidSessionCookieError,
)


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _make_test_config(tmp_dir: Path, **overrides: Any) -> SpatialServerConfig:
    defaults: dict[str, Any] = dict(
        host="127.0.0.1",
        port=8765,
        manifest_path=REPO_ROOT / "public" / "models" / "scene_manifest.json",
        glb_path=REPO_ROOT / "public" / "models" / "house_optimized.glb",
        sqlite_db_path=tmp_dir / "security_test.db",
        calibration_override_path=tmp_dir / "calibs.json",
        data_dir=tmp_dir,
        models_dir=tmp_dir,
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
        ha_local_url="",
        ha_tailscale_url="",
        ha_public_url="",
        ha_token="",
        auth_required=True,
        auth_cache_ttl_s=120.0,
        session_secret_key="test-secret-key-32bytes-minimum-ok",
        allowed_origins=("https://app.tailnet.ts.net", "http://localhost:5173"),
    )
    defaults.update(overrides)
    return SpatialServerConfig(**defaults)


def _patch_verifier_tokens(app: FastAPI, token_map: dict[str, HAUserPrincipal]) -> None:
    async def _fake_verify_token(token: str) -> HAUserPrincipal:
        clean = (token or "").strip()
        if clean not in token_map:
            raise InvalidAuthTokenError("Mock HA rejected Bearer token")
        src = token_map[clean]
        now = time.time()
        return HAUserPrincipal(
            user_id=src.user_id,
            name=src.name,
            is_admin=src.is_admin,
            is_owner=src.is_owner,
            authenticated_at=now,
            expires_at=now + 120.0,
        )

    app.state.auth_verifier.verify_token = _fake_verify_token  # type: ignore[method-assign]


@asynccontextmanager
async def _mock_ha_ws_server(user_map: dict[str, dict[str, Any]]):
    state = {"calls": 0}

    async def _handler(websocket: Any) -> None:
        state["calls"] += 1
        await websocket.send(json.dumps({"type": "auth_required", "ha_version": "2026.1.0"}))
        auth_msg = json.loads(await websocket.recv())
        token = auth_msg.get("access_token", "")
        if token not in user_map:
            await websocket.send(json.dumps({"type": "auth_invalid", "message": "Invalid access token"}))
            return
        await websocket.send(json.dumps({"type": "auth_ok", "ha_version": "2026.1.0"}))
        cmd = json.loads(await websocket.recv())
        if cmd.get("type") == "auth/current_user":
            await websocket.send(
                json.dumps(
                    {
                        "id": cmd["id"],
                        "type": "result",
                        "success": True,
                        "result": user_map[token],
                    }
                )
            )

    async with websockets.serve(_handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}", state


@contextmanager
def _mock_ha_http_server(valid_tokens: set[str], snapshot_bytes: bytes = b"\xff\xd8\xff\xe0MOCKJPEG") -> Iterator[tuple[str, dict[str, Any]]]:
    state: dict[str, Any] = {"api_calls": 0, "snapshot_calls": 0, "last_auth": None, "last_path": None}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            auth = self.headers.get("Authorization", "")
            state["last_auth"] = auth
            state["last_path"] = self.path
            expected_tokens = {f"Bearer {t}" for t in valid_tokens}

            if self.path == "/api/":
                state["api_calls"] += 1
                if auth in expected_tokens:
                    body = json.dumps({"message": "API running."}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(401)
                    self.end_headers()
                return

            if self.path.startswith("/api/camera_proxy/"):
                state["snapshot_calls"] += 1
                if auth in expected_tokens:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(snapshot_bytes)))
                    self.end_headers()
                    self.wfile.write(snapshot_bytes)
                else:
                    self.send_response(401)
                    self.end_headers()
                return

            self.send_response(404)
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def _valid_solve_pnp_payload(app: FastAPI) -> dict[str, Any]:
    pinhole = app.state.pipeline.optical_models["Cam_Carraio"]
    # Ensure camera points toward Driveway_Gravel (+Z) in test if needed, or pick points in front of current pose
    T_gl = np.array(pinhole.to_metadata_dict()["matrix_world_gl"], dtype=np.float64).reshape((4, 4))
    cam_pos = T_gl[:3, 3]
    forward_gl = -T_gl[:3, 2]
    right_gl = T_gl[:3, 0]
    up_gl = T_gl[:3, 1]

    offsets = [
        (0.0, 0.0, 6.0),
        (1.2, -0.4, 7.5),
        (-1.4, -0.2, 8.0),
        (0.8, 0.5, 9.0),
        (-0.9, 0.6, 6.5),
        (0.3, -0.6, 10.0),
    ]
    corrs = []
    for rx, uy, fz in offsets:
        pt = cam_pos + rx * right_gl + uy * up_gl + fz * forward_gl
        pt_tuple = (float(pt[0]), float(pt[1]), float(pt[2]))
        uv = pinhole.world_point_to_pixel(pt_tuple)
        assert uv is not None
        corrs.append(PnPCorrespondence(world_point=pt_tuple, pixel_uv=uv).model_dump())
    return {"camera_id": "Cam_Carraio", "correspondences": corrs}


def _valid_detection_payload() -> dict[str, Any]:
    return DetectionEvent(
        camera_id="Cam_Carraio",
        timestamp=time.time(),
        class_label="person",
        confidence=0.92,
        bbox=BoundingBox2D(x_min=0.45, y_min=0.55, x_max=0.55, y_max=0.80),
        sub_label="Nicola",
        face_confidence=0.90,
    ).model_dump()


def test_config_from_env_defaults_and_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "SPATIAL_SERVER_HOST",
        "SPATIAL_AUTH_REQUIRED",
        "SPATIAL_AUTH_CACHE_TTL_S",
        "SPATIAL_SESSION_SECRET",
        "SPATIAL_ALLOWED_ORIGINS",
        "VITE_HA_PUBLIC_URL",
        "HA_PUBLIC_URL",
        "VITE_HA_TOKEN",
        "HA_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)

    cfg = SpatialServerConfig.from_env()
    assert cfg.host == "127.0.0.1"
    assert cfg.auth_required is True
    assert cfg.auth_cache_ttl_s == 120.0
    assert "*" not in cfg.allowed_origins
    assert "http://localhost:5173" in cfg.allowed_origins

    monkeypatch.setenv("VITE_HA_PUBLIC_URL", "https://pc-fisso.tailnet.ts.net:8443/")
    cfg_pub = SpatialServerConfig.from_env()
    assert cfg_pub.ha_public_url == "https://pc-fisso.tailnet.ts.net:8443"
    assert "https://pc-fisso.tailnet.ts.net:8443" in cfg_pub.allowed_origins
    assert "https://pc-fisso.tailnet.ts.net" in cfg_pub.allowed_origins

    monkeypatch.setenv("SPATIAL_AUTH_REQUIRED", "false")
    monkeypatch.setenv("SPATIAL_AUTH_CACHE_TTL_S", "45")
    monkeypatch.setenv("SPATIAL_SESSION_SECRET", "explicit-secret-key")
    monkeypatch.setenv("SPATIAL_ALLOWED_ORIGINS", "https://a.ts.net, *, http://localhost:5173")
    cfg_custom = SpatialServerConfig.from_env()
    assert cfg_custom.auth_required is False
    assert cfg_custom.auth_cache_ttl_s == 45.0
    assert cfg_custom.session_secret_key == "explicit-secret-key"
    assert cfg_custom.allowed_origins == ("https://a.ts.net", "http://localhost:5173")
    assert "*" not in cfg_custom.allowed_origins

    monkeypatch.setenv("SPATIAL_ALLOWED_ORIGINS", "*")
    cfg_star = SpatialServerConfig.from_env()
    assert "*" not in cfg_star.allowed_origins
    assert len(cfg_star.allowed_origins) >= 1

    monkeypatch.setenv("SPATIAL_AUTH_REQUIRED", "not-a-bool")
    with pytest.raises(ValueError):
        SpatialServerConfig.from_env()


def test_verifier_ws_current_user_and_sha256_cache() -> None:
    async def _run() -> None:
        users = {
            "tok-admin": {"id": "usr-admin-1", "name": "Nicola", "is_admin": True, "is_owner": True},
        }
        with _mock_ha_http_server({"tok-admin"}) as (http_url, http_state):
            async with _mock_ha_ws_server(users) as (ws_base_url, ws_state):
                verifier = HomeAssistantAuthVerifier(
                    ha_local_url=ws_base_url,
                    ha_tailscale_url=http_url,
                    cache_ttl_s=0.08,
                    session_secret_key="test-secret",
                )
                principal = await verifier.verify_token("tok-admin")
                assert principal.user_id == "usr-admin-1"
                assert principal.name == "Nicola"
                assert principal.is_admin is True
                assert principal.is_owner is True
                assert principal.is_privileged is True
                assert ws_state["calls"] == 1

                # Cached hit within TTL; cache key must be SHA-256, never raw token
                assert "tok-admin" not in verifier._cache
                assert len(verifier._cache) == 1
                cached_key = next(iter(verifier._cache))
                assert len(cached_key) == 64

                principal2 = await verifier.verify_token("tok-admin")
                assert principal2.user_id == "usr-admin-1"
                assert ws_state["calls"] == 1

                # TTL expiration triggers fresh WS lookup
                await asyncio.sleep(0.12)
                principal3 = await verifier.verify_token("tok-admin")
                assert principal3.user_id == "usr-admin-1"
                assert ws_state["calls"] == 2

                # Invalid token rejected by WS auth_invalid must NOT fall back to REST
                with pytest.raises(InvalidAuthTokenError):
                    await verifier.verify_token("tok-bad")
                assert http_state["api_calls"] == 0

    asyncio.run(_run())


def test_verifier_rest_fallback_fails_closed() -> None:
    async def _run() -> None:
        dead_port = _get_free_port()
        with _mock_ha_http_server({"tok-rest-valid"}) as (http_url, http_state):
            verifier = HomeAssistantAuthVerifier(
                ha_local_url=f"http://127.0.0.1:{dead_port}",
                ha_tailscale_url=http_url,
                cache_ttl_s=60.0,
                session_secret_key="test-secret",
                request_timeout_s=0.6,
            )
            principal = await verifier.verify_token("tok-rest-valid")
            assert principal.user_id.startswith("ha_rest_")
            assert principal.is_admin is False
            assert principal.is_owner is False
            assert principal.is_privileged is False
            assert principal.expires_at > principal.authenticated_at
            assert http_state["api_calls"] == 1

            with pytest.raises(InvalidAuthTokenError):
                await verifier.verify_token("tok-rest-invalid")

            unavailable_verifier = HomeAssistantAuthVerifier(
                ha_local_url=f"http://127.0.0.1:{dead_port}",
                request_timeout_s=0.4,
            )
            with pytest.raises(HomeAssistantUnavailableError):
                await unavailable_verifier.verify_token("tok-any")

    asyncio.run(_run())


def test_session_cookie_tampering_and_expiry() -> None:
    verifier = HomeAssistantAuthVerifier(session_secret_key="secret-alpha")
    other_verifier = HomeAssistantAuthVerifier(session_secret_key="secret-beta")
    principal = HAUserPrincipal(
        user_id="usr-1",
        name="Nicola",
        is_admin=True,
        is_owner=False,
        authenticated_at=time.time(),
        expires_at=time.time() + 120.0,
    )

    cookie_val, _ = verifier.create_session_token(principal, ttl_s=300.0)
    decoded = verifier.verify_session_cookie(cookie_val)
    assert decoded.user_id == "usr-1"
    assert decoded.name == "Nicola"
    assert decoded.is_admin is True
    assert decoded.is_owner is False

    # Tamper payload
    payload_b64, sig_b64 = cookie_val.split(".")
    flipped_char = "A" if payload_b64[0] != "A" else "B"
    with pytest.raises(InvalidSessionCookieError):
        verifier.verify_session_cookie(f"{flipped_char}{payload_b64[1:]}.{sig_b64}")

    # Tamper signature
    sig_flip = "A" if sig_b64[0] != "A" else "B"
    with pytest.raises(InvalidSessionCookieError):
        verifier.verify_session_cookie(f"{payload_b64}.{sig_flip}{sig_b64[1:]}")

    # Wrong secret
    with pytest.raises(InvalidSessionCookieError):
        other_verifier.verify_session_cookie(cookie_val)

    # Expired cookie
    expired_cookie, _ = verifier.create_session_token(principal, ttl_s=0.01)
    time.sleep(0.05)
    with pytest.raises(InvalidSessionCookieError):
        verifier.verify_session_cookie(expired_cookie)


def test_unauthenticated_requests_return_401() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _make_test_config(Path(tmp))
        app = create_app(cfg)
        try:
            with TestClient(app) as client:
                requests_to_check = [
                    ("GET", "/api/v1/status", None),
                    ("GET", "/api/v1/tracks?t_start=0&t_end=10", None),
                    ("GET", "/api/v1/timeline-density?t_start=0&t_end=10", None),
                    ("GET", "/api/v1/calibration/Cam_Carraio", None),
                    ("GET", "/api/v1/ha-camera/snapshot/camera.carraio", None),
                    ("POST", "/api/v1/calibration/solve-pnp", _valid_solve_pnp_payload(app)),
                    ("POST", "/api/v1/calibration/Cam_Carraio", {"camera_id": "Cam_Carraio", "fov_v_deg": 42.0}),
                    ("POST", "/api/v1/ingestion/mode", {"mode": "synthetic"}),
                    ("POST", "/api/v1/detections", _valid_detection_payload()),
                    ("GET", "/api/v1/auth/verify", None),
                ]
                for method, path, body in requests_to_check:
                    resp = client.request(method, path, json=body)
                    assert resp.status_code == 401, f"Expected 401 for {method} {path}, got {resp.status_code}"
        finally:
            app.state.pipeline.repository.close()


def test_auth_session_verify_logout_and_cookie_flags() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _make_test_config(Path(tmp))
        app = create_app(cfg)
        _patch_verifier_tokens(
            app,
            {
                "valid-admin": HAUserPrincipal("u-adm", "Admin", True, False, time.time(), time.time() + 120),
                "valid-res": HAUserPrincipal("u-res", "Residente", False, False, time.time(), time.time() + 120),
            },
        )
        try:
            with TestClient(app) as client:
                # Missing token
                assert client.post("/api/v1/auth/session").status_code == 401
                # Invalid Bearer
                assert (
                    client.post(
                        "/api/v1/auth/session",
                        headers={"Authorization": "Bearer wrong-token"},
                    ).status_code
                    == 401
                )

                # Valid Bearer-only POST without body over plain HTTP
                login_http = client.post(
                    "/api/v1/auth/session",
                    headers={"Authorization": "Bearer valid-admin"},
                )
                assert login_http.status_code == 200
                body = login_http.json()
                assert body["authenticated"] is True
                assert body["user"]["user_id"] == "u-adm"
                assert body["user"]["is_admin"] is True
                assert "no-store" in login_http.headers.get("cache-control", "").lower()

                set_cookie_http = login_http.headers.get("set-cookie", "")
                assert "sh3d_session=" in set_cookie_http
                assert "httponly" in set_cookie_http.lower()
                assert "samesite=strict" in set_cookie_http.lower()
                assert "path=/" in set_cookie_http.lower()
                assert "; secure" not in set_cookie_http.lower()

                # Verify via cookie in client jar
                verify_cookie = client.get("/api/v1/auth/verify")
                assert verify_cookie.status_code == 200
                assert verify_cookie.headers.get("x-sh3d-user") == "u-adm"
                assert verify_cookie.headers.get("x-sh3d-admin") == "true"
                assert "no-store" in verify_cookie.headers.get("cache-control", "").lower()

                # Logout clears cookie and invalidates subsequent verify
                logout_resp = client.post("/api/v1/auth/logout")
                assert logout_resp.status_code == 200
                assert logout_resp.json()["logged_out"] is True
                logout_cookie = logout_resp.headers.get("set-cookie", "")
                assert "sh3d_session=" in logout_cookie
                assert "max-age=0" in logout_cookie.lower()
                assert "samesite=strict" in logout_cookie.lower()
                assert "httponly" in logout_cookie.lower()
                assert client.get("/api/v1/auth/verify").status_code == 401

                # JSON body login behind HTTPS proxy (X-Forwarded-Proto: https) sets Secure
                login_https = client.post(
                    "/api/v1/auth/session",
                    json={"token": "valid-res"},
                    headers={"X-Forwarded-Proto": "https"},
                )
                assert login_https.status_code == 200
                set_cookie_https = login_https.headers.get("set-cookie", "")
                assert "sh3d_session=" in set_cookie_https
                assert "secure" in set_cookie_https.lower()
                assert "httponly" in set_cookie_https.lower()
                assert "samesite=strict" in set_cookie_https.lower()

                # Verify via Bearer directly
                verify_bearer = client.get(
                    "/api/v1/auth/verify",
                    headers={"Authorization": "Bearer valid-res"},
                )
                assert verify_bearer.status_code == 200
                assert verify_bearer.headers.get("x-sh3d-user") == "u-res"
                assert verify_bearer.headers.get("x-sh3d-admin") == "false"

                # Tampered cookie fails alone, but valid Bearer still succeeds
                assert (
                    client.get(
                        "/api/v1/auth/verify",
                        headers={"Cookie": "sh3d_session=tampered.signature"},
                    ).status_code
                    == 401
                )
                assert (
                    client.get(
                        "/api/v1/auth/verify",
                        headers={
                            "Cookie": "sh3d_session=tampered.signature",
                            "Authorization": "Bearer valid-res",
                        },
                    ).status_code
                    == 200
                )
        finally:
            app.state.pipeline.repository.close()


def test_rbac_resident_vs_admin_and_owner() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _make_test_config(Path(tmp))
        app = create_app(cfg)
        _patch_verifier_tokens(
            app,
            {
                "tok-resident": HAUserPrincipal("u-res", "Ospite", False, False, time.time(), time.time() + 120),
                "tok-admin": HAUserPrincipal("u-adm", "Admin", True, False, time.time(), time.time() + 120),
                "tok-owner": HAUserPrincipal("u-own", "Owner", False, True, time.time(), time.time() + 120),
            },
        )
        try:
            with TestClient(app) as client:
                # 1. Resident login -> read routes 200, mutative routes 403
                assert (
                    client.post("/api/v1/auth/session", headers={"Authorization": "Bearer tok-resident"}).status_code
                    == 200
                )
                assert client.get("/api/v1/status").status_code == 200
                assert client.get("/api/v1/tracks?t_start=0&t_end=10").status_code == 200
                assert client.get("/api/v1/timeline-density?t_start=0&t_end=10").status_code == 200
                assert client.get("/api/v1/calibration/Cam_Carraio").status_code == 200

                assert client.post("/api/v1/calibration/solve-pnp", json=_valid_solve_pnp_payload(app)).status_code == 403
                assert (
                    client.post(
                        "/api/v1/calibration/Cam_Carraio",
                        json={"camera_id": "Cam_Carraio", "fov_v_deg": 42.0},
                    ).status_code
                    == 403
                )
                assert client.post("/api/v1/ingestion/mode", json={"mode": "synthetic"}).status_code == 403
                assert client.post("/api/v1/detections", json=_valid_detection_payload()).status_code == 403

                # 2. Admin AND Owner -> mutative routes 200
                for tok in ("tok-admin", "tok-owner"):
                    assert (
                        client.post("/api/v1/auth/session", headers={"Authorization": f"Bearer {tok}"}).status_code
                        == 200
                    )
                    assert client.post("/api/v1/calibration/solve-pnp", json=_valid_solve_pnp_payload(app)).status_code == 200
                    assert (
                        client.post(
                            "/api/v1/calibration/Cam_Carraio",
                            json={"camera_id": "Cam_Carraio", "fov_v_deg": 42.0},
                        ).status_code
                        == 200
                    )
                    assert client.post("/api/v1/ingestion/mode", json={"mode": "synthetic"}).status_code == 200
                    assert client.post("/api/v1/detections", json=_valid_detection_payload()).status_code == 200
        finally:
            app.state.pipeline.repository.close()


def test_ws_spatial_auth_4401_and_authenticated_connect() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _make_test_config(Path(tmp))
        app = create_app(cfg)
        _patch_verifier_tokens(
            app,
            {
                "tok-resident": HAUserPrincipal("u-res", "Residente", False, False, time.time(), time.time() + 120),
            },
        )
        try:
            with TestClient(app) as client:
                with pytest.raises(WebSocketDisconnect) as exc_unauth:
                    with client.websocket_connect("/ws/spatial"):
                        pass
                assert exc_unauth.value.code == 4401

                with pytest.raises(WebSocketDisconnect) as exc_tampered:
                    with client.websocket_connect(
                        "/ws/spatial",
                        headers={"Cookie": "sh3d_session=invalid.cookie"},
                    ):
                        pass
                assert exc_tampered.value.code == 4401

                # Cookie-based WS connect after HTTP session login
                assert (
                    client.post("/api/v1/auth/session", headers={"Authorization": "Bearer tok-resident"}).status_code
                    == 200
                )
                with client.websocket_connect("/ws/spatial") as ws_cookie:
                    hello = json.loads(ws_cookie.receive_text())
                    assert hello["type"] == "server_status"

            # Fresh client with Bearer header WS connect
            with TestClient(app) as bearer_client:
                with bearer_client.websocket_connect(
                    "/ws/spatial",
                    headers={"Authorization": "Bearer tok-resident"},
                ) as ws_bearer:
                    hello = json.loads(ws_bearer.receive_text())
                    assert hello["type"] == "server_status"
        finally:
            app.state.pipeline.repository.close()


def test_snapshot_proxy_bearer_fallback_and_ha_public_url() -> None:
    mock_jpeg = b"\xff\xd8\xff\xe0MOCK_CAMERA_JPEG"
    with _mock_ha_http_server({"tok-user"}, snapshot_bytes=mock_jpeg) as (http_url, http_state):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _make_test_config(
                Path(tmp),
                ha_token="",
                ha_local_url="",
                ha_tailscale_url="",
                ha_public_url=http_url,
            )
            app = create_app(cfg)
            _patch_verifier_tokens(
                app,
                {
                    "tok-user": HAUserPrincipal("u-res", "Residente", False, False, time.time(), time.time() + 120),
                },
            )
            try:
                with TestClient(app) as client:
                    # Cookie-only without Bearer and with ha_token="" -> 503
                    assert (
                        client.post("/api/v1/auth/session", headers={"Authorization": "Bearer tok-user"}).status_code
                        == 200
                    )
                    resp_no_bearer = client.get("/api/v1/ha-camera/snapshot/camera.carraio_scorrevole")
                    assert resp_no_bearer.status_code == 503

                    # Non-camera entity_id rejected
                    resp_bad_entity = client.get(
                        "/api/v1/ha-camera/snapshot/person.nicola",
                        headers={"Authorization": "Bearer tok-user"},
                    )
                    assert resp_bad_entity.status_code == 400

                    # Untrusted ha_url rejected (SSRF protection)
                    resp_ssrf = client.get(
                        "/api/v1/ha-camera/snapshot/camera.carraio_scorrevole?ha_url=http://169.254.169.254",
                        headers={"Authorization": "Bearer tok-user"},
                    )
                    assert resp_ssrf.status_code == 400

                    # Caller Bearer fallback succeeds against ha_public_url
                    resp_ok = client.get(
                        f"/api/v1/ha-camera/snapshot/camera.carraio_scorrevole?ha_url={http_url}",
                        headers={"Authorization": "Bearer tok-user"},
                    )
                    assert resp_ok.status_code == 200
                    assert resp_ok.content == mock_jpeg
                    assert "no-store" in resp_ok.headers.get("cache-control", "").lower()
                    assert http_state["snapshot_calls"] == 1
                    assert http_state["last_auth"] == "Bearer tok-user"
                    assert http_state["last_path"] == "/api/camera_proxy/camera.carraio_scorrevole"
            finally:
                app.state.pipeline.repository.close()


def test_cors_allowed_origins_enforced() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _make_test_config(
            Path(tmp),
            allowed_origins=("https://app.tailnet.ts.net", "http://localhost:5173"),
        )
        app = create_app(cfg)
        try:
            with TestClient(app) as client:
                ok_preflight = client.options(
                    "/api/v1/status",
                    headers={
                        "Origin": "https://app.tailnet.ts.net",
                        "Access-Control-Request-Method": "GET",
                    },
                )
                assert ok_preflight.headers.get("access-control-allow-origin") == "https://app.tailnet.ts.net"
                assert ok_preflight.headers.get("access-control-allow-credentials") == "true"

                bad_origin = client.options(
                    "/api/v1/status",
                    headers={
                        "Origin": "https://evil.example.com",
                        "Access-Control-Request-Method": "GET",
                    },
                )
                assert "access-control-allow-origin" not in bad_origin.headers
        finally:
            app.state.pipeline.repository.close()
