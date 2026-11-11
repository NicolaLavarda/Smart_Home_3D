import * as THREE from 'three';

export class EntityBinder {
  constructor(scene, haClient) {
    this.scene = scene;
    this.haClient = haClient;
    this.haEntitiesMap = new Map();
    this.lights3D = new Map();      // entity_id -> PointLight
    this.originalGatePositions = new Map(); // mesh -> Vector3
    this.targetGatePositions = new Map();   // mesh -> Vector3
    this.interactionManager = null;

    // Canvas per la schermata interattiva della TV
    this.tvCanvas = document.createElement('canvas');
    this.tvCanvas.width = 512;
    this.tvCanvas.height = 288;
    this.tvTexture = new THREE.CanvasTexture(this.tvCanvas);
    this.tvTexture.colorSpace = THREE.SRGBColorSpace;
    this.renderTVTexture('STANDBY', 'Nessuna riproduzione');
  }

  setInteractionManager(im) {
    this.interactionManager = im;
  }

  bindEntities(haEntitiesMap) {
    this.haEntitiesMap = haEntitiesMap;

    // Crea luci Three.js dinamiche in corrispondenza dei corpi illuminanti
    this.setupDynamicLights();

    // Registra posizioni iniziali dei cancelli per l'animazione di scorrimento
    this.setupGateTransforms();

    // Sottoscrivi aggiornamenti in tempo reale da Home Assistant / Mock
    this.haClient.subscribeEntities((entities) => {
      this.handleEntitiesUpdate(entities);
    });
  }

  setupDynamicLights() {
    this.haEntitiesMap.forEach((meshes, entityId) => {
      if (!entityId.startsWith('light.')) return;

      // Calcola centroide della fixture
      const center = new THREE.Vector3();
      meshes.forEach((m) => {
        const p = new THREE.Vector3();
        m.getWorldPosition(p);
        center.add(p);
      });
      center.divideScalar(meshes.length);

      // Crea PointLight Three.js
      const light = new THREE.PointLight(0xfff1e0, 0.0, 8.0, 1.8);
      light.position.copy(center);
      light.position.y -= 0.15; // Leggermente sotto la coppa
      light.castShadow = true;
      light.shadow.bias = -0.002;
      light.shadow.mapSize.width = 512;
      light.shadow.mapSize.height = 512;

      this.scene.add(light);
      this.lights3D.set(entityId, light);
    });
  }

  setupGateTransforms() {
    const gateMeshes = this.haEntitiesMap.get('cover.cancello_carrabile') || [];
    gateMeshes.forEach((mesh) => {
      this.originalGatePositions.set(mesh, mesh.position.clone());
      this.targetGatePositions.set(mesh, mesh.position.clone());
    });
  }

  handleEntitiesUpdate(entities) {
    Object.entries(entities).forEach(([entityId, stateObj]) => {
      const meshes = this.haEntitiesMap.get(entityId);
      if (!meshes || meshes.length === 0) return;

      const domain = entityId.split('.')[0];
      const isOn = stateObj.state === 'on' || stateObj.state === 'open' || stateObj.state === 'playing';

      // Aggiorna badge CSS2D
      if (this.interactionManager) {
        this.interactionManager.updateBadgeState(entityId, isOn, stateObj.state);
      }

      if (domain === 'light') {
        this.updateLightState(entityId, meshes, stateObj);
      } else if (domain === 'cover' || domain === 'switch') {
        this.updateCoverState(entityId, meshes, stateObj);
      } else if (domain === 'media_player') {
        this.updateMediaPlayerState(entityId, meshes, stateObj);
      }
    });
  }

  updateLightState(entityId, meshes, stateObj) {
    const isOn = stateObj.state === 'on';
    const attrs = stateObj.attributes || {};
    const brightness = (attrs.brightness ?? 255) / 255;
    const rgb = attrs.rgb_color || [255, 240, 200];

    const color = new THREE.Color(`rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`);

    // Aggiorna PointLight
    const pointLight = this.lights3D.get(entityId);
    if (pointLight) {
      pointLight.color.copy(color);
      pointLight.intensity = isOn ? 1.4 * brightness : 0.0;
    }

    // Aggiorna materiale emissivo delle mesh
    meshes.forEach((mesh) => {
      if (mesh.material && 'emissive' in mesh.material) {
        if (isOn) {
          mesh.material.emissive.copy(color);
          mesh.material.emissiveIntensity = 1.0 * brightness;
        } else {
          mesh.material.emissive.setHex(0x000000);
          mesh.material.emissiveIntensity = 0.0;
        }
      }
    });
  }

  updateCoverState(entityId, meshes, stateObj) {
    const isOpen = stateObj.state === 'open' || stateObj.state === 'on';

    meshes.forEach((mesh) => {
      const origPos = this.originalGatePositions.get(mesh);
      if (!origPos) return;

      // Se aperta, trasla le ante del cancello carraio lungo l'asse X
      if (isOpen) {
        const offset = mesh.name.includes('_L') ? -1.8 : 1.8;
        this.targetGatePositions.set(mesh, new THREE.Vector3(origPos.x + offset, origPos.y, origPos.z));
      } else {
        this.targetGatePositions.set(mesh, origPos.clone());
      }
    });
  }

  updateMediaPlayerState(entityId, meshes, stateObj) {
    const isPlaying = stateObj.state === 'playing';
    const attrs = stateObj.attributes || {};
    const title = attrs.media_title || 'Smart TV Salotto';
    const app = attrs.app_name || 'Home Assistant Cast';

    meshes.forEach((mesh) => {
      if (mesh.name === 'TV_Salotto_Screen' && mesh.material) {
        if (isPlaying) {
          this.renderTVTexture(app, title);
          mesh.material.map = this.tvTexture;
          mesh.material.emissiveMap = this.tvTexture;
          mesh.material.emissive.setHex(0xffffff);
          mesh.material.emissiveIntensity = 0.85;
        } else {
          mesh.material.emissive.setHex(0x050505);
          mesh.material.emissiveIntensity = 0.1;
        }
        mesh.material.needsUpdate = true;
      }
    });
  }

  renderTVTexture(subtitle, title) {
    const ctx = this.tvCanvas.getContext('2d');
    // Sfondo gradiente cinematografico
    const grad = ctx.createLinearGradient(0, 0, 512, 288);
    grad.addColorStop(0, '#0f172a');
    grad.addColorStop(0.5, '#1e1b4b');
    grad.addColorStop(1, '#0284c7');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 512, 288);

    // Dettaglio griglia tech
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineWidth = 1;
    for (let x = 0; x < 512; x += 32) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 288); ctx.stroke();
    }

    // Testo
    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 20px sans-serif';
    ctx.fillText('DIGITAL TWIN LIVE TV', 40, 70);

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 28px sans-serif';
    ctx.fillText(title.length > 25 ? title.substring(0, 25) + '...' : title, 40, 140);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '18px sans-serif';
    ctx.fillText(`App: ${subtitle}`, 40, 190);

    // Barra progresso player
    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.fillRect(40, 230, 432, 6);
    ctx.fillStyle = '#38bdf8';
    ctx.fillRect(40, 230, 260, 6);

    this.tvTexture.needsUpdate = true;
  }

  update(delta) {
    // Animazione fluida ante cancelli (lerp)
    this.originalGatePositions.forEach((_, mesh) => {
      const target = this.targetGatePositions.get(mesh);
      if (target) {
        mesh.position.lerp(target, 0.08);
      }
    });
  }

  toggleEntity(entityId) {
    const domain = entityId.split('.')[0];
    this.haClient.callService(domain, 'toggle', { entity_id: entityId });
  }
}

