"""E2E tests for F11: Frontend RBAC UI hiding/blocking, Login overlay & auth wiring."""

from __future__ import annotations

import json

from tests.e2e.helpers.artifacts import run_js_scenario


# ---------------------------------------------------------------------------
# Tier 1: Core Functionality (5 tests)
# ---------------------------------------------------------------------------


def test_f11_t1_topbar_admin_shows_calib_and_role():
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "topbar",
            "initialIsAdmin": True,
            "initialUser": {"id": "u1", "name": "Nicola", "is_admin": True},
        }
    )
    st = res["data"]["states"][0]
    assert st["calibExists"] is True
    assert st["calibVisibleAndEnabled"] is True
    assert "admin" in st["text"].lower()
    assert st["hasLogoutBtn"] is True


def test_f11_t1_topbar_resident_hides_calib_and_shows_role():
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "topbar",
            "initialIsAdmin": False,
            "initialUser": {"id": "u2", "name": "Mario", "is_admin": False},
        }
    )
    st = res["data"]["states"][0]
    assert st["calibVisibleAndEnabled"] is False
    assert "residente" in st["text"].lower()


def test_f11_t1_camera_modal_admin_shows_calib_and_simulator():
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "camera_modal",
            "isAdmin": True,
        }
    )
    d = res["data"]
    assert d["calibVisibleAndEnabled"] is True
    assert d["simVisibleAndEnabled"] is True


def test_f11_t1_camera_modal_resident_hides_admin_controls():
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "camera_modal",
            "isAdmin": False,
        }
    )
    d = res["data"]
    assert d["calibVisibleAndEnabled"] is False
    assert d["simVisibleAndEnabled"] is False
    assert d["povExists"] is True
    assert d["videoExists"] is True


def test_f11_t1_login_overlay_on_auth_required():
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "main_bootstrap",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "localStorage": {},
            "clickLogin": True,
            "fetchRoutes": [
                {
                    "match": "/models/scene_manifest.json",
                    "status": 200,
                    "json": {"ha_entities": {}, "cameras": {}, "ground_colliders": []},
                },
                {
                    "match": "/models/house_optimized.glb",
                    "status": 200,
                    "glb": True,
                },
            ],
        }
    )
    d = res["data"]
    assert d["hasLoginOverlay"] is True
    assert d["loginRedirectTriggered"] is True


# ---------------------------------------------------------------------------
# Tier 2: Edge Cases, Negative & Boundary Conditions (5 tests)
# ---------------------------------------------------------------------------


def test_f11_t2_calibration_assistant_open_blocked_for_non_admin():
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "calibration_guard",
            "isAdmin": False,
        }
    )
    d = res["data"]
    assert d["isOpen"] is False
    assert d["panelOpen"] is False
    assert d["acquireCalled"] is False


def test_f11_t2_topbar_reactive_role_switching():
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "topbar",
            "initialIsAdmin": False,
            "initialUser": None,
            "transitions": [
                {"isAdmin": False, "user": {"id": "u2", "name": "Mario", "is_admin": False}, "status": "authenticated"},
                {"isAdmin": True, "user": {"id": "u1", "name": "Nicola", "is_admin": True}, "status": "authenticated"},
            ],
        }
    )
    states = res["data"]["states"]
    assert len(states) == 3
    # Unauthenticated -> calib hidden/disabled
    assert states[0]["calibVisibleAndEnabled"] is False
    # Residente -> calib hidden/disabled, role Residente shown
    assert states[1]["calibVisibleAndEnabled"] is False
    assert "residente" in states[1]["text"].lower()
    # Admin -> calib visible & enabled, role Admin shown
    assert states[2]["calibVisibleAndEnabled"] is True
    assert "admin" in states[2]["text"].lower()


def test_f11_t2_topbar_logout_invokes_ha_logout():
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "topbar",
            "initialIsAdmin": True,
            "initialUser": {"id": "u1", "name": "Nicola", "is_admin": True},
            "clickLogout": True,
        }
    )
    assert res["data"]["logoutCalled"] is True


def test_f11_t2_auth_wiring_triggers_spatial_session():
    stored = {
        "hassUrl": "https://home.tailnet.ts.net:8443",
        "access_token": "ha-session-wiring-tok",
        "expires": 9_999_999_999_999,
    }
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "main_bootstrap",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "localStorage": {"sh3d_ha_oauth_tokens": json.dumps(stored)},
            "fetchRoutes": [
                {
                    "match": "/models/scene_manifest.json",
                    "status": 200,
                    "json": {"ha_entities": {}, "cameras": {}, "ground_colliders": []},
                },
                {
                    "match": "/models/house_optimized.glb",
                    "status": 200,
                    "glb": True,
                },
                {
                    "match": "/api/v1/auth/session",
                    "status": 200,
                    "json": {"authenticated": True, "user": {"user_id": "u-admin", "is_admin": True}},
                },
            ],
        }
    )
    events = res["data"]["networkEvents"]
    auth_events = [e for e in events if e["type"] == "fetch" and "/api/v1/auth/session" in e["url"]]
    ws_events = [e for e in events if e["type"] == "ws" and "/ws/spatial" in e["url"]]
    assert len(auth_events) >= 1
    assert len(ws_events) >= 1
    assert auth_events[0]["seq"] < ws_events[0]["seq"]


def test_f11_t2_icons_registry_covers_ui_icons():
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    ui_files = [
        repo_root / "src" / "ui" / "TopBar.js",
        repo_root / "src" / "devices" / "camera" / "SecurityCameraModal.js",
        repo_root / "src" / "spatial" / "calibration" / "CalibrationAssistantUI.js",
        repo_root / "src" / "ui" / "PwaUpdatePrompt.js",
        repo_root / "src" / "main.js",
    ]
    discovered: set[str] = {"settings", "sliders-horizontal", "refresh-cw", "x"}
    icon_call_re = re.compile(r"""\bicon\(\s*['"]([a-z0-9-]+)['"]""")
    for path in ui_files:
        if path.is_file():
            content = path.read_text(encoding="utf-8", errors="replace")
            discovered.update(icon_call_re.findall(content))

    required_icons = sorted(discovered)
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "icons",
            "names": required_icons,
        }
    )
    results = res["data"]["results"]
    for name in required_icons:
        svg = results.get(name, "")
        assert svg.startswith("<svg") and "</svg>" in svg, f"Missing or invalid icon '{name}': {svg!r}"
