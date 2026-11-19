"""E2E tests for F8: HAClient OAuth2 (getAuth), hassUrl resolution & user identity."""

from __future__ import annotations

import json
import pytest

from tests.e2e.helpers.artifacts import run_js_scenario


# ---------------------------------------------------------------------------
# Tier 1: Core Functionality (5 tests)
# ---------------------------------------------------------------------------


def test_f8_t1_prod_oauth_with_stored_tokens():
    stored = {
        "hassUrl": "https://home.tailnet.ts.net:8443",
        "access_token": "oauth-tok-admin-1",
        "refresh_token": "ref-1",
        "expires": 9_999_999_999_999,
    }
    res = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "env": {"VITE_HA_TOKEN": ""},
            "localStorage": {"sh3d_ha_oauth_tokens": json.dumps(stored)},
            "mockHaUser": {
                "id": "u-admin",
                "name": "Nicola",
                "is_admin": True,
                "is_owner": False,
            },
        }
    )
    d = res["data"]
    assert len(d["getAuthCalls"]) >= 1
    assert d["createLongLivedTokenAuthCalls"] == []
    assert d["isMockMode"] is False
    assert d["currentUser"]["id"] == "u-admin"
    assert d["isAdmin"] is True
    assert any(s["status"] == "online" for s in d["statuses"])


def test_f8_t1_prod_emits_auth_required_without_tokens():
    res = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "env": {"VITE_HA_TOKEN": ""},
            "localStorage": {},
        }
    )
    d = res["data"]
    assert d["authStatus"] == "auth_required"
    assert d["hasLoginWithOAuth"] is True
    assert any(s["status"] == "auth_required" for s in d["statuses"])
    assert any(e.get("status") == "auth_required" for e in d["authEvents"])


def test_f8_t1_hass_url_resolution():
    res_env = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "production",
            "location": "https://app.example.com/",
            "env": {"VITE_HA_PUBLIC_URL": "https://ha.custom.ts.net:8443"},
        }
    )
    assert res_env["data"]["resolvedOAuthUrl"] == "https://ha.custom.ts.net:8443"

    res_ts = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "production",
            "location": "https://pc-fisso.tail99.ts.net/",
            "env": {"VITE_HA_PUBLIC_URL": ""},
        }
    )
    assert res_ts["data"]["resolvedOAuthUrl"] == "https://pc-fisso.tail99.ts.net:8443"


def test_f8_t1_on_auth_change_and_get_access_token():
    stored = {
        "hassUrl": "https://home.tailnet.ts.net:8443",
        "access_token": "oauth-tok-xyz-777",
        "refresh_token": "ref-xyz",
        "expires": 9_999_999_999_999,
    }
    res = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "localStorage": {"sh3d_ha_oauth_tokens": json.dumps(stored)},
            "mockHaUser": {
                "id": "u-1",
                "name": "Nicola",
                "is_admin": True,
                "is_owner": True,
            },
        }
    )
    d = res["data"]
    assert d["accessToken"] == "oauth-tok-xyz-777"
    authed_events = [e for e in d["authEvents"] if e.get("authenticated") is True]
    assert len(authed_events) >= 1
    assert authed_events[-1]["token"] == "oauth-tok-xyz-777"
    assert authed_events[-1]["user"]["id"] == "u-1"


def test_f8_t1_dev_mode_long_lived_token_and_mock_fallback():
    res_llat = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "development",
            "location": "http://localhost:3000/",
            "env": {
                "VITE_HA_TOKEN": "dev-long-lived-token-abc",
                "VITE_HA_URL": "http://localhost:8123",
            },
        }
    )
    d_llat = res_llat["data"]
    assert len(d_llat["createLongLivedTokenAuthCalls"]) >= 1
    assert d_llat["createLongLivedTokenAuthCalls"][0]["accessToken"] == "dev-long-lived-token-abc"
    assert d_llat["isMockMode"] is False

    res_mock = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "development",
            "location": "http://localhost:3000/",
            "env": {"VITE_HA_TOKEN": ""},
            "localStorage": {},
        }
    )
    d_mock = res_mock["data"]
    assert d_mock["isMockMode"] is True
    assert any(s["status"] == "mock" for s in d_mock["statuses"])


# ---------------------------------------------------------------------------
# Tier 2: Edge Cases, Negative & Boundary Conditions (5 tests)
# ---------------------------------------------------------------------------


def test_f8_t2_prod_missing_token_never_silent_mock_mode():
    res = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "env": {"VITE_HA_TOKEN": ""},
            "localStorage": {},
        }
    )
    d = res["data"]
    assert d["isMockMode"] is False
    assert all(s["status"] != "mock" for s in d["statuses"])
    assert d["authStatus"] == "auth_required"


def test_f8_t2_oauth_callback_query_params_cleaned():
    res = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/?auth_callback=1&code=abc123&state=xyz789",
            "getAuthBehavior": "exchange_callback",
            "env": {"VITE_HA_TOKEN": ""},
        }
    )
    d = res["data"]
    assert len(d["getAuthCalls"]) >= 1
    assert d["authStatus"] == "authenticated"
    assert len(d["historyCalls"]) >= 1
    assert "auth_callback=" not in d["locationHref"]
    assert "code=" not in d["locationHref"]
    assert "state=" not in d["locationHref"]


def test_f8_t2_resident_user_is_admin_false():
    stored = {
        "hassUrl": "https://home.tailnet.ts.net:8443",
        "access_token": "oauth-tok-res-2",
        "expires": 9_999_999_999_999,
    }
    res = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "localStorage": {"sh3d_ha_oauth_tokens": json.dumps(stored)},
            "mockHaUser": {
                "id": "u2",
                "name": "Residente",
                "is_admin": False,
                "is_owner": False,
            },
        }
    )
    d = res["data"]
    assert d["currentUser"]["id"] == "u2"
    assert d["isAdmin"] is False


def test_f8_t2_owner_without_is_admin_is_still_admin():
    stored = {
        "hassUrl": "https://home.tailnet.ts.net:8443",
        "access_token": "oauth-tok-owner-1",
        "expires": 9_999_999_999_999,
    }
    res = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "localStorage": {"sh3d_ha_oauth_tokens": json.dumps(stored)},
            "mockHaUser": {
                "id": "u1",
                "name": "Owner",
                "is_admin": False,
                "is_owner": True,
            },
        }
    )
    d = res["data"]
    assert d["isAdmin"] is True


def test_f8_t2_logout_clears_tokens_and_identity():
    stored = {
        "hassUrl": "https://home.tailnet.ts.net:8443",
        "access_token": "oauth-tok-logout",
        "refresh_token": "refresh-logout",
        "expires": 9_999_999_999_999,
    }
    res = run_js_scenario(
        {
            "action": "f8_connect",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "localStorage": {"sh3d_ha_oauth_tokens": json.dumps(stored)},
            "stepAfterConnect": "logout",
        }
    )
    d = res["data"]
    assert d["localStorageDump"] == {}
    assert d["currentUser"] is None
    assert d["isAdmin"] is False
    assert not d["accessToken"]
    assert d["authStatus"] == "auth_required"
    assert d["statuses"][-1]["status"] == "auth_required"
