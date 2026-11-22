import * as THREE from 'three';
import { CameraFrustumOverlay } from './calibration/CameraFrustumOverlay.js';

const CALIBRATION_STORAGE_PREFIX = 'sh3d_camera_calibration_v2_';
export const FRUSTUM_DEPTH = 16.0; // Copertura ottica fino a 16 metri su strada e ingressi
export const GROUND_CLIP_Y = 0.015; // Piano terra (z=0 in Blender -> y=0 in Three.js) con leggero offset anti z-fighting
const GROUND_EPS = 1e-5;

function resolveFovH(fovV, aspect, explicitFovH) {
  if (explicitFovH) return Number(explicitFovH);
  const tanV = Math.tan(THREE.MathUtils.degToRad(fovV * 0.5));
  return 2 * THREE.MathUtils.radToDeg(Math.atan(tanV * aspect));
}

function isOnGround(point, groundY) {
  return Math.abs(point.y - groundY) <= GROUND_EPS;
}

function edgeKey(a, b) {
  const ka = `${a.x.toFixed(4)},${a.y.toFixed(4)},${a.z.toFixed(4)}`;
  const kb = `${b.x.toFixed(4)},${b.y.toFixed(4)},${b.z.toFixed(4)}`;
  return ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
}

/**
 * Taglia un poligono convesso 3D sul semispazio y >= groundY (Sutherland-Hodgman).
 */
function clipPolygonAboveY(poly, groundY) {
  if (!poly || poly.length < 3) return [];

  const isInside = (p) => p.y >= groundY - GROUND_EPS;
  const intersect = (a, b) => {
    const dy = b.y - a.y;
    if (Math.abs(dy) < 1e-9) {
      return new THREE.Vector3(a.x, groundY, a.z);
    }
    const t = THREE.MathUtils.clamp((groundY - a.y) / dy, 0, 1);
    return new THREE.Vector3(
      a.x + (b.x - a.x) * t,
      groundY,
      a.z + (b.z - a.z) * t
    );
  };

  const out = [];
  for (let i = 0; i < poly.length; i++) {
    const curr = poly[i];
    const next = poly[(i + 1) % poly.length];
    const currIn = isInside(curr);
    const nextIn = isInside(next);

    if (currIn && nextIn) {
      const p = next.clone();
      if (isOnGround(p, groundY)) p.y = groundY;
      out.push(p);
    } else if (currIn && !nextIn) {
      out.push(intersect(curr, next));
    } else if (!currIn && nextIn) {
      out.push(intersect(curr, next));
      const p = next.clone();
      if (isOnGround(p, groundY)) p.y = groundY;
      out.push(p);
    }
  }

  const deduped = [];
  for (const pt of out) {
    if (deduped.length === 0 || deduped[deduped.length - 1].distanceToSquared(pt) > 1e-8) {
      deduped.push(pt);
    }
  }
  if (deduped.length >= 2 && deduped[0].distanceToSquared(deduped[deduped.length - 1]) <= 1e-8) {
    deduped.pop();
  }
  return deduped.length >= 3 ? deduped : [];
}

/**
 * Calcola la geometria del frustum tagliata al piano ground (y >= groundY)
 * e la relativa impronta di proiezione a terra (anche fuori dai confini delle mesh del modello).
 * Tutte le posizioni restituite sono nello spazio locale di (worldPos, worldQuat).
 */
export function computeClippedFrustumData(
  worldPos,
  worldQuat,
  fovV,
  fovH,
  depth = FRUSTUM_DEPTH,
  groundY = GROUND_CLIP_Y
) {
  const toWorld = (lx, ly, lz) =>
    new THREE.Vector3(lx, ly, lz).applyQuaternion(worldQuat).add(worldPos);

  const v0 = worldPos.clone();
  const isPanoramic = Number(fovH) >= 150;
  let faces = [];
  const panoSliceGround = [];

  if (isPanoramic) {
    // Ventaglio panoramico 180° (es. Reolink Duo 3 PoE): discretizza l'arco sferico senza singolarità tan(90°)
    const segments = 24;
    const clampedFovH = Math.min(Math.max(Number(fovH) || 180, 150), 350);
    const clampedFovV = Math.min(Math.max(Number(fovV) || 55, 10), 160);
    const halfHRad = THREE.MathUtils.degToRad(clampedFovH * 0.5);
    const halfVRad = THREE.MathUtils.degToRad(clampedFovV * 0.5);
    const cosV = Math.cos(halfVRad);
    const sinV = Math.sin(halfVRad);

    const intersectSegGround = (a, b) => {
      const dy = b.y - a.y;
      if (Math.abs(dy) < 1e-9) return null;
      const t = (groundY - a.y) / dy;
      if (t < -1e-6 || t > 1 + 1e-6) return null;
      const tc = THREE.MathUtils.clamp(t, 0, 1);
      return new THREE.Vector3(
        a.x + (b.x - a.x) * tc,
        groundY,
        a.z + (b.z - a.z) * tc
      );
    };

    const topPts = [];
    const botPts = [];
    for (let i = 0; i <= segments; i++) {
      const th = -halfHRad + (i / segments) * (2.0 * halfHRad);
      const sx = depth * cosV * Math.sin(th);
      const sz = -depth * cosV * Math.cos(th);
      const tPt = toWorld(sx, depth * sinV, sz);
      const bPt = toWorld(sx, -depth * sinV, sz);
      topPts.push(tPt);
      botPts.push(bPt);

      // Intersezione della fetta verticale [v0, tPt, bPt] col piano ground (evita poligoni non convessi a mezzaluna)
      const hits = [];
      for (const [ea, eb] of [[v0, bPt], [v0, tPt], [tPt, bPt]]) {
        const hit = intersectSegGround(ea, eb);
        if (hit && !hits.some((h) => h.distanceToSquared(hit) <= 1e-8)) {
          hits.push(hit);
        }
      }
      if (hits.length >= 2) {
        hits.sort((p1, p2) => p1.distanceToSquared(v0) - p2.distanceToSquared(v0));
        panoSliceGround.push({ near: hits[0], far: hits[hits.length - 1] });
      } else {
        panoSliceGround.push(null);
      }
    }

    for (let i = 0; i < segments; i++) {
      faces.push([v0, topPts[i], topPts[i + 1]]);
      faces.push([v0, botPts[i + 1], botPts[i]]);
      faces.push([topPts[i], botPts[i], botPts[i + 1], topPts[i + 1]]);
    }
    faces.push([v0, botPts[0], topPts[0]]);
    faces.push([v0, topPts[segments], botPts[segments]]);
  } else {
    const tanV = Math.tan(THREE.MathUtils.degToRad(fovV * 0.5));
    const tanH = Math.tan(THREE.MathUtils.degToRad(fovH * 0.5));
    const halfH = tanV * depth;
    const halfW = tanH * depth;

    const v1 = toWorld(-halfW, halfH, -depth);
    const v2 = toWorld(halfW, halfH, -depth);
    const v3 = toWorld(halfW, -halfH, -depth);
    const v4 = toWorld(-halfW, -halfH, -depth);

    faces = [
      [v0, v1, v2],
      [v0, v2, v3],
      [v0, v3, v4],
      [v0, v4, v1],
      [v1, v4, v3, v2],
    ];
  }

  const coneWorldPts = [];
  const clippedEdgeMap = new Map();
  const rawGroundPts = [];

  for (const face of faces) {
    const clipped = clipPolygonAboveY(face, groundY);
    if (clipped.length < 3) continue;

    const allOnGround = clipped.every((p) => isOnGround(p, groundY));
    if (allOnGround) {
      rawGroundPts.push(...clipped);
      continue;
    }

    for (let i = 1; i < clipped.length - 1; i++) {
      coneWorldPts.push(clipped[0], clipped[i], clipped[i + 1]);
    }

    for (let i = 0; i < clipped.length; i++) {
      const a = clipped[i];
      const b = clipped[(i + 1) % clipped.length];
      if (isOnGround(a, groundY)) rawGroundPts.push(a);
      if (isOnGround(b, groundY)) rawGroundPts.push(b);

      const key = edgeKey(a, b);
      if (!clippedEdgeMap.has(key)) {
        clippedEdgeMap.set(key, [a, b]);
      }
    }
  }

  let groundPolygon = [];
  const groundWorldPts = [];
  const groundLineWorldPts = [];

  if (isPanoramic) {
    // Costruisce l'impronta a terra a mezzaluna/ventaglio per fette convesse senza auto-intersezioni
    const validSlices = [];
    for (let i = 0; i < panoSliceGround.length; i++) {
      if (panoSliceGround[i]) validSlices.push(panoSliceGround[i]);
    }
    for (let i = 0; i < panoSliceGround.length - 1; i++) {
      const s0 = panoSliceGround[i];
      const s1 = panoSliceGround[i + 1];
      if (!s0 || !s1) continue;
      groundWorldPts.push(s0.near, s0.far, s1.far);
      groundWorldPts.push(s0.near, s1.far, s1.near);
    }
    if (validSlices.length >= 2) {
      const outerArc = validSlices.map((s) => s.far);
      const innerArcRev = validSlices.slice().reverse().map((s) => s.near);
      const perim = [...outerArc, ...innerArcRev];
      for (const pt of perim) {
        if (groundPolygon.length === 0 || groundPolygon[groundPolygon.length - 1].distanceToSquared(pt) > 1e-8) {
          groundPolygon.push(pt);
        }
      }
      if (groundPolygon.length >= 2 && groundPolygon[0].distanceToSquared(groundPolygon[groundPolygon.length - 1]) <= 1e-8) {
        groundPolygon.pop();
      }
      if (groundPolygon.length >= 3) {
        for (let i = 0; i < groundPolygon.length; i++) {
          groundLineWorldPts.push(groundPolygon[i], groundPolygon[(i + 1) % groundPolygon.length]);
        }
      } else {
        groundPolygon = [];
      }
    }
  } else {
    // Deduplica i punti d'intersezione col piano ground e ordina il poligono convesso in XZ
    const uniqueGroundPts = [];
    for (const pt of rawGroundPts) {
      if (!uniqueGroundPts.some((existing) => existing.distanceToSquared(pt) <= 1e-8)) {
        uniqueGroundPts.push(new THREE.Vector3(pt.x, groundY, pt.z));
      }
    }

    if (uniqueGroundPts.length >= 3) {
      let cx = 0;
      let cz = 0;
      for (const p of uniqueGroundPts) {
        cx += p.x;
        cz += p.z;
      }
      cx /= uniqueGroundPts.length;
      cz /= uniqueGroundPts.length;

      uniqueGroundPts.sort(
        (a, b) => Math.atan2(a.z - cz, a.x - cx) - Math.atan2(b.z - cz, b.x - cx)
      );

      let area2 = 0;
      for (let i = 0; i < uniqueGroundPts.length; i++) {
        const p1 = uniqueGroundPts[i];
        const p2 = uniqueGroundPts[(i + 1) % uniqueGroundPts.length];
        area2 += p1.x * p2.z - p2.x * p1.z;
      }
      if (Math.abs(area2) * 0.5 > 1e-4) {
        groundPolygon = uniqueGroundPts;
        for (let i = 1; i < groundPolygon.length - 1; i++) {
          groundWorldPts.push(groundPolygon[0], groundPolygon[i], groundPolygon[i + 1]);
        }
        for (let i = 0; i < groundPolygon.length; i++) {
          groundLineWorldPts.push(groundPolygon[i], groundPolygon[(i + 1) % groundPolygon.length]);
        }
      }
    }
  }

  const hasGroundProjection = groundPolygon.length >= 3;
  const wireWorldPts = [];
  for (const [a, b] of clippedEdgeMap.values()) {
    if (hasGroundProjection && isOnGround(a, groundY) && isOnGround(b, groundY)) {
      continue; // Il perimetro a terra viene disegnato da groundLines
    }
    wireWorldPts.push(a, b);
  }

  const worldMat = new THREE.Matrix4().compose(worldPos, worldQuat, new THREE.Vector3(1, 1, 1));
  const invWorldMat = worldMat.clone().invert();

  const toLocalBuffer = (points) => {
    const arr = new Float32Array(points.length * 3);
    const tmp = new THREE.Vector3();
    for (let i = 0; i < points.length; i++) {
      tmp.copy(points[i]).applyMatrix4(invWorldMat);
      arr[i * 3] = tmp.x;
      arr[i * 3 + 1] = tmp.y;
      arr[i * 3 + 2] = tmp.z;
    }
    return arr;
  };

  return {
    conePositions: toLocalBuffer(coneWorldPts),
    wirePositions: toLocalBuffer(wireWorldPts),
    groundPositions: toLocalBuffer(groundWorldPts),
    groundLinePositions: toLocalBuffer(groundLineWorldPts),
    groundPolygonWorld: groundPolygon,
  };
}

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

      const fovV = manifestData?.fov_v_deg || camNode.fov || 42.0;
      const aspect = manifestData?.aspect_ratio || camNode.aspect || 16 / 9;
      const fovH = resolveFovH(fovV, aspect, manifestData?.fov_h_deg);

      this.baseCameraPoses.set(camName, {
        position: basePos.clone(),
        quaternion: baseQuat.clone(),
        fovV,
        fovH,
        aspect,
        opticalModel: manifestData?.optical_model || 'pinhole_radtan',
        distortion: manifestData?.distortion_coeffs || [-0.18, 0.04, 0.0, 0.0, 0.0],
      });

      const frustumGroup = this.createFrustumCone(camNode, manifestData);
      this.scene.add(frustumGroup);
      this.frustumHelpers.set(camName, frustumGroup);
      this.syncGroupVisibility(camName);

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
    const fovH = resolveFovH(fovV, aspect, manifestData?.fov_h_deg);

    const geom = new THREE.BufferGeometry();
    const mat = new THREE.MeshBasicMaterial({
      color: 0x06b6d4, // Cyan tech
      transparent: true,
      opacity: 0.14,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(geom, mat);
    mesh.name = `FrustumCone_${camNode.name}`;
    mesh.renderOrder = 3;
    group.add(mesh);

    const wireGeom = new THREE.BufferGeometry();
    const wireMat = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.65,
    });
    const wireLines = new THREE.LineSegments(wireGeom, wireMat);
    wireLines.name = `FrustumWire_${camNode.name}`;
    wireLines.renderOrder = 4;
    group.add(wireLines);

    const groundGeom = new THREE.BufferGeometry();
    const groundMat = new THREE.MeshBasicMaterial({
      color: 0x06b6d4,
      transparent: true,
      opacity: 0.25,
      side: THREE.DoubleSide,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -1,
      polygonOffsetUnits: -1,
    });
    const groundMesh = new THREE.Mesh(groundGeom, groundMat);
    groundMesh.name = `FrustumGround_${camNode.name}`;
    groundMesh.renderOrder = 2;
    group.add(groundMesh);

    const groundLineGeom = new THREE.BufferGeometry();
    const groundLineMat = new THREE.LineBasicMaterial({
      color: 0x22d3ee,
      transparent: true,
      opacity: 0.95,
    });
    const groundLines = new THREE.LineSegments(groundLineGeom, groundLineMat);
    groundLines.name = `FrustumGroundOutline_${camNode.name}`;
    groundLines.renderOrder = 4;
    group.add(groundLines);

    const overlay = new CameraFrustumOverlay(camNode.name, {
      fovV,
      fovH,
      aspect,
      opticalModel: manifestData?.optical_model || 'pinhole_radtan',
      distortion: manifestData?.distortion_coeffs || [-0.18, 0.04, 0, 0, 0],
    });
    group.add(overlay.mesh);

    this.frustumOverlays.set(camNode.name, overlay);
    this.frustumVolumes.set(camNode.name, {
      coneMesh: mesh,
      wireLines,
      groundMesh,
      groundLines,
      hasConeGeometry: false,
      hasWireGeometry: false,
      hasGroundProjection: false,
    });

    this.updateFrustumVolumeGeometry(camNode.name, worldPos, worldQuat, fovV, fovH, FRUSTUM_DEPTH);

    return group;
  }

  updateFrustumVolumeGeometry(camName, worldPos, worldQuat, fovV, fovH, depth = FRUSTUM_DEPTH) {
    const vol = this.frustumVolumes.get(camName);
    if (!vol) return;

    const {
      conePositions,
      wirePositions,
      groundPositions,
      groundLinePositions,
    } = computeClippedFrustumData(worldPos, worldQuat, fovV, fovH, depth, GROUND_CLIP_Y);

    vol.coneMesh.geometry.setAttribute('position', new THREE.Float32BufferAttribute(conePositions, 3));
    if (conePositions.length > 0) {
      vol.coneMesh.geometry.computeVertexNormals();
      vol.coneMesh.geometry.computeBoundingSphere();
    }

    vol.wireLines.geometry.setAttribute('position', new THREE.Float32BufferAttribute(wirePositions, 3));
    if (wirePositions.length > 0) {
      vol.wireLines.geometry.computeBoundingSphere();
    }

    vol.groundMesh.geometry.setAttribute('position', new THREE.Float32BufferAttribute(groundPositions, 3));
    if (groundPositions.length > 0) {
      vol.groundMesh.geometry.computeVertexNormals();
      vol.groundMesh.geometry.computeBoundingSphere();
    }

    vol.groundLines.geometry.setAttribute('position', new THREE.Float32BufferAttribute(groundLinePositions, 3));
    if (groundLinePositions.length > 0) {
      vol.groundLines.geometry.computeBoundingSphere();
    }

    vol.hasConeGeometry = conePositions.length > 0;
    vol.hasWireGeometry = wirePositions.length > 0;
    vol.hasGroundProjection = groundPositions.length > 0;
    this.syncGroupVisibility(camName);
  }

  syncGroupVisibility(camName) {
    const group = this.frustumHelpers.get(camName);
    const overlay = this.frustumOverlays.get(camName);
    const vol = this.frustumVolumes.get(camName);
    const isPov = this.povActiveCameras.has(camName);

    if (vol) {
      const showVolume = this.frustumsVisible && !isPov;
      vol.coneMesh.visible = showVolume && vol.hasConeGeometry;
      vol.wireLines.visible = showVolume && vol.hasWireGeometry;
      vol.groundMesh.visible = showVolume && vol.hasGroundProjection;
      vol.groundLines.visible = showVolume && vol.hasGroundProjection;
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

  detachOverlayTexture(camName) {
    const overlay = this.frustumOverlays.get(camName);
    if (!overlay) return;
    overlay.attachVideoTexture(null);
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

    this.updateFrustumVolumeGeometry(camName, finalPos, finalQuat, fovV, fovH, FRUSTUM_DEPTH);

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

  getBaseCameraPose(camName) {
    return this.baseCameraPoses.get(camName) || null;
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

    const basePose = this.baseCameraPoses.get(cameraName);
    const calibrated = this.calibratedPoses.get(cameraName);
    const opticalModel = String(basePose?.opticalModel || '').toLowerCase();
    const fovH = calibrated?.fovH ?? basePose?.fovH ?? 80;
    const fovV = calibrated?.fovV ?? basePose?.fovV ?? 42;

    if (opticalModel.includes('equirectangular') || opticalModel.includes('panoramic') || fovH >= 150) {
      camNode.updateMatrixWorld(true);
      const origin = new THREE.Vector3();
      const quat = new THREE.Quaternion();
      camNode.getWorldPosition(origin);
      camNode.getWorldQuaternion(quat);

      const theta = THREE.MathUtils.degToRad((u - 0.5) * fovH);
      const phi = THREE.MathUtils.degToRad((v - 0.5) * fovV);
      const cosPhi = Math.cos(phi);
      // Coerente con EquirectangularPanoramicOpticalModel (+X right, +Y up, -Z forward in Three.js)
      const dirLocal = new THREE.Vector3(
        cosPhi * Math.sin(theta),
        -Math.sin(phi),
        -cosPhi * Math.cos(theta)
      ).normalize();
      const dirWorld = dirLocal.applyQuaternion(quat).normalize();
      this.raycaster.set(origin, dirWorld);
    } else {
      const ndcX = u * 2.0 - 1.0;
      const ndcY = 1.0 - v * 2.0;
      this.raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camNode);
    }

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
