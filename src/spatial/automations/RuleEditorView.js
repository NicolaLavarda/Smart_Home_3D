/**
 * RuleEditorView.js
 *
 * Guided 3-step WHEN / IF / THEN rule builder:
 * - Step 1: Quando scatta (triggers + opt-in pre-triggers + context-aware fields)
 * - Step 2: Solo se (optional condition tree with calm empty state + <= operator)
 * - Step 3: Cosa fa (actions + send_notification builder + custom message & template chips)
 * - Opzioni avanzate inside collapsed <details>
 */

import { icon } from '../../ui/icons.js';
import {
  ACTION_TYPE_LABELS,
  CONDITION_TYPE_LABELS,
  NOTIFICATION_TEMPLATE_VARS,
  TRIGGER_TYPE_LABELS,
  buildRuleSummaryItalian,
  createBlankPreTriggerStage,
  createBlankTrigger,
  defaultActionForType,
  defaultConditionParamsForType,
  defaultTriggerParamsForType,
  escapeHtml,
  getAvailableEntities,
  getHaServiceSuggestions,
  roundClean,
  sanitizeControlId,
} from './RuleDraftModel.js';

export class RuleEditorView {
  constructor(studio) {
    this.studio = studio;
  }

  _ctrl(prefix, path, key) {
    const id = sanitizeControlId(`auto-${prefix}-${path}-${key}`);
    return `id="${id}" name="${id}"`;
  }

  _detailsAttrs(detailsId) {
    const isOpen = this.studio._openDetailsIds?.has(detailsId);
    return `data-details-id="${escapeHtml(detailsId)}" ${isOpen ? 'open' : ''}`;
  }

  render() {
    const r = this.studio.editingRule;
    if (!r) return '';

    const summaryText = buildRuleSummaryItalian(r, { zones: this.studio.zones });
    const hasPreTriggers = Array.isArray(r.pre_triggers) && r.pre_triggers.length > 0;
    const condChildren = Array.isArray(r.condition?.children) ? r.condition.children : [];
    const actions = Array.isArray(r.actions) ? r.actions : [];

    return `
      <div class="auto-editor" data-editor-kind="rule">
        <div class="auto-editor-topbar">
          <button type="button" class="auto-btn ghost xs" id="btn-auto-rule-back">
            ${icon('arrow-left', { size: 13 })} <span>Tutte le regole</span>
          </button>
          <span class="auto-editor-mode-label">${this.studio.isEditingNewRule ? 'Nuova regola' : 'Modifica regola'}</span>
        </div>

        <div class="auto-rule-identity">
          <label class="auto-field" for="rule-inp-name">
            <span>Nome regola</span>
            <input type="text" id="rule-inp-name" name="rule_name" value="${escapeHtml(r.name)}" placeholder="Es. Avviso ingresso giardino" />
          </label>
          <p class="auto-rule-live-summary" id="rule-live-summary">${escapeHtml(summaryText)}</p>
        </div>

        <section class="auto-step" aria-labelledby="step-when-title">
          <div class="auto-step-head">
            <div class="auto-step-heading">
              <span class="auto-step-badge">1</span>
              <h3 class="auto-step-title" id="step-when-title">Quando scatta</h3>
            </div>
            <button type="button" class="auto-btn tonal xs" id="btn-rule-add-trigger">
              ${icon('plus', { size: 12 })} <span>Trigger</span>
            </button>
          </div>

          ${
            hasPreTriggers
              ? `<div class="auto-pretrigger-section">
                   <div class="auto-stack" id="rule-pretriggers-stack">
                     ${r.pre_triggers.map((stg, sIdx) => this._renderPreTriggerStageHtml(stg, sIdx, r.pre_triggers.length)).join('')}
                   </div>
                 </div>`
              : ''
          }

          ${
            r.triggers.length > 1 || r.trigger_logic === 'and_within'
              ? `<div class="auto-trigger-logic-bar">
                   <div class="auto-grid-2">
                     <label class="auto-field ${r.trigger_logic === 'and_within' ? '' : 'span-2'}" for="rule-inp-trigger-logic">
                       <span>Logica trigger</span>
                       <select id="rule-inp-trigger-logic" name="rule_trigger_logic">
                         <option value="or" ${(!r.trigger_logic || r.trigger_logic === 'or') ? 'selected' : ''}>OR · Uno qualsiasi</option>
                         <option value="and_within" ${r.trigger_logic === 'and_within' ? 'selected' : ''}>AND · Tutti entro finestra</option>
                       </select>
                     </label>
                     ${
                       r.trigger_logic === 'and_within'
                         ? `<label class="auto-field" for="rule-inp-trigger-window">
                              <span>Finestra (s)</span>
                              <input type="number" min="0.5" max="3600" step="0.5" id="rule-inp-trigger-window" name="rule_trigger_window_s" value="${Number(r.trigger_window_s ?? 10)}" />
                            </label>
                            <label class="auto-field span-2" for="rule-inp-trigger-corr">
                              <span>Correlazione</span>
                              <select id="rule-inp-trigger-corr" name="rule_trigger_correlation_scope">
                                <option value="same_subject" ${(!r.trigger_correlation_scope || r.trigger_correlation_scope === 'same_subject') ? 'selected' : ''}>Stesso soggetto (consigliato)</option>
                                <option value="same_track" ${r.trigger_correlation_scope === 'same_track' ? 'selected' : ''}>Stessa traccia / ID</option>
                                <option value="same_scene_event" ${r.trigger_correlation_scope === 'same_scene_event' ? 'selected' : ''}>Stesso episodio scena</option>
                                <option value="any" ${r.trigger_correlation_scope === 'any' ? 'selected' : ''}>Qualsiasi (cross-domain)</option>
                              </select>
                            </label>`
                         : ''
                     }
                   </div>
                 </div>`
              : ''
          }

          <div class="auto-stack" id="rule-triggers-stack">
            ${r.triggers.map((t, idx) => this._renderTriggerItemHtml(t, `main:${idx}`, r.triggers.length)).join('')}
          </div>

          <div class="auto-inline-optin">
            <button type="button" class="auto-btn ghost xs" id="btn-rule-add-pretrigger">
              ${icon('zap', { size: 12 })} <span>${hasPreTriggers ? 'Aggiungi altro pre-trigger' : 'Aggiungi fase preparatoria (Pre-trigger)'}</span>
            </button>
          </div>
        </section>

        <section class="auto-step" aria-labelledby="step-if-title">
          <div class="auto-step-head">
            <div class="auto-step-heading">
              <span class="auto-step-badge">2</span>
              <h3 class="auto-step-title" id="step-if-title">Solo se (opzionale)</h3>
            </div>
          </div>
          <div class="auto-cond-root">
            ${this._renderConditionNodeHtml(r.condition, 'root', true)}
          </div>
          ${condChildren.length === 0 ? '' : ''}
        </section>

        <section class="auto-step" aria-labelledby="step-then-title">
          <div class="auto-step-head">
            <div class="auto-step-heading">
              <span class="auto-step-badge">3</span>
              <h3 class="auto-step-title" id="step-then-title">Cosa fa (azioni)</h3>
            </div>
            <button type="button" class="auto-btn tonal xs" id="btn-rule-add-action">
              ${icon('plus', { size: 12 })} <span>Azione</span>
            </button>
          </div>

          ${
            actions.length === 0
              ? `<div class="auto-step-empty">
                   <p class="auto-hint-text">Nessuna azione configurata: scegli cosa deve succedere quando la regola scatta.</p>
                   <div class="auto-quick-actions">
                     <button type="button" class="auto-chip" data-quick-add-action="send_notification">${icon('send', { size: 11 })} <span>Notifica</span></button>
                     <button type="button" class="auto-chip" data-quick-add-action="call_ha_service">${icon('lightbulb', { size: 11 })} <span>Home Assistant</span></button>
                     <button type="button" class="auto-chip" data-quick-add-action="set_virtual_entity">${icon('sliders-horizontal', { size: 11 })} <span>Entità sh3d</span></button>
                     <button type="button" class="auto-chip" data-quick-add-action="ui_alert">${icon('bell-ring', { size: 11 })} <span>Avviso 3D</span></button>
                   </div>
                 </div>`
              : `<div class="auto-stack" id="rule-actions-stack">
                   ${actions.map((a, idx) => this._renderActionItemHtml(a, `${idx}`)).join('')}
                 </div>`
          }
        </section>

        <details class="auto-advanced-details" ${this._detailsAttrs('rule-advanced')}>
          <summary class="auto-details-summary">
            <span>Opzioni avanzate</span>
            ${icon('chevron-down', { size: 14, className: 'auto-details-chevron' })}
          </summary>
          <div class="auto-details-body">
            <div class="auto-grid-2">
              <label class="auto-field" for="rule-inp-exec-mode">
                <span>Modalità esecuzione</span>
                <select id="rule-inp-exec-mode" name="rule_execution_mode">
                  <option value="single" ${r.execution_mode === 'single' ? 'selected' : ''}>Singola (ignora se attiva)</option>
                  <option value="restart" ${r.execution_mode === 'restart' ? 'selected' : ''}>Riavvia se riscatta</option>
                  <option value="parallel" ${r.execution_mode === 'parallel' ? 'selected' : ''}>Parallela</option>
                  <option value="queued" ${r.execution_mode === 'queued' ? 'selected' : ''}>In coda (sequenziale)</option>
                </select>
              </label>
              <label class="auto-field" for="rule-inp-cooldown">
                <span>Cooldown (s)</span>
                <input type="number" min="0" max="86400" step="0.5" id="rule-inp-cooldown" name="rule_cooldown_s" value="${Number(r.cooldown_s ?? 3)}" />
              </label>
              <label class="auto-field span-2" for="rule-inp-desc">
                <span>Note (opzionale)</span>
                <input type="text" id="rule-inp-desc" name="rule_description" value="${escapeHtml(r.description || '')}" placeholder="Descrizione personalizzata per la lista regole" />
              </label>
              <label class="auto-check-row span-2" for="rule-inp-log-blocked">
                <input type="checkbox" id="rule-inp-log-blocked" name="rule_log_blocked" ${r.log_blocked_evaluations ? 'checked' : ''} />
                <span>Registra valutazioni bloccate (diagnostica)</span>
              </label>
            </div>
          </div>
        </details>
      </div>
    `;
  }

  _renderPreTriggerStageHtml(stage, sIdx, totalStages) {
    const triggers = Array.isArray(stage.triggers) ? stage.triggers : [];
    const matchMode = stage.match_mode || 'any';
    const corrScope = stage.correlation_scope || 'same_subject';
    const stageName = stage.name || `Pre-trigger ${sIdx + 1}`;
    const nextLabel = sIdx + 1 < totalStages ? `Fase ${sIdx + 2}` : 'Trigger principali';

    return `
      <div class="auto-pretrigger-card" data-pre-stage-idx="${sIdx}">
        <div class="auto-pretrigger-head">
          <span class="auto-pretrigger-badge">${icon('zap', { size: 12 })} <span>Fase ${sIdx + 1}</span></span>
          <input
            type="text"
            class="auto-pretrigger-name-inp"
            ${this._ctrl('pre', sIdx, 'name')}
            data-pre-field="${sIdx}:name"
            value="${escapeHtml(stageName)}"
            aria-label="Nome fase pre-trigger ${sIdx + 1}"
            placeholder="Nome pre-trigger"
          />
          <button type="button" class="auto-btn icon-only danger xs" data-del-pre-idx="${sIdx}" title="Rimuovi pre-trigger" aria-label="Rimuovi pre-trigger">
            ${icon('x', { size: 13 })}
          </button>
        </div>

        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Attesa max (s)</span>
            <input type="number" min="0.5" max="3600" step="0.5" ${this._ctrl('pre', sIdx, 'max_wait_s')} data-pre-field="${sIdx}:max_wait_s" value="${Number(stage.max_wait_s ?? 10)}" />
          </label>
          <label class="auto-field">
            <span>Ritardo min (s)</span>
            <input type="number" min="0" max="3600" step="0.5" ${this._ctrl('pre', sIdx, 'min_delay_s')} data-pre-field="${sIdx}:min_delay_s" value="${Number(stage.min_delay_s ?? 0)}" />
          </label>
          <label class="auto-field">
            <span>Correlazione</span>
            <select ${this._ctrl('pre', sIdx, 'correlation_scope')} data-pre-field="${sIdx}:correlation_scope">
              <option value="same_subject" ${corrScope === 'same_subject' ? 'selected' : ''}>Stesso soggetto</option>
              <option value="same_track" ${corrScope === 'same_track' ? 'selected' : ''}>Stessa traccia / ID</option>
              <option value="same_scene_event" ${corrScope === 'same_scene_event' ? 'selected' : ''}>Stesso episodio scena</option>
              <option value="any" ${corrScope === 'any' ? 'selected' : ''}>Qualsiasi (cross-domain)</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Logica fase</span>
            <select ${this._ctrl('pre', sIdx, 'match_mode')} data-pre-field="${sIdx}:match_mode">
              <option value="any" ${matchMode === 'any' ? 'selected' : ''}>OR · Uno qualsiasi</option>
              <option value="all" ${matchMode === 'all' ? 'selected' : ''}>AND · Tutti entro finestra</option>
            </select>
          </label>
          ${
            matchMode === 'all'
              ? `<label class="auto-field span-2">
                   <span>Finestra fase AND (s)</span>
                   <input type="number" min="0.5" max="3600" step="0.5" ${this._ctrl('pre', sIdx, 'stage_window_s')} data-pre-field="${sIdx}:stage_window_s" value="${Number(stage.stage_window_s ?? 10)}" />
                 </label>`
              : ''
          }
          <label class="auto-check-row">
            <input type="checkbox" ${this._ctrl('pre', sIdx, 'refresh_on_rearm')} data-pre-bool="${sIdx}:refresh_on_rearm" ${stage.refresh_on_rearm !== false ? 'checked' : ''} />
            <span>Rinnova finestra se attivo</span>
          </label>
          <label class="auto-check-row">
            <input type="checkbox" ${this._ctrl('pre', sIdx, 'consume_on_fire')} data-pre-bool="${sIdx}:consume_on_fire" ${stage.consume_on_fire !== false ? 'checked' : ''} />
            <span>Consuma allo scatto</span>
          </label>
        </div>

        <div class="auto-block-header">
          <span class="auto-notif-label">Trigger della fase</span>
          <div class="auto-block-header-actions">
            <button type="button" class="auto-btn ghost xs" data-pre-toggle-cond="${sIdx}">
              <span>${stage.condition ? 'Rimuovi cond.' : '+ Condizione'}</span>
            </button>
            <button type="button" class="auto-btn tonal xs" data-pre-add-trig="${sIdx}">
              ${icon('plus', { size: 11 })} <span>Trigger</span>
            </button>
          </div>
        </div>

        <div class="auto-stack">
          ${triggers.map((t, tIdx) => this._renderTriggerItemHtml(t, `pre:${sIdx}:${tIdx}`, triggers.length)).join('')}
        </div>

        ${
          stage.condition
            ? `<div class="auto-pretrigger-cond-box">
                 <span class="auto-ifelse-tag">Condizione opzionale fase ${sIdx + 1}</span>
                 ${this._renderConditionNodeHtml(stage.condition, `pre_cond:${sIdx}`, true)}
               </div>`
            : ''
        }
      </div>
      <div class="auto-pretrigger-connector">
        ${icon('chevron-down', { size: 13 })}
        <span>Attende max ${Number(stage.max_wait_s ?? 10)}s prima di ${escapeHtml(nextLabel)}</span>
      </div>
    `;
  }

  _renderTriggerItemHtml(trig, pathStr, siblingCount = 1) {
    const tType = trig.type || 'zone_presence';
    const sf = trig.subject_filter || {};
    const p = trig.params || {};
    const needsSubjectFilter = [
      'zone_presence',
      'perimeter_crossing',
      'zone_transition',
      'kinematic_vector',
      'biometric_detection',
      'proximity_3d',
      'scene_event',
    ].includes(tType);

    const zones = this.studio.zones || [];
    const polygonOptions = zones
      .filter((z) => z.geometry_type === 'polygon')
      .map((z) => `<option value="${escapeHtml(z.zone_id)}" ${p.zone_id === z.zone_id ? 'selected' : ''}>${escapeHtml(z.name)}</option>`)
      .join('');

    const allZoneOptions = zones
      .map((z) => `<option value="${escapeHtml(z.zone_id)}" ${(p.perimeter_id || p.zone_id) === z.zone_id ? 'selected' : ''}>${escapeHtml(z.name)} (${z.geometry_type === 'perimeter' ? 'Perimetro' : 'Area'})</option>`)
      .join('');

    let specificFieldsHtml = '';

    if (tType === 'zone_presence') {
      const eventVal = p.event || 'enter';
      const showDwell = eventVal === 'dwell';
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Area 3D</span>
            <div class="auto-input-with-btn">
              <select ${this._ctrl('trg', pathStr, 'zone_id')} data-trig-param="${escapeHtml(pathStr)}:zone_id">
                <option value="">Seleziona area...</option>
                ${polygonOptions}
              </select>
              <button type="button" class="auto-btn tonal xs" data-quick-new-zone="polygon:${escapeHtml(pathStr)}:zone_id" title="Disegna nuova area nel 3D">
                ${icon('plus', { size: 12 })} <span>Disegna 3D</span>
              </button>
            </div>
          </label>
          <label class="auto-field ${showDwell ? '' : 'span-2'}">
            <span>Evento</span>
            <select ${this._ctrl('trg', pathStr, 'event')} data-trig-param="${escapeHtml(pathStr)}:event">
              <option value="enter" ${eventVal === 'enter' ? 'selected' : ''}>Entrata</option>
              <option value="present" ${eventVal === 'present' ? 'selected' : ''}>Presenza / Riconoscimento in area</option>
              <option value="exit" ${eventVal === 'exit' ? 'selected' : ''}>Uscita</option>
              <option value="dwell" ${eventVal === 'dwell' ? 'selected' : ''}>Stazionamento</option>
            </select>
          </label>
          ${
            showDwell
              ? `<label class="auto-field">
                   <span>Permanenza min (s)</span>
                   <input type="number" min="0" max="3600" step="0.5" ${this._ctrl('trg', pathStr, 'min_dwell_s')} data-trig-param="${escapeHtml(pathStr)}:min_dwell_s" value="${Number(p.min_dwell_s ?? 0)}" />
                 </label>`
              : ''
          }
        </div>
      `;
    } else if (tType === 'perimeter_crossing') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Perimetro / linea 3D</span>
            <div class="auto-input-with-btn">
              <select ${this._ctrl('trg', pathStr, 'perimeter_id')} data-trig-param="${escapeHtml(pathStr)}:perimeter_id">
                <option value="">Seleziona perimetro...</option>
                ${allZoneOptions}
              </select>
              <button type="button" class="auto-btn tonal xs" data-quick-new-zone="perimeter:${escapeHtml(pathStr)}:perimeter_id" title="Disegna nuovo perimetro nel 3D">
                ${icon('plus', { size: 12 })} <span>Disegna 3D</span>
              </button>
            </div>
          </label>
          <label class="auto-field span-2">
            <span>Verso di attraversamento</span>
            <select ${this._ctrl('trg', pathStr, 'direction')} data-trig-param="${escapeHtml(pathStr)}:direction">
              <option value="a_to_b" ${p.direction === 'a_to_b' ? 'selected' : ''}>A → B (verso freccia 3D)</option>
              <option value="b_to_a" ${p.direction === 'b_to_a' ? 'selected' : ''}>B → A (opposto alla freccia)</option>
              <option value="both" ${(!p.direction || p.direction === 'both') ? 'selected' : ''}>Entrambi i versi (A ↔ B)</option>
            </select>
          </label>
        </div>
      `;
    } else if (tType === 'zone_transition') {
      const fromOpts = zones
        .filter((z) => z.geometry_type === 'polygon')
        .map((z) => `<option value="${escapeHtml(z.zone_id)}" ${p.from_zone_id === z.zone_id ? 'selected' : ''}>${escapeHtml(z.name)}</option>`)
        .join('');
      const toOpts = zones
        .filter((z) => z.geometry_type === 'polygon')
        .map((z) => `<option value="${escapeHtml(z.zone_id)}" ${p.to_zone_id === z.zone_id ? 'selected' : ''}>${escapeHtml(z.name)}</option>`)
        .join('');
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Da Area A</span>
            <select ${this._ctrl('trg', pathStr, 'from_zone_id')} data-trig-param="${escapeHtml(pathStr)}:from_zone_id">
              <option value="">Seleziona...</option>
              ${fromOpts}
            </select>
          </label>
          <label class="auto-field">
            <span>Ad Area B</span>
            <select ${this._ctrl('trg', pathStr, 'to_zone_id')} data-trig-param="${escapeHtml(pathStr)}:to_zone_id">
              <option value="">Seleziona...</option>
              ${toOpts}
            </select>
          </label>
          <label class="auto-field">
            <span>Transito max (s)</span>
            <input type="number" min="1" max="600" step="1" ${this._ctrl('trg', pathStr, 'max_transit_s')} data-trig-param="${escapeHtml(pathStr)}:max_transit_s" value="${Number(p.max_transit_s ?? 20)}" />
          </label>
          <label class="auto-field">
            <span>Vel. min (m/s)</span>
            <input type="number" min="0" max="30" step="0.1" ${this._ctrl('trg', pathStr, 'min_speed_mps')} data-trig-param="${escapeHtml(pathStr)}:min_speed_mps" value="${Number(p.min_speed_mps ?? 0)}" />
          </label>
        </div>
      `;
    } else if (tType === 'kinematic_vector') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Area di riferimento</span>
            <select ${this._ctrl('trg', pathStr, 'zone_id')} data-trig-param="${escapeHtml(pathStr)}:zone_id">
              <option value="">Ovunque nella scena 3D</option>
              ${polygonOptions}
            </select>
          </label>
          <label class="auto-field span-2">
            <span>Direzione azimut (0°=Est, 90°=Sud, 180°=Ovest, 270°=Nord)</span>
            <div class="auto-input-with-btn">
              <input type="number" min="0" max="359" step="5" placeholder="Qualsiasi direzione" ${this._ctrl('trg', pathStr, 'target_azimuth_deg')} data-trig-param="${escapeHtml(pathStr)}:target_azimuth_deg" value="${p.target_azimuth_deg ?? ''}" />
              <button type="button" class="auto-btn tonal xs" data-pick-direction-3d="${escapeHtml(pathStr)}" title="Clicca 2 punti nel 3D per orientare il vettore direzione">
                ${icon('compass', { size: 12 })} <span>Punta 3D</span>
              </button>
            </div>
          </label>
          <label class="auto-field">
            <span>Tolleranza (±°)</span>
            <input type="number" min="5" max="180" step="5" ${this._ctrl('trg', pathStr, 'azimuth_tolerance_deg')} data-trig-param="${escapeHtml(pathStr)}:azimuth_tolerance_deg" value="${Number(p.azimuth_tolerance_deg ?? 35)}" />
          </label>
          <label class="auto-field">
            <span>Durata min (s)</span>
            <input type="number" min="0.2" max="120" step="0.1" ${this._ctrl('trg', pathStr, 'min_duration_s')} data-trig-param="${escapeHtml(pathStr)}:min_duration_s" value="${Number(p.min_duration_s ?? 1.0)}" />
          </label>
          <label class="auto-field">
            <span>Vel. min (m/s)</span>
            <input type="number" min="0" max="40" step="0.1" ${this._ctrl('trg', pathStr, 'min_speed_mps')} data-trig-param="${escapeHtml(pathStr)}:min_speed_mps" value="${Number(p.min_speed_mps ?? 0.5)}" />
          </label>
          <label class="auto-field">
            <span>Vel. max (m/s)</span>
            <input type="number" min="0" max="40" step="0.1" placeholder="Illimitata" ${this._ctrl('trg', pathStr, 'max_speed_mps')} data-trig-param="${escapeHtml(pathStr)}:max_speed_mps" value="${p.max_speed_mps ?? ''}" />
          </label>
        </div>
      `;
    } else if (tType === 'time_schedule') {
      const mode = p.mode || 'fixed_time';
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Riferimento</span>
            <select ${this._ctrl('trg', pathStr, 'mode')} data-trig-param="${escapeHtml(pathStr)}:mode">
              <option value="fixed_time" ${mode === 'fixed_time' ? 'selected' : ''}>Ora fissa</option>
              <option value="sunrise" ${mode === 'sunrise' ? 'selected' : ''}>Alba</option>
              <option value="sunset" ${mode === 'sunset' ? 'selected' : ''}>Tramonto</option>
              <option value="interval" ${mode === 'interval' ? 'selected' : ''}>Intervallo periodico</option>
            </select>
          </label>
          ${
            mode === 'fixed_time'
              ? `<label class="auto-field">
                   <span>Orario</span>
                   <input type="time" ${this._ctrl('trg', pathStr, 'at')} data-trig-param="${escapeHtml(pathStr)}:at" value="${escapeHtml(p.at || '22:00')}" />
                 </label>`
              : mode === 'interval'
                ? `<label class="auto-field">
                     <span>Ogni (secondi)</span>
                     <input type="number" min="5" max="86400" step="5" ${this._ctrl('trg', pathStr, 'interval_seconds')} data-trig-param="${escapeHtml(pathStr)}:interval_seconds" value="${Number(p.interval_seconds ?? 60)}" />
                   </label>`
                : `<label class="auto-field">
                     <span>Offset (min, ±)</span>
                     <input type="number" min="-360" max="360" step="5" ${this._ctrl('trg', pathStr, 'offset_minutes')} data-trig-param="${escapeHtml(pathStr)}:offset_minutes" value="${Number(p.offset_minutes ?? 0)}" />
                   </label>`
          }
        </div>
      `;
    } else if (tType === 'entity_state_change') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>ID Entità (<code>sh3d.*</code> o Home Assistant)</span>
            <input type="text" list="auto-all-entities-datalist" ${this._ctrl('trg', pathStr, 'entity_id')} data-trig-param="${escapeHtml(pathStr)}:entity_id" value="${escapeHtml(p.entity_id || '')}" placeholder="Seleziona o scrivi entity_id" />
          </label>
          <label class="auto-field">
            <span>Da stato (opz.)</span>
            <input type="text" ${this._ctrl('trg', pathStr, 'from_state')} data-trig-param="${escapeHtml(pathStr)}:from_state" value="${escapeHtml(p.from_state || '')}" placeholder="Qualsiasi" />
          </label>
          <label class="auto-field">
            <span>A stato</span>
            <input type="text" ${this._ctrl('trg', pathStr, 'to_state')} data-trig-param="${escapeHtml(pathStr)}:to_state" value="${escapeHtml(p.to_state || '')}" placeholder="on" />
          </label>
          <label class="auto-field span-2">
            <span>Mantenuto per almeno (s)</span>
            <input type="number" min="0" max="3600" step="1" ${this._ctrl('trg', pathStr, 'for_duration_s')} data-trig-param="${escapeHtml(pathStr)}:for_duration_s" value="${Number(p.for_duration_s ?? 0)}" />
          </label>
        </div>
      `;
    } else if (tType === 'biometric_detection') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Modalità</span>
            <select ${this._ctrl('trg', pathStr, 'modality')} data-trig-param="${escapeHtml(pathStr)}:modality">
              <option value="any" ${(!p.modality || p.modality === 'any') ? 'selected' : ''}>Volto o targa</option>
              <option value="face" ${p.modality === 'face' ? 'selected' : ''}>Solo volto</option>
              <option value="alpr" ${p.modality === 'alpr' ? 'selected' : ''}>Solo targa</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Camera (opz.)</span>
            <input type="text" list="auto-cameras-datalist" ${this._ctrl('trg', pathStr, 'camera_id')} data-trig-param="${escapeHtml(pathStr)}:camera_id" value="${escapeHtml(p.camera_id || '')}" placeholder="Tutte" />
          </label>
          <label class="auto-field span-2">
            <span>Area 3D (opz.)</span>
            <select ${this._ctrl('trg', pathStr, 'zone_id')} data-trig-param="${escapeHtml(pathStr)}:zone_id">
              <option value="">Ovunque nella scena 3D</option>
              ${polygonOptions}
            </select>
          </label>
          <label class="auto-check-row span-2">
            <input type="checkbox" ${this._ctrl('trg', pathStr, 'require_locked')} data-trig-bool="${escapeHtml(pathStr)}:require_locked" ${p.require_locked !== false ? 'checked' : ''} />
            <span>Solo riconoscimento confermato</span>
          </label>
        </div>
      `;
    } else if (tType === 'proximity_3d') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Coord. X (m)</span>
            <input type="number" step="0.1" ${this._ctrl('trg', pathStr, 'target_x')} data-trig-param="${escapeHtml(pathStr)}:target_x" value="${Number(p.target_x ?? 0)}" />
          </label>
          <label class="auto-field">
            <span>Coord. Z (m)</span>
            <input type="number" step="0.1" ${this._ctrl('trg', pathStr, 'target_z')} data-trig-param="${escapeHtml(pathStr)}:target_z" value="${Number(p.target_z ?? 0)}" />
          </label>
          <label class="auto-field">
            <span>Raggio (m)</span>
            <input type="number" min="0.2" max="50" step="0.2" ${this._ctrl('trg', pathStr, 'radius_m')} data-trig-param="${escapeHtml(pathStr)}:radius_m" value="${Number(p.radius_m ?? 2.0)}" />
          </label>
          <label class="auto-field">
            <span>Permanenza (s)</span>
            <input type="number" min="0" max="600" step="0.5" ${this._ctrl('trg', pathStr, 'min_dwell_s')} data-trig-param="${escapeHtml(pathStr)}:min_dwell_s" value="${Number(p.min_dwell_s ?? 1.0)}" />
          </label>
        </div>
      `;
    } else if (tType === 'scene_event') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Fase episodio</span>
            <select ${this._ctrl('trg', pathStr, 'event')} data-trig-param="${escapeHtml(pathStr)}:event">
              <option value="started" ${(!p.event || p.event === 'started') ? 'selected' : ''}>Inizio episodio</option>
              <option value="importance_escalated" ${p.event === 'importance_escalated' ? 'selected' : ''}>Escalation ad Allerta</option>
              <option value="closed" ${p.event === 'closed' ? 'selected' : ''}>Chiusura episodio</option>
              <option value="any" ${p.event === 'any' ? 'selected' : ''}>Qualsiasi transizione</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Importanza</span>
            <select ${this._ctrl('trg', pathStr, 'importance')} data-trig-param="${escapeHtml(pathStr)}:importance">
              <option value="any" ${(!p.importance || p.importance === 'any') ? 'selected' : ''}>Qualsiasi</option>
              <option value="alert" ${p.importance === 'alert' ? 'selected' : ''}>Allarme</option>
              <option value="silent_alert" ${p.importance === 'silent_alert' ? 'selected' : ''}>Allarme Silenzioso</option>
              <option value="notable" ${p.importance === 'notable' ? 'selected' : ''}>Rilevante</option>
              <option value="routine" ${p.importance === 'routine' ? 'selected' : ''}>Routine</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Area 3D (opz.)</span>
            <select ${this._ctrl('trg', pathStr, 'zone_id')} data-trig-param="${escapeHtml(pathStr)}:zone_id">
              <option value="">Tutte</option>
              ${polygonOptions}
            </select>
          </label>
          <label class="auto-field">
            <span>Soggetti minimi</span>
            <input type="number" min="0" max="20" step="1" ${this._ctrl('trg', pathStr, 'min_subjects')} data-trig-param="${escapeHtml(pathStr)}:min_subjects" value="${Number(p.min_subjects ?? 0)}" />
          </label>
        </div>
      `;
    }

    return `
      <div class="auto-node-surface" data-trigger-card="${escapeHtml(pathStr)}">
        <div class="auto-node-bar">
          <select class="auto-node-type-select" ${this._ctrl('trg-type', pathStr, 'type')} data-trig-type-path="${escapeHtml(pathStr)}" aria-label="Tipo di trigger">
            ${Object.entries(TRIGGER_TYPE_LABELS)
              .map(([k, label]) => `<option value="${k}" ${tType === k ? 'selected' : ''}>${escapeHtml(label)}</option>`)
              .join('')}
          </select>
          ${
            siblingCount > 1
              ? `<button type="button" class="auto-btn icon-only danger xs" data-del-trig-path="${escapeHtml(pathStr)}" title="Rimuovi trigger" aria-label="Rimuovi trigger">
                   ${icon('x', { size: 13 })}
                 </button>`
              : ''
          }
        </div>
        ${specificFieldsHtml}
        ${needsSubjectFilter ? this._renderSubjectFilterHtml(sf, pathStr) : ''}
      </div>
    `;
  }

  _renderSubjectFilterHtml(sf = {}, pathStr) {
    const classesList = Array.isArray(sf.classes) ? sf.classes : [];
    const currentClass = classesList[0] || 'any';
    const faceMode = sf.face_mode || 'any';
    const plateMode = sf.plate_mode || 'any';
    const selectedIds = Array.isArray(sf.identities) ? sf.identities : [];
    const selectedPlates = Array.isArray(sf.plates) ? sf.plates : [];

    const showFace = currentClass === 'person' || currentClass === 'any';
    const showPlate = currentClass === 'vehicle' || currentClass === 'any';
    const showGrace = (showFace && faceMode !== 'any') || (showPlate && plateMode !== 'any');
    const graceVal = roundClean(sf.biometric_grace_s ?? 1.2, 2);

    const savedIdChips = (this.studio.identities || [])
      .map((item) => {
        const name = item.name;
        const active = selectedIds.some((s) => s.toLowerCase() === name.toLowerCase());
        return `<button type="button" class="auto-chip ${active ? 'active' : ''}" data-trig-id-chip="${escapeHtml(pathStr)}:${escapeHtml(name)}">${escapeHtml(name)}</button>`;
      })
      .join('');

    const savedPlateChips = (this.studio.plates || [])
      .map((item) => {
        const plate = String(item.plate || '').toUpperCase();
        if (!plate) return '';
        const label = item.owner_name ? `${plate} · ${item.owner_name}` : plate;
        const active = selectedPlates.some((s) => s.toUpperCase() === plate);
        return `<button type="button" class="auto-chip ${active ? 'active' : ''}" data-trig-plate-chip="${escapeHtml(pathStr)}:${escapeHtml(plate)}">${escapeHtml(label)}</button>`;
      })
      .filter(Boolean)
      .join('');

    const subjectSpanClass = !showFace && !showPlate ? 'span-2' : '';

    return `
      <div class="auto-filter-divider">
        <div class="auto-grid-2">
          <label class="auto-field ${subjectSpanClass}">
            <span>Soggetto</span>
            <select ${this._ctrl('sf', pathStr, 'classes')} data-trig-sf="${escapeHtml(pathStr)}:classes">
              <option value="any" ${currentClass === 'any' ? 'selected' : ''}>Qualsiasi</option>
              <option value="person" ${currentClass === 'person' ? 'selected' : ''}>Persone</option>
              <option value="vehicle" ${currentClass === 'vehicle' ? 'selected' : ''}>Veicoli</option>
              <option value="dog" ${currentClass === 'dog' ? 'selected' : ''}>Animali</option>
              <option value="bicycle" ${currentClass === 'bicycle' ? 'selected' : ''}>Biciclette</option>
            </select>
          </label>

          ${
            showFace
              ? `<label class="auto-field">
                   <span>Filtro volto</span>
                   <select ${this._ctrl('sf', pathStr, 'face_mode')} data-trig-sf="${escapeHtml(pathStr)}:face_mode">
                     <option value="any" ${faceMode === 'any' ? 'selected' : ''}>Chiunque</option>
                     <option value="unknown" ${faceMode === 'unknown' ? 'selected' : ''}>Solo sconosciuti</option>
                     <option value="known" ${faceMode === 'known' ? 'selected' : ''}>Volti registrati</option>
                     <option value="include" ${faceMode === 'include' ? 'selected' : ''}>Solo specifici...</option>
                     <option value="exclude" ${faceMode === 'exclude' ? 'selected' : ''}>Escludi specifici...</option>
                   </select>
                 </label>`
              : ''
          }

          ${
            showFace && (faceMode === 'include' || faceMode === 'exclude')
              ? `<div class="auto-field span-2">
                   <span>Persone (${faceMode === 'include' ? 'incluse' : 'escluse'})</span>
                   ${savedIdChips ? `<div class="auto-chips-wrap">${savedIdChips}</div>` : ''}
                   <input type="text" ${this._ctrl('sf', pathStr, 'identities')} data-trig-sf="${escapeHtml(pathStr)}:identities" value="${escapeHtml(selectedIds.join(', '))}" placeholder="Nomi separati da virgola" />
                 </div>`
              : ''
          }

          ${
            showPlate
              ? `<label class="auto-field ${showFace ? 'span-2' : ''}">
                   <span>Filtro targa</span>
                   <select ${this._ctrl('sf', pathStr, 'plate_mode')} data-trig-sf="${escapeHtml(pathStr)}:plate_mode">
                     <option value="any" ${plateMode === 'any' ? 'selected' : ''}>Qualsiasi</option>
                     <option value="whitelisted" ${plateMode === 'whitelisted' ? 'selected' : ''}>In whitelist</option>
                     <option value="not_whitelisted" ${plateMode === 'not_whitelisted' ? 'selected' : ''}>Non in whitelist</option>
                     <option value="include" ${plateMode === 'include' ? 'selected' : ''}>Specifiche...</option>
                     <option value="exclude" ${plateMode === 'exclude' ? 'selected' : ''}>Escludi...</option>
                   </select>
                 </label>`
              : ''
          }

          ${
            showPlate && (plateMode === 'include' || plateMode === 'exclude')
              ? `<div class="auto-field span-2">
                   <span>Targhe (${plateMode === 'include' ? 'incluse' : 'escluse'})</span>
                   ${savedPlateChips ? `<div class="auto-chips-wrap">${savedPlateChips}</div>` : ''}
                   <input type="text" ${this._ctrl('sf', pathStr, 'plates')} data-trig-sf="${escapeHtml(pathStr)}:plates" value="${escapeHtml(selectedPlates.join(', '))}" placeholder="Es. AB123CD" />
                 </div>`
              : ''
          }

          ${
            showGrace
              ? `<details class="auto-subtle-disclosure span-2" ${this._detailsAttrs(`bio-grace-${pathStr}`)}>
                   <summary class="auto-subtle-summary">
                     <span>Attesa riconoscimento biometria (${graceVal}s)</span>
                     ${icon('chevron-down', { size: 12, className: 'auto-details-chevron' })}
                   </summary>
                   <div class="auto-subtle-body">
                     <label class="auto-field">
                       <span>Grazia biometria (s)</span>
                       <input type="number" min="0" max="60" step="0.2" ${this._ctrl('sf', pathStr, 'biometric_grace_s')} data-trig-sf="${escapeHtml(pathStr)}:biometric_grace_s" value="${graceVal}" />
                     </label>
                   </div>
                 </details>`
              : ''
          }
        </div>
      </div>
    `;
  }

  _renderConditionNodeHtml(node, pathStr = 'root', isRoot = false) {
    if (!node) return '';
    const cType = node.type || 'and';
    const isComposite = ['and', 'or', 'not', 'xor'].includes(cType);

    if (isComposite) {
      const children = Array.isArray(node.children) ? node.children : [];
      return `
        <div class="auto-cond-group ${isRoot ? 'is-root' : ''}">
          <div class="auto-cond-bar">
            ${
              children.length > 1 || !isRoot
                ? `<select class="auto-cond-op-select" ${this._ctrl('cnd-op', pathStr, 'type')} data-cond-type-path="${escapeHtml(pathStr)}" aria-label="Logica condizioni">
                     <option value="and" ${cType === 'and' ? 'selected' : ''}>AND · Tutte vere</option>
                     <option value="or" ${cType === 'or' ? 'selected' : ''}>OR · Almeno una vera</option>
                     <option value="not" ${cType === 'not' ? 'selected' : ''}>NOT · Inverti</option>
                     <option value="xor" ${cType === 'xor' ? 'selected' : ''}>XOR · Solo una vera</option>
                   </select>`
                : `<span class="auto-cond-placeholder-label">${children.length === 1 ? 'Condizione attiva' : 'Nessun filtro obbligatorio'}</span>`
            }
            <div class="auto-cond-actions">
              <button type="button" class="auto-btn tonal xs" data-cond-add-leaf="${escapeHtml(pathStr)}">
                ${icon('plus', { size: 11 })} <span>Condizione</span>
              </button>
              <button type="button" class="auto-btn ghost xs" data-cond-add-group="${escapeHtml(pathStr)}">
                ${icon('plus', { size: 11 })} <span>Gruppo</span>
              </button>
              ${
                !isRoot
                  ? `<button type="button" class="auto-btn icon-only danger xs" data-cond-del-path="${escapeHtml(pathStr)}" title="Rimuovi gruppo" aria-label="Rimuovi gruppo">
                       ${icon('x', { size: 12 })}
                     </button>`
                  : ''
              }
            </div>
          </div>
          <div class="auto-cond-children">
            ${
              children.length === 0
                ? `<p class="auto-hint-text">Nessuna condizione: la regola si attiva ad ogni scatto del trigger.</p>`
                : children.map((ch, idx) => this._renderConditionNodeHtml(ch, `${pathStr}.${idx}`, false)).join('')
            }
          </div>
        </div>
      `;
    }

    const p = node.params || {};
    const zones = this.studio.zones || [];
    const polygonOptions = zones
      .filter((z) => z.geometry_type === 'polygon')
      .map((z) => `<option value="${escapeHtml(z.zone_id)}" ${p.zone_id === z.zone_id ? 'selected' : ''}>${escapeHtml(z.name)}</option>`)
      .join('');

    let leafFields = '';
    if (cType === 'entity_state') {
      leafFields = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Entità (<code>sh3d.*</code> o Home Assistant)</span>
            <input type="text" list="auto-all-entities-datalist" ${this._ctrl('cnd', pathStr, 'entity_id')} data-cond-param="${escapeHtml(pathStr)}:entity_id" value="${escapeHtml(p.entity_id || '')}" placeholder="Seleziona o scrivi entity_id" />
          </label>
          <label class="auto-field">
            <span>Confronto</span>
            <select ${this._ctrl('cnd', pathStr, 'operator')} data-cond-param="${escapeHtml(pathStr)}:operator">
              <option value="==" ${(!p.operator || p.operator === '==') ? 'selected' : ''}>Uguale (=)</option>
              <option value="!=" ${p.operator === '!=' ? 'selected' : ''}>Diverso (≠)</option>
              <option value=">" ${p.operator === '>' ? 'selected' : ''}>Maggiore (&gt;)</option>
              <option value=">=" ${p.operator === '>=' ? 'selected' : ''}>Maggiore o uguale (≥)</option>
              <option value="<" ${p.operator === '<' ? 'selected' : ''}>Minore (&lt;)</option>
              <option value="<=" ${p.operator === '<=' ? 'selected' : ''}>Minore o uguale (≤)</option>
              <option value="in" ${p.operator === 'in' ? 'selected' : ''}>In lista (a, b)</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Valore</span>
            <input type="text" ${this._ctrl('cnd', pathStr, 'value')} data-cond-param="${escapeHtml(pathStr)}:value" value="${escapeHtml(p.value ?? '')}" placeholder="es. on, Acceso" />
          </label>
        </div>
      `;
    } else if (cType === 'time_window') {
      leafFields = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Dalle ore</span>
            <input type="time" ${this._ctrl('cnd', pathStr, 'after_hhmm')} data-cond-param="${escapeHtml(pathStr)}:after_hhmm" value="${escapeHtml(p.after_hhmm || '')}" />
          </label>
          <label class="auto-field">
            <span>Alle ore</span>
            <input type="time" ${this._ctrl('cnd', pathStr, 'before_hhmm')} data-cond-param="${escapeHtml(pathStr)}:before_hhmm" value="${escapeHtml(p.before_hhmm || '')}" />
          </label>
          <label class="auto-field span-2">
            <span>Sole</span>
            <select ${this._ctrl('cnd', pathStr, 'sun_state')} data-cond-param="${escapeHtml(pathStr)}:sun_state">
              <option value="any" ${(!p.sun_state || p.sun_state === 'any') ? 'selected' : ''}>Qualsiasi</option>
              <option value="night" ${p.sun_state === 'night' ? 'selected' : ''}>Solo notte (sotto orizzonte)</option>
              <option value="daylight" ${p.sun_state === 'daylight' ? 'selected' : ''}>Solo giorno (sopra orizzonte)</option>
            </select>
          </label>
        </div>
      `;
    } else if (cType === 'zone_occupancy') {
      leafFields = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Area 3D</span>
            <select ${this._ctrl('cnd', pathStr, 'zone_id')} data-cond-param="${escapeHtml(pathStr)}:zone_id">
              <option value="">Seleziona area...</option>
              ${polygonOptions}
            </select>
          </label>
          <label class="auto-field">
            <span>Confronto presenti</span>
            <select ${this._ctrl('cnd', pathStr, 'operator')} data-cond-param="${escapeHtml(pathStr)}:operator">
              <option value=">=" ${(!p.operator || p.operator === '>=') ? 'selected' : ''}>Almeno (≥)</option>
              <option value="==" ${p.operator === '==' ? 'selected' : ''}>Esattamente (=)</option>
              <option value="<=" ${p.operator === '<=' ? 'selected' : ''}>Al massimo (≤)</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Numero soggetti</span>
            <input type="number" min="0" max="50" step="1" ${this._ctrl('cnd', pathStr, 'count')} data-cond-param="${escapeHtml(pathStr)}:count" value="${Number(p.count ?? 1)}" />
          </label>
        </div>
      `;
    } else if (cType === 'track_kinematics') {
      const evalMode = p.evaluation_mode || 'mean';
      leafFields = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Modalità velocità</span>
            <select ${this._ctrl('cnd', pathStr, 'evaluation_mode')} data-cond-param="${escapeHtml(pathStr)}:evaluation_mode">
              <option value="mean" ${evalMode === 'mean' ? 'selected' : ''}>Media nella finestra</option>
              <option value="peak_in_window" ${evalMode === 'peak_in_window' ? 'selected' : ''}>Picco nella finestra (lookback)</option>
              <option value="min_in_window" ${evalMode === 'min_in_window' ? 'selected' : ''}>Minimo nella finestra</option>
              <option value="current" ${evalMode === 'current' ? 'selected' : ''}>Istantanea attuale</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Finestra (s)</span>
            <input type="number" min="0.5" max="120" step="0.5" ${this._ctrl('cnd', pathStr, 'window_s')} data-cond-param="${escapeHtml(pathStr)}:window_s" value="${Number(p.window_s ?? 2)}" />
          </label>
          <label class="auto-field">
            <span>Vel. min (m/s)</span>
            <input type="number" min="0" max="35" step="0.1" placeholder="Qualsiasi" ${this._ctrl('cnd', pathStr, 'min_speed_mps')} data-cond-param="${escapeHtml(pathStr)}:min_speed_mps" value="${p.min_speed_mps ?? ''}" />
          </label>
          <label class="auto-field">
            <span>Vel. max (m/s)</span>
            <input type="number" min="0" max="35" step="0.1" placeholder="Illimitata" ${this._ctrl('cnd', pathStr, 'max_speed_mps')} data-cond-param="${escapeHtml(pathStr)}:max_speed_mps" value="${p.max_speed_mps ?? ''}" />
          </label>
          <label class="auto-field">
            <span>Azimut (°)</span>
            <input type="number" min="0" max="359" step="5" placeholder="Qualsiasi" ${this._ctrl('cnd', pathStr, 'target_azimuth_deg')} data-cond-param="${escapeHtml(pathStr)}:target_azimuth_deg" value="${p.target_azimuth_deg ?? ''}" />
          </label>
          <label class="auto-field">
            <span>Tolleranza (±°)</span>
            <input type="number" min="5" max="180" step="5" ${this._ctrl('cnd', pathStr, 'azimuth_tolerance_deg')} data-cond-param="${escapeHtml(pathStr)}:azimuth_tolerance_deg" value="${Number(p.azimuth_tolerance_deg ?? 35)}" />
          </label>
        </div>
      `;
    } else if (cType === 'subject_filter') {
      const clsArr = Array.isArray(p.classes) ? p.classes : [];
      const curCls = clsArr[0] || 'any';
      const fMode = p.face_mode || 'any';
      const pMode = p.plate_mode || 'any';
      const idsList = Array.isArray(p.identities) ? p.identities : [];
      const platesList = Array.isArray(p.plates) ? p.plates : [];
      leafFields = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Bersaglio</span>
            <select ${this._ctrl('cnd', pathStr, 'target')} data-cond-param="${escapeHtml(pathStr)}:target">
              <option value="trigger_track" ${(!p.target || p.target === 'trigger_track') ? 'selected' : ''}>Soggetto del trigger</option>
              <option value="any_active" ${p.target === 'any_active' ? 'selected' : ''}>Almeno un soggetto attivo</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Soggetto</span>
            <select ${this._ctrl('cnd', pathStr, 'classes')} data-cond-param="${escapeHtml(pathStr)}:classes">
              <option value="any" ${curCls === 'any' ? 'selected' : ''}>Qualsiasi</option>
              <option value="person" ${curCls === 'person' ? 'selected' : ''}>Persone</option>
              <option value="vehicle" ${curCls === 'vehicle' ? 'selected' : ''}>Veicoli</option>
              <option value="dog" ${curCls === 'dog' ? 'selected' : ''}>Animali</option>
              <option value="bicycle" ${curCls === 'bicycle' ? 'selected' : ''}>Biciclette</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Filtro volto</span>
            <select ${this._ctrl('cnd', pathStr, 'face_mode')} data-cond-param="${escapeHtml(pathStr)}:face_mode">
              <option value="any" ${fMode === 'any' ? 'selected' : ''}>Chiunque</option>
              <option value="unknown" ${fMode === 'unknown' ? 'selected' : ''}>Solo sconosciuti</option>
              <option value="known" ${fMode === 'known' ? 'selected' : ''}>Volti registrati</option>
              <option value="include" ${fMode === 'include' ? 'selected' : ''}>Solo specifici...</option>
              <option value="exclude" ${fMode === 'exclude' ? 'selected' : ''}>Escludi specifici...</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Filtro targa</span>
            <select ${this._ctrl('cnd', pathStr, 'plate_mode')} data-cond-param="${escapeHtml(pathStr)}:plate_mode">
              <option value="any" ${pMode === 'any' ? 'selected' : ''}>Qualsiasi</option>
              <option value="whitelisted" ${pMode === 'whitelisted' ? 'selected' : ''}>In whitelist</option>
              <option value="not_whitelisted" ${pMode === 'not_whitelisted' ? 'selected' : ''}>Non in whitelist</option>
              <option value="include" ${pMode === 'include' ? 'selected' : ''}>Specifiche...</option>
              <option value="exclude" ${pMode === 'exclude' ? 'selected' : ''}>Escludi...</option>
            </select>
          </label>
          ${
            fMode === 'include' || fMode === 'exclude'
              ? `<label class="auto-field span-2">
                   <span>Nomi (separati da virgola)</span>
                   <input type="text" ${this._ctrl('cnd', pathStr, 'identities')} data-cond-param="${escapeHtml(pathStr)}:identities" value="${escapeHtml(idsList.join(', '))}" placeholder="Es. Mario, Lucia" />
                 </label>`
              : ''
          }
          ${
            pMode === 'include' || pMode === 'exclude'
              ? `<label class="auto-field span-2">
                   <span>Targhe (separate da virgola)</span>
                   <input type="text" ${this._ctrl('cnd', pathStr, 'plates')} data-cond-param="${escapeHtml(pathStr)}:plates" value="${escapeHtml(platesList.join(', '))}" placeholder="Es. AB123CD" />
                 </label>`
              : ''
          }
        </div>
      `;
    } else if (cType === 'scene_event') {
      leafFields = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Importanza episodio</span>
            <select ${this._ctrl('cnd', pathStr, 'importance')} data-cond-param="${escapeHtml(pathStr)}:importance">
              <option value="any" ${(!p.importance || p.importance === 'any') ? 'selected' : ''}>Qualsiasi</option>
              <option value="alert" ${p.importance === 'alert' ? 'selected' : ''}>Allarme</option>
              <option value="silent_alert" ${p.importance === 'silent_alert' ? 'selected' : ''}>Allarme Silenzioso</option>
              <option value="notable" ${p.importance === 'notable' ? 'selected' : ''}>Rilevante</option>
              <option value="routine" ${p.importance === 'routine' ? 'selected' : ''}>Routine</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Soggetti minimi</span>
            <input type="number" min="0" max="20" step="1" ${this._ctrl('cnd', pathStr, 'min_subjects')} data-cond-param="${escapeHtml(pathStr)}:min_subjects" value="${p.min_subjects ?? ''}" placeholder="Qualsiasi" />
          </label>
          <label class="auto-field">
            <span>Sconosciuti presenti</span>
            <select ${this._ctrl('cnd', pathStr, 'has_unknown_person')} data-cond-param="${escapeHtml(pathStr)}:has_unknown_person">
              <option value="any" ${(!p.has_unknown_person || p.has_unknown_person === 'any') ? 'selected' : ''}>Indifferente</option>
              <option value="yes" ${p.has_unknown_person === 'yes' ? 'selected' : ''}>Sì</option>
              <option value="no" ${p.has_unknown_person === 'no' ? 'selected' : ''}>No</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Targa in whitelist</span>
            <select ${this._ctrl('cnd', pathStr, 'has_whitelisted_plate')} data-cond-param="${escapeHtml(pathStr)}:has_whitelisted_plate">
              <option value="any" ${(!p.has_whitelisted_plate || p.has_whitelisted_plate === 'any') ? 'selected' : ''}>Indifferente</option>
              <option value="yes" ${p.has_whitelisted_plate === 'yes' ? 'selected' : ''}>Sì</option>
              <option value="no" ${p.has_whitelisted_plate === 'no' ? 'selected' : ''}>No</option>
            </select>
          </label>
        </div>
      `;
    } else if (cType === 'recent_zone_visit') {
      leafFields = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Area 3D visitata</span>
            <select ${this._ctrl('cnd', pathStr, 'zone_id')} data-cond-param="${escapeHtml(pathStr)}:zone_id">
              <option value="">Seleziona area...</option>
              ${polygonOptions}
            </select>
          </label>
          <label class="auto-field">
            <span>Entro gli ultimi (s)</span>
            <input type="number" min="0" max="600" step="0.5" ${this._ctrl('cnd', pathStr, 'within_s')} data-cond-param="${escapeHtml(pathStr)}:within_s" value="${Number(p.within_s ?? 10)}" />
          </label>
          <label class="auto-field">
            <span>Permanenza min (s)</span>
            <input type="number" min="0" max="600" step="0.5" ${this._ctrl('cnd', pathStr, 'min_dwell_s')} data-cond-param="${escapeHtml(pathStr)}:min_dwell_s" value="${Number(p.min_dwell_s ?? 0)}" />
          </label>
        </div>
      `;
    }

    return `
      <div class="auto-node-surface is-compact" data-cond-card="${escapeHtml(pathStr)}">
        <div class="auto-node-bar">
          <select class="auto-node-type-select" ${this._ctrl('cnd-type', pathStr, 'type')} data-cond-type-path="${escapeHtml(pathStr)}" aria-label="Tipo condizione">
            ${Object.entries(CONDITION_TYPE_LABELS)
              .map(([k, label]) => `<option value="${k}" ${cType === k ? 'selected' : ''}>${escapeHtml(label)}</option>`)
              .join('')}
          </select>
          <button type="button" class="auto-btn icon-only danger xs" data-cond-del-path="${escapeHtml(pathStr)}" title="Rimuovi condizione" aria-label="Rimuovi condizione">
            ${icon('x', { size: 12 })}
          </button>
        </div>
        ${leafFields}
      </div>
    `;
  }

  _renderActionItemHtml(act, pathStr) {
    const aType = act.type || 'call_ha_service';
    const p = act.params || {};
    const virtualEntities = this.studio.virtualEntities || [];
    const haEntities = this.studio.haClient?.entities || {};

    let bodyHtml = '';
    if (aType === 'set_virtual_entity') {
      const op = p.operation || 'turn_on';
      const veOptions = virtualEntities
        .map((ve) => `<option value="${escapeHtml(ve.entity_id)}" ${p.entity_id === ve.entity_id ? 'selected' : ''}>${escapeHtml(ve.name)} (${escapeHtml(ve.entity_id)})</option>`)
        .join('');
      const selectedVe = virtualEntities.find((ve) => ve.entity_id === p.entity_id);
      const isSelectVe = selectedVe?.domain === 'select' && Array.isArray(selectedVe.options) && selectedVe.options.length > 0;

      bodyHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Entità interna (<code>sh3d.*</code>)</span>
            ${
              virtualEntities.length > 0
                ? `<select ${this._ctrl('act', pathStr, 'entity_id')} data-act-param="${escapeHtml(pathStr)}:entity_id">
                     <option value="">Seleziona entità...</option>
                     ${veOptions}
                   </select>`
                : `<input type="text" ${this._ctrl('act', pathStr, 'entity_id')} data-act-param="${escapeHtml(pathStr)}:entity_id" value="${escapeHtml(p.entity_id || '')}" placeholder="Crea prima un’entità nella scheda Entità" />`
            }
          </label>
          <label class="auto-field ${op === 'set' ? '' : 'span-2'}">
            <span>Operazione</span>
            <select ${this._ctrl('act', pathStr, 'operation')} data-act-param="${escapeHtml(pathStr)}:operation">
              <option value="turn_on" ${op === 'turn_on' ? 'selected' : ''}>Attiva (ON)</option>
              <option value="turn_off" ${op === 'turn_off' ? 'selected' : ''}>Disattiva (OFF)</option>
              <option value="toggle" ${op === 'toggle' ? 'selected' : ''}>Inverti (Toggle)</option>
              <option value="set" ${op === 'set' ? 'selected' : ''}>Imposta valore</option>
            </select>
          </label>
          ${
            op === 'set'
              ? `<label class="auto-field">
                   <span>Valore</span>
                   ${
                     isSelectVe
                       ? `<select ${this._ctrl('act', pathStr, 'state')} data-act-param="${escapeHtml(pathStr)}:state">
                            ${selectedVe.options.map((opt) => `<option value="${escapeHtml(opt)}" ${p.state === opt ? 'selected' : ''}>${escapeHtml(opt)}</option>`).join('')}
                          </select>`
                       : `<input type="text" ${this._ctrl('act', pathStr, 'state')} data-act-param="${escapeHtml(pathStr)}:state" value="${escapeHtml(p.state ?? '')}" placeholder="es. on, Acceso" />`
                   }
                 </label>`
              : ''
          }
        </div>
      `;
    } else if (aType === 'call_ha_service') {
      const svcDataStr =
        p.service_data && typeof p.service_data === 'object' && Object.keys(p.service_data).length > 0
          ? JSON.stringify(p.service_data)
          : '';
      const svcListId = sanitizeControlId(`auto-ha-svcs-${pathStr}`);
      const svcSuggestions = getHaServiceSuggestions(haEntities);

      bodyHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Servizio HA</span>
            <input type="text" list="${svcListId}" ${this._ctrl('act', pathStr, 'service')} data-act-param="${escapeHtml(pathStr)}:service" value="${escapeHtml(p.service || '')}" placeholder="es. light.turn_on" />
            <datalist id="${svcListId}">
              ${svcSuggestions.map((s) => `<option value="${escapeHtml(s)}"></option>`).join('')}
            </datalist>
          </label>
          <label class="auto-field">
            <span>Entity ID</span>
            <input type="text" list="auto-all-entities-datalist" ${this._ctrl('act', pathStr, 'entity_id')} data-act-param="${escapeHtml(pathStr)}:entity_id" value="${escapeHtml(p.entity_id || '')}" placeholder="Seleziona entità HA" />
          </label>
          <label class="auto-field span-2">
            <span>Dati JSON opzionali (<code>service_data</code>)</span>
            <input type="text" ${this._ctrl('act', pathStr, 'service_data')} data-act-json="${escapeHtml(pathStr)}:service_data" value="${escapeHtml(svcDataStr)}" placeholder='es. {"brightness_pct": 80}' />
          </label>
        </div>
      `;
    } else if (aType === 'send_notification') {
      const toList = (v) =>
        Array.isArray(v)
          ? v
          : String(v || '')
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean);
      const mobileTargets = toList(p.mobile_targets);
      const tvTargets = toList(p.tv_targets);
      const ttsTargets = toList(p.tts_targets);

      const disc = this.studio.haDiscovery || {};
      const allNotify = Array.isArray(disc.notify_services) ? disc.notify_services : [];
      const mobileDisc = allNotify.filter((n) => n.kind === 'mobile_app');
      const tvDisc = allNotify.filter((n) => n.kind === 'tv');
      const mediaPlayersDisc = Array.isArray(disc.media_players) ? disc.media_players : [];
      const ttsEntitiesDisc = Array.isArray(disc.tts_entities) ? disc.tts_entities : [];

      const renderChips = (items, selectedList, listKey, idField = 'service') => {
        if (!items.length) return '';
        return `
          <div class="auto-notif-chips">
            ${items
              .map((it) => {
                const val = String(it[idField] || '');
                const label = String(it.name || val);
                const isSel = selectedList.includes(val);
                return `<button type="button" class="auto-notif-chip ${isSel ? 'active' : ''}" data-act-toggle-target="${escapeHtml(pathStr)}:${listKey}:${escapeHtml(val)}">${escapeHtml(label)}</button>`;
              })
              .join('')}
          </div>
        `;
      };

      const msgMode = String(p.message_mode || 'auto_scene');
      const imgMode = String(p.image_mode || 'annotated');
      const prio = String(p.priority || 'normal');
      const btnList = Array.isArray(p.actions) ? p.actions : [];
      const ttsListId = sanitizeControlId(`auto-tts-entities-${pathStr}`);
      const msgCtrlId = sanitizeControlId(`auto-act-${pathStr}-message`);

      const varChipsHtml = NOTIFICATION_TEMPLATE_VARS.map(
        (v) =>
          `<button type="button" class="auto-chip" data-act-insert-var="${escapeHtml(pathStr)}:message:${escapeHtml(v.token)}" title="${escapeHtml(v.token)}">${escapeHtml(v.label)}</button>`
      ).join('');

      bodyHtml = `
        <div class="auto-notif-builder">
          <div class="auto-grid-2">
            <label class="auto-field">
              <span>Priorità</span>
              <select ${this._ctrl('act', pathStr, 'priority')} data-act-param="${escapeHtml(pathStr)}:priority">
                <option value="silent" ${prio === 'silent' ? 'selected' : ''}>Silenziosa (senza suono)</option>
                <option value="normal" ${prio === 'normal' ? 'selected' : ''}>Normale</option>
                <option value="critical" ${prio === 'critical' ? 'selected' : ''}>Critica (bypassa DND)</option>
              </select>
            </label>
            <label class="auto-field">
              <span>Immagine allegata</span>
              <select ${this._ctrl('act', pathStr, 'image_mode')} data-act-param="${escapeHtml(pathStr)}:image_mode">
                <option value="annotated" ${imgMode === 'annotated' ? 'selected' : ''}>Frame migliore + box nomi</option>
                <option value="raw" ${imgMode === 'raw' ? 'selected' : ''}>Frame originale pulito</option>
                <option value="crop" ${imgMode === 'crop' ? 'selected' : ''}>Solo ritaglio volto/targa</option>
                <option value="none" ${imgMode === 'none' ? 'selected' : ''}>Nessuna immagine</option>
              </select>
            </label>
          </div>

          <div class="auto-notif-group">
            <span class="auto-notif-label">Telefoni e tablet (HA Companion)</span>
            ${renderChips(mobileDisc, mobileTargets, 'mobile_targets', 'service')}
            <input type="text" ${this._ctrl('act', pathStr, 'mobile_targets')} data-act-list="${escapeHtml(pathStr)}:mobile_targets" value="${escapeHtml(mobileTargets.join(', '))}" aria-label="Servizi notifica mobile" placeholder="Es. notify.mobile_app_telefono" />
          </div>

          <div class="auto-grid-2">
            <label class="auto-field">
              <span>Testo notifica</span>
              <select ${this._ctrl('act', pathStr, 'message_mode')} data-act-param="${escapeHtml(pathStr)}:message_mode">
                <option value="auto_scene" ${msgMode === 'auto_scene' ? 'selected' : ''}>Frase automatica (persone + targhe)</option>
                <option value="custom" ${msgMode === 'custom' ? 'selected' : ''}>Testo personalizzato</option>
              </select>
            </label>
            <label class="auto-field">
              <span>Luogo (opzionale)</span>
              <input type="text" ${this._ctrl('act', pathStr, 'location_label')} data-act-param="${escapeHtml(pathStr)}:location_label" value="${escapeHtml(p.location_label || '')}" placeholder="es. al cancelletto" />
            </label>
            <label class="auto-field span-2">
              <span>Titolo notifica</span>
              <input type="text" ${this._ctrl('act', pathStr, 'title')} data-act-param="${escapeHtml(pathStr)}:title" value="${escapeHtml(p.title || '')}" placeholder="Smart Home 3D" />
            </label>
            ${
              msgMode === 'custom'
                ? `<div class="auto-field span-2">
                     <label for="${msgCtrlId}"><span>Messaggio personalizzato</span></label>
                     <textarea id="${msgCtrlId}" name="${msgCtrlId}" rows="2" class="auto-textarea" data-act-param="${escapeHtml(pathStr)}:message" placeholder="Es. Rilevato {{ track.identity }} in {{ trigger.zone_name }}">${escapeHtml(p.message || '')}</textarea>
                     <div class="auto-var-chips" aria-label="Inserisci variabili">
                       ${varChipsHtml}
                     </div>
                   </div>`
                : ''
            }
          </div>

          <label class="auto-check-row">
            <input type="checkbox" ${this._ctrl('act', pathStr, 'update_on_biometrics')} data-act-bool="${escapeHtml(pathStr)}:update_on_biometrics" ${p.update_on_biometrics !== false ? 'checked' : ''} />
            <span>Aggiorna silenziosamente se volto o targa vengono riconosciuti dopo</span>
          </label>

          <div class="auto-notif-group">
            <div class="auto-block-header">
              <span class="auto-notif-label">Pulsanti interattivi</span>
              <div class="auto-notif-preset-bar">
                <button type="button" class="auto-btn ghost xs" data-act-notif-btn-preset="${escapeHtml(pathStr)}:gate">+ Apri cancelletto</button>
                <button type="button" class="auto-btn ghost xs" data-act-notif-btn-preset="${escapeHtml(pathStr)}:alarm_off">+ Spento</button>
                <button type="button" class="auto-btn ghost xs" data-act-notif-btn-preset="${escapeHtml(pathStr)}:alarm_silent">+ Silenzioso</button>
                <button type="button" class="auto-btn tonal xs" data-act-notif-btn-add="${escapeHtml(pathStr)}">${icon('plus', { size: 11 })} <span>Pulsante</span></button>
              </div>
            </div>
            ${
              btnList.length > 0
                ? `<div class="auto-notif-buttons-list">
                     ${btnList
                       .map(
                         (b, bIdx) => `
                       <div class="auto-notif-btn-row">
                         <input type="text" ${this._ctrl('act-btn', `${pathStr}_${bIdx}`, 'title')} data-act-notif-btn-field="${escapeHtml(pathStr)}:${bIdx}:title" value="${escapeHtml(b.title || '')}" aria-label="Etichetta pulsante ${bIdx + 1}" placeholder="Etichetta" />
                         <input type="text" ${this._ctrl('act-btn', `${pathStr}_${bIdx}`, 'action')} data-act-notif-btn-field="${escapeHtml(pathStr)}:${bIdx}:action" value="${escapeHtml(b.action || '')}" aria-label="Azione pulsante ${bIdx + 1}" placeholder="SH3D_ALARM_SPENTO" />
                         <button type="button" class="auto-btn icon-only danger xs" data-act-notif-btn-del="${escapeHtml(pathStr)}:${bIdx}" title="Rimuovi pulsante" aria-label="Rimuovi pulsante">${icon('x', { size: 12 })}</button>
                       </div>`
                       )
                       .join('')}
                   </div>`
                : ''
            }
          </div>

          <div class="auto-notif-group">
            <span class="auto-notif-label">Speaker / Display TTS</span>
            ${renderChips(mediaPlayersDisc, ttsTargets, 'tts_targets', 'entity_id')}
            <div class="auto-grid-2">
              <label class="auto-field">
                <span>Media Player</span>
                <input type="text" ${this._ctrl('act', pathStr, 'tts_targets')} data-act-list="${escapeHtml(pathStr)}:tts_targets" value="${escapeHtml(ttsTargets.join(', '))}" placeholder="Es. media_player.altoparlante" />
              </label>
              <label class="auto-field">
                <span>Motore TTS HA</span>
                <input type="text" list="${ttsListId}" ${this._ctrl('act', pathStr, 'tts_entity')} data-act-param="${escapeHtml(pathStr)}:tts_entity" value="${escapeHtml(p.tts_entity || '')}" placeholder="Es. tts.google_translate" />
                <datalist id="${ttsListId}">
                  ${ttsEntitiesDisc.map((t) => `<option value="${escapeHtml(t.entity_id)}">${escapeHtml(t.name)}</option>`).join('')}
                </datalist>
              </label>
            </div>
          </div>

          <div class="auto-notif-group">
            <span class="auto-notif-label">TV (Toast)</span>
            ${renderChips(tvDisc, tvTargets, 'tv_targets', 'service')}
            <input type="text" ${this._ctrl('act', pathStr, 'tv_targets')} data-act-list="${escapeHtml(pathStr)}:tv_targets" value="${escapeHtml(tvTargets.join(', '))}" aria-label="Servizi notifica TV" placeholder="Es. notify.tv_salotto" />
          </div>

          <details class="auto-subtle-disclosure" ${this._detailsAttrs(`notif-adv-${pathStr}`)}>
            <summary class="auto-subtle-summary">
              <span>Opzioni extra notifica</span>
              ${icon('chevron-down', { size: 12, className: 'auto-details-chevron' })}
            </summary>
            <div class="auto-subtle-body auto-grid-2">
              <label class="auto-field span-2">
                <span>Tag aggiornamento (vuoto = episodio)</span>
                <input type="text" ${this._ctrl('act', pathStr, 'tag')} data-act-param="${escapeHtml(pathStr)}:tag" value="${escapeHtml(p.tag || '')}" placeholder="es. avviso_ingresso" />
              </label>
              <label class="auto-check-row">
                <input type="checkbox" ${this._ctrl('act', pathStr, 'display_show_image')} data-act-bool="${escapeHtml(pathStr)}:display_show_image" ${p.display_show_image !== false ? 'checked' : ''} />
                <span>Mostra foto sul display</span>
              </label>
              <label class="auto-field">
                <span>Durata foto display (s)</span>
                <input type="number" min="5" max="120" step="1" ${this._ctrl('act', pathStr, 'display_duration_s')} data-act-param="${escapeHtml(pathStr)}:display_duration_s" value="${Number(p.display_duration_s ?? 25)}" />
              </label>
              <label class="auto-check-row span-2">
                <input type="checkbox" ${this._ctrl('act', pathStr, 'tv_only_when_on')} data-act-bool="${escapeHtml(pathStr)}:tv_only_when_on" ${p.tv_only_when_on !== false ? 'checked' : ''} />
                <span>Invia alla TV solo quando è accesa</span>
              </label>
            </div>
          </details>
        </div>
      `;
    } else if (aType === 'ui_alert') {
      bodyHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Titolo</span>
            <input type="text" ${this._ctrl('act', pathStr, 'title')} data-act-param="${escapeHtml(pathStr)}:title" value="${escapeHtml(p.title || '')}" placeholder="Es. Avviso giardino" />
          </label>
          <label class="auto-field">
            <span>Livello</span>
            <select ${this._ctrl('act', pathStr, 'severity')} data-act-param="${escapeHtml(pathStr)}:severity">
              <option value="critical" ${p.severity === 'critical' ? 'selected' : ''}>Critico + Sirena</option>
              <option value="warning" ${(!p.severity || p.severity === 'warning') ? 'selected' : ''}>Avviso</option>
              <option value="info" ${p.severity === 'info' ? 'selected' : ''}>Notifica</option>
            </select>
          </label>
          <label class="auto-field span-2">
            <span>Messaggio</span>
            <input type="text" ${this._ctrl('act', pathStr, 'message')} data-act-param="${escapeHtml(pathStr)}:message" value="${escapeHtml(p.message || '')}" placeholder="Es. {{ trigger.summary }}" />
          </label>
          <label class="auto-check-row span-2">
            <input type="checkbox" ${this._ctrl('act', pathStr, 'sound')} data-act-bool="${escapeHtml(pathStr)}:sound" ${p.sound !== false ? 'checked' : ''} />
            <span>Riproduci suono avviso</span>
          </label>
        </div>
      `;
    } else if (aType === 'delay') {
      bodyHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Secondi di attesa</span>
            <input type="number" min="0.5" max="3600" step="0.5" ${this._ctrl('act', pathStr, 'seconds')} data-act-param="${escapeHtml(pathStr)}:seconds" value="${Number(p.seconds ?? 10)}" />
          </label>
        </div>
      `;
    } else if (aType === 'webhook') {
      bodyHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>URL Webhook (HTTP POST)</span>
            <input type="url" ${this._ctrl('act', pathStr, 'url')} data-act-param="${escapeHtml(pathStr)}:url" value="${escapeHtml(p.url || '')}" placeholder="https://..." />
          </label>
        </div>
      `;
    } else if (aType === 'if_then_else') {
      if (!act.if_condition) {
        act.if_condition = {
          condition_id: `cnd_${Math.random().toString(36).slice(2, 9)}`,
          type: 'entity_state',
          children: [],
          params: defaultConditionParamsForType('entity_state', this._ctx()),
        };
      }
      const thenList = Array.isArray(act.then_actions) ? act.then_actions : [];
      const elseList = Array.isArray(act.else_actions) ? act.else_actions : [];
      bodyHtml = `
        <div class="auto-ifelse-container">
          <div class="auto-ifelse-part">
            <span class="auto-ifelse-tag">Se (Condizione)</span>
            ${this._renderConditionNodeHtml(act.if_condition, `act_if:${pathStr}`, true)}
          </div>
          <div class="auto-ifelse-part">
            <div class="auto-block-header">
              <span class="auto-ifelse-tag">Allora (Then)</span>
              <button type="button" class="auto-btn tonal xs" data-act-add-sub="${escapeHtml(pathStr)}:then">
                ${icon('plus', { size: 11 })} <span>Azione</span>
              </button>
            </div>
            <div class="auto-stack">
              ${thenList.map((sa, sIdx) => this._renderActionItemHtml(sa, `${pathStr}.then.${sIdx}`)).join('')}
            </div>
          </div>
          <div class="auto-ifelse-part">
            <div class="auto-block-header">
              <span class="auto-ifelse-tag">Altrimenti (Else)</span>
              <button type="button" class="auto-btn ghost xs" data-act-add-sub="${escapeHtml(pathStr)}:else">
                ${icon('plus', { size: 11 })} <span>Azione</span>
              </button>
            </div>
            <div class="auto-stack">
              ${elseList.map((sa, sIdx) => this._renderActionItemHtml(sa, `${pathStr}.else.${sIdx}`)).join('')}
            </div>
          </div>
        </div>
      `;
    }

    return `
      <div class="auto-node-surface" data-action-card="${escapeHtml(pathStr)}">
        <div class="auto-node-bar">
          <select class="auto-node-type-select" ${this._ctrl('act-type', pathStr, 'type')} data-act-type-path="${escapeHtml(pathStr)}" aria-label="Tipo azione">
            ${Object.entries(ACTION_TYPE_LABELS)
              .map(([k, label]) => `<option value="${k}" ${aType === k ? 'selected' : ''}>${escapeHtml(label)}</option>`)
              .join('')}
          </select>
          <button type="button" class="auto-btn icon-only danger xs" data-del-act-path="${escapeHtml(pathStr)}" title="Rimuovi azione" aria-label="Rimuovi azione">
            ${icon('x', { size: 13 })}
          </button>
        </div>
        ${bodyHtml}
      </div>
    `;
  }

  _ctx() {
    return {
      zones: this.studio.zones,
      virtualEntities: this.studio.virtualEntities,
      haDiscovery: this.studio.haDiscovery,
      haEntities: this.studio.haClient?.entities || {},
    };
  }

  _updateLiveSummary() {
    const el = this.studio.bodyEl?.querySelector('#rule-live-summary');
    if (el && this.studio.editingRule) {
      el.textContent = buildRuleSummaryItalian(this.studio.editingRule, { zones: this.studio.zones });
    }
    this.studio._updateDirtyIndicator();
  }

  _resolveTrigger(pathStr) {
    const r = this.studio.editingRule;
    if (!r || !pathStr) return { list: null, idx: -1, trig: null };
    const parts = String(pathStr).split(':');
    if (parts[0] === 'pre' && parts.length === 3) {
      const sIdx = Number(parts[1]);
      const tIdx = Number(parts[2]);
      const list = r.pre_triggers?.[sIdx]?.triggers;
      return { list, idx: tIdx, trig: list?.[tIdx] || null };
    }
    const idx = parts[0] === 'main' ? Number(parts[1]) : Number(parts[0]);
    return { list: r.triggers, idx, trig: r.triggers?.[idx] || null };
  }

  _resolveConditionNode(pathStr) {
    const r = this.studio.editingRule;
    if (pathStr.startsWith('pre_cond:')) {
      const sub = pathStr.slice('pre_cond:'.length);
      const parts = sub.split('.');
      const stg = r?.pre_triggers?.[Number(parts[0])];
      if (!stg) return { node: null, parent: null, idx: -1 };
      if (parts.length === 1) return { node: stg.condition, parent: null, idx: -1 };
      let curr = stg.condition;
      let parent = null;
      let lastIdx = -1;
      for (let i = 1; i < parts.length; i++) {
        parent = curr;
        lastIdx = Number(parts[i]);
        curr = curr?.children?.[lastIdx];
      }
      return { node: curr, parent, idx: lastIdx };
    }

    if (pathStr.startsWith('act_if:')) {
      const sub = pathStr.slice('act_if:'.length);
      const parts = sub.split('.');
      const act = this._resolveActionNode(parts[0]);
      if (!act) return { node: null, parent: null, idx: -1 };
      if (parts.length === 1) return { node: act.if_condition, parent: null, idx: -1 };
      let curr = act.if_condition;
      let parent = null;
      let lastIdx = -1;
      for (let i = 1; i < parts.length; i++) {
        parent = curr;
        lastIdx = Number(parts[i]);
        curr = curr?.children?.[lastIdx];
      }
      return { node: curr, parent, idx: lastIdx };
    }

    const parts = pathStr.split('.');
    let curr = r?.condition;
    let parent = null;
    let lastIdx = -1;
    for (let i = 1; i < parts.length; i++) {
      parent = curr;
      lastIdx = Number(parts[i]);
      curr = curr?.children?.[lastIdx];
    }
    return { node: curr, parent, idx: lastIdx };
  }

  _resolveActionListAndIndex(pathStr) {
    const parts = pathStr.split('.');
    let list = this.studio.editingRule?.actions;
    for (let i = 0; i < parts.length - 1; i += 2) {
      const act = list?.[Number(parts[i])];
      const branch = parts[i + 1];
      if (!act) return { list: null, idx: -1, node: null };
      list = branch === 'else' ? act.else_actions : act.then_actions;
    }
    const idx = Number(parts[parts.length - 1]);
    return { list, idx, node: list?.[idx] || null };
  }

  _resolveActionNode(pathStr) {
    return this._resolveActionListAndIndex(pathStr).node;
  }

  bindEvents() {
    const body = this.studio.bodyEl;
    const r = this.studio.editingRule;
    if (!body || !r) return;

    // Persist open/closed state for <details>
    body.querySelectorAll('details[data-details-id]').forEach((det) => {
      det.addEventListener('toggle', () => {
        const id = det.dataset.detailsId;
        if (det.open) this.studio._openDetailsIds.add(id);
        else this.studio._openDetailsIds.delete(id);
      });
    });

    body.querySelector('#btn-auto-rule-back')?.addEventListener('click', () => {
      this.studio._requestExitEditor();
    });

    body.querySelector('#rule-inp-name')?.addEventListener('input', (e) => {
      r.name = e.target.value;
      this.studio._updateDirtyIndicator();
    });
    body.querySelector('#rule-inp-desc')?.addEventListener('input', (e) => {
      r.description = e.target.value;
      this.studio._updateDirtyIndicator();
    });
    body.querySelector('#rule-inp-exec-mode')?.addEventListener('change', (e) => {
      r.execution_mode = e.target.value;
      this.studio._updateDirtyIndicator();
    });
    body.querySelector('#rule-inp-cooldown')?.addEventListener('input', (e) => {
      const parsed = parseFloat(e.target.value);
      r.cooldown_s = Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
      this.studio._updateDirtyIndicator();
    });
    body.querySelector('#rule-inp-log-blocked')?.addEventListener('change', (e) => {
      r.log_blocked_evaluations = Boolean(e.target.checked);
      this.studio._updateDirtyIndicator();
    });

    body.querySelector('#rule-inp-trigger-logic')?.addEventListener('change', (e) => {
      r.trigger_logic = e.target.value;
      this.studio.renderBodyPreservingScroll();
    });
    body.querySelector('#rule-inp-trigger-window')?.addEventListener('input', (e) => {
      const parsed = parseFloat(e.target.value);
      r.trigger_window_s = Number.isFinite(parsed) ? Math.max(0.5, parsed) : 10;
      this.studio._updateDirtyIndicator();
    });
    body.querySelector('#rule-inp-trigger-corr')?.addEventListener('change', (e) => {
      r.trigger_correlation_scope = e.target.value;
      this.studio._updateDirtyIndicator();
    });

    // Pre-triggers
    body.querySelector('#btn-rule-add-pretrigger')?.addEventListener('click', () => {
      const newIdx = r.pre_triggers.length;
      r.pre_triggers.push(createBlankPreTriggerStage(newIdx));
      this.studio.renderBodyPreservingScroll({ scrollToNewSelector: `[data-pre-stage-idx="${newIdx}"]` });
    });

    body.querySelectorAll('[data-del-pre-idx]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sIdx = Number(btn.dataset.delPreIdx);
        r.pre_triggers.splice(sIdx, 1);
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-pre-field]').forEach((inp) => {
      const handler = () => {
        const lastColon = inp.dataset.preField.lastIndexOf(':');
        const sIdx = Number(inp.dataset.preField.slice(0, lastColon));
        const key = inp.dataset.preField.slice(lastColon + 1);
        const stg = r.pre_triggers[sIdx];
        if (!stg) return;
        let val = inp.value;
        if (inp.type === 'number') {
          const parsed = parseFloat(val);
          val = Number.isFinite(parsed) ? parsed : 0;
        }
        stg[key] = val;
        if (key === 'match_mode') {
          this.studio.renderBodyPreservingScroll();
        } else if (key === 'max_wait_s') {
          const card = inp.closest('.auto-pretrigger-card');
          const conn = card?.nextElementSibling?.querySelector('span');
          if (conn) {
            const nextLabel = sIdx + 1 < r.pre_triggers.length ? `Fase ${sIdx + 2}` : 'Trigger principali';
            conn.textContent = `Attende max ${Number(val || 10)}s prima di ${nextLabel}`;
          }
          this._updateLiveSummary();
        } else {
          this._updateLiveSummary();
        }
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });

    body.querySelectorAll('[data-pre-bool]').forEach((chk) => {
      chk.addEventListener('change', () => {
        const lastColon = chk.dataset.preBool.lastIndexOf(':');
        const sIdx = Number(chk.dataset.preBool.slice(0, lastColon));
        const key = chk.dataset.preBool.slice(lastColon + 1);
        const stg = r.pre_triggers[sIdx];
        if (!stg) return;
        stg[key] = Boolean(chk.checked);
        this.studio._updateDirtyIndicator();
      });
    });

    body.querySelectorAll('[data-pre-add-trig]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sIdx = Number(btn.dataset.preAddTrig);
        const stg = r.pre_triggers[sIdx];
        if (!stg) return;
        stg.triggers = stg.triggers || [];
        const tIdx = stg.triggers.length;
        const t = createBlankTrigger('zone_presence', this._ctx());
        t.subject_filter.classes = ['vehicle'];
        stg.triggers.push(t);
        this.studio.renderBodyPreservingScroll({ scrollToNewSelector: `[data-trigger-card="pre:${sIdx}:${tIdx}"]` });
      });
    });

    body.querySelectorAll('[data-pre-toggle-cond]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sIdx = Number(btn.dataset.preToggleCond);
        const stg = r.pre_triggers[sIdx];
        if (!stg) return;
        stg.condition = stg.condition
          ? null
          : { condition_id: `cnd_${Math.random().toString(36).slice(2, 9)}`, type: 'and', children: [], params: {} };
        this.studio.renderBodyPreservingScroll();
      });
    });

    // Main triggers
    body.querySelector('#btn-rule-add-trigger')?.addEventListener('click', () => {
      const idx = r.triggers.length;
      r.triggers.push(createBlankTrigger('zone_presence', this._ctx()));
      this.studio.renderBodyPreservingScroll({ scrollToNewSelector: `[data-trigger-card="main:${idx}"]` });
    });

    body.querySelectorAll('[data-del-trig-path]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const { list, idx } = this._resolveTrigger(btn.dataset.delTrigPath);
        if (Array.isArray(list) && idx >= 0 && list.length > 1) {
          list.splice(idx, 1);
          this.studio.renderBodyPreservingScroll();
        }
      });
    });

    body.querySelectorAll('[data-trig-type-path]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const { trig } = this._resolveTrigger(sel.dataset.trigTypePath);
        if (!trig) return;
        trig.type = sel.value;
        trig.params = defaultTriggerParamsForType(sel.value, this._ctx());
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-trig-param]').forEach((inp) => {
      const handler = (ev) => {
        const lastColon = inp.dataset.trigParam.lastIndexOf(':');
        const pathStr = inp.dataset.trigParam.slice(0, lastColon);
        const key = inp.dataset.trigParam.slice(lastColon + 1);
        const { trig } = this._resolveTrigger(pathStr);
        if (!trig) return;
        let val = inp.value;
        if (inp.type === 'number') {
          const parsed = parseFloat(val);
          val = val === '' ? null : (Number.isFinite(parsed) ? parsed : null);
        }
        trig.params = trig.params || {};
        trig.params[key] = val;

        if ((key === 'mode' || key === 'event') && ev.type === 'change' && (trig.type === 'time_schedule' || trig.type === 'zone_presence')) {
          if (key === 'event' && val !== 'dwell') {
            trig.params.min_dwell_s = 0;
          }
          this.studio.renderBodyPreservingScroll();
          return;
        }

        if (
          trig.type === 'kinematic_vector' &&
          (key === 'target_azimuth_deg' || key === 'azimuth_tolerance_deg' || key === 'zone_id')
        ) {
          const az = trig.params.target_azimuth_deg;
          if (az === null || az === undefined || az === '') {
            this.studio.zoneRenderer?.hideDirectionCone?.();
          } else {
            this.studio.zoneRenderer?.showDirectionCone?.({
              azimuthDeg: az,
              toleranceDeg: trig.params.azimuth_tolerance_deg,
              zoneId: trig.params.zone_id,
            });
          }
        }
        this._updateLiveSummary();
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });

    body.querySelectorAll('[data-trig-bool]').forEach((chk) => {
      chk.addEventListener('change', () => {
        const lastColon = chk.dataset.trigBool.lastIndexOf(':');
        const pathStr = chk.dataset.trigBool.slice(0, lastColon);
        const key = chk.dataset.trigBool.slice(lastColon + 1);
        const { trig } = this._resolveTrigger(pathStr);
        if (!trig) return;
        trig.params = trig.params || {};
        trig.params[key] = Boolean(chk.checked);
        this.studio._updateDirtyIndicator();
      });
    });

    // + Disegna 3D (stash rule draft and return with newly created zone selected)
    body.querySelectorAll('[data-quick-new-zone]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const parts = btn.dataset.quickNewZone.split(':');
        const gType = parts[0] || 'polygon';
        const targetKey = parts.pop();
        const targetPath = parts.slice(1).join(':');
        this.studio._startZoneDraftFromRule({
          geometryType: gType,
          targetPath,
          targetKey,
        });
      });
    });

    body.querySelectorAll('[data-pick-direction-3d]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const { trig } = this._resolveTrigger(btn.dataset.pickDirection3d);
        if (!trig) return;
        this.studio.setCollapsed(true);
        this.studio.setStatus('Clicca nel 3D il punto di partenza e poi il punto di direzione.', 'info');
        this.studio.zoneRenderer?.startDirectionPicking?.({
          onDirectionPicked: ({ azimuthDeg }) => {
            trig.params.target_azimuth_deg = azimuthDeg;
            this.studio.setCollapsed(false);
            this.studio.setStatus(`Direzione impostata a ${azimuthDeg}°`, 'success');
            this.studio.renderBodyPreservingScroll();
          },
        });
      });
    });

    // Subject filter
    body.querySelectorAll('[data-trig-sf]').forEach((inp) => {
      const handler = (ev) => {
        const lastColon = inp.dataset.trigSf.lastIndexOf(':');
        const pathStr = inp.dataset.trigSf.slice(0, lastColon);
        const key = inp.dataset.trigSf.slice(lastColon + 1);
        const { trig } = this._resolveTrigger(pathStr);
        if (!trig) return;
        trig.subject_filter = trig.subject_filter || {};
        if (key === 'classes') {
          trig.subject_filter.classes = [inp.value || 'any'];
          if (inp.value === 'vehicle') {
            trig.subject_filter.face_mode = 'any';
            trig.subject_filter.identities = [];
          } else if (inp.value === 'person') {
            trig.subject_filter.plate_mode = 'any';
            trig.subject_filter.plates = [];
          } else if (inp.value !== 'any') {
            trig.subject_filter.face_mode = 'any';
            trig.subject_filter.identities = [];
            trig.subject_filter.plate_mode = 'any';
            trig.subject_filter.plates = [];
          }
          if (ev.type === 'change') {
            this.studio.renderBodyPreservingScroll();
            return;
          }
        } else if (key === 'identities' || key === 'plates') {
          trig.subject_filter[key] = String(inp.value || '')
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean);
        } else if (key === 'biometric_grace_s') {
          const parsed = parseFloat(inp.value);
          trig.subject_filter.biometric_grace_s = Number.isFinite(parsed) ? roundClean(Math.max(0, parsed), 2) : 0;
        } else {
          trig.subject_filter[key] = inp.value;
          if ((key === 'face_mode' || key === 'plate_mode') && ev.type === 'change') {
            this.studio.renderBodyPreservingScroll();
            return;
          }
        }
        this._updateLiveSummary();
      };
      inp.addEventListener('change', handler);
      if (inp.tagName === 'INPUT') inp.addEventListener('input', handler);
    });

    body.querySelectorAll('[data-trig-id-chip]').forEach((chip) => {
      chip.addEventListener('click', () => {
        const lastColon = chip.dataset.trigIdChip.lastIndexOf(':');
        const pathStr = chip.dataset.trigIdChip.slice(0, lastColon);
        const name = chip.dataset.trigIdChip.slice(lastColon + 1);
        const { trig } = this._resolveTrigger(pathStr);
        if (!trig) return;
        trig.subject_filter = trig.subject_filter || {};
        const list = Array.isArray(trig.subject_filter.identities) ? trig.subject_filter.identities : [];
        const existingIdx = list.findIndex((s) => s.toLowerCase() === name.toLowerCase());
        if (existingIdx >= 0) list.splice(existingIdx, 1);
        else list.push(name);
        trig.subject_filter.identities = list;
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-trig-plate-chip]').forEach((chip) => {
      chip.addEventListener('click', () => {
        const lastColon = chip.dataset.trigPlateChip.lastIndexOf(':');
        const pathStr = chip.dataset.trigPlateChip.slice(0, lastColon);
        const plate = chip.dataset.trigPlateChip.slice(lastColon + 1);
        const { trig } = this._resolveTrigger(pathStr);
        if (!trig) return;
        trig.subject_filter = trig.subject_filter || {};
        const list = Array.isArray(trig.subject_filter.plates) ? trig.subject_filter.plates : [];
        const existingIdx = list.findIndex((s) => s.toUpperCase() === plate.toUpperCase());
        if (existingIdx >= 0) list.splice(existingIdx, 1);
        else list.push(plate);
        trig.subject_filter.plates = list;
        this.studio.renderBodyPreservingScroll();
      });
    });

    this._bindConditionEvents(body);
    this._bindActionEvents(body);
  }

  _bindConditionEvents(body) {
    body.querySelectorAll('[data-cond-type-path]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const { node } = this._resolveConditionNode(sel.dataset.condTypePath);
        if (!node) return;
        const nextType = sel.value;
        node.type = nextType;
        if (['and', 'or', 'not', 'xor'].includes(nextType)) {
          node.children = node.children || [];
        } else {
          node.params = defaultConditionParamsForType(nextType, this._ctx());
        }
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-cond-add-leaf]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const pathStr = btn.dataset.condAddLeaf;
        const { node } = this._resolveConditionNode(pathStr);
        if (!node) return;
        node.children = node.children || [];
        const newIdx = node.children.length;
        node.children.push({
          condition_id: `cnd_${Math.random().toString(36).slice(2, 9)}`,
          type: 'entity_state',
          children: [],
          params: defaultConditionParamsForType('entity_state', this._ctx()),
        });
        this.studio.renderBodyPreservingScroll({ scrollToNewSelector: `[data-cond-card="${pathStr}.${newIdx}"]` });
      });
    });

    body.querySelectorAll('[data-cond-add-group]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const pathStr = btn.dataset.condAddGroup;
        const { node } = this._resolveConditionNode(pathStr);
        if (!node) return;
        node.children = node.children || [];
        node.children.push({
          condition_id: `cnd_${Math.random().toString(36).slice(2, 9)}`,
          type: 'or',
          children: [],
          params: {},
        });
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-cond-del-path]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const { parent, idx } = this._resolveConditionNode(btn.dataset.condDelPath);
        if (parent && Array.isArray(parent.children) && idx >= 0) {
          parent.children.splice(idx, 1);
          this.studio.renderBodyPreservingScroll();
        }
      });
    });

    body.querySelectorAll('[data-cond-param]').forEach((inp) => {
      const handler = (ev) => {
        const lastColon = inp.dataset.condParam.lastIndexOf(':');
        const pathStr = inp.dataset.condParam.slice(0, lastColon);
        const key = inp.dataset.condParam.slice(lastColon + 1);
        const { node } = this._resolveConditionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        if (node.type === 'subject_filter') {
          if (key === 'classes') {
            node.params.classes = [inp.value || 'any'];
          } else if (key === 'identities' || key === 'plates') {
            node.params[key] = String(inp.value || '')
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean);
          } else {
            node.params[key] = inp.value;
            if ((key === 'face_mode' || key === 'plate_mode') && ev.type === 'change') {
              this.studio.renderBodyPreservingScroll();
              return;
            }
          }
          this._updateLiveSummary();
          return;
        }
        if (inp.type === 'number') {
          const parsed = parseFloat(inp.value);
          node.params[key] = inp.value === '' ? null : (Number.isFinite(parsed) ? parsed : null);
        } else {
          node.params[key] = inp.value;
        }
        this._updateLiveSummary();
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });
  }

  _bindActionEvents(body) {
    const r = this.studio.editingRule;

    body.querySelector('#btn-rule-add-action')?.addEventListener('click', () => {
      const idx = r.actions.length;
      r.actions.push(defaultActionForType('call_ha_service', this._ctx()));
      this.studio.renderBodyPreservingScroll({ scrollToNewSelector: `[data-action-card="${idx}"]` });
    });

    body.querySelectorAll('[data-quick-add-action]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const aType = btn.dataset.quickAddAction;
        const idx = r.actions.length;
        r.actions.push(defaultActionForType(aType, this._ctx()));
        this.studio.renderBodyPreservingScroll({ scrollToNewSelector: `[data-action-card="${idx}"]` });
      });
    });

    body.querySelectorAll('[data-act-type-path]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const node = this._resolveActionNode(sel.dataset.actTypePath);
        if (!node) return;
        const fresh = defaultActionForType(sel.value, this._ctx());
        node.type = fresh.type;
        node.params = fresh.params;
        if (fresh.type === 'if_then_else') {
          node.if_condition = node.if_condition || fresh.if_condition;
          node.then_actions = Array.isArray(node.then_actions) ? node.then_actions : [];
          node.else_actions = Array.isArray(node.else_actions) ? node.else_actions : [];
        } else {
          delete node.if_condition;
          node.then_actions = [];
          node.else_actions = [];
        }
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-del-act-path]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const { list, idx } = this._resolveActionListAndIndex(btn.dataset.delActPath);
        if (Array.isArray(list) && idx >= 0) {
          list.splice(idx, 1);
          this.studio.renderBodyPreservingScroll();
        }
      });
    });

    body.querySelectorAll('[data-act-add-sub]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const [pathStr, branch] = btn.dataset.actAddSub.split(':');
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        const targetArr =
          branch === 'else'
            ? (node.else_actions = node.else_actions || [])
            : (node.then_actions = node.then_actions || []);
        const sIdx = targetArr.length;
        targetArr.push(defaultActionForType('call_ha_service', this._ctx()));
        this.studio.renderBodyPreservingScroll({
          scrollToNewSelector: `[data-action-card="${pathStr}.${branch}.${sIdx}"]`,
        });
      });
    });

    body.querySelectorAll('[data-act-param]').forEach((inp) => {
      const handler = (ev) => {
        const lastColon = inp.dataset.actParam.lastIndexOf(':');
        const pathStr = inp.dataset.actParam.slice(0, lastColon);
        const key = inp.dataset.actParam.slice(lastColon + 1);
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        if (inp.type === 'number') {
          const parsed = parseFloat(inp.value);
          node.params[key] = Number.isFinite(parsed) ? parsed : 0;
        } else {
          node.params[key] = inp.value;
        }

        if (
          ev.type === 'change' &&
          ((node.type === 'send_notification' && key === 'message_mode') ||
            (node.type === 'set_virtual_entity' && (key === 'operation' || key === 'entity_id')))
        ) {
          this.studio.renderBodyPreservingScroll();
          return;
        }
        this._updateLiveSummary();
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });

    body.querySelectorAll('[data-act-insert-var]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const parts = btn.dataset.actInsertVar.split(':');
        const pathStr = parts[0];
        const key = parts[1];
        const token = parts.slice(2).join(':');
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        const cur = String(node.params[key] || '');
        node.params[key] = cur ? `${cur.trimEnd()} ${token}` : token;
        const field = body.querySelector(`[data-act-param="${pathStr}:${key}"]`);
        if (field) {
          field.value = node.params[key];
          field.focus?.();
        }
        this._updateLiveSummary();
      });
    });

    body.querySelectorAll('[data-act-bool]').forEach((chk) => {
      chk.addEventListener('change', () => {
        const lastColon = chk.dataset.actBool.lastIndexOf(':');
        const pathStr = chk.dataset.actBool.slice(0, lastColon);
        const key = chk.dataset.actBool.slice(lastColon + 1);
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        node.params[key] = Boolean(chk.checked);
        this.studio._updateDirtyIndicator();
      });
    });

    body.querySelectorAll('[data-act-list]').forEach((inp) => {
      const handler = () => {
        const lastColon = inp.dataset.actList.lastIndexOf(':');
        const pathStr = inp.dataset.actList.slice(0, lastColon);
        const key = inp.dataset.actList.slice(lastColon + 1);
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        node.params[key] = String(inp.value || '')
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        this._updateLiveSummary();
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });

    body.querySelectorAll('[data-act-json]').forEach((inp) => {
      const handler = () => {
        const lastColon = inp.dataset.actJson.lastIndexOf(':');
        const pathStr = inp.dataset.actJson.slice(0, lastColon);
        const key = inp.dataset.actJson.slice(lastColon + 1);
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        const raw = String(inp.value || '').trim();
        if (!raw) {
          delete node.params[key];
          inp.setCustomValidity?.('');
          this.studio._updateDirtyIndicator();
          return;
        }
        try {
          const parsed = JSON.parse(raw);
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            node.params[key] = parsed;
            inp.setCustomValidity?.('');
          } else {
            inp.setCustomValidity?.('Inserire un oggetto JSON valido');
          }
        } catch {
          inp.setCustomValidity?.('JSON non valido');
        }
        this.studio._updateDirtyIndicator();
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });

    body.querySelectorAll('[data-act-toggle-target]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const parts = btn.dataset.actToggleTarget.split(':');
        if (parts.length < 3) return;
        const pathStr = parts[0];
        const listKey = parts[1];
        const targetVal = parts.slice(2).join(':');
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        const arr = Array.isArray(node.params[listKey]) ? [...node.params[listKey]] : [];
        const existingIdx = arr.indexOf(targetVal);
        if (existingIdx >= 0) arr.splice(existingIdx, 1);
        else arr.push(targetVal);
        node.params[listKey] = arr;
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-act-notif-btn-add]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const node = this._resolveActionNode(btn.dataset.actNotifBtnAdd);
        if (!node) return;
        node.params = node.params || {};
        node.params.actions = Array.isArray(node.params.actions) ? node.params.actions : [];
        node.params.actions.push({ title: 'Azione', action: 'SH3D_ALARM_SPENTO' });
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-act-notif-btn-preset]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const [pathStr, preset] = btn.dataset.actNotifBtnPreset.split(':');
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        node.params.actions = Array.isArray(node.params.actions) ? node.params.actions : [];
        const gateCand = this.studio.haDiscovery?.action_entities?.find((e) =>
          String(e.entity_id).includes('cancelletto') || String(e.entity_id).includes('gate')
        )?.entity_id;
        const presetMap = {
          gate: { title: 'Apri cancelletto', action: `SH3D_CALL_SERVICE:switch.turn_on:${gateCand || 'switch.cancelletto'}` },
          alarm_off: { title: 'Allarme Spento', action: 'SH3D_ALARM_SPENTO' },
          alarm_silent: { title: 'Modalità Silenziosa', action: 'SH3D_ALARM_SILENZIOSO' },
        };
        if (presetMap[preset]) {
          node.params.actions.push(presetMap[preset]);
          this.studio.renderBodyPreservingScroll();
        }
      });
    });

    body.querySelectorAll('[data-act-notif-btn-del]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const lastColon = btn.dataset.actNotifBtnDel.lastIndexOf(':');
        const pathStr = btn.dataset.actNotifBtnDel.slice(0, lastColon);
        const idx = parseInt(btn.dataset.actNotifBtnDel.slice(lastColon + 1), 10);
        const node = this._resolveActionNode(pathStr);
        if (!node || !Array.isArray(node.params?.actions) || !Number.isFinite(idx)) return;
        node.params.actions.splice(idx, 1);
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-act-notif-btn-field]').forEach((inp) => {
      const handler = () => {
        const parts = inp.dataset.actNotifBtnField.split(':');
        if (parts.length < 3) return;
        const pathStr = parts[0];
        const idx = parseInt(parts[1], 10);
        const field = parts[2];
        const node = this._resolveActionNode(pathStr);
        if (!node || !Array.isArray(node.params?.actions) || !node.params.actions[idx]) return;
        node.params.actions[idx][field] = inp.value;
        this.studio._updateDirtyIndicator();
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });
  }
}
