"""E2E tests for F13: PWA icons, iOS meta tags, PwaUpdatePrompt & safe-area CSS."""

from __future__ import annotations

import re
from pathlib import Path

from tests.e2e.helpers.artifacts import (
    parse_html_meta,
    parse_png_info,
    read_all_css,
    run_js_scenario,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ICON_NAMES = [
    "icon-192.png",
    "icon-512.png",
    "icon-maskable-512.png",
    "apple-touch-icon.png",
]


# ---------------------------------------------------------------------------
# Tier 1: Core Functionality (5 tests)
# ---------------------------------------------------------------------------


def test_f13_t1_pwa_icons_exist_public_and_dist():
    for name in ICON_NAMES:
        assert (REPO_ROOT / "public" / "pwa" / name).is_file(), f"Missing public/pwa/{name}"
        assert (REPO_ROOT / "dist" / "pwa" / name).is_file(), f"Missing dist/pwa/{name}"


def test_f13_t1_index_html_ios_meta_tags():
    parsed = parse_html_meta(REPO_ROOT / "index.html")
    meta = parsed["meta_by_name"]
    assert "viewport-fit=cover" in meta.get("viewport", "")
    assert meta.get("apple-mobile-web-app-capable", "").lower() == "yes"
    assert meta.get("apple-mobile-web-app-status-bar-style", "") != ""
    assert meta.get("theme-color", "") != ""
    apple_links = [
        lnk for lnk in parsed["links"]
        if "apple-touch-icon" in lnk.get("rel", "").lower()
    ]
    assert len(apple_links) >= 1


def test_f13_t1_pwa_update_prompt_need_refresh_toast():
    res = run_js_scenario(
        {
            "action": "f13_pwa_prompt",
            "mode": "production",
            "triggerNeedRefresh": True,
        }
    )
    d = res["data"]
    assert d["registerCalls"] >= 1
    assert d["visibleToastBeforeAction"] is True
    assert "nuova versione disponibile" in d["bodyText"].lower()
    assert d["hasAggiornaBtn"] is True


def test_f13_t1_pwa_update_prompt_aggiorna_calls_update_sw():
    res = run_js_scenario(
        {
            "action": "f13_pwa_prompt",
            "mode": "production",
            "triggerNeedRefresh": True,
            "click": "aggiorna",
        }
    )
    d = res["data"]
    assert True in d["updateSwCalls"]


def test_f13_t1_style_css_safe_area_and_pwa_classes():
    css = read_all_css(REPO_ROOT)
    assert "env(safe-area-inset-" in css
    assert re.search(r"\.[a-z0-9_-]*pwa[a-z0-9_-]*", css, re.IGNORECASE), "Missing PWA toast styles in src/style.css"
    assert re.search(r"\.[a-z0-9_-]*(auth|login|oauth)[a-z0-9_-]*", css, re.IGNORECASE), "Missing OAuth login overlay styles in src/style.css"


# ---------------------------------------------------------------------------
# Tier 2: Edge Cases, Negative & Boundary Conditions (5 tests)
# ---------------------------------------------------------------------------


def test_f13_t2_png_headers_decode_and_dimensions():
    expected = {
        "icon-192.png": (192, 192),
        "icon-512.png": (512, 512),
        "icon-maskable-512.png": (512, 512),
    }
    for name, (exp_w, exp_h) in expected.items():
        info = parse_png_info(REPO_ROOT / "public" / "pwa" / name)
        assert info["valid"] is True, f"Invalid PNG: {name}"
        assert (info["width"], info["height"]) == (exp_w, exp_h), f"Unexpected size for {name}: {info}"

    apple_info = parse_png_info(REPO_ROOT / "public" / "pwa" / "apple-touch-icon.png")
    assert apple_info["valid"] is True
    assert apple_info["width"] >= 180
    assert apple_info["width"] == apple_info["height"]


def test_f13_t2_pwa_update_prompt_dismiss_no_reload():
    res = run_js_scenario(
        {
            "action": "f13_pwa_prompt",
            "mode": "production",
            "triggerNeedRefresh": True,
            "click": "dismiss",
        }
    )
    d = res["data"]
    assert d["hasDismissBtn"] is True
    assert d["updateSwCalls"] == []
    assert d["visibleToastAfterAction"] is False


def test_f13_t2_pwa_update_prompt_idempotent_on_repeated_refresh():
    res = run_js_scenario(
        {
            "action": "f13_pwa_prompt",
            "mode": "production",
            "triggerNeedRefresh": True,
            "repeatNeedRefresh": True,
        }
    )
    assert res["data"]["toastCount"] == 1


def test_f13_t2_pwa_update_prompt_safe_without_sw_support():
    res = run_js_scenario(
        {
            "action": "f13_pwa_prompt",
            "mode": "production",
            "serviceWorkerSupported": False,
            "throwOnRegisterSw": True,
        }
    )
    assert res["ok"] is True


def test_f13_t2_dist_index_html_has_manifest_and_apple_icon():
    dist_index = REPO_ROOT / "dist" / "index.html"
    assert dist_index.is_file(), "dist/index.html missing"
    parsed = parse_html_meta(dist_index)
    manifest_links = [
        lnk for lnk in parsed["links"]
        if "manifest" in lnk.get("rel", "").lower()
        and "manifest.webmanifest" in lnk.get("href", "")
    ]
    apple_links = [
        lnk for lnk in parsed["links"]
        if "apple-touch-icon" in lnk.get("rel", "").lower()
        and "apple-touch-icon.png" in lnk.get("href", "")
    ]
    assert len(manifest_links) >= 1, f"Missing manifest.webmanifest link in dist/index.html: {parsed['links']}"
    assert len(apple_links) >= 1, f"Missing apple-touch-icon.png link in dist/index.html: {parsed['links']}"
