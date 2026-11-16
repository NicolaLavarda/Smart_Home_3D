import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { deviceRegistry } from '../devices/DeviceRegistry.js';

export class InteractionManager {
  constructor(scene, camera, domElement, entityBinder, onOpenModal) {
    this.scene = scene;
    this.camera = camera;
    this.domElement = domElement;
    this.entityBinder = entityBinder;
    this.onOpenModal = onOpenModal;

    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2(-1000, -1000);
    this.interactiveObjects = [];
    this.hoveredObject = null;
    this.originalEmissive = new Map();
    this.deviceBadges = new Map(); // entity_id -> { element, dot, valEl, css2dObj, position }
    this.thermal3DBadges = new Map(); // entity_id -> { canvas, ctx, texture, material, decalMesh, ringColor, sublabel, currentVal }
    this.badgesVisible = false; // Default nascosti all'avvio su richiesta dell'utente

    this.onPointerMove = this.onPointerMove.bind(this);
    this.onPointerDown = this.onPointerDown.bind(this);
    this.onPointerUp = this.onPointerUp.bind(this);
    this.onPointerCancel = this.onPointerCancel.bind(this);

    this._activePointers = new Set();
    this._pointerDownId = null;
    this._pointerDownPos = { x: 0, y: 0 };
    this._wasMultiTouch = false;

    this.domElement.addEventListener('pointermove', this.onPointerMove);
    this.domElement.addEventListener('pointerdown', this.onPointerDown);
    this.domElement.addEventListener('pointerup', this.onPointerUp);
    this.domElement.addEventListener('pointercancel', this.onPointerCancel);
  }

  registerEntities(haEntitiesMap) {
    this.interactiveObjects = [];
    haEntitiesMap.forEach((meshes, entityId) => {
      meshes.forEach((mesh) => {
        if (mesh.isMesh && !this.interactiveObjects.includes(mesh)) {
          this.interactiveObjects.push(mesh);
        }
      });
    });
    console.log(`[InteractionManager] Registrati ${this.interactiveObjects.length} mesh interattivi.`);
  }

  addInteractiveObject(object) {
    if (!object) return;
    if (object.isMesh && !this.interactiveObjects.includes(object)) {
      this.interactiveObjects.push(object);
    } else if (object.traverse) {
      object.traverse((child) => {
        if (child.isMesh && !this.interactiveObjects.includes(child)) {
          this.interactiveObjects.push(child);
        }
      });
    }
  }

  createDeviceBadges(manifest, haEntitiesMap) {
    if (!manifest || !manifest.ha_entities) return;

    // Assicura che le 3 aree di irrigazione siano sempre presenti nel manifest
    const irrigationDefaults = {
      'switch.smart_switch_area1': { name: 'Area 1 - Prato Sud', action: 'modal', ui_type: 'irrigation' },
      'switch.smart_switch_area2': { name: 'Area 2 - Corte Est', action: 'modal', ui_type: 'irrigation' },
      'switch.smart_switch_area3': { name: 'Area 3 - Prato Nord & Viale', action: 'modal', ui_type: 'irrigation' },
    };
    Object.entries(irrigationDefaults).forEach(([id, def]) => {
      if (!manifest.ha_entities[id]) {
        manifest.ha_entities[id] = { entity_id: id, domain: 'switch', ...def, objects: [] };
      }
    });

    Object.entries(manifest.ha_entities).forEach(([entityId, entData]) => {
      // Ignora sensori variazione rimossi su richiesta dell'utente
      if (entityId === 'sensor.variazione_temperatura_caldaia' || entityId === 'sensor.variazione2_temperatura_caldaia') return;

      const meshes = haEntitiesMap ? haEntitiesMap.get(entityId) : null;
      const isFixedPosEntity = entityId.startsWith('switch.smart_switch_area') ||
        entityId === 'switch.switch_casa_interruttore_1' ||
        entityId === 'switch.switch_casa_interruttore_2' ||
        entityId === 'switch.smart_switch_caldaia';

      if (!isFixedPosEntity && (!meshes || meshes.length === 0)) return;

      const badgeStyle = entData.badge_style || '';

      // 1. CENTRALE TERMICA: Badge 3D veri e propri ancorati ad accumulo e caldaia ("oggetti di arredo")
      // Non usano CSS2D, partecipano al Depth-Buffer WebGL e scalano naturalmente con la prospettiva!
      if (badgeStyle === 'puffer_high' || badgeStyle === 'puffer_low' || badgeStyle === 'caldaia') {
        this.createThermal3DDecal(entityId, entData, meshes, badgeStyle);
        return;
      }

      // 2. BADGE CSS2D STANDARD (Luci, interruttori, cancello, elettrodomestici)
      const center = new THREE.Vector3();

      if (entityId === 'switch.switch_casa_interruttore_1') {
        // Al centro del cancello carraio nero (318cm)
        center.set(-13.44, 0.95, 6.28);
      } else if (entityId === 'switch.switch_casa_interruttore_2') {
        // Sul montante del cancelletto pedonale (117cm)
        center.set(-9.60, 1.05, 6.28);
      } else if (entityId === 'switch.smart_switch_caldaia') {
        // Parete di fronte in lavanderia
        center.set(0.90, 1.25, 12.60);
      } else if (entityId === 'switch.smart_switch_area1') {
        // Giardino Area 1 (Prato Sud)
        center.set(-0.50, 0.45, 28.00);
      } else if (entityId === 'switch.smart_switch_area2') {
        // Giardino Area 2 (Corte Est)
        center.set(10.00, 0.45, 12.60);
      } else if (entityId === 'switch.smart_switch_area3') {
        // Giardino Area 3 (Prato Nord & Viale)
        center.set(-5.50, 0.45, 12.50);
      } else if (entityId === 'light.luci_esterne') {
        // Sopra il primo lampioncino
        const b1 = meshes.find((m) => m.name === 'Bollard_Garden_1') || meshes[0];
        const bbox = new THREE.Box3().setFromObject(b1);
        bbox.getCenter(center);
        center.y += 0.45;
      } else if (entityId === 'light.smart_plug_in_unit_switch_3') {
        // Centro soffitto salotto sotto i 6 faretti (griglia 2x3 centrata a X=3.20, Z=3.35)
        center.set(3.20, 2.75, 3.35);
      } else if (entityId === 'sensor.lavastoviglie_stato_di_funzionamento') {
        // Ancorato esattamente sopra il top della lavastoviglie in cucina
        center.set(8.465, 1.05, 7.085);
      } else if (entityId === 'media_player.smart_tv_lg_oled_2' || entityId === 'media_player.lg_webos_smart_tv') {
        // Ancorato sopra la Smart TV LG OLED in salotto
        center.set(0.59, 1.85, 2.65);
      } else if (entityId === 'vacuum.deebot') {
        // Ancorato sopra il robot aspirapolvere Ecovacs Deebot in sala da pranzo
        center.set(13.63, 0.45, 1.65);
      } else {
        const bbox = new THREE.Box3();
        meshes.forEach((m) => bbox.expandByObject(m));
        bbox.getCenter(center);
        center.y += 0.35;
      }

      let badgeEl;
      let dotEl = null;
      let valEl = null;

      if (entityId === 'sensor.lavastoviglie_stato_di_funzionamento') {
        // Badge Lavastoviglie (100% SVG pulito)
        badgeEl = document.createElement('div');
        badgeEl.className = 'device-badge-3d badge-dishwasher';
        badgeEl.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#06b6d4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;">
            <rect x="3" y="3" width="18" height="18" rx="2"></rect>
            <line x1="3" y1="8" x2="21" y2="8"></line>
            <circle cx="7" cy="5.5" r="1" fill="currentColor"></circle>
            <circle cx="10" cy="5.5" r="1" fill="currentColor"></circle>
            <circle cx="12" cy="14" r="3"></circle>
          </svg>
          <span class="badge-name">Lavastoviglie:</span>
          <span class="badge-val" style="color: #38bdf8; font-weight: 600;">Pronto</span>
        `;
        valEl = badgeEl.querySelector('.badge-val');
      } else if (entityId === 'media_player.smart_tv_lg_oled_2' || entityId === 'media_player.lg_webos_smart_tv') {
        // Badge Smart TV OLED
        badgeEl = document.createElement('div');
        badgeEl.className = 'device-badge-3d state-off badge-tv';
        badgeEl.dataset.entityId = entityId;
        badgeEl.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;">
            <rect x="2" y="7" width="20" height="15" rx="2" ry="2"></rect>
            <polyline points="17 2 12 7 7 2"></polyline>
          </svg>
          <span class="badge-name">Smart TV OLED</span>
        `;
      } else if (entityId === 'vacuum.deebot') {
        // Badge Robot Aspirapolvere Ecovacs Deebot (100% SVG pulito)
        badgeEl = document.createElement('div');
        badgeEl.className = 'device-badge-3d badge-vacuum';
        badgeEl.dataset.entityId = entityId;
        badgeEl.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;">
            <circle cx="12" cy="12" r="9"></circle>
            <circle cx="12" cy="9" r="2"></circle>
            <path d="M7 16h10"></path>
          </svg>
          <span class="badge-name">Deebot:</span>
          <span class="badge-val" style="color: #38bdf8; font-weight: 600;">Alla base</span>
        `;
        valEl = badgeEl.querySelector('.badge-val');
      } else if (entityId.startsWith('switch.smart_switch_area')) {
        // Badge Impianto Irrigazione Giardino
        const areaNum = entityId.replace('switch.smart_switch_area', '');
        const areaCounts = { '1': '4 gettini', '2': '2 gettini', '3': '5 gettini' };
        badgeEl = document.createElement('div');
        badgeEl.className = 'device-badge-3d state-off badge-irrigation';
        badgeEl.dataset.entityId = entityId;
        badgeEl.innerHTML = `
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;">
            <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"></path>
          </svg>
          <span class="badge-name">Area ${areaNum} (${areaCounts[areaNum] || ''}):</span>
          <span class="badge-val" style="color: #94a3b8; font-weight: 600;">Spento</span>
        `;
        valEl = badgeEl.querySelector('.badge-val');
      } else {
        // Badge standard interruttori / luci / telecamere
        badgeEl = document.createElement('div');
        badgeEl.className = 'device-badge-3d state-off';
        badgeEl.dataset.entityId = entityId;

        dotEl = document.createElement('span');
        dotEl.className = 'badge-indicator';

        const labelEl = document.createElement('span');
        labelEl.className = 'badge-name';
        labelEl.textContent = entData.name || entityId.split('.')[1];

        badgeEl.appendChild(dotEl);
        badgeEl.appendChild(labelEl);
      }

      badgeEl.addEventListener('click', (e) => {
        e.stopPropagation();
        const action = entityId.startsWith('switch.smart_switch_area') ? 'modal' : (entData.action || 'toggle');
        this.handleEntityAction(entityId, action);
      });

      const css2dObj = new CSS2DObject(badgeEl);
      css2dObj.position.copy(center);
      css2dObj.visible = this.badgesVisible;
      if (!this.badgesVisible) {
        badgeEl.style.display = 'none';
      }
      this.scene.add(css2dObj);

      this.deviceBadges.set(entityId, { element: badgeEl, dot: dotEl, valEl, css2dObj, position: center.clone() });
    });
  }

  /**
   * Crea un badge 3D decal fotorealistico ancorato alla mesh del dispositivo.
   * Risolve definitivamente il problema della visibilità da fuori casa e la scala gigantesca:
   * 1. È una vera mesh 3D di 26cm in scala reale.
   * 2. Usa depthTest: true: scompare dietro i muri opachi da fuori casa.
   * 3. Texture Canvas 512x512 ad altissima nitidezza, identica a media_1794392888308_6b9e7328.jpg.
   */
  createThermal3DDecal(entityId, entData, meshes, badgeStyle) {
    const sensorMesh = meshes[0];
    const pos = new THREE.Vector3();
    sensorMesh.getWorldPosition(pos);

    // Nasconde solo il cilindretto grezzo di placeholder di Blender (Sensor_*)
    meshes.forEach((m) => {
      if (m.name && m.name.startsWith('Sensor_')) {
        m.visible = false;
      }
    });

    const isPuffer = badgeStyle === 'puffer_high' || badgeStyle === 'puffer_low';
    const isPufferLow = badgeStyle === 'puffer_low';
    const isCaldaia = badgeStyle === 'caldaia';

    let ringColor = '#ef4444'; // Rosso vivo per Accumulo Alto e Caldaia
    let sublabel = 'Alto';
    let initialVal = '57.9°C';

    if (isPufferLow) {
      ringColor = '#06b6d4'; // Azzurro ciano per Accumulo Basso
      sublabel = 'Basso';
      initialVal = '14.2°C';
    } else if (isCaldaia) {
      ringColor = '#ef4444'; // Rosso vivo per Caldaia
      sublabel = 'Caldaia';
      initialVal = '43.8°C';
    }

    // Canvas dinamico 512x512
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');

    this.renderThermalBadgeCanvas(ctx, initialVal, sublabel, ringColor);

    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;

    const material = new THREE.MeshBasicMaterial({
      map: texture,
      transparent: true,
      depthTest: true,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
      side: THREE.FrontSide,
    });

    let decalMesh;
    if (isPuffer) {
      // Mesh arcuata cilindrica (r=0.304m, 4mm fuori dal raggio di 0.300 dell'accumulo)
      // thetaStart: Math.PI - 0.44 centra perfettamente il settore sulla faccia frontale rivolta verso Nord (-Z Three.js)
      const geom = new THREE.CylinderGeometry(0.304, 0.304, 0.26, 32, 1, true, Math.PI - 0.44, 0.88);
      decalMesh = new THREE.Mesh(geom, material);
      // Il centro dell'accumulo è posizionato a (pos.x, 0.76, 14.85)
      decalMesh.position.set(pos.x, pos.y, 14.85);
    } else {
      // Mesh planare per la faccia piana della caldaia
      // La faccia frontale della caldaia è a Z = 14.79; posizioniamo il decal a 14.786 rivolto a -Z
      const geom = new THREE.PlaneGeometry(0.26, 0.26);
      decalMesh = new THREE.Mesh(geom, material);
      decalMesh.position.set(pos.x, pos.y, 14.786);
      decalMesh.rotation.set(0, Math.PI, 0); // Rivolto verso Nord (camera)
    }

    decalMesh.name = `Decal_${sensorMesh.name}`;
    decalMesh.userData = {
      ha_entity: entityId,
      ha_action: 'modal',
      ha_name: entData.name || entityId,
      isThermalBadge: true,
    };
    decalMesh.visible = true; // Componente 3D reale con quadranti temperatura della centrale termica

    this.scene.add(decalMesh);
    this.interactiveObjects.push(decalMesh);

    this.thermal3DBadges.set(entityId, {
      canvas,
      ctx,
      texture,
      material,
      decalMesh,
      ringColor,
      sublabel,
      currentVal: initialVal,
    });

    console.log(`[InteractionManager] Creato badge 3D Decal per ${entityId} a posizione`, decalMesh.position);
  }

  /**
   * Disegna il quadrante circolare fotorealistico sul canvas 512x512
   */
  renderThermalBadgeCanvas(ctx, val, sublabel, ringColor) {
    ctx.clearRect(0, 0, 512, 512);

    // 1. Sfondo circolare scuro frosted (alto contrasto contro grigio o bianco)
    ctx.beginPath();
    ctx.arc(256, 256, 222, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
    ctx.fill();

    // 2. Anello circolare esterno colorato luminoso (rosso o ciano)
    ctx.beginPath();
    ctx.arc(256, 256, 212, 0, Math.PI * 2);
    ctx.lineWidth = 18;
    ctx.strokeStyle = ringColor;
    ctx.shadowColor = ringColor;
    ctx.shadowBlur = 24;
    ctx.stroke();
    ctx.shadowBlur = 0;

    // 3. Icona termometro vettoriale bianca centrata in alto
    ctx.fillStyle = '#ffffff';
    // Bulbo
    ctx.beginPath();
    ctx.arc(256, 172, 17, 0, Math.PI * 2);
    ctx.fill();
    // Colonna
    ctx.beginPath();
    this.drawRoundedRect(ctx, 248.5, 106, 15, 58, 7.5);
    ctx.fill();
    // Tacche graduate
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(268, 122); ctx.lineTo(276, 122);
    ctx.moveTo(268, 138); ctx.lineTo(276, 138);
    ctx.moveTo(268, 154); ctx.lineTo(276, 154);
    ctx.stroke();

    // 4. Valore temperatura in caratteri grandi e nitidi
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 84px "Inter", "Segoe UI", system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(val, 256, 275);

    // 5. Etichetta descrittiva (Alto, Basso, Caldaia)
    ctx.fillStyle = '#cbd5e1';
    ctx.font = '600 42px "Inter", "Segoe UI", system-ui, sans-serif';
    ctx.fillText(sublabel, 256, 375);
  }

  drawRoundedRect(ctx, x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
  }

  updateBadgeState(entityId, isOn, friendlyState) {
    const badge = this.deviceBadges.get(entityId);
    if (!badge || !badge.element) return;

    if (isOn) {
      badge.element.classList.remove('state-off');
      badge.element.classList.add('state-on');
    } else {
      badge.element.classList.remove('state-on');
      badge.element.classList.add('state-off');
    }

    if (badge.valEl && entityId.startsWith('switch.smart_switch_area')) {
      badge.valEl.textContent = isOn ? 'In funzione' : 'Spento';
      badge.valEl.style.color = isOn ? '#38bdf8' : '#94a3b8';
    } else if (badge.valEl && entityId === 'vacuum.deebot') {
      const s = String(friendlyState || '').toLowerCase();
      if (s === 'cleaning' || s === 'in pulizia') {
        badge.valEl.textContent = 'In pulizia';
        badge.valEl.style.color = '#38bdf8';
      } else if (s === 'returning' || s === 'ritorno alla base') {
        badge.valEl.textContent = 'Ritorno base';
        badge.valEl.style.color = '#f59e0b';
      } else if (s === 'paused' || s === 'in pausa') {
        badge.valEl.textContent = 'In pausa';
        badge.valEl.style.color = '#cbd5e1';
      } else {
        badge.valEl.textContent = 'Alla base';
        badge.valEl.style.color = '#10b981';
      }
    }
  }

  updateSensorState(entityId, state, attributes = {}) {
    // 1. Gestione Badge 3D Decal (Centrale Termica)
    const thermal = this.thermal3DBadges.get(entityId);
    if (thermal) {
      const unit = attributes.unit_of_measurement || '°C';
      const num = parseFloat(state);
      const valStr = !isNaN(num) ? `${num.toFixed(1)}${unit}` : `${state}${unit}`;
      thermal.currentVal = valStr;
      this.renderThermalBadgeCanvas(thermal.ctx, valStr, thermal.sublabel, thermal.ringColor);
      thermal.texture.needsUpdate = true;
      return;
    }

    // 2. Gestione Badge CSS2D Standard
    const badge = this.deviceBadges.get(entityId);
    if (!badge || !badge.valEl) return;

    if (entityId === 'sensor.lavastoviglie_stato_di_funzionamento') {
      const s = String(state).toLowerCase();
      if (s === 'running' || s === 'in funzione') {
        badge.valEl.textContent = 'In funzione';
        badge.valEl.style.color = '#06b6d4';
      } else if (s === 'finito' || s === 'completed') {
        badge.valEl.textContent = 'Finito';
        badge.valEl.style.color = '#10b981';
      } else if (s === 'pronto' || s === 'ready') {
        badge.valEl.textContent = 'Pronto';
        badge.valEl.style.color = '#f59e0b';
      } else {
        badge.valEl.textContent = state;
        badge.valEl.style.color = '#94a3b8';
      }
      return;
    }

    const unit = attributes.unit_of_measurement || '°C';
    const num = parseFloat(state);
    if (!isNaN(num)) {
      badge.valEl.textContent = `${num.toFixed(1)}${unit}`;
    } else {
      badge.valEl.textContent = state;
    }
  }

  /**
   * Mostra o nasconde i badge fluttuanti CSS2D dei dispositivi
   */
  setBadgesVisible(visible) {
    this.badgesVisible = visible !== undefined ? visible : !this.badgesVisible;

    // Badge CSS2D standard dei dispositivi (luci, cancelli, interruttori, elettrodomestici, TV)
    this.deviceBadges.forEach((badge) => {
      if (badge.css2dObj) {
        badge.css2dObj.visible = this.badgesVisible;
      }
      if (badge.element) {
        badge.element.style.display = this.badgesVisible ? '' : 'none';
      }
    });

    console.log(`[InteractionManager] Visibilità badge dispositivi impostata a: ${this.badgesVisible}`);
    return this.badgesVisible;
  }

  /**
   * Alterna la visibilità dei badge
   */
  toggleBadges(visible) {
    return this.setBadgesVisible(visible);
  }

  /**
   * Aggiorna la scala dei badge CSS2D in base alla distanza della camera
   * per evitare che diventino giganteschi nella vista Panoramica.
   */
  update(camera) {
    if (!camera || !this.badgesVisible || this.deviceBadges.size === 0) return;

    const camPos = camera.position;
    this.deviceBadges.forEach((badge) => {
      if (!badge.element || !badge.position) return;
      const dist = camPos.distanceTo(badge.position);

      // Scala progressiva per distanze elevate (oltre 20 metri)
      if (dist > 20.0) {
        const scale = Math.max(0.65, 1.0 - (dist - 20.0) / 38.0);
        badge.element.style.transform = `scale(${scale.toFixed(2)})`;
      } else {
        badge.element.style.transform = 'scale(1)';
      }
    });
  }

  onPointerMove(event) {
    // Su dispositivi touch l'hover non si applica e lascia i mesh evidenziati dopo il tap
    if (event.pointerType === 'touch') {
      this.clearHover();
      return;
    }
    const rect = this.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    this.checkHover();
  }

  checkHover() {
    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.interactiveObjects, true);

    if (intersects.length > 0) {
      const topObj = intersects[0].object;
      if (this.hoveredObject !== topObj) {
        this.clearHover();
        this.hoveredObject = topObj;
        this.domElement.style.cursor = 'pointer';

        // Evidenzia materiale emissivo se presente (clona se condiviso per evitare side-effect grafici)
        if (topObj.material && 'emissive' in topObj.material) {
          if (!topObj.userData._materialCloned) {
            topObj.material = topObj.material.clone();
            topObj.userData._materialCloned = true;
          }
          if (!this.originalEmissive.has(topObj)) {
            this.originalEmissive.set(topObj, topObj.material.emissive.getHex());
          }
          topObj.material.emissive.setHex(0x38bdf8);
        }
      }
    } else {
      this.clearHover();
    }
  }

  clearHover() {
    if (this.hoveredObject) {
      if (this.hoveredObject.material && 'emissive' in this.hoveredObject.material) {
        const orig = this.originalEmissive.get(this.hoveredObject) ?? 0x000000;
        this.hoveredObject.material.emissive.setHex(orig);
      }
      this.hoveredObject = null;
      this.domElement.style.cursor = 'default';
    }
  }

  onPointerDown(event) {
    this._activePointers.add(event.pointerId);
    if (this._activePointers.size > 1) {
      this._wasMultiTouch = true;
      this._pointerDownId = null;
      return;
    }
    if (event.pointerType === 'mouse' && event.button !== 0) return;

    this._wasMultiTouch = false;
    this._pointerDownId = event.pointerId;
    this._pointerDownPos = { x: event.clientX, y: event.clientY };
  }

  onPointerCancel(event) {
    this._activePointers.delete(event.pointerId);
    if (this._pointerDownId === event.pointerId) {
      this._pointerDownId = null;
    }
    if (this._activePointers.size === 0) {
      this._wasMultiTouch = false;
    }
  }

  onPointerUp(event) {
    this._activePointers.delete(event.pointerId);
    const isTracked = this._pointerDownId === event.pointerId && !this._wasMultiTouch;
    if (this._activePointers.size === 0) {
      this._wasMultiTouch = false;
    }
    if (!isTracked) return;
    this._pointerDownId = null;

    // Ignora orbita/pan/drag su mouse e touch oltre 10px di spostamento
    const dx = event.clientX - this._pointerDownPos.x;
    const dy = event.clientY - this._pointerDownPos.y;
    if (Math.hypot(dx, dy) > 10) return;

    const rect = this.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.interactiveObjects, true);

    if (intersects.length > 0) {
      const clickedObj = intersects[0].object;
      let entityId = clickedObj.userData?.ha_entity;
      let action = clickedObj.userData?.ha_action || 'toggle';

      // Risali la gerarchia se userData non è presente direttamente sul child
      let curr = clickedObj;
      while (curr && !entityId) {
        if (curr.userData && curr.userData.ha_entity) {
          entityId = curr.userData.ha_entity;
          action = curr.userData.ha_action || action;
          break;
        }
        curr = curr.parent;
      }

      // Riconoscimento intelligente per qualsiasi mesh gettino / irrigatore
      if (!entityId && clickedObj.name && clickedObj.name.startsWith('Sprinkler_Area')) {
        if (clickedObj.name.includes('Area1')) entityId = 'switch.smart_switch_area1';
        else if (clickedObj.name.includes('Area2')) entityId = 'switch.smart_switch_area2';
        else if (clickedObj.name.includes('Area3')) entityId = 'switch.smart_switch_area3';
        action = 'modal';
      }

      if (entityId) {
        if (entityId.startsWith('switch.smart_switch_area')) {
          action = 'modal';
        }
        this.handleEntityAction(entityId, action);
      }
    }
  }

  handleEntityAction(entityId, action) {
    console.log(`[InteractionManager] Azione '${action}' su entità: ${entityId}`);
    const hasCustomController = deviceRegistry.findControllerForEntity(entityId);
    if (action === 'modal' || hasCustomController) {
      if (this.onOpenModal) {
        this.onOpenModal(entityId);
      }
    } else {
      // Toggle rapido
      if (this.entityBinder) {
        this.entityBinder.toggleEntity(entityId);
      }
    }
  }

  dispose() {
    this.domElement.removeEventListener('pointermove', this.onPointerMove);
    this.domElement.removeEventListener('pointerdown', this.onPointerDown);
    this.domElement.removeEventListener('pointerup', this.onPointerUp);
    this.domElement.removeEventListener('pointercancel', this.onPointerCancel);
  }
}
