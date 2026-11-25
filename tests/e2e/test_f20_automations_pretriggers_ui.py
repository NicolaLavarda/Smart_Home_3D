"""E2E UI & JS tests for F20: Guided Automation Studio, Blank-Slate Draft, Scroll Preservation & Dirty Guard."""

from __future__ import annotations

from pathlib import Path

from tests.e2e.helpers.artifacts import read_all_css, run_js_scenario


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

      // Create new blank rule
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

      // Add first leaf condition (blank slate starts with 0 conditions) and switch to track_kinematics
      uiLayer.querySelector('[data-cond-add-leaf="root"]')?.click();
      await new Promise((r) => setTimeout(r, 10));

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

    css_src = read_all_css(Path(__file__).resolve().parents[2])
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


def test_f20_blank_slate_draft_context_fields_and_form_ids():
    code = """
      const { AutomationStudioUI } = await loadModule('/src/spatial/automations/AutomationStudioUI.js');

      const mockStream = {
        onAutomationEvent: () => () => {},
        onStatusChange: () => () => {},
        syncHaStates: () => {},
        fetchAutomationsBootstrap: async () => ({
          status: 'ok',
          zones: [{ zone_id: 'zone_1', name: 'Giardino', geometry_type: 'polygon', vertices: [] }],
          virtual_entities: [{ entity_id: 'sh3d.allarme', name: 'Allarme', domain: 'switch', state: 'off' }],
          rules: [],
          armed_states: [],
          logs: [],
          identities: [],
          plates: [],
          cameras: [],
          ha_discovery: { connected: false, notify_services: [], media_players: [], tts_entities: [], action_entities: [] },
        }),
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

      await studio.open();
      const hasStudioOpenClass = uiLayer.classList.contains('studio-open');

      uiLayer.querySelector('#btn-auto-new-rule')?.click();
      await new Promise((r) => setTimeout(r, 10));

      const draftSnap = JSON.parse(JSON.stringify(studio.editingRule));

      // Context-aware: enter hides min_dwell_s; dwell shows it
      const dwellBefore = Boolean(uiLayer.querySelector('[data-trig-param="main:0:min_dwell_s"]'));
      const evtSel = uiLayer.querySelector('[data-trig-param="main:0:event"]');
      evtSel.value = 'dwell';
      evtSel.dispatchEvent(new Event('change', { bubbles: true }));
      const dwellAfter = Boolean(uiLayer.querySelector('[data-trig-param="main:0:min_dwell_s"]'));

      // Context-aware: vehicle hides face_mode & shows plate_mode
      const clsSel = uiLayer.querySelector('[data-trig-sf="main:0:classes"]');
      clsSel.value = 'vehicle';
      clsSel.dispatchEvent(new Event('change', { bubbles: true }));
      const faceForVehicle = Boolean(uiLayer.querySelector('[data-trig-sf="main:0:face_mode"]'));
      const plateForVehicle = Boolean(uiLayer.querySelector('[data-trig-sf="main:0:plate_mode"]'));

      // biometric_grace_s only appears when biometric filter != 'any' and renders cleanly
      const graceBefore = Boolean(uiLayer.querySelector('[data-trig-sf="main:0:biometric_grace_s"]'));
      const plateSel = uiLayer.querySelector('[data-trig-sf="main:0:plate_mode"]');
      plateSel.value = 'whitelisted';
      plateSel.dispatchEvent(new Event('change', { bubbles: true }));
      const graceInput = uiLayer.querySelector('[data-trig-sf="main:0:biometric_grace_s"]');
      const graceAfterVal = graceInput ? graceInput.getAttribute('value') : null;

      // Verify every input/select/textarea has unique non-empty id and name
      const controls = uiLayer.querySelectorAll('input, select, textarea');
      const ids = [];
      let missingIdOrName = 0;
      for (const c of controls) {
        const id = c.getAttribute('id');
        const name = c.getAttribute('name');
        if (!id || !name) missingIdOrName += 1;
        ids.push(id);
      }
      const uniqueIds = new Set(ids).size === ids.length;

      studio.close({ force: true });
      const studioOpenAfterClose = uiLayer.classList.contains('studio-open');
      uiLayer.remove();

      return {
        hasStudioOpenClass,
        studioOpenAfterClose,
        draftSnap,
        dwellBefore,
        dwellAfter,
        faceForVehicle,
        plateForVehicle,
        graceBefore,
        graceAfterVal,
        missingIdOrName,
        uniqueIds,
        controlCount: controls.length,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["hasStudioOpenClass"] is True
    assert d["studioOpenAfterClose"] is False

    draft = d["draftSnap"]
    assert draft["name"] == ""
    assert draft["condition"]["children"] == []
    assert draft["actions"] == []
    assert draft["triggers"][0]["params"]["zone_id"] == ""
    assert draft["triggers"][0]["subject_filter"]["classes"] == ["any"]

    assert d["dwellBefore"] is False
    assert d["dwellAfter"] is True
    assert d["faceForVehicle"] is False
    assert d["plateForVehicle"] is True
    assert d["graceBefore"] is False
    assert d["graceAfterVal"] == "1.2"
    assert d["controlCount"] > 5
    assert d["missingIdOrName"] == 0
    assert d["uniqueIds"] is True


def test_f20_scroll_preservation_custom_notif_and_ws_no_clobber():
    code = """
      const { AutomationStudioUI } = await loadModule('/src/spatial/automations/AutomationStudioUI.js');

      let wsCb = null;
      const mockStream = {
        onAutomationEvent: (cb) => { wsCb = cb; return () => {}; },
        onStatusChange: () => () => {},
        syncHaStates: () => {},
        fetchAutomationsBootstrap: async () => ({
          status: 'ok',
          zones: [],
          virtual_entities: [],
          rules: [],
          armed_states: [],
          logs: [],
          identities: [],
          plates: [],
          cameras: [],
          ha_discovery: { connected: true, notify_services: [], media_players: [], tts_entities: [], action_entities: [] },
        }),
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

      await studio.open();
      uiLayer.querySelector('#btn-auto-new-rule')?.click();
      await new Promise((r) => setTimeout(r, 10));

      const nameInp = uiLayer.querySelector('#rule-inp-name');
      nameInp.value = 'Mia Regola In Corso';
      nameInp.dispatchEvent(new Event('input', { bubbles: true }));

      uiLayer.querySelector('#btn-rule-add-action')?.click();
      await new Promise((r) => setTimeout(r, 10));

      const actSel = uiLayer.querySelector('[data-act-type-path="0"]');
      actSel.value = 'send_notification';
      actSel.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise((r) => setTimeout(r, 10));

      const bodyEl = uiLayer.querySelector('#auto-studio-body');
      bodyEl.scrollTop = 240;

      // Toggle message_mode to custom -> preserves scrollTop & reveals textarea + var chips
      const msgModeSel = uiLayer.querySelector('[data-act-param="0:message_mode"]');
      msgModeSel.value = 'custom';
      msgModeSel.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise((r) => setTimeout(r, 10));

      const scrollAfterToggle = bodyEl.scrollTop;
      const customTextarea = uiLayer.querySelector('textarea[data-act-param="0:message"]');
      const varChipsCount = uiLayer.querySelectorAll('[data-act-insert-var]').length;

      // Background WebSocket events must NOT wipe editor
      wsCb({ type: 'automation_pretrigger_updated', armed_states: [] });
      wsCb({ type: 'automation_rules_updated', rules: [] });
      wsCb({ type: 'automation_triggered', log: { rule_id: 'r_x', rule_name: 'Altra', trigger_type: 'zone_presence', trigger_summary: 'x', timestamp: 1700000000, status: 'executed', actions_executed: [] } });
      await new Promise((r) => setTimeout(r, 10));

      const nameAfterWs = uiLayer.querySelector('#rule-inp-name')?.value || '';
      const stillInEditor = Boolean(studio.editingRule);

      studio.close({ force: true });
      uiLayer.remove();
      return {
        scrollAfterToggle,
        hasTextarea: Boolean(customTextarea),
        varChipsCount,
        nameAfterWs,
        stillInEditor,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["scrollAfterToggle"] == 240
    assert d["hasTextarea"] is True
    assert d["varChipsCount"] >= 4
    assert d["nameAfterWs"] == "Mia Regola In Corso"
    assert d["stillInEditor"] is True


def test_f20_dirty_state_guard_and_3way_confirm_dialog():
    code = """
      const { AutomationStudioUI } = await loadModule('/src/spatial/automations/AutomationStudioUI.js');

      let savedCount = 0;
      const mockStream = {
        onAutomationEvent: () => () => {},
        onStatusChange: () => () => {},
        syncHaStates: () => {},
        fetchAutomationsBootstrap: async () => ({
          status: 'ok',
          zones: [],
          virtual_entities: [],
          rules: [],
          armed_states: [],
          logs: [],
          identities: [],
          plates: [],
          cameras: [],
          ha_discovery: { connected: false, notify_services: [], media_players: [], tts_entities: [], action_entities: [] },
        }),
        upsertAutomationRule: async (rule) => {
          savedCount += 1;
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

      await studio.open();

      // 1. Entering new blank rule and cancelling immediately does NOT show confirm dialog
      uiLayer.querySelector('#btn-auto-new-rule')?.click();
      uiLayer.querySelector('#btn-auto-editor-cancel')?.click();
      const exitedClean = studio.editingRule === null;
      const dialogHiddenClean = uiLayer.querySelector('#auto-confirm-backdrop')?.hidden === true;

      // 2. Modifying rule triggers 3-way confirm dialog on cancel
      uiLayer.querySelector('#btn-auto-new-rule')?.click();
      const nameInp = uiLayer.querySelector('#rule-inp-name');
      nameInp.value = 'Regola Sporca';
      nameInp.dispatchEvent(new Event('input', { bubbles: true }));

      uiLayer.querySelector('#btn-auto-editor-cancel')?.click();
      const confirmRole = uiLayer.querySelector('.sh3d-confirm-dialog')?.getAttribute('role');
      const saveBtnTxt = uiLayer.querySelector('#btn-confirm-save-exit')?.textContent || '';
      const discardBtnTxt = uiLayer.querySelector('#btn-confirm-discard-exit')?.textContent || '';
      const contBtnTxt = uiLayer.querySelector('#btn-confirm-continue')?.textContent || '';

      // 3. Continue keeps editing
      uiLayer.querySelector('#btn-confirm-continue')?.click();
      const stillEditingAfterContinue = Boolean(studio.editingRule);

      // 4. Tab switch while dirty opens dialog -> Discard switches tab
      uiLayer.querySelector('.auto-seg-tab[data-tab="zones"]')?.click();
      const interceptedTab = studio.activeTab === 'rules';
      uiLayer.querySelector('#btn-confirm-discard-exit')?.click();
      const switchedAfterDiscard = studio.activeTab === 'zones' && studio.editingRule === null;

      // 5. Dirty rule + close() -> Save & exit saves and closes
      uiLayer.querySelector('.auto-seg-tab[data-tab="rules"]')?.click();
      uiLayer.querySelector('#btn-auto-new-rule')?.click();
      const nameInp2 = uiLayer.querySelector('#rule-inp-name');
      nameInp2.value = 'Regola Da Salvare';
      nameInp2.dispatchEvent(new Event('input', { bubbles: true }));

      const closeResultWhenDirty = studio.close();
      const stillOpenWhenGuarded = studio.isOpen;
      uiLayer.querySelector('#btn-confirm-save-exit')?.click();
      await new Promise((r) => setTimeout(r, 20));

      const closedAfterSave = !studio.isOpen;
      uiLayer.remove();

      return {
        exitedClean,
        dialogHiddenClean,
        confirmRole,
        saveBtnTxt,
        discardBtnTxt,
        contBtnTxt,
        stillEditingAfterContinue,
        interceptedTab,
        switchedAfterDiscard,
        closeResultWhenDirty,
        stillOpenWhenGuarded,
        closedAfterSave,
        savedCount,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["exitedClean"] is True
    assert d["dialogHiddenClean"] is True
    assert d["confirmRole"] == "alertdialog"
    assert "Salva ed esci" in d["saveBtnTxt"]
    assert "Scarta modifiche" in d["discardBtnTxt"]
    assert "Continua a modificare" in d["contBtnTxt"]
    assert d["stillEditingAfterContinue"] is True
    assert d["interceptedTab"] is True
    assert d["switchedAfterDiscard"] is True
    assert d["closeResultWhenDirty"] is False
    assert d["stillOpenWhenGuarded"] is True
    assert d["closedAfterSave"] is True
    assert d["savedCount"] == 1


def test_f20_zone_ymin_zero_quick_draw_and_entities_list_first():
    code = """
      const { AutomationStudioUI } = await loadModule('/src/spatial/automations/AutomationStudioUI.js');

      let savedZone = null;
      const mockStream = {
        onAutomationEvent: () => () => {},
        onStatusChange: () => () => {},
        syncHaStates: () => {},
        fetchAutomationsBootstrap: async () => ({
          status: 'ok',
          zones: savedZone ? [savedZone] : [],
          virtual_entities: [
            { entity_id: 'sh3d.sirena', name: 'Sirena', domain: 'switch', state: 'off' },
          ],
          rules: [],
          armed_states: [],
          logs: [],
          identities: [],
          plates: [],
          cameras: [],
          ha_discovery: { connected: false, notify_services: [], media_players: [], tts_entities: [], action_entities: [] },
        }),
        upsertAutomationZone: async (z) => {
          savedZone = { ...z, zone_id: 'zone_new_3d' };
          return { status: 'ok', zone: savedZone, zones: [savedZone] };
        },
      };

      const uiLayer = document.createElement('div');
      document.body.appendChild(uiLayer);

      let activeOnVerticesChanged = null;
      const studio = new AutomationStudioUI({
        sceneManager: {},
        cameraController: {},
        spatialStreamClient: mockStream,
        zoneRenderer: {
          setZones: () => {},
          setZonesVisible: () => {},
          flashZoneAlert: () => {},
          hideDirectionCone: () => {},
          startDrawing: ({ onVerticesChanged }) => { activeOnVerticesChanged = onVerticesChanged; },
          stopDrawing: () => {},
          rebuildDraftVisual: () => {},
        },
        haClient: { entities: {}, isAdmin: () => true },
        uiLayer,
      });

      await studio.open('entities');

      // List-first check: no #ve-inp-id form on initial entities list, .m3-switch present
      const formBeforeNew = Boolean(uiLayer.querySelector('#ve-inp-id'));
      const switchCount = uiLayer.querySelectorAll('.m3-switch').length;

      uiLayer.querySelector('#btn-auto-new-entity')?.click();
      const domainSel = uiLayer.querySelector('#ve-inp-domain');
      domainSel.value = 'select';
      domainSel.dispatchEvent(new Event('change', { bubbles: true }));
      const defaultItalianOpts = uiLayer.querySelector('#ve-inp-options')?.value || '';

      // Discard dirty entity editor via 3-way confirm, then test + Disegna 3D + y_min = 0
      uiLayer.querySelector('.auto-seg-tab[data-tab="rules"]')?.click();
      uiLayer.querySelector('#btn-confirm-discard-exit')?.click();
      uiLayer.querySelector('#btn-auto-new-rule')?.click();
      const ruleName = uiLayer.querySelector('#rule-inp-name');
      ruleName.value = 'Regola Con Nuova Area';
      ruleName.dispatchEvent(new Event('input', { bubbles: true }));

      uiLayer.querySelector('[data-quick-new-zone^="polygon:"]')?.click();
      await new Promise((r) => setTimeout(r, 10));

      const yMinInp = uiLayer.querySelector('#zone-inp-ymin');
      yMinInp.value = '0';
      yMinInp.dispatchEvent(new Event('input', { bubbles: true }));
      const yMinStored = studio.editingZone.y_min;

      activeOnVerticesChanged([{ x: 0, z: 0 }, { x: 2, z: 0 }, { x: 2, z: 2 }]);
      uiLayer.querySelector('#btn-zone-save')?.click();
      await new Promise((r) => setTimeout(r, 20));

      const returnedToRules = studio.activeTab === 'rules' && Boolean(studio.editingRule);
      const restoredName = studio.editingRule?.name || '';
      const linkedZoneId = studio.editingRule?.triggers?.[0]?.params?.zone_id || '';

      studio.close({ force: true });
      uiLayer.remove();

      return {
        formBeforeNew,
        switchCount,
        defaultItalianOpts,
        yMinStored,
        returnedToRules,
        restoredName,
        linkedZoneId,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["formBeforeNew"] is False
    assert d["switchCount"] == 1
    assert d["defaultItalianOpts"] == "Spento, Silenzioso, Acceso"
    assert d["yMinStored"] == 0
    assert d["returnedToRules"] is True
    assert d["restoredName"] == "Regola Con Nuova Area"
    assert d["linkedZoneId"] == "zone_new_3d"
