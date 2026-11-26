/**
 * CameraDescriptor
 *
 * Modello immutabile che descrive una telecamera di sicurezza fisica
 * per il player Live, la timeline di Replay Storico e la proiezione 3D.
 */
export class CameraDescriptor {
  constructor(config = {}) {
    this.id = String(config.id || config.name || 'Cam_Carraio');
    this.name = String(config.name || config.label || this.id);
    this.shortName = String(config.shortName || this.name.replace(/\s*\(.*?\)\s*/g, '').trim() || this.id);
    this.blenderCameraName = String(config.blenderCameraName || this.id);
    this.entityId = String(config.entityId || config.ha_camera_entity || '');
    this.mainStream = String(config.mainStream || config.stream_id || '');
    this.subStream = String(config.subStream || config.sub_stream_id || this.mainStream);
    this.cameraIp = String(config.cameraIp || config.camera_ip || '');
    this.coverageZone = String(config.coverageZone || config.coverage_zone || 'outdoor');
    this.opticalModel = String(config.opticalModel || config.optical_model || 'pinhole_radtan');
    this.cameraModel = String(config.cameraModel || config.camera_model || '');
    this.lensMm = Number(config.lensMm ?? config.lens_mm ?? 4.0);
    this.mainStreamLabel = String(config.mainStreamLabel || config.main_stream_label || '');
    this.subStreamLabel = String(config.subStreamLabel || config.sub_stream_label || '');
    this.fovH = Number(config.fovH ?? config.fov_h_deg ?? 80);
    this.fovV = Number(config.fovV ?? config.fov_v_deg ?? 42);
    this.isPanoramic180 = Boolean(
      config.isPanoramic180 ??
      (this.opticalModel.toLowerCase().includes('panoramic') ||
        this.opticalModel.toLowerCase().includes('equirectangular') ||
        this.fovH >= 150)
    );
    const fallbackAspect = this.isPanoramic180 ? 32 / 9 : 16 / 9;
    const rawAspect = Number(config.aspectRatio ?? config.aspect_ratio);
    this.aspectRatio = Number.isFinite(rawAspect) && rawAspect > 0.3 && rawAspect < 6.0
      ? rawAspect
      : fallbackAspect;
    this.recordingCameraId = String(config.recordingCameraId || this.id);
    this.enabled = config.enabled !== false;
  }

  /**
   * Restituisce il nome stream go2rtc migliore per la qualità richiesta ('main' | 'sub').
   */
  getStreamName(quality = 'sub') {
    if (quality === 'main') {
      return this.mainStream || this.subStream || this.id.toLowerCase();
    }
    return this.subStream || this.mainStream || this.id.toLowerCase();
  }
}

/**
 * CameraCatalog
 *
 * Registro centralizzato e scalabile delle telecamere di sicurezza.
 * Carica automaticamente tutte le telecamere reali da `scene_manifest.json`
 * (Blender SSoT) e supporta estensioni dinamiche (es. nuove 3 telecamere,
 * inclusa telecamera panoramica 180°, via manifest o configurazione JSON).
 */
export class CameraCatalog {
  constructor() {
    this.cameras = new Map();
    this.listeners = new Set();
    this._ensureDefaultCamera();
    this._loadEnvExtraCameras();
  }

  _ensureDefaultCamera() {
    if (this.cameras.size === 0) {
      this.registerCamera(
        new CameraDescriptor({
          id: 'Cam_Carraio',
          name: 'Telecamera Carraio (Reolink RLC-540A)',
          shortName: 'Carraio',
          blenderCameraName: 'Cam_Carraio',
          entityId: 'camera.carraio_scorrevole',
          mainStream: 'carraio_main',
          subStream: 'carraio_sub',
          cameraIp: '192.168.86.47',
          coverageZone: 'outdoor_gates_street',
          fovH: 89.0,
          fovV: 72.81,
          aspectRatio: 4 / 3,
        })
      );
    }
  }

  _loadEnvExtraCameras() {
    let rawJson = '';
    try {
      rawJson = import.meta.env.VITE_SECURITY_CAMERAS_JSON || '';
    } catch {}
    if (!rawJson || typeof rawJson !== 'string') return;
    try {
      const parsed = JSON.parse(rawJson);
      if (Array.isArray(parsed)) {
        parsed.forEach((item) => {
          if (item && (item.id || item.name)) {
            this.registerCamera(new CameraDescriptor(item));
          }
        });
      }
    } catch (err) {
      console.warn('[CameraCatalog] Impossibile leggere VITE_SECURITY_CAMERAS_JSON:', err?.message || err);
    }
  }

  /**
   * Sincronizza il catalogo leggendo le telecamere reali dal manifesto Blender SSoT.
   * Qualsiasi nuova telecamera esportata in `scene_manifest.json` con `is_real_security_camera: true`
   * o `ha_camera_entity` appare automaticamente nell'interfaccia Sicurezza.
   */
  syncFromManifest(manifest) {
    if (!manifest || !manifest.cameras) return this.getCameras();

    let updated = false;
    for (const [camKey, camData] of Object.entries(manifest.cameras)) {
      const isSecurityCam =
        camKey === 'Cam_Carraio' ||
        camData?.is_real_security_camera === true ||
        Boolean(camData?.ha_camera_entity);

      if (!isSecurityCam) continue;

      const label = camData.ha_label || camData.name || camKey;
      const shortName = camKey === 'Cam_Carraio'
        ? 'Carraio'
        : label.replace(/^Telecamera\s+/i, '').replace(/\s*\(.*?\)\s*/g, '').trim() || camKey;

      const descriptor = new CameraDescriptor({
        id: camKey,
        name: label,
        shortName,
        blenderCameraName: camKey,
        entityId: camData.ha_camera_entity || '',
        mainStream: camData.stream_id || `${camKey.toLowerCase()}_main`,
        subStream: camData.sub_stream_id || camData.stream_id || `${camKey.toLowerCase()}_sub`,
        cameraIp: camData.camera_ip || '',
        coverageZone: camData.coverage_zone || 'outdoor',
        opticalModel: camData.optical_model || 'pinhole_radtan',
        cameraModel: camData.camera_model || '',
        lensMm: camData.lens_mm,
        mainStreamLabel: camData.main_stream_label || '',
        subStreamLabel: camData.sub_stream_label || '',
        fovH: camData.fov_h_deg,
        fovV: camData.fov_v_deg,
        aspectRatio: camData.aspect_ratio,
        isPanoramic180: camData.is_panoramic_180,
      });

      this.cameras.set(descriptor.id, descriptor);
      updated = true;
    }

    if (updated) {
      this._notify();
    }
    return this.getCameras();
  }

  registerCamera(descriptor) {
    const cam = descriptor instanceof CameraDescriptor ? descriptor : new CameraDescriptor(descriptor);
    this.cameras.set(cam.id, cam);
    this._notify();
    return cam;
  }

  getCameras() {
    return Array.from(this.cameras.values()).filter((c) => c.enabled);
  }

  getCameraById(cameraId) {
    return this.cameras.get(cameraId) || null;
  }

  findByStreamName(streamName) {
    if (!streamName) return null;
    for (const cam of this.cameras.values()) {
      if (cam.mainStream === streamName || cam.subStream === streamName || cam.id === streamName) {
        return cam;
      }
    }
    return null;
  }

  findByEntityId(entityId) {
    if (!entityId) return null;
    for (const cam of this.cameras.values()) {
      if (cam.entityId === entityId) {
        return cam;
      }
    }
    return null;
  }

  onChange(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  _notify() {
    const list = this.getCameras();
    this.listeners.forEach((fn) => {
      try {
        fn(list);
      } catch (err) {
        console.warn('[CameraCatalog] Errore listener:', err);
      }
    });
  }
}
