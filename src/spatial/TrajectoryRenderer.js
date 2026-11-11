import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

export class TrajectoryRenderer {
  constructor(scene) {
    this.scene = scene;

    this.entities = new Map(); // id -> { markerGroup, trailLine, labelObj, class, points }
    this.rawDetections = [];   // Array of { id, class, x, y, z, t, camera_id }
    this.trailDuration = 18.0; // Mostra la scia degli ultimi 18 secondi
  }

  loadDetections(detections) {
    this.rawDetections = detections.sort((a, b) => a.t - b.t);
    this.clearAll();

    // Raggruppa per id entità
    const grouped = new Map();
    this.rawDetections.forEach((d) => {
      if (!grouped.has(d.id)) grouped.set(d.id, []);
      grouped.get(d.id).push(d);
    });

    grouped.forEach((points, id) => {
      const firstPoint = points[0];
      const entityClass = firstPoint.class || 'person';

      // 1. Crea Marker 3D
      const markerGroup = this.createEntityMarker(entityClass, id);
      this.scene.add(markerGroup);

      // 2. Crea Linea per Scia Traiettoria
      const maxTrailPoints = 120;
      const trailGeom = new THREE.BufferGeometry();
      const posArray = new Float32Array(maxTrailPoints * 3);
      const colorArray = new Float32Array(maxTrailPoints * 3);
      trailGeom.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
      trailGeom.setAttribute('color', new THREE.BufferAttribute(colorArray, 3));

      const isCar = entityClass === 'car';
      const trailMat = new THREE.LineBasicMaterial({
        vertexColors: true,
        transparent: true,
        opacity: 0.85,
        linewidth: 2,
      });

      const trailLine = new THREE.Line(trailGeom, trailMat);
      this.scene.add(trailLine);

      this.entities.set(id, {
        id,
        class: entityClass,
        markerGroup,
        trailLine,
        points,
      });
    });

    console.log(`[TrajectoryRenderer] Caricate ${this.rawDetections.length} rilevazioni per ${this.entities.size} entità uniche.`);
  }

  createEntityMarker(entityClass, id) {
    const group = new THREE.Group();
    group.name = `Detection_${id}`;

    const isCar = entityClass === 'car';
    const mainColor = isCar ? 0xf59e0b : 0x06b6d4;

    // 1. Anello a terra pulsante
    const ringGeom = new THREE.RingGeometry(0.35, 0.45, 32);
    ringGeom.rotateX(-Math.PI / 2);
    const ringMat = new THREE.MeshBasicMaterial({
      color: mainColor,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.8,
    });
    const ringMesh = new THREE.Mesh(ringGeom, ringMat);
    ringMesh.position.y = 0.05;
    group.add(ringMesh);

    // 2. Corpo 3D stilizzato
    if (isCar) {
      // Sagoma veicolo stilizzato
      const bodyGeom = new THREE.BoxGeometry(1.6, 0.65, 0.9);
      const bodyMat = new THREE.MeshStandardMaterial({
        color: mainColor,
        roughness: 0.2,
        metalness: 0.7,
        emissive: mainColor,
        emissiveIntensity: 0.3,
      });
      const bodyMesh = new THREE.Mesh(bodyGeom, bodyMat);
      bodyMesh.position.y = 0.4;
      bodyMesh.castShadow = true;
      group.add(bodyMesh);
    } else {
      // Sagoma persona: cilindro + testa sferica stilizzata
      const bodyGeom = new THREE.CylinderGeometry(0.18, 0.18, 1.2, 16);
      const bodyMat = new THREE.MeshStandardMaterial({
        color: mainColor,
        roughness: 0.3,
        metalness: 0.5,
        emissive: mainColor,
        emissiveIntensity: 0.35,
      });
      const bodyMesh = new THREE.Mesh(bodyGeom, bodyMat);
      bodyMesh.position.y = 0.65;
      bodyMesh.castShadow = true;
      group.add(bodyMesh);

      const headGeom = new THREE.SphereGeometry(0.16, 16, 16);
      const headMesh = new THREE.Mesh(headGeom, bodyMat);
      headMesh.position.y = 1.4;
      headMesh.castShadow = true;
      group.add(headMesh);
    }

    // 3. Etichetta HTML CSS2D fluttuante
    const labelDiv = document.createElement('div');
    labelDiv.className = `detection-label-3d ${isCar ? 'car' : ''}`;
    labelDiv.textContent = `${isCar ? '🚗 Auto' : '👤 Persona'} #${id}`;

    const labelObj = new CSS2DObject(labelDiv);
    labelObj.position.y = isCar ? 1.1 : 1.75;
    group.add(labelObj);

    group.visible = false;
    return group;
  }

  updateAtTime(currentTime) {
    this.entities.forEach((entity) => {
      const { markerGroup, trailLine, points, class: entityClass } = entity;
      const isCar = entityClass === 'car';
      const baseR = isCar ? 0.96 : 0.02;
      const baseG = isCar ? 0.62 : 0.71;
      const baseB = isCar ? 0.04 : 0.83;

      // Trova punti rilevati fino all'istante currentTime
      const pastPoints = points.filter((p) => p.t <= currentTime);
      const futurePoints = points.filter((p) => p.t > currentTime);

      if (pastPoints.length === 0) {
        // L'entità non è ancora apparsa
        markerGroup.visible = false;
        trailLine.visible = false;
        return;
      }

      const lastPoint = pastPoints[pastPoints.length - 1];
      const timeSinceLastDetection = currentTime - lastPoint.t;

      // Se non si hanno più rilevazioni da oltre 15 secondi, nascondi l'entità
      if (timeSinceLastDetection > 15.0 && futurePoints.length === 0) {
        markerGroup.visible = false;
        trailLine.visible = false;
        return;
      }

      markerGroup.visible = true;
      trailLine.visible = true;

      // Calcola posizione interpolata
      let currentPos = new THREE.Vector3(lastPoint.x, lastPoint.y, lastPoint.z);

      if (futurePoints.length > 0) {
        const nextPoint = futurePoints[0];
        const segDuration = nextPoint.t - lastPoint.t;
        if (segDuration > 0.01) {
          const factor = Math.min((currentTime - lastPoint.t) / segDuration, 1.0);
          const pA = new THREE.Vector3(lastPoint.x, lastPoint.y, lastPoint.z);
          const pB = new THREE.Vector3(nextPoint.x, nextPoint.y, nextPoint.z);
          currentPos.lerpVectors(pA, pB, factor);

          // Calcola orientamento (rotazione verso la direzione di marcia)
          const dir = pB.clone().sub(pA);
          if (dir.lengthSq() > 0.01) {
            const angle = Math.atan2(dir.x, dir.z);
            markerGroup.rotation.y = angle;
          }
        }
      }

      markerGroup.position.copy(currentPos);

      // Aggiorna la scia (trail) degli ultimi N secondi
      const trailWindowStart = currentTime - this.trailDuration;
      const trailPoints = pastPoints.filter((p) => p.t >= trailWindowStart);
      trailPoints.push({ x: currentPos.x, y: currentPos.y, z: currentPos.z, t: currentTime });

      const geom = trailLine.geometry;
      const posAttr = geom.attributes.position;
      const colAttr = geom.attributes.color;
      const n = Math.min(trailPoints.length, 120);

      for (let i = 0; i < n; i++) {
        const pt = trailPoints[i];
        posAttr.setXYZ(i, pt.x, pt.y + 0.05, pt.z);

        // Calcola gradiente di dissolvenza temporale (da 0 a 1)
        const age = currentTime - pt.t;
        const fade = Math.max(0.0, 1.0 - age / this.trailDuration);
        colAttr.setXYZ(i, baseR * fade, baseG * fade, baseB * fade);
      }

      // Riempie il resto con l'ultimo punto per evitare artefatti
      for (let i = n; i < 120; i++) {
        posAttr.setXYZ(i, currentPos.x, currentPos.y + 0.05, currentPos.z);
        colAttr.setXYZ(i, 0, 0, 0);
      }

      posAttr.needsUpdate = true;
      colAttr.needsUpdate = true;
      geom.setDrawRange(0, n);
    });
  }

  clearAll() {
    this.entities.forEach((e) => {
      this.scene.remove(e.markerGroup);
      this.scene.remove(e.trailLine);
    });
    this.entities.clear();
  }
}

