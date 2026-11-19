from __future__ import annotations

import json
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def _create_session(client: TestClient, token: str = "tok-admin"):
    return client.post(
        "/api/v1/auth/session",
        headers={"Authorization": f"Bearer {token}"},
    )


def _solve_pnp_payload(app) -> dict:
    pinhole = app.state.pipeline.optical_models["Cam_Carraio"]
    calib = pinhole.to_metadata_dict()
    T_gl = np.array(calib["matrix_world_gl"], dtype=np.float64).reshape((4, 4))
    R_flip_y = np.diag([-1.0, 1.0, -1.0, 1.0])
    from spatial_server.optics.pinhole_model import matrix_gl_to_cv

    pinhole.update_calibration(
        extrinsic_cv_to_world=matrix_gl_to_cv(T_gl @ R_flip_y).reshape(-1).tolist()
    )
    pts_w = [
        (-13.0, 0.0, 10.0),
        (-10.0, 0.0, 12.0),
        (-13.5, 0.0, 15.0),
        (-9.5, 0.0, 17.0),
        (-12.0, 1.2, 13.0),
        (-11.0, 0.5, 9.5),
    ]
    corrs = []
    for p in pts_w:
        uv = pinhole.world_point_to_pixel(p)
        assert uv is not None
        corrs.append({"world_point": list(p), "pixel_uv": list(uv)})
    return {"camera_id": "Cam_Carraio", "correspondences": corrs}


@pytest.mark.tier1
def test_f3_t1_01_post_auth_session_via_bearer_sets_httponly_cookie(
    client: TestClient,
) -> None:
    resp = _create_session(client, "tok-admin")
    assert resp.status_code == 200
    body = resp.json()
    assert body["authenticated"] is True
    assert body["user"]["user_id"] == "u-admin"
    assert body["user"]["is_admin"] is True
    assert body["expires_at"] > time.time()

    set_cookie = resp.headers.get("set-cookie", "")
    assert "sh3d_session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()
    assert "path=/" in set_cookie.lower()


@pytest.mark.tier1
def test_f3_t1_02_post_auth_session_via_json_body_and_verify_cookie(
    client: TestClient,
) -> None:
    resp = client.post("/api/v1/auth/session", json={"token": "tok-resident"})
    assert resp.status_code == 200
    assert resp.json()["authenticated"] is True
    assert "sh3d_session" in client.cookies

    verify_resp = client.get("/api/v1/auth/verify")
    assert verify_resp.status_code == 200
    v_body = verify_resp.json()
    assert v_body["user"]["user_id"] == "u-res"
    assert v_body["user"]["is_admin"] is False
    assert v_body["user"]["is_owner"] is False


@pytest.mark.tier1
def test_f3_t1_03_post_auth_logout_clears_session_cookie(client: TestClient) -> None:
    assert _create_session(client, "tok-admin").status_code == 200
    assert client.get("/api/v1/auth/verify").status_code == 200

    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    set_cookie = logout_resp.headers.get("set-cookie", "").lower()
    assert "sh3d_session=" in set_cookie
    assert "max-age=0" in set_cookie or "expires=" in set_cookie

    assert client.get("/api/v1/auth/verify").status_code == 401


@pytest.mark.tier1
def test_f3_t1_04_read_endpoints_allow_authenticated_resident(
    client: TestClient,
) -> None:
    assert _create_session(client, "tok-resident").status_code == 200
    now = time.time()

    assert client.get("/api/v1/status").status_code == 200
    assert (
        client.get(f"/api/v1/tracks?t_start={now - 60}&t_end={now + 60}").status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/timeline-density?t_start={now - 60}&t_end={now + 60}&buckets=10"
        ).status_code
        == 200
    )
    assert client.get("/api/v1/calibration/Cam_Carraio").status_code == 200


@pytest.mark.tier1
def test_f3_t1_05_admin_allowed_on_all_mutative_endpoints(client: TestClient) -> None:
    assert _create_session(client, "tok-admin").status_code == 200

    r_mode = client.post("/api/v1/ingestion/mode", json={"mode": "synthetic"})
    assert r_mode.status_code == 200

    r_det = client.post(
        "/api/v1/detections",
        json={
            "camera_id": "Cam_Carraio",
            "timestamp": time.time(),
            "class_label": "person",
            "confidence": 0.9,
            "bbox": {"x_min": 0.4, "y_min": 0.5, "x_max": 0.5, "y_max": 0.8},
        },
    )
    assert r_det.status_code == 200

    r_cal = client.post(
        "/api/v1/calibration/Cam_Carraio",
        json={"camera_id": "Cam_Carraio", "fov_v_deg": 42.0, "fov_h_deg": 80.0},
    )
    assert r_cal.status_code == 200

    pnp_req = _solve_pnp_payload(client.app)
    r_pnp = client.post("/api/v1/calibration/solve-pnp", json=pnp_req)
    assert r_pnp.status_code == 200


@pytest.mark.tier1
def test_f3_t1_06_snapshot_proxy_uses_caller_bearer_when_server_ha_token_empty(
    client: TestClient, fake_ha_server
) -> None:
    resp = client.get(
        "/api/v1/ha-camera/snapshot/camera.carraio",
        headers={"Authorization": "Bearer tok-resident"},
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"\xff\xd8\xff")
    assert "no-store" in resp.headers.get("cache-control", "").lower()
    assert fake_ha_server.state.last_snapshot_entity_id == "camera.carraio"
    assert fake_ha_server.state.last_snapshot_auth_header == "Bearer tok-resident"


@pytest.mark.tier1
def test_f3_t1_07_websocket_spatial_accepts_authenticated_cookie_and_bearer(
    isolated_app_factory,
) -> None:
    app = isolated_app_factory()
    with TestClient(app) as tc:
        # 1. Cookie auth
        assert _create_session(tc, "tok-resident").status_code == 200
        with tc.websocket_connect("/ws/spatial") as ws:
            hello = json.loads(ws.receive_text())
            assert hello["type"] == "server_status"
            ws.send_text("ping")
            assert ws.receive_text() == "pong"

    app2 = isolated_app_factory()
    with TestClient(app2) as tc2:
        # 2. Bearer header auth (without prior cookie)
        with tc2.websocket_connect(
            "/ws/spatial", headers={"Authorization": "Bearer tok-admin"}
        ) as ws2:
            hello2 = json.loads(ws2.receive_text())
            assert hello2["type"] == "server_status"
            ws2.send_text("ping")
            assert ws2.receive_text() == "pong"


@pytest.mark.tier2
def test_f3_t2_01_unauthenticated_read_and_verify_endpoints_return_401(
    client: TestClient,
) -> None:
    now = time.time()
    for path in (
        "/api/v1/auth/verify",
        "/api/v1/status",
        f"/api/v1/tracks?t_start={now - 60}&t_end={now}",
        f"/api/v1/timeline-density?t_start={now - 60}&t_end={now}&buckets=10",
        "/api/v1/calibration/Cam_Carraio",
        "/api/v1/ha-camera/snapshot/camera.carraio",
    ):
        assert client.get(path).status_code == 401, f"Expected 401 on {path}"


@pytest.mark.tier2
def test_f3_t2_02_non_admin_resident_gets_403_on_all_four_mutative_endpoints(
    client: TestClient,
) -> None:
    assert _create_session(client, "tok-resident").status_code == 200

    assert (
        client.post(
            "/api/v1/ingestion/mode", json={"mode": "synthetic"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/detections",
            json={
                "camera_id": "Cam_Carraio",
                "timestamp": time.time(),
                "class_label": "person",
                "confidence": 0.9,
                "bbox": {"x_min": 0.4, "y_min": 0.5, "x_max": 0.5, "y_max": 0.8},
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/calibration/Cam_Carraio",
            json={"camera_id": "Cam_Carraio", "fov_v_deg": 42.0},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/calibration/solve-pnp",
            json={
                "camera_id": "Cam_Carraio",
                "correspondences": [
                    {"world_point": [0, 0, 0], "pixel_uv": [0.5, 0.5]}
                    for _ in range(4)
                ],
            },
        ).status_code
        == 403
    )


@pytest.mark.tier2
def test_f3_t2_03_websocket_unauthenticated_or_invalid_cookie_closes_4401(
    client: TestClient,
) -> None:
    # No credentials
    with pytest.raises(WebSocketDisconnect) as exc_no_auth:
        with client.websocket_connect("/ws/spatial") as ws:
            ws.receive_text()
    assert exc_no_auth.value.code == 4401

    # Tampered cookie
    client.cookies.set("sh3d_session", "tampered.signature")
    with pytest.raises(WebSocketDisconnect) as exc_bad_cookie:
        with client.websocket_connect("/ws/spatial") as ws:
            ws.receive_text()
    assert exc_bad_cookie.value.code == 4401


@pytest.mark.tier2
def test_f3_t2_04_secure_cookie_flag_follows_x_forwarded_proto(
    isolated_app_factory,
) -> None:
    app = isolated_app_factory()
    with TestClient(app) as tc:
        r_http = tc.post(
            "/api/v1/auth/session",
            headers={"Authorization": "Bearer tok-admin"},
        )
        assert r_http.status_code == 200
        cookie_http = r_http.headers.get("set-cookie", "")
        assert "secure" not in cookie_http.lower()

        r_https = tc.post(
            "/api/v1/auth/session",
            headers={
                "Authorization": "Bearer tok-admin",
                "X-Forwarded-Proto": "https",
            },
        )
        assert r_https.status_code == 200
        cookie_https = r_https.headers.get("set-cookie", "")
        assert "secure" in cookie_https.lower()


@pytest.mark.tier2
def test_f3_t2_05_cors_allows_configured_origin_and_blocks_disallowed_origin(
    client: TestClient,
) -> None:
    r_allowed = client.options(
        "/api/v1/status",
        headers={
            "Origin": "https://smarthome.tailnet.ts.net",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert (
        r_allowed.headers.get("access-control-allow-origin")
        == "https://smarthome.tailnet.ts.net"
    )
    assert r_allowed.headers.get("access-control-allow-credentials") == "true"

    r_evil = client.options(
        "/api/v1/status",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    evil_acao = r_evil.headers.get("access-control-allow-origin")
    assert evil_acao is None
    assert evil_acao != "*"


@pytest.mark.tier2
def test_f3_t2_06_post_auth_session_missing_or_invalid_token_returns_401(
    client: TestClient,
) -> None:
    for kwargs in (
        {},
        {"json": {"token": ""}},
        {"headers": {"Authorization": "Bearer tok-invalid"}},
    ):
        resp = client.post("/api/v1/auth/session", **kwargs)
        assert resp.status_code == 401
        assert "sh3d_session=" not in resp.headers.get("set-cookie", "")


@pytest.mark.tier2
def test_f3_t2_07_snapshot_invalid_entity_id_returns_400_and_ha_error_propagates(
    client: TestClient,
) -> None:
    headers = {"Authorization": "Bearer tok-resident"}
    bad = client.get("/api/v1/ha-camera/snapshot/bad;id", headers=headers)
    assert bad.status_code == 400

    unknown = client.get("/api/v1/ha-camera/snapshot/camera.nonexistent", headers=headers)
    assert unknown.status_code in (404, 502)


@pytest.mark.tier2
def test_f3_t2_08_auth_session_with_is_owner_only_grants_admin_rbac(
    client: TestClient,
) -> None:
    resp = _create_session(client, "tok-owner")
    assert resp.status_code == 200
    assert resp.json()["user"]["is_owner"] is True
    assert resp.json()["user"]["is_admin"] is False

    r_mode = client.post("/api/v1/ingestion/mode", json={"mode": "synthetic"})
    assert r_mode.status_code == 200
