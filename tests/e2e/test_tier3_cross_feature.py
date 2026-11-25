from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.e2e.helpers.artifacts import read_all_css
from tests.e2e.helpers.ps_bat_harness import (
    build_isolated_workspace,
    run_bat_dry_run,
    run_ps_dry_run,
)
from tests.e2e.helpers.tier34_js_harness import (
    resolve_vite_config_json,
    run_vite_module_script,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _extract_set_cookie_header(resp) -> str:
    headers = resp.headers.get_list("set-cookie") if hasattr(resp.headers, "get_list") else []
    if not headers:
        raw = resp.headers.get("set-cookie", "")
        headers = [raw] if raw else []
    for h in headers:
        if "sh3d_session=" in h:
            return h
    return ""


# =============================================================================
# Tier 3 — Pairwise Cross-Feature Integration Tests (20 tests)
# =============================================================================


def test_t3_01_f3_f6_caddy_forward_auth_and_fastapi_auth_verify(fake_ha_server, isolated_app_factory):
    """T3-01 (F3+F6): Caddyfile forward_auth URI matches FastAPI /api/v1/auth/verify (401 vs 200)."""
    caddy_text = (REPO_ROOT / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "forward_auth 127.0.0.1:8765" in caddy_text
    assert "uri /api/v1/auth/verify" in caddy_text
    assert "/go2rtc/api/webrtc*" in caddy_text
    assert "/go2rtc/api/ws*" in caddy_text

    app = isolated_app_factory(
        auth_required=True,
        ha_local_url=fake_ha_server.base_url,
        session_secret_key="t3-01-secret-" + "a" * 48,
    )
    with TestClient(app) as client:
        unauth = client.get("/api/v1/auth/verify")
        assert unauth.status_code == 401

        bearer_ok = client.get(
            "/api/v1/auth/verify",
            headers={"Authorization": "Bearer tok-admin"},
        )
        assert bearer_ok.status_code == 200

        sess = client.post(
            "/api/v1/auth/session",
            headers={"Authorization": "Bearer tok-resident"},
        )
        assert sess.status_code == 200
        cookie_ok = client.get("/api/v1/auth/verify")
        assert cookie_ok.status_code == 200


def test_t3_02_f4_f6_go2rtc_bind_and_caddy_allowlist_403():
    """T3-02 (F4+F6): go2rtc.yaml binds localhost-only API/RTSP and Caddy exposes only webrtc*/ws* with 403 elsewhere."""
    go2rtc_cfg = yaml.safe_load((REPO_ROOT / "go2rtc" / "go2rtc.yaml").read_text(encoding="utf-8"))
    assert go2rtc_cfg["api"]["listen"] == "127.0.0.1:1984"
    assert go2rtc_cfg["api"]["origin"] == ""
    assert go2rtc_cfg["rtsp"]["listen"] == "127.0.0.1:8554"

    caddy_text = (REPO_ROOT / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "handle /go2rtc/api/webrtc*" in caddy_text
    assert "handle /go2rtc/api/ws*" in caddy_text
    assert caddy_text.count("uri strip_prefix /go2rtc") >= 2
    assert caddy_text.count("reverse_proxy 127.0.0.1:1984") >= 2
    assert re.search(r"handle\s+/go2rtc/\*\s*\{[^}]*403", caddy_text, re.DOTALL)


def test_t3_03_f1_f3_f9_spatial_stream_client_session_and_ws_auth(fake_ha_server, isolated_app_factory):
    """T3-03 (F1+F3+F9): POST /api/v1/auth/session cookie flags, SpatialStreamClient pre-WS auth, and /ws/spatial 4401."""
    app = isolated_app_factory(
        auth_required=True,
        ha_local_url=fake_ha_server.base_url,
        session_secret_key="t3-03-secret-" + "b" * 48,
    )
    with TestClient(app, base_url="https://testserver") as client:
        # Unauthenticated WS must close with 4401
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/spatial") as ws:
                ws.receive_text()
        assert exc_info.value.code == 4401

        # Authenticate via POST /api/v1/auth/session behind HTTPS proxy header
        resp = client.post(
            "/api/v1/auth/session",
            headers={"Authorization": "Bearer tok-admin", "X-Forwarded-Proto": "https"},
        )
        assert resp.status_code == 200
        set_cookie = _extract_set_cookie_header(resp)
        assert "sh3d_session=" in set_cookie
        assert "httponly" in set_cookie.lower()
        assert "samesite=strict" in set_cookie.lower()
        assert "secure" in set_cookie.lower()
        assert "path=/" in set_cookie.lower()

        # Authenticated WS connects and receives initial server_status
        with client.websocket_connect("wss://testserver/ws/spatial") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "server_status"

    # Frontend SpatialStreamClient exchanges token with credentials: 'include'
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const fetchCalls = [];
        globalThis.fetch = async (url, init = {}) => {
          fetchCalls.push({ url, method: init.method, credentials: init.credentials, headers: init.headers });
          return { ok: true, status: 200, json: async () => ({ authenticated: true, user: { user_id: 'u1', is_admin: true } }) };
        };
        const { SpatialStreamClient } = await server.ssrLoadModule('/src/spatial/network/SpatialStreamClient.js');
        const client = new SpatialStreamClient();
        const ok = await client.authenticateWithHaToken('ha_tok_123');
        return { ok, isAuthenticated: client.isAuthenticated, fetchCalls };
        """,
    )
    assert js_res["ok"] is True
    assert js_res["isAuthenticated"] is True
    assert js_res["fetchCalls"][0]["url"] == "/api/v1/auth/session"
    assert js_res["fetchCalls"][0]["method"] == "POST"
    assert js_res["fetchCalls"][0]["credentials"] == "include"


def test_t3_04_f2_f6_f9_config_cors_caddy_8765_and_spatial_client_prod_urls(
    monkeypatch, fake_ha_server, isolated_app_factory
):
    """T3-04 (F2+F6+F9): Config defaults 127.0.0.1:8765 + strict CORS, Caddy routes :8765, SpatialStreamClient uses same-origin."""
    for k in list(os.environ.keys()):
        if k.startswith("SPATIAL_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SPATIAL_ALLOWED_ORIGINS", "https://pc-fisso.tail123.ts.net")

    from spatial_server.config import SpatialServerConfig

    cfg = SpatialServerConfig.from_env()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8765
    assert cfg.allowed_origins == ("https://pc-fisso.tail123.ts.net",) or list(cfg.allowed_origins) == [
        "https://pc-fisso.tail123.ts.net"
    ]

    app = isolated_app_factory(
        auth_required=True,
        ha_local_url=fake_ha_server.base_url,
        allowed_origins=("https://pc-fisso.tail123.ts.net",),
    )
    with TestClient(app) as client:
        allowed_preflight = client.options(
            "/api/v1/status",
            headers={"Origin": "https://pc-fisso.tail123.ts.net", "Access-Control-Request-Method": "GET"},
        )
        assert allowed_preflight.headers.get("access-control-allow-origin") == "https://pc-fisso.tail123.ts.net"
        assert allowed_preflight.headers.get("access-control-allow-credentials") == "true"

        evil_preflight = client.options(
            "/api/v1/status",
            headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "GET"},
        )
        assert evil_preflight.headers.get("access-control-allow-origin") != "https://evil.example.com"

    caddy_text = (REPO_ROOT / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "handle /api/v1/*" in caddy_text
    assert "handle /ws/spatial" in caddy_text
    assert "reverse_proxy 127.0.0.1:8765" in caddy_text

    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const { SpatialStreamClient } = await server.ssrLoadModule('/src/spatial/network/SpatialStreamClient.js');
        const c = new SpatialStreamClient();
        return { baseUrl: c.baseUrl, wsUrl: c.wsUrl };
        """,
    )
    assert js_res["baseUrl"] == ""
    assert js_res["wsUrl"] == "wss://pc-fisso.tail123.ts.net/ws/spatial"


def test_t3_05_f8_f9_f11_ha_client_oauth_main_wiring_and_logout(fake_ha_server, isolated_app_factory):
    """T3-05 (F8+F9+F11): HAClient emits auth_required in prod, main.js wires auth & logout, backend /logout clears cookie."""
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const { HAClient } = await server.ssrLoadModule('/src/ha/HAClient.js');
        const ha = new HAClient();
        const statuses = [];
        ha.onStatusChange((s, d) => statuses.push({ s, d }));
        await ha.connect();
        return {
          statuses,
          isMockMode: ha.isMockMode,
          hasLogin: typeof ha.loginWithOAuth === 'function',
          hasOnAuthChange: typeof ha.onAuthChange === 'function',
          hasGetAccessToken: typeof ha.getAccessToken === 'function',
          hasLogout: typeof ha.logout === 'function',
        };
        """,
    )
    assert any(item["s"] == "auth_required" for item in js_res["statuses"]), f"Expected auth_required: {js_res}"
    assert js_res["isMockMode"] is False
    assert js_res["hasLogin"] is True
    assert js_res["hasOnAuthChange"] is True
    assert js_res["hasGetAccessToken"] is True
    assert js_res["hasLogout"] is True

    main_js = (REPO_ROOT / "src" / "main.js").read_text(encoding="utf-8")
    assert "onAuthChange" in main_js
    assert "authenticateWithHaToken" in main_js
    assert "auth/logout" in main_js or "logout" in main_js

    app = isolated_app_factory(auth_required=True, ha_local_url=fake_ha_server.base_url)
    with TestClient(app) as client:
        client.post("/api/v1/auth/session", headers={"Authorization": "Bearer tok-admin"})
        logout_resp = client.post("/api/v1/auth/logout")
        assert logout_resp.status_code == 200
        set_cookie = _extract_set_cookie_header(logout_resp)
        assert "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower()
        assert client.get("/api/v1/auth/verify").status_code == 401


def test_t3_06_f1_f3_f11_backend_403_and_frontend_rbac_ui_hiding(fake_ha_server, isolated_app_factory):
    """T3-06 (F1+F3+F11): Non-admin gets 403 on backend mutative routes and UI hides/blocks calibration & simulator."""
    app = isolated_app_factory(auth_required=True, ha_local_url=fake_ha_server.base_url)
    with TestClient(app) as client:
        sess = client.post("/api/v1/auth/session", headers={"Authorization": "Bearer tok-resident"})
        assert sess.status_code == 200
        assert sess.json()["user"]["is_admin"] is False

        assert client.get("/api/v1/status").status_code == 200
        assert client.get("/api/v1/tracks", params={"t_start": 0, "t_end": 10}).status_code == 200
        assert client.get("/api/v1/timeline-density", params={"t_start": 0, "t_end": 10}).status_code == 200
        assert client.get("/api/v1/calibration/Cam_Carraio").status_code == 200

        valid_pnp_payload = {
            "camera_id": "Cam_Carraio",
            "correspondences": [
                {"world_point": [0.0, 0.0, 5.0], "pixel_uv": [0.2, 0.3]},
                {"world_point": [2.0, 0.0, 5.0], "pixel_uv": [0.7, 0.3]},
                {"world_point": [0.0, 0.0, 9.0], "pixel_uv": [0.25, 0.65]},
                {"world_point": [2.0, 0.0, 9.0], "pixel_uv": [0.75, 0.65]},
            ],
        }
        valid_det_payload = [
            {
                "camera_id": "Cam_Carraio",
                "timestamp": 1700000000.0,
                "class_label": "person",
                "confidence": 0.9,
                "bbox": {"x_min": 0.4, "y_min": 0.4, "x_max": 0.5, "y_max": 0.8},
            }
        ]
        assert client.post("/api/v1/calibration/solve-pnp", json=valid_pnp_payload).status_code == 403
        assert client.post("/api/v1/calibration/Cam_Carraio", json={"camera_id": "Cam_Carraio", "fov_h_deg": 80}).status_code == 403
        assert client.post("/api/v1/ingestion/mode", json={"mode": "synthetic"}).status_code == 403
        assert client.post("/api/v1/detections", json=valid_det_payload).status_code == 403

    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        const { documentObj, makeElement } = installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const { TopBar } = await server.ssrLoadModule('/src/ui/TopBar.js');
        const { SecurityCameraModal } = await server.ssrLoadModule('/src/devices/camera/SecurityCameraModal.js');
        const { CalibrationAssistantUI } = await server.ssrLoadModule('/src/spatial/calibration/CalibrationAssistantUI.js');

        const haResident = {
          isAdmin: false,
          isTailscale: false,
          currentUser: { id: 'res_1', name: 'Residente', is_admin: false, is_owner: false },
          authStatus: 'authenticated',
          onStatusChange: () => () => {},
          onAuthChange: () => () => {},
          loginWithOAuth: async () => {},
          logout: async () => {},
        };

        const topContainer = makeElement('header', 'top-bar');
        new TopBar(topContainer, {
          sceneManager: { isNightMode: false, setNightMode() {} },
          cameraController: { resetView() {}, flyTo() {} },
          cameraProjector: { toggleFrustums: () => false },
          interactionManager: { toggleBadges: () => true },
          haClient: haResident,
          calibrationAssistant: null,
        });
        const topCalibBtn = topContainer.querySelector('#btn-open-cam-calib');
        const topCalibHidden = !topCalibBtn || topCalibBtn.hidden || topCalibBtn.style?.display === 'none' || topCalibBtn.classList.contains('hidden');

        const modalContainer = makeElement('div', 'cam-modal');
        const mockCtrl = {
          findMatchingBlenderCameraName: () => 'Cam_Carraio',
          haClient: haResident,
          spatialStreamClient: { fetchStatus: async () => ({ ingestion_mode: 'synthetic' }) },
          videoStreamManager: { attachToVideoElement: async () => ({ mode: 'snapshot', latencyMs: 50, getStatus: () => ({}) }) },
        };
        const modal = new SecurityCameraModal(mockCtrl);
        await modal.render(modalContainer, { haClient: haResident, assetLoader: { manifest: { cameras: { Cam_Carraio: {} } } } });
        const modalCalibBtn = modalContainer.querySelector('#btn-camera-calibrate');
        const modalSimBtn = modalContainer.querySelector('#btn-toggle-simulator');
        const isHidden = (b) => !b || b.hidden || b.style?.display === 'none' || b.classList.contains('hidden');

        const calibUi = new CalibrationAssistantUI({
          sceneManager: { scene: { add() {}, remove() {} }, addUpdateCallback() {}, removeUpdateCallback() {} },
          cameraController: {},
          cameraProjector: {},
          videoStreamManager: {},
          spatialStreamClient: {},
          assetLoader: { manifest: { cameras: { Cam_Carraio: {} } } },
          haClient: haResident,
        });
        await calibUi.open('Cam_Carraio');

        return {
          topCalibHidden,
          modalCalibHidden: isHidden(modalCalibBtn),
          modalSimHidden: isHidden(modalSimBtn),
          calibIsOpen: calibUi.isOpen,
        };
        """,
    )
    assert js_res["topCalibHidden"] is True
    assert js_res["modalCalibHidden"] is True
    assert js_res["modalSimHidden"] is True
    assert js_res["calibIsOpen"] is False


def test_t3_07_f3_f10_ha_snapshot_fallback_prod_url_and_bearer_forwarding(fake_ha_server, isolated_app_factory):
    """T3-07 (F3+F10): HaSnapshotFallbackStream hits /api/v1/ha-camera/snapshot/... in prod and FastAPI forwards caller Bearer."""
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const requests = [];
        globalThis.fetch = async (url, init = {}) => {
          requests.push({ url, credentials: init.credentials, headers: init.headers || {} });
          return { ok: true, status: 200, blob: async () => new Blob([]) };
        };
        globalThis.createImageBitmap = async () => ({ width: 640, height: 360, close() {} });
        const { HaSnapshotFallbackStream } = await server.ssrLoadModule('/src/video/HaSnapshotFallbackStream.js');
        const stream = new HaSnapshotFallbackStream('carraio_main', {
          cameraEntityId: 'camera.carraio_scorrevole',
          haClient: { isTailscale: true, getAccessToken: () => 'user-ha-token-123' },
        });
        const video = document.createElement('video');
        await stream.connect(video);
        await new Promise((r) => setTimeout(r, 80));
        stream.disconnect();
        return { requests };
        """,
    )
    assert js_res["requests"], "Expected snapshot fetch request"
    req0 = js_res["requests"][0]
    assert "/api/v1/ha-camera/snapshot/camera.carraio_scorrevole" in req0["url"]
    assert not req0["url"].startswith("/api/ha-camera/snapshot"), "Must not collide with dev Vite snapshot URL"
    assert req0["credentials"] == "include"

    app = isolated_app_factory(
        auth_required=True,
        ha_local_url=fake_ha_server.base_url,
        ha_token="",
    )
    with TestClient(app) as client:
        snap = client.get(
            "/api/v1/ha-camera/snapshot/camera.carraio_scorrevole",
            headers={"Authorization": "Bearer tok-resident"},
        )
        assert snap.status_code == 200
        assert snap.headers["content-type"].startswith("image/")
        assert len(snap.content) > 0


def test_t3_08_f6_f10_video_stream_manager_urls_and_caddy_forward_auth_paths():
    """T3-08 (F6+F10): VideoStreamManager, Go2RtcWebRTCStream, and Go2RtcMSEStream align with Caddy forward_auth paths."""
    caddy_text = (REPO_ROOT / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "handle /go2rtc/api/webrtc*" in caddy_text
    assert "handle /go2rtc/api/ws*" in caddy_text

    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const fetchLog = [];
        const wsLog = [];
        globalThis.fetch = async (url, init = {}) => {
          fetchLog.push({ url, credentials: init.credentials });
          return { ok: false, status: 503, text: async () => 'err' };
        };
        globalThis.RTCPeerConnection = class {
          addTransceiver() {}
          async createOffer() { return { type: 'offer', sdp: 'v=0' }; }
          async setLocalDescription() {}
          async setRemoteDescription() {}
          close() {}
          get iceGatheringState() { return 'complete'; }
        };
        globalThis.WebSocket = class {
          constructor(url) { wsLog.push(url); setTimeout(() => this.onerror?.(), 5); }
          close() {}
        };
        globalThis.MediaSource = class {
          static isTypeSupported() { return true; }
          addEventListener(ev, fn) { if (ev === 'sourceopen') setTimeout(fn, 2); }
        };

        const { VideoStreamManager } = await server.ssrLoadModule('/src/video/VideoStreamManager.js');
        const mgr = new VideoStreamManager({ haClient: { isTailscale: true } });
        const chain = mgr.buildProviderChain('carraio_main', 'auto');
        const webrtc = chain[0];
        const mse = chain[1];
        const v = document.createElement('video');
        await webrtc.connect(v).catch(() => {});
        await mse.connect(v).catch(() => {});
        return {
          go2rtcUrl: mgr.go2rtcUrl,
          webrtcTimeoutMs: webrtc.timeoutMs,
          fetchLog,
          wsLog,
        };
        """,
    )
    assert js_res["go2rtcUrl"] == "https://pc-fisso.tail123.ts.net/go2rtc"
    assert js_res["webrtcTimeoutMs"] == 2200
    assert js_res["fetchLog"][0]["url"].startswith("https://pc-fisso.tail123.ts.net/go2rtc/api/webrtc")
    assert js_res["fetchLog"][0]["credentials"] == "include"
    assert js_res["wsLog"][0].startswith("wss://pc-fisso.tail123.ts.net/go2rtc/api/ws")


def test_t3_09_f6_f12_caddy_cache_control_and_vite_pwa_workbox():
    """T3-09 (F6+F12): Caddy Cache-Control headers match VitePWA registerType='prompt' & Workbox rules."""
    caddy_text = (REPO_ROOT / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    for path_tok in ("/", "/index.html", "/sw.js", "/workbox-*.js", "/manifest.webmanifest", "/models/scene_manifest.json"):
        assert path_tok in caddy_text
    assert "no-cache, must-revalidate" in caddy_text
    assert "immutable" in caddy_text

    cfg = resolve_vite_config_json(REPO_ROOT, mode="production")
    assert cfg["pwaOptions"] is not None, "VitePWA plugin must be configured in vite.config.js"
    assert cfg["pwaOptions"]["registerType"] == "prompt"

    dist_dir = REPO_ROOT / "dist"
    if dist_dir.exists():
        assert (dist_dir / "sw.js").exists()
        assert (dist_dir / "manifest.webmanifest").exists()
        assert list((dist_dir / "assets").glob("*.js")), "Expected hashed JS assets under dist/assets/"


def test_t3_10_f12_f14_asset_loader_deterministic_version_and_workbox_glb_cache():
    """T3-10 (F12+F14): AssetLoader uses deterministic ?v=<manifestVersion> matching Workbox CacheFirst for .glb."""
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const manifestPayload = { version: '2026.11.18-1', blender_version: '5.2.3 LTS', ha_entities: {}, ground_colliders: [] };
        globalThis.fetch = async (url) => ({
          ok: true,
          status: 200,
          json: async () => manifestPayload,
        });
        const { AssetLoader } = await server.ssrLoadModule('/src/core/AssetLoader.js');
        const loader = new AssetLoader();
        const loadedUrls = [];
        loader.gltfLoader.load = (finalUrl, onLoad) => {
          loadedUrls.push(finalUrl);
          onLoad({ scene: { traverse() {} }, cameras: [] });
        };
        await loader.loadHouseModel('/models/house_optimized.glb');
        await loader.loadHouseModel('/models/house_optimized.glb');
        return { loadedUrls, manifestVersion: loader.manifestVersion };
        """,
    )
    urls = js_res["loadedUrls"]
    assert len(urls) == 2
    assert "?v=" in urls[0], f"Expected deterministic ?v= query param, got {urls[0]}"
    assert "?t=" not in urls[0], f"Must not use timestamp ?t= cache buster: {urls[0]}"
    assert urls[0] == urls[1], f"Deterministic ?v= must stay identical across loads: {urls}"

    cfg = resolve_vite_config_json(REPO_ROOT, mode="production")
    wb = cfg["pwaOptions"]["workbox"]
    glb_rules = [r for r in wb["runtimeCaching"] if "glb" in r["urlPattern"].lower()]
    manifest_rules = [r for r in wb["runtimeCaching"] if "scene_manifest" in r["urlPattern"].lower()]
    assert glb_rules and glb_rules[0]["handler"] == "CacheFirst"
    assert manifest_rules and manifest_rules[0]["handler"] == "NetworkFirst"
    assert any("glb" in str(ig).lower() for ig in (wb.get("globIgnores") or [])) or (
        "glb" not in " ".join(wb.get("globPatterns") or []).lower()
    )


def test_t3_11_f12_f13_manifest_index_html_and_pwa_png_icons():
    """T3-11 (F12+F13): index.html, manifest.webmanifest, and public/pwa/*.png + dist/pwa/*.png align."""
    from tests.e2e.helpers.artifacts import parse_png_info

    index_html = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
    assert "apple-touch-icon" in index_html
    assert "apple-mobile-web-app-capable" in index_html

    cfg = resolve_vite_config_json(REPO_ROOT, mode="production")
    manifest = cfg["pwaOptions"]["manifest"]
    assert manifest["display"] == "standalone"
    assert manifest["lang"] == "it"

    expected_sizes = {
        "icon-192.png": (192, 192),
        "icon-512.png": (512, 512),
        "icon-maskable-512.png": (512, 512),
        "apple-touch-icon.png": (180, 180),
    }
    for fname, (w, h) in expected_sizes.items():
        pub_png = REPO_ROOT / "public" / "pwa" / fname
        assert pub_png.exists(), f"Missing {pub_png}"
        info = parse_png_info(pub_png)
        assert info["valid"] is True
        assert (info["width"], info["height"]) == (w, h)

    dist_manifest = REPO_ROOT / "dist" / "manifest.webmanifest"
    if dist_manifest.exists():
        import json

        dm = json.loads(dist_manifest.read_text(encoding="utf-8"))
        assert dm["display"] == "standalone"
        assert len(dm["icons"]) >= 3


def test_t3_12_f8_f12_ha_client_auth_callback_and_workbox_network_only():
    """T3-12 (F8+F12): HAClient cleans ?auth_callback=1 and Workbox excludes auth_callback=1, /api/, /ws/, /go2rtc/."""
    ha_client_src = (REPO_ROOT / "src" / "ha" / "HAClient.js").read_text(encoding="utf-8")
    assert "auth_callback" in ha_client_src
    assert "replaceState" in ha_client_src

    cfg = resolve_vite_config_json(REPO_ROOT, mode="production")
    wb = cfg["pwaOptions"]["workbox"]
    denylist = " ".join(wb.get("navigateFallbackDenylist") or [])
    for pat in ("api", "ws", "go2rtc"):
        assert pat in denylist, f"navigateFallbackDenylist missing {pat}: {denylist}"

    network_only = [r for r in wb["runtimeCaching"] if r["handler"] == "NetworkOnly"]
    joined_no = " ".join(r["urlPattern"] for r in network_only)
    for pat in ("api", "ws", "go2rtc", "auth_callback"):
        assert pat in joined_no, f"Workbox NetworkOnly missing '{pat}': {joined_no}"


def test_t3_13_f7_f2_f4_env_example_keys_consumed_by_config_and_go2rtc(monkeypatch):
    """T3-13 (F7+F2+F4): .env.example documents all prod keys consumed by SpatialServerConfig and go2rtc.yaml."""
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    kv: dict[str, str] = {}
    for ln in env_example.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        kv[k.strip()] = v.strip()

    for required_key in (
        "VITE_HA_PUBLIC_URL",
        "VITE_HA_TOKEN",
        "SPATIAL_SERVER_HOST",
        "SPATIAL_AUTH_REQUIRED",
        "SPATIAL_SESSION_SECRET",
        "SPATIAL_ALLOWED_ORIGINS",
        "GO2RTC_CANDIDATE_LAN",
        "GO2RTC_CANDIDATE_TAILSCALE",
        "REOLINK_CARRAIO_PASS",
    ):
        assert required_key in kv, f".env.example missing {required_key}"

    assert kv["VITE_HA_TOKEN"] == ""
    assert kv["SPATIAL_SERVER_HOST"] == "127.0.0.1"
    assert kv["SPATIAL_AUTH_REQUIRED"].lower() == "true"

    go2rtc_text = (REPO_ROOT / "go2rtc" / "go2rtc.yaml").read_text(encoding="utf-8")
    assert "GO2RTC_CANDIDATE_LAN" in go2rtc_text
    assert "GO2RTC_CANDIDATE_TAILSCALE" in go2rtc_text
    assert "REOLINK_CARRAIO_PASS" in go2rtc_text

    monkeypatch.setenv("SPATIAL_SERVER_HOST", kv["SPATIAL_SERVER_HOST"])
    monkeypatch.setenv("SPATIAL_AUTH_REQUIRED", kv["SPATIAL_AUTH_REQUIRED"])
    from spatial_server.config import SpatialServerConfig

    cfg = SpatialServerConfig.from_env()
    assert cfg.host == "127.0.0.1"
    assert cfg.auth_required is True


def test_t3_14_f7_f15_env_example_propagation_to_nssm_and_start_services(tmp_path: Path):
    """T3-14 (F7+F15): .env.example keys propagate through install_windows_services.ps1 and start_services.bat."""
    sample_env = (
        "VITE_HA_PUBLIC_URL=https://pc-fisso.tail123.ts.net:8443\n"
        "VITE_HA_TOKEN=\n"
        "SPATIAL_SERVER_HOST=127.0.0.1\n"
        "SPATIAL_SERVER_PORT=8765\n"
        "SPATIAL_AUTH_REQUIRED=true\n"
        "SPATIAL_SESSION_SECRET=prod_secret_example_1234567890\n"
        "SPATIAL_ALLOWED_ORIGINS=https://pc-fisso.tail123.ts.net\n"
        "GO2RTC_CANDIDATE_LAN=192.168.86.50:8555\n"
        "GO2RTC_CANDIDATE_TAILSCALE=100.64.0.5:8555\n"
        "REOLINK_CARRAIO_PASS=cam_pass_dummy\n"
    )
    ws_ps = build_isolated_workspace(tmp_path / "ps", REPO_ROOT, env_content=sample_env)
    ps_res = run_ps_dry_run(ws_ps, "scripts/install_windows_services.ps1")
    assert ps_res["returncode"] == 0, ps_res["stderr"]
    nssm_joined = "\n".join(" ".join(c["args"]) for c in ps_res["stub_calls"] if c["exe"] == "nssm.exe")
    for expected in (
        "SPATIAL_AUTH_REQUIRED=true",
        "SPATIAL_SESSION_SECRET=prod_secret_example_1234567890",
        "GO2RTC_CANDIDATE_LAN=192.168.86.50:8555",
        "GO2RTC_CANDIDATE_TAILSCALE=100.64.0.5:8555",
        "REOLINK_CARRAIO_PASS=cam_pass_dummy",
    ):
        assert expected in nssm_joined

    ws_bat = build_isolated_workspace(tmp_path / "bat", REPO_ROOT, env_content=sample_env)
    bat_res = run_bat_dry_run(ws_bat, "scripts/start_services.bat", nssm_status_exit=1)
    assert bat_res["returncode"] == 0, bat_res["stderr"]
    uv_call = next(c for c in bat_res["stub_calls"] if c["exe"] == "uvicorn.exe")
    assert uv_call["env"]["SPATIAL_SERVER_HOST"] == "127.0.0.1"
    assert uv_call["env"]["SPATIAL_AUTH_REQUIRED"] == "true"


def test_t3_15_f6_f15_caddyfile_dist_root_and_nssm_caddy_update_services(tmp_path: Path):
    """T3-15 (F6+F15): Caddyfile root * dist aligns with SmartHome3D-Caddy NSSM AppDirectory & update_services.bat."""
    caddy_text = (REPO_ROOT / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "root * dist" in caddy_text

    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        env_content="REOLINK_CARRAIO_PASS=dummy\n",
    )
    ps_res = run_ps_dry_run(ws_info, "scripts/install_windows_services.ps1")
    assert ps_res["returncode"] == 0, ps_res["stderr"]
    nssm_joined = "\n".join(" ".join(c["args"]) for c in ps_res["stub_calls"] if c["exe"] == "nssm.exe")
    assert "SmartHome3D-Caddy" in nssm_joined
    assert "Caddyfile" in nssm_joined


def test_t3_16_f4_f15_go2rtc_yaml_ports_and_nssm_firewall_8555(tmp_path: Path):
    """T3-16 (F4+F15): go2rtc.yaml :8555 WebRTC + :1984 API aligns with NSSM SmartHome3D-go2rtc & Firewall :8555."""
    go2rtc_cfg = yaml.safe_load((REPO_ROOT / "go2rtc" / "go2rtc.yaml").read_text(encoding="utf-8"))
    assert str(go2rtc_cfg["webrtc"]["listen"]).endswith(":8555")
    assert go2rtc_cfg["api"]["listen"] == "127.0.0.1:1984"

    ws_info = build_isolated_workspace(tmp_path, REPO_ROOT, env_content="REOLINK_CARRAIO_PASS=dummy\n")
    ps_res = run_ps_dry_run(ws_info, "scripts/install_windows_services.ps1")
    assert ps_res["returncode"] == 0
    fw_calls = [c["data"] for c in ps_res["ps_calls"] if c["kind"] == "New-NetFirewallRule"]
    assert {str(c.get("Protocol", "")).upper() for c in fw_calls} >= {"TCP", "UDP"}
    assert all(str(c.get("LocalPort")) == "8555" for c in fw_calls)


def test_t3_17_f7_f6_f15_gitignore_excludes_all_runtime_and_deploy_artifacts():
    """T3-17 (F7+F6+F15): .gitignore excludes all binaries, logs, .env, dist, and calibration runtime files."""
    gi = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {ln.strip() for ln in gi.splitlines() if ln.strip() and not ln.strip().startswith("#")}
    for required in (
        ".env",
        "dist/",
        "go2rtc/go2rtc.exe",
        "caddy/caddy.exe",
        "tools/nssm.exe",
        "logs/",
        "spatial_server/data/camera_calibrations.json",
    ):
        assert required in lines, f".gitignore missing '{required}'"


def test_t3_18_f5_f2_f3_verify_pipeline_compat_with_auth_required_false(monkeypatch, isolated_app_factory):
    """T3-18 (F5+F2+F3): Isolated pipeline testing works with auth_required=False while from_env() defaults True."""
    for k in list(os.environ.keys()):
        if k.startswith("SPATIAL_"):
            monkeypatch.delenv(k, raising=False)
    from spatial_server.config import SpatialServerConfig

    default_cfg = SpatialServerConfig.from_env()
    assert default_cfg.auth_required is True

    vp_text = (REPO_ROOT / "spatial_server" / "tests" / "verify_pipeline.py").read_text(encoding="utf-8")
    assert "auth_required" in vp_text or "SPATIAL_AUTH_REQUIRED" in vp_text

    app = isolated_app_factory(auth_required=False)
    with TestClient(app) as client:
        assert client.get("/api/v1/status").status_code == 200
        det = client.post(
            "/api/v1/detections",
            json=[
                {
                    "camera_id": "Cam_Carraio",
                    "timestamp": 1700000000.0,
                    "class_label": "person",
                    "confidence": 0.9,
                    "bbox": {"x_min": 0.4, "y_min": 0.4, "x_max": 0.5, "y_max": 0.8},
                }
            ],
        )
        assert det.status_code == 200


def test_t3_19_f13_f11_f14_pwa_prompt_oauth_overlay_and_mobile_css_wiring():
    """T3-19 (F13+F11+F14): index.html, style.css, PwaUpdatePrompt, main.js, and SceneManager mobile wiring align."""
    index_html = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
    assert "viewport-fit=cover" in index_html

    style_css = read_all_css(REPO_ROOT)
    assert "safe-area-inset" in style_css

    pwa_prompt_path = REPO_ROOT / "src" / "ui" / "PwaUpdatePrompt.js"
    assert pwa_prompt_path.exists()
    pwa_prompt_src = pwa_prompt_path.read_text(encoding="utf-8")
    assert "Nuova versione disponibile" in pwa_prompt_src

    scene_mgr_src = (REPO_ROOT / "src" / "core" / "SceneManager.js").read_text(encoding="utf-8")
    assert "visibilitychange" in scene_mgr_src
    assert "document.hidden" in scene_mgr_src


def test_t3_20_f15_f16_runbook_cross_references_scripts_services_ports_env():
    """T3-20 (F15+F16): Runbook script names, service names, ports, CIDRs, and env vars match repo configs."""
    runbook = (REPO_ROOT / "docs" / "runbooks" / "production-tailscale.md").read_text(encoding="utf-8")
    install_ps1 = (REPO_ROOT / "scripts" / "install_windows_services.ps1").read_text(encoding="utf-8")
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    for svc in ("SmartHome3D-go2rtc", "SmartHome3D-SpatialServer", "SmartHome3D-Caddy"):
        assert svc in runbook
        assert svc in install_ps1

    assert "100.64.0.0/10" in runbook
    assert "100.64.0.0/10" in install_ps1

    for env_key in ("VITE_HA_PUBLIC_URL", "SPATIAL_AUTH_REQUIRED", "GO2RTC_CANDIDATE_LAN", "REOLINK_CARRAIO_PASS"):
        assert env_key in runbook
        assert env_key in env_example
