/**
 * ZonesEntitiesLogsViews.js
 *
 * Views & event binders for:
 * - Tab 1: Regole list
 * - Tab 2: Aree 3D list & Zone editor (with y_min=0 fix & <details> elevation)
 * - Tab 3: Entità list-first (.m3-switch, segmented select) & Entity editor
 * - Tab 4: Attività / Log with status filter pills & 2-step clear
 */

import { icon } from '../../ui/icons.js';
import {
  DEFAULT_SELECT_OPTIONS_TEXT,
  TRIGGER_TYPE_LABELS,
  buildRuleSummaryItalian,
  escapeHtml,
  roundClean,
} from './RuleDraftModel.js';

export class ZonesEntitiesLogsViews {
  constructor(studio) {
    this.studio = studio;
    this.confirmDeleteKey = null; // e.g. 'rule:<id>' | 'zone:<id>' | 've:<id>' | 'logs:clear'
    this.logFilter = 'all'; // 'all' | 'executed' | 'condition_blocked' | 'error'
  }

  _detailsAttrs(detailsId) {
    const isOpen = this.studio._openDetailsIds?.has(detailsId);
    return `data-details-id="${escapeHtml(detailsId)}" ${isOpen ? 'open' : ''}`;
  }

  // =========================================================================
  // TAB 1: RULES LIST
  // =========================================================================

  renderRulesList() {
    const rules = this.studio.rules || [];
    const zones = this.studio.zones || [];
    const armedStates = this.studio.armedStates || [];

    const rowsHtml =
      rules.length === 0
        ? `<div class="sh3d-empty-state">
             <span class="sh3d-empty-icon">${icon('zap', { size: 18 })}</span>
             <div class="sh3d-empty-title">Nessuna regola configurata</div>
             <div class="sh3d-empty-hint">Crea una regola guidata scegliendo un evento 3D, eventuali condizioni e le azioni da eseguire.</div>
           </div>`
        : rules
            .map((r) => {
              const lastStr = r.last_triggered_at
                ? new Date(r.last_triggered_at * 1000).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
                : 'Mai';
              const armedForRule = armedStates.filter((a) => a.rule_id === r.rule_id);
              const armedHtml = armedForRule.length
                ? `<div class="auto-armed-pill" title="${escapeHtml(armedForRule[0].summary || '')}">
                     ${icon('zap', { size: 11 })}
                     <span>Pre-trigger: ${escapeHtml(armedForRule[0].stage_name || 'Attivo')} · ${Number(armedForRule[0].remaining_s ?? 0).toFixed(0)}s</span>
                   </div>`
                : '';
              const summaryText = r.description?.trim()
                ? r.description
                : buildRuleSummaryItalian(r, { zones });
              const delKey = `rule:${r.rule_id}`;
              const isConfirmDel = this.confirmDeleteKey === delKey;

              return `
                <div class="auto-list-item ${r.enabled ? '' : 'is-disabled'}" data-rule-card="${escapeHtml(r.rule_id)}">
                  <div class="auto-item-main">
                    <div class="auto-item-info">
                      <div class="auto-item-title-row">
                        <span class="auto-status-dot ${r.enabled ? 'on' : 'off'}"></span>
                        <h4 class="auto-item-title">${escapeHtml(r.name || 'Regola senza nome')}</h4>
                      </div>
                      <p class="auto-item-sub">${escapeHtml(summaryText)}</p>
                      ${armedHtml}
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked="${r.enabled ? 'true' : 'false'}"
                      aria-label="${r.enabled ? 'Disattiva' : 'Attiva'} ${escapeHtml(r.name || 'regola')}"
                      class="m3-switch ${r.enabled ? 'checked' : ''}"
                      data-rule-toggle="${escapeHtml(r.rule_id)}"
                      data-next-enabled="${r.enabled ? 'false' : 'true'}"
                    >
                      <span class="m3-switch-thumb"></span>
                    </button>
                  </div>
                  <div class="auto-item-footer">
                    <span class="auto-item-stat">${r.trigger_count || 0} esecuzioni · Ultima: ${escapeHtml(lastStr)}</span>
                    <div class="auto-item-actions">
                      <button type="button" class="auto-btn ghost xs" data-run-rule="${escapeHtml(r.rule_id)}" title="Esegui subito le azioni">
                        ${icon('play', { size: 12 })} <span>Test</span>
                      </button>
                      <button type="button" class="auto-btn tonal xs" data-edit-rule="${escapeHtml(r.rule_id)}">
                        <span>Modifica</span>
                      </button>
                      ${
                        isConfirmDel
                          ? `<button type="button" class="auto-btn danger xs" data-del-rule-confirm="${escapeHtml(r.rule_id)}">Conferma</button>
                             <button type="button" class="auto-btn ghost xs" data-del-cancel="1">Annulla</button>`
                          : `<button type="button" class="auto-btn icon-only danger xs" data-del-rule="${escapeHtml(r.rule_id)}" title="Elimina regola" aria-label="Elimina regola">
                               ${icon('trash-2', { size: 13 })}
                             </button>`
                      }
                    </div>
                  </div>
                </div>
              `;
            })
            .join('');

    return `
      <div class="auto-toolbar-row">
        <button type="button" class="auto-btn primary full" id="btn-auto-new-rule">
          ${icon('plus', { size: 15 })}
          <span>Nuova regola</span>
        </button>
      </div>
      <div class="auto-list">
        ${rowsHtml}
      </div>
    `;
  }

  bindRulesListEvents() {
    const body = this.studio.bodyEl;
    if (!body) return;

    body.querySelector('#btn-auto-new-rule')?.addEventListener('click', () => {
      this.confirmDeleteKey = null;
      this.studio.startNewRule();
    });

    body.querySelectorAll('[data-rule-toggle]').forEach((sw) => {
      sw.addEventListener('click', async () => {
        const ruleId = sw.dataset.ruleToggle;
        const nextEnabled = sw.dataset.nextEnabled === 'true';
        await this.studio.spatialStreamClient?.toggleAutomationRule?.(ruleId, nextEnabled);
        await this.studio.refreshBootstrapData();
      });
    });

    body.querySelectorAll('[data-run-rule]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const ruleId = btn.dataset.runRule;
        const res = await this.studio.spatialStreamClient?.triggerAutomationRule?.(ruleId);
        if (res?.status === 'ok') {
          this.studio.setStatus('Azioni eseguite.', 'success');
          await this.studio.refreshBootstrapData();
        } else {
          this.studio.setStatus('Errore durante il test della regola.', 'error');
        }
      });
    });

    body.querySelectorAll('[data-edit-rule]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.confirmDeleteKey = null;
        this.studio.startEditRule(btn.dataset.editRule);
      });
    });

    body.querySelectorAll('[data-del-rule]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.confirmDeleteKey = `rule:${btn.dataset.delRule}`;
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-del-rule-confirm]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const ruleId = btn.dataset.delRuleConfirm;
        this.confirmDeleteKey = null;
        await this.studio.spatialStreamClient?.deleteAutomationRule?.(ruleId);
        this.studio.setStatus('Regola eliminata.', 'info');
        await this.studio.refreshBootstrapData();
      });
    });

    body.querySelectorAll('[data-del-cancel]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.confirmDeleteKey = null;
        this.studio.renderBodyPreservingScroll();
      });
    });
  }

  // =========================================================================
  // TAB 2: 2.5D POLYGONAL ZONES & ORIENTED PERIMETERS
  // =========================================================================

  renderZonesList() {
    const zones = this.studio.zones || [];
    const itemsHtml =
      zones.length === 0
        ? `<div class="sh3d-empty-state">
             <span class="sh3d-empty-icon">${icon('pentagon', { size: 18 })}</span>
             <div class="sh3d-empty-title">Nessun’area o perimetro salvato</div>
             <div class="sh3d-empty-hint">Avvia il disegno e tocca il pavimento nella scena 3D per posizionare i vertici.</div>
           </div>`
        : zones
            .map((z) => {
              const isPerim = z.geometry_type === 'perimeter';
              const vCount = Array.isArray(z.vertices) ? z.vertices.length : 0;
              const delKey = `zone:${z.zone_id}`;
              const isConfirmDel = this.confirmDeleteKey === delKey;

              return `
                <div class="auto-list-item" data-zone-card="${escapeHtml(z.zone_id)}">
                  <div class="auto-item-main">
                    <div class="auto-item-info">
                      <div class="auto-item-title-row">
                        <span class="auto-color-dot" style="background:${escapeHtml(z.color || '#38bdf8')}"></span>
                        <h4 class="auto-item-title">${escapeHtml(z.name)}</h4>
                      </div>
                      <p class="auto-item-sub">
                        ${isPerim ? 'Perimetro orientato' : 'Area poligonale'} · ${vCount} ${vCount === 1 ? 'vertice' : 'vertici'}
                      </p>
                    </div>
                  </div>
                  <div class="auto-item-footer">
                    <span class="auto-item-stat">${isPerim ? 'Linea 3D' : 'Zona 3D'}</span>
                    <div class="auto-item-actions">
                      <button type="button" class="auto-btn ghost xs" data-focus-zone="${escapeHtml(z.zone_id)}">
                        <span>Evidenzia</span>
                      </button>
                      <button type="button" class="auto-btn tonal xs" data-edit-zone="${escapeHtml(z.zone_id)}">
                        <span>Modifica</span>
                      </button>
                      ${
                        isConfirmDel
                          ? `<button type="button" class="auto-btn danger xs" data-del-zone-confirm="${escapeHtml(z.zone_id)}">Conferma</button>
                             <button type="button" class="auto-btn ghost xs" data-del-cancel="1">Annulla</button>`
                          : `<button type="button" class="auto-btn icon-only danger xs" data-del-zone="${escapeHtml(z.zone_id)}" title="Elimina" aria-label="Elimina area">
                               ${icon('trash-2', { size: 13 })}
                             </button>`
                      }
                    </div>
                  </div>
                </div>
              `;
            })
            .join('');

    return `
      <div class="auto-toolbar-grid">
        <button type="button" class="auto-btn primary" id="btn-auto-new-polygon">
          ${icon('plus', { size: 14 })} <span>Nuova area 3D</span>
        </button>
        <button type="button" class="auto-btn tonal" id="btn-auto-new-perimeter">
          ${icon('plus', { size: 14 })} <span>Nuovo perimetro</span>
        </button>
      </div>
      <div class="auto-list">
        ${itemsHtml}
      </div>
    `;
  }

  bindZonesListEvents() {
    const body = this.studio.bodyEl;
    if (!body) return;

    body.querySelector('#btn-auto-new-polygon')?.addEventListener('click', () => {
      this.confirmDeleteKey = null;
      this.studio.startNewZoneDraft('polygon');
    });
    body.querySelector('#btn-auto-new-perimeter')?.addEventListener('click', () => {
      this.confirmDeleteKey = null;
      this.studio.startNewZoneDraft('perimeter');
    });

    body.querySelectorAll('[data-focus-zone]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const zid = btn.dataset.focusZone;
        this.studio.zoneRenderer?.flashZoneAlert(zid, 'warning', 3500);
      });
    });

    body.querySelectorAll('[data-edit-zone]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.confirmDeleteKey = null;
        this.studio.startEditZone(btn.dataset.editZone);
      });
    });

    body.querySelectorAll('[data-del-zone]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.confirmDeleteKey = `zone:${btn.dataset.delZone}`;
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-del-zone-confirm]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const zid = btn.dataset.delZoneConfirm;
        this.confirmDeleteKey = null;
        await this.studio.spatialStreamClient?.deleteAutomationZone?.(zid);
        this.studio.setStatus('Geometria eliminata.', 'info');
        await this.studio.refreshBootstrapData();
      });
    });

    body.querySelectorAll('[data-del-cancel]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.confirmDeleteKey = null;
        this.studio.renderBodyPreservingScroll();
      });
    });
  }

  renderZoneEditor() {
    const z = this.studio.editingZone;
    if (!z) return '';
    const isPerim = z.geometry_type === 'perimeter';
    const minVerts = isPerim ? 2 : 3;

    return `
      <div class="auto-editor" data-editor-kind="zone">
        <div class="auto-editor-topbar">
          <button type="button" class="auto-btn ghost xs" id="btn-zone-back">
            ${icon('arrow-left', { size: 13 })} <span>${this.studio.pendingZoneReturn ? 'Torna alla regola' : 'Tutte le aree'}</span>
          </button>
          <span class="auto-editor-mode-label">${this.studio.isEditingNewZone ? (isPerim ? 'Nuovo perimetro' : 'Nuova area 3D') : 'Modifica geometria'}</span>
        </div>

        <div class="auto-draw-callout">
          <div class="auto-draw-callout-head">
            ${icon('crosshair', { size: 15 })}
            <span>Tocca il terreno nella scena 3D per posizionare i vertici</span>
          </div>
          <div class="auto-draw-callout-meta">
            <strong id="zone-vertices-count">${z.vertices.length} vertici posizionati</strong> (minimo ${minVerts})
          </div>
          <div class="auto-draw-callout-actions">
            <button type="button" class="auto-btn primary xs" id="btn-zone-collapse-to-draw">
              ${icon('chevron-down', { size: 12 })} <span>Riduci per disegnare nel 3D</span>
            </button>
            <button type="button" class="auto-btn tonal xs" id="btn-zone-undo-vertex">
              ${icon('rotate-ccw', { size: 12 })} <span>Annulla punto</span>
            </button>
            <button type="button" class="auto-btn ghost xs" id="btn-zone-clear-vertices">
              <span>Svuota</span>
            </button>
            ${
              isPerim
                ? `<button type="button" class="auto-btn tonal xs" id="btn-zone-flip-normal">
                     ${icon('refresh-cw', { size: 12 })} <span>Inverti freccia A↔B</span>
                   </button>`
                : ''
            }
          </div>
        </div>

        <section class="auto-step">
          <div class="auto-grid-2">
            <label class="auto-field span-2" for="zone-inp-name">
              <span>Nome</span>
              <input type="text" id="zone-inp-name" name="zone_name" value="${escapeHtml(z.name)}" placeholder="Es. Giardino nord" />
            </label>
            <label class="auto-field" for="zone-inp-gtype">
              <span>Geometria</span>
              <select id="zone-inp-gtype" name="zone_geometry_type">
                <option value="polygon" ${!isPerim ? 'selected' : ''}>Area poligonale</option>
                <option value="perimeter" ${isPerim ? 'selected' : ''}>Perimetro / linea</option>
              </select>
            </label>
            <label class="auto-field" for="zone-inp-color">
              <span>Colore 3D</span>
              <input type="color" id="zone-inp-color" name="zone_color" value="${escapeHtml(z.color || '#38bdf8')}" />
            </label>
          </div>
        </section>

        <details class="auto-advanced-details" ${this._detailsAttrs('zone-advanced')}>
          <summary class="auto-details-summary">
            <span>Quota Y e isteresi 3D</span>
            ${icon('chevron-down', { size: 14, className: 'auto-details-chevron' })}
          </summary>
          <div class="auto-details-body">
            <div class="auto-grid-2">
              <label class="auto-field" for="zone-inp-ymin">
                <span>Quota Y min (m)</span>
                <input type="number" step="0.2" id="zone-inp-ymin" name="zone_y_min" value="${Number.isFinite(Number(z.y_min)) ? Number(z.y_min) : -1.5}" />
              </label>
              <label class="auto-field" for="zone-inp-ymax">
                <span>Quota Y max (m)</span>
                <input type="number" step="0.2" id="zone-inp-ymax" name="zone_y_max" value="${Number.isFinite(Number(z.y_max)) ? Number(z.y_max) : 4.0}" />
              </label>
              <label class="auto-field span-2" for="zone-inp-hysteresis">
                <span>Isteresi bordo (m)</span>
                <input type="number" min="0" max="2" step="0.02" id="zone-inp-hysteresis" name="zone_hysteresis_m" value="${roundClean(z.hysteresis_m ?? 0.12, 2)}" />
              </label>
            </div>
          </div>
        </details>
      </div>
    `;
  }

  bindZoneEditorEvents() {
    const body = this.studio.bodyEl;
    const z = this.studio.editingZone;
    if (!body || !z) return;

    body.querySelectorAll('details[data-details-id]').forEach((det) => {
      det.addEventListener('toggle', () => {
        const id = det.dataset.detailsId;
        if (det.open) this.studio._openDetailsIds.add(id);
        else this.studio._openDetailsIds.delete(id);
      });
    });

    body.querySelector('#btn-zone-back')?.addEventListener('click', () => {
      this.studio._requestExitEditor();
    });

    body.querySelector('#zone-inp-name')?.addEventListener('input', (e) => {
      z.name = e.target.value;
      this.studio._updateHeaderChrome();
      this.studio._updateDirtyIndicator();
    });

    body.querySelector('#zone-inp-gtype')?.addEventListener('change', (e) => {
      z.geometry_type = e.target.value;
      this.studio._activate3DZoneDrawing();
      this.studio.renderBodyPreservingScroll();
    });

    body.querySelector('#zone-inp-color')?.addEventListener('input', (e) => {
      z.color = e.target.value;
      if (this.studio.zoneRenderer) {
        this.studio.zoneRenderer.draftColor = z.color;
        this.studio.zoneRenderer.rebuildDraftVisual?.();
      }
      this.studio._updateDirtyIndicator();
    });

    body.querySelector('#zone-inp-ymin')?.addEventListener('input', (e) => {
      const parsed = parseFloat(e.target.value);
      z.y_min = Number.isFinite(parsed) ? parsed : -2.0;
      this.studio._updateDirtyIndicator();
    });

    body.querySelector('#zone-inp-ymax')?.addEventListener('input', (e) => {
      const parsed = parseFloat(e.target.value);
      z.y_max = Number.isFinite(parsed) ? parsed : 4.5;
      this.studio._updateDirtyIndicator();
    });

    body.querySelector('#zone-inp-hysteresis')?.addEventListener('input', (e) => {
      const parsed = parseFloat(e.target.value);
      z.hysteresis_m = Number.isFinite(parsed) ? Math.max(0, roundClean(parsed, 2)) : 0.12;
      this.studio._updateDirtyIndicator();
    });

    body.querySelector('#btn-zone-collapse-to-draw')?.addEventListener('click', () => {
      this.studio.setCollapsed(true);
    });
    body.querySelector('#btn-zone-undo-vertex')?.addEventListener('click', () => {
      this.studio.zoneRenderer?.undoLastDraftVertex?.();
    });
    body.querySelector('#btn-zone-clear-vertices')?.addEventListener('click', () => {
      this.studio.zoneRenderer?.clearDraftVertices?.();
    });
    body.querySelector('#btn-zone-flip-normal')?.addEventListener('click', () => {
      z.normal_flipped = !z.normal_flipped;
      if (this.studio.zoneRenderer) {
        this.studio.zoneRenderer.draftNormalFlipped = z.normal_flipped;
        this.studio.zoneRenderer.rebuildDraftVisual?.();
      }
      this.studio._updateDirtyIndicator();
    });
  }

  // =========================================================================
  // TAB 3: VIRTUAL ENTITIES (List-first + Entity Editor)
  // =========================================================================

  parseOptionsText(raw) {
    const seen = new Set();
    const out = [];
    for (const part of String(raw || '').split(',')) {
      const clean = part.trim();
      if (clean && !seen.has(clean)) {
        seen.add(clean);
        out.push(clean);
      }
    }
    return out;
  }

  renderEntitiesList() {
    const entities = this.studio.virtualEntities || [];
    const rowsHtml =
      entities.length === 0
        ? `<div class="sh3d-empty-state">
             <span class="sh3d-empty-icon">${icon('sliders-horizontal', { size: 18 })}</span>
             <div class="sh3d-empty-title">Nessuna entità interna configurata</div>
             <div class="sh3d-empty-hint">Crea interruttori o selettori di stato (es. modalità allarme) da usare nelle regole.</div>
           </div>`
        : entities
            .map((ve) => {
              const isSwitch = ve.domain === 'switch' || ve.domain === 'boolean';
              const isSelect = ve.domain === 'select' && Array.isArray(ve.options) && ve.options.length > 0;
              const isOn = String(ve.state).toLowerCase() === 'on';
              const delKey = `ve:${ve.entity_id}`;
              const isConfirmDel = this.confirmDeleteKey === delKey;

              let controlHtml = '';
              if (isSwitch) {
                controlHtml = `
                  <button
                    type="button"
                    role="switch"
                    aria-checked="${isOn ? 'true' : 'false'}"
                    aria-label="${escapeHtml(ve.name)}"
                    class="m3-switch ${isOn ? 'checked' : ''}"
                    data-ve-toggle="${escapeHtml(ve.entity_id)}"
                  >
                    <span class="m3-switch-thumb"></span>
                  </button>
                `;
              } else if (isSelect && ve.options.length <= 4) {
                controlHtml = `
                  <div class="auto-seg-options" role="group" aria-label="${escapeHtml(ve.name)}">
                    ${ve.options
                      .map(
                        (opt) =>
                          `<button type="button" class="auto-seg-opt ${ve.state === opt ? 'active' : ''}" data-ve-select-opt="${escapeHtml(ve.entity_id)}:${escapeHtml(opt)}">${escapeHtml(opt)}</button>`
                      )
                      .join('')}
                  </div>
                `;
              } else if (isSelect) {
                const selId = `ve-sel-${escapeHtml(ve.entity_id).replace(/[^a-zA-Z0-9_-]/g, '_')}`;
                controlHtml = `
                  <select class="auto-ve-inline-select" id="${selId}" name="${selId}" data-ve-select="${escapeHtml(ve.entity_id)}" aria-label="${escapeHtml(ve.name)}">
                    ${ve.options.map((opt) => `<option value="${escapeHtml(opt)}" ${ve.state === opt ? 'selected' : ''}>${escapeHtml(opt)}</option>`).join('')}
                  </select>
                `;
              } else {
                const inpId = `ve-val-${escapeHtml(ve.entity_id).replace(/[^a-zA-Z0-9_-]/g, '_')}`;
                controlHtml = `
                  <div class="auto-input-with-btn">
                    <input type="text" class="auto-ve-inline-input" id="${inpId}" name="${inpId}" data-ve-val-inp="${escapeHtml(ve.entity_id)}" value="${escapeHtml(ve.state)}" aria-label="${escapeHtml(ve.name)}" />
                    <button type="button" class="auto-btn tonal xs" data-ve-set-btn="${escapeHtml(ve.entity_id)}">OK</button>
                  </div>
                `;
              }

              return `
                <div class="auto-list-item" data-entity-card="${escapeHtml(ve.entity_id)}">
                  <div class="auto-item-main">
                    <div class="auto-item-info">
                      <div class="auto-item-title-row">
                        <span class="auto-status-dot ${isOn || (isSelect && ve.state !== 'Spento') ? 'on' : 'off'}"></span>
                        <h4 class="auto-item-title">${escapeHtml(ve.name)}</h4>
                      </div>
                      <code class="auto-entity-code">${escapeHtml(ve.entity_id)}</code>
                    </div>
                    <div class="auto-item-actions">
                      ${isSwitch ? controlHtml : ''}
                    </div>
                  </div>
                  ${!isSwitch ? `<div class="auto-entity-control-row">${controlHtml}</div>` : ''}
                  <div class="auto-item-footer">
                    <span class="auto-item-stat">${escapeHtml(ve.domain === 'select' ? 'Selettore' : ve.domain === 'number' ? 'Numero' : ve.domain === 'sensor' ? 'Testo' : 'Interruttore')}</span>
                    <div class="auto-item-actions">
                      <button type="button" class="auto-btn tonal xs" data-ve-edit="${escapeHtml(ve.entity_id)}">
                        <span>Modifica</span>
                      </button>
                      ${
                        isConfirmDel
                          ? `<button type="button" class="auto-btn danger xs" data-ve-del-confirm="${escapeHtml(ve.entity_id)}">Conferma</button>
                             <button type="button" class="auto-btn ghost xs" data-del-cancel="1">Annulla</button>`
                          : `<button type="button" class="auto-btn icon-only danger xs" data-ve-del="${escapeHtml(ve.entity_id)}" title="Elimina entità" aria-label="Elimina entità">
                               ${icon('trash-2', { size: 13 })}
                             </button>`
                      }
                    </div>
                  </div>
                </div>
              `;
            })
            .join('');

    return `
      <div class="auto-toolbar-row">
        <button type="button" class="auto-btn primary full" id="btn-auto-new-entity">
          ${icon('plus', { size: 15 })}
          <span>Nuova entità</span>
        </button>
      </div>
      <div class="auto-list">
        ${rowsHtml}
      </div>
    `;
  }

  bindEntitiesListEvents() {
    const body = this.studio.bodyEl;
    if (!body) return;

    body.querySelector('#btn-auto-new-entity')?.addEventListener('click', () => {
      this.confirmDeleteKey = null;
      this.studio.startNewEntity();
    });

    body.querySelectorAll('[data-ve-edit]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.confirmDeleteKey = null;
        this.studio.startEditEntity(btn.dataset.veEdit);
      });
    });

    body.querySelectorAll('[data-ve-toggle]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const eid = btn.dataset.veToggle;
        await this.studio.spatialStreamClient?.setVirtualEntityState?.(eid, { operation: 'toggle' });
        await this.studio.refreshBootstrapData();
      });
    });

    body.querySelectorAll('[data-ve-select-opt]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const firstColon = btn.dataset.veSelectOpt.indexOf(':');
        const eid = btn.dataset.veSelectOpt.slice(0, firstColon);
        const optVal = btn.dataset.veSelectOpt.slice(firstColon + 1);
        await this.studio.spatialStreamClient?.setVirtualEntityState?.(eid, { state: optVal, operation: 'set' });
        await this.studio.refreshBootstrapData();
      });
    });

    body.querySelectorAll('[data-ve-select]').forEach((sel) => {
      sel.addEventListener('change', async () => {
        const eid = sel.dataset.veSelect;
        await this.studio.spatialStreamClient?.setVirtualEntityState?.(eid, { state: sel.value, operation: 'set' });
        await this.studio.refreshBootstrapData();
      });
    });

    body.querySelectorAll('[data-ve-set-btn]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const eid = btn.dataset.veSetBtn;
        const inp = body.querySelector(`[data-ve-val-inp="${eid}"]`);
        if (!inp) return;
        await this.studio.spatialStreamClient?.setVirtualEntityState?.(eid, { state: inp.value, operation: 'set' });
        await this.studio.refreshBootstrapData();
      });
    });

    body.querySelectorAll('[data-ve-del]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.confirmDeleteKey = `ve:${btn.dataset.veDel}`;
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelectorAll('[data-ve-del-confirm]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const eid = btn.dataset.veDelConfirm;
        this.confirmDeleteKey = null;
        await this.studio.spatialStreamClient?.deleteVirtualEntity?.(eid);
        this.studio.setStatus(`Entità ${eid} eliminata.`, 'info');
        await this.studio.refreshBootstrapData();
      });
    });

    body.querySelectorAll('[data-del-cancel]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.confirmDeleteKey = null;
        this.studio.renderBodyPreservingScroll();
      });
    });
  }

  renderEntityEditor() {
    const draft = this.studio.editingEntity;
    if (!draft) return '';
    const draftDomain = draft.domain || 'switch';
    const parsedOptions = this.parseOptionsText(draft.optionsText);
    const effectiveOptions = parsedOptions.length > 0 ? parsedOptions : ['Spento', 'Acceso'];
    const selectedInitialState =
      draftDomain === 'select'
        ? (effectiveOptions.includes(draft.state) ? draft.state : effectiveOptions[0])
        : draftDomain === 'switch'
          ? (String(draft.state).toLowerCase() === 'on' ? 'on' : 'off')
          : (draft.state ?? '');

    let initialStateControlHtml = '';
    if (draftDomain === 'switch') {
      initialStateControlHtml = `
        <select id="ve-inp-state" name="ve_state">
          <option value="off" ${selectedInitialState === 'off' ? 'selected' : ''}>Spento (off)</option>
          <option value="on" ${selectedInitialState === 'on' ? 'selected' : ''}>Acceso (on)</option>
        </select>
      `;
    } else if (draftDomain === 'select') {
      initialStateControlHtml = `
        <select id="ve-inp-state" name="ve_state">
          ${effectiveOptions.map((opt) => `<option value="${escapeHtml(opt)}" ${selectedInitialState === opt ? 'selected' : ''}>${escapeHtml(opt)}</option>`).join('')}
        </select>
      `;
    } else if (draftDomain === 'number') {
      initialStateControlHtml = `<input type="number" step="any" id="ve-inp-state" name="ve_state" value="${escapeHtml(selectedInitialState || '0')}" />`;
    } else {
      initialStateControlHtml = `<input type="text" id="ve-inp-state" name="ve_state" value="${escapeHtml(selectedInitialState)}" placeholder="Valore iniziale" />`;
    }

    return `
      <div class="auto-editor" data-editor-kind="entity">
        <div class="auto-editor-topbar">
          <button type="button" class="auto-btn ghost xs" id="btn-ve-back">
            ${icon('arrow-left', { size: 13 })} <span>Tutte le entità</span>
          </button>
          <span class="auto-editor-mode-label">${this.studio.isEditingNewEntity ? 'Nuova entità' : 'Modifica entità'}</span>
        </div>

        <section class="auto-step">
          <div class="auto-grid-2">
            <label class="auto-field span-2" for="ve-inp-name">
              <span>Nome visualizzato</span>
              <input type="text" id="ve-inp-name" name="ve_name" value="${escapeHtml(draft.name)}" placeholder="Es. Modalità Notte" />
            </label>
            <label class="auto-field span-2" for="ve-inp-id">
              <span>ID entità (<code>sh3d.*</code>)</span>
              <input type="text" id="ve-inp-id" name="ve_entity_id" value="${escapeHtml(draft.entity_id)}" placeholder="sh3d.modalita_notte" ${!this.studio.isEditingNewEntity ? 'readonly' : ''} />
            </label>
            <label class="auto-field" for="ve-inp-domain">
              <span>Tipo</span>
              <select id="ve-inp-domain" name="ve_domain">
                <option value="switch" ${draftDomain === 'switch' ? 'selected' : ''}>Interruttore ON/OFF</option>
                <option value="select" ${draftDomain === 'select' ? 'selected' : ''}>Selettore modalità</option>
                <option value="number" ${draftDomain === 'number' ? 'selected' : ''}>Valore numerico</option>
                <option value="sensor" ${draftDomain === 'sensor' ? 'selected' : ''}>Testo / stato</option>
              </select>
            </label>
            <label class="auto-field" for="ve-inp-state">
              <span>Stato</span>
              ${initialStateControlHtml}
            </label>
            ${
              draftDomain === 'select'
                ? `<label class="auto-field span-2" for="ve-inp-options">
                     <span>Stati possibili (separati da virgola)</span>
                     <input type="text" id="ve-inp-options" name="ve_options" value="${escapeHtml(draft.optionsText || DEFAULT_SELECT_OPTIONS_TEXT)}" placeholder="es. Spento, Silenzioso, Acceso" />
                   </label>`
                : ''
            }
          </div>
        </section>
      </div>
    `;
  }

  bindEntityEditorEvents() {
    const body = this.studio.bodyEl;
    const draft = this.studio.editingEntity;
    if (!body || !draft) return;

    body.querySelector('#btn-ve-back')?.addEventListener('click', () => {
      this.studio._requestExitEditor();
    });

    body.querySelector('#ve-inp-id')?.addEventListener('input', (e) => {
      draft.entity_id = e.target.value;
      this.studio._updateDirtyIndicator();
    });
    body.querySelector('#ve-inp-name')?.addEventListener('input', (e) => {
      draft.name = e.target.value;
      if (this.studio.isEditingNewEntity && !this.studio._entityIdManuallyEdited) {
        const slug = String(e.target.value || '')
          .toLowerCase()
          .normalize('NFD')
          .replace(/[\u0300-\u036f]/g, '')
          .replace(/[^a-z0-9]+/g, '_')
          .replace(/^_+|_+$/g, '');
        draft.entity_id = slug ? `sh3d.${slug}` : '';
        const idEl = body.querySelector('#ve-inp-id');
        if (idEl) idEl.value = draft.entity_id;
      }
      this.studio._updateDirtyIndicator();
    });
    body.querySelector('#ve-inp-id')?.addEventListener('keydown', () => {
      this.studio._entityIdManuallyEdited = true;
    });

    const stateInp = body.querySelector('#ve-inp-state');
    stateInp?.addEventListener('input', (e) => {
      draft.state = e.target.value;
      this.studio._updateDirtyIndicator();
    });
    stateInp?.addEventListener('change', (e) => {
      draft.state = e.target.value;
      this.studio._updateDirtyIndicator();
    });

    body.querySelector('#ve-inp-domain')?.addEventListener('change', (e) => {
      const nextDomain = e.target.value;
      draft.domain = nextDomain;
      if (nextDomain === 'switch') {
        draft.state = 'off';
      } else if (nextDomain === 'select') {
        const opts = this.parseOptionsText(draft.optionsText);
        if (opts.length === 0) {
          draft.optionsText = DEFAULT_SELECT_OPTIONS_TEXT;
          draft.state = 'Spento';
        } else if (!opts.includes(draft.state)) {
          draft.state = opts[0];
        }
      } else if (nextDomain === 'number') {
        draft.state = Number.isFinite(Number(draft.state)) && draft.state !== '' ? draft.state : '0';
      }
      this.studio.renderBodyPreservingScroll();
    });

    body.querySelector('#ve-inp-options')?.addEventListener('input', (e) => {
      draft.optionsText = e.target.value;
      const opts = this.parseOptionsText(draft.optionsText);
      const stateSelectEl = body.querySelector('#ve-inp-state');
      if (stateSelectEl && stateSelectEl.tagName === 'SELECT') {
        const effective = opts.length > 0 ? opts : ['Spento', 'Acceso'];
        if (!effective.includes(draft.state)) {
          draft.state = effective[0];
        }
        stateSelectEl.innerHTML = effective
          .map((opt) => `<option value="${escapeHtml(opt)}" ${draft.state === opt ? 'selected' : ''}>${escapeHtml(opt)}</option>`)
          .join('');
      }
      this.studio._updateDirtyIndicator();
    });
  }

  // =========================================================================
  // TAB 4: ATTIVITÀ / LOGS
  // =========================================================================

  renderLogsTab() {
    const allLogs = this.studio.logs || [];
    const filtered = allLogs.filter((l) => {
      const st = l.status || 'executed';
      if (this.logFilter === 'all') return true;
      return st === this.logFilter;
    });

    const filterPills = [
      { id: 'all', label: 'Tutti' },
      { id: 'executed', label: 'Eseguite' },
      { id: 'condition_blocked', label: 'Bloccate' },
      { id: 'error', label: 'Errori' },
    ];

    const isConfirmClear = this.confirmDeleteKey === 'logs:clear';

    const itemsHtml =
      filtered.length === 0
        ? `<div class="sh3d-empty-state">
             <span class="sh3d-empty-icon">${icon('activity', { size: 18 })}</span>
             <div class="sh3d-empty-title">${allLogs.length === 0 ? 'Nessuna attività registrata' : 'Nessun evento per questo filtro'}</div>
             <div class="sh3d-empty-hint">${allLogs.length === 0 ? 'Le esecuzioni delle regole appariranno qui in tempo reale.' : 'Prova a selezionare "Tutti" per vedere l’intero registro.'}</div>
           </div>`
        : filtered
            .map((l) => {
              const dtStr = new Date((l.timestamp || 0) * 1000).toLocaleTimeString('it-IT');
              const actionsCount = Array.isArray(l.actions_executed) ? l.actions_executed.length : 0;
              const statusKey = l.status || 'executed';
              const statusLabel = statusKey === 'condition_blocked' ? 'Bloccata' : statusKey === 'error' ? 'Errore' : 'Eseguita';
              const triggerLabel = TRIGGER_TYPE_LABELS[l.trigger_type] || l.trigger_type || 'Evento';
              const preSum = l.details?.pre_trigger_summary ? ` · Pre: ${l.details.pre_trigger_summary}` : '';

              return `
                <div class="auto-list-item">
                  <div class="auto-item-main">
                    <div class="auto-item-info">
                      <div class="auto-item-title-row">
                        <span class="auto-log-status-pill is-${escapeHtml(statusKey)}">${statusLabel}</span>
                        <h4 class="auto-item-title">${escapeHtml(l.rule_name || 'Regola')}</h4>
                      </div>
                      <p class="auto-item-sub">${escapeHtml(l.trigger_summary || '')}</p>
                    </div>
                    <span class="auto-item-time">${escapeHtml(dtStr)}</span>
                  </div>
                  <div class="auto-item-footer">
                    <span class="auto-item-stat">${escapeHtml(triggerLabel)} · ${actionsCount} ${actionsCount === 1 ? 'azione' : 'azioni'}${l.identity ? ` · ${escapeHtml(l.identity)}` : ''}${l.plate ? ` · ${escapeHtml(l.plate)}` : ''}${escapeHtml(preSum)}</span>
                  </div>
                </div>
              `;
            })
            .join('');

    return `
      <div class="auto-logs-toolbar">
        <div class="auto-chips-wrap" role="group" aria-label="Filtra attività">
          ${filterPills
            .map(
              (fp) =>
                `<button type="button" class="auto-chip ${this.logFilter === fp.id ? 'active' : ''}" data-log-filter="${fp.id}">${escapeHtml(fp.label)}</button>`
            )
            .join('')}
        </div>
        ${
          allLogs.length > 0
            ? isConfirmClear
              ? `<div class="auto-item-actions">
                   <button type="button" class="auto-btn danger xs" id="btn-auto-clear-logs-confirm">Conferma</button>
                   <button type="button" class="auto-btn ghost xs" data-del-cancel="1">Annulla</button>
                 </div>`
              : `<button type="button" class="auto-btn ghost xs" id="btn-auto-clear-logs">
                   ${icon('trash-2', { size: 12 })} <span>Svuota registro</span>
                 </button>`
            : ''
        }
      </div>
      <div class="auto-list">
        ${itemsHtml}
      </div>
    `;
  }

  bindLogsEvents() {
    const body = this.studio.bodyEl;
    if (!body) return;

    body.querySelectorAll('[data-log-filter]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.logFilter = btn.dataset.logFilter || 'all';
        this.studio.renderBodyPreservingScroll();
      });
    });

    body.querySelector('#btn-auto-clear-logs')?.addEventListener('click', () => {
      this.confirmDeleteKey = 'logs:clear';
      this.studio.renderBodyPreservingScroll();
    });

    body.querySelector('#btn-auto-clear-logs-confirm')?.addEventListener('click', async () => {
      this.confirmDeleteKey = null;
      await this.studio.spatialStreamClient?.clearAutomationLogs?.();
      this.studio.logs = [];
      this.studio.renderBodyPreservingScroll();
    });

    body.querySelectorAll('[data-del-cancel]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.confirmDeleteKey = null;
        this.studio.renderBodyPreservingScroll();
      });
    });
  }
}
