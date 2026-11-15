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
  const videoStreamManager = new VideoStreamManager({ haClient });
  const spatialStreamClient = new SpatialStreamClient();
  const calibrationAssistant = new CalibrationAssistantUI({
    sceneManager,
    cameraController,
    cameraProjector,
    videoStreamManager,
    spatialStreamClient,
    assetLoader,
  });

  timelineController.setSpatialStreamClient(spatialStreamClient);

  const secCamCtrl = deviceRegistry.get('security_camera');
  if (secCamCtrl) {
    secCamCtrl.setServices({
      videoStreamManager,
      cameraProjector,
      calibrationAssistant,
      spatialStreamClient,
      cameraController,
      assetLoader,
    });
  }

  // 9. Top Navigation Bar
  new TopBar(topBarContainer, {
    sceneManager,
    cameraController,
    cameraProjector,
    interactionManager,
    haClient,
    calibrationAssistant,
    assetLoader,
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

  // 11. Avvia connessione Home Assistant e Spatial CV Backend (o fallback)
  haClient.connect();
  spatialStreamClient.connectWebSocket();

  // 12. Hook di Aggiornamento per il Render Loop
  sceneManager.addUpdateCallback((delta) => {
    cameraController.update(delta);
    entityBinder.update(delta);
    timelineController.update(delta);
    interactionManager.update(sceneManager.camera);
  });
}

window.addEventListener('DOMContentLoaded', bootstrap);

