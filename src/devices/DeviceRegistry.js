import { TVController } from './tv/index.js';
import { DishwasherController } from './dishwasher/index.js';
import { IrrigationController } from './irrigation/index.js';
import { VacuumController } from './vacuum/index.js';
import { SecurityCameraController } from './camera/index.js';
import { ThermalController } from './thermal/index.js';

/**
 * DeviceRegistry
 * 
 * Registro decentralizzato e scalabile dei dispositivi smart digital twin.
 * Coordina il ciclo di vita, il mapping delle entità Home Assistant,
 * il binding 3D e il routing dei pannelli modali per ciascun dispositivo.
 * 
 * Struttura scalabile:
 * Per aggiungere un nuovo dispositivo (es. Lavastoviglie, Aspirapolvere, Telecamera Frigate),
 * basta creare una cartella in `src/devices/<nome>/` con una classe che eredita da `BaseDeviceController`
 * e registrarla qui con `deviceRegistry.register(...)`.
 */
export class DeviceRegistry {
  constructor() {
    this.controllers = new Map();
    this.initDefaultDevices();
  }

  initDefaultDevices() {
    // 1. Modulo Smart TV LG webOS
    this.register(new TVController());

    // 2. Modulo Lavastoviglie Smart Cucina
    this.register(new DishwasherController());

    // 3. Modulo Impianto Irrigazione Smart Giardino (3 Aree, 11 Gettini)
    this.register(new IrrigationController());

    // 4. Modulo Robot Aspirapolvere Ecovacs Deebot
    this.register(new VacuumController());

    // 5. Modulo Telecamera Sicurezza Reolink (Cam_Carraio)
    this.register(new SecurityCameraController());

    // 6. Modulo Impianto Termico (Caldaia & Accumulo Puffer in Lavanderia)
    this.register(new ThermalController());
  }

  /**
   * Registra un nuovo controller di dispositivo
   * @param {BaseDeviceController} controller 
   */
  register(controller) {
    if (!controller || !controller.id) {
      console.warn('[DeviceRegistry] Tentativo di registrare un controller non valido:', controller);
      return;
    }
    this.controllers.set(controller.id, controller);
    console.log(`[DeviceRegistry] Registrato modulo dispositivo: '${controller.id}' (${controller.name})`);
  }

  /**
   * Restituisce un controller tramite il suo identificatore univoco
   */
  get(id) {
    return this.controllers.get(id) || null;
  }

  /**
   * Trova il controller associato a un'entità Home Assistant (es. media_player.lg_webos_smart_tv)
   */
  findControllerForEntity(entityId) {
    if (!entityId) return null;
    for (const controller of this.controllers.values()) {
      if (controller.matchesEntity(entityId)) {
        return controller;
      }
    }
    return null;
  }

  /**
   * Trova il controller associato a una mesh 3D
   */
  findControllerForMesh(mesh) {
    if (!mesh || !mesh.userData) return null;
    const entityId = mesh.userData.ha_entity || mesh.userData.ha_alt_entity;
    if (entityId) {
      return this.findControllerForEntity(entityId);
    }
    return null;
  }

  /**
   * Collega tutti i dispositivi registrati alle rispettive mesh 3D trovate nella scena
   */
  bind3D(haEntitiesMap, scene, context) {
    for (const controller of this.controllers.values()) {
      const monitoredEntities = controller.getMonitoredEntityIds();
      const allMeshes = [];

      monitoredEntities.forEach((entId) => {
        const meshes = haEntitiesMap.get(entId);
        if (meshes && meshes.length > 0) {
          meshes.forEach((m) => {
            if (!allMeshes.includes(m)) allMeshes.push(m);
          });
        }
      });

      // Se non trovate direttamente tramite entità esatta (es. alias o nome Blender)
      if (allMeshes.length === 0 && controller.id === 'tv') {
        scene.traverse((node) => {
          if (node.isMesh && (node.name === 'TV_Salotto_Screen' || node.name === 'TV_Salotto_Bezel')) {
            if (!allMeshes.includes(node)) allMeshes.push(node);
          }
        });
      } else if (allMeshes.length === 0 && controller.id === 'dishwasher') {
        scene.traverse((node) => {
          if (node.isMesh && node.name.startsWith('Lavastoviglie')) {
            if (!allMeshes.includes(node)) allMeshes.push(node);
          }
        });
      } else if (allMeshes.length === 0 && controller.id === 'irrigation') {
        scene.traverse((node) => {
          if (node.isMesh && node.name.startsWith('Sprinkler_') && !node.name.includes('_Base') && !node.name.includes('_Nozzle')) {
            if (!allMeshes.includes(node)) allMeshes.push(node);
          }
        });
      } else if (allMeshes.length === 0 && controller.id === 'vacuum') {
        scene.traverse((node) => {
          if (node.isMesh && node.name.startsWith('Ecovacs_Deebot_')) {
            if (!allMeshes.includes(node)) allMeshes.push(node);
          }
        });
      } else if (allMeshes.length === 0 && controller.id === 'security_camera') {
        scene.traverse((node) => {
          if (node.isMesh && (node.name === 'Security_Cam_Body' || node.name === 'Security_Cam_Pole_Pillar')) {
            if (!allMeshes.includes(node)) allMeshes.push(node);
          }
        });
      }

      if (allMeshes.length > 0 || controller.id === 'irrigation' || controller.id === 'vacuum' || controller.id === 'security_camera' || controller.id === 'thermal') {
        controller.bind3D(allMeshes, scene, context);
        console.log(`[DeviceRegistry] Mesh 3D collegate a '${controller.id}': ${allMeshes.length} nodi.`);
      }
    }
  }

  /**
   * Notifica gli aggiornamenti di stato provenienti da Home Assistant ai controller
   * solo quando almeno una delle entità monitorate dal controller è effettivamente cambiata.
   */
  update3D(entities) {
    if (!entities) return;
    if (!this._controllerSnapshots) {
      this._controllerSnapshots = new Map();
    }

    for (const controller of this.controllers.values()) {
      const monitored = controller.getMonitoredEntityIds();
      let prevSnap = this._controllerSnapshots.get(controller.id);
      let changed = !prevSnap;

      if (!changed) {
        for (let i = 0; i < monitored.length; i++) {
          const eid = monitored[i];
          const curObj = entities[eid];
          const prevObj = prevSnap.get(eid);
          if (
            curObj !== prevObj &&
            !(curObj && prevObj && curObj.state === prevObj.state && curObj.last_updated && curObj.last_updated === prevObj.last_updated)
          ) {
            changed = true;
            break;
          }
        }
      }

      if (!changed) continue;

      const nextSnap = new Map();
      for (let i = 0; i < monitored.length; i++) {
        const eid = monitored[i];
        nextSnap.set(eid, entities[eid]);
      }
      this._controllerSnapshots.set(controller.id, nextSnap);

      const primaryId = controller.primaryEntityId;
      const stateObj = entities[primaryId] || this.findStateInAssociated(controller, entities);
      if (stateObj) {
        controller.update3D(stateObj, entities);
      }
    }
  }

  findStateInAssociated(controller, entities) {
    const domain = controller.primaryEntityId ? controller.primaryEntityId.split('.')[0] : '';
    for (const entId of controller.associatedEntityIds) {
      if (domain && !entId.startsWith(domain + '.')) continue;
      if (entities[entId]) return entities[entId];
    }
    return null;
  }

  /**
   * Render loop tick per animazioni dei dispositivi
   */
  update(delta) {
    for (const controller of this.controllers.values()) {
      controller.onTick(delta);
    }
  }

  dispose() {
    for (const controller of this.controllers.values()) {
      controller.dispose();
    }
    this.controllers.clear();
  }
}

// Istanza singleton condivisa
export const deviceRegistry = new DeviceRegistry();

