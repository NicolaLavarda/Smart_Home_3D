"""E2E tests for F9: SpatialStreamClient same-origin routing, auth & WS handling."""

from __future__ import annotations

from tests.e2e.helpers.artifacts import run_js_scenario


# ---------------------------------------------------------------------------
# Tier 1: Core Functionality (5 tests)
# ---------------------------------------------------------------------------


def test_f9_t1_prod_same_origin_urls():
    res = run_js_scenario(
        {
            "action": "f9_client_check",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
        }
    )
    d = res["data"]
    assert d["baseUrl"] == ""
    assert d["wsUrl"] == "wss://home.tailnet.ts.net/ws/spatial"


def test_f9_t1_dev_fallback_urls():
    res = run_js_scenario(
        {
            "action": "f9_client_check",
            "mode": "development",
            "location": "http://localhost:3000/",
            "env": {"VITE_SPATIAL_SERVER_URL": ""},
        }
    )
    d = res["data"]
    assert d["baseUrl"] == "http://localhost:8765"
    assert d["wsUrl"] == "ws://localhost:8765/ws/spatial"


def test_f9_t1_authenticate_with_ha_token():
    res = run_js_scenario(
        {
            "action": "f9_client_check",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "callAuthWith": "ha-jwt-token-xyz",
            "fetchRoutes": [
                {
                    "match": "/api/v1/auth/session",
                    "status": 200,
                    "json": {"authenticated": True, "user": {"user_id": "u1", "is_admin": True}},
                }
            ],
        }
    )
    d = res["data"]
    assert len(d["fetchLog"]) == 1
    req = d["fetchLog"][0]
    assert req["url"] == "/api/v1/auth/session"
    assert req["method"] == "POST"
    assert req["credentials"] == "include"
    has_bearer = any(
        k.lower() == "authorization" and "Bearer ha-jwt-token-xyz" in v
        for k, v in req["headers"].items()
    )
    has_body_token = isinstance(req["body"], str) and "ha-jwt-token-xyz" in req["body"]
    assert has_bearer or has_body_token
    assert d["authResult"] is not None


def test_f9_t1_request_json_credentials_and_json_headers():
    res = run_js_scenario(
        {
            "action": "f9_client_check",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "callFetchStatus": True,
            "fetchRoutes": [
                {
                    "match": "/api/v1/status",
                    "status": 200,
                    "json": {"ingestion_mode": "synthetic"},
                }
            ],
        }
    )
    d = res["data"]
    assert d["statusResult"] == {"ingestion_mode": "synthetic"}
    req = d["fetchLog"][0]
    assert req["url"] == "/api/v1/status"
    assert req["credentials"] == "include"
    ct = next((v for k, v in req["headers"].items() if k.lower() == "content-type"), None)
    assert ct == "application/json"


def test_f9_t1_websocket_dispatches_frames_and_status():
    res = run_js_scenario(
        {
            "action": "f9_client_check",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "testWs": True,
            "wsMessages": [
                {"type": "spatial_frame", "objects": [{"track_id": 1, "x": 1.2}]},
                {"type": "server_status", "ingestion_mode": "openvino"},
            ],
        }
    )
    d = res["data"]
    assert d["wsCount"] == 1
    assert d["wsUrls"] == ["wss://home.tailnet.ts.net/ws/spatial"]
    assert len(d["frames"]) == 1
    assert d["frames"][0]["objects"][0]["track_id"] == 1
    assert any(s["connected"] is True and s["meta"] and s["meta"].get("ingestion_mode") == "openvino" for s in d["statuses"])


# ---------------------------------------------------------------------------
# Tier 2: Edge Cases, Negative & Boundary Conditions (5 tests)
# ---------------------------------------------------------------------------


def test_f9_t2_request_json_custom_headers_preserve_content_type():
    res = run_js_scenario(
        {
            "action": "f9_client_check",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "requestCall": {
                "path": "/api/v1/calibration/cam1",
                "options": {
                    "method": "POST",
                    "headers": {"X-Test": "1"},
                    "body": "{}",
                },
            },
            "fetchRoutes": [{"match": "/api/v1/calibration/cam1", "status": 200, "json": {"ok": True}}],
        }
    )
    d = res["data"]
    assert d["requestResult"] == {"ok": True}
    headers_lower = {k.lower(): v for k, v in d["fetchLog"][0]["headers"].items()}
    assert headers_lower.get("content-type") == "application/json"
    assert headers_lower.get("x-test") == "1"


def test_f9_t2_authenticate_empty_token_no_network_call():
    for empty_val in ("", None):
        res = run_js_scenario(
            {
                "action": "f9_client_check",
                "mode": "production",
                "location": "https://home.tailnet.ts.net/",
                "callAuthWith": empty_val,
            }
        )
        d = res["data"]
        assert d["fetchLog"] == []
        assert not d["authResult"]


def test_f9_t2_ws_close_4401_halts_reconnect_loop():
    res = run_js_scenario(
        {
            "action": "f9_client_check",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "fakeTimers": True,
            "testWs": True,
            "wsCloseCode": 4401,
            "wsCloseReason": "Unauthorized",
        }
    )
    d = res["data"]
    assert d["connected"] is False
    assert d["wsCount"] == 1
    assert d["scheduledTimeoutsCount"] == 0


def test_f9_t2_request_json_401_403_returns_null():
    for status_code in (401, 403):
        res = run_js_scenario(
            {
                "action": "f9_client_check",
                "mode": "production",
                "location": "https://home.tailnet.ts.net/",
                "requestCall": {"path": "/api/v1/status", "options": {"method": "GET"}},
                "fetchRoutes": [{"match": "/api/v1/status", "status": status_code, "json": {"detail": "denied"}}],
            }
        )
        assert res["data"]["requestResult"] is None


def test_f9_t2_request_json_network_reject_or_abort_returns_null():
    res = run_js_scenario(
        {
            "action": "f9_client_check",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "requestCall": {"path": "/api/v1/status", "options": {"method": "GET"}},
            "fetchRoutes": [{"match": "/api/v1/status", "reject": "NetworkError when attempting to fetch resource"}],
        }
    )
    assert res["data"]["requestResult"] is None
