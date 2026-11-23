from __future__ import annotations

import dataclasses
import itertools
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import pytest
import uvicorn
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Minimal valid JPEG bytes (SOI + APP0 + EOI) for snapshot proxy verification.
_MINIMAL_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
    b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
    b"\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00"
    b"\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\t\xff\xda\x00\x08\x01\x01"
    b"\x00\x00?\x00\xd2\xcf \xff\xd9"
)

_PRE_SEEDED_ENV: dict[str, str] = {
    "SH3D_DEV_MODE": "false",
    "SPATIAL_DEV_AUTH_REQUIRED": "",
    "VITE_HA_DEV_URL": "",
    "SPATIAL_SERVER_HOST": "127.0.0.1",
    "SPATIAL_AUTH_REQUIRED": "true",
    "SPATIAL_SESSION_SECRET": "e2e-test-session-secret-0123456789abcdef",
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


def pytest_configure(config: pytest.Config) -> None:
    """Pre-seed deterministic env defaults BEFORE any spatial_server.* import.

    NOTE: FastAPI/Starlette TestClient and local uvicorn loopback servers
    require BypassSandbox: true when invoked on Windows in sandboxed runners.
    """
    for key, value in _PRE_SEEDED_ENV.items():
        os.environ[key] = value

    config.addinivalue_line("markers", "tier1: Core positive behavior (happy path) E2E tests")
    config.addinivalue_line("markers", "tier2: Negative, security, boundary, and error-handling E2E tests")
    config.addinivalue_line("markers", "tier3: Cross-feature pairwise integration E2E tests")
    config.addinivalue_line("markers", "tier4: End-to-end realistic user scenario tests")


def _default_tokens() -> dict[str, dict[str, Any]]:
    return {
        "tok-admin": {
            "id": "u-admin",
            "name": "Admin",
            "is_admin": True,
            "is_owner": False,
        },
        "tok-owner": {
            "id": "u-owner",
            "name": "Owner",
            "is_admin": False,
            "is_owner": True,
        },
        "tok-resident": {
            "id": "u-res",
            "name": "Residente",
            "is_admin": False,
            "is_owner": False,
        },
    }


@dataclass
class FakeHAState:
    tokens: dict[str, dict[str, Any]] = field(default_factory=_default_tokens)
    ws_mode: str = "normal"  # "normal" | "auth_current_user_error" | "drop"
    rest_status_override: Optional[int] = None
    ws_auth_calls: int = 0
    rest_auth_calls: int = 0
    last_snapshot_auth_header: Optional[str] = None
    last_snapshot_entity_id: Optional[str] = None
    valid_cameras: set[str] = field(
        default_factory=lambda: {"camera.carraio", "camera.carraio_scorrevole"}
    )

    def reset(self) -> None:
        self.tokens = _default_tokens()
        self.ws_mode = "normal"
        self.rest_status_override = None
        self.ws_auth_calls = 0
        self.rest_auth_calls = 0
        self.last_snapshot_auth_header = None
        self.last_snapshot_entity_id = None
        self.valid_cameras = {"camera.carraio", "camera.carraio_scorrevole"}


def _extract_bearer(header_value: Optional[str]) -> str:
    if not header_value:
        return ""
    parts = header_value.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


def _build_fake_ha_app(state: FakeHAState) -> FastAPI:
    app = FastAPI(title="Fake Home Assistant E2E Server")

    @app.get("/api/")
    async def api_root(request: Request) -> Response:
        state.rest_auth_calls += 1
        if state.rest_status_override is not None:
            return JSONResponse(
                {"message": f"Override {state.rest_status_override}"},
                status_code=state.rest_status_override,
            )
        token = _extract_bearer(request.headers.get("authorization"))
        if token and token in state.tokens:
            return JSONResponse({"message": "API running."}, status_code=200)
        return JSONResponse({"message": "401: Unauthorized"}, status_code=401)

    @app.get("/api/camera_proxy/{entity_id}")
    async def camera_proxy(entity_id: str, request: Request) -> Response:
        auth_header = request.headers.get("authorization")
        state.last_snapshot_auth_header = auth_header
        state.last_snapshot_entity_id = entity_id
        token = _extract_bearer(auth_header)
        if not token or token not in state.tokens:
            return JSONResponse({"message": "401: Unauthorized"}, status_code=401)
        if entity_id not in state.valid_cameras:
            return JSONResponse({"message": "404: Not Found"}, status_code=404)
        return Response(content=_MINIMAL_JPEG, media_type="image/jpeg", status_code=200)

    @app.websocket("/api/websocket")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        if state.ws_mode == "drop":
            await websocket.close(code=1011)
            return

        authed_user: Optional[dict[str, Any]] = None
        try:
            await websocket.send_json(
                {"type": "auth_required", "ha_version": "2024.10.0"}
            )
            auth_msg = await websocket.receive_json()
            state.ws_auth_calls += 1
            token = str(auth_msg.get("access_token") or "")
            if auth_msg.get("type") != "auth" or token not in state.tokens:
                await websocket.send_json(
                    {
                        "type": "auth_invalid",
                        "message": "Invalid access token or password",
                    }
                )
                await websocket.close(code=1008)
                return

            authed_user = dict(state.tokens[token])
            await websocket.send_json(
                {"type": "auth_ok", "ha_version": "2024.10.0"}
            )

            while True:
                msg = await websocket.receive_json()
                msg_id = msg.get("id", 1)
                msg_type = msg.get("type")
                if msg_type == "auth/current_user":
                    if state.ws_mode == "auth_current_user_error":
                        await websocket.send_json(
                            {
                                "id": msg_id,
                                "type": "result",
                                "success": False,
                                "error": {
                                    "code": "unknown_error",
                                    "message": "Simulated auth/current_user error",
                                },
                            }
                        )
                    else:
                        await websocket.send_json(
                            {
                                "id": msg_id,
                                "type": "result",
                                "success": True,
                                "result": authed_user,
                            }
                        )
                else:
                    await websocket.send_json(
                        {
                            "id": msg_id,
                            "type": "result",
                            "success": False,
                            "error": {"code": "unknown_command", "message": "Unsupported"},
                        }
                    )
        except WebSocketDisconnect:
            return
        except Exception:
            return

    return app


class FakeHAServer:
    def __init__(self) -> None:
        self.state = FakeHAState()
        self._app = _build_fake_ha_app(self.state)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(128)
        self.port: int = int(self._sock.getsockname()[1])
        self.base_url: str = f"http://127.0.0.1:{self.port}"
        self.ws_url: str = f"ws://127.0.0.1:{self.port}/api/websocket"

        config = uvicorn.Config(
            self._app,
            host="127.0.0.1",
            port=self.port,
            log_level="error",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run,
            kwargs={"sockets": [self._sock]},
            daemon=True,
            name=f"fake-ha-{self.port}",
        )

    def start(self) -> None:
        self._thread.start()
        deadline = time.monotonic() + 5.0
        while not self._server.started:
            if not self._thread.is_alive():
                raise RuntimeError("FakeHAServer failed to start")
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for FakeHAServer to listen")
            time.sleep(0.01)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5.0)
        try:
            self._sock.close()
        except OSError:
            pass


@pytest.fixture(scope="session")
def _fake_ha_server_session() -> Iterator[FakeHAServer]:
    srv = FakeHAServer()
    srv.start()
    try:
        yield srv
    finally:
        srv.stop()


@pytest.fixture
def fake_ha_server(_fake_ha_server_session: FakeHAServer) -> Iterator[FakeHAServer]:
    _fake_ha_server_session.state.reset()
    yield _fake_ha_server_session
    _fake_ha_server_session.state.reset()


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def closed_port_url() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def isolated_app_factory(
    tmp_path: Path,
    fake_ha_server: FakeHAServer,
) -> Iterator[Callable[..., Any]]:
    from spatial_server.config import SpatialServerConfig
    from spatial_server.main import create_app

    created_apps: list[Any] = []
    counter = itertools.count(1)

    def factory(**cfg_overrides: Any) -> Any:
        idx = next(counter)
        base_cfg = SpatialServerConfig.from_env()
        defaults: dict[str, Any] = {
            "host": "127.0.0.1",
            "sqlite_db_path": tmp_path / f"spatial_test_{idx}.db",
            "calibration_override_path": tmp_path / f"calibs_{idx}.json",
            "data_dir": tmp_path,
            "models_dir": tmp_path,
            "default_ingestion_mode": "synthetic",
            "ha_local_url": fake_ha_server.base_url,
            "ha_tailscale_url": "",
            "ha_public_url": "",
            "ha_token": "",
            "auth_required": True,
            "session_secret_key": "e2e-test-session-secret-0123456789abcdef",
            "allowed_origins": [
                "https://smarthome.tailnet.ts.net",
                "http://127.0.0.1:8080",
            ],
        }
        defaults.update(cfg_overrides)
        cfg = dataclasses.replace(base_cfg, **defaults)
        app = create_app(cfg)
        created_apps.append(app)
        return app

    try:
        yield factory
    finally:
        for app in created_apps:
            try:
                app.state.pipeline.repository.close()
            except Exception:
                pass


@pytest.fixture
def client(isolated_app_factory: Callable[..., Any]) -> Iterator[TestClient]:
    app = isolated_app_factory()
    with TestClient(app) as test_client:
        yield test_client
