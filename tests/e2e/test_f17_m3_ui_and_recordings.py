"""Tests for Material 3 UI/UX Redesign, Multi-Camera Security Hub, Thermal Controller & OOP Recording Service."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from spatial_server.config import SpatialServerConfig
from spatial_server.main import create_app
from spatial_server.recordings.filesystem_nvr import FilesystemNvrArchiveRepository
from tests.e2e.helpers.artifacts import run_js_scenario


def _invoke_zero_await(coro):
    """Drives an async FastAPI route handler that performs synchronous repository work."""
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    finally:
        coro.close()
    raise RuntimeError("Coroutine unexpectedly yielded")


def _get_route_endpoint(app, path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route.endpoint
    raise AssertionError(f"Route not registered: {path}")


# ---------------------------------------------------------------------------
# Backend: OOP Recording Archive & FastAPI Endpoints
# ---------------------------------------------------------------------------


def _make_config_with_nvr(tmp_path: Path, nvr_dir: Path | None) -> SpatialServerConfig:
    base = SpatialServerConfig.from_env()
    return SpatialServerConfig(
        host=base.host,
        port=base.port,
        manifest_path=base.manifest_path,
        glb_path=base.glb_path,
        sqlite_db_path=tmp_path / "test_tracks.db",
        calibration_override_path=tmp_path / "calibs.json",
        data_dir=tmp_path,
        models_dir=base.models_dir,
        default_ingestion_mode="synthetic",
        go2rtc_rtsp_url=base.go2rtc_rtsp_url,
        mqtt_host=base.mqtt_host,
        mqtt_port=base.mqtt_port,
        mqtt_user="",
        mqtt_password="",
        mqtt_topic_prefix=base.mqtt_topic_prefix,
        openvino_device=base.openvino_device,
        openvino_model_path=base.openvino_model_path,
        db_retention_days=7,
        face_webhook_url="",
        auth_required=False,
        nvr_storage_dir=nvr_dir,
    )


def test_f17_backend_nvr_unconfigured_graceful_response(tmp_path: Path):
    cfg = _make_config_with_nvr(tmp_path, nvr_dir=None)
    app = create_app(cfg)
    req = SimpleNamespace(app=app)

    status_ep = _get_route_endpoint(app, "/api/v1/recordings/status")
    resolve_ep = _get_route_endpoint(app, "/api/v1/recordings/{camera_id}/resolve")

    body = _invoke_zero_await(status_ep(request=req, _user=None))
    assert body["configured"] is False
    assert body["storage_type"] == "pc_nvr_hdd"

    rbody = _invoke_zero_await(resolve_ep(request=req, camera_id="Cam_Carraio", t=1795092025.0, _user=None))
    assert rbody["available"] is False
    assert rbody["reason"] == "storage_not_configured"


def test_f17_backend_nvr_filesystem_segments_resolve_and_stream(tmp_path: Path):
    nvr_root = tmp_path / "Surveillance"
    cam_dir = nvr_root / "Cam_Carraio" / "2026-11-19"
    cam_dir.mkdir(parents=True)
    seg_file = cam_dir / "1795092000_60.mp4"
    seg_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")

    repo = FilesystemNvrArchiveRepository(storage_dir=nvr_root)
    assert repo.is_configured is True
    assert repo.list_cameras() == ["Cam_Carraio"]

    cfg = _make_config_with_nvr(tmp_path, nvr_dir=nvr_root)
    app = create_app(cfg)
    req = SimpleNamespace(app=app)

    status_ep = _get_route_endpoint(app, "/api/v1/recordings/status")
    segments_ep = _get_route_endpoint(app, "/api/v1/recordings/{camera_id}/segments")
    resolve_ep = _get_route_endpoint(app, "/api/v1/recordings/{camera_id}/resolve")
    file_ep = _get_route_endpoint(app, "/api/v1/recordings/{camera_id}/file/{filename}")

    st = _invoke_zero_await(status_ep(request=req, _user=None))
    assert st["configured"] is True
    assert "Cam_Carraio" in st["cameras"]

    segs = _invoke_zero_await(
        segments_ep(request=req, camera_id="Cam_Carraio", t_start=1795091900.0, t_end=1795092200.0, _user=None)
    )
    assert segs["count"] == 1
    assert segs["segments"][0]["duration_sec"] == 60.0

    hit = _invoke_zero_await(resolve_ep(request=req, camera_id="Cam_Carraio", t=1795092025.5, _user=None))
    assert hit["available"] is True
    assert hit["seek_offset_sec"] == 25.5
    assert hit["segment"]["stream_url"] == "/api/v1/recordings/Cam_Carraio/file/1795092000_60.mp4"

    miss = _invoke_zero_await(resolve_ep(request=req, camera_id="Cam_Carraio", t=1795095000.0, _user=None))
    assert miss["available"] is False
    assert miss["reason"] == "no_recording"

    file_resp = _invoke_zero_await(
        file_ep(request=req, camera_id="Cam_Carraio", filename="1795092000_60.mp4", _user=None)
    )
    assert isinstance(file_resp, FileResponse)
    assert file_resp.media_type == "video/mp4"

    with pytest.raises(HTTPException) as exc_info:
        _invoke_zero_await(file_ep(request=req, camera_id="Cam_Carraio", filename="../secret.mp4", _user=None))
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Frontend: NavigationFabHub, ThermalController, SecurityFabHub & Icons
# ---------------------------------------------------------------------------


def test_f17_frontend_nav_fab_hub_sections_and_contextual_devices():
    code = """
      const { NavigationFabHub } = await loadModule('/src/ui/NavigationFabHub.js');
      const root = ctx.document.createElement('div');
      ctx.document.body.appendChild(root);

      const flown = [];
      const openedModals = [];
      let closedModals = 0;

      const hub = new NavigationFabHub(root, {
        cameraController: {
          flyToPreset: (preset) => flown.push(preset),
          startFollowing: () => flown.push('follow_deebot'),
        },
        deviceModals: {
          open: (entityId) => openedModals.push(entityId),
          close: () => { closedModals += 1; },
        },
        haClient: {
          subscribeEntities: () => () => {},
        },
      });

      const viewBtns = root.querySelectorAll('[data-hub-view]');
      const deviceBtns = root.querySelectorAll('[data-hub-device]');
      const viewLabels = viewBtns.map((b) => b.querySelector('.m3-tile-title').textContent.trim());
      const deviceLabels = deviceBtns.map((b) => b.querySelector('.m3-tile-title').textContent.trim());

      // Apri FAB e clicca una vista
      root.querySelector('#btn-nav-fab').click();
      const openAfterFab = hub.isOpen;
      root.querySelector('[data-hub-view="topdown"]').click();
      const openAfterView = hub.isOpen;

      // Clicca ognuno dei 5 dispositivi (con Deebot prima senza coordinate -> fallback preset, poi con coordinate -> zoomToRobot)
      for (const dev of ['thermal', 'irrigation', 'tv', 'dishwasher', 'deebot']) {
        root.querySelector(`[data-hub-device="${dev}"]`).click();
      }

      // Simula coordinate valide sul controller Deebot e verifica che usi zoomToRobot invece del preset statico
      const { deviceRegistry } = await loadModule('/src/devices/DeviceRegistry.js');
      const vacCtrl = deviceRegistry.get('vacuum');
      const prevTelemetry = vacCtrl.lastTelemetry;
      vacCtrl.lastTelemetry = { targetX: '12.0', targetZ: '3.0' };
      root.querySelector('[data-hub-device="deebot"]').click();
      vacCtrl.lastTelemetry = prevTelemetry;

      hub.dispose();
      return {
        viewLabels,
        deviceLabels,
        openAfterFab,
        openAfterView,
        flown,
        openedModals,
        closedModals,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["viewLabels"] == ["Panoramica", "Pianta", "Giardino", "Salotto", "Sala da Pranzo", "Cucina"]
    assert d["deviceLabels"] == ["Impianto Termico", "Irrigazione", "TV", "Lavastoviglie", "Deebot"]
    assert d["openAfterFab"] is True
    assert d["openAfterView"] is False
    assert d["closedModals"] == 1
    assert d["flown"] == [
        "topdown",
        "device_thermal",
        "device_irrigation",
        "device_tv",
        "device_dishwasher",
        "device_deebot",
        "follow_deebot",
    ]
    assert d["openedModals"] == [
        "switch.smart_switch_caldaia",
        "input_boolean.irrigazione_attiva",
        "media_player.lg_webos_smart_tv",
        "sensor.lavastoviglie_stato_di_funzionamento",
        "vacuum.deebot",
        "vacuum.deebot",
    ]


def test_f17_frontend_thermal_controller_and_modal():
    code = """
      const { deviceRegistry } = await loadModule('/src/devices/DeviceRegistry.js');
      const { HAClient } = await loadModule('/src/ha/HAClient.js');
      const ha = new HAClient();
      ha.initMockMode();

      const ctrl = deviceRegistry.findControllerForEntity('switch.smart_switch_caldaia');
      const bySensor = deviceRegistry.findControllerForEntity('sensor.temperatura_caldaia');
      const byWait = deviceRegistry.findControllerForEntity('sensor.minuti_di_attesa');
      const byAutoValve = deviceRegistry.findControllerForEntity('automation.controllo_valvola_acqua_calda');
      const container = ctx.document.createElement('div');
      ctrl.renderModal(container, ha.getEntity('switch.smart_switch_caldaia'), { haClient: ha });

      const highBefore = container.querySelector('#thermal-val-puffer-high')?.textContent;
      const litersBefore = container.querySelector('#thermal-val-liters')?.textContent;
      const showerMinsBefore = container.querySelector('#thermal-val-shower')?.textContent;
      const waitMinsBefore = container.querySelector('#thermal-val-wait')?.textContent;
      const desiredBefore = container.querySelector('#thermal-val-desired')?.textContent;
      const adviceInitial = container.querySelector('#thermal-advice-text')?.textContent;
      const boilerBefore = ctrl.isBoilerOn();

      // Verifica incremento minuti desiderati & toggle caldaia
      container.querySelector('#btn-thermal-desired-inc').click();
      ctrl.update3D(ha.getEntity('input_number.minuti_doccia_desiderati'), ha.mockEntities);
      const desiredAfterInc = container.querySelector('#thermal-val-desired')?.textContent;

      container.querySelector('#btn-thermal-boiler-toggle').click();
      ctrl.update3D(ha.getEntity('switch.smart_switch_caldaia'), ha.mockEntities);
      const boilerAfter = ctrl.isBoilerOn();

      // Verifica messaggio dinamico con doccia in corso + attesa > 0
      ha.setMockEntityState('input_boolean.doccia_in_corso', 'on');
      ha.setMockEntityState('sensor.minuti_di_attesa', '7');
      ctrl.update3D(ha.getEntity('sensor.minuti_di_attesa'), ha.mockEntities);
      const adviceShowerAndWait = container.querySelector('#thermal-advice-text')?.textContent;

      // Verifica messaggio quando minuti disponibili = 0
      ha.setMockEntityState('input_boolean.doccia_in_corso', 'off');
      ha.setMockEntityState('sensor.minuti_doccia_disponibili', '0');
      ctrl.update3D(ha.getEntity('sensor.minuti_doccia_disponibili'), ha.mockEntities);
      const adviceZeroAvail = container.querySelector('#thermal-advice-text')?.textContent;

      // Verifica visibilità condizionale della valvola manuale nella scheda Parametri
      container.querySelector('[data-thermal-tab="params"]').click();
      const manualHiddenWhenAutoOn = Boolean(container.querySelector('#thermal-manual-valve-row')?.hidden);
      container.querySelector('#btn-thermal-auto-valve').click();
      ctrl.update3D(ha.getEntity('automation.controllo_valvola_acqua_calda'), ha.mockEntities);
      const manualHiddenWhenAutoOff = Boolean(container.querySelector('#thermal-manual-valve-row')?.hidden);

      // Verifica assenza di "Altre informazioni" in Acqua Calda e assenza di "Calda Caldaia" in Temperature
      const hasAltreInfoBtn = Boolean(container.querySelector('#btn-thermal-goto-temps') || container.querySelector('#btn-thermal-goto-params'));
      const hasBoilerHotInTemps = Boolean(container.querySelector('#thermal-val-boiler-hot-temps'));
      const hasBoilerSolidBox = Boolean(container.querySelector('#thermal-boiler-fill'));
      const pufferRowsCount = container.querySelectorAll('[data-thermal-panel="temps"] .thermal-stratification-box:not(.thermal-boiler-box) .thermal-reading-row').length;

      // Verifica soglie colore dinamiche rispetto a sensor.temperatura_calda_caldaia (48.5°C)
      // 57.9°C (+9.4 > +1) -> hot (rosso), 43.8°C (-4.7 <= -0.5) -> cool (azzurro), 48.2°C (-0.3) -> warm (arancione)
      const zoneHighInit = container.querySelector('#thermal-row-puffer-high')?.dataset.thermalZone;
      const zoneLowInit = container.querySelector('#thermal-row-puffer-low')?.dataset.thermalZone;
      const zoneBoilerCool = container.querySelector('#thermal-row-boiler')?.dataset.thermalZone;

      ha.setMockEntityState('sensor.temperatura_caldaia', '48.2');
      ctrl.update3D(ha.getEntity('sensor.temperatura_caldaia'), ha.mockEntities);
      const zoneBoilerWarm = container.querySelector('#thermal-row-boiler')?.dataset.thermalZone;

      ha.setMockEntityState('sensor.temperatura_caldaia', '50.0');
      ctrl.update3D(ha.getEntity('sensor.temperatura_caldaia'), ha.mockEntities);
      const zoneBoilerHot = container.querySelector('#thermal-row-boiler')?.dataset.thermalZone;

      // Verifica programmazione accensione caldaia
      container.querySelector('#btn-thermal-sched-on').click();
      ctrl.update3D(ha.getEntity('automation.accensione_programmata_caldaia'), ha.mockEntities);
      const schedOnAfter = ctrl.isBoilerScheduleOnEnabled();

      ctrl.onModalClose();

      return {
        ctrlId: ctrl?.id,
        matchesSensor: bySensor === ctrl,
        matchesWait: byWait === ctrl,
        matchesAutoValve: byAutoValve === ctrl,
        highBefore,
        litersBefore,
        showerMinsBefore,
        waitMinsBefore,
        desiredBefore,
        desiredAfterInc,
        adviceInitial,
        adviceShowerAndWait,
        adviceZeroAvail,
        boilerBefore,
        boilerAfter,
        manualHiddenWhenAutoOn,
        manualHiddenWhenAutoOff,
        hasAltreInfoBtn,
        hasBoilerHotInTemps,
        hasBoilerSolidBox,
        pufferRowsCount,
        zoneHighInit,
        zoneLowInit,
        zoneBoilerCool,
        zoneBoilerWarm,
        zoneBoilerHot,
        schedOnAfter,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["ctrlId"] == "thermal"
    assert d["matchesSensor"] is True
    assert d["matchesWait"] is True
    assert d["matchesAutoValve"] is True
    assert d["highBefore"] == "57.9°C"
    assert d["litersBefore"] == "68 L"
    assert d["showerMinsBefore"] == "8 min"
    assert d["waitMinsBefore"] == "0 min"
    assert d["desiredBefore"] == "12 min"
    assert d["desiredAfterInc"] == "13 min"
    assert "Hai a disposizione 8 minuti di acqua calda." in d["adviceInitial"]
    assert "La caldaia è accesa, non hai bisogno di attendere." in d["adviceInitial"]
    assert "Qualcuno è già in doccia. Ad ogni modo," in d["adviceShowerAndWait"]
    assert "attendi 7 minuti." in d["adviceShowerAndWait"]
    assert "Devi aspettare 7 minuti per avere l'acqua calda." in d["adviceZeroAvail"]
    assert d["boilerBefore"] is True
    assert d["boilerAfter"] is False
    assert d["manualHiddenWhenAutoOn"] is True
    assert d["manualHiddenWhenAutoOff"] is False
    assert d["hasAltreInfoBtn"] is False
    assert d["hasBoilerHotInTemps"] is False
    assert d["hasBoilerSolidBox"] is True
    assert d["pufferRowsCount"] == 2
    assert d["zoneHighInit"] == "hot"
    assert d["zoneLowInit"] == "cool"
    assert d["zoneBoilerCool"] == "cool"
    assert d["zoneBoilerWarm"] == "warm"
    assert d["zoneBoilerHot"] == "hot"
    assert d["schedOnAfter"] is True


def test_f17_frontend_security_hub_multicam_180_replay_darkstate_and_strip():
    code = """
      const { CameraCatalog } = await loadModule('/src/video/CameraCatalog.js');
      const { CameraRecordingManager, SpatialServerNvrProvider } = await loadModule('/src/video/recordings/index.js');
      const { SecurityFabHub } = await loadModule('/src/ui/SecurityFabHub.js');

      const catalog = new CameraCatalog();
      catalog.registerCamera({
        id: 'Cam_Giardino_180',
        name: 'Telecamera Giardino 180°',
        shortName: 'Giardino',
        entityId: 'camera.giardino_180',
        mainStream: 'giardino_main',
        subStream: 'giardino_sub',
        fovH: 180,
        aspectRatio: 3.2,
        isPanoramic180: true,
      });

      const attachedLive = [];
      const videoStreamManagerMock = {
        attachToVideoElement: async (streamName, videoEl) => {
          attachedLive.push(streamName);
          return { mode: 'webrtc', getStatus: () => ({ mode: 'webrtc', connected: true, latencyMs: 42 }), onStatusChange: () => () => {} };
        },
        detachFromVideoElement: () => {},
      };

      const nvrProvider = new SpatialServerNvrProvider({
        spatialStreamClient: {
          baseUrl: '',
          requestJson: async (path) => {
            if (path.includes('/resolve')) {
              return { status: 'ok', available: false, reason: 'no_recording' };
            }
            if (path.includes('/segments')) {
              return { status: 'ok', segments: [] };
            }
            return { status: 'ok', configured: false };
          },
        },
      });
      const recMgr = new CameraRecordingManager({ cameraCatalog: catalog, providers: [nvrProvider] });

      let entitiesVisibleFlag = false;
      const trajMock = {
        setLiveMode: () => {},
        setEntitiesVisible: (v) => { entitiesVisibleFlag = v; },
        loadDetections: () => {},
        clearHistorical: () => {},
        updateAtTime: () => {},
        interpolateLive: () => {},
      };

      const root = ctx.document.createElement('div');
      ctx.document.body.appendChild(root);

      const hub = new SecurityFabHub(root, {
        cameraCatalog: catalog,
        videoStreamManager: videoStreamManagerMock,
        recordingManager: recMgr,
        trajectoryRenderer: trajMock,
        spatialStreamClient: { connected: false, onStatusChange: () => () => {}, onFrame: () => () => {} },
        cameraController: { flyToPreset: () => {}, flyToCameraPOV: () => {} },
        assetLoader: { cameras: new Map() },
        deviceModals: { open: () => {} },
      });

      // 1. Apri FAB Sicurezza in Live -> SOLO telecamere visibili, controlli cronologia nascosti, nessun pulsante Demo 3D
      root.querySelector('#btn-security-fab').click();
      for (let i = 0; i < 8; i++) await Promise.resolve();

      const tiles = root.querySelectorAll('.m3-cam-tile');
      const panoramicTile = tiles.find((t) => t.dataset.cameraId === 'Cam_Giardino_180');
      const panoramicAspect = panoramicTile?.style.getPropertyValue('--cam-aspect');
      const isPanoramicClass = panoramicTile?.classList.contains('is-panoramic');
      const historyHiddenInLive = Boolean(root.querySelector('#sec-history-section')?.hidden);
      const hasDemoButton = Boolean(root.querySelector('#btn-sec-demo-3d'));

      // 2. Passa a Cronologia -> controlli cronologia visibili + stato scuro/nero robusto su assenza registrazione
      await hub.setMode('replay');
      for (let i = 0; i < 8; i++) await Promise.resolve();
      const historyHiddenInReplay = Boolean(root.querySelector('#sec-history-section')?.hidden);
      const darkStates = tiles.map((t) => t.classList.contains('is-no-recording'));

      // 3. Riduci a Striscia in basso -> preserva video DOM elements senza ricrearli
      const videoRefBefore = panoramicTile.querySelector('video');
      root.querySelector('#btn-sec-strip-toggle').click();
      const isStripState = hub.isStrip;
      const panelHasStripClass = root.querySelector('#m3-security-panel').classList.contains('mode-strip');
      const videoRefAfter = root.querySelector('[data-camera-id="Cam_Giardino_180"] video');

      // 4. Torna a Live -> controlli cronologia nuovamente nascosti
      await hub.setMode('live');
      const historyHiddenBackInLive = Boolean(root.querySelector('#sec-history-section')?.hidden);

      hub.dispose();
      return {
        camCount: tiles.length,
        attachedLive,
        panoramicAspect,
        isPanoramicClass,
        historyHiddenInLive,
        historyHiddenInReplay,
        historyHiddenBackInLive,
        hasDemoButton,
        darkStates,
        entitiesVisibleFlag,
        isStripState,
        panelHasStripClass,
        sameVideoElement: videoRefBefore === videoRefAfter,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["camCount"] == 2
    assert set(d["attachedLive"]) == {"carraio_sub", "giardino_sub"}
    assert d["panoramicAspect"] == "3.2"
    assert d["isPanoramicClass"] is True
    assert d["historyHiddenInLive"] is True
    assert d["historyHiddenInReplay"] is False
    assert d["historyHiddenBackInLive"] is True
    assert d["hasDemoButton"] is False
    assert d["darkStates"] == [True, True]
    assert d["entitiesVisibleFlag"] is True
    assert d["isStripState"] is True
    assert d["panelHasStripClass"] is True
    assert d["sameVideoElement"] is True


def test_f17_responsive_camera_presets_and_device_refinements():
    repo_root = Path(__file__).resolve().parents[2]

    # 1. Verifica assenza di riferimenti "gettini" / "Demo 3D" nei file UI e presenza telecomando TV sempre aperto
    irrig_modal_src = (repo_root / "src" / "devices" / "irrigation" / "IrrigationModal.js").read_text(encoding="utf-8")
    assert "Gettini Attivi" not in irrig_modal_src
    assert "Gettini ON" not in irrig_modal_src

    interaction_src = (repo_root / "src" / "core" / "InteractionManager.js").read_text(encoding="utf-8")
    assert "4 gettini" not in interaction_src

    sec_src = (repo_root / "src" / "ui" / "SecurityFabHub.js").read_text(encoding="utf-8")
    assert "Demo 3D" not in sec_src
    assert "activateSyntheticDemoScenario" not in sec_src

    # 2. Verifica runtime CameraController (avvio in Panoramica responsive PC vs Mobile, lavanderia dentro muro, lavastoviglie diagonale)
    #    e TVModal (telecomando sempre visibile senza toggle)
    code = """
      const { TVModal } = await loadModule('/src/devices/tv/TVModal.js');
      const { HAClient } = await loadModule('/src/ha/HAClient.js');
      const ha = new HAClient();
      ha.initMockMode();
      const { deviceRegistry } = await loadModule('/src/devices/DeviceRegistry.js');
      const tvCtrl = deviceRegistry.get('tv');
      const tvContainer = ctx.document.createElement('div');
      tvCtrl.renderModal(tvContainer, ha.getEntity('media_player.lg_webos_smart_tv'), { haClient: ha });
      const hasRemoteToggleBtn = Boolean(tvContainer.querySelector('#btn-toggle-remote'));
      const remoteSlotOpen = Boolean(tvContainer.querySelector('#remote-slot')?.classList.contains('open'));
      const remoteHasChildren = (tvContainer.querySelector('#remote-slot')?.children?.length || 0) > 0;
      tvCtrl.onModalClose();

      // Verifica IrrigationModal senza colonna gettini
      const irrigCtrl = deviceRegistry.get('irrigation');
      const irrigContainer = ctx.document.createElement('div');
      irrigCtrl.renderModal(irrigContainer, ha.getEntity('input_boolean.irrigazione_attiva'), { haClient: ha });
      const irrigStatBoxes = irrigContainer.querySelectorAll('.irrigation-stat-box').length;
      const irrigTextHasGettini = /gettin/i.test(irrigContainer.innerHTML);
      irrigCtrl.onModalClose();

      // Verifica che nessun pannello dispositivo mostri codici tecnici entity_id nel sottotitolo
      const { DeviceModals } = await loadModule('/src/ha/DeviceModals.js');
      const drawer = ctx.document.createElement('div');
      ctx.document.body.appendChild(drawer);
      const modals = new DeviceModals(drawer, ha, { flyToPreset: () => {}, startFollowing: () => {} }, { cameras: new Map() });
      const checkedSubtitles = {};
      for (const entId of [
        'sensor.lavastoviglie_stato_di_funzionamento',
        'media_player.lg_webos_smart_tv',
        'vacuum.deebot',
        'switch.smart_switch_caldaia',
        'input_boolean.irrigazione_attiva',
        'light.forno',
        'switch.switch_casa_interruttore_1',
      ]) {
        modals.open(entId);
        checkedSubtitles[entId] = drawer.querySelector('#modal-subtitle')?.textContent || '';
        modals.close();
      }

      return {
        hasRemoteToggleBtn,
        remoteSlotOpen,
        remoteHasChildren,
        irrigStatBoxes,
        irrigTextHasGettini,
        checkedSubtitles,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["hasRemoteToggleBtn"] is False
    assert d["remoteSlotOpen"] is True
    assert d["remoteHasChildren"] is True
    assert d["irrigStatBoxes"] == 2
    assert d["irrigTextHasGettini"] is False
    for ent_id, sub in d["checkedSubtitles"].items():
        assert ent_id not in sub, f"Codice tecnico '{ent_id}' ancora visibile nel sottotitolo '{sub}'"
        assert "." not in sub, f"Possibile codice entity_id nel sottotitolo '{sub}'"

    # 3. Verifica loghi SVG TV (Netflix & YouTube corretti) e CSS FAB + icone sorgenti
    netflix_svg = (repo_root / "public" / "logos" / "netflix.svg").read_text(encoding="utf-8")
    assert "M140.8 19.3" not in netflix_svg
    assert 'viewBox="0 0 666 200"' in netflix_svg

    youtube_svg = (repo_root / "public" / "logos" / "youtube.svg").read_text(encoding="utf-8")
    assert 'viewBox="0 0 630 180"' in youtube_svg
    assert ">YouTube<" in youtube_svg

    css_src = (repo_root / "src" / "style.css").read_text(encoding="utf-8")
    assert ".ui-layer.nav-expanded-active .m3-fab-security" in css_src
    assert ".ui-layer.sec-expanded-active .m3-fab-nav" in css_src
    assert ".m3-hub-tile-device:first-child:nth-last-child(odd)" in css_src
    assert re.search(r"\.chip-service-logo\s*\{[^}]*height:\s*22px;[^}]*width:\s*auto;", css_src, re.S) is not None

    # 4. Verifica coordinate camera chiave in CameraController.js
    cam_src = (repo_root / "src" / "core" / "CameraController.js").read_text(encoding="utf-8")
    assert "this.applyPresetImmediate('overview')" in cam_src
    assert "this.mobilePresets = {" in cam_src
    assert "isPortraitViewport()" in cam_src
    # Verifica che device_thermal sia dentro il muro nord della lavanderia (Z > 12.63)
    m_thermal = re.search(r"device_thermal:\s*\{[^}]*eye:\s*new THREE\.Vector3\(([^)]+)\)", cam_src)
    assert m_thermal is not None
    thermal_z = float(m_thermal.group(1).split(",")[2].strip())
    assert thermal_z > 12.63, f"device_thermal eye.z={thermal_z} deve oltrepassare il muro lavanderia (Z=12.63)"
    # Verifica che device_dishwasher abbia l'angolazione diagonale stile cucina (X > 10, Z < 5.5)
    m_dish = re.search(r"device_dishwasher:\s*\{[^}]*eye:\s*new THREE\.Vector3\(([^)]+)\)", cam_src)
    assert m_dish is not None
    dx, dy, dz = [float(v.strip()) for v in m_dish.group(1).split(",")]
    assert dx > 10.0 and dz < 5.5, f"device_dishwasher eye=({dx},{dy},{dz}) non corrisponde all'angolazione diagonale cucina"


def test_f17_history_3d_rest_without_ws_centered_slice_and_sqlite_density(tmp_path: Path):
    from spatial_server.domain.models import SpatialPoint3D, TrackedEntity3D
    from spatial_server.persistence.repository import SQLiteWALTrackRepository

    # 1. Backend SQL GROUP BY density histogram (incluso bordo t_end)
    repo = SQLiteWALTrackRepository(tmp_path / "hist_density.db")
    base_ts = 1795090000.0
    ents = [
        TrackedEntity3D(
            track_id=1,
            class_label="car",
            confidence=0.92,
            state=SpatialPoint3D(x=-12.0, y=0.0, z=4.0, camera_sources=["Cam_Carraio"]),
            last_seen=base_ts + 10.0,
        ),
        TrackedEntity3D(
            track_id=2,
            class_label="car",
            confidence=0.94,
            state=SpatialPoint3D(x=-11.5, y=0.0, z=5.0, camera_sources=["Cam_Carraio"]),
            last_seen=base_ts + 1800.0,
        ),
        TrackedEntity3D(
            track_id=2,
            class_label="car",
            confidence=0.95,
            state=SpatialPoint3D(x=-11.2, y=0.0, z=5.2, camera_sources=["Cam_Carraio"]),
            last_seen=base_ts + 3600.0,  # esatto bordo t_end
        ),
    ]
    assert repo.append_batch(ents) == 3
    bins = repo.query_timeline_density(base_ts, base_ts + 3600.0, buckets=60)
    assert len(bins) == 60
    assert sum(b["count"] for b in bins) == 3
    assert bins[0]["count"] == 1
    assert bins[-1]["count"] == 1
    repo.close()

    # 2. Frontend: Cronologia interroga REST anche con WS offline, non cancella istogramma,
    #    usa slice centrata su finestre 24h (evitando troncamento LIMIT) e gestisce chip 'Ieri' senza NaN.
    code = """
      const { CameraCatalog } = await loadModule('/src/video/CameraCatalog.js');
      const { SecurityFabHub } = await loadModule('/src/ui/SecurityFabHub.js');

      const densityCalls = [];
      const trackCalls = [];
      let loadedDetections = [];
      let lastUpdateT = null;

      const spatialMock = {
        connected: false, // WS momentaneamente scollegato: REST cronologia DEVE funzionare lo stesso!
        onStatusChange: () => () => {},
        onFrame: () => () => {},
        fetchTimelineDensity: async (tStart, tEnd, buckets) => {
          densityCalls.push({ tStart, tEnd, buckets });
          return {
            status: 'ok',
            bins: Array.from({ length: buckets }, (_, i) => ({
              bucket: i,
              t_start: tStart + i * ((tEnd - tStart) / buckets),
              t_end: tStart + (i + 1) * ((tEnd - tStart) / buckets),
              count: i === 40 ? 25 : 0,
            })),
          };
        },
        fetchTracks: async (tStart, tEnd, classes, limit) => {
          trackCalls.push({ tStart, tEnd, limit });
          return {
            status: 'ok',
            count: 2,
            t_min: tStart + 100,
            t_max: tStart + 110,
            detections: [
              { track_id: 7, class_label: 'car', confidence: 0.94, x: -12.1, y: 0, z: 4.5, vx: 0.2, vz: 0.1, timestamp: (tStart + tEnd) / 2, camera_sources: ['Cam_Carraio'] },
              { track_id: 7, class_label: 'car', confidence: 0.94, x: -11.9, y: 0, z: 4.6, vx: 0.2, vz: 0.1, timestamp: (tStart + tEnd) / 2 + 10, camera_sources: ['Cam_Carraio'] },
            ],
          };
        },
      };

      const trajMock = {
        setLiveMode: () => {},
        setEntitiesVisible: () => {},
        loadDetections: (arr) => { loadedDetections = arr; },
        clearHistorical: () => { loadedDetections = []; },
        updateAtTime: (t) => { lastUpdateT = t; return loadedDetections.length > 0 ? 1 : 0; },
        interpolateLive: () => {},
      };

      const root = ctx.document.createElement('div');
      ctx.document.body.appendChild(root);

      const hub = new SecurityFabHub(root, {
        cameraCatalog: new CameraCatalog(),
        videoStreamManager: { attachToVideoElement: async () => ({ getStatus: () => ({}), onStatusChange: () => () => {} }), detachFromVideoElement: () => {} },
        recordingManager: { registerSlot: () => {}, setPlaybackRate: () => {}, setPlaying: () => {}, seekAllToTimestamp: async () => {}, queryAllSegments: async () => new Map(), detachAll: () => {}, getStorageSummary: async () => ({ configured: false }) },
        trajectoryRenderer: trajMock,
        spatialStreamClient: spatialMock,
        cameraController: { flyToPreset: () => {}, flyToCameraPOV: () => {} },
        assetLoader: { cameras: new Map() },
        deviceModals: { open: () => {} },
      });

      // Passa a Cronologia e seleziona finestra 24h centrata su un orario passato (16:23)
      await hub.setMode('replay');
      hub.windowSpanSec = 86400;
      const target1623 = Math.floor(Date.now() / 1000) - 20000;
      await hub.jumpToUnixTimestamp(target1623, { switchToReplay: true, reloadWindow: true });

      const lastDensity = densityCalls[densityCalls.length - 1];
      const lastTrack = trackCalls[trackCalls.length - 1];
      const densityCount = hub.densityBins.reduce((s, b) => s + (b.count || 0), 0);
      const loadedCount = loadedDetections.length;

      // Verifica click sul chip 'Ieri' con input time formato HH:MM (senza secondi -> mai NaN!)
      root.querySelector('#sec-time-input').value = '16:23';
      root.querySelector('[data-day-offset="1"]').click();
      for (let i = 0; i < 6; i++) await Promise.resolve();
      const yesterdayUnixValid = Number.isFinite(hub.currentUnix) && hub.currentUnix > 1700000000;

      hub.dispose();
      return {
        densitySpan: Math.round(lastDensity.tEnd - lastDensity.tStart),
        trackSliceSpan: Math.round(lastTrack.tEnd - lastTrack.tStart),
        trackSliceCoversTarget: lastTrack.tStart <= target1623 && lastTrack.tEnd >= target1623,
        densityCount,
        loadedCount,
        lastUpdateTValid: Number.isFinite(lastUpdateT),
        yesterdayUnixValid,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["densitySpan"] == 86400
    assert d["trackSliceSpan"] <= 1805
    assert d["trackSliceCoversTarget"] is True
    assert d["densityCount"] == 25
    assert d["loadedCount"] == 2
    assert d["lastUpdateTValid"] is True
    assert d["yesterdayUnixValid"] is True


def test_f17_topbar_no_longer_renders_side_quicknav():
    code = """
      const { TopBar } = await loadModule('/src/ui/TopBar.js');
      const topBarEl = ctx.document.getElementById('top-bar');
      new TopBar(topBarEl, {
        sceneManager: { isNightMode: false, setNightMode() {} },
        cameraController: { flyToPreset() {}, flyToCameraPOV() {} },
        cameraProjector: { toggleFrustums: () => false },
        interactionManager: { toggleBadges: () => false },
        haClient: {
          isAdmin: false,
          isMockMode: true,
          onStatusChange: () => () => {},
          onAuthChange: () => () => {},
        },
      });
      return {
        hasLegacyQuicknav: Boolean(ctx.document.querySelector('.side-quicknav')),
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    assert res["data"]["hasLegacyQuicknav"] is False


def test_f17_icons_registry_covers_all_new_m3_ui_icons():
    repo_root = Path(__file__).resolve().parents[2]
    new_ui_files = [
        repo_root / "src" / "ui" / "NavigationFabHub.js",
        repo_root / "src" / "ui" / "SecurityFabHub.js",
        repo_root / "src" / "devices" / "thermal" / "ThermalModal.js",
    ]
    discovered: set[str] = set()
    icon_call_re = re.compile(r"""\bicon\(\s*['"]([a-z0-9-]+)['"]""")
    for path in new_ui_files:
        content = path.read_text(encoding="utf-8")
        discovered.update(icon_call_re.findall(content))

    assert len(discovered) >= 10
    res = run_js_scenario({
        "action": "f11_rbac_ui",
        "target": "icons",
        "names": sorted(discovered),
    })
    assert res["ok"] is True, res
    results = res["data"]["results"]
    for name in sorted(discovered):
        svg = results.get(name, "")
        assert svg.startswith("<svg") and "</svg>" in svg, f"Icona mancante '{name}'"


def test_f17_portico_multicam_manifest_modal_and_ha_resolution():
    import json

    repo_root = Path(__file__).resolve().parents[2]
    manifest = json.loads((repo_root / "public" / "models" / "scene_manifest.json").read_text(encoding="utf-8"))
    manifest_subset = {
        "cameras": {
            k: v
            for k, v in manifest.get("cameras", {}).items()
            if v.get("is_real_security_camera")
        },
        "ha_entities": {
            k: v
            for k, v in manifest.get("ha_entities", {}).items()
            if k in ("camera.carraio_scorrevole", "camera.portico")
        },
    }
    manifest_json = json.dumps(manifest_subset)

    code = f"""
      const manifest = {manifest_json};
      const {{ CameraCatalog }} = await loadModule('/src/video/CameraCatalog.js');
      const {{ HAClient }} = await loadModule('/src/ha/HAClient.js');
      const {{ DeviceModals }} = await loadModule('/src/ha/DeviceModals.js');
      const {{ deviceRegistry }} = await loadModule('/src/devices/DeviceRegistry.js');
      const {{ SecurityFabHub }} = await loadModule('/src/ui/SecurityFabHub.js');

      const catalog = new CameraCatalog();
      catalog.syncFromManifest(manifest);

      const ha = new HAClient();
      ha.initMockMode();

      const attachedStreams = [];
      const mockVideoMgr = {{
        attachToVideoElement: async (streamName, _videoEl, _haClient, _entityId, extra) => {{
          attachedStreams.push({{ streamName, extra }});
          return {{
            mode: 'webrtc',
            getStatus: () => ({{ mode: 'webrtc', connected: true, latencyMs: 35 }}),
            onStatusChange: () => () => {{}},
          }};
        }},
        detachFromVideoElement: () => {{}},
      }};

      const secCtrl = deviceRegistry.get('security_camera');
      secCtrl.setServices({{
        haClient: ha,
        videoStreamManager: mockVideoMgr,
        cameraCatalog: catalog,
        assetLoader: {{ cameras: new Map(), manifest }},
      }});
      secCtrl.syncFromManifest(manifest);

      const drawer = ctx.document.createElement('div');
      ctx.document.body.appendChild(drawer);
      const modals = new DeviceModals(
        drawer,
        ha,
        {{ flyToPreset: () => {{}}, flyToCameraPOV: () => {{}}, startFollowing: () => {{}} }},
        {{ cameras: new Map(), manifest }}
      );

      // 1. Apri modale Portico
      modals.open('camera.portico');
      for (let i = 0; i < 4; i++) await Promise.resolve();
      const porticoTitle = drawer.querySelector('#modal-title')?.textContent?.trim();
      const porticoSubtitle = drawer.querySelector('#modal-subtitle')?.textContent?.trim();
      const porticoMainBtn = drawer.querySelector('[data-stream="portico_main"]')?.textContent?.trim();
      const porticoSubBtn = drawer.querySelector('[data-stream="portico_sub"]')?.textContent?.trim();
      const porticoHtml = drawer.innerHTML;
      modals.close();

      // 2. Apri modale Carraio (regressione zero)
      modals.open('camera.carraio_scorrevole');
      for (let i = 0; i < 4; i++) await Promise.resolve();
      const carraioTitle = drawer.querySelector('#modal-title')?.textContent?.trim();
      const carraioSubtitle = drawer.querySelector('#modal-subtitle')?.textContent?.trim();
      const carraioHtml = drawer.innerHTML;
      modals.close();

      // 3. Verifica risoluzione entity HA multi-camera senza cross-fallback verso Carraio
      const resolvedPorticoExact = ha.resolveCameraEntityId('camera.portico');
      delete ha.entities['camera.portico'];
      delete ha.mockEntities['camera.portico'];
      ha.entities['camera.portico_scorrevole'] = {{ entity_id: 'camera.portico_scorrevole', state: 'streaming', attributes: {{}} }};
      const resolvedPorticoVariant = ha.resolveCameraEntityId('camera.portico');
      delete ha.entities['camera.portico_scorrevole'];
      const resolvedPorticoMissing = ha.resolveCameraEntityId('camera.portico');

      // 4. Verifica SecurityFabHub mostra entrambe le telecamere dal manifest reale
      const hubRoot = ctx.document.createElement('div');
      ctx.document.body.appendChild(hubRoot);
      const hubAttached = [];
      const hub = new SecurityFabHub(hubRoot, {{
        cameraCatalog: catalog,
        videoStreamManager: {{
          attachToVideoElement: async (streamName) => {{
            hubAttached.push(streamName);
            return {{ mode: 'webrtc', getStatus: () => ({{ mode: 'webrtc', connected: true }}), onStatusChange: () => () => {{}} }};
          }},
          detachFromVideoElement: () => {{}},
        }},
        recordingManager: {{
          registerSlot: () => {{}},
          setPlaybackRate: () => {{}},
          setPlaying: () => {{}},
          seekAllToTimestamp: async () => {{}},
          queryAllSegments: async () => new Map(),
          detachAll: () => {{}},
          getStorageSummary: async () => ({{ configured: false }}),
        }},
        trajectoryRenderer: {{
          setLiveMode: () => {{}},
          setEntitiesVisible: () => {{}},
          loadDetections: () => {{}},
          clearHistorical: () => {{}},
          updateAtTime: () => {{}},
          interpolateLive: () => {{}},
        }},
        spatialStreamClient: {{ connected: false, onStatusChange: () => () => {{}}, onFrame: () => () => {{}} }},
        cameraController: {{ flyToPreset: () => {{}}, flyToCameraPOV: () => {{}} }},
        assetLoader: {{ cameras: new Map(), manifest }},
        deviceModals: {{ open: () => {{}} }},
      }});
      hubRoot.querySelector('#btn-security-fab').click();
      for (let i = 0; i < 6; i++) await Promise.resolve();
      const hubCamIds = hubRoot.querySelectorAll('.m3-cam-tile').map((t) => t.dataset.cameraId);
      hub.dispose();

      return {{
        catalogIds: catalog.getCameras().map((c) => c.id),
        porticoEntry: catalog.cameras.get('Cam_Portico'),
        porticoTitle,
        porticoSubtitle,
        porticoMainBtn,
        porticoSubBtn,
        porticoHasControls: porticoHtml.includes('cam-ha-controls') && porticoHtml.includes('Faretto LED') && porticoHtml.includes('Attiva Sirena'),
        porticoNoLegacyDetails: !porticoHtml.includes('btn-camera-pov') && !porticoHtml.includes('Modello & Ottica'),
        carraioTitle,
        carraioSubtitle,
        carraioHasControls: carraioHtml.includes('cam-ha-controls') && carraioHtml.includes('Faretto LED'),
        attachedStreamNames: attachedStreams.map((s) => s.streamName),
        resolvedPorticoExact,
        resolvedPorticoVariant,
        resolvedPorticoMissing,
        hubCamIds,
        hubAttached,
      }};
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert set(d["catalogIds"]) == {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso", "Cam_Stradina"}
    assert d["porticoEntry"]["entityId"] == "camera.portico"
    assert d["porticoEntry"]["mainStream"] == "portico_main"
    assert d["porticoEntry"]["subStream"] == "portico_sub"
    assert d["porticoEntry"]["cameraIp"] == "192.168.86.51"
    assert d["porticoEntry"]["fovH"] == 87
    assert d["porticoEntry"]["fovV"] == 44
    assert "Portico" in d["porticoTitle"]
    assert "." not in d["porticoSubtitle"]
    assert d["porticoMainBtn"] == "Main 4K"
    assert d["porticoSubBtn"] == "Sub 640×360"
    assert d["porticoHasControls"] is True
    assert d["porticoNoLegacyDetails"] is True
    assert "." not in d["carraioSubtitle"]
    assert d["carraioHasControls"] is True
    assert d["attachedStreamNames"] == ["portico_main", "carraio_main"]
    assert d["resolvedPorticoExact"] == "camera.portico"
    assert d["resolvedPorticoVariant"] == "camera.portico_scorrevole"
    assert d["resolvedPorticoMissing"] == "camera.portico"
    assert set(d["hubCamIds"]) == {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso", "Cam_Stradina"}
    assert set(d["hubAttached"]) == {"carraio_sub", "portico_sub", "ingresso_sub", "stradina_sub"}


def test_f17_pov_video_overlay_live_replay_exit_and_multicam_calibration():
    import json

    repo_root = Path(__file__).resolve().parents[2]
    manifest = json.loads((repo_root / "public" / "models" / "scene_manifest.json").read_text(encoding="utf-8"))
    manifest_subset = {
        "cameras": {
            k: v
            for k, v in manifest.get("cameras", {}).items()
            if v.get("is_real_security_camera")
        }
    }
    manifest_json = json.dumps(manifest_subset)

    code = f"""
      const manifest = {manifest_json};
      const {{ CameraCatalog }} = await loadModule('/src/video/CameraCatalog.js');
      const {{ CameraPovOverlayController }} = await loadModule('/src/spatial/CameraPovOverlayController.js');
      const {{ CalibrationAssistantUI }} = await loadModule('/src/spatial/calibration/CalibrationAssistantUI.js');
      const {{ SecurityFabHub }} = await loadModule('/src/ui/SecurityFabHub.js');
      const {{ TopBar }} = await loadModule('/src/ui/TopBar.js');
      const {{ RecordingPlaybackStatus }} = await loadModule('/src/video/recordings/index.js');

      const catalog = new CameraCatalog();
      catalog.syncFromManifest(manifest);

      // Mock CameraController che implementa la macchina a stati POV reale
      const povListeners = new Set();
      let povExitLocked = false;
      const camCtrl = {{
        activePovCameraName: null,
        onPovChange(fn) {{
          povListeners.add(fn);
          return () => povListeners.delete(fn);
        }},
        setPovExitLocked(v) {{ povExitLocked = Boolean(v); }},
        flyToPreset() {{ this.exitCameraPOV({{ reason: 'preset' }}); }},
        setInstantCameraPose(_p, _q, _f, camName) {{
          if (camName) this.activePovCameraName = camName;
        }},
        flyToCameraPOV(camNode, _dur, onComplete, opts = {{}}) {{
          const camName = camNode?.name || opts.cameraName || null;
          const prev = this.activePovCameraName;
          if (prev && prev !== camName) {{
            this.exitCameraPOV({{ reason: 'switch_pov' }});
          }}
          this.activePovCameraName = camName;
          povListeners.forEach((fn) => fn({{ cameraName: camName, phase: 'entering', previousCameraName: prev !== camName ? prev : null, forCalibration: Boolean(opts.forCalibration) }}));
          povListeners.forEach((fn) => fn({{ cameraName: camName, phase: 'active', previousCameraName: null, forCalibration: Boolean(opts.forCalibration) }}));
          if (onComplete) onComplete();
        }},
        exitCameraPOV({{ reason = 'manual' }} = {{}}) {{
          if (!this.activePovCameraName) return false;
          const prev = this.activePovCameraName;
          this.activePovCameraName = null;
          povListeners.forEach((fn) => fn({{ cameraName: null, phase: 'exited', previousCameraName: prev, reason }}));
          return true;
        }},
      }};

      const projectorState = new Map();
      const projectorMock = {{
        frustumHelpers: new Map([['Cam_Carraio', {{}}], ['Cam_Portico', {{}}], ['Cam_Ingresso', {{}}], ['Cam_Stradina', {{}}]]),
        attachOverlayTexture(cam, tex) {{
          const s = projectorState.get(cam) || {{}};
          s.texture = tex;
          projectorState.set(cam, s);
        }},
        detachOverlayTexture(cam) {{
          const s = projectorState.get(cam) || {{}};
          s.texture = null;
          projectorState.set(cam, s);
        }},
        setOverlayPOVMode(cam, isPov, opacity) {{
          const s = projectorState.get(cam) || {{}};
          s.isPov = Boolean(isPov);
          s.opacity = opacity;
          projectorState.set(cam, s);
        }},
        setOverlayOpacity(cam, opacity) {{
          const s = projectorState.get(cam) || {{}};
          s.opacity = opacity;
          projectorState.set(cam, s);
        }},
        applyCameraCalibration(cam) {{
          return {{ position: {{ x: 0, y: 2, z: 0 }}, quaternion: {{ x: 0, y: 0, z: 0, w: 1 }}, matrixWorldElements: new Array(16).fill(0) }};
        }},
        getCalibratedCameraPose() {{ return null; }},
      }};

      const acquiredLive = [];
      const releasedLive = [];
      const vsmMock = {{
        attachToVideoElement: async () => ({{ mode: 'webrtc', getStatus: () => ({{ mode: 'webrtc', connected: true }}), onStatusChange: () => () => {{}} }}),
        detachFromVideoElement: () => {{}},
        acquireVideoTexture: async (streamName, _mode, extra) => {{
          acquiredLive.push({{ streamName, extra }});
          return {{ streamName, texture: {{ isVideoTexture: true, streamName, dispose() {{}} }}, provider: {{ connected: true }} }};
        }},
        releaseVideoTexture: (streamName) => {{
          releasedLive.push(streamName);
        }},
      }};

      const registeredReplaySlots = new Map();
      const recMgrMock = {{
        registerSlot(slotKey, videoEl, onStateChange, opts = {{}}) {{
          registeredReplaySlots.set(slotKey, {{ slotKey, cameraId: opts.cameraId || slotKey, videoEl, onStateChange }});
        }},
        unregisterSlot(slotKey) {{
          registeredReplaySlots.delete(slotKey);
        }},
        async syncSlotToTimestamp(slotKey, ts) {{
          const slot = registeredReplaySlots.get(slotKey);
          slot?.onStateChange?.({{ status: RecordingPlaybackStatus.PLAYING, timestampUnix: ts }});
        }},
        async seekAllToTimestamp(ts) {{
          for (const slot of registeredReplaySlots.values()) {{
            slot.onStateChange?.({{ status: RecordingPlaybackStatus.NO_RECORDING, timestampUnix: ts }});
          }}
        }},
        setPlaybackRate() {{}},
        setPlaying() {{}},
        queryAllSegments: async () => new Map(),
        detachAll() {{}},
        getStorageSummary: async () => ({{ configured: true, providers: [] }}),
      }};

      const secRoot = ctx.document.createElement('div');
      ctx.document.body.appendChild(secRoot);
      const secHub = new SecurityFabHub(secRoot, {{
        cameraCatalog: catalog,
        videoStreamManager: vsmMock,
        recordingManager: recMgrMock,
        trajectoryRenderer: {{ setLiveMode() {{}}, setEntitiesVisible() {{}}, loadDetections() {{}}, clearHistorical() {{}}, updateAtTime() {{}}, interpolateLive() {{}} }},
        spatialStreamClient: {{ connected: false, onStatusChange: () => () => {{}}, onFrame: () => () => {{}} }},
        cameraController: camCtrl,
        assetLoader: {{ cameras: new Map([['Cam_Carraio', {{ name: 'Cam_Carraio' }}], ['Cam_Portico', {{ name: 'Cam_Portico' }}], ['Cam_Ingresso', {{ name: 'Cam_Ingresso' }}], ['Cam_Stradina', {{ name: 'Cam_Stradina' }}]]), manifest }},
        deviceModals: {{ open() {{}} }},
      }});

      const haAdmin = {{ isAdmin: true, isMockMode: false, authStatus: 'authenticated', currentUser: {{ name: 'Admin' }}, onStatusChange: () => () => {{}}, onAuthChange: () => () => {{}} }};
      const fakeCanvas = ctx.document.createElement('canvas');
      const sceneMgrMock = {{
        renderer: {{ domElement: fakeCanvas }},
        camera: {{ updateMatrixWorld() {{}} }},
        scene: {{ children: [] }},
        isNightMode: false,
        setNightMode() {{}},
        addUpdateCallback() {{}},
        removeUpdateCallback() {{}},
      }};

      const assetLoaderMock = {{
        manifest,
        cameras: new Map([['Cam_Carraio', {{ name: 'Cam_Carraio' }}], ['Cam_Portico', {{ name: 'Cam_Portico' }}], ['Cam_Ingresso', {{ name: 'Cam_Ingresso' }}], ['Cam_Stradina', {{ name: 'Cam_Stradina' }}]]),
      }};

      const calibUI = new CalibrationAssistantUI({{
        sceneManager: sceneMgrMock,
        cameraController: camCtrl,
        cameraProjector: projectorMock,
        videoStreamManager: vsmMock,
        spatialStreamClient: null,
        assetLoader: assetLoaderMock,
        haClient: haAdmin,
        cameraCatalog: catalog,
      }});

      const povOverlay = new CameraPovOverlayController({{
        cameraController: camCtrl,
        cameraProjector: projectorMock,
        videoStreamManager: vsmMock,
        recordingManager: recMgrMock,
        cameraCatalog: catalog,
        securityFabHub: secHub,
        calibrationAssistant: calibUI,
        haClient: haAdmin,
        assetLoader: assetLoaderMock,
        uiLayer: ctx.document.body,
      }});

      calibUI.setLifecycleHooks({{
        onOpen: () => povOverlay.suspendForCalibration(),
        onClose: () => povOverlay.resumeAfterCalibration(),
      }});

      const topBarEl = ctx.document.getElementById('top-bar');
      new TopBar(topBarEl, {{
        sceneManager: sceneMgrMock,
        cameraController: camCtrl,
        cameraProjector: {{ toggleFrustums: () => false }},
        interactionManager: {{ toggleBadges: () => false }},
        haClient: haAdmin,
        calibrationAssistant: calibUI,
        assetLoader: assetLoaderMock,
        deviceModals: {{ close() {{}}, currentEntityId: null }},
        cameraCatalog: catalog,
      }});

      // 1. Entra in POV Portico in modalità LIVE -> overlay live trasparente attivo su Cam_Portico
      camCtrl.flyToCameraPOV({{ name: 'Cam_Portico' }}, 0);
      for (let i = 0; i < 6; i++) await Promise.resolve();
      const livePorticoState = {{ ...(projectorState.get('Cam_Portico') || {{}}) }};
      const liveHudVisible = Boolean(ctx.document.querySelector('#pov-overlay-hud')?.classList.contains('visible'));
      const liveHudBadge = ctx.document.querySelector('#pov-hud-mode-pill')?.textContent?.trim();

      // 2. Passa a modalità CRONOLOGIA (replay) mentre sei in POV -> hot-swap automatico a replay!
      secHub.openExpanded();
      await secHub.setMode('replay', {{ skipInitialLoad: true }});
      for (let i = 0; i < 6; i++) await Promise.resolve();
      const replayNoRecState = {{ ...(projectorState.get('Cam_Portico') || {{}}) }};
      const replayNoRecBadge = ctx.document.querySelector('#pov-hud-mode-pill')?.textContent?.trim();

      // Simula registrazione trovata per Cam_Portico -> overlay replay appare!
      const tileSlot = registeredReplaySlots.get('Cam_Portico');
      tileSlot?.onStateChange?.({{ status: RecordingPlaybackStatus.PLAYING, timestampUnix: 1795092000 }});
      for (let i = 0; i < 4; i++) await Promise.resolve();
      const replayPlayingState = {{ ...(projectorState.get('Cam_Portico') || {{}}) }};
      const replayPlayingBadge = ctx.document.querySelector('#pov-hud-mode-pill')?.textContent?.trim();

      // 3. Clicca 'Calibra Cam' in TopBar mentre sei in POV Portico -> DEVE aprire Calibrazione su Cam_Portico (NON Carraio!)
      topBarEl.querySelector('#btn-open-cam-calib').click();
      for (let i = 0; i < 8; i++) await Promise.resolve();
      const calibActiveAfterTopBar = calibUI.activeCameraName;
      const calibPills = Array.from(ctx.document.querySelectorAll('.calib-cam-pill')).map((b) => b.dataset.calibCam);
      const hudHiddenDuringCalib = !ctx.document.querySelector('#pov-overlay-hud')?.classList.contains('visible');

      // 4. Switch a Cam_Carraio tramite pill nella UI di calibrazione -> cambia a Cam_Carraio
      ctx.document.querySelector('.calib-cam-pill[data-calib-cam="Cam_Carraio"]').click();
      for (let i = 0; i < 8; i++) await Promise.resolve();
      const calibAfterSwitchToCarraio = calibUI.activeCameraName;

      // 5. Chiudi calibrazione, rientra in POV Carraio (live), poi ESCI da POV -> overlay sparisce del tutto!
      calibUI.close();
      await secHub.setMode('live');
      camCtrl.flyToCameraPOV({{ name: 'Cam_Carraio' }}, 0);
      for (let i = 0; i < 6; i++) await Promise.resolve();
      const carraioPovActive = Boolean(projectorState.get('Cam_Carraio')?.isPov);

      camCtrl.exitCameraPOV({{ reason: 'drag' }});
      for (let i = 0; i < 4; i++) await Promise.resolve();
      const carraioAfterExit = {{ ...(projectorState.get('Cam_Carraio') || {{}}) }};
      const hudHiddenAfterExit = !ctx.document.querySelector('#pov-overlay-hud')?.classList.contains('visible');

      povOverlay.dispose();
      secHub.dispose();

      return {{
        livePorticoIsPov: Boolean(livePorticoState.isPov),
        livePorticoOpacity: livePorticoState.opacity,
        livePorticoStream: livePorticoState.texture?.streamName,
        liveHudVisible,
        liveHudBadge,
        replayNoRecIsPov: Boolean(replayNoRecState.isPov),
        replayNoRecBadge,
        replayPlayingIsPov: Boolean(replayPlayingState.isPov),
        replayPlayingOpacity: replayPlayingState.opacity,
        replayPlayingBadge,
        calibActiveAfterTopBar,
        calibPills,
        hudHiddenDuringCalib,
        calibAfterSwitchToCarraio,
        carraioPovActive,
        carraioAfterExitIsPov: Boolean(carraioAfterExit.isPov),
        carraioAfterExitHasTex: Boolean(carraioAfterExit.texture),
        hudHiddenAfterExit,
        acquiredStreams: acquiredLive.map((a) => a.streamName),
        releasedLive,
      }};
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["livePorticoIsPov"] is True
    assert 0.3 <= d["livePorticoOpacity"] <= 0.65
    assert d["livePorticoStream"] == "portico_main"
    assert d["liveHudVisible"] is True
    assert d["liveHudBadge"] == "LIVE"
    assert d["replayNoRecIsPov"] is False
    assert d["replayNoRecBadge"] == "NO REGISTRAZIONE"
    assert d["replayPlayingIsPov"] is True
    assert 0.3 <= d["replayPlayingOpacity"] <= 0.65
    assert d["replayPlayingBadge"] == "REPLAY"
    assert d["calibActiveAfterTopBar"] == "Cam_Portico"
    assert set(d["calibPills"]) == {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso", "Cam_Stradina"}
    assert d["hudHiddenDuringCalib"] is True
    assert d["calibAfterSwitchToCarraio"] == "Cam_Carraio"
    assert d["carraioPovActive"] is True
    assert d["carraioAfterExitIsPov"] is False
    assert d["carraioAfterExitHasTex"] is False
    assert d["hudHiddenAfterExit"] is True
    assert "portico_main" in d["acquiredStreams"]
    assert "carraio_main" in d["acquiredStreams"]
    assert "portico_main" in d["releasedLive"]
    assert "carraio_main" in d["releasedLive"]


def test_f17_ingresso_180_panoramic_frustum_overlay_and_modal():
    import json

    repo_root = Path(__file__).resolve().parents[2]
    manifest = json.loads((repo_root / "public" / "models" / "scene_manifest.json").read_text(encoding="utf-8"))
    manifest_subset = {
        "cameras": {
            k: v
            for k, v in manifest.get("cameras", {}).items()
            if v.get("is_real_security_camera")
        },
        "ha_entities": {
            k: v
            for k, v in manifest.get("ha_entities", {}).items()
            if k in ("camera.carraio_scorrevole", "camera.portico", "camera.ingresso")
        },
    }
    manifest_json = json.dumps(manifest_subset)

    code = f"""
      const manifest = {manifest_json};
      const THREE = await loadModule('three');
      const {{ CameraCatalog }} = await loadModule('/src/video/CameraCatalog.js');
      const {{ HAClient }} = await loadModule('/src/ha/HAClient.js');
      const {{ DeviceModals }} = await loadModule('/src/ha/DeviceModals.js');
      const {{ deviceRegistry }} = await loadModule('/src/devices/DeviceRegistry.js');
      const {{ SecurityFabHub }} = await loadModule('/src/ui/SecurityFabHub.js');
      const {{ computeClippedFrustumData }} = await loadModule('/src/spatial/CameraProjector.js');
      const {{ CameraFrustumOverlay }} = await loadModule('/src/spatial/calibration/CameraFrustumOverlay.js');
      const {{ CalibrationAssistantUI }} = await loadModule('/src/spatial/calibration/CalibrationAssistantUI.js');

      const catalog = new CameraCatalog();
      catalog.syncFromManifest(manifest);
      const ingCam = catalog.getCameraById('Cam_Ingresso');

      // 1. Verifica frustum 180° sferico (zero NaN/Infinity da tan(90°) e impronta ground ad ovest)
      const ingManifest = manifest.cameras.Cam_Ingresso;
      const matRowMajor = ingManifest.gltf_transform.matrix_world_gl;
      const mat4 = new THREE.Matrix4().set(...matRowMajor);
      const pos = new THREE.Vector3();
      const quat = new THREE.Quaternion();
      const scale = new THREE.Vector3();
      mat4.decompose(pos, quat, scale);

      const frustum = computeClippedFrustumData(pos, quat, 55.0, 180.0, 16.0);
      const allConeFinite = Array.from(frustum.conePositions).every((v) => Number.isFinite(v));
      const allWireFinite = Array.from(frustum.wirePositions).every((v) => Number.isFinite(v));
      const allGroundFinite = Array.from(frustum.groundPositions).every((v) => Number.isFinite(v));
      const groundCentroidX = frustum.groundPolygonWorld.length > 0
        ? frustum.groundPolygonWorld.reduce((acc, p) => acc + p.x, 0) / frustum.groundPolygonWorld.length
        : 0;
      const groundMinX = frustum.groundPolygonWorld.length > 0
        ? Math.min(...frustum.groundPolygonWorld.map((p) => p.x))
        : 0;
      const groundWestCount = frustum.groundPolygonWorld.filter((p) => Number.isFinite(p.x) && p.x < 0.0).length;
      const allGroundWest = frustum.groundPolygonWorld.length >= 20 &&
        groundMinX < -10.0 &&
        groundCentroidX < -4.0 &&
        groundWestCount / frustum.groundPolygonWorld.length >= 0.8;

      // 2. Verifica cupola sferica equirettangolare CameraFrustumOverlay (raggio costante = depth, zero NaN)
      const overlay = new CameraFrustumOverlay('Cam_Ingresso', {{
        opticalModel: 'equirectangular_180',
        fovH: 180.0,
        fovV: 55.0,
        aspect: 32 / 9,
        depth: 2.0,
      }});
      const ovPos = overlay.geometry.attributes.position;
      let ovAllFinite = true;
      let ovMaxRadiusErr = 0;
      let ovMinX = Infinity;
      let ovMaxX = -Infinity;
      for (let i = 0; i < ovPos.count; i++) {{
        const x = ovPos.getX(i);
        const y = ovPos.getY(i);
        const z = ovPos.getZ(i);
        if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {{
          ovAllFinite = false;
          break;
        }}
        const r = Math.hypot(x, y, z);
        ovMaxRadiusErr = Math.max(ovMaxRadiusErr, Math.abs(r - 2.0));
        ovMinX = Math.min(ovMinX, x);
        ovMaxX = Math.max(ovMaxX, x);
      }}

      // 3. Modale DeviceModals('camera.ingresso') e risoluzione entity HA
      const ha = new HAClient();
      ha.initMockMode();
      const attachedStreams = [];
      const mockVideoMgr = {{
        attachToVideoElement: async (streamName) => {{
          attachedStreams.push(streamName);
          return {{ mode: 'webrtc', getStatus: () => ({{ mode: 'webrtc', connected: true }}), onStatusChange: () => () => {{}} }};
        }},
        detachFromVideoElement: () => {{}},
        acquireVideoTexture: async (streamName) => ({{ streamName, texture: {{ isVideoTexture: true, dispose() {{}} }} }}),
        releaseVideoTexture: () => {{}},
      }};

      const secCtrl = deviceRegistry.get('security_camera');
      secCtrl.setServices({{
        haClient: ha,
        videoStreamManager: mockVideoMgr,
        cameraCatalog: catalog,
        assetLoader: {{ cameras: new Map([['Cam_Ingresso', {{ name: 'Cam_Ingresso' }}]]), manifest }},
      }});
      secCtrl.syncFromManifest(manifest);

      const drawer = ctx.document.createElement('div');
      ctx.document.body.appendChild(drawer);
      const modals = new DeviceModals(
        drawer,
        ha,
        {{ flyToPreset: () => {{}}, flyToCameraPOV: () => {{}}, startFollowing: () => {{}} }},
        {{ cameras: new Map([['Cam_Ingresso', {{ name: 'Cam_Ingresso' }}]]), manifest }}
      );
      modals.open('camera.ingresso');
      for (let i = 0; i < 4; i++) await Promise.resolve();
      const ingTitle = drawer.querySelector('#modal-title')?.textContent?.trim();
      const ingSubtitle = drawer.querySelector('#modal-subtitle')?.textContent?.trim();
      const ingMainBtn = drawer.querySelector('[data-stream="ingresso_main"]')?.textContent?.trim();
      const ingSubBtn = drawer.querySelector('[data-stream="ingresso_sub"]')?.textContent?.trim();
      const ingHtml = drawer.innerHTML;
      modals.close();

      // 4. SecurityFabHub marca il riquadro Cam_Ingresso come is-panoramic (32:9)
      const hubRoot = ctx.document.createElement('div');
      ctx.document.body.appendChild(hubRoot);
      const hub = new SecurityFabHub(hubRoot, {{
        cameraCatalog: catalog,
        videoStreamManager: mockVideoMgr,
        recordingManager: {{
          registerSlot: () => {{}},
          setPlaybackRate: () => {{}},
          setPlaying: () => {{}},
          seekAllToTimestamp: async () => {{}},
          queryAllSegments: async () => new Map(),
          detachAll: () => {{}},
          getStorageSummary: async () => ({{ configured: false }}),
        }},
        trajectoryRenderer: {{ setLiveMode() {{}}, setEntitiesVisible() {{}}, loadDetections() {{}}, clearHistorical() {{}}, updateAtTime() {{}}, interpolateLive() {{}} }},
        spatialStreamClient: {{ connected: false, onStatusChange: () => () => {{}}, onFrame: () => () => {{}} }},
        cameraController: {{ flyToPreset: () => {{}}, flyToCameraPOV: () => {{}} }},
        assetLoader: {{ cameras: new Map(), manifest }},
        deviceModals: {{ open: () => {{}} }},
      }});
      hubRoot.querySelector('#btn-security-fab').click();
      for (let i = 0; i < 6; i++) await Promise.resolve();
      const ingTile = hubRoot.querySelector('.m3-cam-tile[data-camera-id="Cam_Ingresso"]');
      const ingTileIsPanoramic = Boolean(ingTile?.classList.contains('is-panoramic'));
      hub.dispose();

      // 5. CalibrationAssistantUI su Cam_Ingresso disabilita PnP pinhole ma mantiene i 3 switcher
      const haAdmin = {{ isAdmin: true, isMockMode: false, authStatus: 'authenticated', currentUser: {{ name: 'Admin' }}, onStatusChange: () => () => {{}}, onAuthChange: () => () => {{}} }};
      const fakeCanvas = ctx.document.createElement('canvas');
      const calibUI = new CalibrationAssistantUI({{
        sceneManager: {{ renderer: {{ domElement: fakeCanvas }}, camera: {{ updateMatrixWorld() {{}} }}, scene: {{ children: [] }}, addUpdateCallback() {{}}, removeUpdateCallback() {{}} }},
        cameraController: {{ activePovCameraName: null, flyToCameraPOV(_c, _d, cb) {{ if (cb) cb(); }}, exitCameraPOV() {{}}, setPovExitLocked() {{}}, setInstantCameraPose() {{}} }},
        cameraProjector: {{
          frustumHelpers: new Map([['Cam_Carraio', {{}}], ['Cam_Portico', {{}}], ['Cam_Ingresso', {{}}], ['Cam_Stradina', {{}}]]),
          attachOverlayTexture() {{}},
          detachOverlayTexture() {{}},
          setOverlayPOVMode() {{}},
          setOverlayOpacity() {{}},
          applyCameraCalibration() {{ return {{ position: pos, quaternion: quat, matrixWorldElements: matRowMajor }}; }},
          getCalibratedCameraPose() {{ return null; }},
        }},
        videoStreamManager: mockVideoMgr,
        spatialStreamClient: null,
        assetLoader: {{ manifest, cameras: new Map([['Cam_Carraio', {{ name: 'Cam_Carraio' }}], ['Cam_Portico', {{ name: 'Cam_Portico' }}], ['Cam_Ingresso', {{ name: 'Cam_Ingresso' }}], ['Cam_Stradina', {{ name: 'Cam_Stradina' }}]]) }},
        haClient: haAdmin,
        cameraCatalog: catalog,
      }});
      await calibUI.open('Cam_Ingresso');
      const pnpDisabledForPano = Boolean(ctx.document.querySelector('#calib-pnp-toggle')?.disabled);
      const calibPills = Array.from(ctx.document.querySelectorAll('.calib-cam-pill')).map((b) => b.dataset.calibCam);
      calibUI.close();

      return {{
        ingIsPanoramic: ingCam?.isPanoramic180,
        ingFovH: ingCam?.fovH,
        ingFovV: ingCam?.fovV,
        ingAspect: ingCam?.aspectRatio,
        ingIp: ingCam?.cameraIp,
        ingEntity: ingCam?.entityId,
        ingMainStream: ingCam?.mainStream,
        ingSubStream: ingCam?.subStream,
        coneLen: frustum.conePositions.length,
        groundLen: frustum.groundPositions.length,
        allConeFinite,
        allWireFinite,
        allGroundFinite,
        allGroundWest,
        ovAllFinite,
        ovMaxRadiusErr,
        ovSpanX: ovMaxX - ovMinX,
        ingTitle,
        ingSubtitle,
        ingMainBtn,
        ingSubBtn,
        ingHasControls: ingHtml.includes('cam-ha-controls') && ingHtml.includes('Faretto LED') && ingHtml.includes('Attiva Sirena'),
        ingNoLegacyDetails: !ingHtml.includes('btn-camera-pov') && !ingHtml.includes('Modello & Ottica'),
        attachedStreams,
        ingTileIsPanoramic,
        pnpDisabledForPano,
        calibPills,
        resolvedIngresso: ha.resolveCameraEntityId('camera.ingresso'),
      }};
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["ingIsPanoramic"] is True
    assert d["ingFovH"] == 180
    assert d["ingFovV"] == 55
    assert abs(d["ingAspect"] - (32.0 / 9.0)) < 0.01
    assert d["ingIp"] == "192.168.86.53"
    assert d["ingEntity"] == "camera.ingresso"
    assert d["ingMainStream"] == "ingresso_main"
    assert d["ingSubStream"] == "ingresso_sub"
    assert d["coneLen"] > 100 and d["groundLen"] > 100
    assert d["allConeFinite"] is True
    assert d["allWireFinite"] is True
    assert d["allGroundFinite"] is True
    assert d["allGroundWest"] is True
    assert d["ovAllFinite"] is True
    assert d["ovMaxRadiusErr"] < 1e-4
    assert d["ovSpanX"] > 3.5  # cupola 180° raggio 2m -> larghezza ~3.55m..4.0m
    assert "Ingresso" in d["ingTitle"]
    assert "." not in d["ingSubtitle"]
    assert d["ingMainBtn"] == "Main 16MP 180°"
    assert d["ingSubBtn"] == "Sub 1536×576"
    assert d["ingHasControls"] is True
    assert d["ingNoLegacyDetails"] is True
    assert d["attachedStreams"][0] == "ingresso_main"
    assert set(d["attachedStreams"][1:]) == {"carraio_sub", "portico_sub", "ingresso_sub", "stradina_sub"}
    assert d["ingTileIsPanoramic"] is True
    assert d["pnpDisabledForPano"] is True
    assert set(d["calibPills"]) == {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso", "Cam_Stradina"}
    assert d["resolvedIngresso"] == "camera.ingresso"


def test_f17_stradina_180_panoramic_frustum_overlay_and_4cam_ui():
    import json

    repo_root = Path(__file__).resolve().parents[2]
    manifest = json.loads((repo_root / "public" / "models" / "scene_manifest.json").read_text(encoding="utf-8"))
    manifest_subset = {
        "cameras": {
            k: v
            for k, v in manifest.get("cameras", {}).items()
            if v.get("is_real_security_camera")
        },
        "ha_entities": {
            k: v
            for k, v in manifest.get("ha_entities", {}).items()
            if k in ("camera.carraio_scorrevole", "camera.portico", "camera.ingresso", "camera.stradina")
        },
    }
    manifest_json = json.dumps(manifest_subset)

    code = f"""
      const manifest = {manifest_json};
      const THREE = await loadModule('three');
      const {{ CameraCatalog }} = await loadModule('/src/video/CameraCatalog.js');
      const {{ HAClient }} = await loadModule('/src/ha/HAClient.js');
      const {{ DeviceModals }} = await loadModule('/src/ha/DeviceModals.js');
      const {{ deviceRegistry }} = await loadModule('/src/devices/DeviceRegistry.js');
      const {{ SecurityFabHub }} = await loadModule('/src/ui/SecurityFabHub.js');
      const {{ computeClippedFrustumData }} = await loadModule('/src/spatial/CameraProjector.js');
      const {{ CameraFrustumOverlay }} = await loadModule('/src/spatial/calibration/CameraFrustumOverlay.js');
      const {{ CalibrationAssistantUI }} = await loadModule('/src/spatial/calibration/CalibrationAssistantUI.js');

      const catalog = new CameraCatalog();
      catalog.syncFromManifest(manifest);
      const strCam = catalog.getCameraById('Cam_Stradina');

      // 1. Verifica frustum 180° sferico verso Nord (-Z glTF) ruotato 10° Ovest e inclinato 30° giù
      const strManifest = manifest.cameras.Cam_Stradina;
      const matRowMajor = strManifest.gltf_transform.matrix_world_gl;
      const mat4 = new THREE.Matrix4().set(...matRowMajor);
      const pos = new THREE.Vector3();
      const quat = new THREE.Quaternion();
      const scale = new THREE.Vector3();
      mat4.decompose(pos, quat, scale);

      const frustum = computeClippedFrustumData(pos, quat, 55.0, 180.0, 16.0);
      const allConeFinite = Array.from(frustum.conePositions).every((v) => Number.isFinite(v));
      const allWireFinite = Array.from(frustum.wirePositions).every((v) => Number.isFinite(v));
      const allGroundFinite = Array.from(frustum.groundPositions).every((v) => Number.isFinite(v));
      const groundCentroidZ = frustum.groundPolygonWorld.length > 0
        ? frustum.groundPolygonWorld.reduce((acc, p) => acc + p.z, 0) / frustum.groundPolygonWorld.length
        : 0;
      const groundMinZ = frustum.groundPolygonWorld.length > 0
        ? Math.min(...frustum.groundPolygonWorld.map((p) => p.z))
        : 0;
      const groundNorthCount = frustum.groundPolygonWorld.filter((p) => Number.isFinite(p.z) && p.z < 0.0).length;
      const groundNorthOk = frustum.groundPolygonWorld.length >= 20 &&
        groundMinZ < -10.0 &&
        groundCentroidZ < -3.5 &&
        groundNorthCount / frustum.groundPolygonWorld.length >= 0.8;

      // 2. Verifica cupola sferica equirettangolare CameraFrustumOverlay
      const overlay = new CameraFrustumOverlay('Cam_Stradina', {{
        opticalModel: 'equirectangular_180',
        fovH: 180.0,
        fovV: 55.0,
        aspect: 32 / 9,
        depth: 2.0,
      }});
      const ovPos = overlay.geometry.attributes.position;
      let ovAllFinite = true;
      let ovMaxRadiusErr = 0;
      for (let i = 0; i < ovPos.count; i++) {{
        const x = ovPos.getX(i), y = ovPos.getY(i), z = ovPos.getZ(i);
        if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {{
          ovAllFinite = false;
          break;
        }}
        ovMaxRadiusErr = Math.max(ovMaxRadiusErr, Math.abs(Math.hypot(x, y, z) - 2.0));
      }}

      // 3. Modale DeviceModals('camera.stradina') e risoluzione entity HA
      const ha = new HAClient();
      ha.initMockMode();
      const attachedStreams = [];
      const mockVideoMgr = {{
        attachToVideoElement: async (streamName) => {{
          attachedStreams.push(streamName);
          return {{ mode: 'webrtc', getStatus: () => ({{ mode: 'webrtc', connected: true }}), onStatusChange: () => () => {{}} }};
        }},
        detachFromVideoElement: () => {{}},
        acquireVideoTexture: async (streamName) => ({{ streamName, texture: {{ isVideoTexture: true, dispose() {{}} }} }}),
        releaseVideoTexture: () => {{}},
      }};

      const secCtrl = deviceRegistry.get('security_camera');
      secCtrl.setServices({{
        haClient: ha,
        videoStreamManager: mockVideoMgr,
        cameraCatalog: catalog,
        assetLoader: {{ cameras: new Map([['Cam_Stradina', {{ name: 'Cam_Stradina' }}]]), manifest }},
      }});
      secCtrl.syncFromManifest(manifest);

      const drawer = ctx.document.createElement('div');
      ctx.document.body.appendChild(drawer);
      const modals = new DeviceModals(
        drawer,
        ha,
        {{ flyToPreset: () => {{}}, flyToCameraPOV: () => {{}}, startFollowing: () => {{}} }},
        {{ cameras: new Map([['Cam_Stradina', {{ name: 'Cam_Stradina' }}]]), manifest }}
      );
      modals.open('camera.stradina');
      for (let i = 0; i < 4; i++) await Promise.resolve();
      const strTitle = drawer.querySelector('#modal-title')?.textContent?.trim();
      const strSubtitle = drawer.querySelector('#modal-subtitle')?.textContent?.trim();
      const strMainBtn = drawer.querySelector('[data-stream="stradina_main"]')?.textContent?.trim();
      const strSubBtn = drawer.querySelector('[data-stream="stradina_sub"]')?.textContent?.trim();
      const strHtml = drawer.innerHTML;
      modals.close();

      // 4. SecurityFabHub mostra tutte le 4 camere e marca entrambe le Duo 3 PoE come is-panoramic
      const hubRoot = ctx.document.createElement('div');
      ctx.document.body.appendChild(hubRoot);
      const hub = new SecurityFabHub(hubRoot, {{
        cameraCatalog: catalog,
        videoStreamManager: mockVideoMgr,
        recordingManager: {{
          registerSlot: () => {{}},
          setPlaybackRate: () => {{}},
          setPlaying: () => {{}},
          seekAllToTimestamp: async () => {{}},
          queryAllSegments: async () => new Map(),
          detachAll: () => {{}},
          getStorageSummary: async () => ({{ configured: false }}),
        }},
        trajectoryRenderer: {{ setLiveMode() {{}}, setEntitiesVisible() {{}}, loadDetections() {{}}, clearHistorical() {{}}, updateAtTime() {{}}, interpolateLive() {{}} }},
        spatialStreamClient: {{ connected: false, onStatusChange: () => () => {{}}, onFrame: () => () => {{}} }},
        cameraController: {{ flyToPreset: () => {{}}, flyToCameraPOV: () => {{}} }},
        assetLoader: {{ cameras: new Map(), manifest }},
        deviceModals: {{ open: () => {{}} }},
      }});
      hubRoot.querySelector('#btn-security-fab').click();
      for (let i = 0; i < 6; i++) await Promise.resolve();
      const panoTileIds = hubRoot.querySelectorAll('.m3-cam-tile.is-panoramic').map((t) => t.dataset.cameraId);
      const allTileIds = hubRoot.querySelectorAll('.m3-cam-tile').map((t) => t.dataset.cameraId);
      hub.dispose();

      // 5. CalibrationAssistantUI su Cam_Stradina disabilita PnP pinhole e mostra 4 switcher
      const haAdmin = {{ isAdmin: true, isMockMode: false, authStatus: 'authenticated', currentUser: {{ name: 'Admin' }}, onStatusChange: () => () => {{}}, onAuthChange: () => () => {{}} }};
      const fakeCanvas = ctx.document.createElement('canvas');
      const calibUI = new CalibrationAssistantUI({{
        sceneManager: {{ renderer: {{ domElement: fakeCanvas }}, camera: {{ updateMatrixWorld() {{}} }}, scene: {{ children: [] }}, addUpdateCallback() {{}}, removeUpdateCallback() {{}} }},
        cameraController: {{ activePovCameraName: null, flyToCameraPOV(_c, _d, cb) {{ if (cb) cb(); }}, exitCameraPOV() {{}}, setPovExitLocked() {{}}, setInstantCameraPose() {{}} }},
        cameraProjector: {{
          frustumHelpers: new Map([['Cam_Carraio', {{}}], ['Cam_Portico', {{}}], ['Cam_Ingresso', {{}}], ['Cam_Stradina', {{}}]]),
          attachOverlayTexture() {{}},
          detachOverlayTexture() {{}},
          setOverlayPOVMode() {{}},
          setOverlayOpacity() {{}},
          applyCameraCalibration() {{ return {{ position: pos, quaternion: quat, matrixWorldElements: matRowMajor }}; }},
          getCalibratedCameraPose() {{ return null; }},
        }},
        videoStreamManager: mockVideoMgr,
        spatialStreamClient: null,
        assetLoader: {{ manifest, cameras: new Map([['Cam_Carraio', {{ name: 'Cam_Carraio' }}], ['Cam_Portico', {{ name: 'Cam_Portico' }}], ['Cam_Ingresso', {{ name: 'Cam_Ingresso' }}], ['Cam_Stradina', {{ name: 'Cam_Stradina' }}]]) }},
        haClient: haAdmin,
        cameraCatalog: catalog,
      }});
      await calibUI.open('Cam_Stradina');
      const pnpDisabledForPano = Boolean(ctx.document.querySelector('#calib-pnp-toggle')?.disabled);
      const calibPills = Array.from(ctx.document.querySelectorAll('.calib-cam-pill')).map((b) => b.dataset.calibCam);
      calibUI.close();

      return {{
        strIsPanoramic: strCam?.isPanoramic180,
        strFovH: strCam?.fovH,
        strFovV: strCam?.fovV,
        strAspect: strCam?.aspectRatio,
        strIp: strCam?.cameraIp,
        strEntity: strCam?.entityId,
        strMainStream: strCam?.mainStream,
        strSubStream: strCam?.subStream,
        coneLen: frustum.conePositions.length,
        groundLen: frustum.groundPositions.length,
        allConeFinite,
        allWireFinite,
        allGroundFinite,
        groundNorthOk,
        ovAllFinite,
        ovMaxRadiusErr,
        strTitle,
        strSubtitle,
        strMainBtn,
        strSubBtn,
        strHasControls: strHtml.includes('cam-ha-controls') && strHtml.includes('Faretto LED') && strHtml.includes('Attiva Sirena'),
        strNoLegacyDetails: !strHtml.includes('btn-camera-pov') && !strHtml.includes('Modello & Ottica'),
        attachedStreams,
        panoTileIds,
        allTileIds,
        pnpDisabledForPano,
        calibPills,
        resolvedStradina: ha.resolveCameraEntityId('camera.stradina'),
      }};
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["strIsPanoramic"] is True
    assert d["strFovH"] == 180
    assert d["strFovV"] == 55
    assert abs(d["strAspect"] - (32.0 / 9.0)) < 0.01
    assert d["strIp"] == "192.168.86.55"
    assert d["strEntity"] == "camera.stradina"
    assert d["strMainStream"] == "stradina_main"
    assert d["strSubStream"] == "stradina_sub"
    assert d["coneLen"] > 100 and d["groundLen"] > 100
    assert d["allConeFinite"] is True
    assert d["allWireFinite"] is True
    assert d["allGroundFinite"] is True
    assert d["groundNorthOk"] is True
    assert d["ovAllFinite"] is True
    assert d["ovMaxRadiusErr"] < 1e-4
    assert "Stradina" in d["strTitle"]
    assert "." not in d["strSubtitle"]
    assert d["strMainBtn"] == "Main 16MP 180°"
    assert d["strSubBtn"] == "Sub 1536×576"
    assert d["strHasControls"] is True
    assert d["strNoLegacyDetails"] is True
    assert d["attachedStreams"][0] == "stradina_main"
    assert set(d["attachedStreams"][1:]) == {"carraio_sub", "portico_sub", "ingresso_sub", "stradina_sub"}
    assert set(d["panoTileIds"]) == {"Cam_Ingresso", "Cam_Stradina"}
    assert set(d["allTileIds"]) == {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso", "Cam_Stradina"}
    assert d["pnpDisabledForPano"] is True
    assert set(d["calibPills"]) == {"Cam_Carraio", "Cam_Portico", "Cam_Ingresso", "Cam_Stradina"}
    assert d["resolvedStradina"] == "camera.stradina"


def test_f17_panoramic_aspect_preservation_ordering_and_layout_switch():
    import json

    repo_root = Path(__file__).resolve().parents[2]
    manifest = json.loads((repo_root / "public" / "models" / "scene_manifest.json").read_text(encoding="utf-8"))
    manifest_subset = {
        "cameras": {
            k: v
            for k, v in manifest.get("cameras", {}).items()
            if v.get("is_real_security_camera")
        },
    }
    manifest_json = json.dumps(manifest_subset)

    code = f"""
      const manifest = {manifest_json};
      const {{ CameraCatalog }} = await loadModule('/src/video/CameraCatalog.js');
      const {{ HaSnapshotFallbackStream }} = await loadModule('/src/video/HaSnapshotFallbackStream.js');
      const {{ SecurityFabHub }} = await loadModule('/src/ui/SecurityFabHub.js');

      const catalog = new CameraCatalog();
      catalog.syncFromManifest(manifest);

      // 1. Verifica che HaSnapshotFallbackStream non schiacci mai il 180° in 640x360:
      //    parte a 1280x360 (32:9) per Duo 3 PoE e si ridimensiona dinamicamente a 960x360 su frame 1536x576 (8:3)
      const ingCam = catalog.getCameraById('Cam_Ingresso');
      const carCam = catalog.getCameraById('Cam_Carraio');
      const panoStream = new HaSnapshotFallbackStream('ingresso_sub', {{
        cameraName: ingCam.id,
        aspectRatio: ingCam.aspectRatio,
        isPanoramic180: ingCam.isPanoramic180,
      }});
      const stdStream = new HaSnapshotFallbackStream('carraio_sub', {{
        cameraName: carCam.id,
        aspectRatio: carCam.aspectRatio,
        isPanoramic180: carCam.isPanoramic180,
      }});
      const panoVideo = ctx.document.createElement('video');
      const stdVideo = ctx.document.createElement('video');
      await panoStream.connect(panoVideo);
      await stdStream.connect(stdVideo);
      const panoInitSize = {{ w: panoStream.canvas.width, h: panoStream.canvas.height }};
      const stdInitSize = {{ w: stdStream.canvas.width, h: stdStream.canvas.height }};

      // Simula arrivo di snapshot 1536x576 (8:3 sub-stream Reolink Duo 3 PoE) -> canvas 960x360
      panoStream._syncCanvasDimensionsToImage({{ width: 1536, height: 576 }});
      const panoAfterSubSize = {{ w: panoStream.canvas.width, h: panoStream.canvas.height }};
      // Simula arrivo di snapshot 7680x2160 (32:9 main-stream Reolink Duo 3 PoE) -> canvas 1280x360
      panoStream._syncCanvasDimensionsToImage({{ width: 7680, height: 2160 }});
      const panoAfterMainSize = {{ w: panoStream.canvas.width, h: panoStream.canvas.height }};
      panoStream.disconnect();
      stdStream.disconnect();

      // 2. Verifica ordine DOM in SecurityFabHub: prima le 2 normali (Carraio, Portico), poi le 2 180° (Ingresso, Stradina)
      const hubRoot = ctx.document.createElement('div');
      ctx.document.body.appendChild(hubRoot);
      const hub = new SecurityFabHub(hubRoot, {{
        cameraCatalog: catalog,
        videoStreamManager: {{
          attachToVideoElement: async () => ({{ mode: 'webrtc', getStatus: () => ({{ mode: 'webrtc', connected: true }}), onStatusChange: () => () => {{}} }}),
          detachFromVideoElement: () => {{}},
        }},
        recordingManager: {{
          registerSlot: () => {{}},
          setPlaybackRate: () => {{}},
          setPlaying: () => {{}},
          seekAllToTimestamp: async () => {{}},
          queryAllSegments: async () => new Map(),
          detachAll: () => {{}},
          getStorageSummary: async () => ({{ configured: false }}),
        }},
        trajectoryRenderer: {{ setLiveMode() {{}}, setEntitiesVisible() {{}}, loadDetections() {{}}, clearHistorical() {{}}, updateAtTime() {{}}, interpolateLive() {{}} }},
        spatialStreamClient: {{ connected: false, onStatusChange: () => () => {{}}, onFrame: () => () => {{}} }},
        cameraController: {{ flyToPreset: () => {{}}, flyToCameraPOV: () => {{}} }},
        assetLoader: {{ cameras: new Map(), manifest }},
        deviceModals: {{ open: () => {{}} }},
      }});

      const orderedIds = hubRoot.querySelectorAll('.m3-cam-tile').map((t) => t.dataset.cameraId);
      const trackEl = hubRoot.querySelector('#sec-cameras-track');
      const layoutPropBtn = hubRoot.querySelector('#btn-sec-settings-layout-prop');
      const layoutCompactBtn = hubRoot.querySelector('#btn-sec-settings-layout-compact');
      const alarmBtn = hubRoot.querySelector('#btn-sec-alarm-control');

      // Default: modalità proporzionata (2 normali affiancate + 180° una sotto l'altra = 3 righe)
      const defaultLayout = hub.gridLayoutMode;
      const defaultHasCompact = trackEl.classList.contains('layout-compact');
      const defaultAriaChecked = layoutCompactBtn.getAttribute('aria-pressed');

      // Click in Impostazioni -> modalità compatta 2x2
      layoutCompactBtn.click();
      const afterToggleLayout = hub.gridLayoutMode;
      const afterToggleHasCompact = trackEl.classList.contains('layout-compact');
      const afterToggleAriaChecked = layoutCompactBtn.getAttribute('aria-pressed');

      // Click di nuovo su Proporzionata -> torna proporzionata
      layoutPropBtn.click();
      const restoredLayout = hub.gridLayoutMode;
      const restoredHasCompact = trackEl.classList.contains('layout-compact');
      const alarmBtnExists = Boolean(alarmBtn);

      // Verifica modale Allarme (switch & select dinamici per sh3d.allarme)
      alarmBtn.click();
      const alarmOverlay = hubRoot.querySelector('#sec-alarm-modal-overlay');
      const alarmOpened = Boolean(alarmOverlay && !alarmOverlay.hidden);
      const emptyMsgPresent = Boolean(hubRoot.querySelector('.m3-alarm-empty'));
      hub._setAlarmEntityState({{ entity_id: 'sh3d.allarme', name: 'Allarme', domain: 'switch', state: 'off' }});
      const switchModeRendered = Boolean(hubRoot.querySelector('#btn-alarm-modal-switch'));
      hub._setAlarmEntityState({{
        entity_id: 'sh3d.allarme',
        name: 'Allarme',
        domain: 'select',
        state: 'casa',
        options: ['disattivato', 'casa', 'notte'],
      }});
      const selectOptionsCount = hubRoot.querySelectorAll('[data-alarm-option]').length;
      hub.closeAlarmModal();
      const alarmClosed = Boolean(alarmOverlay && alarmOverlay.hidden);

      // 3. Verifica che un evento loadedmetadata temporaneo 640x360 NON tolga is-panoramic a Cam_Ingresso,
      //    e che un successivo resize 1536x576 aggiorni --cam-aspect a 2.6667 mantenendo is-panoramic
      const ingTile = hubRoot.querySelector('.m3-cam-tile[data-camera-id="Cam_Ingresso"]');
      const ingVideo = ingTile.querySelector('video');
      ingVideo.videoWidth = 640;
      ingVideo.videoHeight = 360;
      ingVideo.dispatchEvent({{ type: 'loadedmetadata' }});
      const ingStillPanoAfter16x9 = ingTile.classList.contains('is-panoramic');
      const ingAspectAfter16x9 = parseFloat(ingTile.style.getPropertyValue('--cam-aspect'));

      ingVideo.videoWidth = 1536;
      ingVideo.videoHeight = 576;
      ingVideo.dispatchEvent({{ type: 'resize' }});
      const ingStillPanoAfterSub = ingTile.classList.contains('is-panoramic');
      const ingAspectAfterSub = parseFloat(ingTile.style.getPropertyValue('--cam-aspect'));

      hub.dispose();
      return {{
        panoInitSize,
        stdInitSize,
        panoAfterSubSize,
        panoAfterMainSize,
        orderedIds,
        defaultLayout,
        defaultHasCompact,
        defaultAriaChecked,
        afterToggleLayout,
        afterToggleHasCompact,
        afterToggleAriaChecked,
        restoredLayout,
        restoredHasCompact,
        alarmBtnExists,
        alarmOpened,
        emptyMsgPresent,
        switchModeRendered,
        selectOptionsCount,
        alarmClosed,
        ingStillPanoAfter16x9,
        ingAspectAfter16x9,
        ingStillPanoAfterSub,
        ingAspectAfterSub,
      }};
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["panoInitSize"] == {"w": 1280, "h": 360}
    assert d["stdInitSize"] == {"w": 640, "h": 360}
    assert d["panoAfterSubSize"] == {"w": 960, "h": 360}
    assert d["panoAfterMainSize"] == {"w": 1280, "h": 360}
    assert d["orderedIds"] == ["Cam_Carraio", "Cam_Portico", "Cam_Ingresso", "Cam_Stradina"]
    assert d["defaultLayout"] == "proportional"
    assert d["defaultHasCompact"] is False
    assert d["defaultAriaChecked"] == "false"
    assert d["afterToggleLayout"] == "compact"
    assert d["afterToggleHasCompact"] is True
    assert d["afterToggleAriaChecked"] == "true"
    assert d["restoredLayout"] == "proportional"
    assert d["restoredHasCompact"] is False
    assert d["alarmBtnExists"] is True
    assert d["alarmOpened"] is True
    assert d["emptyMsgPresent"] is True
    assert d["switchModeRendered"] is True
    assert d["selectOptionsCount"] == 3
    assert d["alarmClosed"] is True
    assert d["ingStillPanoAfter16x9"] is True
    assert abs(d["ingAspectAfter16x9"] - (32.0 / 9.0)) < 0.01
    assert d["ingStillPanoAfterSub"] is True
    assert abs(d["ingAspectAfterSub"] - (8.0 / 3.0)) < 0.01


def test_f17_camera_modal_ha_controls_and_entity_resolution():
    code = """
      const { HAClient } = await loadModule('/src/ha/HAClient.js');
      const { SecurityCameraModal, resolveCameraControlEntities } = await loadModule('/src/devices/camera/SecurityCameraModal.js');
      const { SecurityCameraController } = await loadModule('/src/devices/camera/SecurityCameraController.js');

      const ha = new HAClient();
      const ctrl = new SecurityCameraController({ haClient: ha });

      // 1. Verifica risoluzione prefissi HA reali vs portico lampada principale
      const liveLikeEntities = {
        'light.portico': { entity_id: 'light.portico', state: 'on', attributes: {} },
        'camera.giardino_portico_scorrevole': { entity_id: 'camera.giardino_portico_scorrevole', state: 'idle', attributes: {} },
        'light.giardino_portico_faretto': { entity_id: 'light.giardino_portico_faretto', state: 'off', attributes: {} },
        'siren.giardino_portico_sirena': { entity_id: 'siren.giardino_portico_sirena', state: 'off', attributes: {} },
      };
      const resolvedPortico = resolveCameraControlEntities(liveLikeEntities, {
        entityId: 'camera.giardino_portico_scorrevole',
        camName: 'Cam_Portico',
        haClient: ha,
      });

      const resolvedCarraio = resolveCameraControlEntities(ha.mockEntities, {
        entityId: 'camera.carraio_scorrevole',
        camName: 'Cam_Carraio',
        haClient: ha,
      });

      // 2. Render modale Carraio e interazioni live
      const serviceCalls = [];
      const origCall = ha.callService.bind(ha);
      ha.callService = (domain, service, data) => {
        serviceCalls.push({ domain, service, data });
        return origCall(domain, service, data);
      };

      const vsmStub = {
        attachToVideoElement: async (streamName) => ({
          streamName,
          getStatus: () => ({ mode: 'webrtc', connected: true, latencyMs: 38 }),
          onStatusChange: () => () => {},
        }),
        detachFromVideoElement() {},
      };
      ctrl.videoStreamManager = vsmStub;

      const modal = new SecurityCameraModal(ctrl);
      const container = document.createElement('div');
      await modal.render(container, {
        entityId: 'camera.carraio_scorrevole',
        haClient: ha,
        assetLoader: { manifest: { cameras: { Cam_Carraio: {} } } },
      });

      const hasLegacyButtons = Boolean(
        container.querySelector('#btn-camera-pov') ||
        container.querySelector('#btn-camera-calibrate') ||
        container.querySelector('#btn-toggle-simulator')
      );

      // Toggle Faretto LED
      const spotlightBtn = container.querySelector('#btn-cam-spotlight-toggle');
      spotlightBtn.click();
      const spotlightCheckedAfterClick = spotlightBtn.classList.contains('checked');

      // Slider Luminosità
      const slider = container.querySelector('#cam-spotlight-brightness');
      slider.value = '85';
      slider.dispatchEvent({ type: 'change' });

      // Toggle Sirena Manuale ON -> OFF
      const sirenBtn = container.querySelector('#btn-cam-siren-toggle');
      sirenBtn.click();
      const sirenActiveAfterOn = sirenBtn.classList.contains('is-active');
      sirenBtn.click();
      const sirenActiveAfterOff = sirenBtn.classList.contains('is-active');

      // Toggle Notifiche Push + Modalità Faretto
      const pushTile = container.querySelector('#cam-sw-push');
      pushTile.click();
      const spotlightModesEl = container.querySelector('#cam-spotlight-modes');
      const scheduleChip = spotlightModesEl?.querySelector('[data-option="schedule"]');
      scheduleChip?.click();

      // Riavvio 2-step Admin confirmation + RBAC
      const rebootBtn = container.querySelector('#btn-cam-reboot');
      const rebootDisabledResident = Boolean(rebootBtn.disabled);
      ha.isAdmin = true;
      ha._notifyAuthChange();
      const rebootEnabledAdmin = !rebootBtn.disabled;
      rebootBtn.click(); // arme
      const callsAfterFirstRebootClick = serviceCalls.filter((c) => c.domain === 'button').length;
      rebootBtn.click(); // conferma
      const callsAfterSecondRebootClick = serviceCalls.filter((c) => c.domain === 'button').length;

      modal.destroy();

      return {
        resolvedPorticoSpotlight: resolvedPortico.spotlight,
        resolvedPorticoSiren: resolvedPortico.siren,
        resolvedCarraioSpotlight: resolvedCarraio.spotlight,
        resolvedCarraioSiren: resolvedCarraio.siren,
        hasLegacyButtons,
        spotlightCheckedAfterClick,
        sirenActiveAfterOn,
        sirenActiveAfterOff,
        rebootDisabledResident,
        rebootEnabledAdmin,
        callsAfterFirstRebootClick,
        callsAfterSecondRebootClick,
        serviceCalls,
        latencyText: container.querySelector('#cam-latency-badge')?.textContent,
      };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["resolvedPorticoSpotlight"] == "light.giardino_portico_faretto"
    assert d["resolvedPorticoSiren"] == "siren.giardino_portico_sirena"
    assert d["resolvedCarraioSpotlight"] == "light.carraio_faretto"
    assert d["resolvedCarraioSiren"] == "siren.carraio_sirena"
    assert d["hasLegacyButtons"] is False
    assert d["spotlightCheckedAfterClick"] is True
    assert d["sirenActiveAfterOn"] is True
    assert d["sirenActiveAfterOff"] is False
    assert d["rebootDisabledResident"] is True
    assert d["rebootEnabledAdmin"] is True
    assert d["callsAfterFirstRebootClick"] == 0
    assert d["callsAfterSecondRebootClick"] == 1
    assert d["latencyText"] == "38 ms"
    calls = d["serviceCalls"]
    assert any(c["domain"] == "light" and c["service"] == "turn_on" and c["data"]["entity_id"] == "light.carraio_faretto" for c in calls)
    assert any(c["domain"] == "number" and c["service"] == "set_value" and c["data"]["value"] == 85 for c in calls)
    assert any(c["domain"] == "siren" and c["service"] == "turn_on" and c["data"]["entity_id"] == "siren.carraio_sirena" for c in calls)
    assert any(c["domain"] == "siren" and c["service"] == "turn_off" and c["data"]["entity_id"] == "siren.carraio_sirena" for c in calls)
    assert any(c["domain"] == "switch" and c["service"] == "toggle" and c["data"]["entity_id"] == "switch.carraio_notifiche_push" for c in calls)
    assert any(c["domain"] == "select" and c["service"] == "select_option" and c["data"]["option"] == "schedule" for c in calls)
    assert any(c["domain"] == "button" and c["service"] == "press" and c["data"]["entity_id"] == "button.carraio_riavvia" for c in calls)

