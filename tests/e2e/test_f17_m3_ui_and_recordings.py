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
