import { BaseDeviceController } from '../BaseDeviceController.js';
import { SecurityCameraModal } from './SecurityCameraModal.js';

/**
 * SecurityCameraController
 *
 * Controller decentralizzato multi-camera per le telecamere di sicurezza Reolink (SSoT da scene_manifest.json).
 * Integra il flusso video go2rtc (WebRTC/MSE), la vista POV 3D,
 * l'assistente di calibrazione ottica e il collegamento con il backend spaziale.
 */
export class SecurityCameraController extends BaseDeviceController {
  constructor(options = {}) {
    super('security_camera', {
      name: 'Telecamera Carraio (Reolink RLC-540A)',
      subtitle: 'Esterno Carraio • Live & Calibrazione',
      primaryEntityId: options.primaryEntityId || 'camera.carraio_scorrevole',
      associatedEntityIds: [
        'camera.carraio_scorrevole',
        'camera.carraio_trasparente',
        'camera.portico',
        'camera.portico_scorrevole',
        'camera.portico_trasparente',
        'camera.portico_fluente',
        'camera.ingresso',
        'camera.ingresso_scorrevole',
        'camera.ingresso_trasparente',
        'camera.ingresso_fluente',
        ...(options.associatedEntityIds || []),
      ],
      haClient: options.haClient,
    });

    this.modalView = new SecurityCameraModal(this);
    this.videoStreamManager = options.videoStreamManager || null;
    this.cameraProjector = options.cameraProjector || null;
    this.calibrationAssistant = options.calibrationAssistant || null;
    this.spatialStreamClient = options.spatialStreamClient || null;
    this.cameraController = options.cameraController || null;
    this.assetLoader = options.assetLoader || null;
    this.cameraCatalog = options.cameraCatalog || null;
    this.cameraMeshes = [];
    this.activeEntityId = this.primaryEntityId;
    this.isModalOpen = false;
  }

  setServices(services = {}) {
    if (services.haClient) this.haClient = services.haClient;
    if (services.videoStreamManager) this.videoStreamManager = services.videoStreamManager;
    if (services.cameraProjector) this.cameraProjector = services.cameraProjector;
    if (services.calibrationAssistant) this.calibrationAssistant = services.calibrationAssistant;
    if (services.spatialStreamClient) this.spatialStreamClient = services.spatialStreamClient;
    if (services.cameraController) this.cameraController = services.cameraController;
    if (services.assetLoader) this.assetLoader = services.assetLoader;
    if (services.cameraCatalog) this.cameraCatalog = services.cameraCatalog;
  }

  /**
   * Registra dinamicamente tutte le entità camera presenti nel manifesto Blender SSoT.
   */
  syncFromManifest(manifest) {
    const cameras = manifest?.cameras;
    if (!cameras) return;
    for (const [camName, camData] of Object.entries(cameras)) {
      const isSecurityCam =
        camName === 'Cam_Carraio' ||
        camData?.is_real_security_camera === true ||
        Boolean(camData?.ha_camera_entity);
      if (!isSecurityCam) continue;
      if (camData?.ha_camera_entity) {
        this.associatedEntityIds.add(camData.ha_camera_entity);
      }
    }
  }

  matchesEntity(entityId) {
    if (!entityId) return false;
    if (super.matchesEntity(entityId)) return true;
    if (this.cameraCatalog?.findByEntityId?.(entityId)) return true;
    const cameras = this.assetLoader?.manifest?.cameras;
    if (cameras) {
      for (const camData of Object.values(cameras)) {
        if (camData?.ha_camera_entity === entityId) return true;
      }
    }
    return false;
  }

  bind3D(meshes, scene, context) {
    super.bind3D(meshes, scene, context);
    this.cameraMeshes = meshes || [];

    // Assicura che i mesh fisici di ogni telecamera siano cliccabili mantenendo il proprio ha_entity SSoT
    this.cameraMeshes.forEach((mesh) => {
      if (!mesh.userData) mesh.userData = {};
      if (!mesh.userData.ha_entity) {
        mesh.userData.ha_entity = this.primaryEntityId;
      }
      mesh.userData.ha_action = 'modal';
    });
  }

  findMatchingBlenderCameraName(entityId = this.activeEntityId || this.primaryEntityId) {
    const cameras = this.assetLoader?.manifest?.cameras;
    const targetId = String(entityId || this.primaryEntityId || '').trim();
    const targetLower = targetId.toLowerCase();

    if (cameras) {
      // 1. Match esatto su ha_camera_entity
      for (const [name, camData] of Object.entries(cameras)) {
        if (camData?.ha_camera_entity && camData.ha_camera_entity === targetId) {
          return name;
        }
      }

      // 2. Match su slug / alias (es. camera.carraio_trasparente -> Cam_Carraio, camera.portico_scorrevole -> Cam_Portico)
      const entitySlug = targetLower.replace(/^camera\./, '');
      const baseSlug = entitySlug.replace(/_(scorrevole|trasparente|fluente|main|sub)$/i, '');
      for (const [name, camData] of Object.entries(cameras)) {
        const isSecurityCam =
          name === 'Cam_Carraio' ||
          camData?.is_real_security_camera === true ||
          Boolean(camData?.ha_camera_entity);
        if (!isSecurityCam) continue;

        const camSlug = name.replace(/^Cam_/i, '').toLowerCase();
        const streamBase = String(camData?.stream_id || '').replace(/_main$/i, '').toLowerCase();
        if (
          (baseSlug && (camSlug === baseSlug || streamBase === baseSlug || entitySlug.startsWith(`${camSlug}_`))) ||
          (camData?.ha_camera_entity && baseSlug && camData.ha_camera_entity.toLowerCase().includes(baseSlug))
        ) {
          return name;
        }
      }
    }

    if (targetLower.includes('portico')) return 'Cam_Portico';
    if (targetLower.includes('ingresso')) return 'Cam_Ingresso';
    return 'Cam_Carraio';
  }

  getModalHeaderInfo(entityId = this.activeEntityId || this.primaryEntityId, entity = null) {
    const camName = this.findMatchingBlenderCameraName(entityId);
    const manifestCam = this.assetLoader?.manifest?.cameras?.[camName];
    const catalogCam = this.cameraCatalog?.getCameraById?.(camName) || this.cameraCatalog?.findByEntityId?.(entityId);

    const title =
      manifestCam?.ha_label ||
      catalogCam?.name ||
      (camName === 'Cam_Portico' ? 'Portico (Reolink RLC-810A)' : null) ||
      (camName === 'Cam_Ingresso' ? 'Ingresso (Reolink Duo 3 PoE)' : null) ||
      entity?.attributes?.friendly_name ||
      this.name;

    const rawZone = manifestCam?.coverage_zone || catalogCam?.coverageZone || '';
    const zoneLabel =
      camName === 'Cam_Carraio' || rawZone === 'outdoor_gates_street'
        ? 'Esterno Carraio'
        : rawZone && rawZone !== 'general' && rawZone !== 'outdoor'
          ? String(rawZone).replace(/\./g, ' ').trim()
          : (catalogCam?.shortName || camName.replace(/^Cam_/i, '').replace(/_/g, ' '));

    return {
      title,
      subtitle: `${zoneLabel} • Live & Calibrazione`,
    };
  }

  renderModal(container, entity, context = {}) {
    this.isModalOpen = true;
    this.activeEntityId = entity?.entity_id || context.entityId || this.primaryEntityId;
    if (context.haClient) this.haClient = context.haClient;
    if (context.cameraController) this.cameraController = context.cameraController;
    if (context.assetLoader) this.assetLoader = context.assetLoader;
    this.modalView.render(container, context, entity);
  }

  onModalClose() {
    this.isModalOpen = false;
    this.modalView.destroy();
  }

  dispose() {
    this.modalView.destroy();
  }
}

