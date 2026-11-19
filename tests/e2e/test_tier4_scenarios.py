from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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


def _extract_sh3d_cookie(resp) -> str:
    headers = resp.headers.get_list("set-cookie") if hasattr(resp.headers, "get_list") else []
    if not headers:
        raw = resp.headers.get("set-cookie", "")
        headers = [raw] if raw else []
    for h in headers:
        if "sh3d_session=" in h:
            return h
    return ""


# =============================================================================
# Tier 4 — Real-World Application Scenarios (9 scenarios)
# =============================================================================


def test_t4_01_admin_full_lifecycle(fake_ha_server, isolated_app_factory):
    """T4-01: Admin login -> session cookie -> auth/verify -> status/tracks -> PnP/calib/mode -> WS -> logout -> 401/4401."""
    app = isolated_app_factory(
        auth_required=True,
        ha_local_url=fake_ha_server.base_url,
        session_secret_key="t4-01-admin-lifecycle-" + "x" * 40,
    )
    with TestClient(app, base_url="https://testserver") as client:
        # 1. Exchange HA Admin Bearer token for sh3d_session cookie behind Tailscale HTTPS proxy
        sess = client.post(
            "/api/v1/auth/session",
            headers={"Authorization": "Bearer tok-admin", "X-Forwarded-Proto": "https"},
        )
        assert sess.status_code == 200
        sess_body = sess.json()
        assert sess_body["authenticated"] is True
        assert sess_body["user"]["is_admin"] is True

        cookie_hdr = _extract_sh3d_cookie(sess)
        assert "sh3d_session=" in cookie_hdr
        assert "httponly" in cookie_hdr.lower()
        assert "samesite=strict" in cookie_hdr.lower()
        assert "secure" in cookie_hdr.lower()

        # 2. Caddy forward_auth verification passes with session cookie
        verify = client.get("/api/v1/auth/verify")
        assert verify.status_code == 200

        # 3. Read endpoints succeed
        st = client.get("/api/v1/status")
        assert st.status_code == 200
        assert "Cam_Carraio" in st.json()["active_cameras"]
        assert client.get("/api/v1/tracks", params={"t_start": 0, "t_end": 9999999999}).status_code == 200

        # 4. Mutative calibration & ingestion mode endpoints succeed for Admin
        cam_calib = client.get("/api/v1/calibration/Cam_Carraio").json()["calibration"]
        t_gl = np.array(cam_calib["matrix_world_gl"], dtype=np.float64).reshape((4, 4))
        t_flipped = t_gl @ np.diag([-1.0, 1.0, -1.0, 1.0])

        upd = client.post(
            "/api/v1/calibration/Cam_Carraio",
            json={
                "camera_id": "Cam_Carraio",
                "fov_v_deg": 42.0,
                "fov_h_deg": 80.0,
                "distortion_coeffs": [-0.18, 0.04, 0.0, 0.0, 0.0],
                "calibrated_matrix_world_gl": t_flipped.reshape(-1).tolist(),
            },
        )
        assert upd.status_code == 200

        pinhole = app.state.pipeline.optical_models["Cam_Carraio"]
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
            corrs.append({"world_point": list(p), "pixel_uv": [uv[0], uv[1]]})

        pnp = client.post(
            "/api/v1/calibration/solve-pnp",
            json={"camera_id": "Cam_Carraio", "correspondences": corrs},
        )
        assert pnp.status_code == 200
        assert pnp.json()["reprojection_error_px"] < 5.0

        mode_resp = client.post("/api/v1/ingestion/mode", json={"mode": "synthetic"})
        assert mode_resp.status_code == 200
        assert mode_resp.json()["ingestion_mode"] == "synthetic"

        # 5. WebSocket connects with session cookie and streams initial server_status
        with client.websocket_connect("wss://testserver/ws/spatial") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "server_status"

        # 6. Logout clears session cookie and revokes REST + WS access
        logout = client.post("/api/v1/auth/logout")
        assert logout.status_code == 200
        assert client.get("/api/v1/status").status_code == 401
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws/spatial") as ws:
                ws.receive_text()
        assert exc_info.value.code == 4401


def test_t4_02_residente_restricted_workflow_backend_and_frontend_rbac(fake_ha_server, isolated_app_factory):
    """T4-02: Residente can view telemetry/video/snapshots but gets 403 on mutations and sees no admin UI controls."""
    app = isolated_app_factory(
        auth_required=True,
        ha_local_url=fake_ha_server.base_url,
        ha_token="",
    )
    with TestClient(app) as client:
        sess = client.post("/api/v1/auth/session", headers={"Authorization": "Bearer tok-resident"})
        assert sess.status_code == 200
        assert sess.json()["user"]["is_admin"] is False
        assert sess.json()["user"]["is_owner"] is False

        # Read endpoints + snapshot + WS succeed
        assert client.get("/api/v1/status").status_code == 200
        assert client.get("/api/v1/tracks", params={"t_start": 0, "t_end": 100}).status_code == 200
        assert client.get("/api/v1/timeline-density", params={"t_start": 0, "t_end": 100}).status_code == 200
        assert client.get("/api/v1/calibration/Cam_Carraio").status_code == 200
        assert client.get(
            "/api/v1/ha-camera/snapshot/camera.carraio_scorrevole",
            headers={"Authorization": "Bearer tok-resident"},
        ).status_code == 200
        with client.websocket_connect("/ws/spatial") as ws:
            assert ws.receive_json()["type"] == "server_status"

        # Mutative endpoints return 403 Forbidden
        pnp_body = {
            "camera_id": "Cam_Carraio",
            "correspondences": [
                {"world_point": [0.0, 0.0, 5.0], "pixel_uv": [0.2, 0.3]},
                {"world_point": [2.0, 0.0, 5.0], "pixel_uv": [0.7, 0.3]},
                {"world_point": [0.0, 0.0, 9.0], "pixel_uv": [0.25, 0.65]},
                {"world_point": [2.0, 0.0, 9.0], "pixel_uv": [0.75, 0.65]},
            ],
        }
        assert client.post("/api/v1/calibration/solve-pnp", json=pnp_body).status_code == 403
        assert client.post("/api/v1/calibration/Cam_Carraio", json={"camera_id": "Cam_Carraio", "fov_h_deg": 75.0}).status_code == 403
        assert client.post("/api/v1/ingestion/mode", json={"mode": "synthetic"}).status_code == 403
        assert client.post(
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
        ).status_code == 403

    # Frontend RBAC UI verification
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        const { makeElement } = installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const { TopBar } = await server.ssrLoadModule('/src/ui/TopBar.js');
        const { SecurityCameraModal } = await server.ssrLoadModule('/src/devices/camera/SecurityCameraModal.js');
        const { CalibrationAssistantUI } = await server.ssrLoadModule('/src/spatial/calibration/CalibrationAssistantUI.js');

        const haResident = {
          isAdmin: false,
          isTailscale: true,
          currentUser: { id: 'res_1', name: 'Mario', is_admin: false, is_owner: false },
          authStatus: 'authenticated',
          onStatusChange: () => () => {},
          onAuthChange: () => () => {},
          loginWithOAuth: async () => {},
          logout: async () => {},
        };

        const topEl = makeElement('header', 'top-bar');
        new TopBar(topEl, {
          sceneManager: { isNightMode: false, setNightMode() {} },
          cameraController: { resetView() {}, flyTo() {} },
          cameraProjector: { toggleFrustums: () => false },
          interactionManager: { toggleBadges: () => true },
          haClient: haResident,
        });
        const topText = topEl.innerHTML;
        const topCalibBtn = topEl.querySelector('#btn-open-cam-calib');

        const camEl = makeElement('div', 'cam-modal');
        const modal = new SecurityCameraModal({
          findMatchingBlenderCameraName: () => 'Cam_Carraio',
          haClient: haResident,
          spatialStreamClient: { fetchStatus: async () => ({ ingestion_mode: 'synthetic' }) },
          videoStreamManager: { attachToVideoElement: async () => ({ mode: 'webrtc', latencyMs: 40, getStatus: () => ({}) }) },
        });
        await modal.render(camEl, { haClient: haResident, assetLoader: { manifest: { cameras: { Cam_Carraio: {} } } } });
        const calBtn = camEl.querySelector('#btn-camera-calibrate');
        const simBtn = camEl.querySelector('#btn-toggle-simulator');

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

        const isHidden = (b) => !b || b.hidden || b.style?.display === 'none' || b.classList.contains('hidden');
        return {
          mentionsResidente: /residente/i.test(topText),
          topCalibHidden: isHidden(topCalibBtn),
          camCalibHidden: isHidden(calBtn),
          camSimHidden: isHidden(simBtn),
          calibOpen: calibUi.isOpen,
        };
        """,
    )
    assert js_res["mentionsResidente"] is True
    assert js_res["topCalibHidden"] is True
    assert js_res["camCalibHidden"] is True
    assert js_res["camSimHidden"] is True
    assert js_res["calibOpen"] is False


def test_t4_03_pwa_cold_start_glb_deterministic_versioning_and_sw_update():
    """T4-03: Built PWA artifacts, Workbox caching strategy, AssetLoader ?v= stability, and PwaUpdatePrompt toast."""
    from tests.e2e.helpers.artifacts import parse_html_meta, parse_png_info

    dist_dir = REPO_ROOT / "dist"
    assert (dist_dir / "index.html").exists(), "Production dist/index.html must exist"
    assert (dist_dir / "manifest.webmanifest").exists(), "Production dist/manifest.webmanifest must exist"
    assert (dist_dir / "sw.js").exists(), "Production dist/sw.js must exist"
    assert list(dist_dir.glob("workbox-*.js")), "Expected dist/workbox-*.js"

    meta = parse_html_meta(dist_dir / "index.html")
    assert meta.get("viewport") and "viewport-fit=cover" in meta["viewport"]

    for png_name in ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png"):
        png_path = dist_dir / "pwa" / png_name
        assert png_path.exists(), f"Missing {png_path}"
        assert parse_png_info(png_path)["valid"] is True

    sw_text = (dist_dir / "sw.js").read_text(encoding="utf-8")
    assert "house_optimized.glb" not in sw_text, "Large .glb must NOT be precached in dist/sw.js"
    assert "NetworkOnly" in sw_text
    assert "NetworkFirst" in sw_text
    assert "CacheFirst" in sw_text

    cfg = resolve_vite_config_json(REPO_ROOT, mode="production")
    rules = cfg["pwaOptions"]["workbox"]["runtimeCaching"]
    assert any("glb" in r["urlPattern"].lower() and r["handler"] == "CacheFirst" for r in rules)
    assert any("scene_manifest" in r["urlPattern"].lower() and r["handler"] == "NetworkFirst" for r in rules)
    assert any("gstatic" in r["urlPattern"].lower() and r["handler"] == "CacheFirst" for r in rules)

    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        let currentManifest = { version: 'v1-abc', ha_entities: {}, ground_colliders: [] };
        globalThis.fetch = async () => ({
          ok: true,
          status: 200,
          json: async () => currentManifest,
        });
        const { AssetLoader } = await server.ssrLoadModule('/src/core/AssetLoader.js');
        const loader = new AssetLoader();
        const urls = [];
        loader.gltfLoader.load = (u, onLoad) => {
          urls.push(u);
          onLoad({ scene: { traverse() {} }, cameras: [] });
        };
        await loader.loadHouseModel('/models/house_optimized.glb');
        await loader.loadHouseModel('/models/house_optimized.glb');
        currentManifest = { version: 'v2-def', ha_entities: {}, ground_colliders: [] };
        await loader.loadHouseModel('/models/house_optimized.glb');

        const { PwaUpdatePrompt } = await server.ssrLoadModule('/src/ui/PwaUpdatePrompt.js');
        let updateTriggered = false;
        const prompt = new PwaUpdatePrompt({ onUpdate: async () => { updateTriggered = true; } });
        prompt.show();
        const renderedHtml = document.body.innerHTML + (prompt.el?.innerHTML || '');
        const btn = prompt.el?.querySelector('button') || document.querySelector('#btn-pwa-update');
        btn?.click();

        return {
          urls,
          promptText: renderedHtml,
          updateTriggered,
        };
        """,
    )
    u1, u2, u3 = js_res["urls"]
    assert "?v=" in u1 and u1 == u2, f"Unchanged manifest must produce identical ?v=: {js_res['urls']}"
    assert u3 != u1 and "?v=" in u3, f"Changed manifest must rotate ?v=: {js_res['urls']}"
    assert "Nuova versione disponibile" in js_res["promptText"]
    assert "Aggiorna" in js_res["promptText"]
    assert js_res["updateTriggered"] is True


def test_t4_04_tailscale_serve_443_8443_same_origin_topology_consistency(fake_ha_server, isolated_app_factory):
    """T4-04: Tailscale Serve :443 & :8443 topology aligns across frontend, Caddyfile, backend, and Runbook."""
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const { HAClient } = await server.ssrLoadModule('/src/ha/HAClient.js');
        const { SpatialStreamClient } = await server.ssrLoadModule('/src/spatial/network/SpatialStreamClient.js');
        const { VideoStreamManager } = await server.ssrLoadModule('/src/video/VideoStreamManager.js');
        const { HaSnapshotFallbackStream } = await server.ssrLoadModule('/src/video/HaSnapshotFallbackStream.js');

        const ha = new HAClient();
        const spatial = new SpatialStreamClient();
        const video = new VideoStreamManager({ haClient: ha });
        const snap = new HaSnapshotFallbackStream('carraio_main', { haClient: ha });
        return {
          haUrl: ha.url || ha.publicUrl,
          spatialBase: spatial.baseUrl,
          spatialWs: spatial.wsUrl,
          go2rtcUrl: video.go2rtcUrl,
          snapSpatialBase: snap.spatialServerUrl,
        };
        """,
    )
    assert js_res["haUrl"] == "https://pc-fisso.tail123.ts.net:8443"
    assert js_res["spatialBase"] == ""
    assert js_res["spatialWs"] == "wss://pc-fisso.tail123.ts.net/ws/spatial"
    assert js_res["go2rtcUrl"] == "https://pc-fisso.tail123.ts.net/go2rtc"
    assert js_res["snapSpatialBase"] == ""

    caddy_text = (REPO_ROOT / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "http://:8080" in caddy_text and "bind 127.0.0.1" in caddy_text
    assert "forward_auth 127.0.0.1:8765" in caddy_text

    app = isolated_app_factory(
        auth_required=True,
        ha_local_url=fake_ha_server.base_url,
        allowed_origins=("https://pc-fisso.tail123.ts.net",),
    )
    with TestClient(app) as client:
        sess = client.post(
            "/api/v1/auth/session",
            headers={
                "Authorization": "Bearer tok-admin",
                "Origin": "https://pc-fisso.tail123.ts.net",
                "X-Forwarded-Proto": "https",
            },
        )
        assert sess.status_code == 200
        assert "secure" in _extract_sh3d_cookie(sess).lower()
        assert sess.headers.get("access-control-allow-origin") == "https://pc-fisso.tail123.ts.net"

    runbook = (REPO_ROOT / "docs" / "RUNBOOK_PRODUZIONE_FAMIGLIA_TAILSCALE.md").read_text(encoding="utf-8")
    assert "8080" in runbook and "8443" in runbook and "trusted_proxies" in runbook


def test_t4_05_unattended_win10_first_deploy_update_and_crash_recovery(tmp_path: Path):
    """T4-05: Unattended setup -> NSSM registration + crash restart + Firewall -> update_services rebuilds missing dist/."""
    import subprocess

    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        include_binaries=False,
        include_venv=False,
        include_dist=False,
        include_env_file=False,
    )
    # 1. Setup with -InstallServices (delegation check)
    setup_res = run_ps_dry_run(
        ws_info,
        "scripts/setup_windows_node.ps1",
        ["-InstallServices"],
        vc_redist_present=True,
        shadow_install_script=True,
    )
    assert setup_res["returncode"] == 0, f"setup failed:\n{setup_res['stdout']}\n{setup_res['stderr']}"
    ws: Path = ws_info["workspace"]
    assert (ws / ".env").exists()
    assert (ws / "go2rtc" / "go2rtc.exe").exists()
    assert (ws / "caddy" / "caddy.exe").exists()
    assert (ws / "tools" / "nssm.exe").exists()

    # 2. Run install_windows_services.ps1 with prod-like .env
    (ws / ".env").write_text(
        "REOLINK_CARRAIO_PASS=cam_prod\n"
        "GO2RTC_CANDIDATE_LAN=192.168.86.50:8555\n"
        "SPATIAL_SERVER_HOST=127.0.0.1\n"
        "SPATIAL_SESSION_SECRET=prod_secret_0123456789abcdef0123456789abcdef\n",
        encoding="utf-8",
    )
    inst_res = run_ps_dry_run(ws_info, "scripts/install_windows_services.ps1")
    assert inst_res["returncode"] == 0, f"install_windows_services failed:\n{inst_res['stdout']}\n{inst_res['stderr']}"
    nssm_cmds = "\n".join(" ".join(c["args"]) for c in inst_res["stub_calls"] if c["exe"] == "nssm.exe")
    assert "SmartHome3D-go2rtc" in nssm_cmds
    assert "SmartHome3D-SpatialServer" in nssm_cmds
    assert "SmartHome3D-Caddy" in nssm_cmds
    assert "AppExit" in nssm_cmds and "Restart" in nssm_cmds
    assert "AppRotateFiles" in nssm_cmds

    # 3. Initialize bare git origin and run update_services.bat while dist/ is missing
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=str(ws), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@e.local"], cwd=str(ws), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(ws), check=True, capture_output=True)
    (ws / ".gitignore").write_text(".env\n.venv/\ngo2rtc/go2rtc.exe\ncaddy/caddy.exe\ntools/nssm.exe\ndist/\nlogs/\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(ws), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(ws), check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=str(ws), check=True, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=str(ws), check=True, capture_output=True)

    assert not (ws / "dist").exists()
    ws_info["stub_log"].unlink(missing_ok=True)
    upd_res = run_bat_dry_run(ws_info, "scripts/update_services.bat", nssm_status_exit=0)
    assert upd_res["returncode"] == 0, f"update_services.bat failed:\n{upd_res['stdout']}\n{upd_res['stderr']}"
    npm_calls = [c for c in upd_res["stub_calls"] if c["exe"] == "npm_stub.exe"]
    assert any(c["args"][:2] == ["run", "build"] for c in npm_calls)


def test_t4_06_ios17_safari_pwa_video_fallback_chain():
    """T4-06: iOS 17+ Safari/PWA chain falls back WebRTC (2200ms) -> ManagedMediaSource -> HA Snapshot."""
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const events = [];

        globalThis.MediaSource = undefined;
        globalThis.ManagedMediaSource = class FakeManagedMediaSource {
          static isTypeSupported() { return true; }
          addEventListener(ev, fn) { if (ev === 'sourceopen') setTimeout(fn, 2); }
        };
        globalThis.RTCPeerConnection = class {
          addTransceiver() {}
          async createOffer() { return { type: 'offer', sdp: 'v=0' }; }
          async setLocalDescription() {}
          close() {}
          get iceGatheringState() { return 'complete'; }
        };
        globalThis.WebSocket = class {
          constructor(url) {
            events.push({ kind: 'mse_ws', url });
            setTimeout(() => this.onerror?.(), 5);
          }
          close() {}
        };
        globalThis.createImageBitmap = async () => ({ width: 640, height: 360, close() {} });
        globalThis.fetch = async (url, init = {}) => {
          events.push({ kind: 'fetch', url, credentials: init.credentials });
          if (url.includes('/go2rtc/api/webrtc')) {
            return { ok: false, status: 504, text: async () => 'timeout' };
          }
          return { ok: true, status: 200, blob: async () => new Blob([]) };
        };

        const { VideoStreamManager } = await server.ssrLoadModule('/src/video/VideoStreamManager.js');
        const mgr = new VideoStreamManager({ haClient: { isTailscale: true, getAccessToken: () => 'tok-ios' } });
        const chain = mgr.buildProviderChain('carraio_main', 'auto');
        const webrtcTimeout = chain[0].timeoutMs;

        const videoEl = document.createElement('video');
        const provider = await mgr.attachToVideoElement('carraio_main', videoEl, 'auto');
        await new Promise((r) => setTimeout(r, 80));
        mgr.detachFromVideoElement(videoEl);

        return {
          webrtcTimeout,
          finalMode: provider.mode,
          disableRemotePlayback: videoEl.disableRemotePlayback,
          events,
        };
        """,
    )
    assert js_res["webrtcTimeout"] == 2200
    assert js_res["finalMode"] == "snapshot"
    assert js_res["disableRemotePlayback"] is True
    webrtc_fetches = [e for e in js_res["events"] if e["kind"] == "fetch" and "/go2rtc/api/webrtc" in e["url"]]
    assert webrtc_fetches and webrtc_fetches[0]["credentials"] == "include"
    mse_ws = [e for e in js_res["events"] if e["kind"] == "mse_ws"]
    assert mse_ws and "/go2rtc/api/ws" in mse_ws[0]["url"]
    snap_fetches = [e for e in js_res["events"] if e["kind"] == "fetch" and "/api/v1/ha-camera/snapshot/" in e["url"]]
    assert snap_fetches and snap_fetches[0]["credentials"] == "include"


def test_t4_07_zero_secret_production_build_and_repo_hygiene_audit():
    """T4-07: Production dist/ contains zero leaked secrets; .gitignore & .env.example uphold production hygiene."""
    from tests.e2e.helpers.artifacts import scan_dist_js_secrets

    dist_dir = REPO_ROOT / "dist"
    assert dist_dir.exists(), "dist/ must exist for production build audit"

    leaks = scan_dist_js_secrets(dist_dir)
    assert leaks == [], f"Secret patterns leaked in dist/: {leaks}"

    for artifact in dist_dir.rglob("*"):
        if artifact.is_file() and artifact.suffix.lower() in (".js", ".css", ".html", ".webmanifest", ".map"):
            content = artifact.read_text(encoding="utf-8", errors="ignore")
            assert not re.search(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}", content), (
                f"JWT-like secret found in {artifact}"
            )
            assert "REOLINK_CARRAIO_PASS" not in content
            assert "SPATIAL_SESSION_SECRET" not in content

    gi = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "camera_calibrations.json", "caddy/caddy.exe", "tools/nssm.exe", "go2rtc/go2rtc.exe", "logs/"):
        assert pattern in gi

    env_ex = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^SPATIAL_AUTH_REQUIRED=true\s*$", env_ex, re.MULTILINE)
    assert re.search(r"^SPATIAL_SERVER_HOST=127\.0\.0\.1\s*$", env_ex, re.MULTILINE)
    assert re.search(r"^VITE_HA_TOKEN=\s*$", env_ex, re.MULTILINE)


def test_t4_08_multi_camera_snapshot_auth_fallback_empty_server_ha_token(fake_ha_server, isolated_app_factory):
    """T4-08: With empty server ha_token, snapshot proxy enforces auth (401), uses caller Bearer (200), blocks traversal."""
    app = isolated_app_factory(
        auth_required=True,
        ha_local_url=fake_ha_server.base_url,
        ha_token="",
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/ha-camera/snapshot/camera.carraio_scorrevole").status_code == 401

        ok = client.get(
            "/api/v1/ha-camera/snapshot/camera.carraio_scorrevole",
            headers={"Authorization": "Bearer tok-resident"},
        )
        assert ok.status_code == 200
        assert ok.headers["content-type"].startswith("image/")
        assert "no-store" in ok.headers.get("cache-control", "").lower()
        assert len(ok.content) > 0

        bad = client.get(
            "/api/v1/ha-camera/snapshot/..%2Fsecrets",
            headers={"Authorization": "Bearer tok-resident"},
        )
        assert bad.status_code in (400, 404, 422)


def test_t4_09_mobile_power_saving_visibility_raf_pause_and_adaptive_rendering():
    """T4-09: SceneManager caps mobile touch pixelRatio <= 1.5 & shadowMap 1024, pauses rAF when hidden, resets Clock."""
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        const { documentObj, rafQueue, makeElement } = installBrowserShims({
          href: 'https://pc-fisso.tail123.ts.net/',
          innerWidth: 390,
          innerHeight: 844,
          devicePixelRatio: 3,
          isCoarsePointer: true,
          maxTouchPoints: 5,
        });

        // Minimal WebGL2 stub so THREE.WebGLRenderer constructs cleanly in Node without GPU
        const noop = () => {};
        const glStubBase = {
          ARRAY_BUFFER: 34962, ELEMENT_ARRAY_BUFFER: 34963, FLOAT: 5126, UNSIGNED_SHORT: 5123,
          UNSIGNED_INT: 5125, TRIANGLES: 4, TEXTURE_2D: 3553, RGBA: 6408, UNSIGNED_BYTE: 5121,
          COLOR_BUFFER_BIT: 16384, DEPTH_BUFFER_BIT: 256, STENCIL_BUFFER_BIT: 1024,
          VERSION: 7938, SHADING_LANGUAGE_VERSION: 35724, VENDOR: 7936, RENDERER: 7937,
          MAX_TEXTURE_IMAGE_UNITS: 34930, MAX_VERTEX_TEXTURE_IMAGE_UNITS: 35660,
          MAX_TEXTURE_SIZE: 3379, MAX_CUBE_MAP_TEXTURE_SIZE: 34076, MAX_VERTEX_ATTRIBS: 34921,
          MAX_VERTEX_UNIFORM_VECTORS: 36347, MAX_VARYING_VECTORS: 36348, MAX_FRAGMENT_UNIFORM_VECTORS: 36349,
          MAX_COMBINED_TEXTURE_IMAGE_UNITS: 35661, MAX_SAMPLES: 36183, SAMPLES: 32937,
          DEPTH_TEST: 2929, CULL_FACE: 2884, BLEND: 3042, SCISSOR_TEST: 3089,
          VERTEX_SHADER: 35633, FRAGMENT_SHADER: 35632, COMPILE_STATUS: 35713, LINK_STATUS: 35714,
          ACTIVE_UNIFORMS: 35718, ACTIVE_ATTRIBUTES: 35721, FRAMEBUFFER: 36160,
          getExtension: (name) => (name === 'WEBGL_debug_renderer_info' ? null : {}),
          getParameter: (p) => {
            if (p === 7938) return 'WebGL 2.0 (Mock)';
            if (p === 35724) return 'WebGL GLSL ES 3.00';
            if (p === 36183) return 4;
            return 4096;
          },
          getContextAttributes: () => ({ alpha: false, antialias: true, depth: true, stencil: true }),
          getShaderPrecisionFormat: () => ({ precision: 23, rangeMin: 127, rangeMax: 127 }),
          createBuffer: () => ({}), bindBuffer: noop, bufferData: noop, deleteBuffer: noop,
          createFramebuffer: () => ({}), bindFramebuffer: noop, deleteFramebuffer: noop, framebufferTexture2D: noop,
          createRenderbuffer: () => ({}), bindRenderbuffer: noop, renderbufferStorage: noop, framebufferRenderbuffer: noop,
          checkFramebufferStatus: () => 36053,
          createTexture: () => ({}), bindTexture: noop, texImage2D: noop, texParameteri: noop, activeTexture: noop, deleteTexture: noop,
          createProgram: () => ({}), attachShader: noop, linkProgram: noop, useProgram: noop, deleteProgram: noop,
          getProgramParameter: () => true, getProgramInfoLog: () => '',
          createShader: () => ({}), shaderSource: noop, compileShader: noop, deleteShader: noop,
          getShaderParameter: () => true, getShaderInfoLog: () => '',
          getActiveUniform: () => ({ name: 'u', size: 1, type: 5126 }),
          getActiveAttrib: () => ({ name: 'a', size: 1, type: 5126 }),
          getUniformLocation: () => ({}), getAttribLocation: () => 0,
          enableVertexAttribArray: noop, disableVertexAttribArray: noop, vertexAttribPointer: noop,
          createVertexArray: () => ({}), bindVertexArray: noop, deleteVertexArray: noop,
          enable: noop, disable: noop, depthFunc: noop, depthMask: noop, cullFace: noop, frontFace: noop,
          blendFunc: noop, blendEquation: noop, blendFuncSeparate: noop, blendEquationSeparate: noop,
          viewport: noop, scissor: noop, clearColor: noop, clearDepth: noop, clearStencil: noop, clear: noop,
          colorMask: noop, stencilMask: noop, pixelStorei: noop, drawArrays: noop, drawElements: noop,
          isContextLost: () => false,
        };
        // Fallback: any WebGL2 method not explicitly stubbed (e.g. texImage3D) becomes a no-op
        const glStub = new Proxy(glStubBase, {
          get: (t, p) => (p in t ? t[p] : (typeof p === 'string' && /^[A-Z0-9_]+$/.test(p) ? 0 : noop)),
        });
        const origCreateEl = documentObj.createElement;
        documentObj.createElement = (tag) => {
          const el = origCreateEl(tag);
          if (tag === 'canvas') {
            el.addEventListener = noop;
            el.removeEventListener = noop;
            el.getContext = (kind) => (kind === 'webgl2' || kind === 'webgl' ? glStub : origCreateEl('canvas').getContext('2d'));
          }
          return el;
        };

        const { SceneManager } = await server.ssrLoadModule('/src/core/SceneManager.js');
        const canvasWrap = makeElement('div', 'canvas-container');
        const css2dWrap = makeElement('div', 'css2d-container');
        const mgr = new SceneManager(canvasWrap, css2dWrap);

        const pixelRatio = mgr.renderer.getPixelRatio();
        const shadowW = mgr.sunLight.shadow.mapSize.width;
        const shadowH = mgr.sunLight.shadow.mapSize.height;

        // Simulate tab becoming hidden -> rAF must pause
        const queuedBeforeHide = rafQueue.length;
        documentObj.hidden = true;
        documentObj.visibilityState = 'hidden';
        documentObj.dispatchEvent({ type: 'visibilitychange' });
        // Drain pending frame if any; animate() should NOT reschedule while hidden
        while (rafQueue.length > 0) {
          const item = rafQueue.shift();
          item.cb(performance.now());
        }
        const queuedWhileHidden = rafQueue.length;

        // Simulate returning visible -> clock resets & rAF resumes
        let clockResetCalled = false;
        const origGetDelta = mgr.clock.getDelta.bind(mgr.clock);
        const origStart = mgr.clock.start.bind(mgr.clock);
        mgr.clock.start = () => { clockResetCalled = true; return origStart(); };
        mgr.clock.getDelta = () => { clockResetCalled = true; return origGetDelta(); };

        documentObj.hidden = false;
        documentObj.visibilityState = 'visible';
        documentObj.dispatchEvent({ type: 'visibilitychange' });
        const queuedAfterShow = rafQueue.length;

        return {
          pixelRatio,
          shadowW,
          shadowH,
          queuedBeforeHide,
          queuedWhileHidden,
          queuedAfterShow,
          clockResetCalled,
        };
        """,
    )
    assert js_res["pixelRatio"] <= 1.5
    assert js_res["shadowW"] <= 1024 and js_res["shadowH"] <= 1024
    assert js_res["queuedBeforeHide"] >= 1
    assert js_res["queuedWhileHidden"] == 0, "rAF loop must pause when document.hidden === true"
    assert js_res["queuedAfterShow"] >= 1, "rAF loop must resume when document becomes visible"
    assert js_res["clockResetCalled"] is True
