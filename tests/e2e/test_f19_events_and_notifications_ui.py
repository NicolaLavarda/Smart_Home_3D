"""E2E UI & unit JS tests for F19: Daily SceneEvents tab, replay jump, 3-state alarm, and notification action builder."""

from __future__ import annotations

from pathlib import Path

from tests.e2e.helpers.artifacts import read_all_css, run_js_scenario


def test_f19_spatial_stream_client_scene_events_and_ha_discovery():
    code = """
      const { SpatialStreamClient } = await loadModule('/src/spatial/network/SpatialStreamClient.js');

      const fetchLog = [];
      ctx.setFetchHandler(async (url, opts = {}) => {
        fetchLog.push({ url: String(url), method: opts.method || 'GET' });
        return {
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', count: 1, events: [], notify_services: [] }),
        };
      });

      const client = new SpatialStreamClient('http://localhost:8765');
      const received = [];
      const unsub = client.onSceneEvent((msg) => received.push(msg));

      await client.fetchSceneEvents({
        tStart: 1000,
        tEnd: 5000,
        importance: 'alert',
        subjectClass: 'person',
        unknownOnly: true,
        limit: 40,
      });
      await client.fetchSceneEvent('evt_1700000100000_cafe');
      await client.deleteSceneEvent('evt_1700000100000_cafe');
      await client.fetchHaDiscovery();
      const coverUrl = client.getSceneEventCoverUrl('evt_1700000100000_cafe', 'annotated', 1700000100.5);

      client.connectWebSocket();
      const ws = ctx.wsInstances[ctx.wsInstances.length - 1];
      ws._triggerOpen();
      ws._triggerMessage(JSON.stringify({ type: 'scene_event_updated', event: { event_id: 'evt_1700000100000_cafe', title: 'Nicola' } }));
      unsub();
      ws._triggerMessage(JSON.stringify({ type: 'scene_event_updated', event: { event_id: 'evt_2', title: 'Altro' } }));
      client.disconnect();
      ctx.setFetchHandler(null);

      return { fetchLog, received, coverUrl };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]

    assert len(d["received"]) == 1
    assert d["received"][0]["event"]["event_id"] == "evt_1700000100000_cafe"
    assert d["coverUrl"].startswith("http://localhost:8765/api/v1/events/evt_1700000100000_cafe/annotated.jpg")

    urls = [(item["method"], item["url"]) for item in d["fetchLog"]]
    assert urls[0][0] == "GET" and "/api/v1/events?" in urls[0][1]
    assert "t_start=1000" in urls[0][1] and "t_end=5000" in urls[0][1]
    assert "importance=alert" in urls[0][1] and "subject_class=person" in urls[0][1] and "unknown_only=true" in urls[0][1]
    assert urls[1] == ("GET", "http://localhost:8765/api/v1/events/evt_1700000100000_cafe")
    assert urls[2] == ("DELETE", "http://localhost:8765/api/v1/events/evt_1700000100000_cafe")
    assert urls[3] == ("GET", "http://localhost:8765/api/v1/automations/ha-discovery")


def test_f19_security_fab_hub_events_tab_replay_jump_and_3state_alarm():
    code = """
      const { SecurityFabHub } = await loadModule('/src/ui/SecurityFabHub.js');

      const nowSec = Math.floor(Date.now() / 1000);
      const evt1 = {
        event_id: 'evt_1700000200000_a1b2',
        status: 'closed',
        started_at: nowSec - 180,
        ended_at: nowSec - 165,
        duration_s: 15,
        replay_start_at: nowSec - 183,
        importance: 'alert',
        title: 'Persona sconosciuta · Cancelletto',
        summary_it: "C'è una persona al cancelletto.",
        best_camera_id: 'Cam_Cancelletto',
        cameras: ['Cam_Cancelletto'],
        zones: ['Cancelletto'],
        subjects: [{ track_id: 9, class_label: 'person', biometric_status: 'unknown' }],
        annotated_url: '/api/v1/events/evt_1700000200000_a1b2/annotated.jpg',
        has_video_clip: true,
        has_hd_clip: true,
      };
      const evt2 = {
        event_id: 'evt_1700000300000_c3d4',
        status: 'closed',
        started_at: nowSec - 60,
        ended_at: nowSec - 50,
        duration_s: 10,
        replay_start_at: nowSec - 63,
        importance: 'routine',
        title: 'Nicola · Ingresso',
        summary_it: "C'è Nicola all'ingresso.",
        best_camera_id: 'Cam_Ingresso',
        cameras: ['Cam_Ingresso'],
        zones: ['Ingresso'],
        subjects: [{ track_id: 10, class_label: 'person', identity: 'Nicola', biometric_status: 'locked' }],
        annotated_url: '/api/v1/events/evt_1700000300000_c3d4/annotated.jpg',
        has_video_clip: false,
        has_hd_clip: false,
      };

      const fetchCalls = [];
      let wsSceneCb = null;
      let autoCb = null;

      const root = document.createElement('div');
      document.body.appendChild(root);

      const hub = new SecurityFabHub(root, {
        cameraCatalog: {
          getCameras: () => [{ id: 'Cam_Cancelletto', name: 'Cancelletto', blenderCameraName: 'Cam_Cancelletto', recordingCameraId: 'Cam_Cancelletto', aspectRatio: 16 / 9, getStreamName: (tier = 'sub') => `cancelletto_${tier}` }],
          onChange: () => () => {},
        },
        videoStreamManager: {
          attachToVideoElement: async () => ({ getStatus: () => ({ mode: 'standby' }), onStatusChange: () => () => {} }),
          detachFromVideoElement: () => {},
        },
        recordingManager: {
          getStorageSummary: async () => ({ configured: true, providers: [{ detail: 'NVR attivo' }] }),
          registerSlot: () => {},
          unregisterSlot: () => {},
          detachAll: () => {},
          setPlaybackRate: () => {},
          setPlaying: () => {},
          seekAllToTimestamp: async () => {},
          queryAllSegments: async () => new Map(),
          querySegments: async () => [],
          syncPlaybackTick: () => {},
        },
        trajectoryRenderer: {
          setLiveMode: () => {},
          setEntitiesVisible: () => {},
          updateAtTime: () => 0,
          setWindowBounds: () => {},
          setTracksData: () => {},
        },
        spatialStreamClient: {
          connected: true,
          resolveUrl: (u) => 'http://localhost:8765' + u,
          onStatusChange: () => () => {},
          onFrame: () => () => {},
          onBiometricEvent: () => () => {},
          onSceneEvent: (cb) => { wsSceneCb = cb; return () => {}; },
          onAutomationEvent: (cb) => { autoCb = cb; return () => {}; },
          fetchVirtualEntities: async () => ({
            virtual_entities: [{
              entity_id: 'sh3d.allarme',
              name: 'Allarme Casa',
              domain: 'select',
              state: 'Silenzioso',
              options: ['Spento', 'Silenzioso', 'Acceso'],
            }],
          }),
          fetchSceneEvents: async (opts) => {
            fetchCalls.push({ fn: 'fetchSceneEvents', opts });
            return { status: 'ok', count: 1, events: [evt1] };
          },
          fetchSceneEvent: async (id) => {
            fetchCalls.push({ fn: 'fetchSceneEvent', id });
            return { status: 'ok', event: evt2 };
          },
          fetchTracks: async () => ({ tracks: [], count: 0 }),
          fetchDensity: async () => ({ bins: [] }),
          fetchBiometricIdentities: async () => ({ identities: [] }),
          fetchBiometricEvents: async () => ({ events: [] }),
        },
        haClient: {
          isAdmin: () => true,
          userRole: 'admin',
          onAuthChange: () => () => {},
        },
      });

      await new Promise((r) => setTimeout(r, 15));

      // Check 3-state alarm visual classes: Silenzioso -> is-silent
      const alarmBtn = root.querySelector('#btn-sec-alarm-control');
      const silentLevel = alarmBtn.dataset.alarmLevel;
      const hasSilentCls = alarmBtn.classList.contains('is-silent');
      const silentHasArmedCls = alarmBtn.classList.contains('is-armed');

      autoCb({
        type: 'virtual_entity_updated',
        entity: { entity_id: 'sh3d.allarme', domain: 'select', state: 'Acceso', options: ['Spento', 'Silenzioso', 'Acceso'] },
      });
      const armedLevel = alarmBtn.dataset.alarmLevel;
      const hasArmedCls = alarmBtn.classList.contains('is-armed');

      autoCb({
        type: 'virtual_entity_updated',
        entity: { entity_id: 'sh3d.allarme', domain: 'select', state: 'Spento', options: ['Spento', 'Silenzioso', 'Acceso'] },
      });
      const offLevel = alarmBtn.dataset.alarmLevel;

      // Switch to Eventi tab and verify card rendering + WS update
      hub.openExpanded();
      await hub.setMode('events');
      const cardCountInitial = root.querySelectorAll('.m3-scene-card').length;
      const firstSummary = root.querySelector('.m3-scene-card-summary')?.textContent || '';

      wsSceneCb({ type: 'scene_event_updated', event: evt2 });
      const cardCountAfterWs = root.querySelectorAll('.m3-scene-card').length;

      // Click first card (evt2) -> jumps to replay_start_at with entitiesVisible=true & isPlaying=true
      root.querySelector('.m3-scene-card')?.click();
      await new Promise((r) => setTimeout(r, 20));
      const modeAfterCardClick = hub.mode;
      const playingAfterCardClick = hub.isPlaying;
      const entitiesAfterCardClick = hub.entitiesVisible;
      const unixAfterCardClick = hub.currentUnix;

      // Also test deep-link openEventById
      await hub.openEventById('evt_1700000300000_c3d4');
      const deepLinkOk = hub.isExpanded && hub.mode === 'replay' && hub.isPlaying === true;

      hub.dispose();
      root.remove();

      return {
        silentLevel,
        hasSilentCls,
        silentHasArmedCls,
        armedLevel,
        hasArmedCls,
        offLevel,
        cardCountInitial,
        firstSummary,
        cardCountAfterWs,
        modeAfterCardClick,
        playingAfterCardClick,
        entitiesAfterCardClick,
        unixAfterCardClick,
        expectedReplayStart: evt2.replay_start_at,
        deepLinkOk,
        fetchCalls,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]

    assert d["silentLevel"] == "silent" and d["hasSilentCls"] is True and d["silentHasArmedCls"] is False
    assert d["armedLevel"] == "armed" and d["hasArmedCls"] is True
    assert d["offLevel"] == "off"

    assert d["cardCountInitial"] == 1
    assert "persona al cancelletto" in d["firstSummary"].lower()
    assert d["cardCountAfterWs"] == 2
    assert d["modeAfterCardClick"] == "replay"
    assert d["playingAfterCardClick"] is True
    assert d["entitiesAfterCardClick"] is True
    assert abs(d["unixAfterCardClick"] - d["expectedReplayStart"]) <= 1
    assert d["deepLinkOk"] is True


def test_f19_automation_studio_send_notification_editor():
    code = """
      const { AutomationStudioUI } = await loadModule('/src/spatial/automations/AutomationStudioUI.js');

      let savedPayload = null;
      const mockStream = {
        onAutomationEvent: () => () => {},
        onStatusChange: () => () => {},
        syncHaStates: () => {},
        fetchAutomationsBootstrap: async () => ({
          status: 'ok',
          zones: [],
          virtual_entities: [
            { entity_id: 'sh3d.allarme', name: 'Allarme Casa', domain: 'select', state: 'Silenzioso', options: ['Spento', 'Silenzioso', 'Acceso'] },
          ],
          rules: [],
          logs: [],
          identities: [{ name: 'Nicola', samples_count: 3 }],
          plates: [],
          cameras: ['Cam_Cancelletto'],
          ha_discovery: {
            connected: true,
            notify_services: [
              { service: 'notify.mobile_app_pixel_8a', name: 'Pixel 8A', kind: 'mobile_app' },
              { service: 'notify.lg_tv_cucina', name: 'Lg Tv Cucina', kind: 'tv' },
            ],
            media_players: [
              { entity_id: 'media_player.nest_hub_cucina', name: 'Nest Hub Cucina', state: 'idle' },
            ],
            tts_entities: [
              { entity_id: 'tts.google_translate_en_com', name: 'Google Translate' },
            ],
            action_entities: [
              { entity_id: 'switch.cancelletto', name: 'Cancelletto', state: 'off' },
            ],
          },
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

      uiLayer.querySelector('#btn-auto-new-rule')?.click();
      await new Promise((r) => setTimeout(r, 10));
      const nameInp = uiLayer.querySelector('#rule-inp-name');
      nameInp.value = 'Notifica Cancelletto';
      nameInp.dispatchEvent(new Event('input', { bubbles: true }));
      uiLayer.querySelector('#btn-rule-add-action')?.click();
      await new Promise((r) => setTimeout(r, 10));

      const actTypeSel = uiLayer.querySelector('[data-act-type-path="0"]');
      actTypeSel.value = 'send_notification';
      actTypeSel.dispatchEvent(new Event('change', { bubbles: true }));
      await new Promise((r) => setTimeout(r, 10));

      // Toggle mobile phone chip, Nest Hub chip, LG TV chip, and + Apri cancelletto preset
      uiLayer.querySelector('[data-act-toggle-target="0:mobile_targets:notify.mobile_app_pixel_8a"]')?.click();
      uiLayer.querySelector('[data-act-toggle-target="0:tts_targets:media_player.nest_hub_cucina"]')?.click();
      uiLayer.querySelector('[data-act-toggle-target="0:tv_targets:notify.lg_tv_cucina"]')?.click();
      uiLayer.querySelector('[data-act-notif-btn-preset="0:gate"]')?.click();
      await new Promise((r) => setTimeout(r, 10));

      const locInput = uiLayer.querySelector('[data-act-param="0:location_label"]');
      locInput.value = 'al cancelletto';
      locInput.dispatchEvent(new Event('input', { bubbles: true }));

      uiLayer.querySelector('#btn-auto-rule-save')?.click();
      await new Promise((r) => setTimeout(r, 20));

      uiLayer.remove();
      return { savedPayload };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    saved = res["data"]["savedPayload"]
    assert saved is not None
    act = saved["actions"][0]
    assert act["type"] == "send_notification"
    assert act["params"]["mobile_targets"] == ["notify.mobile_app_pixel_8a"]
    assert act["params"]["tts_targets"] == ["media_player.nest_hub_cucina"]
    assert act["params"]["tv_targets"] == ["notify.lg_tv_cucina"]
    assert act["params"]["location_label"] == "al cancelletto"
    assert act["params"]["actions"][0]["action"] == "SH3D_CALL_SERVICE:switch.turn_on:switch.cancelletto"
    assert act["params"]["actions"][0]["title"] == "Apri cancelletto"

    css_src = read_all_css(Path(__file__).resolve().parents[2])
    assert ".m3-security-panel.mode-events .m3-sec-cameras-viewport" in css_src
    assert ".m3-alarm-header-btn.is-silent" in css_src
    assert ".auto-notif-builder" in css_src
