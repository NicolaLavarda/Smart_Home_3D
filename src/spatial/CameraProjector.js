import * as THREE from 'three';

export class CameraProjector {
  constructor(scene, assetLoader) {
    this.scene = scene;
    this.assetLoader = assetLoader;

    this.raycaster = new THREE.Raycaster();
    this.frustumHelpers = new Map();
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
      const isSecurityCam = camName === 'Cam_Carraio' || manifestData?.ha_camera_entity !== '';

      if (!isSecurityCam) return;

      const frustumGroup = this.createFrustumCone(camNode, manifestData);
      frustumGroup.visible = this.frustumsVisible;
      this.scene.add(frustumGroup);
      this.frustumHelpers.set(camName, frustumGroup);
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

    const fov = camNode.fov || manifestData?.fov_v_deg || 55;
    const aspect = camNode.aspect || manifestData?.aspect_ratio || 1.777;
    const depth = 16.0; // Copertura ottica fino a 16 metri su strada e ingressi

    const h = 2 * Math.tan(THREE.MathUtils.degToRad(fov / 2)) * depth;
    const w = h * aspect;

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

    return group;
  }

  toggleFrustums(visible) {
    this.frustumsVisible = visible !== undefined ? visible : !this.frustumsVisible;
    this.frustumHelpers.forEach((group) => {
      group.visible = this.frustumsVisible;
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
