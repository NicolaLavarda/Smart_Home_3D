import * as THREE from 'three';
import { CameraFrustumOverlay } from './calibration/CameraFrustumOverlay.js';
import { decomposeWorldMatrixToCalibState } from './calibration/PnPSolver.js';

export const CALIBRATION_STORAGE_PREFIX = 'sh3d_camera_calibration_v2_';
export const FRUSTUM_DEPTH = 16.0; // Copertura ottica fino a 16 metri su strada e ingressi
export const GROUND_CLIP_Y = 0.015; // Piano terra (z=0 in Blender -> y=0 in Three.js) con leggero offset anti z-fighting
export const FRUSTUM_MODES = ['off', '3d', '2d'];
export const MAX_CALIBRATION_POS_OFFSET_M = 2.2;
const GROUND_EPS = 1e-5;
const RAY_NEAR = 0.15;
const CURTAIN_JUMP_THRESHOLD = 0.8;

function intersectRayAABB(ox, oy, oz, dx, dy, dz, box, tMin, tMax) {
  let t0 = tMin;
  let t1 = tMax;

  if (Math.abs(dx) < 1e-9) {
    if (ox < box.minX || ox > box.maxX) return Infinity;
  } else {
    const inv = 1.0 / dx;
    let a = (box.minX - ox) * inv;
    let b = (box.maxX - ox) * inv;
    if (a > b) { const tmp = a; a = b; b = tmp; }
    if (a > t0) t0 = a;
    if (b < t1) t1 = b;
    if (t0 > t1) return Infinity;
  }

  if (Math.abs(dy) < 1e-9) {
    if (oy < box.minY || oy > box.maxY) return Infinity;
  } else {
    const inv = 1.0 / dy;
    let a = (box.minY - oy) * inv;
    let b = (box.maxY - oy) * inv;
    if (a > b) { const tmp = a; a = b; b = tmp; }
    if (a > t0) t0 = a;
    if (b < t1) t1 = b;
    if (t0 > t1) return Infinity;
  }

  if (Math.abs(dz) < 1e-9) {
    if (oz < box.minZ || oz > box.maxZ) return Infinity;
  } else {
    const inv = 1.0 / dz;
    let a = (box.minZ - oz) * inv;
    let b = (box.maxZ - oz) * inv;
    if (a > b) { const tmp = a; a = b; b = tmp; }
    if (a > t0) t0 = a;
    if (b < t1) t1 = b;
    if (t0 > t1) return Infinity;
  }

  return t0 >= tMin && t0 <= tMax ? t0 : Infinity;
}

function castRayObstacles(ox, oy, oz, dx, dy, dz, tMin, tMax, boxes) {
  let bestT = tMax;
  let hit = false;
  for (let i = 0; i < boxes.length; i++) {
    const t = intersectRayAABB(ox, oy, oz, dx, dy, dz, boxes[i], tMin, bestT);
    if (t < bestT) {
      bestT = t;
      hit = true;
    }
  }
  return hit ? bestT : Infinity;
}

function hasAnyObstacleHit(ox, oy, oz, dx, dy, dz, tMin, tMax, boxes) {
  for (let i = 0; i < boxes.length; i++) {
    if (intersectRayAABB(ox, oy, oz, dx, dy, dz, boxes[i], tMin, tMax) < Infinity) {
      return true;
    }
  }
  return false;
}

function filterNearbyOccluders(worldPos, maxRadius, occluders) {
  const pad = maxRadius + 1.0;
  const minX = worldPos.x - pad;
  const maxX = worldPos.x + pad;
  const minY = worldPos.y - pad;
  const maxY = worldPos.y + pad;
  const minZ = worldPos.z - pad;
  const maxZ = worldPos.z + pad;
  const local = [];
  for (let i = 0; i < occluders.length; i++) {
    const b = occluders[i];
    if (
      b.maxX >= minX && b.minX <= maxX &&
      b.maxY >= minY && b.minY <= maxY &&
      b.maxZ >= minZ && b.minZ <= maxZ
    ) {
      local.push(b);
    }
  }
  return local;
}

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
 * e la relativa impronta di proiezione a terra, con raycasting contro eventuali ostacoli AABB.
 * Tutte le posizioni restituite sono nello spazio locale di (worldPos, worldQuat).
 */
export function computeClippedFrustumData(
  worldPos,
  worldQuat,
  fovV,
  fovH,
  depth = FRUSTUM_DEPTH,
  groundY = GROUND_CLIP_Y,
  occluders = null
) {
  const hasOccluders = Array.isArray(occluders) && occluders.length > 0;
  const isPanoramic = Number(fovH) >= 150;

  if (hasOccluders) {
    return computeOccludedFrustumData(worldPos, worldQuat, fovV, fovH, depth, groundY, occluders, isPanoramic);
  }

  const toWorld = (lx, ly, lz) =>
    new THREE.Vector3(lx, ly, lz).applyQuaternion(worldQuat).add(worldPos);

  const v0 = worldPos.clone();
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

function buildAngularSamples(baseCount, worldPos, invWorldQuat, isPanoramic, halfHRad, tanH, localBoxes) {
  const samples = [];
  for (let i = 0; i <= baseCount; i++) {
    samples.push(i / baseCount);
  }

  if (localBoxes && localBoxes.length > 0) {
    const corner = new THREE.Vector3();
    const eps = 1e-4;
    for (let i = 0; i < localBoxes.length; i++) {
      const b = localBoxes[i];
      const xs = [b.minX, b.maxX];
      const zs = [b.minZ, b.maxZ];
      for (let xi = 0; xi < 2; xi++) {
        for (let zi = 0; zi < 2; zi++) {
          corner.set(xs[xi] - worldPos.x, 0, zs[zi] - worldPos.z).applyQuaternion(invWorldQuat);
          let uCorner;
          if (isPanoramic) {
            const theta = Math.atan2(corner.x, -corner.z);
            uCorner = 0.5 + theta / (2.0 * halfHRad);
          } else {
            if (corner.z >= -1e-4) continue;
            uCorner = 0.5 + (corner.x / -corner.z) / (2.0 * tanH);
          }
          if (uCorner > 2.0 * eps && uCorner < 1.0 - 2.0 * eps) {
            samples.push(uCorner - eps, uCorner + eps);
          }
        }
      }
    }
  }

  samples.sort((a, b) => a - b);
  const deduped = [samples[0]];
  for (let i = 1; i < samples.length; i++) {
    if (samples[i] - deduped[deduped.length - 1] > 2e-5) {
      deduped.push(samples[i]);
    }
  }
  return deduped;
}

function subtractIntervals(t0, t1, overlaps) {
  if (!overlaps || overlaps.length === 0) {
    return t1 - t0 > 1e-4 ? [[t0, t1]] : [];
  }
  const sorted = overlaps.slice().sort((a, b) => a[0] - b[0]);
  const out = [];
  let cursor = t0;
  for (let i = 0; i < sorted.length; i++) {
    const [o0, o1] = sorted[i];
    if (o0 > cursor + 1e-4) {
      out.push([cursor, Math.min(t1, o0)]);
    }
    if (o1 > cursor) {
      cursor = o1;
    }
  }
  if (t1 > cursor + 1e-4) {
    out.push([cursor, t1]);
  }
  return out;
}

function computeOccludedFrustumData(
  worldPos,
  worldQuat,
  fovV,
  fovH,
  depth,
  groundY,
  occluders,
  isPanoramic
) {
  const v0 = worldPos.clone();
  const invWorldQuat = worldQuat.clone().invert();
  const localBoxes = filterNearbyOccluders(worldPos, depth * 1.5, occluders);

  const clampedFovH = isPanoramic
    ? Math.min(Math.max(Number(fovH) || 180, 150), 350)
    : Math.max(1, Number(fovH) || 80);
  const clampedFovV = isPanoramic
    ? Math.min(Math.max(Number(fovV) || 55, 10), 160)
    : Math.max(1, Number(fovV) || 42);

  const halfHRad = THREE.MathUtils.degToRad(clampedFovH * 0.5);
  const halfVRad = THREE.MathUtils.degToRad(clampedFovV * 0.5);
  const tanH = Math.tan(halfHRad);
  const tanV = Math.tan(halfVRad);

  const sampleRay = (u, v) => {
    const dir = new THREE.Vector3();
    let maxDist;
    if (isPanoramic) {
      const th = (u * 2.0 - 1.0) * halfHRad;
      const ph = (v * 2.0 - 1.0) * halfVRad;
      const cosPh = Math.cos(ph);
      dir.set(cosPh * Math.sin(th), Math.sin(ph), -cosPh * Math.cos(th));
      maxDist = depth;
    } else {
      const lx = (u * 2.0 - 1.0) * tanH;
      const ly = (v * 2.0 - 1.0) * tanV;
      const len = Math.hypot(lx, ly, 1.0);
      dir.set(lx / len, ly / len, -1.0 / len);
      maxDist = depth * len;
    }
    dir.applyQuaternion(worldQuat).normalize();
    return { dir, maxDist };
  };

  // 1. Volume 3D con campionamento ad alta densità + raggi iniettati sugli spigoli dei muri
  const u3d = buildAngularSamples(
    isPanoramic ? 180 : 96,
    worldPos,
    invWorldQuat,
    isPanoramic,
    halfHRad,
    tanH,
    localBoxes
  );
  const cols3d = u3d.length - 1;
  const rows = 12;
  const gridPts = Array.from({ length: cols3d + 1 }, () => new Array(rows + 1));
  const gridDist = Array.from({ length: cols3d + 1 }, () => new Float32Array(rows + 1));

  for (let i = 0; i <= cols3d; i++) {
    const u = u3d[i];
    for (let j = 0; j <= rows; j++) {
      const v = j / rows;
      const { dir, maxDist } = sampleRay(u, v);
      const tGround =
        dir.y < -1e-6 && worldPos.y > groundY
          ? (groundY - worldPos.y) / dir.y
          : (worldPos.y <= groundY && dir.y < 0 ? 0 : Infinity);
      const tLimit = Math.min(maxDist, tGround);
      const tObs =
        tLimit > RAY_NEAR && localBoxes.length > 0
          ? castRayObstacles(v0.x, v0.y, v0.z, dir.x, dir.y, dir.z, RAY_NEAR, tLimit, localBoxes)
          : Infinity;
      const tFinal = Math.min(tLimit, tObs);
      const pt = new THREE.Vector3(
        v0.x + dir.x * tFinal,
        v0.y + dir.y * tFinal,
        v0.z + dir.z * tFinal
      );
      if (tFinal === tGround && Number.isFinite(tGround)) {
        pt.y = groundY;
      }
      gridPts[i][j] = pt;
      gridDist[i][j] = tFinal;
    }
  }

  const coneWorldPts = [];
  const wireWorldPts = [];

  for (let i = 0; i < cols3d; i++) {
    coneWorldPts.push(v0, gridPts[i][rows], gridPts[i + 1][rows]);
    coneWorldPts.push(v0, gridPts[i + 1][0], gridPts[i][0]);
  }
  for (let j = 0; j < rows; j++) {
    coneWorldPts.push(v0, gridPts[0][j], gridPts[0][j + 1]);
    coneWorldPts.push(v0, gridPts[cols3d][j + 1], gridPts[cols3d][j]);
  }
  for (let i = 0; i < cols3d; i++) {
    for (let j = 0; j < rows; j++) {
      const d00 = gridDist[i][j];
      const d10 = gridDist[i + 1][j];
      const d11 = gridDist[i + 1][j + 1];
      const d01 = gridDist[i][j + 1];
      const maxD = Math.max(d00, d10, d11, d01);
      const minD = Math.min(d00, d10, d11, d01);
      if (maxD - minD < CURTAIN_JUMP_THRESHOLD) {
        coneWorldPts.push(gridPts[i][j], gridPts[i + 1][j], gridPts[i + 1][j + 1]);
        coneWorldPts.push(gridPts[i][j], gridPts[i + 1][j + 1], gridPts[i][j + 1]);
      }
    }
  }

  wireWorldPts.push(v0, gridPts[0][0], v0, gridPts[0][rows], v0, gridPts[cols3d][0], v0, gridPts[cols3d][rows]);
  for (let i = 0; i < cols3d; i++) {
    const jump = Math.abs(gridDist[i][rows] - gridDist[i + 1][rows]);
    if (jump < CURTAIN_JUMP_THRESHOLD || u3d[i + 1] - u3d[i] < 0.005) {
      wireWorldPts.push(gridPts[i][rows], gridPts[i + 1][rows]);
    }
  }
  for (let j = 0; j < rows; j++) {
    if (Math.abs(gridDist[0][j] - gridDist[0][j + 1]) < CURTAIN_JUMP_THRESHOLD) {
      wireWorldPts.push(gridPts[0][j], gridPts[0][j + 1]);
    }
    if (Math.abs(gridDist[cols3d][j] - gridDist[cols3d][j + 1]) < CURTAIN_JUMP_THRESHOLD) {
      wireWorldPts.push(gridPts[cols3d][j], gridPts[cols3d][j + 1]);
    }
  }
  for (let k = 1; k < 8; k++) {
    const targetU = k / 8;
    let bestIdx = 0;
    let bestErr = Infinity;
    for (let i = 0; i <= cols3d; i++) {
      const err = Math.abs(u3d[i] - targetU);
      if (err < bestErr) {
        bestErr = err;
        bestIdx = i;
      }
    }
    wireWorldPts.push(v0, gridPts[bestIdx][rows]);
  }

  // 2. Proiezione 2D al suolo esatta: intervalli continui rifiniti con bisezione (precisione sub-millimetrica)
  const intersectSegGround = (a, b) => {
    const dy = b.y - a.y;
    if (Math.abs(dy) < 1e-9) return null;
    const t = (groundY - a.y) / dy;
    if (t < -1e-6 || t > 1 + 1e-6) return null;
    const tc = THREE.MathUtils.clamp(t, 0, 1);
    return new THREE.Vector3(a.x + (b.x - a.x) * tc, groundY, a.z + (b.z - a.z) * tc);
  };

  const u2d = buildAngularSamples(
    isPanoramic ? 360 : 180,
    worldPos,
    invWorldQuat,
    isPanoramic,
    halfHRad,
    tanH,
    localBoxes
  );
  const gCols = u2d.length - 1;
  const probeSteps = 32;
  const colSegments = new Array(u2d.length);
  const colIntervals = new Array(u2d.length);

  for (let i = 0; i <= gCols; i++) {
    const u = u2d[i];
    const bot = sampleRay(u, 0);
    const top = sampleRay(u, 1);
    const pBot = new THREE.Vector3(
      v0.x + bot.dir.x * bot.maxDist,
      v0.y + bot.dir.y * bot.maxDist,
      v0.z + bot.dir.z * bot.maxDist
    );
    const pTop = new THREE.Vector3(
      v0.x + top.dir.x * top.maxDist,
      v0.y + top.dir.y * top.maxDist,
      v0.z + top.dir.z * top.maxDist
    );

    const hits = [];
    for (const [ea, eb] of [[v0, pBot], [v0, pTop], [pBot, pTop]]) {
      const hit = intersectSegGround(ea, eb);
      if (hit && !hits.some((h) => h.distanceToSquared(hit) <= 1e-8)) {
        hits.push(hit);
      }
    }

    if (hits.length < 2) {
      colSegments[i] = null;
      colIntervals[i] = [];
      continue;
    }

    hits.sort((p1, p2) => p1.distanceToSquared(v0) - p2.distanceToSquared(v0));
    const pNear = hits[0];
    const pFar = hits[hits.length - 1];
    colSegments[i] = { pNear, pFar };

    const lerpPt = (t) =>
      new THREE.Vector3(
        pNear.x + (pFar.x - pNear.x) * t,
        groundY,
        pNear.z + (pFar.z - pNear.z) * t
      );

    if (localBoxes.length === 0) {
      colIntervals[i] = [{ t0: 0, t1: 1, p0: pNear, p1: pFar }];
      continue;
    }

    const isGroundParamVisible = (t) => {
      const px = pNear.x + (pFar.x - pNear.x) * t;
      const pz = pNear.z + (pFar.z - pNear.z) * t;
      const vx = px - v0.x;
      const vy = (groundY + 0.02) - v0.y;
      const vz = pz - v0.z;
      const dist = Math.hypot(vx, vy, vz);
      if (dist <= RAY_NEAR) return true;
      return !hasAnyObstacleHit(
        v0.x, v0.y, v0.z,
        vx / dist, vy / dist, vz / dist,
        RAY_NEAR, dist - 0.002,
        localBoxes
      );
    };

    const intervals = [];
    let curVis = isGroundParamVisible(0);
    let segStart = curVis ? 0 : null;

    for (let k = 1; k <= probeSteps; k++) {
      const tPrev = (k - 1) / probeSteps;
      const tCurr = k / probeSteps;
      const nextVis = isGroundParamVisible(tCurr);
      if (nextVis !== curVis) {
        let lo = tPrev;
        let hi = tCurr;
        for (let iter = 0; iter < 10; iter++) {
          const mid = 0.5 * (lo + hi);
          if (isGroundParamVisible(mid) === curVis) {
            lo = mid;
          } else {
            hi = mid;
          }
        }
        const tEdge = 0.5 * (lo + hi);
        if (curVis) {
          if (segStart !== null && tEdge - segStart > 1e-4) {
            intervals.push({ t0: segStart, t1: tEdge, p0: lerpPt(segStart), p1: lerpPt(tEdge) });
          }
          segStart = null;
        } else {
          segStart = tEdge;
        }
        curVis = nextVis;
      }
    }

    if (curVis && segStart !== null && 1.0 - segStart > 1e-4) {
      intervals.push({ t0: segStart, t1: 1.0, p0: lerpPt(segStart), p1: lerpPt(1.0) });
    }
    colIntervals[i] = intervals;
  }

  const groundWorldPts = [];
  const groundLineWorldPts = [];
  const lerpCol = (seg, t) =>
    new THREE.Vector3(
      seg.pNear.x + (seg.pFar.x - seg.pNear.x) * t,
      groundY,
      seg.pNear.z + (seg.pFar.z - seg.pNear.z) * t
    );

  // Bordo esterno sinistro (colonna 0)
  if (colSegments[0]) {
    for (const iv of colIntervals[0]) {
      groundLineWorldPts.push(iv.p0, iv.p1);
    }
  }
  // Bordo esterno destro (ultima colonna)
  if (colSegments[gCols]) {
    for (const iv of colIntervals[gCols]) {
      groundLineWorldPts.push(iv.p0, iv.p1);
    }
  }

  for (let i = 0; i < gCols; i++) {
    const segA = colSegments[i];
    const segB = colSegments[i + 1];
    const listA = colIntervals[i];
    const listB = colIntervals[i + 1];

    if (!segA || !segB) {
      if (segA) {
        for (const a of listA) groundLineWorldPts.push(a.p0, a.p1);
      }
      if (segB) {
        for (const b of listB) groundLineWorldPts.push(b.p0, b.p1);
      }
      continue;
    }

    const overlapsA = listA.map(() => []);
    const overlapsB = listB.map(() => []);

    for (let ai = 0; ai < listA.length; ai++) {
      const a = listA[ai];
      for (let bi = 0; bi < listB.length; bi++) {
        const b = listB[bi];
        const ov0 = Math.max(a.t0, b.t0);
        const ov1 = Math.min(a.t1, b.t1);
        if (ov1 - ov0 <= 1e-4) continue;

        overlapsA[ai].push([ov0, ov1]);
        overlapsB[bi].push([ov0, ov1]);

        const pa0 = lerpCol(segA, ov0);
        const pa1 = lerpCol(segA, ov1);
        const pb0 = lerpCol(segB, ov0);
        const pb1 = lerpCol(segB, ov1);

        groundWorldPts.push(pa0, pa1, pb1);
        groundWorldPts.push(pa0, pb1, pb0);
        groundLineWorldPts.push(pa0, pb0);
        groundLineWorldPts.push(pa1, pb1);
      }
    }

    for (let ai = 0; ai < listA.length; ai++) {
      const a = listA[ai];
      for (const [u0, u1] of subtractIntervals(a.t0, a.t1, overlapsA[ai])) {
        groundLineWorldPts.push(lerpCol(segA, u0), lerpCol(segA, u1));
      }
    }
    for (let bi = 0; bi < listB.length; bi++) {
      const b = listB[bi];
      for (const [u0, u1] of subtractIntervals(b.t0, b.t1, overlapsB[bi])) {
        groundLineWorldPts.push(lerpCol(segB, u0), lerpCol(segB, u1));
      }
    }
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
    groundPolygonWorld: groundLineWorldPts,
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
    this.calibratedStates = new Map();
    this.povActiveCameras = new Set();
    this.frustumMode = 'off'; // 'off' | '3d' | '2d'
    this.frustumsVisible = false; // Nascosto di default all'avvio su richiesta dell'utente
    this.groundColliders = [];
    this.occlusionColliders = [];
  }

  setGroundColliders(colliders) {
    this.groundColliders = colliders;
    console.log(`[CameraProjector] Ground colliders configurati: ${this.groundColliders.length}`);
  }

  setOcclusionColliders(colliders) {
    this.occlusionColliders = Array.isArray(colliders) ? colliders : [];
    console.log(`[CameraProjector] Occlusion colliders configurati: ${this.occlusionColliders.length}`);
    if (this.frustumVolumes.size > 0) {
      this.frustumVolumes.forEach((_, camName) => {
        const pose = this.getCalibratedCameraPose(camName);
        if (pose) {
          this.updateFrustumVolumeGeometry(camName, pose.position, pose.quaternion, pose.fovV, pose.fovH, FRUSTUM_DEPTH);
        }
      });
    }
  }

  isCalibrationPosePlausible(calibState) {
    if (!calibState || typeof calibState !== 'object') return false;
    const ox = Number(calibState.offsetX) || 0;
    const oy = Number(calibState.offsetY) || 0;
    const oz = Number(calibState.offsetZ) || 0;
    return Math.hypot(ox, oy, oz) <= MAX_CALIBRATION_POS_OFFSET_M;
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

      // Allinea il FOV iniziale del nodo 3D al manifesto SSoT (evita yfov grezzi del GLB prima della calibrazione)
      if (camNode.isPerspectiveCamera && Number.isFinite(fovV) && fovV > 0) {
        camNode.fov = fovV;
        const isPano = this._isPanoramicBase({ opticalModel: manifestData?.optical_model, fovH });
        const tanH = Math.tan(THREE.MathUtils.degToRad(fovH * 0.5));
        const tanV = Math.max(1e-5, Math.tan(THREE.MathUtils.degToRad(fovV * 0.5)));
        if (!isPano && Number.isFinite(tanH / tanV) && tanH > 0) {
          camNode.aspect = tanH / tanV;
        }
        camNode.updateProjectionMatrix();
      }

      const frustumGroup = this.createFrustumCone(camNode, manifestData);
      this.scene.add(frustumGroup);
      this.frustumHelpers.set(camName, frustumGroup);
      this.syncGroupVisibility(camName);

      // Ripristina eventuale cache locale in attesa della sincronizzazione autorevole dal backend
      const saved = this.readLocalCalibration(camName);
      if (saved) {
        const normalizedSaved = this.normalizeCalibrationState(camName, saved);
        if (this.isCalibrationPosePlausible(normalizedSaved)) {
          this.applyCameraCalibration(camName, normalizedSaved);
        } else {
          console.warn(
            `[CameraProjector] Cache locale calibrazione scartata per ${camName}: offset posizione non plausibile (${normalizedSaved.offsetX}, ${normalizedSaved.offsetY}, ${normalizedSaved.offsetZ}).`
          );
          this.clearLocalCalibration(camName);
        }
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
    } = computeClippedFrustumData(worldPos, worldQuat, fovV, fovH, depth, GROUND_CLIP_Y, this.occlusionColliders);

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
    const is3d = this.frustumMode === '3d' && !isPov;
    const is2d = this.frustumMode === '2d' && !isPov;

    if (vol) {
      vol.coneMesh.visible = is3d && vol.hasConeGeometry;
      vol.wireLines.visible = is3d && vol.hasWireGeometry;
      vol.groundMesh.visible = (is3d || is2d) && vol.hasGroundProjection;
      vol.groundLines.visible = (is3d || is2d) && vol.hasGroundProjection;
      if (vol.groundMesh.material) {
        vol.groundMesh.material.opacity = is2d ? 0.34 : 0.22;
      }
      if (vol.groundLines.material) {
        vol.groundLines.material.opacity = is2d ? 0.95 : 0.90;
      }
    }
    if (overlay) {
      overlay.setVisible(isPov || (is3d && Boolean(overlay.videoTexture)));
    }
    if (group) {
      group.visible = isPov || is3d || is2d;
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

  _isPanoramicBase(base) {
    if (!base) return false;
    const optical = String(base.opticalModel || '').toLowerCase();
    return optical.includes('equirectangular') || optical.includes('panoramic') || Number(base.fovH || 0) >= 150;
  }

  createDefaultCalibrationState(camName) {
    const base = this.baseCameraPoses.get(camName);
    const isPano = this._isPanoramicBase(base);
    const dist = Array.isArray(base?.distortion)
      ? base.distortion
      : (isPano ? [0, 0, 0, 0, 0] : [-0.18, 0.04, 0, 0, 0]);
    return {
      offsetX: 0.0,
      offsetY: 0.0,
      offsetZ: 0.0,
      yawDeg: 0.0,
      pitchDeg: 0.0,
      rollDeg: 0.0,
      fovV: Number(base?.fovV) || (isPano ? 55.0 : 42.0),
      fovH: Number(base?.fovH) || (isPano ? 180.0 : 80.0),
      k1: isPano ? 0.0 : (Number.isFinite(Number(dist[0])) ? Number(dist[0]) : -0.18),
      k2: isPano ? 0.0 : (Number.isFinite(Number(dist[1])) ? Number(dist[1]) : 0.04),
      flip180: false,
    };
  }

  normalizeCalibrationState(camName, rawState = {}) {
    const defaults = this.createDefaultCalibrationState(camName);
    const src = rawState && typeof rawState === 'object' ? rawState : {};
    const num = (key, fallback) => {
      const val = Number(src[key]);
      return Number.isFinite(val) ? val : fallback;
    };
    const isPano = this._isPanoramicBase(this.baseCameraPoses.get(camName));
    return {
      offsetX: num('offsetX', defaults.offsetX),
      offsetY: num('offsetY', defaults.offsetY),
      offsetZ: num('offsetZ', defaults.offsetZ),
      yawDeg: num('yawDeg', defaults.yawDeg),
      pitchDeg: num('pitchDeg', defaults.pitchDeg),
      rollDeg: num('rollDeg', defaults.rollDeg),
      fovV: Math.max(5, num('fovV', defaults.fovV)),
      fovH: Math.max(10, num('fovH', defaults.fovH)),
      k1: isPano ? 0.0 : num('k1', defaults.k1),
      k2: isPano ? 0.0 : num('k2', defaults.k2),
      flip180: Boolean(src.flip180),
    };
  }

  _computePoseFromState(base, normalized) {
    const finalPos = base.position.clone().add(
      new THREE.Vector3(normalized.offsetX, normalized.offsetY, normalized.offsetZ)
    );
    const totalYawDeg = normalized.yawDeg + (normalized.flip180 ? 180.0 : 0.0);
    const deltaEuler = new THREE.Euler(
      THREE.MathUtils.degToRad(normalized.pitchDeg),
      THREE.MathUtils.degToRad(totalYawDeg),
      THREE.MathUtils.degToRad(normalized.rollDeg),
      'YXZ'
    );
    const deltaQuat = new THREE.Quaternion().setFromEuler(deltaEuler);
    const finalQuat = base.quaternion.clone().multiply(deltaQuat);
    return { finalPos, finalQuat };
  }

  _uiStateMatchesWorldMatrix(base, uiState, matrixWorldGl) {
    if (!Array.isArray(matrixWorldGl) || matrixWorldGl.length !== 16) return true;
    if (!matrixWorldGl.every((v) => Number.isFinite(Number(v)))) return true;
    const { finalPos, finalQuat } = this._computePoseFromState(base, uiState);
    const mat = new THREE.Matrix4().set(...matrixWorldGl.map(Number));
    const matPos = new THREE.Vector3();
    const matQuat = new THREE.Quaternion();
    const matScale = new THREE.Vector3();
    mat.decompose(matPos, matQuat, matScale);
    const posErr = finalPos.distanceTo(matPos);
    const angleErrRad = finalQuat.angleTo(matQuat);
    return posErr <= 0.02 && angleErrRad <= THREE.MathUtils.degToRad(0.5);
  }

  readLocalCalibration(camName) {
    try {
      if (typeof localStorage === 'undefined') return null;
      const raw = localStorage.getItem(`${CALIBRATION_STORAGE_PREFIX}${camName}`);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (e) {
      console.warn(`[CameraProjector] Errore lettura calibrazione salvata per ${camName}:`, e);
      return null;
    }
  }

  saveLocalCalibration(camName, calibState, meta = {}) {
    try {
      if (typeof localStorage === 'undefined') return;
      const normalized = this.normalizeCalibrationState(camName, calibState);
      const record = { ...normalized };
      if (meta.syncedToBackend !== undefined) {
        record._syncedToBackend = Boolean(meta.syncedToBackend);
      }
      if (meta.updatedAt !== undefined && meta.updatedAt !== null) {
        record._updatedAt = meta.updatedAt;
      }
      localStorage.setItem(`${CALIBRATION_STORAGE_PREFIX}${camName}`, JSON.stringify(record));
    } catch (e) {
      console.warn(`[CameraProjector] Impossibile salvare cache locale per ${camName}:`, e);
    }
  }

  clearLocalCalibration(camName) {
    try {
      if (typeof localStorage === 'undefined') return;
      localStorage.removeItem(`${CALIBRATION_STORAGE_PREFIX}${camName}`);
    } catch {}
  }

  calibrationFromBackendMetadata(camName, backendMeta) {
    const base = this.baseCameraPoses.get(camName);
    if (!base || !backendMeta || typeof backendMeta !== 'object') return null;

    const defaults = this.createDefaultCalibrationState(camName);
    const isPano = this._isPanoramicBase(base);
    const fovV = Number.isFinite(Number(backendMeta.fov_v_deg))
      ? Number(backendMeta.fov_v_deg)
      : defaults.fovV;
    const fovH = Number.isFinite(Number(backendMeta.fov_h_deg))
      ? Number(backendMeta.fov_h_deg)
      : defaults.fovH;
    const dist = Array.isArray(backendMeta.distortion_coeffs) ? backendMeta.distortion_coeffs : null;
    const k1 = isPano ? 0.0 : (dist && Number.isFinite(Number(dist[0])) ? Number(dist[0]) : defaults.k1);
    const k2 = isPano ? 0.0 : (dist && Number.isFinite(Number(dist[1])) ? Number(dist[1]) : defaults.k2);

    const opticalSeed = { ...defaults, fovV, fovH, k1, k2 };

    if (backendMeta.ui_state && typeof backendMeta.ui_state === 'object') {
      const candidate = this.normalizeCalibrationState(camName, {
        ...opticalSeed,
        ...backendMeta.ui_state,
        fovV,
        fovH,
        k1,
        k2,
      });
      if (this._uiStateMatchesWorldMatrix(base, candidate, backendMeta.matrix_world_gl)) {
        return candidate;
      }
    }

    if (
      Array.isArray(backendMeta.matrix_world_gl) &&
      backendMeta.matrix_world_gl.length === 16 &&
      backendMeta.matrix_world_gl.every((v) => Number.isFinite(Number(v)))
    ) {
      const decomposed = decomposeWorldMatrixToCalibState(
        backendMeta.matrix_world_gl.map(Number),
        base,
        opticalSeed
      );
      return this.normalizeCalibrationState(camName, decomposed);
    }

    return this.normalizeCalibrationState(camName, opticalSeed);
  }

  applyBackendCalibration(camName, backendMeta, { persistLocal = true } = {}) {
    if (!this.baseCameraPoses.has(camName) || !backendMeta || typeof backendMeta !== 'object') {
      return { applied: false, reset: false, changed: false, state: null, pose: null };
    }

    if (backendMeta.is_calibrated === true) {
      const calibState = this.calibrationFromBackendMetadata(camName, backendMeta);
      if (!calibState) {
        return { applied: false, reset: false, changed: false, state: null, pose: null };
      }
      if (!this.isCalibrationPosePlausible(calibState)) {
        console.warn(
          `[CameraProjector] Calibrazione backend scartata per ${camName}: offset posizione non plausibile (${calibState.offsetX}, ${calibState.offsetY}, ${calibState.offsetZ}) -> ripristinata posa fisica.`
        );
        const pose = this.resetCameraCalibration(camName, { clearLocal: persistLocal });
        return { applied: false, reset: true, changed: true, state: this.createDefaultCalibrationState(camName), pose };
      }
      const pose = this.applyCameraCalibration(camName, calibState);
      if (persistLocal) {
        this.saveLocalCalibration(camName, calibState, {
          syncedToBackend: true,
          updatedAt: backendMeta.updated_at ?? null,
        });
      }
      return { applied: true, reset: false, changed: true, state: calibState, pose };
    }

    if (backendMeta.is_calibrated === false) {
      const local = this.readLocalCalibration(camName);
      if (local && local._syncedToBackend === false) {
        return { applied: false, reset: false, changed: false, state: this.getCalibrationState(camName), pose: this.getCalibratedCameraPose(camName) };
      }
      if (this.calibratedStates.has(camName) || local) {
        const pose = this.resetCameraCalibration(camName, { clearLocal: persistLocal });
        return { applied: false, reset: true, changed: true, state: this.createDefaultCalibrationState(camName), pose };
      }
    }

    return { applied: false, reset: false, changed: false, state: this.getCalibrationState(camName), pose: this.getCalibratedCameraPose(camName) };
  }

  applyBackendCalibrations(calibrationsMap, options = {}) {
    const appliedCameras = [];
    const resetCameras = [];
    const updatedCameras = [];
    if (!calibrationsMap || typeof calibrationsMap !== 'object') {
      return { appliedCameras, resetCameras, updatedCameras };
    }

    for (const [camName, meta] of Object.entries(calibrationsMap)) {
      const res = this.applyBackendCalibration(camName, meta, options);
      if (res.applied) appliedCameras.push(camName);
      if (res.reset) resetCameras.push(camName);
      if (res.changed) updatedCameras.push(camName);
    }

    if (appliedCameras.length > 0 || resetCameras.length > 0) {
      console.log(
        `[CameraProjector] Calibrazioni sincronizzate dal backend: applicate=${appliedCameras.length} (${appliedCameras.join(', ') || '-'}), ripristinate=${resetCameras.length}.`
      );
    }
    return { appliedCameras, resetCameras, updatedCameras };
  }

  resetCameraCalibration(camName, { clearLocal = true } = {}) {
    const base = this.baseCameraPoses.get(camName);
    if (!base) return null;
    const defaults = this.createDefaultCalibrationState(camName);
    const pose = this.applyCameraCalibration(camName, defaults);
    this.calibratedPoses.delete(camName);
    this.calibratedStates.delete(camName);
    if (clearLocal) {
      this.clearLocalCalibration(camName);
    }
    return pose;
  }

  applyCameraCalibration(camName, calibState) {
    const base = this.baseCameraPoses.get(camName);
    const group = this.frustumHelpers.get(camName);
    if (!base) return null;

    const normalized = this.normalizeCalibrationState(camName, calibState);
    const { finalPos, finalQuat } = this._computePoseFromState(base, normalized);
    const fovV = normalized.fovV;
    const fovH = normalized.fovH;

    if (group) {
      group.position.copy(finalPos);
      group.quaternion.copy(finalQuat);
    }

    const overlay = this.frustumOverlays.get(camName);
    if (overlay) {
      overlay.updateOptics({
        fovV,
        fovH,
        distortion: [normalized.k1, normalized.k2, 0, 0, 0],
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
        const isPano = this._isPanoramicBase(base);
        const tanH = Math.tan(THREE.MathUtils.degToRad(fovH * 0.5));
        const tanV = Math.max(1e-5, Math.tan(THREE.MathUtils.degToRad(fovV * 0.5)));
        if (!isPano && Number.isFinite(tanH / tanV) && tanH > 0) {
          camNode.aspect = tanH / tanV;
        }
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
    this.calibratedStates.set(camName, normalized);
    return result;
  }

  getCalibrationState(camName) {
    const st = this.calibratedStates.get(camName);
    return st ? { ...st } : null;
  }

  getCalibratedCameraPose(camName) {
    return this.calibratedPoses.get(camName) || this.baseCameraPoses.get(camName) || null;
  }

  getBaseCameraPose(camName) {
    return this.baseCameraPoses.get(camName) || null;
  }

  /**
   * Calcola il FOV verticale del viewport 3D per contenere interamente l'overlay video
   * della telecamera data l'aspect ratio corrente del browser, l'ottica e il roll fisico.
   */
  computePovViewportFov(camName, viewportAspect) {
    const overlay = this.frustumOverlays.get(camName);
    const pose = this.getCalibratedCameraPose(camName);
    if (!overlay) {
      return pose?.fovV ?? 42.0;
    }

    let rollRad = 0;
    if (pose?.quaternion) {
      const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(pose.quaternion).normalize();
      const rightLevel = fwd.clone().cross(new THREE.Vector3(0, 1, 0));
      if (rightLevel.lengthSq() > 1e-6) {
        rightLevel.normalize();
        const upLevel = rightLevel.clone().cross(fwd).normalize();
        const upCam = new THREE.Vector3(0, 1, 0).applyQuaternion(pose.quaternion).normalize();
        rollRad = Math.atan2(upCam.dot(rightLevel), upCam.dot(upLevel));
      }
    }

    return overlay.getRequiredViewportFovV(viewportAspect, { rollRad });
  }

  getFrustumMode() {
    return this.frustumMode;
  }

  setFrustumMode(mode) {
    let nextMode = this.frustumMode;
    if (typeof mode === 'boolean') {
      nextMode = mode ? '3d' : 'off';
    } else if (FRUSTUM_MODES.includes(mode)) {
      nextMode = mode;
    } else {
      return this.frustumMode;
    }
    this.frustumMode = nextMode;
    this.frustumsVisible = nextMode !== 'off';
    this.frustumHelpers.forEach((_, camName) => {
      this.syncGroupVisibility(camName);
    });
    return this.frustumMode;
  }

  cycleFrustumMode() {
    const idx = FRUSTUM_MODES.indexOf(this.frustumMode);
    const nextMode = FRUSTUM_MODES[(idx + 1) % FRUSTUM_MODES.length];
    return this.setFrustumMode(nextMode);
  }

  toggleFrustums(visible) {
    if (visible !== undefined) {
      this.setFrustumMode(visible);
    } else {
      this.cycleFrustumMode();
    }
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
