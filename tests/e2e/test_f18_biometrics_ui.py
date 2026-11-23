"""E2E UI & unit JS tests for F18: Biometric 3D avatars, XSS safety, SecurityFabHub filters & SecurityCameraModal strip."""

from __future__ import annotations

import re
from pathlib import Path

from tests.e2e.helpers.artifacts import run_js_scenario


def test_f18_spatial_stream_client_biometric_ws_and_rest():
    code = """
      const { SpatialStreamClient } = await loadModule('/src/spatial/network/SpatialStreamClient.js');

      const fetchLog = [];
      ctx.setFetchHandler(async (url, opts = {}) => {
        fetchLog.push({ url: String(url), method: opts.method || 'GET' });
        return {
          ok: true,
          status: 200,
          json: async () => ({ status: 'ok', count: 1, events: [], identities: [], plates: [] }),
        };
      });

      const client = new SpatialStreamClient('http://localhost:8765');
      const bioReceived = [];
      const unsub = client.onBiometricEvent((ev) => bioReceived.push(ev));

      // Verify REST helper URLs & filter params
      await client.fetchTracks(1000, 2000, ['person'], 500, { identity: 'Nicola', plate: 'ab123cd', unknownOnly: true });
      await client.fetchBiometricsStatus();
      await client.fetchBiometricEvents({ tStart: 100, tEnd: 200, modality: 'face', identity: 'Nicola', limit: 25 });
      await client.fetchBiometricIdentities();
      await client.fetchBiometricPlates();
      const cropUrl = client.getBiometricCropUrl('170000_1_face_2');

      // Verify WS dispatch on biometric_event
      client.connectWebSocket();
      const ws = ctx.wsInstances[ctx.wsInstances.length - 1];
      ws._triggerOpen();
      ws._triggerMessage(JSON.stringify({ type: 'biometric_event', track_id: 5, modality: 'face', identity: 'Nicola', biometric_locked: true }));
      unsub();
      ws._triggerMessage(JSON.stringify({ type: 'biometric_event', track_id: 6, modality: 'alpr', plate: 'AB123CD' }));
      client.disconnect();
      ctx.setFetchHandler(null);

      return { fetchLog, bioReceived, cropUrl };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert len(d["bioReceived"]) == 1
    assert d["bioReceived"][0]["identity"] == "Nicola"
    assert d["cropUrl"] == "http://localhost:8765/api/v1/biometrics/crops/170000_1_face_2"

    urls = [item["url"] for item in d["fetchLog"]]
    assert "identity=Nicola" in urls[0] and "plate=AB123CD" in urls[0] and "unknown_only=true" in urls[0]
    assert urls[1] == "http://localhost:8765/api/v1/biometrics/status"
    assert "/api/v1/biometrics/events?" in urls[2] and "modality=face" in urls[2] and "limit=25" in urls[2]
    assert urls[3] == "http://localhost:8765/api/v1/biometrics/identities"
    assert urls[4] == "http://localhost:8765/api/v1/biometrics/plates"


def test_f18_avatar_factory_xss_protection_state_sources_and_plates():
    code = """
      const { SpatialAvatarFactory } = await loadModule('/src/spatial/avatars/SpatialAvatarFactory.js');
      const { TrajectoryRenderer } = await loadModule('/src/spatial/TrajectoryRenderer.js');

      const factory = new SpatialAvatarFactory();

      // 1. Person with malicious XSS identity + state.camera_sources fusion + biometric lock
      const xssGroup = factory.createAvatar({
        track_id: 12,
        class_label: 'person',
        identity: '<img src=x onerror=alert(1)>Nicola',
        confidence: 0.94,
        biometric_locked: true,
        state: { vx: 0.4, vz: 0.2, camera_sources: ['Cam_Carraio', 'Cam_Ingresso'] },
      });
      const xssHtml = xssGroup.userData.badgeEl.innerHTML;
      const personColorHex = xssGroup.userData.ringMat.color.getHex();

      // 2. Non-whitelisted car -> guest amber styling + EU I pill + escaped plate
      const guestCar = factory.createAvatar({
        track_id: 22,
        class_label: 'car',
        plate: 'FG789KL<script>',
        plate_whitelisted: false,
        biometric_locked: true,
        confidence: 0.91,
        state: { vx: 0, vz: 0, camera_sources: ['Cam_Carraio'] },
      });
      const guestHtml = guestCar.userData.badgeEl.innerHTML;
      const guestColorHex = guestCar.userData.ringMat.color.getHex();

      // 3. Motorbike supported distinctly
      const moto = factory.createAvatar({
        track_id: 33,
        class_label: 'motorbike',
        confidence: 0.88,
        state: { vx: 0, vz: 0, camera_sources: ['Cam_Portico'] },
      });
      const motoHtml = moto.userData.badgeEl.innerHTML;

      // 4. TrajectoryRenderer replay preserves biometric plate/lock fields
      const added = [];
      const sceneStub = { add: (o) => added.push(o), remove: () => {} };
      const renderer = new TrajectoryRenderer(sceneStub);
      renderer.setEntitiesVisible(true);
      renderer.loadDetections([
        {
          id: 99,
          class: 'car',
          plate: 'AB123CD',
          plate_whitelisted: true,
          plate_owner: 'Auto Nicola',
          biometric_locked: true,
          confidence: 0.96,
          x: -10,
          y: 0,
          z: 8,
          t: 10,
          camera_sources: ['Cam_Carraio', 'Cam_Portico'],
        },
      ]);
      renderer.updateAtTime(10);
      const replayEntry = renderer.entities.get('99');
      const replayBadgeHtml = replayEntry.markerGroup.userData.badgeEl.innerHTML;
      renderer.clearAll();
      factory.dispose();

      return {
        xssHtml,
        personColorHex,
        guestHtml,
        guestColorHex,
        motoHtml,
        replayBadgeHtml,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]

    assert "<img" not in d["xssHtml"] and "&lt;img" in d["xssHtml"]
    assert "Carraio+Ingresso" in d["xssHtml"]
    assert "spatial-lock-chip" in d["xssHtml"]
    assert d["personColorHex"] == 0x10B981

    assert "<script>" not in d["guestHtml"] and "&lt;SCRIPT&gt;" in d["guestHtml"]
    assert "spatial-plate-pill is-guest" in d["guestHtml"]
    assert d["guestColorHex"] == 0xF59E0B

    assert "Moto #33" in d["motoHtml"]
    assert "Auto Nicola" in d["replayBadgeHtml"]
    assert "AB123CD" in d["replayBadgeHtml"]
    assert "Carraio+Portico" in d["replayBadgeHtml"]


def test_f18_security_fab_hub_biometric_filters_events_and_camera_modal_strip():
    code = """
      const { CameraCatalog } = await loadModule('/src/video/CameraCatalog.js');
      const { SecurityFabHub } = await loadModule('/src/ui/SecurityFabHub.js');
      const { HAClient } = await loadModule('/src/ha/HAClient.js');
      const { SecurityCameraModal } = await loadModule('/src/devices/camera/SecurityCameraModal.js');
      const { SecurityCameraController } = await loadModule('/src/devices/camera/SecurityCameraController.js');

      const bioWsListeners = new Set();
      const trackQueries = [];
      const eventQueries = [];

      const spatialMock = {
        connected: true,
        onStatusChange: () => () => {},
        onFrame: () => () => {},
        onBiometricEvent: (cb) => { bioWsListeners.add(cb); return () => bioWsListeners.delete(cb); },
        getBiometricCropUrl: (id) => `/api/v1/biometrics/crops/${encodeURIComponent(id)}`,
        fetchBiometricIdentities: async () => ({
          status: 'ok',
          identities: [{ name: 'Nicola', samples_count: 8, enrolled: true }],
        }),
        fetchBiometricEvents: async (opts = {}) => {
          eventQueries.push(opts);
          return {
            status: 'ok',
            count: 2,
            events: [
              {
                id: 1,
                track_id: 41,
                modality: 'face',
                camera_id: 'Cam_Carraio',
                timestamp: 1700001000,
                identity: 'Nicola',
                biometric_locked: true,
                crop_url: '/api/v1/biometrics/crops/1700001000_41_face_2',
              },
              {
                id: 2,
                track_id: 42,
                modality: 'alpr',
                camera_id: 'Cam_Portico',
                timestamp: 1700001100,
                plate: 'AB123CD',
                plate_whitelisted: true,
                plate_owner: 'Auto Nicola',
                biometric_locked: true,
                crop_url: '/api/v1/biometrics/crops/1700001100_42_alpr_2',
              },
            ],
          };
        },
        fetchTimelineDensity: async (tStart, tEnd, buckets) => ({ status: 'ok', bins: [] }),
        fetchTracks: async (tStart, tEnd, classes, limit, filters) => {
          trackQueries.push({ tStart, tEnd, filters: filters || null });
          return { status: 'ok', count: 0, detections: [] };
        },
      };

      const root = ctx.document.createElement('div');
      ctx.document.body.appendChild(root);
      const hub = new SecurityFabHub(root, {
        cameraCatalog: new CameraCatalog(),
        videoStreamManager: { attachToVideoElement: async () => ({ mode: 'webrtc', getStatus: () => ({ mode: 'webrtc', connected: true }), onStatusChange: () => () => {} }), detachFromVideoElement: () => {} },
        recordingManager: { registerSlot: () => {}, setPlaybackRate: () => {}, setPlaying: () => {}, seekAllToTimestamp: async () => {}, queryAllSegments: async () => new Map(), detachAll: () => {}, getStorageSummary: async () => ({ configured: false }) },
        trajectoryRenderer: { setLiveMode() {}, setEntitiesVisible() {}, loadDetections() {}, clearHistorical() {}, updateAtTime() { return 0; }, interpolateLive() {} },
        spatialStreamClient: spatialMock,
        cameraController: { flyToPreset: () => {}, flyToCameraPOV: () => {} },
        assetLoader: { cameras: new Map() },
        deviceModals: { open: () => {} },
      });

      // 1. Live biometric WS event populates live strip
      bioWsListeners.forEach((cb) => cb({
        track_id: 90,
        modality: 'face',
        camera_id: 'Cam_Carraio',
        timestamp: 1700001200,
        identity: 'Nicola<xss>',
        biometric_locked: true,
        best_crop_id: '1700001200_90_face_2',
      }));
      const liveStripHidden = Boolean(root.querySelector('#sec-bio-live-strip')?.hidden);
      const liveStripHtml = root.querySelector('#sec-bio-live-strip')?.innerHTML || '';

      // 2. Open panel + switch to Cronologia -> loads identities + biometric event feed
      root.querySelector('#btn-security-fab').click();
      await hub.setMode('replay');
      for (let i = 0; i < 6; i++) await Promise.resolve();

      const liveStripHiddenInReplay = Boolean(root.querySelector('#sec-bio-live-strip')?.hidden);
      const eventCardsCount = root.querySelectorAll('.m3-bio-event-card').length;
      const idSelectEl = root.querySelector('#sec-filter-identity');
      const optionEls = Array.from(idSelectEl?.options || idSelectEl?.children || []);
      const filterOpts = optionEls.map((o) => o.getAttribute?.('value') ?? o.value);

      // 3. Apply semantic identity + plate filters
      const idSelect = root.querySelector('#sec-filter-identity');
      idSelect.value = 'Nicola';
      idSelect.dispatchEvent({ type: 'change' });
      const plateInput = root.querySelector('#sec-filter-plate');
      plateInput.value = 'ab123cd';
      plateInput.dispatchEvent({ type: 'keydown', key: 'Enter' });
      for (let i = 0; i < 6; i++) await Promise.resolve();

      const clearBtnHiddenWithFilter = Boolean(root.querySelector('#btn-sec-bio-filter-clear')?.hidden);
      const filteredQuery = trackQueries[trackQueries.length - 1];

      // 4. Click clear button -> resets filters
      root.querySelector('#btn-sec-bio-filter-clear').click();
      for (let i = 0; i < 4; i++) await Promise.resolve();
      const clearBtnHiddenAfterReset = Boolean(root.querySelector('#btn-sec-bio-filter-clear')?.hidden);

      hub.dispose();

      // 5. SecurityCameraModal biometric strip subscribes, filters by camera_id, escapes XSS, unsubscribes on destroy
      const ha = new HAClient();
      ha.initMockMode();
      const ctrl = new SecurityCameraController({ haClient: ha, spatialStreamClient: spatialMock });
      ctrl.videoStreamManager = { attachToVideoElement: async (s) => ({ streamName: s, getStatus: () => ({ mode: 'webrtc', connected: true, latencyMs: 20 }), onStatusChange: () => () => {} }), detachFromVideoElement() {} };
      const modal = new SecurityCameraModal(ctrl);
      const modalDiv = ctx.document.createElement('div');
      await modal.render(modalDiv, { entityId: 'camera.carraio_scorrevole', haClient: ha, assetLoader: { manifest: { cameras: { Cam_Carraio: {} } } } });
      for (let i = 0; i < 4; i++) await Promise.resolve();

      const stripHtmlInitial = modalDiv.querySelector('#cam-bio-strip')?.innerHTML || '';
      const stripHiddenInitial = Boolean(modalDiv.querySelector('#cam-bio-strip')?.hidden);

      // Unrelated camera event must NOT overwrite Cam_Carraio strip
      bioWsListeners.forEach((cb) => cb({
        track_id: 99,
        modality: 'alpr',
        camera_id: 'Cam_Portico',
        timestamp: 1700001300,
        plate: 'ZZ999ZZ',
      }));
      const stripAfterOtherCam = modalDiv.querySelector('#cam-bio-strip')?.innerHTML || '';

      // Matching camera event updates strip & escapes HTML
      bioWsListeners.forEach((cb) => cb({
        track_id: 100,
        modality: 'alpr',
        camera_id: 'Cam_Carraio',
        timestamp: 1700001400,
        plate: 'EF456GH',
        plate_owner: 'Auto Ospite<b>X</b>',
        plate_whitelisted: true,
        biometric_locked: true,
      }));
      const stripAfterMatchCam = modalDiv.querySelector('#cam-bio-strip')?.innerHTML || '';
      const listenersBeforeDestroy = bioWsListeners.size;
      modal.destroy();
      const listenersAfterDestroy = bioWsListeners.size;

      return {
        liveStripHidden,
        liveStripHtml,
        liveStripHiddenInReplay,
        eventCardsCount,
        filterOpts,
        clearBtnHiddenWithFilter,
        filteredQuery,
        clearBtnHiddenAfterReset,
        stripHtmlInitial,
        stripHiddenInitial,
        stripAfterOtherCam,
        stripAfterMatchCam,
        listenersBeforeDestroy,
        listenersAfterDestroy,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]

    assert d["liveStripHidden"] is False
    assert "<xss>" not in d["liveStripHtml"] and "Nicola&lt;xss&gt;" in d["liveStripHtml"]
    assert d["liveStripHiddenInReplay"] is True
    assert d["eventCardsCount"] == 2
    assert "Nicola" in d["filterOpts"] and "__unknown__" in d["filterOpts"]
    assert d["clearBtnHiddenWithFilter"] is False
    assert d["filteredQuery"]["filters"] == {"identity": "Nicola", "plate": "AB123CD", "unknownOnly": False}
    assert d["clearBtnHiddenAfterReset"] is True

    assert d["stripHiddenInitial"] is False
    assert "Nicola" in d["stripHtmlInitial"]
    assert d["stripAfterOtherCam"] == d["stripHtmlInitial"]
    assert "EF456GH" in d["stripAfterMatchCam"]
    assert "<b>X</b>" not in d["stripAfterMatchCam"] and "&lt;b&gt;X&lt;/b&gt;" in d["stripAfterMatchCam"]
    assert d["listenersBeforeDestroy"] >= 1 and d["listenersAfterDestroy"] == 0


def test_f18_biometrics_ui_icons_are_all_registered():
    repo_root = Path(__file__).resolve().parents[2]
    icon_call_re = re.compile(r"""\bicon\(\s*['"]([a-z0-9-]+)['"]""")
    discovered: set[str] = set()
    for rel in (
        "src/spatial/avatars/SpatialAvatarFactory.js",
        "src/ui/SecurityFabHub.js",
        "src/devices/camera/SecurityCameraModal.js",
    ):
        discovered.update(icon_call_re.findall((repo_root / rel).read_text(encoding="utf-8")))

    assert discovered
    res = run_js_scenario(
        {
            "action": "f11_rbac_ui",
            "target": "icons",
            "names": sorted(discovered),
        }
    )
    assert res["ok"] is True, res
    results = res["data"]["results"]
    for name in sorted(discovered):
        svg = results.get(name, "")
        assert isinstance(svg, str) and svg.startswith("<svg") and "</svg>" in svg, (
            f"Icon '{name}' missing or empty in src/ui/icons.js"
        )


def test_f18_admin_hitl_and_whitelist_rbac_ui():
    code = """
      const { CameraCatalog } = await loadModule('/src/video/CameraCatalog.js');
      const { SecurityFabHub } = await loadModule('/src/ui/SecurityFabHub.js');
      const { SpatialStreamClient } = await loadModule('/src/spatial/network/SpatialStreamClient.js');

      // 1. Verify SpatialStreamClient Admin REST endpoints
      const fetchCalls = [];
      ctx.setFetchHandler(async (url, opts = {}) => {
        fetchCalls.push({ url: String(url), method: opts.method || 'GET', body: opts.body || null });
        return { ok: true, status: 200, json: async () => ({ status: 'ok', count: 0, plates: [], identities: [] }) };
      });
      const streamClient = new SpatialStreamClient('http://localhost:8765');
      await streamClient.assignBiometricEvent(12, { identity: 'Nicola', enroll_crop: true });
      await streamClient.reloadBiometricIdentities();
      await streamClient.deleteBiometricIdentity('Nicola');
      await streamClient.upsertBiometricPlate({ plate: 'AB123CD', owner_name: 'Nicola', vehicle_label: 'Audi A3' });
      await streamClient.deleteBiometricPlate('AB123CD');
      await streamClient.pruneBiometricCrops();
      ctx.setFetchHandler(null);

      // 2. Verify SecurityFabHub RBAC gating + Admin HITL + Whitelist/Gallery controls
      const authListeners = new Set();
      const haMock = {
        isAdmin: false,
        onAuthChange: (cb) => { authListeners.add(cb); return () => authListeners.delete(cb); },
      };

      const adminCalls = [];
      let platesState = [{ plate: 'ZZ111AA', owner_name: 'Auto <script>X</script>', vehicle_label: 'Panda' }];
      let identitiesState = [{ name: 'Mario', samples_count: 4, enrolled: true }];
      let eventsState = [
        {
          id: 77,
          track_id: 501,
          modality: 'face',
          camera_id: 'Cam_Carraio',
          timestamp: 1700002000,
          identity: null,
          biometric_locked: false,
          biometric_status: 'unknown',
          crop_url: '/api/v1/biometrics/crops/1700002000_501_face_2',
        },
        {
          id: 78,
          track_id: 502,
          modality: 'alpr',
          camera_id: 'Cam_Portico',
          timestamp: 1700002100,
          plate: null,
          plate_raw: 'AB123CD',
          biometric_locked: false,
          biometric_status: 'unknown',
        },
      ];

      const spatialMock = {
        connected: true,
        onStatusChange: () => () => {},
        onFrame: () => () => {},
        onBiometricEvent: () => () => {},
        getBiometricCropUrl: (id) => `/api/v1/biometrics/crops/${encodeURIComponent(id)}`,
        fetchTimelineDensity: async () => ({ status: 'ok', bins: [] }),
        fetchTracks: async () => ({ status: 'ok', count: 0, detections: [] }),
        fetchBiometricEvents: async () => ({ status: 'ok', count: eventsState.length, events: eventsState }),
        fetchBiometricIdentities: async () => ({ status: 'ok', count: identitiesState.length, identities: identitiesState }),
        fetchBiometricPlates: async () => ({ status: 'ok', count: platesState.length, plates: platesState }),
        assignBiometricEvent: async (id, payload) => {
          adminCalls.push({ op: 'assign', id, payload });
          eventsState = eventsState.map((ev) => (
            ev.id === id
              ? { ...ev, identity: payload.identity || null, biometric_locked: true, biometric_status: 'locked', reviewed_by: 'Admin' }
              : ev
          ));
          return { status: 'ok', event: eventsState.find((e) => e.id === id), enrolled_sample: true };
        },
        upsertBiometricPlate: async (payload) => {
          adminCalls.push({ op: 'upsertPlate', payload });
          platesState = [...platesState, { plate: payload.plate.toUpperCase(), owner_name: payload.owner_name, vehicle_label: payload.vehicle_label }];
          return { status: 'ok', count: platesState.length, plates: platesState };
        },
        deleteBiometricPlate: async (plate) => {
          adminCalls.push({ op: 'deletePlate', plate });
          platesState = platesState.filter((p) => p.plate !== plate);
          return { status: 'ok', count: platesState.length, plates: platesState };
        },
        reloadBiometricIdentities: async () => {
          adminCalls.push({ op: 'reloadIdentities' });
          return { status: 'ok', count: identitiesState.length, identities: identitiesState };
        },
        deleteBiometricIdentity: async (name) => {
          adminCalls.push({ op: 'deleteIdentity', name });
          identitiesState = identitiesState.filter((i) => i.name !== name);
          return { status: 'ok', deleted: name };
        },
      };

      const root = ctx.document.createElement('div');
      ctx.document.body.appendChild(root);
      const hub = new SecurityFabHub(root, {
        cameraCatalog: new CameraCatalog(),
        videoStreamManager: { attachToVideoElement: async () => ({ mode: 'webrtc', getStatus: () => ({ mode: 'webrtc', connected: true }), onStatusChange: () => () => {} }), detachFromVideoElement: () => {} },
        recordingManager: { registerSlot: () => {}, setPlaybackRate: () => {}, setPlaying: () => {}, seekAllToTimestamp: async () => {}, queryAllSegments: async () => new Map(), detachAll: () => {}, getStorageSummary: async () => ({ configured: false }) },
        trajectoryRenderer: { setLiveMode() {}, setEntitiesVisible() {}, loadDetections() {}, clearHistorical() {}, updateAtTime() { return 0; }, interpolateLive() {} },
        spatialStreamClient: spatialMock,
        cameraController: { flyToPreset: () => {}, flyToCameraPOV: () => {} },
        assetLoader: { cameras: new Map() },
        deviceModals: { open: () => {} },
        haClient: haMock,
      });

      root.querySelector('#btn-security-fab').click();
      await hub.setMode('replay');
      for (let i = 0; i < 6; i++) await Promise.resolve();

      // Resident: admin button hidden/disabled and 0 HITL buttons rendered
      const resAdminBtnVisible = helpers.isElementVisibleAndEnabled(root.querySelector('#btn-sec-bio-admin'));
      const resHitlCount = root.querySelectorAll('.m3-bio-hitl-btn').length;

      // Switch to Admin dynamically
      haMock.isAdmin = true;
      authListeners.forEach((cb) => cb({ isAdmin: true, authenticated: true }));
      for (let i = 0; i < 6; i++) await Promise.resolve();

      const adminBtnVisible = helpers.isElementVisibleAndEnabled(root.querySelector('#btn-sec-bio-admin'));
      const adminHitlCount = root.querySelectorAll('.m3-bio-hitl-btn').length;

      // Open Admin panel & check whitelist/gallery XSS escaping + mutations
      root.querySelector('#btn-sec-bio-admin').click();
      for (let i = 0; i < 6; i++) await Promise.resolve();
      const adminPanelHiddenAfterOpen = Boolean(root.querySelector('#sec-bio-admin-panel')?.hidden);
      const platesHtml = root.querySelector('#sec-admin-plates-list')?.innerHTML || '';

      root.querySelector('#sec-admin-plate-input').value = 'fg456hj';
      root.querySelector('#sec-admin-plate-owner').value = 'Ospite';
      root.querySelector('#sec-admin-plate-vehicle').value = 'Golf';
      root.querySelector('#btn-sec-admin-plate-add').click();
      for (let i = 0; i < 6; i++) await Promise.resolve();

      root.querySelector('[data-del-plate="ZZ111AA"]').click();
      for (let i = 0; i < 6; i++) await Promise.resolve();

      root.querySelector('#btn-sec-admin-reload-gallery').click();
      for (let i = 0; i < 6; i++) await Promise.resolve();

      root.querySelector('[data-del-identity="Mario"]').click();
      for (let i = 0; i < 6; i++) await Promise.resolve();

      // Trigger HITL editor on face event 77 and assign XSS-containing identity
      root.querySelector('.m3-bio-hitl-btn[data-hitl-event-id="77"]').click();
      const hitlEditorHiddenOpen = Boolean(root.querySelector('#sec-bio-hitl-editor')?.hidden);
      root.querySelector('#sec-hitl-identity-input').value = 'Nicola<b>';
      root.querySelector('#btn-sec-hitl-save').click();
      for (let i = 0; i < 8; i++) await Promise.resolve();

      const eventsHtmlAfterAssign = root.querySelector('#sec-bio-events-list')?.innerHTML || '';

      // Demote back to Resident -> closes admin panel & HITL editor and hides admin button
      haMock.isAdmin = false;
      authListeners.forEach((cb) => cb({ isAdmin: false, authenticated: true }));
      for (let i = 0; i < 4; i++) await Promise.resolve();

      const demotedAdminBtnVisible = helpers.isElementVisibleAndEnabled(root.querySelector('#btn-sec-bio-admin'));
      const demotedAdminPanelHidden = Boolean(root.querySelector('#sec-bio-admin-panel')?.hidden);
      const demotedHitlEditorHidden = Boolean(root.querySelector('#sec-bio-hitl-editor')?.hidden);
      const demotedHitlCount = root.querySelectorAll('.m3-bio-hitl-btn').length;

      hub.dispose();

      return {
        fetchCalls,
        resAdminBtnVisible,
        resHitlCount,
        adminBtnVisible,
        adminHitlCount,
        adminPanelHiddenAfterOpen,
        platesHtml,
        hitlEditorHiddenOpen,
        eventsHtmlAfterAssign,
        adminCalls,
        demotedAdminBtnVisible,
        demotedAdminPanelHidden,
        demotedHitlEditorHidden,
        demotedHitlCount,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]

    urls = [(c["method"], c["url"]) for c in d["fetchCalls"]]
    assert urls == [
        ("POST", "http://localhost:8765/api/v1/biometrics/events/12/assign"),
        ("POST", "http://localhost:8765/api/v1/biometrics/identities/reload"),
        ("DELETE", "http://localhost:8765/api/v1/biometrics/identities/Nicola"),
        ("PUT", "http://localhost:8765/api/v1/biometrics/plates"),
        ("DELETE", "http://localhost:8765/api/v1/biometrics/plates/AB123CD"),
        ("POST", "http://localhost:8765/api/v1/biometrics/crops/prune"),
    ]

    assert d["resAdminBtnVisible"] is False
    assert d["resHitlCount"] == 0

    assert d["adminBtnVisible"] is True
    assert d["adminHitlCount"] == 2
    assert d["adminPanelHiddenAfterOpen"] is False
    assert "<script>" not in d["platesHtml"] and "&lt;script&gt;X&lt;/script&gt;" in d["platesHtml"]
    assert d["hitlEditorHiddenOpen"] is False
    assert "<b>" not in d["eventsHtmlAfterAssign"] and "Nicola&lt;b&gt;" in d["eventsHtmlAfterAssign"]
    assert "Verificato" in d["eventsHtmlAfterAssign"]

    ops = [c["op"] for c in d["adminCalls"]]
    assert ops == ["upsertPlate", "deletePlate", "reloadIdentities", "deleteIdentity", "assign"]

    assert d["demotedAdminBtnVisible"] is False
    assert d["demotedAdminPanelHidden"] is True
    assert d["demotedHitlEditorHidden"] is True
    assert d["demotedHitlCount"] == 0
