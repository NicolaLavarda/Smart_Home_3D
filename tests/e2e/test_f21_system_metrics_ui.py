"""E2E tests for System Metrics & FPS settings button and chart panel."""

from __future__ import annotations

from pathlib import Path
import re

from tests.e2e.helpers.artifacts import read_all_css, run_js_scenario


def test_f21_topbar_metrics_button_under_calib_and_rbac():
    code = """
      const { TopBar } = await loadModule('/src/ui/TopBar.js');
      const { SystemMetricsPanel } = await loadModule('/src/ui/SystemMetricsPanel.js');

      const uiLayer = ctx.document.querySelector('.ui-layer') || ctx.document.body;
      const topBarEl = ctx.document.getElementById('top-bar');

      const authListeners = new Set();
      const haClientMock = {
        isAdmin: false,
        isMockMode: false,
        authStatus: 'authenticated',
        currentUser: { id: 'u2', name: 'Mario', is_admin: false },
        onStatusChange() { return () => {}; },
        onAuthChange(fn) { authListeners.add(fn); return () => authListeners.delete(fn); },
        async logout() {},
      };

      const requestedWindows = [];
      const spatialMock = {
        async fetchMetricsHistory({ windowS }) {
          requestedWindows.push(windowS);
          return {
            status: 'ok',
            window_s: windowS,
            source: windowS > 3600 ? 'sqlite' : 'memory',
            resolution_s: windowS > 3600 ? 1800 : 2,
            current: {
              cpu_pct: 27.4,
              gpu_pct: 19.2,
              gpu_mem_mb: 320.0,
              ram_pct: 61.8,
              ram_used_mb: 4980,
              ram_total_mb: 8079,
              proc_cpu_pct: 8.2,
              proc_rss_mb: 310.0,
              cv_fps_total: 5.2,
              cv_fps_target: 7.0,
              cv_fps_person: 4.0,
              cv_fps_vehicle: 0.0,
              cv_fps_idle: 1.2,
              cv_infer_ms: 42.5,
              cv_infer_ms_max: 54.0,
              person_det_fps: 3.1,
              vehicle_det_fps: 0.0,
              bio_fps: 0.5,
              bio_face_ms: 39.0,
              bio_alpr_ms: 0.0,
              bio_queue: 0,
              tracks_person: 1,
              tracks_vehicle: 0,
              tracks_animal: 0,
              openvino_backend: 'openvino_ir(GPU)',
              gpu_backend: 'win_d3dkmt',
              cameras: {
                Cam_Carraio: { actual_fps: 4.0, target_fps: 4.0, infer_ms: 42.5, tier: 'person', rtsp_connected: true },
                Cam_Portico: { actual_fps: 1.2, target_fps: 1.2, infer_ms: 35.0, tier: 'idle', rtsp_connected: true },
              },
            },
            entities: [
              { entity_id: 'sensor.sh3d_pc_cpu', name: 'PC Fisso CPU', state: 27.4, unit_of_measurement: '%' },
              { entity_id: 'sensor.sh3d_pc_gpu', name: 'PC Fisso GPU', state: 19.2, unit_of_measurement: '%' },
              { entity_id: 'sensor.sh3d_cv_fps_totale', name: 'CV FPS Totale', state: 5.2, unit_of_measurement: 'FPS' },
            ],
            series: [
              { t: 1700000000, cpu_pct: 22.0, gpu_pct: 15.0, ram_pct: 60.0, proc_cpu_pct: 6.0, cv_fps_total: 4.8, cv_fps_person: 0.0, cv_fps_vehicle: 0.0, cv_fps_target: 4.8, cv_infer_ms: 38.0, cv_infer_ms_max: 45.0, bio_face_ms: 0, bio_alpr_ms: 0, tracks_person: 0, tracks_vehicle: 0, tracks_animal: 0, bio_fps: 0 },
              { t: 1700000060, cpu_pct: 27.4, gpu_pct: 19.2, ram_pct: 61.8, proc_cpu_pct: 8.2, cv_fps_total: 5.2, cv_fps_person: 4.0, cv_fps_vehicle: 0.0, cv_fps_target: 7.0, cv_infer_ms: 42.5, cv_infer_ms_max: 54.0, bio_face_ms: 39.0, bio_alpr_ms: 0, tracks_person: 1, tracks_vehicle: 0, tracks_animal: 0, bio_fps: 0.5 },
            ],
            summary: {
              samples_count: 2,
              sample_interval_s: 2.0,
              retention_days: 7,
              db_size_estimate_mb: 0.42,
              cpu_avg: 24.7,
              cpu_max: 27.4,
              gpu_avg: 17.1,
              cv_fps_avg: 5.0,
              cv_fps_max: 5.2,
            },
            bridges: { ha_bridge_connected: true, mqtt_bridge_connected: false, ha_publish_interval_s: 15.0 },
          };
        },
      };

      const metricsPanel = new SystemMetricsPanel({
        spatialStreamClient: spatialMock,
        haClient: haClientMock,
        uiLayer,
      });

      new TopBar(topBarEl, {
        sceneManager: { isNightMode: false, setNightMode() {} },
        cameraController: { flyToPreset() {}, flyToCameraPOV() {} },
        cameraProjector: { toggleFrustums: () => false },
        interactionManager: { toggleBadges: () => false },
        haClient: haClientMock,
        calibrationAssistant: { isOpen: false, open() {}, close() {} },
        automationStudio: { isOpen: false, open() {}, close() {} },
        systemMetricsPanel: metricsPanel,
      });

      const dropdownItems = Array.from(topBarEl.querySelectorAll('#top-settings-dropdown .settings-dropdown-item')).map((el) => el.id);
      const calibIdx = dropdownItems.indexOf('btn-open-cam-calib');
      const metricsIdx = dropdownItems.indexOf('btn-open-system-metrics');

      const metricsBtn = topBarEl.querySelector('#btn-open-system-metrics');
      const residentVisible = !metricsBtn.hidden && !metricsBtn.disabled && metricsBtn.style.display !== 'none';

      // Promote to Admin
      haClientMock.isAdmin = true;
      haClientMock.currentUser = { id: 'u1', name: 'Nicola', is_admin: true };
      for (const cb of authListeners) {
        cb({ authenticated: true, status: 'authenticated', user: haClientMock.currentUser, isAdmin: true, isMockMode: false });
      }
      const adminVisible = !metricsBtn.hidden && !metricsBtn.disabled && metricsBtn.style.display !== 'none';

      metricsBtn.click();
      for (let i = 0; i < 8; i++) await Promise.resolve();

      const panelOpen = metricsPanel.isOpen;
      const bodyTextBefore = metricsPanel.bodyEl.textContent;
      const svgCount = metricsPanel.bodyEl.querySelectorAll('svg.sys-chart-svg').length;

      // Switch to 7g window
      const btn7d = metricsPanel.panelEl.querySelector('[data-metrics-window="604800"]');
      btn7d.click();
      for (let i = 0; i < 8; i++) await Promise.resolve();

      const windowAfter7d = metricsPanel.windowS;
      const resBadge7d = metricsPanel.resBadgeEl.textContent;

      metricsPanel.close();
      const closedAriaHidden = metricsPanel.panelEl.getAttribute('aria-hidden');
      metricsPanel.dispose();

      return {
        calibIdx,
        metricsIdx,
        residentVisible,
        adminVisible,
        panelOpen,
        svgCount,
        requestedWindows,
        hasCpuText: bodyTextBefore.includes('27.4%'),
        hasGpuText: bodyTextBefore.includes('19.2%'),
        hasFpsText: bodyTextBefore.includes('5.2'),
        hasCamPill: bodyTextBefore.includes('Carraio'),
        hasEntityId: bodyTextBefore.includes('sensor.sh3d_pc_gpu'),
        windowAfter7d,
        resBadge7d,
        closedAriaHidden,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["calibIdx"] >= 0
    assert d["metricsIdx"] == d["calibIdx"] + 1
    assert d["residentVisible"] is False
    assert d["adminVisible"] is True
    assert d["panelOpen"] is True
    assert d["svgCount"] == 4
    assert d["requestedWindows"] == [300, 604800]
    assert d["hasCpuText"] is True
    assert d["hasGpuText"] is True
    assert d["hasFpsText"] is True
    assert d["hasCamPill"] is True
    assert d["hasEntityId"] is True
    assert d["windowAfter7d"] == 604800
    assert "SQLite" in d["resBadge7d"]
    assert d["closedAriaHidden"] == "true"


def test_f21_icons_and_styles_consistency():
    repo_root = Path(__file__).resolve().parents[2]
    src_text = (repo_root / "src" / "ui" / "SystemMetricsPanel.js").read_text(encoding="utf-8")
    discovered = sorted(set(re.findall(r"""\bicon\(\s*['"]([a-z0-9-]+)['"]""", src_text)))
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "icons",
            "names": discovered,
        }
    )
    for name in discovered:
        svg = res["data"]["results"].get(name, "")
        assert svg.startswith("<svg") and "</svg>" in svg, f"Invalid icon {name!r}"

    css_all = read_all_css(repo_root)
    assert ".sys-metrics-drawer" in css_all
    assert ".sys-chart-svg" in css_all
    assert ".ui-layer.metrics-open .nav-hub-root" in css_all

