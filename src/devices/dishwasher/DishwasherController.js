import { BaseDeviceController } from '../BaseDeviceController.js';
import { DishwasherModal } from './DishwasherModal.js';
import * as THREE from 'three';

/**
 * DishwasherController
 * 
 * Controller decentralizzato per la lavastoviglie smart:
 * - Monitora stato di funzionamento, programma selezionato, avanzamento % e orario di fine
 * - Gestisce accensione, avvio programma (script), arresto (button) e opzioni speciali
 * - Anima in 3D il display LED della lavastoviglie in cucina (Lavastoviglie_Display)
 * - Rende il pannello di controllo modale ad alta definizione
 */
export class DishwasherController extends BaseDeviceController {
  constructor(options = {}) {
    super('dishwasher', {
      name: 'Lavastoviglie Cucina',
      primaryEntityId: 'sensor.lavastoviglie_stato_di_funzionamento',
      associatedEntityIds: [
        'sensor.lavastoviglie_stato_di_funzionamento',
        'switch.lavastoviglie_potenza',
        'select.lavastoviglie_programma_selezionato',
        'sensor.lavastoviglie_orario_di_fine_del_programma',
        'sensor.lavastoviglie_avanzamento_del_programma',
        'switch.lavastoviglie_extra_dry',
        'switch.lavastoviglie_half_load',
        'switch.lavastoviglie_hygiene',
        'switch.lavastoviglie_vario_speed',
        'switch.lavastoviglie_silence_on_demand',
        'sensor.lavastoviglie_sale_quasi_vuoto',
        'sensor.lavastoviglie_brillantante_quasi_vuoto',
        'sensor.lavastoviglie_porta',
        'button.lavastoviglie_stop_program',
        'script.avvio_programma',
        ...(options.associatedEntityIds || []),
      ],
      haClient: options.haClient,
    });

    this.subtitle = 'Cucina • Programmi & Avanzamento';
    this.modalView = new DishwasherModal(this);
    this.displayMesh = null;
    this.doorPivot = null;
    this.currentDoorAngle = 0.0;
    this.targetDoorAngle = 0.0;
    this.maxDoorAngle = -THREE.MathUtils.degToRad(40); // -40 gradi di rotazione verso l'esterno
    this.animationTimer = 0;
    this.isModalOpen = false;
  }

  isPoweredOn() {
    const pwr = this.getEntity('switch.lavastoviglie_potenza');
    if (pwr && pwr.state) {
      return pwr.state === 'on';
    }
    const st = this.getStatus().toLowerCase();
    return st !== 'off' && st !== 'non disponibile' && st !== 'unavailable' && st !== 'sconosciuto';
  }

  getStatus() {
    const ent = this.getEntity('sensor.lavastoviglie_stato_di_funzionamento');
    return ent?.state || 'Pronto';
  }

  getProgram() {
    const sel = this.getEntity('select.lavastoviglie_programma_selezionato');
    const raw = sel?.state || 'Auto 45°-65°C';
    let clean = raw.replace(/^.*?_program_/, '');
    clean = clean.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    return clean || 'Auto 45°-65°C';
  }

  getRawProgram() {
    const sel = this.getEntity('select.lavastoviglie_programma_selezionato');
    return sel?.state || '';
  }

  getEndTime() {
    const end = this.getEntity('sensor.lavastoviglie_orario_di_fine_del_programma');
    const raw = end?.state;
    if (!raw || raw === 'unavailable' || raw === 'unknown') return '--:--';
    try {
      const dt = new Date(raw);
      if (isNaN(dt.getTime())) return raw;
      return dt.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', hour12: false });
    } catch {
      return '--:--';
    }
  }

  getProgress() {
    const prg = this.getEntity('sensor.lavastoviglie_avanzamento_del_programma');
    const val = parseFloat(prg?.state);
    if (isNaN(val)) return 0;
    return Math.max(0, Math.min(100, Math.round(val)));
  }

  isOptionActive(optionEntityId) {
    const ent = this.getEntity(optionEntityId);
    return ent?.state === 'on';
  }

  isDoorOpen() {
    const door = this.getEntity('sensor.lavastoviglie_porta');
    if (!door) return false;
    const s = String(door.state).toLowerCase().trim();
    return s === 'on' || s === 'open' || s === 'aperta' || s === 'true' || s === 'opened';
  }

  updateDoorState() {
    const isOpen = this.isDoorOpen();
    this.targetDoorAngle = isOpen ? this.maxDoorAngle : 0.0;
  }

  toggleDoor() {
    const isOpen = this.isDoorOpen();
    const nextState = isOpen ? 'closed' : 'open';
    if (this.haClient) {
      if (typeof this.haClient.setMockEntityState === 'function') {
        this.haClient.setMockEntityState('sensor.lavastoviglie_porta', nextState);
      } else if (this.haClient.isMockMode && this.haClient.mockEntities && this.haClient.mockEntities['sensor.lavastoviglie_porta']) {
        this.haClient.mockEntities['sensor.lavastoviglie_porta'].state = nextState;
        this.haClient.notifyEntities({ ...this.haClient.mockEntities });
      } else {
        this.haClient.callService('homeassistant', 'toggle', {
          entity_id: 'sensor.lavastoviglie_porta',
        });
      }
    }
  }

  isSaltLow() {
    const salt = this.getEntity('sensor.lavastoviglie_sale_quasi_vuoto');
    if (!salt) return false;
    const s = String(salt.state).toLowerCase();
    return s === 'on' || s === 'true' || s === 'scarso' || s === 'quasi vuoto';
  }

  isRinseAidLow() {
    const rinse = this.getEntity('sensor.lavastoviglie_brillantante_quasi_vuoto');
    if (!rinse) return false;
    const s = String(rinse.state).toLowerCase();
    return s === 'on' || s === 'true' || s === 'scarso' || s === 'quasi vuoto';
  }

  // --- AZIONI SMART DISHWASHER ---

  togglePower() {
    if (!this.haClient) return;
    this.haClient.callService('switch', 'toggle', {
      entity_id: 'switch.lavastoviglie_potenza',
    });
  }

  startProgram() {
    if (!this.haClient) return;
    this.haClient.callService('script', 'avvio_programma', {});
  }

  stopProgram() {
    if (!this.haClient) return;
    this.haClient.callService('button', 'press', {
      entity_id: 'button.lavastoviglie_stop_program',
    });
  }

  selectProgram(programOption) {
    if (!this.haClient) return;
    this.haClient.callService('select', 'select_option', {
      entity_id: 'select.lavastoviglie_programma_selezionato',
      option: programOption,
    });
  }

  toggleOption(optionEntityId) {
    if (!this.haClient) return;
    this.haClient.callService('switch', 'toggle', {
      entity_id: optionEntityId,
    });
  }

  // --- BINDING 3D & FEEDBACK LUMINOSO & APERTURA PORTA ---

  bind3D(meshes, scene, context) {
    super.bind3D(meshes, scene, context);

    if (context && context.haClient) {
      this.haClient = context.haClient;
    }

    // Assicura che le matrici world della scena siano aggiornate
    scene.updateMatrixWorld(true);

    // 1. Configura cerniera inferiore e pivot per l'apertura dello sportello a 40°
    if (!this.doorPivot) {
      // Hinge alla base dell'anta (Y = 0.130, Z = 7.090, centrato a X = 8.465)
      const hingePos = new THREE.Vector3(8.465, 0.130, 7.090);
      this.doorPivot = new THREE.Group();
      this.doorPivot.name = 'Lavastoviglie_Door_Pivot';
      this.doorPivot.position.copy(hingePos);
      scene.add(this.doorPivot);
      this.doorPivot.updateMatrixWorld(true);

      const doorMeshNames = [
        'Lavastoviglie',
        'Lavastoviglie_Bugna',
        'Lavastoviglie_Pannello_Comandi',
        'Lavastoviglie_Display',
        'Lavastoviglie_Maniglia'
      ];

      doorMeshNames.forEach((name) => {
        const mesh = scene.getObjectByName(name);
        if (mesh) {
          mesh.updateMatrixWorld(true);
          this.doorPivot.attach(mesh);
        }
      });

      console.log(`[DishwasherController] Cerniera porta configurata con ${this.doorPivot.children.length} componenti dell'anta.`);
    }

    // Cerca la mesh del display LED / pannello comandi
    this.displayMesh = scene.getObjectByName('Lavastoviglie_Display');

    if (this.displayMesh) {
      // Clona materiale per non condividere modifiche emissive accidentali
      if (this.displayMesh.material) {
        this.displayMesh.material = this.displayMesh.material.clone();
      }
      this.update3DDisplayLighting();
    }

    // Inizializza stato porta in base ad HA
    this.updateDoorState();
    this.currentDoorAngle = this.targetDoorAngle;
    if (this.doorPivot) {
      this.doorPivot.rotation.x = this.currentDoorAngle;
    }
  }

  update3DDisplayLighting() {
    if (!this.displayMesh || !this.displayMesh.material) return;
    const mat = this.displayMesh.material;
    const status = this.getStatus().toLowerCase();
    const isRunning = status === 'running' || status === 'in funzione' || this.getProgress() > 0;
    const isFinished = status === 'finito' || status === 'completed';
    const isReady = status === 'pronto' || status === 'ready';

    if (isRunning) {
      mat.color = new THREE.Color('#06b6d4');
      mat.emissive = new THREE.Color('#06b6d4');
      mat.emissiveIntensity = 1.6;
    } else if (isFinished) {
      mat.color = new THREE.Color('#10b981');
      mat.emissive = new THREE.Color('#10b981');
      mat.emissiveIntensity = 1.0;
    } else if (isReady) {
      mat.color = new THREE.Color('#f59e0b');
      mat.emissive = new THREE.Color('#f59e0b');
      mat.emissiveIntensity = 0.8;
    } else {
      mat.color = new THREE.Color('#1e293b');
      mat.emissive = new THREE.Color('#020617');
      mat.emissiveIntensity = 0.05;
    }
  }

  update3D(stateObj, allEntities) {
    super.update3D(stateObj, allEntities);
    this.update3DDisplayLighting();
    this.updateDoorState();
    if (this.modalView && this.isModalOpen) {
      this.modalView.updateLive();
    }
  }

  onTick(delta) {
    this.animationTimer += delta;
    const status = this.getStatus().toLowerCase();
    const isRunning = status === 'running' || status === 'in funzione' || this.getProgress() > 0;

    if (isRunning && this.displayMesh && this.displayMesh.material) {
      // Pulsazione sottile ed elegante del display cyan in funzione
      const pulse = Math.sin(this.animationTimer * 3.5) * 0.35 + 1.25;
      this.displayMesh.material.emissiveIntensity = pulse;
    }

    // Transizione fluida apertura / chiusura porta a 40° attorno alla cerniera inferiore
    if (this.doorPivot) {
      const diff = this.targetDoorAngle - this.currentDoorAngle;
      if (Math.abs(diff) > 0.0002) {
        // Damping fisico con decelerazione morbida
        const t = Math.min(1.0, delta * 5.0);
        this.currentDoorAngle += diff * t;
        if (Math.abs(this.targetDoorAngle - this.currentDoorAngle) < 0.0005) {
          this.currentDoorAngle = this.targetDoorAngle;
        }
        this.doorPivot.rotation.x = this.currentDoorAngle;
      }
    }
  }

  renderModal(container, entity, context) {
    this.isModalOpen = true;
    if (context && context.haClient) {
      this.haClient = context.haClient;
    }
    this.modalView.render(container);
  }

  onModalClose() {
    this.isModalOpen = false;
    if (this.modalView) {
      this.modalView.container = null;
    }
  }
}
