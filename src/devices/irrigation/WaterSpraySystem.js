import * as THREE from 'three';

/**
 * WaterSpraySystem
 * 
 * Sistema particellare ad alte prestazioni a 60 fps per l'animazione realistica
 * dei getti d'acqua degli 11 irrigatori/gettini del giardino.
 * Simula la traiettoria balistica parabolica con gravità, oscillazione angolare
 * dei settori d'irrigazione, dispersione delle gocce e impatto sul prato verde.
 */
export class WaterSpraySystem {
  constructor(scene, sprinklersConfig) {
    this.scene = scene;
    this.config = sprinklersConfig; // Array delle definizioni degli 11 gettini
    this.sprinklerUnits = new Map();

    // Texture procedurale canvas per le gocce d'acqua fotorealistiche
    this.waterTexture = this.createWaterDropTexture();

    // Materiale particellare condiviso per la massima efficienza WebGL
    this.particleMaterial = new THREE.PointsMaterial({
      size: 0.16,
      map: this.waterTexture,
      transparent: true,
      opacity: 0.82,
      depthWrite: false,
      blending: THREE.NormalBlending,
      vertexColors: true,
    });

    this.initSprinklers();
  }

  createWaterDropTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');

    const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 30);
    grad.addColorStop(0.0, 'rgba(255, 255, 255, 1.0)');     // Nucleo goccia bianco
    grad.addColorStop(0.25, 'rgba(224, 242, 254, 0.95)');   // Azzurro chiarissimo (Sky 100)
    grad.addColorStop(0.60, 'rgba(56, 189, 248, 0.65)');    // Ciano acqua vivido (Sky 400)
    grad.addColorStop(0.90, 'rgba(14, 165, 233, 0.20)');    // Sfocatura esterna
    grad.addColorStop(1.0, 'rgba(2, 132, 199, 0.0)');

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(32, 32, 30, 0, Math.PI * 2);
    ctx.fill();

    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  initSprinklers() {
    const PARTICLES_PER_SPRINKLER = 280;

    this.config.forEach((cfg) => {
      // Buffer particelle per questo gettino
      const positions = new Float32Array(PARTICLES_PER_SPRINKLER * 3);
      const colors = new Float32Array(PARTICLES_PER_SPRINKLER * 3);

      // Inizializza particelle dormienti sotto terra
      for (let i = 0; i < PARTICLES_PER_SPRINKLER; i++) {
        positions[i * 3] = cfg.position.x;
        positions[i * 3 + 1] = -10.0; // fuori vista
        positions[i * 3 + 2] = cfg.position.z;

        colors[i * 3] = 0.85;
        colors[i * 3 + 1] = 0.95;
        colors[i * 3 + 2] = 1.0;
      }

      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

      const points = new THREE.Points(geometry, this.particleMaterial);
      points.frustumCulled = false;
      this.scene.add(points);

      // Struttura dati per le particelle attive
      const particlesData = [];
      for (let i = 0; i < PARTICLES_PER_SPRINKLER; i++) {
        particlesData.push({
          active: false,
          x: cfg.position.x,
          y: -10.0,
          z: cfg.position.z,
          vx: 0,
          vy: 0,
          vz: 0,
          life: 0,
          maxLife: 1.0,
          isSplash: false,
        });
      }

      this.sprinklerUnits.set(cfg.id, {
        cfg,
        points,
        geometry,
        positions,
        colors,
        particlesData,
        currentSweepAngle: cfg.minAngle,
        sweepDir: 1,
        sweepSpeed: cfg.sweepSpeed || 0.75, // radianti al secondo
        emitTimer: 0,
        active: false,
        riserMesh: null,
        currentHeight: 0.0, // 0.0m retratto -> 0.25m esteso
        targetHeight: 0.0,
      });
    });
  }

  /**
   * Associa le mesh 3D di Blender o Three.js ai rispettivi gettini
   */
  bindMeshes(meshMap) {
    this.sprinklerUnits.forEach((unit, id) => {
      const mesh = meshMap.get(id);
      if (mesh) {
        unit.riserMesh = mesh;
        unit.baseY = mesh.position.y;
      }
    });
  }

  /**
   * Imposta lo stato di funzionamento per un'area (1, 2, o 3)
   */
  setAreaState(areaNum, isOn) {
    this.sprinklerUnits.forEach((unit) => {
      if (unit.cfg.area === areaNum) {
        unit.active = isOn;
        unit.targetHeight = isOn ? 0.25 : 0.0; // 25cm estensione pop-up
      }
    });
  }

  /**
   * Render loop tick (60 fps)
   */
  update(delta) {
    const dt = Math.min(delta, 0.05); // cap per evitare salti temporali

    this.sprinklerUnits.forEach((unit) => {
      // 1. Animazione sollevamento/abbassamento stelo pop-up da 25cm
      const heightDiff = unit.targetHeight - unit.currentHeight;
      if (Math.abs(heightDiff) > 0.001) {
        unit.currentHeight += heightDiff * Math.min(dt * 5.0, 1.0);
        if (unit.riserMesh) {
          const by = unit.baseY ?? 0;
          unit.riserMesh.position.y = by + unit.currentHeight;
        }
      } else {
        unit.currentHeight = unit.targetHeight;
      }

      // 2. Oscillazione angolare del getto dentro il settore del prato
      if (unit.active && unit.currentHeight > 0.15) {
        unit.currentSweepAngle += unit.sweepDir * unit.sweepSpeed * dt;
        if (unit.currentSweepAngle >= unit.cfg.maxAngle) {
          unit.currentSweepAngle = unit.cfg.maxAngle;
          unit.sweepDir = -1;
        } else if (unit.currentSweepAngle <= unit.cfg.minAngle) {
          unit.currentSweepAngle = unit.cfg.minAngle;
          unit.sweepDir = 1;
        }

        // Ruota anche la testina del gettino in Three.js se presente
        if (unit.riserMesh) {
          unit.riserMesh.rotation.y = unit.currentSweepAngle;
        }

        // 3. Emissione continua di gocce d'acqua
        unit.emitTimer += dt;
        const emitInterval = 0.009; // ~110 gocce al secondo per gettino
        while (unit.emitTimer >= emitInterval) {
          unit.emitTimer -= emitInterval;
          this.emitDrop(unit);
        }
      }

      // 4. Aggiornamento particelle in volo e impatti sul prato
      let needsUpdate = false;
      const count = unit.particlesData.length;
      const positions = unit.positions;
      const colors = unit.colors;
      const gravity = 9.81;

      for (let i = 0; i < count; i++) {
        const p = unit.particlesData[i];
        if (!p.active) continue;

        needsUpdate = true;
        p.life -= dt;

        if (p.life <= 0) {
          p.active = false;
          positions[i * 3 + 1] = -10.0;
          continue;
        }

        // Fisica balistica parabolica
        p.vy -= gravity * dt;
        p.vx *= (1.0 - 0.15 * dt); // attrito aria
        p.vz *= (1.0 - 0.15 * dt);

        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.z += p.vz * dt;

        // Impatto sul prato (Y <= 0.015m)
        if (p.y <= 0.015 && p.vy < 0) {
          p.y = 0.015;
          p.vy = -p.vy * 0.12; // rimbalzo morbido
          p.vx *= 0.4;
          p.vz *= 0.4;
          p.life = Math.min(p.life, 0.12); // si dissipa rapidamente come vapore/rugiada
        }

        positions[i * 3] = p.x;
        positions[i * 3 + 1] = p.y;
        positions[i * 3 + 2] = p.z;

        // Gradiente di colore e trasparenza lungo la traiettoria
        const tLife = p.life / p.maxLife;
        colors[i * 3] = 0.70 + 0.30 * tLife;     // R
        colors[i * 3 + 1] = 0.88 + 0.12 * tLife; // G
        colors[i * 3 + 2] = 1.0;                 // B
      }

      if (needsUpdate) {
        unit.geometry.attributes.position.needsUpdate = true;
        unit.geometry.attributes.color.needsUpdate = true;
      }
    });
  }

  emitDrop(unit) {
    // Trova uno slot libero nel pool di particelle
    const p = unit.particlesData.find((pt) => !pt.active);
    if (!p) return;

    const angle = unit.currentSweepAngle + (Math.random() - 0.5) * 0.08; // piccola dispersione
    const pitch = (24 + Math.random() * 12) * (Math.PI / 180); // inclinazione ~24°-36°
    const power = unit.cfg.throwSpeed * (0.55 + Math.random() * 0.50); // getto vicino + getto lungo

    // Origine dall'ugello a 25cm
    const nozzleHeight = Math.max(unit.currentHeight, 0.05);
    p.active = true;
    p.x = unit.cfg.position.x;
    p.y = nozzleHeight + 0.02;
    p.z = unit.cfg.position.z;

    p.vx = Math.cos(angle) * Math.cos(pitch) * power;
    p.vy = Math.sin(pitch) * power;
    p.vz = Math.sin(angle) * Math.cos(pitch) * power;

    p.life = 0.85 + Math.random() * 0.45;
    p.maxLife = p.life;
  }

  dispose() {
    this.sprinklerUnits.forEach((unit) => {
      this.scene.remove(unit.points);
      unit.geometry.dispose();
    });
    this.sprinklerUnits.clear();
    this.waterTexture.dispose();
    this.particleMaterial.dispose();
  }
}

