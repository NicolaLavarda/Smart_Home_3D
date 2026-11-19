import { BaseDeviceController } from '../BaseDeviceController.js';
import { SecurityCameraModal } from './SecurityCameraModal.js';

/**
 * SecurityCameraController
 *
 * Controller decentralizzato per le telecamere di sicurezza Reolink (Cam_Carraio).
 * Integra il flusso video go2rtc (WebRTC/MSE), la vista POV 3D,
 * l'assistente di calibrazione ottica e il collegamento con il backend spaziale.
 */
export class SecurityCameraController extends BaseDeviceController {
  constructor(options = {}) {
    super('security_camera', {
      name: 'Telecamera Carraio (Reolink RLC-540A)',
      subtitle: 'camera.carraio_scorrevole • 192.168.86.47',
      primaryEntityId: options.primaryEntityId || 'camera.carraio_scorrevole',
      associatedEntityIds: [
        'camera.carraio_scorrevole',
        'camera.carraio_trasparente',
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
    this.cameraMeshes = [];
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
  }

  bind3D(meshes, scene, context) {
    super.bind3D(meshes, scene, context);
    this.cameraMeshes = meshes || [];

    // Assicura che i mesh fisici della telecamera sul pilastrino siano cliccabili
    this.cameraMeshes.forEach((mesh) => {
      if (!mesh.userData) mesh.userData = {};
      if (!mesh.userData.ha_entity) {
        mesh.userData.ha_entity = this.primaryEntityId;
      }
      mesh.userData.ha_action = 'modal';
    });
  }

  findMatchingBlenderCameraName(entityId = this.primaryEntityId) {
    const cameras = this.assetLoader?.manifest?.cameras;
    if (!cameras) return 'Cam_Carraio';
    for (const [name, camData] of Object.entries(cameras)) {
      if (camData.ha_camera_entity === entityId || (camData.ha_camera_entity && entityId?.includes('carraio'))) {
        return name;
      }
    }
    return 'Cam_Carraio';
  }

  renderModal(container, entity, context = {}) {
    this.isModalOpen = true;
    if (context.haClient) this.haClient = context.haClient;
    if (context.cameraController) this.cameraController = context.cameraController;
    if (context.assetLoader) this.assetLoader = context.assetLoader;
    this.modalView.render(container, context);
  }

  onModalClose() {
    this.isModalOpen = false;
    this.modalView.destroy();
  }

  dispose() {
    this.modalView.destroy();
  }
}

