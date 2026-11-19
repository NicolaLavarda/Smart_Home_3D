"""E2E tests for F14: Deterministic .glb versioning & SceneManager mobile perf/rAF pause."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from tests.e2e.helpers.artifacts import run_js_scenario


def _extract_glb_query(urls: list[str], filename: str = "house_optimized.glb") -> dict[str, list[str]]:
    matches = [u for u in urls if filename in u]
    assert matches, f"No fetch recorded for {filename} in {urls}"
    return parse_qs(urlparse(matches[0]).query)


# ---------------------------------------------------------------------------
# Tier 1: Core Functionality (5 tests)
# ---------------------------------------------------------------------------


def test_f14_t1_asset_loader_deterministic_glb_version():
    manifest_a = {
        "version": "2026.11.18",
        "ha_entities": {"light.forno": {}},
        "cameras": {"Cam_Carraio": {"fov_v_deg": 42}},
        "ground_colliders": [],
    }
    res = run_js_scenario(
        {
            "action": "f14_asset_loader",
            "mode": "production",
            "secondLoad": True,
            "secondManifest": manifest_a,
            "fetchRoutes": [
                {"match": "/models/scene_manifest.json", "status": 200, "json": manifest_a},
                {"match": "/models/house_optimized.glb", "status": 200, "glb": True},
            ],
        }
    )
    q1 = _extract_glb_query(res["data"]["urls"], "house_optimized.glb")
    q2 = _extract_glb_query(res["data"]["secondUrls"], "house_optimized.glb")
    assert "v" in q1 and q1["v"][0]
    assert q1["v"] == q2["v"]


def test_f14_t1_asset_loader_version_changes_with_manifest():
    manifest_a = {
        "version": "1.0.0",
        "ha_entities": {},
        "cameras": {"Cam_Carraio": {"fov_v_deg": 42}},
        "ground_colliders": [],
    }
    manifest_b = {
        "version": "2.0.0",
        "ha_entities": {"light.forno": {}},
        "cameras": {"Cam_Carraio": {"fov_v_deg": 48}},
        "ground_colliders": [{"object_name": "Floor_Salotto"}],
    }
    res = run_js_scenario(
        {
            "action": "f14_asset_loader",
            "mode": "production",
            "secondLoad": True,
            "secondManifest": manifest_b,
            "fetchRoutes": [
                {"match": "/models/scene_manifest.json", "status": 200, "json": manifest_a},
                {"match": "/models/house_optimized.glb", "status": 200, "glb": True},
            ],
        }
    )
    q1 = _extract_glb_query(res["data"]["urls"], "house_optimized.glb")
    q2 = _extract_glb_query(res["data"]["secondUrls"], "house_optimized.glb")
    assert "v" in q1 and "v" in q2
    assert q1["v"][0] != q2["v"][0]


def test_f14_t1_scene_manager_pauses_raf_on_hidden():
    res = run_js_scenario(
        {
            "action": "f14_scene_manager",
            "mode": "production",
            "viewport": {"width": 1920, "height": 1080, "dpr": 2, "pointer": "fine", "maxTouchPoints": 0},
            "testVisibility": True,
        }
    )
    d = res["data"]
    assert d["initialRafCount"] == 1
    assert d["hiddenRafCount"] == 0
    assert d["ticksWhileHidden"] == 0


def test_f14_t1_scene_manager_resumes_and_resets_clock():
    res = run_js_scenario(
        {
            "action": "f14_scene_manager",
            "mode": "production",
            "viewport": {"width": 1920, "height": 1080, "dpr": 2, "pointer": "fine", "maxTouchPoints": 0},
            "testVisibility": True,
        }
    )
    d = res["data"]
    assert d["resumedRafCount"] == 1
    assert d["resumedFirstDelta"] is not None
    assert d["resumedFirstDelta"] < 0.2


def test_f14_t1_scene_manager_desktop_quality_defaults():
    res = run_js_scenario(
        {
            "action": "f14_scene_manager",
            "mode": "production",
            "viewport": {"width": 1920, "height": 1080, "dpr": 2, "pointer": "fine", "maxTouchPoints": 0},
        }
    )
    d = res["data"]
    assert d["initialPixelRatio"] <= 2
    assert d["initialShadowSize"] == {"width": 2048, "height": 2048}


# ---------------------------------------------------------------------------
# Tier 2: Edge Cases, Negative & Boundary Conditions (5 tests)
# ---------------------------------------------------------------------------


def test_f14_t2_asset_loader_never_uses_date_now():
    res = run_js_scenario(
        {
            "action": "f14_asset_loader",
            "mode": "production",
            "fetchRoutes": [
                {
                    "match": "/models/scene_manifest.json",
                    "status": 200,
                    "json": {"ha_entities": {}, "cameras": {}, "ground_colliders": []},
                },
                {"match": "/models/house_optimized.glb", "status": 200, "glb": True},
            ],
        }
    )
    for url in res["data"]["urls"]:
        q = parse_qs(urlparse(url).query)
        assert "t" not in q, f"Legacy Date.now() cache-buster '?t=' found in {url}"


def test_f14_t2_asset_loader_raw_glb_fallback_also_versioned():
    res = run_js_scenario(
        {
            "action": "f14_asset_loader",
            "mode": "production",
            "fetchRoutes": [
                {
                    "match": "/models/scene_manifest.json",
                    "status": 200,
                    "json": {"version": "v9", "ha_entities": {}, "cameras": {}, "ground_colliders": []},
                },
                {"match": "/models/house_optimized.glb", "status": 404, "text": "Not Found"},
                {"match": "/models/house_raw.glb", "status": 200, "glb": True},
            ],
        }
    )
    urls = res["data"]["urls"]
    q_raw = _extract_glb_query(urls, "house_raw.glb")
    assert "v" in q_raw and q_raw["v"][0]
    assert "t" not in q_raw


def test_f14_t2_asset_loader_manifest_fetch_failure_safe_version():
    res = run_js_scenario(
        {
            "action": "f14_asset_loader",
            "mode": "production",
            "fetchRoutes": [
                {"match": "/models/scene_manifest.json", "status": 404, "text": "Not Found"},
                {"match": "/models/house_optimized.glb", "status": 200, "glb": True},
            ],
        }
    )
    q = _extract_glb_query(res["data"]["urls"], "house_optimized.glb")
    assert "v" in q
    ver = q["v"][0]
    assert ver and ver.lower() not in ("undefined", "null", "nan")
    assert "t" not in q


def test_f14_t2_scene_manager_mobile_touch_caps_dpr_and_shadows():
    res = run_js_scenario(
        {
            "action": "f14_scene_manager",
            "mode": "production",
            "viewport": {
                "width": 390,
                "height": 844,
                "dpr": 3,
                "pointer": "coarse",
                "maxTouchPoints": 5,
            },
            "triggerResize": True,
        }
    )
    d = res["data"]
    assert d["initialPixelRatio"] <= 1.5
    assert d["pixelRatioAfterResize"] <= 1.5
    assert d["initialShadowSize"]["width"] <= 1024
    assert d["initialShadowSize"]["height"] <= 1024


def test_f14_t2_scene_manager_rapid_visibility_toggles_single_raf():
    res = run_js_scenario(
        {
            "action": "f14_scene_manager",
            "mode": "production",
            "viewport": {"width": 1280, "height": 720, "dpr": 1, "pointer": "fine", "maxTouchPoints": 0},
            "testRapidToggle": True,
        }
    )
    assert res["data"]["rapidToggleRafCount"] == 1
