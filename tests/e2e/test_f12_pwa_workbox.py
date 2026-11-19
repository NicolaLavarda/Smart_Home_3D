"""E2E tests for F12: vite-plugin-pwa installation, Workbox rules & zero-secret dist bundle."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.e2e.helpers.artifacts import inspect_vite_config, scan_dist_js_secrets

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = REPO_ROOT / "dist"


def _pattern_to_text(pattern_obj) -> str:
    if isinstance(pattern_obj, str):
        return pattern_obj
    if isinstance(pattern_obj, dict):
        return f"{pattern_obj.get('source', '')} {pattern_obj.get('string', '')}"
    return str(pattern_obj or "")


def _find_runtime_rule(pwa_opts: dict, needle: str) -> dict | None:
    rules = (pwa_opts or {}).get("workbox", {}).get("runtimeCaching", [])
    for rule in rules:
        pat = _pattern_to_text(rule.get("urlPattern"))
        if needle in pat:
            return rule
    return None


# ---------------------------------------------------------------------------
# Tier 1: Core Functionality (5 tests)
# ---------------------------------------------------------------------------


def test_f12_t1_vite_plugin_pwa_installed():
    pkg = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert "vite-plugin-pwa" in all_deps
    assert (REPO_ROOT / "node_modules" / "vite-plugin-pwa").is_dir()


def test_f12_t1_vite_config_pwa_prompt_and_manifest():
    cfg = inspect_vite_config("production")
    assert cfg["hasPwaPlugin"] is True
    pwa = cfg.get("pwaOptions") or {}
    assert pwa.get("registerType") == "prompt"

    manifest = pwa.get("manifest") or {}
    assert manifest.get("display") == "standalone"
    assert manifest.get("lang", "").lower().startswith("it") or "smart home" in manifest.get("name", "").lower()

    icons = manifest.get("icons") or []
    sizes = {str(ic.get("sizes", "")) for ic in icons}
    purposes = " ".join(str(ic.get("purpose", "")) for ic in icons).lower()
    assert "192x192" in sizes
    assert "512x512" in sizes
    assert "maskable" in purposes


def test_f12_t1_dist_manifest_webmanifest_valid():
    manifest_path = DIST_DIR / "manifest.webmanifest"
    assert manifest_path.is_file(), "dist/manifest.webmanifest missing"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data.get("display") == "standalone"
    assert data.get("start_url")
    assert isinstance(data.get("icons"), list) and len(data["icons"]) >= 2


def test_f12_t1_dist_sw_and_workbox_present():
    assert (DIST_DIR / "sw.js").is_file(), "dist/sw.js missing"
    workbox_files = list(DIST_DIR.glob("workbox-*.js"))
    assert len(workbox_files) >= 1, "dist/workbox-*.js missing"


def test_f12_t1_workbox_manifest_and_glb_caching():
    cfg = inspect_vite_config("production")
    pwa = cfg.get("pwaOptions") or {}
    assert pwa, "VitePWA options not exposed in vite.config.js"

    manifest_rule = _find_runtime_rule(pwa, "scene_manifest")
    assert manifest_rule is not None, "Missing runtimeCaching rule for scene_manifest.json"
    assert manifest_rule.get("handler") == "NetworkFirst"

    glb_rule = _find_runtime_rule(pwa, "glb")
    assert glb_rule is not None, "Missing runtimeCaching rule for .glb models"
    assert glb_rule.get("handler") == "CacheFirst"

    draco_rule = _find_runtime_rule(pwa, "gstatic")
    assert draco_rule is not None, "Missing runtimeCaching rule for Draco CDN"
    assert draco_rule.get("handler") == "CacheFirst"

    sw_text = (DIST_DIR / "sw.js").read_text(encoding="utf-8", errors="replace")
    assert "scene_manifest" in sw_text
    assert "glb" in sw_text
    assert "gstatic" in sw_text


# ---------------------------------------------------------------------------
# Tier 2: Edge Cases, Negative & Boundary Conditions (5 tests)
# ---------------------------------------------------------------------------


def test_f12_t2_glb_excluded_from_precache():
    cfg = inspect_vite_config("production")
    wb = (cfg.get("pwaOptions") or {}).get("workbox", {})
    ignores = " ".join(str(x) for x in wb.get("globIgnores", []))
    patterns = " ".join(str(x) for x in wb.get("globPatterns", []))
    assert ".glb" in ignores or "glb" not in patterns

    sw_text = (DIST_DIR / "sw.js").read_text(encoding="utf-8", errors="replace")
    precache_match = re.search(r"precacheAndRoute\(\s*(\[.*?\])\s*[,\)]", sw_text, re.DOTALL)
    assert precache_match, "precacheAndRoute manifest not found in dist/sw.js"
    precache_block = precache_match.group(1)
    assert ".glb" not in precache_block.lower()
    assert "house_optimized.glb" not in precache_block
    assert "house_raw.glb" not in precache_block


def test_f12_t2_workbox_network_only_sensitive_routes():
    cfg = inspect_vite_config("production")
    pwa = cfg.get("pwaOptions") or {}
    rules = pwa.get("workbox", {}).get("runtimeCaching", [])
    network_only_patterns = " ".join(
        _pattern_to_text(r.get("urlPattern"))
        for r in rules
        if r.get("handler") == "NetworkOnly"
    )
    for required_fragment in ("api", "ws", "go2rtc", "auth_callback"):
        assert required_fragment in network_only_patterns, (
            f"Missing NetworkOnly rule for '{required_fragment}' in workbox.runtimeCaching"
        )

    sw_text = (DIST_DIR / "sw.js").read_text(encoding="utf-8", errors="replace")
    assert "NetworkOnly" in sw_text


def test_f12_t2_navigate_fallback_excludes_backend_and_oauth():
    cfg = inspect_vite_config("production")
    wb = (cfg.get("pwaOptions") or {}).get("workbox", {})
    if wb.get("navigateFallback") is not None:
        denylist = " ".join(_pattern_to_text(p) for p in wb.get("navigateFallbackDenylist", []))
        for required_fragment in ("api", "ws", "go2rtc", "auth_callback"):
            assert required_fragment in denylist, (
                f"navigateFallbackDenylist must exclude '{required_fragment}'"
            )


def test_f12_t2_dist_assets_zero_secret_leaks():
    assert (DIST_DIR / "assets").is_dir(), "dist/assets directory missing"
    findings = scan_dist_js_secrets(DIST_DIR)
    assert findings == [], f"Secret leaks found in dist/assets/: {findings}"


def test_f12_t2_dev_proxy_plugin_intact_in_vite_config():
    cfg = inspect_vite_config("development")
    assert "ha-camera-bridge-proxy" in cfg.get("pluginNames", [])
    assert scan_dist_js_secrets(DIST_DIR) == []
