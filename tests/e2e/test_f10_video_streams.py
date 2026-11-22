"""E2E tests for F10: VideoStreamManager, Go2RtcWebRTC, Go2RtcMSE (iOS17) & HaSnapshotFallback."""

from __future__ import annotations

from tests.e2e.helpers.artifacts import run_js_scenario


# ---------------------------------------------------------------------------
# Tier 1: Core Functionality (5 tests)
# ---------------------------------------------------------------------------


def test_f10_t1_prod_go2rtc_same_origin_url():
    res = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "manager_init",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "env": {"VITE_GO2RTC_URL": "", "VITE_GO2RTC_TAILSCALE_URL": ""},
        }
    )
    assert res["data"]["go2rtcUrl"] == "https://home.tailnet.ts.net/go2rtc"


def test_f10_t1_auto_provider_chain_fallback():
    res = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "manager_fallback",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "rtcSupported": False,
            "mediaSourceMode": "none",
            "fetchRoutes": [
                {
                    "match": "/api/v1/ha-camera/snapshot/",
                    "status": 200,
                    "contentType": "image/jpeg",
                    "bytes": [255, 216, 255, 217],
                }
            ],
        }
    )
    d = res["data"]
    assert d["mode"] == "snapshot"
    assert d["providerName"] == "HaSnapshotFallbackStream"


def test_f10_t1_webrtc_posts_sdp_offer():
    res = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "webrtc",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "go2rtcUrl": "https://home.tailnet.ts.net/go2rtc",
            "fetchRoutes": [
                {
                    "match": "/api/webrtc?src=carraio_main",
                    "status": 200,
                    "contentType": "application/sdp",
                    "text": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\n",
                }
            ],
        }
    )
    d = res["data"]
    assert d["connected"] is True
    assert d["hasSrcObject"] is True
    assert len(d["fetchLog"]) == 1
    req = d["fetchLog"][0]
    assert req["method"] == "POST"
    assert req["url"] == "https://home.tailnet.ts.net/go2rtc/api/webrtc?src=carraio_main"
    assert "v=0" in (req["body"] or "")


def test_f10_t1_mse_ws_handshake_and_append():
    res = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "mse",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "go2rtcUrl": "https://home.tailnet.ts.net/go2rtc",
            "mediaSourceMode": "standard",
        }
    )
    d = res["data"]
    assert d["connected"] is True
    assert d["wsUrls"] == ["wss://home.tailnet.ts.net/go2rtc/api/ws?src=carraio_main"]
    assert len(d["wsSent"]) >= 1
    assert '"type":"mse"' in d["wsSent"][0].replace(" ", "")
    assert len(d["appended"]) >= 1 and d["appended"][0] > 0


def test_f10_t1_snapshot_prod_uses_fastapi_endpoint():
    res = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "snapshot",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "fetchRoutes": [
                {
                    "match": "/api/v1/ha-camera/snapshot/",
                    "status": 200,
                    "contentType": "image/jpeg",
                    "bytes": [255, 216, 255, 217],
                }
            ],
        }
    )
    d = res["data"]
    assert d["connected"] is True
    assert len(d["fetchLog"]) >= 1
    req = d["fetchLog"][0]
    assert "/api/v1/ha-camera/snapshot/camera.carraio_scorrevole" in req["url"]
    assert req["credentials"] == "include"


# ---------------------------------------------------------------------------
# Tier 2: Edge Cases, Negative & Boundary Conditions (5 tests)
# ---------------------------------------------------------------------------


def test_f10_t2_webrtc_2200ms_timeout_and_credentials_include():
    res = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "webrtc",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "go2rtcUrl": "https://home.tailnet.ts.net/go2rtc",
            "fakeTimers": True,
            "hangAndAdvanceMs": 2300,
            "fetchRoutes": [
                {
                    "match": "/api/webrtc",
                    "hang": True,
                }
            ],
        }
    )
    d = res["data"]
    assert d["defaultTimeoutMs"] == 2200
    assert d["connected"] is False
    assert len(d["fetchLog"]) == 1
    assert d["fetchLog"][0]["credentials"] == "include"
    assert d["fetchLog"][0]["aborted"] is True


def test_f10_t2_webrtc_returns_false_on_401_or_no_rtc():
    res_no_rtc = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "webrtc",
            "mode": "production",
            "rtcSupported": False,
        }
    )
    assert res_no_rtc["data"]["connected"] is False

    res_401 = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "webrtc",
            "mode": "production",
            "go2rtcUrl": "https://home.tailnet.ts.net/go2rtc",
            "fetchRoutes": [{"match": "/api/webrtc", "status": 401, "text": "Unauthorized"}],
        }
    )
    assert res_401["data"]["connected"] is False


def test_f10_t2_mse_managed_media_source_ios17_fallback():
    res = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "mse",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "go2rtcUrl": "https://home.tailnet.ts.net/go2rtc",
            "mediaSourceMode": "ios17",
        }
    )
    d = res["data"]
    assert d["connected"] is True
    assert d["usedManaged"] is True
    assert d["disableRemotePlayback"] is True


def test_f10_t2_mse_returns_false_when_no_media_source():
    res = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "mse",
            "mode": "production",
            "mediaSourceMode": "none",
        }
    )
    assert res["data"]["connected"] is False


def test_f10_t2_snapshot_prod_no_vite_or_localhost_collision():
    res = run_js_scenario(
        {
            "action": "f10_video_check",
            "target": "snapshot",
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "fetchRoutes": [
                {"match": "/api/v1/ha-camera/snapshot/", "status": 502, "json": {"error": "Bad Gateway"}},
            ],
        }
    )
    d = res["data"]
    assert d["connected"] is True
    urls = [e["url"] for e in d["fetchLog"]]
    assert all("/api/ha-camera/snapshot" not in u for u in urls)
    assert all("127.0.0.1:8765" not in u for u in urls)
    assert all("localhost:8765" not in u for u in urls)


# ---------------------------------------------------------------------------
# Tier 3: Persistent Direct Stream Sharing (Sicurezza -> Modale -> POV -> Calibrazione)
# ---------------------------------------------------------------------------


def test_f10_t3_direct_connection_and_zero_reload_sharing_across_hub_modal_pov_and_calib():
    code = """
      const { VideoStreamManager } = await loadModule('/src/video/VideoStreamManager.js');
      const { CameraCatalog } = await loadModule('/src/video/CameraCatalog.js');
      const { SecurityFabHub } = await loadModule('/src/ui/SecurityFabHub.js');
      const catalog = new CameraCatalog();
      const mgr = new VideoStreamManager({
        go2rtcUrl: 'https://home.tailnet.ts.net/go2rtc',
        cameraCatalog: catalog,
      });

      // 1. Connessione diretta sul tile <video> di SecurityFabHub (identica a HEAD)
      const tileVideo = ctx.document.createElement('video');
      const p1 = await mgr.attachToVideoElement('carraio_sub', tileVideo, 'auto');
      const webrtcAfterHubConnect = ctx.fetchLog.filter((f) => f.url.includes('/api/webrtc')).length;

      // 2. Apertura SecurityCameraModal ('carraio_main') -> riusa a 0ms il MediaStream di 'carraio_sub' senza nuove richieste!
      const modalVideo = ctx.document.createElement('video');
      const pModal = await mgr.attachToVideoElement('carraio_main', modalVideo, 'auto');
      const webrtcAfterModalOpen = ctx.fetchLog.filter((f) => f.url.includes('/api/webrtc')).length;
      const sameProviderInModal = pModal === p1;
      const sameSrcObjectInModal = Boolean(tileVideo.srcObject && tileVideo.srcObject === modalVideo.srcObject);

      // 3. Chiusura modale -> sgancia solo il clone lasciando vivo il tile di SecurityFabHub!
      mgr.detachFromVideoElement(modalVideo);
      const tileStillLiveAfterModalClose = Boolean(tileVideo.srcObject && p1.connected);

      // 4. Ingresso in Vista POV 3D ('carraio_main') -> avvolge direttamente tileVideo in THREE.VideoTexture a 0ms!
      const povTexEntry = await mgr.acquireVideoTexture('carraio_main', 'auto');
      const webrtcAfterPovOpen = ctx.fetchLog.filter((f) => f.url.includes('/api/webrtc')).length;
      const povWrapsTileVideoDirectly = povTexEntry.videoElement === tileVideo;

      // 5. Passaggio POV -> Calibrazione (releaseVideoTexture + acquireVideoTexture dentro il Grace TTL di 30s) -> 0ms!
      mgr.releaseVideoTexture('carraio_main');
      const calibTexEntry = await mgr.acquireVideoTexture('carraio_main', 'auto');
      const webrtcAfterCalibOpen = ctx.fetchLog.filter((f) => f.url.includes('/api/webrtc')).length;
      const sameTextureAcrossPovAndCalib = povTexEntry.texture === calibTexEntry.texture;

      mgr.releaseVideoTexture('carraio_main');
      mgr.disposeAll();
      return {
        webrtcAfterHubConnect,
        webrtcAfterModalOpen,
        webrtcAfterPovOpen,
        webrtcAfterCalibOpen,
        sameProviderInModal,
        sameSrcObjectInModal,
        tileStillLiveAfterModalClose,
        povWrapsTileVideoDirectly,
        sameTextureAcrossPovAndCalib,
      };
    """
    res = run_js_scenario(
        {
            "code": code,
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "fetchRoutes": [
                {
                    "match": "/api/webrtc?src=carraio_sub",
                    "status": 200,
                    "contentType": "application/sdp",
                    "text": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\n",
                }
            ],
        }
    )
    assert res["ok"] is True, res
    d = res["data"]
    assert d["webrtcAfterHubConnect"] == 1
    assert d["webrtcAfterModalOpen"] == 1
    assert d["webrtcAfterPovOpen"] == 1
    assert d["webrtcAfterCalibOpen"] == 1
    assert d["sameProviderInModal"] is True
    assert d["sameSrcObjectInModal"] is True
    assert d["tileStillLiveAfterModalClose"] is True
    assert d["povWrapsTileVideoDirectly"] is True
    assert d["sameTextureAcrossPovAndCalib"] is True


def test_f10_t3_security_hub_keeps_streams_alive_on_close_and_fallback_main_to_sub():
    code = """
      const { VideoStreamManager } = await loadModule('/src/video/VideoStreamManager.js');
      const { CameraCatalog } = await loadModule('/src/video/CameraCatalog.js');
      const { SecurityFabHub } = await loadModule('/src/ui/SecurityFabHub.js');

      const catalog = new CameraCatalog();
      catalog.registerCamera({
        id: 'Cam_Portico',
        name: 'Portico (Reolink RLC-810A)',
        shortName: 'Portico',
        entityId: 'camera.portico',
        mainStream: 'portico_main',
        subStream: 'portico_sub',
      });

      const mgr = new VideoStreamManager({
        go2rtcUrl: 'https://home.tailnet.ts.net/go2rtc',
        cameraCatalog: catalog,
      });

      const hubRoot = ctx.document.createElement('div');
      ctx.document.body.appendChild(hubRoot);
      const hub = new SecurityFabHub(hubRoot, {
        cameraCatalog: catalog,
        videoStreamManager: mgr,
        recordingManager: {
          registerSlot() {},
          setPlaybackRate() {},
          setPlaying() {},
          seekAllToTimestamp: async () => {},
          queryAllSegments: async () => new Map(),
          detachAll() {},
          getStorageSummary: async () => ({ configured: false }),
        },
        trajectoryRenderer: { setLiveMode() {}, setEntitiesVisible() {}, loadDetections() {}, clearHistorical() {}, updateAtTime() {}, interpolateLive() {} },
        spatialStreamClient: { connected: false, onStatusChange: () => () => {}, onFrame: () => () => {} },
        cameraController: { flyToPreset() {}, flyToCameraPOV() {} },
        assetLoader: { cameras: new Map(), manifest: {} },
        deviceModals: { open() {} },
      });

      // 1. Apri Sicurezza -> connette i 2 flussi sub (carraio_sub, portico_sub)
      await hub._onPanelOpened();
      const fetchesAfterFirstOpen = ctx.fetchLog.filter((f) => f.url.includes('/api/webrtc')).length;

      // 2. Chiudi e riapri Sicurezza -> i flussi restano vivi in background, ZERO nuove richieste!
      hub.close();
      await hub._onPanelOpened();
      const fetchesAfterReopen = ctx.fetchLog.filter((f) => f.url.includes('/api/webrtc')).length;

      hub.dispose();
      mgr.disposeAll();
      return {
        fetchesAfterFirstOpen,
        fetchesAfterReopen,
      };
    """
    res = run_js_scenario(
        {
            "code": code,
            "mode": "production",
            "location": "https://home.tailnet.ts.net/",
            "fetchRoutes": [
                {
                    "match": "/api/webrtc",
                    "status": 200,
                    "contentType": "application/sdp",
                    "text": "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\n",
                },
            ],
        }
    )
    assert res["ok"] is True, res
    d = res["data"]
    assert d["fetchesAfterFirstOpen"] == 2
    assert d["fetchesAfterReopen"] == 2


def test_f10_t3_standby_snapshot_never_poisons_session_cache():
    code = """
      const { VideoStreamManager } = await loadModule('/src/video/VideoStreamManager.js');
      const { CameraCatalog } = await loadModule('/src/video/CameraCatalog.js');
      const catalog = new CameraCatalog();

      let webrtcOnline = false;
      ctx.setFetchHandler(async (url) => {
        if (url.includes('/api/webrtc')) {
          if (!webrtcOnline) {
            return { ok: false, status: 503, text: async () => 'temporarily unavailable' };
          }
          return { ok: true, status: 200, text: async () => 'v=0\\r\\no=- 1 1 IN IP4 127.0.0.1\\r\\n' };
        }
        return { ok: false, status: 502, text: async () => 'bad gateway' };
      });

      const OrigWS = globalThis.WebSocket;
      globalThis.WebSocket = class FailingWS extends OrigWS {
        constructor(url) {
          super(url);
          queueMicrotask(() => this._triggerError({}));
        }
      };

      const mgr = new VideoStreamManager({
        go2rtcUrl: 'https://home.tailnet.ts.net/go2rtc',
        cameraCatalog: catalog,
      });

      // 1. Prima connessione fallisce WebRTC+MSE -> cade in HaSnapshotFallbackStream (STANDBY)
      const v1 = ctx.document.createElement('video');
      const p1 = await mgr.attachToVideoElement('carraio_sub', v1, 'auto');
      const readyOnStandby = mgr.isStreamReady('carraio_sub');

      // 2. WebRTC torna disponibile -> riaprendo NON deve restituire STANDBY ma riconnettersi in WebRTC!
      webrtcOnline = true;
      const p2 = await mgr.attachToVideoElement('carraio_sub', v1, 'auto');
      const readyAfterRecovery = mgr.isStreamReady('carraio_sub');

      mgr.disposeAll();
      return {
        mode1: p1.mode,
        readyOnStandby,
        mode2: p2.mode,
        readyAfterRecovery,
      };
    """
    res = run_js_scenario({"code": code, "mode": "production", "location": "https://home.tailnet.ts.net/"})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["mode1"] == "snapshot"
    assert d["readyOnStandby"] is False
    assert d["mode2"] == "webrtc"
    assert d["readyAfterRecovery"] is True

