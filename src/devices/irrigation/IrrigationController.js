import * as THREE from 'three';
import { BaseDeviceController } from '../BaseDeviceController.js';
import { WaterSpraySystem } from './WaterSpraySystem.js';
import { IrrigationModal } from './IrrigationModal.js';

/**
 * IrrigationController
 * 
 * Controller decentralizzato per l'impianto di irrigazione del giardino.
 * Mappa esattamente le entità della card Home Assistant personalizzata dell'utente:
 * - Ciclo Automatico Generale: `input_boolean.irrigazione_attiva`
 * - Abilitazione singole zone: `input_boolean.area_1`, `input_boolean.area_2`, `input_boolean.area_3`
 * - Timer durata per zona (minuti): `input_number.tempo_area_1`, `input_number.tempo_area_2`, `input_number.tempo_area_3`
 * - Valvole/Switch fisici per i gettini pop-up (25cm):
 *   • `switch.smart_switch_area1` -> 4 gettini nell'Area 1 (Prato Sud)
 *   • `switch.smart_switch_area2` -> 2 gettini nell'Area 2 (Corte Est)
 *   • `switch.smart_switch_area3` -> 5 gettini nell'Area 3 (Prato Nord & Viale)
 * - Coordina il sistema particellare 3D a 60 fps e la rotazione/estensione dei gettini
 */
export class IrrigationController extends BaseDeviceController {
  constructor(options = {}) {
    super('irrigation', {
      name: 'Controllo Irrigazione',
      primaryEntityId: 'input_boolean.irrigazione_attiva',
      associatedEntityIds: [
        'input_boolean.irrigazione_attiva',
        'input_boolean.area_1',
        'input_boolean.area_2',
        'input_boolean.area_3',
        'input_number.tempo_area_1',
        'input_number.tempo_area_2',
        'input_number.tempo_area_3',
        'switch.smart_switch_area1',
        'switch.smart_switch_area2',
        'switch.smart_switch_area3',
        ...(options.associatedEntityIds || []),
      ],
      haClient: options.haClient,
    });

    this.subtitle = 'Giardino • Cicli & Zone';
    this.modalView = new IrrigationModal(this);
    this.isModalOpen = false;
    this.waterSpray = null;
    this.scene = null;
    this.sprinklersConfig = this.initSprinklersConfig();
    this.sprinklerMeshes = new Map();
  }

  initSprinklersConfig() {
    const DEG2RAD = Math.PI / 180;

    return [
      // AREA 1 (Prato Sud): 4 gettini -> switch.smart_switch_area1
      {
        id: 'Sprinkler_Area1_1',
        name: 'Gettino Area 1 - 1',
        area: 1,
        entityId: 'switch.smart_switch_area1',
        position: new THREE.Vector3(-13.50, 0.0, 31.50),
        minAngle: 280 * DEG2RAD,
        maxAngle: 355 * DEG2RAD,
        sweepSpeed: 0.65,
        throwSpeed: 7.2,
      },
      {
        id: 'Sprinkler_Area1_2',
        name: 'Gettino Area 1 - 2',
        area: 1,
        entityId: 'switch.smart_switch_area1',
        position: new THREE.Vector3(-1.50, 0.0, 24.20),
        minAngle: 10 * DEG2RAD,
        maxAngle: 170 * DEG2RAD,
        sweepSpeed: 0.85,
        throwSpeed: 6.8,
      },
      {
        id: 'Sprinkler_Area1_3',
        name: 'Gettino Area 1 - 3',
        area: 1,
        entityId: 'switch.smart_switch_area1',
        position: new THREE.Vector3(4.50, 0.0, 26.80),
        minAngle: 10 * DEG2RAD,
        maxAngle: 170 * DEG2RAD,
        sweepSpeed: 0.80,
        throwSpeed: 6.5,
      },
      {
        id: 'Sprinkler_Area1_4',
        name: 'Gettino Area 1 - 4',
        area: 1,
        entityId: 'switch.smart_switch_area1',
        position: new THREE.Vector3(12.30, 0.0, 25.80),
        minAngle: 100 * DEG2RAD,
        maxAngle: 260 * DEG2RAD,
        sweepSpeed: 0.75,
        throwSpeed: 6.8,
      },

      // AREA 2 (Corte Est): 2 gettini -> switch.smart_switch_area2
      {
        id: 'Sprinkler_Area2_1',
        name: 'Gettino Area 2 - 1',
        area: 2,
        entityId: 'switch.smart_switch_area2',
        position: new THREE.Vector3(6.89, 0.0, 9.60),
        minAngle: 280 * DEG2RAD,
        maxAngle: 365 * DEG2RAD,
        sweepSpeed: 0.70,
        throwSpeed: 7.5,
      },
      {
        id: 'Sprinkler_Area2_2',
        name: 'Gettino Area 2 - 2',
        area: 2,
        entityId: 'switch.smart_switch_area2',
        position: new THREE.Vector3(13.28, 0.0, 16.58),
        minAngle: 100 * DEG2RAD,
        maxAngle: 185 * DEG2RAD,
        sweepSpeed: 0.70,
        throwSpeed: 7.5,
      },

      // AREA 3 (Prato Nord & Viale Ovest): 5 gettini -> switch.smart_switch_area3
      {
        id: 'Sprinkler_Area3_1',
        name: 'Gettino Area 3 - 1',
        area: 3,
        entityId: 'switch.smart_switch_area3',
        position: new THREE.Vector3(-7.80, 0.0, 2.50),
        minAngle: 290 * DEG2RAD,
        maxAngle: 375 * DEG2RAD,
        sweepSpeed: 0.70,
        throwSpeed: 6.0,
      },
      {
        id: 'Sprinkler_Area3_2',
        name: 'Gettino Area 3 - 2',
        area: 3,
        entityId: 'switch.smart_switch_area3',
        position: new THREE.Vector3(-1.60, 0.0, 5.40),
        minAngle: 100 * DEG2RAD,
        maxAngle: 240 * DEG2RAD,
        sweepSpeed: 0.70,
        throwSpeed: 6.0,
      },
      {
        id: 'Sprinkler_Area3_3',
        name: 'Gettino Area 3 - 3',
        area: 3,
        entityId: 'switch.smart_switch_area3',
        position: new THREE.Vector3(-5.09, 0.0, 7.96),
        minAngle: -30 * DEG2RAD,
        maxAngle: 130 * DEG2RAD,
        sweepSpeed: 0.85,
        throwSpeed: 6.5,
      },
      {
        id: 'Sprinkler_Area3_4',
        name: 'Gettino Area 3 - 4',
        area: 3,
        entityId: 'switch.smart_switch_area3',
        position: new THREE.Vector3(-1.60, 0.0, 14.95),
        minAngle: 110 * DEG2RAD,
        maxAngle: 250 * DEG2RAD,
        sweepSpeed: 0.80,
        throwSpeed: 6.5,
      },
      {
        id: 'Sprinkler_Area3_5',
        name: 'Gettino Area 3 - 5',
        area: 3,
        entityId: 'switch.smart_switch_area3',
        position: new THREE.Vector3(3.80, 0.0, 17.00),
        minAngle: 170 * DEG2RAD,
        maxAngle: 310 * DEG2RAD,
        sweepSpeed: 0.75,
        throwSpeed: 6.0,
      },
    ];
  }

  bind3D(meshes, scene, context) {
    super.bind3D(meshes, scene, context);
    this.scene = scene;

    if (!this.waterSpray) {
      this.waterSpray = new WaterSpraySystem(this.scene, this.sprinklersConfig);
    }

    this.sprinklerMeshes.clear();
    const foundMeshes = new Set();

    if (meshes && meshes.length > 0) {
      meshes.forEach((mesh) => {
        this.registerSprinklerMesh(mesh);
        foundMeshes.add(mesh.name);
      });
    }

    // Scansiona la scena per trovare le mesh Blender esportate
    this.scene.traverse((node) => {
      if (node.isMesh && node.name.startsWith('Sprinkler_') && !node.name.includes('_Base') && !node.name.includes('_Nozzle')) {
        this.registerSprinklerMesh(node);
        foundMeshes.add(node.name);
      }
    });

    // Fallback procedurale per massima robustezza
    this.sprinklersConfig.forEach((cfg) => {
      if (!this.sprinklerMeshes.has(cfg.id)) {
        const procMesh = this.createProceduralSprinklerMesh(cfg, context);
        this.scene.add(procMesh);
        this.registerSprinklerMesh(procMesh);
      }
    });

    // Registra tutte le parti delle mesh (stelo, ugello e ghiera a terra) come oggetti interattivi cliccabili
    const allInteractiveSprinklers = [];
    this.scene.traverse((node) => {
      if (node.isMesh && node.name.startsWith('Sprinkler_')) {
        const cfg = this.sprinklersConfig.find((c) => node.name.startsWith(c.id));
        if (cfg) {
          node.userData.ha_entity = cfg.entityId;
          node.userData.ha_action = 'modal';
          node.userData.ha_name = cfg.name;
          node.userData.ha_ui_type = 'irrigation';
          allInteractiveSprinklers.push(node);

          if (context && context.interactionManager) {
            context.interactionManager.addInteractiveObject(node);
          }
        }
      }
    });

    // Assicura che haEntitiesMap contenga i riferimenti per gli switch delle 3 aree
    if (context && context.haEntitiesMap) {
      allInteractiveSprinklers.forEach((node) => {
        const ent = node.userData.ha_entity;
        if (ent) {
          if (!context.haEntitiesMap.has(ent)) {
            context.haEntitiesMap.set(ent, []);
          }
          const list = context.haEntitiesMap.get(ent);
          if (!list.includes(node)) list.push(node);
        }
      });
    }

    this.waterSpray.bindMeshes(this.sprinklerMeshes);

    console.log(
      `[IrrigationController] Impianto collegato: ${this.sprinklersConfig.length} gettini 3D sincronizzati (${allInteractiveSprinklers.length} mesh interattive).`
    );
  }

  registerSprinklerMesh(mesh) {
    const id = mesh.name;
    this.sprinklerMeshes.set(id, mesh);
    mesh.castShadow = true;
    mesh.receiveShadow = true;

    const cfg = this.sprinklersConfig.find((c) => id.startsWith(c.id));
    if (cfg) {
      mesh.userData.ha_entity = cfg.entityId;
      mesh.userData.ha_action = 'modal';
      mesh.userData.ha_name = cfg.name;
      mesh.userData.ha_ui_type = 'irrigation';

      mesh.traverse((child) => {
        if (child.isMesh) {
          child.userData.ha_entity = cfg.entityId;
          child.userData.ha_action = 'modal';
          child.userData.ha_name = cfg.name;
          child.userData.ha_ui_type = 'irrigation';
        }
      });
    }
  }

  createProceduralSprinklerMesh(cfg, context = null) {
    const group = new THREE.Group();
    group.name = cfg.id;
    group.position.copy(cfg.position);
    group.userData.ha_entity = cfg.entityId;
    group.userData.ha_action = 'modal';

    // Ghiera circolare a terra
    const collarGeom = new THREE.CylinderGeometry(0.045, 0.045, 0.025, 20);
    const collarMat = new THREE.MeshStandardMaterial({
      color: 0x1e242b,
      roughness: 0.65,
      metalness: 0.1,
    });
    const collarMesh = new THREE.Mesh(collarGeom, collarMat);
    collarMesh.position.y = 0.0125;
    collarMesh.name = `${cfg.id}_Base`;
    collarMesh.userData.ha_entity = cfg.entityId;
    collarMesh.userData.ha_action = 'modal';
    this.scene.add(collarMesh);

    // Torretta pop-up da 25cm
    const riserGeom = new THREE.CylinderGeometry(0.016, 0.016, 0.25, 18);
    const riserMat = new THREE.MeshStandardMaterial({
      color: 0x334155,
      roughness: 0.35,
      metalness: 0.3,
    });
    const riserMesh = new THREE.Mesh(riserGeom, riserMat);
    riserMesh.position.y = 0.125;
    riserMesh.name = cfg.id;
    riserMesh.userData.ha_entity = cfg.entityId;
    riserMesh.userData.ha_action = 'modal';

    // Ugello
    const nozzleGeom = new THREE.CylinderGeometry(0.022, 0.022, 0.03, 18);
    const nozzleMat = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      roughness: 0.45,
      metalness: 0.2,
    });
    const nozzleMesh = new THREE.Mesh(nozzleGeom, nozzleMat);
    nozzleMesh.position.y = 0.25 - 0.015;
    nozzleMesh.name = `${cfg.id}_Nozzle`;
    nozzleMesh.userData.ha_entity = cfg.entityId;
    nozzleMesh.userData.ha_action = 'modal';

    const riserGroup = new THREE.Group();
    riserGroup.name = cfg.id;
    riserGroup.position.copy(cfg.position);
    riserGroup.userData.ha_entity = cfg.entityId;
    riserGroup.userData.ha_action = 'modal';
    riserGroup.add(riserMesh);
    riserGroup.add(nozzleMesh);

    if (context && context.interactionManager) {
      context.interactionManager.addInteractiveObject(collarMesh);
      context.interactionManager.addInteractiveObject(riserMesh);
      context.interactionManager.addInteractiveObject(nozzleMesh);
    }

    return riserGroup;
  }

  // --- GETTERS STATO ENTITÀ HOME ASSISTANT ---

  isCycleActive() {
    const ent = this.getEntity('input_boolean.irrigazione_attiva');
    return ent?.state === 'on';
  }

  isAreaEnabled(areaNum) {
    const ent = this.getEntity(`input_boolean.area_${areaNum}`);
    return ent?.state === 'on';
  }

  getAreaTime(areaNum) {
    const ent = this.getEntity(`input_number.tempo_area_${areaNum}`);
    const val = parseFloat(ent?.state);
    return !isNaN(val) ? Math.round(val) : (areaNum === 1 ? 10 : areaNum === 2 ? 5 : 15);
  }

  isAreaValveOn(areaNum) {
    const ent = this.getEntity(`switch.smart_switch_area${areaNum}`);
    return ent?.state === 'on';
  }

  getTotalDurationMinutes() {
    let sum = 0;
    [1, 2, 3].forEach((num) => {
      if (this.isAreaEnabled(num)) {
        sum += this.getAreaTime(num);
      }
    });
    return sum;
  }

  getActiveValvesCount() {
    let count = 0;
    if (this.isAreaValveOn(1)) count += 4;
    if (this.isAreaValveOn(2)) count += 2;
    if (this.isAreaValveOn(3)) count += 5;
    return count;
  }

  // --- AZIONI E CHIAMATE SERVIZI HOME ASSISTANT ---

  toggleCycle() {
    if (this.haClient) {
      this.haClient.callService('input_boolean', 'toggle', {
        entity_id: 'input_boolean.irrigazione_attiva',
      });
    }
  }

  setCycleState(turnOn) {
    if (this.haClient) {
      this.haClient.callService('input_boolean', turnOn ? 'turn_on' : 'turn_off', {
        entity_id: 'input_boolean.irrigazione_attiva',
      });
    }
  }

  toggleAreaEnable(areaNum) {
    if (this.haClient) {
      this.haClient.callService('input_boolean', 'toggle', {
        entity_id: `input_boolean.area_${areaNum}`,
      });
    }
  }

  setAreaTime(areaNum, minutes) {
    const clamped = Math.max(5, Math.min(120, Math.round(minutes / 5) * 5));
    if (this.haClient) {
      this.haClient.callService('input_number', 'set_value', {
        entity_id: `input_number.tempo_area_${areaNum}`,
        value: clamped,
      });
    }
  }

  stepAreaTime(areaNum, deltaMinutes = 5) {
    const current = this.getAreaTime(areaNum);
    const nextVal = Math.round((current + deltaMinutes) / 5) * 5;
    this.setAreaTime(areaNum, nextVal);
  }

  toggleAreaValve(areaNum) {
    if (this.haClient) {
      this.haClient.callService('switch', 'toggle', {
        entity_id: `switch.smart_switch_area${areaNum}`,
      });
    }
  }

  turnOffAllValves() {
    if (this.haClient) {
      [1, 2, 3].forEach((num) => {
        this.haClient.callService('switch', 'turn_off', {
          entity_id: `switch.smart_switch_area${num}`,
        });
      });
    }
  }

  setAllValves(turnOn) {
    const service = turnOn ? 'turn_on' : 'turn_off';
    if (this.haClient) {
      [1, 2, 3].forEach((num) => {
        this.haClient.callService('switch', service, {
          entity_id: `switch.smart_switch_area${num}`,
        });
      });
    }
  }

  togglePower(entityId = null) {
    if (entityId) {
      const match = entityId.match(/switch\.smart_switch_area([123])/);
      if (match) {
        this.toggleAreaValve(parseInt(match[1], 10));
        return;
      }
    }
    this.toggleCycle();
  }

  // --- RENDER LOOP & 3D UPDATE ---

  update3D(stateObj, allEntities) {
    super.update3D(stateObj, allEntities);

    // I gettini salgono e spruzzano acqua se la valvola dell'area è attiva
    if (this.waterSpray) {
      this.waterSpray.setAreaState(1, this.isAreaValveOn(1));
      this.waterSpray.setAreaState(2, this.isAreaValveOn(2));
      this.waterSpray.setAreaState(3, this.isAreaValveOn(3));
    }

    if (this.modalView && this.isModalOpen) {
      this.modalView.updateLiveState();
    }
  }

  onTick(delta) {
    if (this.waterSpray) {
      this.waterSpray.update(delta);
    }
  }

  renderModal(container, entity, context) {
    this.isModalOpen = true;
    if (context && context.haClient) {
      this.haClient = context.haClient;
    }
    if (this.modalView) {
      this.modalView.render(container, context);
    }
  }

  onModalClose() {
    this.isModalOpen = false;
    if (this.modalView) {
      this.modalView.container = null;
      this.modalView.context = null;
    }
  }

  dispose() {
    if (this.waterSpray) {
      this.waterSpray.dispose();
      this.waterSpray = null;
    }
    this.sprinklerMeshes.clear();
  }
}
