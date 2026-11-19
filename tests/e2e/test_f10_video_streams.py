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
