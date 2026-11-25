"""E2E UI & JS tests for F20: Pre-Trigger Builder, Windowed Trigger Logic, New Conditions & Armed Pills."""

from __future__ import annotations

from pathlib import Path

from tests.e2e.helpers.artifacts import run_js_scenario


def test_f20_automation_studio_pretrigger_builder_and_conditions():
    code = """
      const { AutomationStudioUI } = await loadModule('/src/spatial/automations/AutomationStudioUI.js');

      let savedPayload = null;
      let autoWsCb = null;
      const mockStream = {
        onAutomationEvent: (cb) => { autoWsCb = cb; return () => {}; },
        onStatusChange: () => () => {},
        syncHaStates: () => {},
        fetchAutomationsBootstrap: async () => ({
          status: 'ok',
          zones: [
            { zone_id: 'zone_cancelletto', name: 'Cancelletto', geometry_type: 'polygon', vertices: [] },
          ],
          virtual_entities: [
            { entity_id: 'sh3d.allarme', name: 'Allarme Casa', domain: 'select', state: 'Spento', options: ['Spento', 'Acceso'] },
          ],
          rules: savedPayload ? [savedPayload] : [],
          armed_states: [],
          logs: [],
          identities: [{ name: 'Nicola', samples_count: 3 }],
          plates: [{ plate: 'HD858PC', owner_name: 'Nicola' }],
          cameras: ['Cam_Carraio', 'Cam_Cancelletto'],
          ha_discovery: { connected: true, notify_services: [], media_players: [], tts_entities: [], action_entities: [] },
        }),
        upsertAutomationRule: async (rule) => {
          savedPayload = rule;
          return { status: 'ok', rule, rules: [rule] };
        },
      };

      const uiLayer = document.createElement('div');
      document.body.appendChild(uiLayer);

      const studio = new AutomationStudioUI({
        sceneManager: {},
        cameraController: {},
        spatialStreamClient: mockStream,
        zoneRenderer: { setZones: () => {}, setZonesVisible: () => {}, flashZoneAlert: () => {}, hideDirectionCone: () => {} },
        haClient: { entities: {}, isAdmin: () => true },
        uiLayer,
      });

      await studio.refreshBootstrapData();
      studio.open();
      await new Promise((r) => setTimeout(r, 15));

      // Create new rule
      uiLayer.querySelector('#btn-auto-new-rule')?.click();
      await new Promise((r) => setTimeout(r, 10));

      const nameInp = uiLayer.querySelector('#rule-inp-name');
      nameInp.value = 'Cancello Smart Pre-Trigger';
      nameInp.dispatchEvent(new Event('input', { bubbles: true }));

      // Add a Pre-Trigger stage (defaults to kinematic_vector >= 0.5 m/s on vehicle, max_wait_s=10)
      uiLayer.querySelector('#btn-rule-add-pretrigger')?.click();
      await new Promise((r) => setTimeout(r, 10));

      // Switch Main Trigger 0 to biometric_detection + whitelisted plate in zone_cancelletto
      const mainTypeSel = uiLayer.querySelector('[data-trig-type-path="main:0"]');
      mainTypeSel.value = 'biometric_detection';
      mainTypeSel.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise((r) => setTimeout(r, 10));

      const zoneSel = uiLayer.querySelector('[data-trig-param="main:0:zone_id"]');
      zoneSel.value = 'zone_cancelletto';
      zoneSel.dispatchEvent(new Event('change', { bubbles: true }));

      const plateModeSel = uiLayer.querySelector('[data-trig-sf="main:0:plate_mode"]');
      plateModeSel.value = 'whitelisted';
      plateModeSel.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise((r) => setTimeout(r, 10));

      // Switch root Condition 0 to track_kinematics with peak_in_window & 10s window
      const condTypeSel = uiLayer.querySelector('[data-cond-type-path="root.0"]');
      condTypeSel.value = 'track_kinematics';
      condTypeSel.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise((r) => setTimeout(r, 10));

      const evalModeSel = uiLayer.querySelector('[data-cond-param="root.0:evaluation_mode"]');
      evalModeSel.value = 'peak_in_window';
      evalModeSel.dispatchEvent(new Event('change', { bubbles: true }));

      // Add a second leaf condition: subject_filter
      uiLayer.querySelector('[data-cond-add-leaf="root"]')?.click();
      await new Promise((r) => setTimeout(r, 10));
      const cond2Sel = uiLayer.querySelector('[data-cond-type-path="root.1"]');
      cond2Sel.value = 'subject_filter';
      cond2Sel.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise((r) => setTimeout(r, 10));

      // Save rule
      uiLayer.querySelector('#btn-auto-rule-save')?.click();
      await new Promise((r) => setTimeout(r, 20));

      // Simulate live WS automation_pretrigger_updated -> armed pill appears on rule card
      autoWsCb({
        type: 'automation_pretrigger_updated',
        armed_states: [
          {
            rule_id: savedPayload.rule_id,
            rule_name: savedPayload.name,
            stage_id: savedPayload.pre_triggers[0].stage_id,
            stage_index: 0,
            stage_name: 'Pre-trigger 1',
            remaining_s: 8.4,
            summary: 'vehicle (#7) velocità media 1.20 m/s',
          },
        ],
      });
      await new Promise((r) => setTimeout(r, 10));
      const armedPillText = uiLayer.querySelector('.auto-armed-pill')?.textContent || '';

      uiLayer.remove();
      return { savedPayload, armedPillText };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    saved = res["data"]["savedPayload"]
    assert saved is not None
    assert len(saved["pre_triggers"]) == 1
    stg = saved["pre_triggers"][0]
    assert stg["max_wait_s"] == 10
    assert stg["correlation_scope"] == "same_subject"
    assert stg["triggers"][0]["type"] == "kinematic_vector"
    assert stg["triggers"][0]["params"]["min_speed_mps"] == 0.5

    main_t = saved["triggers"][0]
    assert main_t["type"] == "biometric_detection"
    assert main_t["params"]["zone_id"] == "zone_cancelletto"
    assert main_t["subject_filter"]["plate_mode"] == "whitelisted"

    assert saved["condition"]["children"][0]["type"] == "track_kinematics"
    assert saved["condition"]["children"][0]["params"]["evaluation_mode"] == "peak_in_window"
    assert saved["condition"]["children"][0]["params"]["window_s"] == 10
    assert saved["condition"]["children"][1]["type"] == "subject_filter"

    assert "Pre-trigger 1" in res["data"]["armedPillText"]

    css_src = (Path(__file__).resolve().parents[2] / "src" / "style.css").read_text(encoding="utf-8")
    assert ".auto-pretrigger-card" in css_src
    assert ".auto-armed-pill" in css_src
    assert ".auto-trigger-logic-bar" in css_src
    assert ".auto-log-status-pill" in css_src


def test_f20_spatial_stream_client_armed_and_diagnostics_api():
    code = """
      const { SpatialStreamClient } = await loadModule('/src/spatial/network/SpatialStreamClient.js');

      const calls = [];
      ctx.setFetchHandler(async (url, opts = {}) => {
        calls.push({ url: String(url), method: opts.method || 'GET' });
        return { ok: true, status: 200, json: async () => ({ status: 'ok', armed_states: [], diagnostics: [] }) };
      });

      const client = new SpatialStreamClient('http://localhost:8765');
      const autoEvents = [];
      client.onAutomationEvent((m) => autoEvents.push(m));

      await client.fetchAutomationArmedStates();
      await client.fetchAutomationRuleDiagnostics('rule_1', 25);

      client.connectWebSocket();
      const ws = ctx.wsInstances[ctx.wsInstances.length - 1];
      ws._triggerOpen();
      ws._triggerMessage(JSON.stringify({ type: 'automation_pretrigger_updated', armed_states: [{ rule_id: 'rule_1', remaining_s: 9 }] }));
      client.disconnect();
      ctx.setFetchHandler(null);

      return { calls, autoEvents };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["calls"][0]["url"] == "http://localhost:8765/api/v1/automations/armed"
    assert d["calls"][1]["url"] == "http://localhost:8765/api/v1/automations/rules/rule_1/diagnostics?limit=25"
    assert len(d["autoEvents"]) == 1
    assert d["autoEvents"][0]["type"] == "automation_pretrigger_updated"
