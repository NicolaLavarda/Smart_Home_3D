import { SceneManager } from './core/SceneManager.js';
import { CameraController } from './core/CameraController.js';
import { AssetLoader } from './core/AssetLoader.js';
import { InteractionManager } from './core/InteractionManager.js';
import { HAClient } from './ha/HAClient.js';
import { EntityBinder } from './ha/EntityBinder.js';
import { DeviceModals } from './ha/DeviceModals.js';
import { CameraProjector } from './spatial/CameraProjector.js';
import { CameraPovOverlayController } from './spatial/CameraPovOverlayController.js';
import { TrajectoryRenderer } from './spatial/TrajectoryRenderer.js';
import { SpatialStreamClient } from './spatial/network/SpatialStreamClient.js';
import { CalibrationAssistantUI } from './spatial/calibration/CalibrationAssistantUI.js';
import { SpatialZoneRenderer3D } from './spatial/automations/SpatialZoneRenderer3D.js';
import { AutomationStudioUI } from './spatial/automations/AutomationStudioUI.js';
import { VideoStreamManager } from './video/VideoStreamManager.js';
import { CameraCatalog } from './video/CameraCatalog.js';
import {
  CameraRecordingManager,
  SpatialServerNvrProvider,
  EdgeCameraSdProvider,
} from './video/recordings/index.js';
import { deviceRegistry } from './devices/DeviceRegistry.js';
import { TopBar } from './ui/TopBar.js';
import { NavigationFabHub } from './ui/NavigationFabHub.js';
import { SecurityFabHub } from './ui/SecurityFabHub.js';
import { PwaUpdatePrompt } from './ui/PwaUpdatePrompt.js';
import { icon } from './ui/icons.js';

function createAuthOverlay(haClient, uiLayer) {
  const host = uiLayer || document.body;
  let overlay = document.getElementById('ha-auth-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'ha-auth-overlay';
    overlay.className = 'ha-auth-overlay';
    overlay.hidden = true;
    overlay.innerHTML = `
      <div class="ha-auth-card glass" role="dialog" aria-modal="true" aria-labelledby="ha-auth-title">
        <div class="ha-auth-icon">${icon('shield-check', { size: 28 })}</div>
        <h2 class="ha-auth-title" id="ha-auth-title">Smart Home 3D</h2>
        <p class="ha-auth-subtitle">
          Accedi con il tuo account Home Assistant per controllare i dispositivi, visualizzare le telecamere e lo Spatial Engine.
        </p>
        <div class="ha-auth-error" id="ha-auth-error-msg" hidden></div>
        <button type="button" class="btn-action-primary ha-auth-btn" id="btn-ha-oauth-login">
          ${icon('log-in', { size: 16 })}
          <span>Accedi con Home Assistant</span>
        </button>
      </div>
    `;
    host.appendChild(overlay);
  }

  const errorEl = overlay.querySelector('#ha-auth-error-msg');
  const loginBtn = overlay.querySelector('#btn-ha-oauth-login');

  const show = (errorMsg = '') => {
    if (errorEl) {
      if (errorMsg) {
        errorEl.textContent = errorMsg;
        errorEl.hidden = false;
      } else {
        errorEl.textContent = '';
        errorEl.hidden = true;
      }
    }
    if (loginBtn) {
      loginBtn.disabled = false;
      loginBtn.innerHTML = `${icon('log-in', { size: 16 })} <span>Accedi con Home Assistant</span>`;
    }
    overlay.hidden = false;
    overlay.classList.add('open');
  };

  const hide = () => {
    overlay.classList.remove('open');
    overlay.hidden = true;
    if (errorEl) {
      errorEl.textContent = '';
      errorEl.hidden = true;
    }
  };

  loginBtn?.addEventListener('click', async () => {
    if (errorEl) {
      errorEl.textContent = '';
      errorEl.hidden = true;
    }
    loginBtn.disabled = true;
    loginBtn.innerHTML = `${icon('log-in', { size: 16 })} <span>Reindirizzamento...</span>`;
    const started = await haClient.loginWithOAuth();
    if (!started) {
      loginBtn.disabled = false;
      loginBtn.innerHTML = `${icon('log-in', { size: 16 })} <span>Accedi con Home Assistant</span>`;
    }
  });

  return { overlay, show, hide };
}

function ensureUiContainer(uiLayer, id, className) {
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement('div');
    el.id = id;
    el.className = className;
    (uiLayer || document.body)?.appendChild(el);
  }
  return el;
}

async function bootstrap() {
  console.log('[Main] Inizializzazione Smart Home 3D Digital Twin...');

  // 1. Container DOM
  const canvasContainer = document.getElementById('canvas-container');
  const css2dContainer = document.getElementById('css2d-container');
  const topBarContainer = document.getElementById('top-bar');
  const modalContainer = document.getElementById('device-modal-drawer');
  const uiLayer = document.querySelector('.ui-layer');
  const securityHubContainer = ensureUiContainer(uiLayer, 'security-hub-root', 'security-hub-root');
  const navHubContainer = ensureUiContainer(uiLayer, 'nav-hub-root', 'nav-hub-root');

  // 2. Core 3D Scene
  const sceneManager = new SceneManager(canvasContainer, css2dContainer);
  const cameraController = new CameraController(sceneManager.camera, sceneManager.renderer.domElement);

  // 3. Asset Loader
  const assetLoader = new AssetLoader();

  // 4. Client Home Assistant
  const haClient = new HAClient();

  // 5. Entity Binder (Mesh 3D <-> HA)
  const entityBinder = new EntityBinder(sceneManager.scene, haClient, {
    isMobileProfile: sceneManager.isMobileProfile,
    onSceneMoved: () => sceneManager.requestShadowUpdate(),
  });
  entityBinder.setCameraController(cameraController);

  // 6. Device Modals
  const deviceModals = new DeviceModals(modalContainer, haClient, cameraController, assetLoader);

  // 7. Interaction Manager (Raycasting, Click, CSS2D Badges)
  const interactionManager = new InteractionManager(
    sceneManager.scene,
    sceneManager.camera,
    sceneManager.renderer.domElement,
    entityBinder,
    (entityId) => deviceModals.open(entityId)
  );
  entityBinder.setInteractionManager(interactionManager);

  // 8. Spatial CV Engine, Multi-Camera Catalog, Video Streaming & Architettura NVR/Edge OOP
  const cameraCatalog = new CameraCatalog();
  const cameraProjector = new CameraProjector(sceneManager.scene, assetLoader);
  const trajectoryRenderer = new TrajectoryRenderer(sceneManager.scene);
  const spatialStreamClient = new SpatialStreamClient();
  const videoStreamManager = new VideoStreamManager({
    haClient,
    cameraCatalog,
    spatialServerUrl: spatialStreamClient.baseUrl,
  });
  const recordingManager = new CameraRecordingManager({
    cameraCatalog,
    providers: [
      new SpatialServerNvrProvider({ spatialStreamClient }),
      new EdgeCameraSdProvider({ haClient }),
    ],
  });
  const calibrationAssistant = new CalibrationAssistantUI({
    sceneManager,
    cameraController,
    cameraProjector,
    videoStreamManager,
    spatialStreamClient,
    assetLoader,
    haClient,
    cameraCatalog,
  });

  const spatialZoneRenderer = new SpatialZoneRenderer3D({
    sceneManager,
    cameraProjector,
  });
  const automationStudio = new AutomationStudioUI({
    sceneManager,
    cameraController,
    spatialStreamClient,
    zoneRenderer: spatialZoneRenderer,
    haClient,
    uiLayer,
  });

  const secCamCtrl = deviceRegistry.get('security_camera');
  if (secCamCtrl) {
    secCamCtrl.setServices({
      haClient,
      videoStreamManager,
      cameraProjector,
      calibrationAssistant,
      spatialStreamClient,
      cameraController,
      assetLoader,
      cameraCatalog,
    });
  }

  // 9. Top Navigation Bar + Nuovi Hub FAB Material 3 (Sinistra: Sicurezza, Destra: Viste & Dispositivi)
  const topBar = new TopBar(topBarContainer, {
    sceneManager,
    cameraController,
    cameraProjector,
    interactionManager,
    haClient,
    calibrationAssistant,
    automationStudio,
    assetLoader,
    deviceModals,
    cameraCatalog,
  });

  let navFabHub = null;
  let securityFabHub = null;
  let povOverlayController = null;

  const syncUiLayerState = () => {
    const anyDrawerOpen =
      modalContainer.classList.contains('open') ||
      Boolean(calibrationAssistant?.isOpen) ||
      Boolean(automationStudio?.isOpen);
    const secStripActive = Boolean(securityFabHub?.isStrip);
    const secExpanded = Boolean(securityFabHub?.isExpanded);
    const navExpanded = Boolean(navFabHub?.isOpen);

    uiLayer?.classList.toggle('sheet-open', anyDrawerOpen);
    uiLayer?.classList.toggle('sec-strip-active', secStripActive);
    uiLayer?.classList.toggle('sec-expanded-active', secExpanded);
    uiLayer?.classList.toggle('nav-expanded-active', navExpanded);
    topBar?.calibBtn?.classList.toggle('active', Boolean(calibrationAssistant?.isOpen));
    topBar?.automationsBtn?.classList.toggle('active', Boolean(automationStudio?.isOpen));
  };

  navFabHub = new NavigationFabHub(navHubContainer, {
    cameraController,
    deviceModals,
    haClient,
    onOpenChange: (opened) => {
      if (opened && securityFabHub?.isExpanded) {
        securityFabHub.close();
      }
      syncUiLayerState();
    },
  });

  securityFabHub = new SecurityFabHub(securityHubContainer, {
    cameraCatalog,
    videoStreamManager,
    recordingManager,
    trajectoryRenderer,
    spatialStreamClient,
    cameraController,
    assetLoader,
    deviceModals,
    haClient,
    onStateChange: (state) => {
      if (state === 'expanded') {
        navFabHub?.close();
        if (window.innerWidth <= 1024) {
          if (modalContainer.classList.contains('open')) deviceModals.close();
          if (calibrationAssistant?.isOpen) calibrationAssistant.close();
        }
      }
      povOverlayController?.handleSecurityPanelStateChange?.();
      syncUiLayerState();
    },
  });

  povOverlayController = new CameraPovOverlayController({
    cameraController,
    cameraProjector,
    videoStreamManager,
    recordingManager,
    cameraCatalog,
    securityFabHub,
    calibrationAssistant,
    haClient,
    assetLoader,
    uiLayer,
  });

  deviceModals.setLifecycleHooks({
    onOpen: () => {
      if (calibrationAssistant?.isOpen) {
        calibrationAssistant.close();
      }
      navFabHub?.close();
      if (window.innerWidth <= 1024 && securityFabHub?.isExpanded) {
        securityFabHub.close();
      }
      syncUiLayerState();
    },
    onClose: syncUiLayerState,
  });

  calibrationAssistant.setLifecycleHooks({
    onOpen: () => {
      povOverlayController?.suspendForCalibration?.();
      if (modalContainer.classList.contains('open')) {
        deviceModals.close();
      }
      if (automationStudio?.isOpen) {
        automationStudio.close();
      }
      navFabHub?.close();
      if (securityFabHub?.isExpanded) {
        securityFabHub.close();
      }
      syncUiLayerState();
    },
    onClose: () => {
      povOverlayController?.resumeAfterCalibration?.();
      syncUiLayerState();
    },
  });

  automationStudio.setLifecycleHooks({
    onOpen: () => {
      if (modalContainer.classList.contains('open')) {
        deviceModals.close();
      }
      if (calibrationAssistant?.isOpen) {
        calibrationAssistant.close();
      }
      navFabHub?.close();
      if (window.innerWidth <= 1024 && securityFabHub?.isExpanded) {
        securityFabHub.close();
      }
      syncUiLayerState();
    },
    onClose: syncUiLayerState,
  });

  // 9b. Overlay Auth OAuth2 Home Assistant, PWA Update Prompt & Sincronizzazione Spatial Session
  const authOverlay = createAuthOverlay(haClient, uiLayer);
  new PwaUpdatePrompt({ container: uiLayer });

  spatialStreamClient.setTokenProvider(() => haClient.getAccessToken());
  spatialStreamClient.onAuthError(async () => {
    if (haClient.isMockMode) return;
    if (!haClient.connection || haClient.authStatus === 'auth_required') {
      authOverlay.show('Sessione scaduta. Accedi nuovamente con Home Assistant.');
      return;
    }
    const token = await haClient.getAccessToken();
    if (!token) {
      authOverlay.show('Sessione Home Assistant scaduta. Effettua di nuovo il login.');
    }
  });

  haClient.onStatusChange((status) => {
    if (status === 'auth_required') {
      authOverlay.show();
    } else if (status === 'online' || status === 'mock') {
      authOverlay.hide();
    }
  });

  let frustumsReady = false;
  let authReadyForSpatial = false;
  let lastSpatialWsConnected = false;
  let calibrationSyncPromise = null;
  let handledInitialDeepLink = false;

  const processDeepLinkQueryIfNeeded = async () => {
    if (handledInitialDeepLink || typeof window === 'undefined') return;
    let params;
    try {
      params = new URLSearchParams(window.location.search || '');
    } catch {
      return;
    }
    const eventId = (params.get('event') || '').trim();
    const panelParam = (params.get('panel') || '').trim().toLowerCase();
    const modeParam = (params.get('mode') || '').trim().toLowerCase();
    if (!eventId && panelParam !== 'security') return;

    handledInitialDeepLink = true;
    try {
      if (eventId) {
        await securityFabHub.openEventById(eventId);
      } else if (panelParam === 'security') {
        securityFabHub.openExpanded();
        if (['live', 'events', 'replay', 'settings'].includes(modeParam)) {
          await securityFabHub.setMode(modeParam);
        }
      }
    } catch (err) {
      console.warn('[Main] Errore apertura deep-link:', err);
    }

    try {
      params.delete('event');
      params.delete('panel');
      params.delete('mode');
      const nextSearch = params.toString();
      const cleanUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ''}${window.location.hash || ''}`;
      window.history.replaceState({}, '', cleanUrl);
    } catch {}
  };

  const refreshActivePovIfNeeded = (updatedCameras = []) => {
    if (!Array.isArray(updatedCameras) || updatedCameras.length === 0) return;
    if (calibrationAssistant?.isOpen) return;
    const activePovCam = cameraController?.activePovCameraName;
    if (!activePovCam || !updatedCameras.includes(activePovCam)) return;
    if (cameraController.isTransitioning || cameraController._povPhase !== 'active') return;
    const pose = cameraProjector.getCalibratedCameraPose(activePovCam);
    if (pose?.position && pose?.quaternion) {
      cameraController.setInstantCameraPose(pose.position, pose.quaternion, pose.fovV, activePovCam);
    }
  };

  const syncCalibrationsFromBackend = async () => {
    if (!frustumsReady || !authReadyForSpatial) return null;
    if (calibrationSyncPromise) return await calibrationSyncPromise;
    calibrationSyncPromise = (async () => {
      try {
        const res = await spatialStreamClient.fetchAllCameraCalibrations();
        if (res?.status === 'ok' && res.calibrations) {
          const syncRes = cameraProjector.applyBackendCalibrations(res.calibrations, { persistLocal: true });
          refreshActivePovIfNeeded(syncRes.updatedCameras);
          return syncRes;
        }
      } catch (err) {
        console.warn('[Main] Errore sincronizzazione calibrazioni dal backend:', err);
      }
      return null;
    })();
    try {
      return await calibrationSyncPromise;
    } finally {
      calibrationSyncPromise = null;
    }
  };

  spatialStreamClient.onCalibrationUpdate((msg) => {
    if (!frustumsReady || !msg?.camera_id || !msg?.calibration) return;
    if (calibrationAssistant?.isOpen && calibrationAssistant.activeCameraName === msg.camera_id) {
      return;
    }
    const res = cameraProjector.applyBackendCalibration(msg.camera_id, msg.calibration, { persistLocal: true });
    if (res.changed) {
      refreshActivePovIfNeeded([msg.camera_id]);
    }
  });

  spatialStreamClient.onStatusChange((connected) => {
    const isNowConnected = Boolean(connected);
    if (isNowConnected && !lastSpatialWsConnected) {
      syncCalibrationsFromBackend();
    }
    lastSpatialWsConnected = isNowConnected;
  });

  haClient.onAuthChange(async (authState) => {
    let isProdBuild = false;
    try { isProdBuild = Boolean(import.meta.env.PROD); } catch {}
    const isProd = isProdBuild || (typeof window !== 'undefined' && window.location?.protocol === 'https:');

    if (authState.authenticated) {
      authOverlay.hide();
      const token = (await haClient.getAccessToken()) || authState.token;
      const session = token ? await spatialStreamClient.authenticateWithHaToken(token) : false;
      if (session === true || session?.authenticated || (!isProd && Boolean(session))) {
        spatialStreamClient.connectWebSocket();
        authReadyForSpatial = true;
        syncCalibrationsFromBackend();
        void processDeepLinkQueryIfNeeded();
      }
      return;
    }

    if (authState.isMockMode) {
      authOverlay.hide();
      if (!isProd) {
        spatialStreamClient.connectWebSocket();
        authReadyForSpatial = true;
        syncCalibrationsFromBackend();
        void processDeepLinkQueryIfNeeded();
      }
      return;
    }

    if (authState.status === 'auth_required' || authState.status === 'error') {
      authReadyForSpatial = false;
      if (authState.reason === 'logout' || spatialStreamClient.isAuthenticated || spatialStreamClient.connected) {
        await spatialStreamClient.logout().catch(() => {});
      } else {
        spatialStreamClient.disconnect();
      }
      authOverlay.show(authState.error || '');
    }
  });

  // 10. Carica Modello e Manifesto
  try {
    const { model, manifest, haEntitiesMap, groundColliders, occlusionColliders } = await assetLoader.loadHouseModel('/models/house_optimized.glb');
    sceneManager.scene.add(model);

    // Sincronizza il catalogo telecamere e il controller multi-camera con Blender SSoT
    cameraCatalog.syncFromManifest(manifest);
    secCamCtrl?.syncFromManifest?.(manifest);

    // Registra ground colliders e ostacoli architettonici per il raycasting spaziale
    cameraProjector.setGroundColliders(groundColliders);
    cameraProjector.setOcclusionColliders(occlusionColliders);
    cameraProjector.setupCameraFrustums();
    frustumsReady = true;
    syncCalibrationsFromBackend();

    // Collega entità a EntityBinder e InteractionManager
    entityBinder.bindEntities(haEntitiesMap);
    interactionManager.registerEntities(haEntitiesMap);
    interactionManager.createDeviceBadges(manifest, haEntitiesMap);
    sceneManager.requestShadowUpdate();

    console.log('[Main] Scena 3D configurata e pronta!');
  } catch (err) {
    console.error('[Main] Errore critico durante il caricamento:', err);
  }

  // 11. Avvia connessione Home Assistant (lo Spatial WS si collega via onAuthChange dopo sessione)
  haClient.connect();

  // 12. Hook di Aggiornamento per il Render Loop
  sceneManager.addUpdateCallback((delta) => {
    cameraController.update(delta);
    entityBinder.update(delta);
    securityFabHub.update(delta);
    interactionManager.update(sceneManager.camera);
  });
}

window.addEventListener('DOMContentLoaded', bootstrap);
