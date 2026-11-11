import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

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
    this.deviceBadges = new Map(); // entity_id -> { element, css2dObject }

    this.onPointerMove = this.onPointerMove.bind(this);
    this.onPointerDown = this.onPointerDown.bind(this);

    this.domElement.addEventListener('pointermove', this.onPointerMove);
    this.domElement.addEventListener('pointerdown', this.onPointerDown);
  }

  registerEntities(haEntitiesMap) {
    this.interactiveObjects = [];
    haEntitiesMap.forEach((meshes, entityId) => {
      meshes.forEach((mesh) => {
        if (mesh.isMesh) {
          this.interactiveObjects.push(mesh);
        }
      });
    });
    console.log(`[InteractionManager] Registrati ${this.interactiveObjects.length} mesh interattivi.`);
  }

  createDeviceBadges(manifest, haEntitiesMap) {
    if (!manifest || !manifest.ha_entities) return;

    Object.entries(manifest.ha_entities).forEach(([entityId, entData]) => {
      const meshes = haEntitiesMap.get(entityId);
      if (!meshes || meshes.length === 0) return;

      // Calcola centro medio dei mesh associati
      const center = new THREE.Vector3();
      meshes.forEach((m) => {
        const p = new THREE.Vector3();
        m.getWorldPosition(p);
        center.add(p);
      });
      center.divideScalar(meshes.length);
      center.y += 0.45; // Posiziona leggermente sopra l'oggetto

      // Crea elemento HTML per CSS2D
      const badgeEl = document.createElement('div');
      badgeEl.className = 'device-badge-3d state-off';
      badgeEl.dataset.entityId = entityId;

      const dotEl = document.createElement('span');
      dotEl.className = 'badge-indicator';

      const labelEl = document.createElement('span');
      labelEl.className = 'badge-name';
      labelEl.textContent = entData.name || entityId.split('.')[1];

      badgeEl.appendChild(dotEl);
      badgeEl.appendChild(labelEl);

      badgeEl.addEventListener('click', (e) => {
        e.stopPropagation();
        this.handleEntityAction(entityId, entData.action || 'toggle');
      });

      const css2dObj = new CSS2DObject(badgeEl);
      css2dObj.position.copy(center);
      this.scene.add(css2dObj);

      this.deviceBadges.set(entityId, { element: badgeEl, dot: dotEl, css2dObj });
    });
  }

  updateBadgeState(entityId, isOn, friendlyState) {
    const badge = this.deviceBadges.get(entityId);
    if (!badge) return;

    if (isOn) {
      badge.element.classList.remove('state-off');
      badge.element.classList.add('state-on');
    } else {
      badge.element.classList.remove('state-on');
      badge.element.classList.add('state-off');
    }
  }

  onPointerMove(event) {
    const rect = this.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    this.checkHover();
  }

  checkHover() {
    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.interactiveObjects, false);

    if (intersects.length > 0) {
      const topObj = intersects[0].object;
      if (this.hoveredObject !== topObj) {
        this.clearHover();
        this.hoveredObject = topObj;
        this.domElement.style.cursor = 'pointer';

        // Evidenzia materiale
        if (topObj.material && 'emissive' in topObj.material) {
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
    // Intercetta click su mesh 3D
    const rect = this.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.interactiveObjects, false);

    if (intersects.length > 0) {
      const clickedObj = intersects[0].object;
      const entityId = clickedObj.userData.ha_entity;
      const action = clickedObj.userData.ha_action || 'toggle';

      if (entityId) {
        this.handleEntityAction(entityId, action);
      }
    }
  }

  handleEntityAction(entityId, action) {
    console.log(`[InteractionManager] Azione '${action}' su entità: ${entityId}`);
    if (action === 'modal') {
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
  }
}

