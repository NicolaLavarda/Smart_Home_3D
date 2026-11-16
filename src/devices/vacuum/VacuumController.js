import { BaseDeviceController } from '../BaseDeviceController.js';
import { VacuumModal } from './VacuumModal.js';
import * as THREE from 'three';

/**
 * VacuumController
 * 
 * Controller decentralizzato per il Robot Aspirapolvere Ecovacs Deebot X1 Turbo:
 * - Monitora stato di funzionamento (docked, cleaning, returning, paused, error)
 * - Riceve telemetria real-time ad alta frequenza su topic MQTT (homeassistant/deebot/pose)
 * - Trasforma le coordinate SLAM dToF (mm) in coordinate mondiali 3D Three.js
 * - Muove in tempo reale il robot con interpolazione fluida (LERP/SLERP) a 60 FPS
 * - Anima il LED e la luce del robottino e della stazione di ricarica
 * - Rende il pannello modale ad alta fedeltà con visualizzazione telemetrica live
 */
export class VacuumController extends BaseDeviceController {
  constructor(options = {}) {
    super('vacuum', {
      name: 'Ecovacs Deebot',
      subtitle: 'vacuum.deebot • Sala da pranzo',
      primaryEntityId: 'vacuum.deebot',
      associatedEntityIds: [
        'vacuum.deebot',
        'sensor.deebot_batteria',
        'sensor.deebot_area_cleaned',
        'sensor.deebot_cleaning_duration',
        'sensor.deebot_total_area_cleaned',
        'sensor.deebot_total_cleaning_duration',
        'sensor.deebot_total_cleanings',
        'select.deebot_water_flow_level',
        'select.deebot_active_map',
        'switch.deebot_advanced_mode',
        'switch.deebot_carpet_auto_boost_suction',
        'binary_sensor.deebot_mop_attached',
        'button.deebot_relocate',
        'image.deebot_map',
        'sensor.deebot_main_brush_lifespan',
        'sensor.deebot_filter_lifespan',
        'sensor.deebot_round_mop_lifespan',
        'sensor.deebot_side_brush_lifespan',
        'sensor.deebot_unit_care_lifespan',
        ...(options.associatedEntityIds || []),
      ],
      haClient: options.haClient,
    });

    this.modalView = new VacuumModal(this);

    // Riferimenti mesh 3D
    this.robotPivot = null;
    this.robotBodyMesh = null;
    this.ledMesh = null;
    this.dockLedMesh = null;

    // Coordinate di riposo alla base (parete Est della sala da pranzo, orientata a Ovest)
    this.dockPosition = new THREE.Vector3(13.63, 0.00, 1.65);
    this.dockYaw = -Math.PI / 2; // -90 gradi (guarda verso -X, dentro la stanza)

    // Parametri di calibrazione tra mappa Ecovacs (ruotata di 90° antiorario) e planimetria 3D
    this.calibration = {
      scale: 1.0,       // Scala reale 1:1 metrica (1 mm LiDAR = 1 mm reale)
      invertZ: true,    // DeltaX negativo di Ecovacs corrisponde a Sud (+Z Three.js)
      invertX: true,    // DeltaY positivo di Ecovacs corrisponde a Ovest (-X Three.js, verso il salotto)
      offsetX: 0.0,
      offsetZ: 0.0,
    };

    // Vettori di interpolazione cinematica live
    this.targetPosition = this.dockPosition.clone();
    this.targetQuaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, this.dockYaw, 0));

    // Telemetria MQTT
    this.mqttTopic = 'homeassistant/deebot/pose';
    this.mqttConnected = false;
    this.lastTelemetry = null;
    this.lastMqttTimestamp = 0;
    this.mockPatrolTimer = 0;

    this.animationTimer = 0;
    this.isModalOpen = false;
    this.cameraController = null;
  }

  // --- GETTERS STATO & ATTRIBUTI ---

  getRawState() {
    const ent = this.getEntity('vacuum.deebot');
    return ent?.state || 'docked';
  }

  getStateLabel() {
    const s = this.getRawState().toLowerCase();
    switch (s) {
      case 'docked':
        return 'Alla base';
      case 'cleaning':
        return 'In pulizia';
      case 'returning':
        return 'Ritorno alla base';
      case 'paused':
        return 'In pausa';
      case 'idle':
        return 'Inattivo';
      case 'error':
        return 'In errore';
      default:
        return s.charAt(0).toUpperCase() + s.slice(1);
    }
  }

  getBattery() {
    const battEnt = this.getEntity('sensor.deebot_batteria');
    if (battEnt && battEnt.state !== undefined && battEnt.state !== 'unknown' && battEnt.state !== 'unavailable') {
      const val = parseFloat(battEnt.state);
      if (!isNaN(val)) return Math.max(0, Math.min(100, Math.round(val)));
    }
    const vac = this.getEntity('vacuum.deebot');
    const val = vac?.attributes?.battery_level;
    if (val !== undefined) return Math.max(0, Math.min(100, Math.round(val)));
    return 100;
  }

  getFanSpeed() {
    const vac = this.getEntity('vacuum.deebot');
    return vac?.attributes?.fan_speed || 'normal';
  }

  getFanSpeedLabel(speed = null) {
    const sp = speed || this.getFanSpeed();
    switch (sp.toLowerCase()) {
      case 'quiet':
        return 'Silenzioso';
      case 'normal':
        return 'Normale';
      case 'max':
        return 'Massima';
      case 'max_plus':
        return 'Max+';
      default:
        return sp;
    }
  }

  getWaterFlow() {
    const ent = this.getEntity('select.deebot_water_flow_level');
    return ent?.state || 'medium';
  }

  getWaterFlowLabel(flow = null) {
    const fl = flow || this.getWaterFlow();
    switch (fl.toLowerCase()) {
      case 'low':
        return 'Basso';
      case 'medium':
        return 'Medio';
      case 'high':
        return 'Alto';
      default:
        return fl;
    }
  }

  getActiveMap() {
    const ent = this.getEntity('select.deebot_active_map');
    return ent?.state || 'Piano terra';
  }

  getAreaCleaned() {
    const ent = this.getEntity('sensor.deebot_area_cleaned');
    const val = parseFloat(ent?.state);
    return !isNaN(val) ? val : 69;
  }

  getCleaningDuration() {
    const ent = this.getEntity('sensor.deebot_cleaning_duration');
    const val = parseFloat(ent?.state);
    return !isNaN(val) ? Math.round(val) : 54;
  }

  getTotalAreaCleaned() {
    const ent = this.getEntity('sensor.deebot_total_area_cleaned');
    const val = parseFloat(ent?.state);
    return !isNaN(val) ? Math.round(val) : 20088;
  }

  getTotalCleaningDuration() {
    const ent = this.getEntity('sensor.deebot_total_cleaning_duration');
    const val = parseFloat(ent?.state);
    return !isNaN(val) ? Math.round(val) : 364;
  }

  getTotalCleanings() {
    const ent = this.getEntity('sensor.deebot_total_cleanings');
    const val = parseInt(ent?.state, 10);
    return !isNaN(val) ? val : 516;
  }

  isMopAttached() {
    const ent = this.getEntity('binary_sensor.deebot_mop_attached');
    return ent?.state === 'on';
  }

  isCarpetBoostOn() {
    const ent = this.getEntity('switch.deebot_carpet_auto_boost_suction');
    return ent?.state === 'on';
  }

  isAdvancedModeOn() {
    const ent = this.getEntity('switch.deebot_advanced_mode');
    return ent?.state === 'on';
  }

  getConsumables() {
    const getVal = (id, def) => {
      const ent = this.getEntity(id);
      const num = parseFloat(ent?.state);
      return !isNaN(num) ? Math.max(0, Math.min(100, Math.round(num * 10) / 10)) : def;
    };

    return {
      mainBrush: getVal('sensor.deebot_main_brush_lifespan', 56.7),
      sideBrush: getVal('sensor.deebot_side_brush_lifespan', 97.1),
      filter: getVal('sensor.deebot_filter_lifespan', 96.5),
      roundMop: getVal('sensor.deebot_round_mop_lifespan', 99.9),
      unitCare: getVal('sensor.deebot_unit_care_lifespan', 85.9),
    };
  }

  // --- AZIONI SERVIZIO HOME ASSISTANT ---

  start() {
    if (!this.haClient) return;
    this.haClient.callService('vacuum', 'start', { entity_id: 'vacuum.deebot' });
  }

  pause() {
    if (!this.haClient) return;
    this.haClient.callService('vacuum', 'pause', { entity_id: 'vacuum.deebot' });
  }

  stop() {
    if (!this.haClient) return;
    this.haClient.callService('vacuum', 'stop', { entity_id: 'vacuum.deebot' });
  }

  returnToBase() {
    if (!this.haClient) return;
    this.haClient.callService('vacuum', 'return_to_base', { entity_id: 'vacuum.deebot' });
  }

  locate() {
    if (!this.haClient) return;
    this.haClient.callService('vacuum', 'locate', { entity_id: 'vacuum.deebot' });
  }

  setFanSpeed(speed) {
    if (!this.haClient) return;
    this.haClient.callService('vacuum', 'set_fan_speed', {
      entity_id: 'vacuum.deebot',
      fan_speed: speed,
    });
  }

  setWaterFlow(level) {
    if (!this.haClient) return;
    this.haClient.callService('select', 'select_option', {
      entity_id: 'select.deebot_water_flow_level',
      option: level,
    });
  }

  toggleCarpetBoost() {
    if (!this.haClient) return;
    this.haClient.callService('switch', 'toggle', {
      entity_id: 'switch.deebot_carpet_auto_boost_suction',
    });
  }

  toggleAdvancedMode() {
    if (!this.haClient) return;
    this.haClient.callService('switch', 'toggle', {
      entity_id: 'switch.deebot_advanced_mode',
    });
  }

  relocate() {
    if (!this.haClient) return;
    this.haClient.callService('button', 'press', {
      entity_id: 'button.deebot_relocate',
    });
  }

  // --- BINDING 3D, PIVOT HIERARCHY & TELEMETRIA MQTT ---

  bind3D(meshes, scene, context) {
    super.bind3D(meshes, scene, context);

    if (context && context.cameraController) {
      this.cameraController = context.cameraController;
    }

    // 1. Crea il Pivot Group mobile del Robot per muovere tutti i componenti rigidamente
    if (!this.robotPivot) {
      this.robotPivot = new THREE.Group();
      this.robotPivot.name = 'Ecovacs_Deebot_Robot_Group';
      // Posiziona e orienta il pivot alla base PRIMA di fare attach per azzerare l'offset relativo
      this.robotPivot.position.copy(this.dockPosition);
      this.robotPivot.quaternion.setFromEuler(new THREE.Euler(0, this.dockYaw, 0));
      scene.add(this.robotPivot);
      this.robotPivot.updateMatrixWorld(true);

      const robotMeshNames = [
        'Ecovacs_Deebot_Body',
        'Ecovacs_Deebot_Bumper',
        'Ecovacs_Deebot_Lidar',
        'Ecovacs_Deebot_Lidar_Ring',
        'Ecovacs_Deebot_Power_Button',
      ];

      robotMeshNames.forEach((name) => {
        const mesh = scene.getObjectByName(name);
        if (mesh) {
          mesh.updateMatrixWorld(true);
          this.robotPivot.attach(mesh);
        }
      });

      console.log(`[VacuumController] Gruppo cinematico creato con ${this.robotPivot.children.length} componenti del robot.`);
    }

    // 2. Trova le mesh pertinenti per le animazioni luminose
    scene.traverse((node) => {
      if (node.isMesh) {
        if (node.name === 'Ecovacs_Deebot_Body') {
          this.robotBodyMesh = node;
        } else if (node.name === 'Ecovacs_Deebot_Power_Button') {
          this.ledMesh = node;
          if (this.ledMesh.material) {
            this.ledMesh.material = this.ledMesh.material.clone();
          }
        } else if (node.name === 'Ecovacs_Deebot_Dock_LED') {
          this.dockLedMesh = node;
          if (this.dockLedMesh.material) {
            this.dockLedMesh.material = this.dockLedMesh.material.clone();
          }
        }
      }
    });

    // 3. Sottoscrizione MQTT in tempo reale via HAClient WebSocket
    if (this.haClient && typeof this.haClient.subscribeMqtt === 'function') {
      this.haClient.subscribeMqtt(this.mqttTopic, (telemetry) => {
        this.onMqttTelemetry(telemetry);
      });
      // Sottoscrivi anche al topic secondario breve 'deebot/pose'
      this.haClient.subscribeMqtt('deebot/pose', (telemetry) => {
        this.onMqttTelemetry(telemetry);
      });
      console.log(`[VacuumController] In ascolto telemetria MQTT su '${this.mqttTopic}'`);
    }
  }

  /**
   * Elabora il pacchetto JSON di telemetria MQTT ricevuto
   * @param {Object} data - Payload contenente robot {x, y, angle} e dock {x, y}
   */
  onMqttTelemetry(data) {
    if (!data) return;

    try {
      const robot = data.robot || data.position || data;
      const dock = data.dock || data.charger || { x: 0, y: 0, angle: 180 };

      if (robot && robot.x !== undefined && robot.y !== undefined) {
        // Delta grezzi in millimetri rispetto alla stazione di ricarica
        const deltaX_mm = Number(robot.x) - Number(dock.x || 0);
        const deltaY_mm = Number(robot.y) - Number(dock.y || 0);

        // Conversione millimetri -> metri
        const rawDx_m = deltaX_mm * 0.001;
        const rawDy_m = deltaY_mm * 0.001;

        // Mappatura cinematica con rotazione 90° antioraria:
        // Nella mappa Ecovacs, l'asse X corrisponde all'asse Nord/Sud della casa (Sud = +Z Three.js).
        // L'asse Y di Ecovacs corrisponde all'asse Est/Ovest della casa (Ovest = -X Three.js, interno stanza).
        const worldDeltaZ = (this.calibration.invertZ ? -rawDx_m : rawDx_m) * this.calibration.scale + this.calibration.offsetZ;
        const worldDeltaX = (this.calibration.invertX ? -rawDy_m : rawDy_m) * this.calibration.scale + this.calibration.offsetX;

        const targetX = this.dockPosition.x + worldDeltaX;
        const targetZ = this.dockPosition.z + worldDeltaZ;

        // Calcolo rotazione Yaw (0 rad = verso Sud / +Z; -PI/2 = verso Ovest / -X)
        const angleDeg = robot.angle !== undefined ? Number(robot.angle) : Number(robot.a || 0);
        const yaw = THREE.MathUtils.degToRad(angleDeg - 180.0);

        this.targetPosition.set(targetX, 0.00, targetZ);
        this.targetQuaternion.setFromEuler(new THREE.Euler(0, yaw, 0));

        this.mqttConnected = true;
        this.lastMqttTimestamp = Date.now();
        this.lastTelemetry = {
          ...data,
          targetX: targetX.toFixed(2),
          targetZ: targetZ.toFixed(2),
          deltaX_m: worldDeltaX.toFixed(2),
          deltaZ_m: worldDeltaZ.toFixed(2),
          angleDeg: Math.round(angleDeg),
          scale: this.calibration.scale,
          timestamp: Date.now(),
        };
      }
    } catch (err) {
      console.warn('[VacuumController] Errore parsing telemetria MQTT:', err);
    }
  }

  setCalibrationScale(scale) {
    this.calibration.scale = Number(scale);
    if (this.lastTelemetry) {
      this.onMqttTelemetry(this.lastTelemetry);
    }
  }

  update3D(stateObj, allEntities) {
    super.update3D(stateObj, allEntities);
    if (this.modalView && this.isModalOpen) {
      this.modalView.updateLive();
    }
  }

  onTick(delta) {
    this.animationTimer += delta;
    const st = this.getRawState().toLowerCase();

    // 1. Se il robottino è 'docked' e non riceve telemetria attiva, resta agganciato al dock
    if (st === 'docked' && (!this.mqttConnected || Date.now() - this.lastMqttTimestamp > 5000)) {
      this.targetPosition.copy(this.dockPosition);
      this.targetQuaternion.setFromEuler(new THREE.Euler(0, this.dockYaw, 0));
    }

    // 2. Simulazione di pattugliamento se in modalità Demo/Mock durante 'cleaning'
    if (this.haClient && this.haClient.isMockMode && st === 'cleaning' && !this.mqttConnected) {
      this.simulateMockPatrol(delta);
    }

    // 3. Interpolazione LERP cinematica morbida (60 FPS fluidi, senza scatti)
    if (this.robotPivot) {
      const factor = Math.min(1.0, delta * 5.5);
      this.robotPivot.position.lerp(this.targetPosition, factor);
      this.robotPivot.quaternion.slerp(this.targetQuaternion, factor);
    }

    // 4. Effetti LED reattivi
    if (this.ledMesh && this.ledMesh.material) {
      if (st === 'cleaning') {
        const pulse = Math.sin(this.animationTimer * 4.0) * 0.5 + 1.5;
        this.ledMesh.material.emissiveIntensity = pulse;
      } else if (st === 'returning') {
        const pulse = Math.sin(this.animationTimer * 2.0) * 0.4 + 1.2;
        this.ledMesh.material.emissiveIntensity = pulse;
      } else {
        this.ledMesh.material.emissiveIntensity = 1.0;
      }
    }
  }

  /**
   * Simula un percorso realistico a serpentina nella sala da pranzo in modalità Demo/Mock
   */
  simulateMockPatrol(delta) {
    this.mockPatrolTimer += delta * 0.6;
    // Pattugliamento tra X: [10.5 .. 13.2], Z: [2.0 .. 5.5]
    const offsetX = Math.sin(this.mockPatrolTimer * 0.7) * 1.3 + 1.4;
    const offsetZ = Math.cos(this.mockPatrolTimer * 0.35) * 1.6 + 1.8;
    const yaw = Math.atan2(-Math.sin(this.mockPatrolTimer * 0.7), Math.cos(this.mockPatrolTimer * 0.35));

    this.targetPosition.set(this.dockPosition.x - offsetX, 0.00, this.dockPosition.z + offsetZ);
    this.targetQuaternion.setFromEuler(new THREE.Euler(0, yaw, 0));

    this.lastTelemetry = {
      state: 'cleaning',
      deltaX_m: offsetX.toFixed(2),
      deltaZ_m: offsetZ.toFixed(2),
      targetX: (this.dockPosition.x - offsetX).toFixed(2),
      targetZ: (this.dockPosition.z + offsetZ).toFixed(2),
      angleDeg: Math.round(THREE.MathUtils.radToDeg(yaw)),
      timestamp: Date.now(),
      simulated: true,
    };
  }

  renderModal(container, entity, context) {
    this.isModalOpen = true;
    if (context && context.haClient) {
      this.haClient = context.haClient;
    }
    if (context && context.cameraController) {
      this.cameraController = context.cameraController;
    }
    this.modalView.render(container, context);
  }

  onModalClose() {
    this.isModalOpen = false;
    if (this.modalView) {
      this.modalView.container = null;
    }
  }

  getRobotWorldPosition() {
    const pos = new THREE.Vector3();
    if (this.robotPivot) {
      this.robotPivot.getWorldPosition(pos);
    } else {
      pos.copy(this.dockPosition);
    }
    if (!Number.isFinite(pos.x) || !Number.isFinite(pos.y) || !Number.isFinite(pos.z)) {
      pos.copy(this.dockPosition);
    }
    pos.y = Math.max(0.2, pos.y + 0.2);
    return pos;
  }

  zoomToRobot() {
    const camCtrl = this.cameraController || this.modalView?.context?.cameraController;
    if (!camCtrl) return;

    const followOffset = new THREE.Vector3(-2.1, 1.65, 2.1);
    camCtrl.startFollowing(
      () => this.getRobotWorldPosition(),
      followOffset,
      1.1,
      46
    );
  }
}
