import { SceneManager } from './core/SceneManager.js';
import { CameraController } from './core/CameraController.js';
import { AssetLoader } from './core/AssetLoader.js';
import { InteractionManager } from './core/InteractionManager.js';
import { HAClient } from './ha/HAClient.js';
import { EntityBinder } from './ha/EntityBinder.js';
import { DeviceModals } from './ha/DeviceModals.js';
import { CameraProjector } from './spatial/CameraProjector.js';
import { TrajectoryRenderer } from './spatial/TrajectoryRenderer.js';
import { TimelineController } from './spatial/TimelineController.js';
import { SpatialStreamClient } from './spatial/network/SpatialStreamClient.js';
import { CalibrationAssistantUI } from './spatial/calibration/CalibrationAssistantUI.js';
import { VideoStreamManager } from './video/VideoStreamManager.js';
import { deviceRegistry } from './devices/DeviceRegistry.js';
import { TopBar } from './ui/TopBar.js';
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

async function bootstrap() {
  console.log('[Main] Inizializzazione Smart Home 3D Digital Twin...');

  // 1. Container DOM
  const canvasContainer = document.getElementById('canvas-container');
  const css2dContainer = document.getElementById('css2d-container');
  const topBarContainer = document.getElementById('top-bar');
  const modalContainer = document.getElementById('device-modal-drawer');
  const timelineContainer = document.getElementById('timeline-container');

  // 2. Core 3D Scene
  const sceneManager = new SceneManager(canvasContainer, css2dContainer);
  const cameraController = new CameraController(sceneManager.camera, sceneManager.renderer.domElement);

  // 3. Asset Loader
  const assetLoader = new AssetLoader();

  // 4. Client Home Assistant
  const haClient = new HAClient();

  // 5. Entity Binder (Mesh 3D <-> HA)
  const entityBinder = new EntityBinder(sceneManager.scene, haClient);

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

  // 8. Spatial CV Engine, Video Streaming & Calibrazione POV
  const cameraProjector = new CameraProjector(sceneManager.scene, assetLoader);
  const trajectoryRenderer = new TrajectoryRenderer(sceneManager.scene);
  const timelineController = new TimelineController(timelineContainer, trajectoryRenderer, cameraProjector);
  const spatialStreamClient = new SpatialStreamClient();
  const videoStreamManager = new VideoStreamManager({
    haClient,
    spatialServerUrl: spatialStreamClient.baseUrl,
  });
  const calibrationAssistant = new CalibrationAssistantUI({
    sceneManager,
    cameraController,
    cameraProjector,
    videoStreamManager,
    spatialStreamClient,
    assetLoader,
    haClient,
  });

  timelineController.setSpatialStreamClient(spatialStreamClient);

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
    });
  }

  // 9. Top Navigation Bar
  const uiLayer = document.querySelector('.ui-layer');
  const topBar = new TopBar(topBarContainer, {
    sceneManager,
    cameraController,
    cameraProjector,
    interactionManager,
    haClient,
    calibrationAssistant,
    assetLoader,
    deviceModals,
  });

  const syncSheetState = () => {
    const anyOpen = modalContainer.classList.contains('open') || Boolean(calibrationAssistant?.isOpen);
    uiLayer?.classList.toggle('sheet-open', anyOpen);
    topBar?.calibBtn?.classList.toggle('active', Boolean(calibrationAssistant?.isOpen));
  };

  deviceModals.setLifecycleHooks({
    onOpen: () => {
      if (calibrationAssistant?.isOpen) {
        calibrationAssistant.close();
      }
      if (window.innerWidth <= 1024) {
        topBar.setQuickNavCollapsed(true);
      }
      syncSheetState();
    },
    onClose: syncSheetState,
  });

  calibrationAssistant.setLifecycleHooks({
    onOpen: () => {
      if (modalContainer.classList.contains('open')) {
        deviceModals.close();
      }
      if (window.innerWidth <= 1024) {
        topBar.setQuickNavCollapsed(true);
      }
      syncSheetState();
    },
    onClose: syncSheetState,
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
      }
      return;
    }

    if (authState.isMockMode) {
      authOverlay.hide();
      if (!isProd) {
        spatialStreamClient.connectWebSocket();
      }
      return;
    }

    if (authState.status === 'auth_required' || authState.status === 'error') {
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
    const { model, manifest, haEntitiesMap, groundColliders } = await assetLoader.loadHouseModel('/models/house_optimized.glb');
    sceneManager.scene.add(model);

    // Registra ground colliders per il raycasting spaziale
    cameraProjector.setGroundColliders(groundColliders);
    cameraProjector.setupCameraFrustums();

    // Collega entità a EntityBinder e InteractionManager
    entityBinder.bindEntities(haEntitiesMap);
    interactionManager.registerEntities(haEntitiesMap);
    interactionManager.createDeviceBadges(manifest, haEntitiesMap);

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
    timelineController.update(delta);
    interactionManager.update(sceneManager.camera);
  });
}

window.addEventListener('DOMContentLoaded', bootstrap);

