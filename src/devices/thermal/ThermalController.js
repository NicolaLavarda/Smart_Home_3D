import { BaseDeviceController } from '../BaseDeviceController.js';
import { ThermalModal } from './ThermalModal.js';

/**
 * ThermalController
 *
 * Controller decentralizzato per la Centrale Termica (Lavanderia):
 * - Acqua calda & Caldaia (`switch.smart_switch_caldaia`, `sensor.minuti_doccia_disponibili`,
 *   `sensor.minuti_di_attesa`, `input_number.minuti_doccia_desiderati`, `input_boolean.doccia_in_corso`)
 * - Programmazione oraria caldaia (`input_datetime.orario_accensione_caldaia`,
 *   `automation.accensione_programmata_caldaia`, `input_datetime.orario_spegnimento_caldaia`,
 *   `automation.spegnimento_programmato_caldaia`)
 * - Temperature & Puffer (`sensor.temperatura_accumulo_alto`, `sensor.temperatura_accumulo_basso`,
 *   `sensor.temperatura_caldaia`, `sensor.temperatura_calda_caldaia`, `sensor.litri_acqua_calda`,
 *   `sensor.minuti_caldaia_accesa`, `sensor.temperatura_esterna_attuale`)
 * - Parametri doccia & Valvola (`input_number.temperatura_doccia`, `input_select.doccia_selezionata`,
 *   `automation.controllo_valvola_acqua_calda`, `switch.valvola_acqua_calda`,
 *   `input_boolean.gestione_automatica_acqua_calda`)
 */
export class ThermalController extends BaseDeviceController {
  constructor(options = {}) {
    super('thermal', {
      name: 'Impianto Termico',
      primaryEntityId: 'switch.smart_switch_caldaia',
      associatedEntityIds: [
        'switch.smart_switch_caldaia',
        'switch.valvola_acqua_calda',
        'input_boolean.gestione_automatica_acqua_calda',
        'input_boolean.doccia_in_corso',
        'sensor.minuti_doccia_disponibili',
        'sensor.minuti_di_attesa',
        'input_number.minuti_doccia_desiderati',
        'input_datetime.orario_accensione_caldaia',
        'automation.accensione_programmata_caldaia',
        'input_datetime.orario_spegnimento_caldaia',
        'automation.spegnimento_programmato_caldaia',
        'input_number.temperatura_doccia',
        'input_select.doccia_selezionata',
        'sensor.temperatura_calda_caldaia',
        'automation.controllo_valvola_acqua_calda',
        'sensor.temperatura_caldaia',
        'sensor.temperatura_accumulo_alto',
        'sensor.temperatura_accumulo_basso',
        'sensor.litri_acqua_calda',
        'sensor.minuti_caldaia_accesa',
        'sensor.temperatura_esterna_attuale',
        ...(options.associatedEntityIds || []),
      ],
      haClient: options.haClient,
    });

    this.subtitle = 'Acqua Calda • Caldaia & Parametri';
    this.modalView = new ThermalModal(this);
    this.isModalOpen = false;
  }

  _readNumber(entityId, fallback = null) {
    const ent = this.getEntity(entityId);
    const val = parseFloat(ent?.state);
    return Number.isFinite(val) ? val : fallback;
  }

  _readNumericBounds(entityId, defaults = { min: 0, max: 100, step: 1 }) {
    const attrs = this.getEntity(entityId)?.attributes || {};
    const min = Number.isFinite(Number(attrs.min)) ? Number(attrs.min) : defaults.min;
    const max = Number.isFinite(Number(attrs.max)) ? Number(attrs.max) : defaults.max;
    const step = Number.isFinite(Number(attrs.step)) && Number(attrs.step) > 0 ? Number(attrs.step) : defaults.step;
    return { min, max, step };
  }

  _formatTimeHHMM(rawState, fallback = '07:00') {
    if (!rawState || typeof rawState !== 'string') return fallback;
    const match = rawState.match(/(\d{2}:\d{2})/);
    return match ? match[1] : fallback;
  }

  _normalizeTimeForHa(hhmm) {
    if (!hhmm || typeof hhmm !== 'string') return null;
    const clean = hhmm.trim();
    if (/^\d{2}:\d{2}:\d{2}$/.test(clean)) return clean;
    if (/^\d{2}:\d{2}$/.test(clean)) return `${clean}:00`;
    return null;
  }

  // --- Stato Acqua Calda & Caldaia ---

  isBoilerOn() {
    return this.getEntity('switch.smart_switch_caldaia')?.state === 'on';
  }

  isShowerInProgress() {
    return this.getEntity('input_boolean.doccia_in_corso')?.state === 'on';
  }

  getShowerMinutes() {
    return this._readNumber('sensor.minuti_doccia_disponibili', 0);
  }

  getWaitMinutes() {
    return this._readNumber('sensor.minuti_di_attesa', 0);
  }

  getDesiredShowerMinutes() {
    return this._readNumber('input_number.minuti_doccia_desiderati', 12);
  }

  getDesiredShowerBounds() {
    return this._readNumericBounds('input_number.minuti_doccia_desiderati', { min: 1, max: 60, step: 1 });
  }

  /**
   * Riproduce fedelmente la logica dinamica della card Home Assistant dell'utente
   * per lo stato dell'acqua calda e i tempi di attesa.
   */
  getSmartAdvice() {
    const minutiDisponibili = this.getShowerMinutes() ?? 0;
    const minutiAttesa = this.getWaitMinutes() ?? 0;
    const caldaiaAccesa = this.isBoilerOn();
    const docciaInCorso = this.isShowerInProgress();

    const minDispRound = Math.round(minutiDisponibili);
    const minAttRound = Math.round(minutiAttesa);
    const parts = [];

    if (docciaInCorso) {
      parts.push('Qualcuno è già in doccia. Ad ogni modo,');
    }

    let tone = 'waiting';
    if (minutiDisponibili > 0 && minutiAttesa < 1) {
      tone = 'ready';
      parts.push(`Hai a disposizione ${minDispRound} minuti di acqua calda.`);
      if (caldaiaAccesa) {
        parts.push('La caldaia è accesa, non hai bisogno di attendere.');
      } else {
        parts.push('Se non ti sono sufficienti accendi la caldaia, ma non hai bisogno di attendere.');
      }
    } else if (minutiDisponibili > 0 && minutiAttesa > 0) {
      tone = caldaiaAccesa ? 'heating' : 'waiting';
      parts.push(`Hai a disposizione ${minDispRound} minuti di acqua calda.`);
      if (caldaiaAccesa) {
        parts.push(`La caldaia è già accesa, attendi ancora ${minAttRound} minuti se ne vuoi di più.`);
      } else {
        parts.push(`Se non ti sono sufficienti accendi la caldaia e attendi ${minAttRound} minuti.`);
      }
    } else {
      tone = caldaiaAccesa ? 'heating' : 'waiting';
      if (caldaiaAccesa) {
        parts.push(`La caldaia è già accesa, attendi ancora ${minAttRound} minuti per avere l'acqua calda.`);
      } else {
        parts.push(`Devi aspettare ${minAttRound} minuti per avere l'acqua calda. Accendi la caldaia per iniziare.`);
      }
    }

    return { text: parts.join(' '), tone };
  }

  // --- Programmazione Caldaia ---

  getBoilerScheduleOnTime() {
    const raw = this.getEntity('input_datetime.orario_accensione_caldaia')?.state;
    return this._formatTimeHHMM(raw, '06:30');
  }

  isBoilerScheduleOnEnabled() {
    return this.getEntity('automation.accensione_programmata_caldaia')?.state === 'on';
  }

  getBoilerScheduleOffTime() {
    const raw = this.getEntity('input_datetime.orario_spegnimento_caldaia')?.state;
    return this._formatTimeHHMM(raw, '22:30');
  }

  isBoilerScheduleOffEnabled() {
    return this.getEntity('automation.spegnimento_programmato_caldaia')?.state === 'on';
  }

  // --- Parametri Doccia & Valvola ---

  getShowerTemp() {
    return this._readNumber('input_number.temperatura_doccia', 39);
  }

  getShowerTempBounds() {
    return this._readNumericBounds('input_number.temperatura_doccia', { min: 30, max: 48, step: 0.5 });
  }

  getSelectedShower() {
    return this.getEntity('input_select.doccia_selezionata')?.state || 'Doccia Bagno';
  }

  getShowerOptions() {
    const opts = this.getEntity('input_select.doccia_selezionata')?.attributes?.options;
    if (Array.isArray(opts) && opts.length > 0) {
      return opts.map((o) => String(o));
    }
    const current = this.getSelectedShower();
    return current ? [current] : ['Doccia Bagno', 'Doccia Lavanderia'];
  }

  isAutoValveOn() {
    return this.getEntity('automation.controllo_valvola_acqua_calda')?.state === 'on';
  }

  isManualValveVisible() {
    // Condizione di visibilità HA: visibile solo quando automation.controllo_valvola_acqua_calda è 'off'
    return this.getEntity('automation.controllo_valvola_acqua_calda')?.state === 'off';
  }

  isHotWaterValveOn() {
    return this.getEntity('switch.valvola_acqua_calda')?.state === 'on';
  }

  isAutoManagementOn() {
    return this.getEntity('input_boolean.gestione_automatica_acqua_calda')?.state === 'on';
  }

  // --- Temperature & Metriche ---

  getBoilerHotTemp() {
    return this._readNumber('sensor.temperatura_calda_caldaia', null);
  }

  getBoilerTemp() {
    return this._readNumber('sensor.temperatura_caldaia', 43.8);
  }

  getPufferHighTemp() {
    return this._readNumber('sensor.temperatura_accumulo_alto', 57.9);
  }

  getPufferLowTemp() {
    return this._readNumber('sensor.temperatura_accumulo_basso', 14.2);
  }

  getHotWaterLiters() {
    return this._readNumber('sensor.litri_acqua_calda', 68);
  }

  getBoilerRuntimeHours() {
    return this._readNumber('sensor.minuti_caldaia_accesa', 0.0);
  }

  getOutdoorTemp() {
    return this._readNumber('sensor.temperatura_esterna_attuale', null);
  }

  getSummaryLabel() {
    const boiler = this.isBoilerOn() ? 'Caldaia ON' : 'Caldaia OFF';
    const mins = this.getShowerMinutes();
    if (mins !== null && Number.isFinite(mins)) {
      return `${boiler} • ${Math.round(mins)} min doccia`;
    }
    const high = this.getPufferHighTemp();
    return high !== null ? `${boiler} • ${high.toFixed(1)}°C` : boiler;
  }

  // --- Azioni Home Assistant ---

  toggleBoiler() {
    if (!this.haClient) return;
    this.haClient.callService('switch', 'toggle', {
      entity_id: 'switch.smart_switch_caldaia',
    });
  }

  togglePower() {
    this.toggleBoiler();
  }

  setDesiredShowerMinutes(value) {
    if (!this.haClient) return;
    const { min, max } = this.getDesiredShowerBounds();
    const clamped = Math.max(min, Math.min(max, Math.round(Number(value) * 10) / 10));
    if (!Number.isFinite(clamped)) return;
    this.haClient.callService('input_number', 'set_value', {
      entity_id: 'input_number.minuti_doccia_desiderati',
      value: clamped,
    });
  }

  stepDesiredShowerMinutes(direction) {
    const { step } = this.getDesiredShowerBounds();
    const current = this.getDesiredShowerMinutes() ?? 10;
    this.setDesiredShowerMinutes(current + (direction >= 0 ? step : -step));
  }

  setBoilerScheduleOnTime(hhmm) {
    if (!this.haClient) return;
    const time = this._normalizeTimeForHa(hhmm);
    if (!time) return;
    this.haClient.callService('input_datetime', 'set_datetime', {
      entity_id: 'input_datetime.orario_accensione_caldaia',
      time,
    });
  }

  toggleBoilerScheduleOn() {
    if (!this.haClient) return;
    this.haClient.callService('automation', 'toggle', {
      entity_id: 'automation.accensione_programmata_caldaia',
    });
  }

  setBoilerScheduleOffTime(hhmm) {
    if (!this.haClient) return;
    const time = this._normalizeTimeForHa(hhmm);
    if (!time) return;
    this.haClient.callService('input_datetime', 'set_datetime', {
      entity_id: 'input_datetime.orario_spegnimento_caldaia',
      time,
    });
  }

  toggleBoilerScheduleOff() {
    if (!this.haClient) return;
    this.haClient.callService('automation', 'toggle', {
      entity_id: 'automation.spegnimento_programmato_caldaia',
    });
  }

  setShowerTemp(value) {
    if (!this.haClient) return;
    const { min, max } = this.getShowerTempBounds();
    const clamped = Math.max(min, Math.min(max, Math.round(Number(value) * 10) / 10));
    if (!Number.isFinite(clamped)) return;
    this.haClient.callService('input_number', 'set_value', {
      entity_id: 'input_number.temperatura_doccia',
      value: clamped,
    });
  }

  stepShowerTemp(direction) {
    const { step } = this.getShowerTempBounds();
    const current = this.getShowerTemp() ?? 39;
    this.setShowerTemp(current + (direction >= 0 ? step : -step));
  }

  selectShower(option) {
    if (!this.haClient || !option) return;
    this.haClient.callService('input_select', 'select_option', {
      entity_id: 'input_select.doccia_selezionata',
      option: String(option),
    });
  }

  toggleAutoValve() {
    if (!this.haClient) return;
    this.haClient.callService('automation', 'toggle', {
      entity_id: 'automation.controllo_valvola_acqua_calda',
    });
  }

  toggleHotWaterValve() {
    if (!this.haClient) return;
    this.haClient.callService('switch', 'toggle', {
      entity_id: 'switch.valvola_acqua_calda',
    });
  }

  toggleAutoManagement() {
    if (!this.haClient) return;
    this.haClient.callService('input_boolean', 'toggle', {
      entity_id: 'input_boolean.gestione_automatica_acqua_calda',
    });
  }

  bind3D(meshes, scene, context) {
    super.bind3D(meshes, scene, context);
    // Assicura che lo switch a parete apra il pannello di gestione dell'impianto termico
    (meshes || []).forEach((mesh) => {
      if (mesh?.userData?.ha_entity === 'switch.smart_switch_caldaia') {
        mesh.userData.ha_action = 'modal';
      }
    });
  }

  update3D(stateObj, allEntities) {
    super.update3D(stateObj, allEntities);
    if (this.isModalOpen && this.modalView) {
      this.modalView.updateLive();
    }
  }

  renderModal(container, entity, context = {}) {
    this.isModalOpen = true;
    if (context && context.haClient) {
      this.haClient = context.haClient;
    }
    this.modalView.render(container, context);
  }

  onModalClose() {
    this.isModalOpen = false;
    if (this.modalView) {
      this.modalView.container = null;
    }
  }
}
