import * as THREE from 'three';
import { SpatialAvatarFactory } from './avatars/SpatialAvatarFactory.js';

const CLASS_COLORS = {
  person: [0.02, 0.71, 0.83],
  car: [0.96, 0.62, 0.04],
  truck: [0.98, 0.45, 0.09],
  motorbike: [0.55, 0.36, 0.96],
  bicycle: [0.06, 0.73, 0.51],
  dog: [0.93, 0.28, 0.60],
};

function shortestAngleDiff(current, target) {
  let diff = ((target - current + Math.PI) % (Math.PI * 2)) - Math.PI;
  if (diff < -Math.PI) diff += Math.PI * 2;
  return diff;
}

export class TrajectoryRenderer {
  constructor(scene) {
    this.scene = scene;
    this.avatarFactory = new SpatialAvatarFactory();

    this.entities = new Map();     // Historical entities: id -> { markerGroup, trailLine, class, points }
    this.liveEntities = new Map(); // Live Kalman-interpolated entities: trackId -> state
    this.rawDetections = [];
    this.trailDuration = 18.0;
    this.liveModeActive = false;
    this.entitiesVisible = false;
    this.pulseClock = 0;
  }

  setEntityObjectVisible(entry, visible, trailVisible = visible) {
    if (!entry) return;
    const showMarker = Boolean(visible && this.entitiesVisible);
    const showTrail = Boolean(trailVisible && this.entitiesVisible);
    if (entry.markerGroup) {
      entry.markerGroup.visible = showMarker;
      if (entry.markerGroup.userData?.css2dLabel) {
        entry.markerGroup.userData.css2dLabel.visible = showMarker;
      }
      if (entry.markerGroup.userData?.badgeEl) {
        entry.markerGroup.userData.badgeEl.style.display = showMarker ? 'inline-flex' : 'none';
      }
    }
    if (entry.trailLine) {
      entry.trailLine.visible = showTrail;
    }
  }

  setEntitiesVisible(visible) {
    this.entitiesVisible = Boolean(visible);
    if (!this.entitiesVisible) {
      this.entities.forEach((e) => this.setEntityObjectVisible(e, false, false));
      this.liveEntities.forEach((e) => this.setEntityObjectVisible(e, false, false));
      return;
    }

    if (this.liveModeActive) {
      this.entities.forEach((e) => this.setEntityObjectVisible(e, false, false));
      this.liveEntities.forEach((e) => this.setEntityObjectVisible(e, true, e.trailPoints.length >= 2));
    } else {
      this.liveEntities.forEach((e) => this.setEntityObjectVisible(e, false, false));
    }
  }

  createTrailLine(maxPoints = 120) {
    const geom = new THREE.BufferGeometry();
    const posArray = new Float32Array(maxPoints * 3);
    const colArray = new Float32Array(maxPoints * 3);
    geom.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
    geom.setAttribute('color', new THREE.BufferAttribute(colArray, 3));
    geom.setDrawRange(0, 0);

    const mat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.88,
      linewidth: 2,
    });
    const line = new THREE.Line(geom, mat);
    line.frustumCulled = false;
    return line;
  }

  setLiveMode(isLive) {
    this.liveModeActive = Boolean(isLive);
    this.entities.forEach((e) => {
      if (this.liveModeActive) {
        this.setEntityObjectVisible(e, false, false);
      }
    });
    this.liveEntities.forEach((e) => {
      this.setEntityObjectVisible(e, this.liveModeActive, this.liveModeActive && e.trailPoints.length >= 2);
    });
  }

  loadDetections(detections) {
    this.rawDetections = [...detections].sort((a, b) => a.t - b.t);
    this.clearHistorical();

    const grouped = new Map();
    this.rawDetections.forEach((d) => {
      const key = String(d.id ?? d.track_id);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(d);
    });

    grouped.forEach((points, id) => {
      const firstPoint = points[0];
      const richestPoint = points.find((p) => p.identity || p.plate) || firstPoint;
      const entityClass = firstPoint.class || firstPoint.class_label || 'person';
      const camSources = Array.isArray(richestPoint.camera_sources) && richestPoint.camera_sources.length > 0
        ? richestPoint.camera_sources
        : [firstPoint.camera_id || 'Cam_Carraio'];

      const markerGroup = this.avatarFactory.createAvatar({
        track_id: id,
        class_label: entityClass,
        identity: richestPoint.identity || null,
        identity_confidence: richestPoint.identity_confidence ?? 0,
        plate: richestPoint.plate || null,
        plate_confidence: richestPoint.plate_confidence ?? 0,
        plate_whitelisted: richestPoint.plate_whitelisted ?? null,
        plate_owner: richestPoint.plate_owner || null,
        biometric_locked: Boolean(richestPoint.biometric_locked),
        biometric_status: richestPoint.biometric_status || 'none',
        best_crop_id: richestPoint.best_crop_id || null,
        confidence: richestPoint.confidence ?? firstPoint.confidence ?? 0.92,
        camera_sources: camSources,
        state: { vx: 0, vz: 0, camera_sources: camSources },
      });
      markerGroup.visible = false;
      this.scene.add(markerGroup);

      const trailLine = this.createTrailLine(120);
      trailLine.visible = false;
      this.scene.add(trailLine);

      const entry = {
        id,
        class: entityClass,
        markerGroup,
        trailLine,
        points,
      };
      this.setEntityObjectVisible(entry, false, false);
      this.entities.set(id, entry);
    });

    console.log(`[TrajectoryRenderer] Caricate ${this.rawDetections.length} rilevazioni storiche per ${this.entities.size} entità.`);
  }

  updateLiveTracks(activeTracks, serverTimestamp = null) {
    const nowPerf = performance.now() * 0.001;
    const nowUnix = serverTimestamp || Date.now() * 0.001;
    const seenIds = new Set();

    activeTracks.forEach((track) => {
      const id = String(track.track_id ?? track.id);
      seenIds.add(id);

      const st = track.state || {};
      const x = Number(st.x ?? track.x ?? 0);
      const y = Number(st.y ?? track.y ?? 0);
      const z = Number(st.z ?? track.z ?? 0);
      const vx = Number(st.vx ?? 0);
      const vy = Number(st.vy ?? 0);
      const vz = Number(st.vz ?? 0);

      let entry = this.liveEntities.get(id);
      if (!entry) {
        const markerGroup = this.avatarFactory.createAvatar(track);
        markerGroup.position.set(x, y, z);
        markerGroup.visible = this.liveModeActive;
        this.scene.add(markerGroup);

        const trailLine = this.createTrailLine(120);
        trailLine.visible = this.liveModeActive;
        this.scene.add(trailLine);

        entry = {
          trackId: id,
          classLabel: track.class_label || 'person',
          isKnown: Boolean((track.identity && track.identity !== 'Sconosciuto') || track.plate_whitelisted === true),
          markerGroup,
          trailLine,
          targetPos: new THREE.Vector3(x, y, z),
          velocity: new THREE.Vector3(vx, vy, vz),
          lastUpdatePerf: nowPerf,
          lastSeenPerf: nowPerf,
          trailPoints: [{ x, y, z, t: nowUnix }],
        };
        this.setEntityObjectVisible(entry, this.liveModeActive, false);
        this.liveEntities.set(id, entry);
      } else {
        entry.targetPos.set(x, y, z);
        entry.velocity.set(vx, vy, vz);
        entry.isKnown = Boolean((track.identity && track.identity !== 'Sconosciuto') || track.plate_whitelisted === true);
        entry.lastUpdatePerf = nowPerf;
        entry.lastSeenPerf = nowPerf;
        this.avatarFactory.updateAvatarMetadata(entry.markerGroup, track);

        const lastPt = entry.trailPoints[entry.trailPoints.length - 1];
        const dist = lastPt ? Math.hypot(x - lastPt.x, z - lastPt.z) : 1.0;
        if (!lastPt || dist > 0.08 || nowUnix - lastPt.t >= 0.25) {
          entry.trailPoints.push({ x, y, z, t: nowUnix });
          if (entry.trailPoints.length > 120) {
            entry.trailPoints.shift();
          }
        }
      }
    });

    // Rimuove immediatamente dal 3D le tracce fuse o scadute non più presenti in activeTracks del backend
    for (const [id, entry] of this.liveEntities.entries()) {
      if (!seenIds.has(id)) {
        this.removeLiveEntity(id, entry);
      }
    }
  }

  interpolateLive(delta) {
    if (!this.liveModeActive) return;
    this.pulseClock += delta;
    const nowPerf = performance.now() * 0.001;
    const nowUnix = Date.now() * 0.001;

    for (const [id, entry] of this.liveEntities.entries()) {
      const ageSinceMsg = nowPerf - entry.lastUpdatePerf;
      if (nowPerf - entry.lastSeenPerf > 6.0) {
        this.removeLiveEntity(id, entry);
        continue;
      }

      // Predizione cinematica lineare (dead reckoning limitata a 1.2s)
      const predDt = Math.min(Math.max(ageSinceMsg, 0), 1.2);
      const predictedTarget = entry.targetPos.clone().addScaledVector(entry.velocity, predDt);

      const lerpAlpha = Math.min(1.0, delta * 12.0);
      entry.markerGroup.position.lerp(predictedTarget, lerpAlpha);

      // Orientamento verso la direzione di marcia
      const speedH = Math.hypot(entry.velocity.x, entry.velocity.z);
      if (speedH > 0.12) {
        const targetYaw = Math.atan2(entry.velocity.x, entry.velocity.z);
        entry.markerGroup.rotation.y += shortestAngleDiff(entry.markerGroup.rotation.y, targetYaw) * Math.min(1.0, delta * 10.0);
      }

      // Animazione ring a terra
      const ring = entry.markerGroup.userData?.ring;
      if (ring) {
        const baseScale = entry.classLabel === 'car' || entry.classLabel === 'truck' ? 2.4 : 1.0;
        const pulse = 1.0 + 0.07 * Math.sin(this.pulseClock * 4.5);
        ring.scale.set(baseScale * pulse, baseScale * pulse, 1);
      }

      // Aggiorna BufferGeometry scia
      const [baseR, baseG, baseB] = entry.isKnown
        ? [0.06, 0.73, 0.51]
        : (CLASS_COLORS[entry.classLabel] || CLASS_COLORS.person);
      const trailWindowStart = nowUnix - this.trailDuration;
      const validTrail = entry.trailPoints.filter((pt) => pt.t >= trailWindowStart);
      if (validTrail.length !== entry.trailPoints.length) {
        entry.trailPoints = validTrail;
      }

      const geom = entry.trailLine.geometry;
      const posAttr = geom.attributes.position;
      const colAttr = geom.attributes.color;
      const renderPoints = [...validTrail, { x: entry.markerGroup.position.x, y: entry.markerGroup.position.y, z: entry.markerGroup.position.z, t: nowUnix }];
      const n = Math.min(renderPoints.length, 120);

      for (let i = 0; i < n; i++) {
        const pt = renderPoints[i];
        posAttr.setXYZ(i, pt.x, pt.y + 0.05, pt.z);
        const fade = Math.max(0.05, 1.0 - (nowUnix - pt.t) / this.trailDuration);
        colAttr.setXYZ(i, baseR * fade, baseG * fade, baseB * fade);
      }
      posAttr.needsUpdate = true;
      colAttr.needsUpdate = true;
      geom.setDrawRange(0, n);
      this.setEntityObjectVisible(entry, true, n >= 2);
    }
  }

  updateAtTime(currentTime) {
    if (this.liveModeActive) return 0;

    // Soglie calibrate sul persist_heartbeat_s (10s) del backend:
    // - gap <= 45s: interpolazione continua (copre sia veicoli in movimento sia parcheggiati con heartbeat)
    // - gap > 45s: interruzione traccia (es. riavvio server con riuso track_id), evita scie o oggetti fantasma
    const MAX_INTERP_GAP_SEC = 45.0;
    const MAX_HOLD_AFTER_LAST_SEC = 25.0;
    let visibleCount = 0;

    this.entities.forEach((entity) => {
      const { markerGroup, trailLine, points, class: entityClass } = entity;

      const pastPoints = points.filter((p) => p.t <= currentTime);
      const futurePoints = points.filter((p) => p.t > currentTime);

      if (pastPoints.length === 0) {
        this.setEntityObjectVisible(entity, false, false);
        return;
      }

      const lastPoint = pastPoints[pastPoints.length - 1];
      const nextPoint = futurePoints.length > 0 ? futurePoints[0] : null;
      const timeSinceLastDetection = currentTime - lastPoint.t;
      const segDuration = nextPoint ? nextPoint.t - lastPoint.t : Infinity;
      const hasContinuousBridge = Boolean(nextPoint && segDuration > 0.01 && segDuration <= MAX_INTERP_GAP_SEC);

      if (!hasContinuousBridge && timeSinceLastDetection > MAX_HOLD_AFTER_LAST_SEC) {
        this.setEntityObjectVisible(entity, false, false);
        return;
      }

      visibleCount += 1;
      this.setEntityObjectVisible(entity, true, true);

      let currentPos = new THREE.Vector3(lastPoint.x, lastPoint.y, lastPoint.z);
      let vx = lastPoint.vx || 0;
      let vz = lastPoint.vz || 0;

      if (hasContinuousBridge) {
        const factor = Math.min((currentTime - lastPoint.t) / segDuration, 1.0);
        const pA = new THREE.Vector3(lastPoint.x, lastPoint.y, lastPoint.z);
        const pB = new THREE.Vector3(nextPoint.x, nextPoint.y, nextPoint.z);
        currentPos.lerpVectors(pA, pB, factor);

        const dir = pB.clone().sub(pA);
        vx = dir.x / segDuration;
        vz = dir.z / segDuration;
        if (dir.lengthSq() > 0.005) {
          markerGroup.rotation.y = Math.atan2(dir.x, dir.z);
        }
      }

      const metaPoint =
        (lastPoint.identity || lastPoint.plate)
          ? lastPoint
          : pastPoints.slice().reverse().find((p) => p.identity || p.plate) || lastPoint;
      const camSources = Array.isArray(lastPoint.camera_sources) && lastPoint.camera_sources.length > 0
        ? lastPoint.camera_sources
        : [lastPoint.camera_id || 'Cam_Carraio'];
      const isKnown = Boolean((metaPoint.identity && metaPoint.identity !== 'Sconosciuto') || metaPoint.plate_whitelisted === true);
      const [baseR, baseG, baseB] = isKnown
        ? [0.06, 0.73, 0.51]
        : (CLASS_COLORS[entityClass] || CLASS_COLORS.person);

      markerGroup.position.copy(currentPos);
      this.avatarFactory.updateAvatarMetadata(markerGroup, {
        track_id: entity.id,
        class_label: entityClass,
        identity: metaPoint.identity || null,
        identity_confidence: metaPoint.identity_confidence ?? 0,
        plate: metaPoint.plate || null,
        plate_confidence: metaPoint.plate_confidence ?? 0,
        plate_whitelisted: metaPoint.plate_whitelisted ?? null,
        plate_owner: metaPoint.plate_owner || null,
        biometric_locked: Boolean(metaPoint.biometric_locked),
        best_crop_id: metaPoint.best_crop_id || null,
        confidence: lastPoint.confidence ?? 0.92,
        camera_sources: camSources,
        state: { vx, vz, camera_sources: camSources },
      });

      const trailWindowStart = currentTime - this.trailDuration;
      const rawTrail = pastPoints.filter((p) => p.t >= trailWindowStart);
      // Tronca la scia se presente un gap > MAX_INTERP_GAP_SEC tra campioni consecutivi
      const trailPoints = [];
      for (let i = rawTrail.length - 1; i >= 0; i--) {
        const pt = rawTrail[i];
        if (trailPoints.length > 0 && (trailPoints[0].t - pt.t) > MAX_INTERP_GAP_SEC) {
          break;
        }
        trailPoints.unshift(pt);
      }
      trailPoints.push({ x: currentPos.x, y: currentPos.y, z: currentPos.z, t: currentTime });

      const geom = trailLine.geometry;
      const posAttr = geom.attributes.position;
      const colAttr = geom.attributes.color;
      const n = Math.min(trailPoints.length, 120);

      for (let i = 0; i < n; i++) {
        const pt = trailPoints[i];
        posAttr.setXYZ(i, pt.x, pt.y + 0.05, pt.z);
        const age = currentTime - pt.t;
        const fade = Math.max(0.0, 1.0 - age / this.trailDuration);
        colAttr.setXYZ(i, baseR * fade, baseG * fade, baseB * fade);
      }

      posAttr.needsUpdate = true;
      colAttr.needsUpdate = true;
      geom.setDrawRange(0, n);
    });

    return visibleCount;
  }

  removeLiveEntity(id, entry) {
    this.scene.remove(entry.markerGroup);
    this.scene.remove(entry.trailLine);
    entry.trailLine.geometry.dispose();
    entry.trailLine.material.dispose();
    if (entry.markerGroup.userData?.css2dLabel?.element?.parentNode) {
      entry.markerGroup.userData.css2dLabel.element.remove();
    }
    this.liveEntities.delete(id);
  }

  clearHistorical() {
    this.entities.forEach((e) => {
      this.scene.remove(e.markerGroup);
      this.scene.remove(e.trailLine);
      e.trailLine.geometry.dispose();
      e.trailLine.material.dispose();
      if (e.markerGroup.userData?.css2dLabel?.element?.parentNode) {
        e.markerGroup.userData.css2dLabel.element.remove();
      }
    });
    this.entities.clear();
  }

  clearAll() {
    this.clearHistorical();
    for (const [id, entry] of [...this.liveEntities.entries()]) {
      this.removeLiveEntity(id, entry);
    }
  }
}
