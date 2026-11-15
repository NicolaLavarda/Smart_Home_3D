import * as THREE from 'three';
import { CameraFrustumOverlay } from './calibration/CameraFrustumOverlay.js';

const CALIBRATION_STORAGE_PREFIX = 'sh3d_camera_calibration_v1_';

export class CameraProjector {
  constructor(scene, assetLoader) {
    this.scene = scene;
    this.assetLoader = assetLoader;

    this.raycaster = new THREE.Raycaster();
    this.frustumHelpers = new Map();
    this.frustumOverlays = new Map();
    this.frustumVolumes = new Map();
    this.baseCameraPoses = new Map();
    this.calibratedPoses = new Map();
    this.povActiveCameras = new Set();
    this.frustumsVisible = false; // Nascosto di default all'avvio su richiesta dell'utente
    this.groundColliders = [];
  }

  setGroundColliders(colliders) {
    this.groundColliders = colliders;
    console.log(`[CameraProjector] Ground colliders configurati: ${this.groundColliders.length}`);
  }

  setupCameraFrustums() {
    const cameras = this.assetLoader.cameras;
    const manifestCameras = this.assetLoader.manifest?.cameras || {};

    cameras.forEach((camNode, camName) => {
      const manifestData = manifestCameras[camName];
      // Mostra solo telecamere di sicurezza reali (Cam_Carraio o con ha_camera_entity definita)
      const isSecurityCam =
        camName === 'Cam_Carraio' ||
        Boolean(manifestData?.ha_camera_entity) ||
        manifestData?.is_real_security_camera === true;

      if (!isSecurityCam) return;

      camNode.updateMatrixWorld(true);
      const basePos = new THREE.Vector3();
      const baseQuat = new THREE.Quaternion();
      camNode.getWorldPosition(basePos);
      camNode.getWorldQuaternion(baseQuat);

      this.baseCameraPoses.set(camName, {
        position: basePos.clone(),
        quaternion: baseQuat.clone(),
        fovV: manifestData?.fov_v_deg || camNode.fov || 42.0,
        fovH: manifestData?.fov_h_deg || 80.0,
        aspect: manifestData?.aspect_ratio || camNode.aspect || 16 / 9,
        distortion: manifestData?.distortion_coeffs || [-0.18, 0.04, 0.0, 0.0, 0.0],
      });

      const frustumGroup = this.createFrustumCone(camNode, manifestData);
      frustumGroup.visible = this.frustumsVisible;
      this.scene.add(frustumGroup);
      this.frustumHelpers.set(camName, frustumGroup);

      // Ripristina eventuale calibrazione salvata in localStorage
      try {
        const saved = localStorage.getItem(`${CALIBRATION_STORAGE_PREFIX}${camName}`);
        if (saved) {
          this.applyCameraCalibration(camName, JSON.parse(saved));
        }
      } catch (e) {
        console.warn(`[CameraProjector] Errore lettura calibrazione salvata per ${camName}:`, e);
      }
    });

    console.log(`[CameraProjector] Frustum generati per ${this.frustumHelpers.size} telecamera reale.`);
  }

  createFrustumCone(camNode, manifestData) {
    const group = new THREE.Group();
    group.name = `Frustum_${camNode.name}`;

    const worldPos = new THREE.Vector3();
    const worldQuat = new THREE.Quaternion();
    camNode.getWorldPosition(worldPos);
    camNode.getWorldQuaternion(worldQuat);

    group.position.copy(worldPos);
    group.quaternion.copy(worldQuat);

    const fovV = manifestData?.fov_v_deg || camNode.fov || 42.0;
    const aspect = manifestData?.aspect_ratio || camNode.aspect || 16 / 9;
    const fovH =
      manifestData?.fov_h_deg ||
      2 * THREE.MathUtils.radToDeg(Math.atan(Math.tan(THREE.MathUtils.degToRad(fovV * 0.5)) * aspect));
    const depth = 16.0; // Copertura ottica fino a 16 metri su strada e ingressi

    const tanV = Math.tan(THREE.MathUtils.degToRad(fovV * 0.5));
    const tanH = Math.tan(THREE.MathUtils.degToRad(fovH * 0.5));
    const h = 2 * tanV * depth;
    const w = 2 * tanH * depth;

    const v0 = new THREE.Vector3(0, 0, 0);
    const v1 = new THREE.Vector3(-w / 2, h / 2, -depth);
    const v2 = new THREE.Vector3(w / 2, h / 2, -depth);
    const v3 = new THREE.Vector3(w / 2, -h / 2, -depth);
    const v4 = new THREE.Vector3(-w / 2, -h / 2, -depth);

    const geom = new THREE.BufferGeometry();
    const positions = [
      v0.x, v0.y, v0.z, v1.x, v1.y, v1.z, v2.x, v2.y, v2.z,
      v0.x, v0.y, v0.z, v2.x, v2.y, v2.z, v3.x, v3.y, v3.z,
      v0.x, v0.y, v0.z, v3.x, v3.y, v3.z, v4.x, v4.y, v4.z,
      v0.x, v0.y, v0.z, v4.x, v4.y, v4.z, v1.x, v1.y, v1.z,
      v1.x, v1.y, v1.z, v4.x, v4.y, v4.z, v2.x, v2.y, v2.z,
      v2.x, v2.y, v2.z, v4.x, v4.y, v4.z, v3.x, v3.y, v3.z,
    ];
    geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geom.computeVertexNormals();

    const mat = new THREE.MeshBasicMaterial({
      color: 0x06b6d4, // Cyan tech
      transparent: true,
      opacity: 0.18,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(geom, mat);
    group.add(mesh);

    const wireGeom = new THREE.BufferGeometry();
    const wirePositions = [
      v0.x, v0.y, v0.z, v1.x, v1.y, v1.z,
      v0.x, v0.y, v0.z, v2.x, v2.y, v2.z,
      v0.x, v0.y, v0.z, v3.x, v3.y, v3.z,
      v0.x, v0.y, v0.z, v4.x, v4.y, v4.z,
      v1.x, v1.y, v1.z, v2.x, v2.y, v2.z,
      v2.x, v2.y, v2.z, v3.x, v3.y, v3.z,
      v3.x, v3.y, v3.z, v4.x, v4.y, v4.z,
      v4.x, v4.y, v4.z, v1.x, v1.y, v1.z,
    ];
    wireGeom.setAttribute('position', new THREE.Float32BufferAttribute(wirePositions, 3));
    const wireMat = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.7,
      linewidth: 2,
    });
    const wireLines = new THREE.LineSegments(wireGeom, wireMat);
    group.add(wireLines);

    const overlay = new CameraFrustumOverlay(camNode.name, {
      fovV,
      fovH,
      aspect,
      distortion: manifestData?.distortion_coeffs || [-0.18, 0.04, 0, 0, 0],
    });
    group.add(overlay.mesh);

    this.frustumOverlays.set(camNode.name, overlay);
    this.frustumVolumes.set(camNode.name, { coneMesh: mesh, wireLines });

    return group;
  }

  syncGroupVisibility(camName) {
    const group = this.frustumHelpers.get(camName);
    const overlay = this.frustumOverlays.get(camName);
    const vol = this.frustumVolumes.get(camName);
    const isPov = this.povActiveCameras.has(camName);

    if (vol) {
      vol.coneMesh.visible = this.frustumsVisible && !isPov;
      vol.wireLines.visible = this.frustumsVisible && !isPov;
    }
    if (overlay) {
      overlay.setVisible(isPov || (this.frustumsVisible && Boolean(overlay.videoTexture)));
    }
    if (group) {
      group.visible = this.frustumsVisible || isPov;
    }
  }

  attachOverlayTexture(camName, videoTexture) {
    const overlay = this.frustumOverlays.get(camName);
    if (!overlay) return;
    overlay.attachVideoTexture(videoTexture);
    this.syncGroupVisibility(camName);
  }

  setOverlayPOVMode(camName, isPOV, opacity = 0.52) {
    const overlay = this.frustumOverlays.get(camName);
    if (!overlay) return;

    if (isPOV) {
      this.povActiveCameras.add(camName);
    } else {
      this.povActiveCameras.delete(camName);
    }

    overlay.setPOVMode(isPOV);
    if (opacity !== undefined) {
      overlay.setOpacity(opacity);
    }
    this.syncGroupVisibility(camName);
  }

  setOverlayOpacity(camName, opacity) {
    const overlay = this.frustumOverlays.get(camName);
    if (overlay) {
      overlay.setOpacity(opacity);
    }
  }

  applyCameraCalibration(camName, calibState) {
    const base = this.baseCameraPoses.get(camName);
    const group = this.frustumHelpers.get(camName);
    if (!base) return null;

    const finalPos = base.position.clone().add(
      new THREE.Vector3(
        Number(calibState.offsetX) || 0,
        Number(calibState.offsetY) || 0,
        Number(calibState.offsetZ) || 0
      )
    );

    const totalYawDeg = (Number(calibState.yawDeg) || 0) + (calibState.flip180 ? 180.0 : 0.0);
    const deltaEuler = new THREE.Euler(
      THREE.MathUtils.degToRad(Number(calibState.pitchDeg) || 0),
      THREE.MathUtils.degToRad(totalYawDeg),
      THREE.MathUtils.degToRad(Number(calibState.rollDeg) || 0),
      'YXZ'
    );
    const deltaQuat = new THREE.Quaternion().setFromEuler(deltaEuler);
    const finalQuat = base.quaternion.clone().multiply(deltaQuat);

    const fovV = Number(calibState.fovV) || base.fovV;
    const fovH = Number(calibState.fovH) || base.fovH;

    if (group) {
      group.position.copy(finalPos);
      group.quaternion.copy(finalQuat);
    }

    const overlay = this.frustumOverlays.get(camName);
    if (overlay) {
      overlay.updateOptics({
        fovV,
        fovH,
        distortion: [Number(calibState.k1) || 0, Number(calibState.k2) || 0, 0, 0, 0],
      });
    }

    const vol = this.frustumVolumes.get(camName);
    if (vol) {
      const depth = 16.0;
      const h = 2 * Math.tan(THREE.MathUtils.degToRad(fovV * 0.5)) * depth;
      const w = 2 * Math.tan(THREE.MathUtils.degToRad(fovH * 0.5)) * depth;
      const v0 = [0, 0, 0];
      const v1 = [-w / 2, h / 2, -depth];
      const v2 = [w / 2, h / 2, -depth];
      const v3 = [w / 2, -h / 2, -depth];
      const v4 = [-w / 2, -h / 2, -depth];

      vol.coneMesh.geometry.setAttribute(
        'position',
        new THREE.Float32BufferAttribute(
          [
            ...v0, ...v1, ...v2,
            ...v0, ...v2, ...v3,
            ...v0, ...v3, ...v4,
            ...v0, ...v4, ...v1,
            ...v1, ...v4, ...v2,
            ...v2, ...v4, ...v3,
          ],
          3
        )
      );
      vol.coneMesh.geometry.computeVertexNormals();

      vol.wireLines.geometry.setAttribute(
        'position',
        new THREE.Float32BufferAttribute(
          [
            ...v0, ...v1,
            ...v0, ...v2,
            ...v0, ...v3,
            ...v0, ...v4,
            ...v1, ...v2,
            ...v2, ...v3,
            ...v3, ...v4,
            ...v4, ...v1,
          ],
          3
        )
      );
    }

    const camNode = this.assetLoader.cameras.get(camName);
    if (camNode) {
      if (camNode.parent) {
        camNode.parent.updateMatrixWorld(true);
        const invParent = camNode.parent.matrixWorld.clone().invert();
        const worldMat = new THREE.Matrix4().compose(finalPos, finalQuat, new THREE.Vector3(1, 1, 1));
        const localMat = invParent.multiply(worldMat);
        localMat.decompose(camNode.position, camNode.quaternion, new THREE.Vector3());
      } else {
        camNode.position.copy(finalPos);
        camNode.quaternion.copy(finalQuat);
      }
      if (camNode.isPerspectiveCamera) {
        camNode.fov = fovV;
        camNode.updateProjectionMatrix();
      }
      camNode.updateMatrixWorld(true);
    }

    const worldMat4 = new THREE.Matrix4().compose(finalPos, finalQuat, new THREE.Vector3(1, 1, 1));
    const matrixWorldElements = Array.from(worldMat4.clone().transpose().elements);

    const result = {
      position: finalPos,
      quaternion: finalQuat,
      fovV,
      fovH,
      matrixWorldElements,
    };
    this.calibratedPoses.set(camName, result);
    return result;
  }

  getCalibratedCameraPose(camName) {
    return this.calibratedPoses.get(camName) || this.baseCameraPoses.get(camName) || null;
  }

  toggleFrustums(visible) {
    this.frustumsVisible = visible !== undefined ? visible : !this.frustumsVisible;
    this.frustumHelpers.forEach((_, camName) => {
      this.syncGroupVisibility(camName);
    });
    return this.frustumsVisible;
  }

  projectDetectionToGround(cameraName, uvBottomCenter) {
    // Se la camera richiesta non esiste o è una vecchia camera, usa Cam_Carraio
    let camNode = this.assetLoader.cameras.get(cameraName) || this.assetLoader.cameras.get('Cam_Carraio');
    if (!camNode) {
      console.warn(`[CameraProjector] Camera '${cameraName}' non trovata.`);
      return { hit: false, point: new THREE.Vector3(0, 0, 0), groundMesh: null };
    }

    const u = Array.isArray(uvBottomCenter) ? uvBottomCenter[0] : uvBottomCenter.u;
    const v = Array.isArray(uvBottomCenter) ? uvBottomCenter[1] : uvBottomCenter.v;

    const ndcX = u * 2.0 - 1.0;
    const ndcY = 1.0 - v * 2.0;

    this.raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camNode);

    const colliders = this.groundColliders.length > 0 ? this.groundColliders : this.assetLoader.groundColliders;
    const intersects = this.raycaster.intersectObjects(colliders, false);

    if (intersects.length > 0) {
      const topHit = intersects[0];
      return {
        hit: true,
        point: topHit.point.clone(),
        groundMesh: topHit.object.name,
        distance: topHit.distance,
      };
    }

    const ray = this.raycaster.ray;
    if (Math.abs(ray.direction.y) > 0.001) {
      const t = (0.05 - ray.origin.y) / ray.direction.y;
      if (t > 0) {
        const fallbackPoint = ray.origin.clone().add(ray.direction.clone().multiplyScalar(t));
        return {
          hit: true,
          point: fallbackPoint,
          groundMesh: 'Ground_Plane_Fallback',
          distance: t,
        };
      }
    }

    return { hit: false, point: new THREE.Vector3(0, 0, 0), groundMesh: null };
  }
}
