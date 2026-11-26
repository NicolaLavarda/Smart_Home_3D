import * as THREE from 'three';

const DEFAULT_REF_WIDTH = 1920;
const DEFAULT_REF_HEIGHT = 1080;

/**
 * Restituisce il raggio limite positivo prima dell'eventuale ripiegamento non monotono
 * del modello radiale Brown-Conrady: d/dr [r * (1 + k1*r^2 + k2*r^4)] = 1 + 3*k1*r^2 + 5*k2*r^4 = 0.
 */
function findRadialFoldbackLimit(k1, k2) {
  let minU = Infinity;

  if (Math.abs(k2) <= 1e-12) {
    if (k1 < -1e-9) {
      minU = -1.0 / (3.0 * k1);
    }
  } else {
    const a = 5.0 * k2;
    const b = 3.0 * k1;
    const disc = b * b - 4.0 * a;
    if (disc >= 0) {
      const sqrtDisc = Math.sqrt(disc);
      const u1 = (-b - sqrtDisc) / (2.0 * a);
      const u2 = (-b + sqrtDisc) / (2.0 * a);
      if (u1 > 0 && u1 < minU) minU = u1;
      if (u2 > 0 && u2 < minU) minU = u2;
    }
  }

  return Number.isFinite(minU) && minU > 0 ? Math.sqrt(minU) : null;
}

/**
 * Inverte il modello di distorsione radiale Brown-Conrady (k1, k2)
 * da pixel normalizzati immagine [u, v] (origine in alto a sinistra)
 * al piano pinhole normalizzato (+X destra, +Y alto, Z = -1).
 */
export function undistortPixelUvToNormalized(pixelUv, fovV, fovH, k1 = 0, k2 = 0) {
  const uGl = Number(pixelUv[0]);
  const vGl = 1.0 - Number(pixelUv[1]);

  const tanV = Math.max(1e-5, Math.tan(THREE.MathUtils.degToRad(fovV * 0.5)));
  const tanH = Math.max(1e-5, Math.tan(THREE.MathUtils.degToRad(fovH * 0.5)));

  const xd = (uGl - 0.5) * 2.0 * tanH;
  const yd = (vGl - 0.5) * 2.0 * tanV;

  if (Math.abs(k1) <= 1e-6 && Math.abs(k2) <= 1e-6) {
    return { xn: xd, yn: yd, tanV, tanH };
  }

  const rd = Math.hypot(xd, yd);
  if (rd < 1e-9) {
    return { xn: 0, yn: 0, tanV, tanH };
  }

  const evalDistorted = (r) => {
    const r2 = r * r;
    return r * (1.0 + k1 * r2 + k2 * r2 * r2);
  };
  const evalDerivative = (r) => {
    const r2 = r * r;
    return 1.0 + 3.0 * k1 * r2 + 5.0 * k2 * r2 * r2;
  };

  const rPeak = findRadialFoldbackLimit(k1, k2);
  const rMax = rPeak !== null ? Math.min(rPeak * 0.96, Math.max(rd * 3.0, 4.0)) : Math.max(rd * 2.5, 4.0);
  const rdMax = evalDistorted(rMax);

  let r;
  if (rPeak !== null && rd >= rdMax) {
    r = rMax;
  } else {
    let lo = 0.0;
    let hi = rMax;
    r = Math.min(Math.max(rd, lo), hi);
    for (let i = 0; i < 12; i++) {
      const f = evalDistorted(r) - rd;
      if (Math.abs(f) < 1e-9) break;
      if (f < 0) {
        lo = Math.max(lo, r);
      } else {
        hi = Math.min(hi, r);
      }
      const df = evalDerivative(r);
      let nextR = df > 1e-4 ? r - f / df : 0.5 * (lo + hi);
      if (!(nextR > lo && nextR < hi)) {
        nextR = 0.5 * (lo + hi);
      }
      r = nextR;
    }
  }

  const scale = r / rd;
  return { xn: xd * scale, yn: yd * scale, tanV, tanH };
}

/**
 * Proietta dal piano pinhole normalizzato (+X destra, +Y alto, Z = -1)
 * ai pixel normalizzati dell'immagine [u, v] (origine in alto a sinistra).
 */
export function normalizedToDistortedPixelUv(xn, yn, fovV, fovH, k1 = 0, k2 = 0) {
  const tanV = Math.max(1e-5, Math.tan(THREE.MathUtils.degToRad(fovV * 0.5)));
  const tanH = Math.max(1e-5, Math.tan(THREE.MathUtils.degToRad(fovH * 0.5)));

  const r2 = xn * xn + yn * yn;
  const radial = 1.0 + k1 * r2 + k2 * r2 * r2;
  const uDist = 0.5 + (xn * radial) / (2.0 * tanH);
  const vDist = 0.5 + (yn * radial) / (2.0 * tanV);

  return [uDist, 1.0 - vDist];
}

/**
 * Restituisce il punto 3D nello spazio mondo sull'overlay video della camera
 * corrispondente alla coordinata normalizzata [u, v] cliccata sul video.
 */
export function getOverlayWorldPointFromPixelUv(
  pixelUv,
  camPos,
  camQuat,
  fovV,
  fovH,
  k1 = 0,
  k2 = 0,
  depth = 2.0
) {
  const { xn, yn } = undistortPixelUvToNormalized(pixelUv, fovV, fovH, k1, k2);
  return new THREE.Vector3(xn * depth, yn * depth, -depth)
    .applyQuaternion(camQuat)
    .add(camPos);
}

/**
 * Proietta un punto 3D nello spazio schermo CSS (px), verificando che si trovi davanti alla camera.
 */
export function projectWorldToScreen(worldPoint, camera, width, height) {
  const viewPos = worldPoint.clone().applyMatrix4(camera.matrixWorldInverse);
  const inFront = viewPos.z < -0.05;
  const ndc = worldPoint.clone().project(camera);

  return {
    x: (ndc.x * 0.5 + 0.5) * width,
    y: (-ndc.y * 0.5 + 0.5) * height,
    inFront,
    ndcX: ndc.x,
    ndcY: ndc.y,
    viewZ: viewPos.z,
  };
}

/**
 * Calcola l'errore di riproiezione ottica (in pixel 1080p) tra un punto 3D del modello
 * e il corrispondente pixel sul feed video secondo la posa/ottica corrente della camera.
 */
export function computePairCameraPixelError(
  worldPoint,
  pixelUv,
  camPos,
  camQuat,
  fovV,
  fovH,
  k1 = 0,
  k2 = 0,
  refWidth = DEFAULT_REF_WIDTH,
  refHeight = DEFAULT_REF_HEIGHT
) {
  const invQuat = camQuat.clone().invert();
  const pt = Array.isArray(worldPoint)
    ? new THREE.Vector3(worldPoint[0], worldPoint[1], worldPoint[2])
    : worldPoint.clone();

  const local = pt.sub(camPos).applyQuaternion(invQuat);
  const zCam = -local.z;
  if (zCam <= 0.05) {
    return { inFront: false, errorPx: Infinity, projectedUv: null };
  }

  const xn = local.x / zCam;
  const yn = local.y / zCam;
  const projectedUv = normalizedToDistortedPixelUv(xn, yn, fovV, fovH, k1, k2);
  const dx = (projectedUv[0] - pixelUv[0]) * refWidth;
  const dy = (projectedUv[1] - pixelUv[1]) * refHeight;

  return {
    inFront: true,
    errorPx: Math.hypot(dx, dy),
    projectedUv,
  };
}

function wrapDeg180(deg) {
  return ((((deg + 180) % 360) + 360) % 360) - 180;
}

/**
 * Decompone una matrice 4x4 row-major GL (da SolvePnPRansac o SolvePnPLocal)
 * nello stato parametrizzato degli slider di CalibrationAssistantUI.
 */
export function decomposeWorldMatrixToCalibState(matrixWorldGlRowMajor, basePose, currentState) {
  const solvedMat = new THREE.Matrix4().set(...matrixWorldGlRowMajor);
  const solvedPos = new THREE.Vector3();
  const solvedQuat = new THREE.Quaternion();
  const solvedScale = new THREE.Vector3();
  solvedMat.decompose(solvedPos, solvedQuat, solvedScale);

  const offset = solvedPos.clone().sub(basePose.position);
  const deltaQuat = basePose.quaternion.clone().invert().multiply(solvedQuat);
  const euler = new THREE.Euler().setFromQuaternion(deltaQuat, 'YXZ');

  const rawYawDeg = wrapDeg180(THREE.MathUtils.radToDeg(euler.y));
  const flip180 = Math.abs(rawYawDeg) > 90;
  const yawDeg = flip180 ? wrapDeg180(rawYawDeg - 180) : rawYawDeg;
  const pitchDeg = wrapDeg180(THREE.MathUtils.radToDeg(euler.x));
  const rollDeg = wrapDeg180(THREE.MathUtils.radToDeg(euler.z));

  return {
    ...currentState,
    offsetX: Number(offset.x.toFixed(3)),
    offsetY: Number(offset.y.toFixed(3)),
    offsetZ: Number(offset.z.toFixed(3)),
    yawDeg: Number(yawDeg.toFixed(2)),
    pitchDeg: Number(pitchDeg.toFixed(2)),
    rollDeg: Number(rollDeg.toFixed(2)),
    flip180,
  };
}

function applyRotVecToQuat(rotVec, baseQuat) {
  const angle = Math.hypot(rotVec[0], rotVec[1], rotVec[2]);
  if (angle < 1e-10) return baseQuat.clone();
  const axis = new THREE.Vector3(rotVec[0] / angle, rotVec[1] / angle, rotVec[2] / angle);
  const dq = new THREE.Quaternion().setFromAxisAngle(axis, angle);
  return dq.multiply(baseQuat);
}

function solveLinear6x6(A, b) {
  const n = 6;
  const M = A.map((row, i) => [...row, b[i]]);

  for (let col = 0; col < n; col++) {
    let pivotRow = col;
    let maxVal = Math.abs(M[col][col]);
    for (let r = col + 1; r < n; r++) {
      const val = Math.abs(M[r][col]);
      if (val > maxVal) {
        maxVal = val;
        pivotRow = r;
      }
    }
    if (maxVal < 1e-12) return null;

    if (pivotRow !== col) {
      [M[col], M[pivotRow]] = [M[pivotRow], M[col]];
    }

    const pivot = M[col][col];
    for (let c = col; c <= n; c++) {
      M[col][c] /= pivot;
    }

    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const factor = M[r][col];
      if (Math.abs(factor) < 1e-15) continue;
      for (let c = col; c <= n; c++) {
        M[r][c] -= factor * M[col][c];
      }
    }
  }

  return M.map((row) => row[n]);
}

function evaluatePnPResiduals(
  params,
  basePos,
  baseQuat,
  correspondences,
  fovV,
  fovH,
  k1,
  k2,
  refWidth,
  refHeight
) {
  const pos = new THREE.Vector3(
    basePos.x + params[0],
    basePos.y + params[1],
    basePos.z + params[2]
  );
  const quat = applyRotVecToQuat([params[3], params[4], params[5]], baseQuat);
  const invQuat = quat.clone().invert();

  const residuals = [];
  let cost = 0;
  let sumErr = 0;
  const tmp = new THREE.Vector3();

  for (const corr of correspondences) {
    tmp.set(corr.world_point[0], corr.world_point[1], corr.world_point[2])
      .sub(pos)
      .applyQuaternion(invQuat);

    const zCam = -tmp.z;
    if (zCam <= 0.05) {
      return { valid: false, residuals: null, cost: Infinity, meanErrorPx: Infinity };
    }

    const xn = tmp.x / zCam;
    const yn = tmp.y / zCam;
    const [uProj, vProj] = normalizedToDistortedPixelUv(xn, yn, fovV, fovH, k1, k2);
    const rx = (uProj - corr.pixel_uv[0]) * refWidth;
    const ry = (vProj - corr.pixel_uv[1]) * refHeight;

    residuals.push(rx, ry);
    cost += 0.5 * (rx * rx + ry * ry);
    sumErr += Math.hypot(rx, ry);
  }

  return {
    valid: true,
    residuals,
    cost,
    meanErrorPx: sumErr / correspondences.length,
    pos,
    quat,
  };
}

function runLevenbergMarquardt(
  basePos,
  baseQuat,
  correspondences,
  fovV,
  fovH,
  k1,
  k2,
  refWidth,
  refHeight
) {
  let params = [0, 0, 0, 0, 0, 0];
  let current = evaluatePnPResiduals(
    params,
    basePos,
    baseQuat,
    correspondences,
    fovV,
    fovH,
    k1,
    k2,
    refWidth,
    refHeight
  );
  if (!current.valid) return null;

  let lambda = 1e-2;
  const m = correspondences.length * 2;
  const eps = 1e-5;

  for (let iter = 0; iter < 50; iter++) {
    // Jacobiano numerico m x 6
    const J = Array.from({ length: m }, () => new Array(6).fill(0));
    let jacOk = true;
    for (let j = 0; j < 6; j++) {
      const pPlus = [...params];
      pPlus[j] += eps;
      const ev = evaluatePnPResiduals(
        pPlus,
        basePos,
        baseQuat,
        correspondences,
        fovV,
        fovH,
        k1,
        k2,
        refWidth,
        refHeight
      );
      if (!ev.valid) {
        jacOk = false;
        break;
      }
      for (let i = 0; i < m; i++) {
        J[i][j] = (ev.residuals[i] - current.residuals[i]) / eps;
      }
    }
    if (!jacOk) break;

    const JtJ = Array.from({ length: 6 }, () => new Array(6).fill(0));
    const Jtr = new Array(6).fill(0);

    for (let r = 0; r < m; r++) {
      const res = current.residuals[r];
      for (let i = 0; i < 6; i++) {
        const jri = J[r][i];
        Jtr[i] -= jri * res;
        for (let k = 0; k < 6; k++) {
          JtJ[i][k] += jri * J[r][k];
        }
      }
    }

    const damped = JtJ.map((row, i) =>
      row.map((val, k) => (i === k ? val + lambda * Math.max(val, 1e-4) : val))
    );
    const delta = solveLinear6x6(damped, Jtr);
    if (!delta) {
      lambda *= 10;
      if (lambda > 1e8) break;
      continue;
    }

    const stepNorm = Math.hypot(...delta);
    const candidateParams = params.map((v, i) => v + delta[i]);
    const candidate = evaluatePnPResiduals(
      candidateParams,
      basePos,
      baseQuat,
      correspondences,
      fovV,
      fovH,
      k1,
      k2,
      refWidth,
      refHeight
    );

    if (candidate.valid && candidate.cost < current.cost) {
      const improvement = current.cost - candidate.cost;
      params = candidateParams;
      current = candidate;
      lambda = Math.max(lambda * 0.3, 1e-7);
      if (stepNorm < 1e-6 || improvement < 1e-6) break;
    } else {
      lambda *= 5;
      if (lambda > 1e8) break;
    }
  }

  return current;
}

/**
 * Risolutore PnP locale in browser (Levenberg-Marquardt 6-DoF) usato come fallback
 * quando il microservizio Python `spatial_server` non è raggiungibile.
 */
export function solvePnPLocal(
  correspondences,
  initPos,
  initQuat,
  fovV,
  fovH,
  k1 = 0,
  k2 = 0,
  refWidth = DEFAULT_REF_WIDTH,
  refHeight = DEFAULT_REF_HEIGHT
) {
  if (!Array.isArray(correspondences) || correspondences.length < 4) {
    return null;
  }

  const centroid = new THREE.Vector3();
  for (const c of correspondences) {
    centroid.x += c.world_point[0];
    centroid.y += c.world_point[1];
    centroid.z += c.world_point[2];
  }
  centroid.divideScalar(correspondences.length);

  const flipQuat = new THREE.Quaternion()
    .setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI)
    .multiply(initQuat);

  const lookMat = new THREE.Matrix4().lookAt(initPos, centroid, new THREE.Vector3(0, 1, 0));
  const lookQuat = new THREE.Quaternion().setFromRotationMatrix(lookMat);

  const candidates = [initQuat, flipQuat, lookQuat];
  let best = null;

  for (const qStart of candidates) {
    const res = runLevenbergMarquardt(
      initPos,
      qStart,
      correspondences,
      fovV,
      fovH,
      k1,
      k2,
      refWidth,
      refHeight
    );
    if (res && (!best || res.meanErrorPx < best.meanErrorPx)) {
      best = res;
    }
  }

  if (!best) return null;

  const worldMat4 = new THREE.Matrix4().compose(best.pos, best.quat, new THREE.Vector3(1, 1, 1));
  const matrixWorldGl = Array.from(worldMat4.clone().transpose().elements);

  return {
    matrix_world_gl: matrixWorldGl,
    reprojection_error_px: best.meanErrorPx,
    inliers_count: correspondences.length,
    source: 'local_lm',
  };
}
