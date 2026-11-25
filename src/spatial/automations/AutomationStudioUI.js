import { icon } from '../../ui/icons.js';

function escapeHtml(val) {
  return String(val ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function uid(prefix = 'id') {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
}

const TRIGGER_TYPE_LABELS = {
  zone_presence: 'Presenza in area 3D',
  perimeter_crossing: 'Attraversamento perimetro',
  zone_transition: 'Passaggio Area A → Area B',
  kinematic_vector: 'Direzione e velocità media',
  time_schedule: 'Orario, alba o tramonto',
  entity_state_change: 'Cambio stato entità',
  biometric_detection: 'Riconoscimento volto / targa',
  proximity_3d: 'Prossimità a punto 3D',
  scene_event: 'Episodio scena (SceneEvent)',
};

const ACTION_TYPE_LABELS = {
  set_virtual_entity: 'Stato entità interna (sh3d.*)',
  call_ha_service: 'Servizio Home Assistant',
  send_notification: 'Notifica dispositivo (Push / TTS / TV)',
  ui_alert: 'Avviso e sirena 3D',
  if_then_else: 'Condizione Se / Altrimenti',
  delay: 'Attesa (secondi)',
  webhook: 'Webhook HTTP',
};

/**
 * AutomationStudioUI
 *
 * Pannello operativo per la configurazione di:
 * - Regole di automazione (Trigger spaziali/cinematici/orari/entità, logica AND/OR/NOT, azioni).
 * - Aree poligonali 2.5D e perimetri orientati disegnabili sul modello 3D (visibili nel 3D solo a pannello aperto).
 * - Entità virtuali interne (`sh3d.*`).
 * - Registro esecuzioni in tempo reale.
 */
export class AutomationStudioUI {
  constructor({
    sceneManager,
    cameraController,
    spatialStreamClient,
    zoneRenderer,
    haClient,
    uiLayer = null,
  }) {
    this.sceneManager = sceneManager;
    this.cameraController = cameraController;
    this.spatialStreamClient = spatialStreamClient;
    this.zoneRenderer = zoneRenderer;
    this.haClient = haClient;
    this.uiLayer = uiLayer || document.body;

    this.isOpen = false;
    this.isCollapsed = false;
    this.activeTab = 'rules'; // 'rules' | 'zones' | 'entities' | 'logs'

    this.zones = [];
    this.virtualEntities = [];
    this.rules = [];
    this.armedStates = [];
    this.logs = [];
    this.identities = [];
    this.plates = [];
    this.cameras = [];
    this.sunInfo = null;
    this.haDiscovery = null;

    this.editingRule = null;
    this.editingZone = null;
    this.newEntityDraft = {
      entity_id: '',
      name: '',
      domain: 'switch',
      state: 'off',
      optionsText: 'Spento, Silenzioso, Acceso',
    };
    this.statusMessage = null;

    this.onOpenCallback = null;
    this.onCloseCallback = null;

    this.zoneRenderer?.setZonesVisible(false);
    this._initDOM();
    this._bindGlobalListeners();
  }

  setLifecycleHooks({ onOpen, onClose } = {}) {
    this.onOpenCallback = typeof onOpen === 'function' ? onOpen : null;
    this.onCloseCallback = typeof onClose === 'function' ? onClose : null;
  }

  _initDOM() {
    this.panelEl = document.createElement('section');
    this.panelEl.id = 'sh3d-automation-studio';
    this.panelEl.className = 'auto-studio-drawer';
    this.panelEl.setAttribute('role', 'dialog');
    this.panelEl.setAttribute('aria-label', 'Automazioni');
    this.panelEl.hidden = true;
    this.uiLayer.appendChild(this.panelEl);

    this.alertBannerEl = document.createElement('div');
    this.alertBannerEl.id = 'sh3d-automation-alert-banner';
    this.alertBannerEl.className = 'auto-live-alert-banner';
    this.alertBannerEl.hidden = true;
    this.uiLayer.appendChild(this.alertBannerEl);
  }

  _bindGlobalListeners() {
    this.spatialStreamClient?.onAutomationEvent?.((msg) => {
      this._handleBackendAutomationMessage(msg);
    });

    this.haClient?.subscribe?.((entitiesMap) => {
      if (this.spatialStreamClient?.connected) {
        this.spatialStreamClient.syncHaStates(entitiesMap, { triggerOnDiff: true });
      }
      if (this.isOpen) {
        this._refreshHaDatalist();
      }
    });

    this.spatialStreamClient?.onStatusChange?.((connected) => {
      if (connected) {
        this.refreshBootstrapData();
        if (this.haClient?.entities && Object.keys(this.haClient.entities).length > 0) {
          this.spatialStreamClient.syncHaStates(this.haClient.entities, { triggerOnDiff: false });
        }
      }
    });
  }

  async refreshBootstrapData() {
    const data = await this.spatialStreamClient?.fetchAutomationsBootstrap?.();
    if (!data || data.status !== 'ok') return;

    this.zones = Array.isArray(data.zones) ? data.zones : [];
    this.virtualEntities = Array.isArray(data.virtual_entities) ? data.virtual_entities : [];
    this.rules = Array.isArray(data.rules) ? data.rules : [];
    this.armedStates = Array.isArray(data.armed_states) ? data.armed_states : [];
    this.logs = Array.isArray(data.logs) ? data.logs : [];
    this.identities = Array.isArray(data.identities) ? data.identities : [];
    this.plates = Array.isArray(data.plates) ? data.plates : [];
    this.cameras = Array.isArray(data.cameras) ? data.cameras : [];
    this.sunInfo = data.sun || null;
    this.haDiscovery = data.ha_discovery || null;

    this.zoneRenderer?.setZones(this.zones);
    this.zoneRenderer?.setZonesVisible(this.isOpen);
    if (this.isOpen) {
      this.render();
    }
  }

  _handleBackendAutomationMessage(msg) {
    if (!msg || typeof msg !== 'object') return;

    if (msg.type === 'automation_zones_updated' && Array.isArray(msg.zones)) {
      this.zones = msg.zones;
      this.zoneRenderer?.setZones(this.zones);
      this.zoneRenderer?.setZonesVisible(this.isOpen);
      if (this.isOpen && !this.editingZone) this.render();
      return;
    }

    if (msg.type === 'automation_rules_updated' && Array.isArray(msg.rules)) {
      this.rules = msg.rules;
      if (this.isOpen && !this.editingRule) this.render();
      return;
    }

    if (msg.type === 'automation_pretrigger_updated') {
      this.armedStates = Array.isArray(msg.armed_states) ? msg.armed_states : [];
      if (this.isOpen && !this.editingRule && this.activeTab === 'rules') {
        this.render();
      }
      return;
    }

    if (msg.type === 'virtual_entity_updated' && msg.entity) {
      const idx = this.virtualEntities.findIndex((e) => e.entity_id === msg.entity.entity_id);
      if (idx >= 0) this.virtualEntities[idx] = msg.entity;
      else this.virtualEntities.push(msg.entity);
      if (this.isOpen && this.activeTab === 'entities') this.render();
      return;
    }

    if (msg.type === 'virtual_entities_list' && Array.isArray(msg.entities)) {
      this.virtualEntities = msg.entities;
      if (this.isOpen && this.activeTab === 'entities') this.render();
      return;
    }

    if (msg.type === 'automation_triggered' && msg.log) {
      this.logs.unshift(msg.log);
      if (this.logs.length > 100) this.logs.length = 100;
      const r = this.rules.find((item) => item.rule_id === msg.rule_id);
      if (r) {
        r.trigger_count = msg.trigger_count ?? (r.trigger_count || 0) + 1;
        r.last_triggered_at = msg.last_triggered_at ?? msg.log.timestamp;
      }
      if (this.isOpen && (this.activeTab === 'logs' || (!this.editingRule && this.activeTab === 'rules'))) {
        this.render();
      }
      return;
    }

    if (msg.type === 'automation_ha_service_call') {
      const { domain, service, service_data } = msg;
      if (domain && service && this.haClient) {
        this.haClient.callService(domain, service, service_data || {});
      }
      return;
    }

    if (msg.type === 'automation_ui_alert') {
      this.showLiveAlertBanner(msg);
      if (this.isOpen && msg.zone_id) {
        this.zoneRenderer?.flashZoneAlert(msg.zone_id, msg.severity || 'critical');
      }
      if (msg.sound) {
        this._playAlertTone(msg.severity);
      }
    }
  }

  showLiveAlertBanner(alertMsg) {
    if (!this.alertBannerEl) return;
    const sev = alertMsg.severity || 'warning';
    this.alertBannerEl.className = `auto-live-alert-banner severity-${escapeHtml(sev)}`;
    this.alertBannerEl.innerHTML = `
      <div class="auto-alert-icon">${icon(sev === 'critical' ? 'siren' : 'shield-alert', { size: 18 })}</div>
      <div class="auto-alert-copy">
        <div class="auto-alert-title">${escapeHtml(alertMsg.title || 'Automazione attivata')}</div>
        <div class="auto-alert-msg">${escapeHtml(alertMsg.message || '')}</div>
      </div>
      <button type="button" class="auto-alert-close" id="btn-close-auto-alert" aria-label="Chiudi avviso">
        ${icon('x', { size: 15 })}
      </button>
    `;
    this.alertBannerEl.hidden = false;
    this.alertBannerEl.querySelector('#btn-close-auto-alert')?.addEventListener('click', () => {
      this.alertBannerEl.hidden = true;
    });

    if (this._alertBannerTimer) clearTimeout(this._alertBannerTimer);
    this._alertBannerTimer = setTimeout(() => {
      if (this.alertBannerEl) this.alertBannerEl.hidden = true;
    }, 9000);
  }

  _playAlertTone(severity = 'warning') {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = severity === 'critical' ? 'sawtooth' : 'sine';
      osc.frequency.setValueAtTime(severity === 'critical' ? 880 : 587.33, ctx.currentTime);
      if (severity === 'critical') {
        osc.frequency.linearRampToValueAtTime(1320, ctx.currentTime + 0.22);
        osc.frequency.linearRampToValueAtTime(880, ctx.currentTime + 0.45);
      }
      gain.gain.setValueAtTime(0.14, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.55);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.56);
    } catch {}
  }

  async open(initialTab = null) {
    if (initialTab) this.activeTab = initialTab;
    this.isOpen = true;
    this.isCollapsed = false;
    this.panelEl.hidden = false;
    this.panelEl.classList.add('open');
    this.panelEl.classList.remove('collapsed');
    this.zoneRenderer?.setZonesVisible(true);
    this.onOpenCallback?.();
    await this.refreshBootstrapData();
    this.render();
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this.isCollapsed = false;
    this.editingRule = null;
    this.editingZone = null;
    this.zoneRenderer?.stopDrawing();
    this.zoneRenderer?.hideDirectionCone();
    this.zoneRenderer?.setHighlightedZone(null);
    this.zoneRenderer?.setZonesVisible(false);
    this.panelEl.classList.remove('open', 'collapsed');
    this.panelEl.hidden = true;
    this.onCloseCallback?.();
  }

  setCollapsed(collapsed) {
    this.isCollapsed = Boolean(collapsed);
    if (!this.panelEl) return;
    this.panelEl.classList.toggle('collapsed', this.isCollapsed);
    const collapseBtn = this.panelEl.querySelector('#btn-auto-collapse');
    if (collapseBtn) {
      collapseBtn.innerHTML = icon(this.isCollapsed ? 'chevron-up' : 'chevron-down', { size: 17 });
      collapseBtn.title = this.isCollapsed
        ? 'Espandi pannello Automazioni'
        : 'Riduci in basso per vedere e toccare il 3D';
      collapseBtn.setAttribute('aria-expanded', String(!this.isCollapsed));
    }
  }

  toggleCollapsed() {
    this.setCollapsed(!this.isCollapsed);
  }

  toggle() {
    if (this.isOpen) this.close();
    else this.open();
  }

  setStatus(text, type = 'info') {
    this.statusMessage = text ? { text, type } : null;
    const msgEl = this.panelEl?.querySelector('#auto-studio-status-bar');
    if (msgEl) {
      if (!this.statusMessage) {
        msgEl.hidden = true;
      } else {
        msgEl.hidden = false;
        msgEl.className = `auto-status-bar ${this.statusMessage.type}`;
        msgEl.textContent = this.statusMessage.text;
      }
    }
  }

  // =========================================================================
  // MAIN RENDER & TAB DISPATCHER
  // =========================================================================

  render() {
    if (!this.isOpen || !this.panelEl) return;

    this.panelEl.classList.toggle('collapsed', this.isCollapsed);

    const sunLine = this.editingZone
      ? `Disegno 3D attivo · Tocca il modello 3D per aggiungere punti`
      : this.sunInfo
        ? `Alba ${this.sunInfo.sunrise_hhmm} · Tramonto ${this.sunInfo.sunset_hhmm}`
        : 'Aree 3D visibili in scena';

    const collapsedDrawToolbarHtml = this.editingZone
      ? `
        <div class="auto-collapsed-draw-bar" id="auto-collapsed-draw-bar">
          <span class="auto-collapsed-draw-count" id="zone-collapsed-vertices-count">
            ${this.editingZone.vertices.length} pt
          </span>
          <div class="auto-collapsed-draw-actions">
            <button type="button" class="auto-btn ghost xs" id="btn-collapsed-zone-undo" title="Annulla ultimo punto">
              ${icon('rotate-ccw', { size: 12 })} <span>Annulla</span>
            </button>
            ${
              this.editingZone.geometry_type === 'perimeter'
                ? `<button type="button" class="auto-btn tonal xs" id="btn-collapsed-zone-flip" title="Inverti verso freccia A↔B">
                     ${icon('refresh-cw', { size: 12 })} <span>A↔B</span>
                   </button>`
                : ''
            }
            <button type="button" class="auto-btn primary xs" id="btn-collapsed-zone-save">
              ${icon('check', { size: 12 })} <span>Salva</span>
            </button>
          </div>
        </div>
      `
      : '';

    this.panelEl.innerHTML = `
      <header class="auto-studio-header" id="auto-header-toggle" title="Tocca per ridurre in basso o espandere">
        <div class="auto-header-copy">
          <h2 class="auto-header-title">${this.editingZone ? escapeHtml(this.editingZone.name || 'Disegno Area 3D') : 'Automazioni'}</h2>
          <span class="auto-header-sub">${escapeHtml(sunLine)}</span>
        </div>
        <div class="auto-header-actions">
          <button
            type="button"
            class="auto-close-btn auto-collapse-btn"
            id="btn-auto-collapse"
            aria-expanded="${!this.isCollapsed}"
            title="${this.isCollapsed ? 'Espandi pannello Automazioni' : 'Riduci in basso per vedere e toccare il 3D'}"
            aria-label="Riduci o espandi pannello Automazioni"
          >
            ${icon(this.isCollapsed ? 'chevron-up' : 'chevron-down', { size: 17 })}
          </button>
          <button type="button" class="auto-close-btn" id="btn-auto-close" title="Chiudi Automazioni" aria-label="Chiudi Automazioni">
            ${icon('x', { size: 17 })}
          </button>
        </div>
      </header>

      ${collapsedDrawToolbarHtml}

      <div class="auto-tabs-bar">
        <nav class="auto-segmented-tabs" role="tablist" aria-label="Sezioni automazioni">
          <button type="button" class="auto-seg-tab ${this.activeTab === 'rules' ? 'active' : ''}" data-tab="rules" role="tab" aria-selected="${this.activeTab === 'rules'}">
            <span>Regole</span>
            <span class="auto-tab-count">${this.rules.length}</span>
          </button>
          <button type="button" class="auto-seg-tab ${this.activeTab === 'zones' ? 'active' : ''}" data-tab="zones" role="tab" aria-selected="${this.activeTab === 'zones'}">
            <span>Aree 3D</span>
            <span class="auto-tab-count">${this.zones.length}</span>
          </button>
          <button type="button" class="auto-seg-tab ${this.activeTab === 'entities' ? 'active' : ''}" data-tab="entities" role="tab" aria-selected="${this.activeTab === 'entities'}">
            <span>Entità</span>
            <span class="auto-tab-count">${this.virtualEntities.length}</span>
          </button>
          <button type="button" class="auto-seg-tab ${this.activeTab === 'logs' ? 'active' : ''}" data-tab="logs" role="tab" aria-selected="${this.activeTab === 'logs'}">
            <span>Log</span>
            <span class="auto-tab-count">${this.logs.length}</span>
          </button>
        </nav>
      </div>

      <div id="auto-studio-status-bar" class="auto-status-bar ${this.statusMessage?.type || 'info'}" ${this.statusMessage ? '' : 'hidden'}>
        ${escapeHtml(this.statusMessage?.text || '')}
      </div>

      <div class="auto-studio-body" id="auto-studio-body">
        ${this._renderActiveTabContent()}
      </div>

      <datalist id="auto-all-entities-datalist">
        ${this._buildEntitiesDatalistOptionsHtml()}
      </datalist>
      <datalist id="auto-cameras-datalist">
        ${this.cameras.map((cam) => `<option value="${escapeHtml(cam)}"></option>`).join('')}
      </datalist>
    `;

    this._bindHeaderAndTabEvents();
    this._bindActiveTabEvents();
  }

  _buildEntitiesDatalistOptionsHtml() {
    const options = [];
    for (const ve of this.virtualEntities) {
      options.push(
        `<option value="${escapeHtml(ve.entity_id)}">[SH3D] ${escapeHtml(ve.name)} (${escapeHtml(ve.state)})</option>`
      );
    }
    const haEntities = this.haClient?.entities || {};
    for (const [eid, st] of Object.entries(haEntities)) {
      const fn = st?.attributes?.friendly_name || eid;
      options.push(
        `<option value="${escapeHtml(eid)}">[HA] ${escapeHtml(fn)} (${escapeHtml(st?.state ?? '')})</option>`
      );
    }
    return options.join('');
  }

  _refreshHaDatalist() {
    const dl = this.panelEl?.querySelector('#auto-all-entities-datalist');
    if (dl) {
      dl.innerHTML = this._buildEntitiesDatalistOptionsHtml();
    }
  }

  _renderActiveTabContent() {
    if (this.activeTab === 'rules') {
      return this.editingRule ? this._renderRuleEditor() : this._renderRulesList();
    }
    if (this.activeTab === 'zones') {
      return this.editingZone ? this._renderZoneEditor() : this._renderZonesList();
    }
    if (this.activeTab === 'entities') {
      return this._renderVirtualEntitiesTab();
    }
    return this._renderLogsTab();
  }

  _bindHeaderAndTabEvents() {
    this.panelEl.querySelector('#btn-auto-close')?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.close();
    });

    this.panelEl.querySelector('#btn-auto-collapse')?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleCollapsed();
    });

    this.panelEl.querySelector('#auto-header-toggle')?.addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      this.toggleCollapsed();
    });

    this.panelEl.querySelector('#btn-collapsed-zone-undo')?.addEventListener('click', () => {
      this.zoneRenderer?.undoLastDraftVertex();
    });

    this.panelEl.querySelector('#btn-collapsed-zone-flip')?.addEventListener('click', () => {
      if (!this.editingZone) return;
      this.editingZone.normal_flipped = !this.editingZone.normal_flipped;
      if (this.zoneRenderer) {
        this.zoneRenderer.draftNormalFlipped = this.editingZone.normal_flipped;
        this.zoneRenderer.rebuildDraftVisual();
      }
    });

    this.panelEl.querySelector('#btn-collapsed-zone-save')?.addEventListener('click', () => {
      this._saveEditingZone();
    });

    this.panelEl.querySelectorAll('.auto-seg-tab[data-tab]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.zoneRenderer?.stopDrawing();
        this.zoneRenderer?.hideDirectionCone();
        this.editingRule = null;
        this.editingZone = null;
        this.statusMessage = null;
        this.activeTab = btn.dataset.tab;
        this.render();
      });
    });
  }

  _bindActiveTabEvents() {
    if (this.activeTab === 'rules') {
      if (this.editingRule) this._bindRuleEditorEvents();
      else this._bindRulesListEvents();
    } else if (this.activeTab === 'zones') {
      if (this.editingZone) this._bindZoneEditorEvents();
      else this._bindZonesListEvents();
    } else if (this.activeTab === 'entities') {
      this._bindVirtualEntitiesEvents();
    } else if (this.activeTab === 'logs') {
      this._bindLogsEvents();
    }
  }

  // =========================================================================
  // TAB 1: RULES LIST & RULE EDITOR
  // =========================================================================

  _renderRulesList() {
    const rowsHtml =
      this.rules.length === 0
        ? `<div class="auto-empty-state">
             <p class="auto-empty-title">Nessuna regola configurata</p>
             <span class="auto-empty-sub">Crea una regola usando aree 3D, perimetri orientati, direzione e velocità, orari o stati entità.</span>
           </div>`
        : this.rules
            .map((r) => {
              const preCount = Array.isArray(r.pre_triggers) ? r.pre_triggers.length : 0;
              const trigCount = Array.isArray(r.triggers) ? r.triggers.length : 0;
              const actCount = Array.isArray(r.actions) ? r.actions.length : 0;
              const lastStr = r.last_triggered_at
                ? new Date(r.last_triggered_at * 1000).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
                : 'Mai';
              const armedForRule = this.armedStates.filter((a) => a.rule_id === r.rule_id);
              const armedHtml = armedForRule.length
                ? `<div class="auto-armed-pill" title="${escapeHtml(armedForRule[0].summary || '')}">⚡ Pre-trigger: ${escapeHtml(armedForRule[0].stage_name || 'Attivo')} · ${Number(armedForRule[0].remaining_s ?? 0).toFixed(0)}s</div>`
                : '';
              const seqPrefix = preCount > 0 ? `${preCount} pre-trigger → ` : '';
              return `
                <div class="auto-list-item ${r.enabled ? '' : 'is-disabled'}" data-rule-card="${escapeHtml(r.rule_id)}">
                  <div class="auto-item-main">
                    <div class="auto-item-info">
                      <div class="auto-item-title-row">
                        <span class="auto-status-dot ${r.enabled ? 'on' : 'off'}"></span>
                        <h4 class="auto-item-title">${escapeHtml(r.name)}</h4>
                      </div>
                      <p class="auto-item-sub">
                        ${escapeHtml(r.description || `${seqPrefix}${trigCount} trigger · ${actCount} azioni · Ultima: ${lastStr}`)}
                      </p>
                      ${armedHtml}
                    </div>
                    <label class="auto-switch" title="Attiva o disattiva regola">
                      <input type="checkbox" class="auto-rule-toggle-cb" data-rule-id="${escapeHtml(r.rule_id)}" ${r.enabled ? 'checked' : ''} />
                      <span class="auto-switch-slider"></span>
                    </label>
                  </div>
                  <div class="auto-item-footer">
                    <span class="auto-item-stat">${r.trigger_count || 0} esecuzioni · ${escapeHtml(r.execution_mode || 'single')}</span>
                    <div class="auto-item-actions">
                      <button type="button" class="auto-btn ghost xs" data-run-rule="${escapeHtml(r.rule_id)}" title="Esegui subito le azioni">
                        ${icon('play', { size: 12 })} <span>Test</span>
                      </button>
                      <button type="button" class="auto-btn tonal xs" data-edit-rule="${escapeHtml(r.rule_id)}">
                        <span>Modifica</span>
                      </button>
                      <button type="button" class="auto-btn icon-only danger xs" data-del-rule="${escapeHtml(r.rule_id)}" title="Elimina regola" aria-label="Elimina regola">
                        ${icon('x', { size: 13 })}
                      </button>
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

  _bindRulesListEvents() {
    this.panelEl.querySelector('#btn-auto-new-rule')?.addEventListener('click', () => {
      this.editingRule = this._createDefaultRuleDraft();
      this.render();
    });

    this.panelEl.querySelectorAll('.auto-rule-toggle-cb').forEach((cb) => {
      cb.addEventListener('change', async () => {
        const ruleId = cb.dataset.ruleId;
        await this.spatialStreamClient?.toggleAutomationRule?.(ruleId, cb.checked);
        await this.refreshBootstrapData();
      });
    });

    this.panelEl.querySelectorAll('[data-run-rule]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const ruleId = btn.dataset.runRule;
        const res = await this.spatialStreamClient?.triggerAutomationRule?.(ruleId);
        if (res?.status === 'ok') {
          this.setStatus('Azioni eseguite.', 'success');
          await this.refreshBootstrapData();
        } else {
          this.setStatus('Errore durante il test della regola.', 'error');
        }
      });
    });

    this.panelEl.querySelectorAll('[data-edit-rule]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const found = this.rules.find((r) => r.rule_id === btn.dataset.editRule);
        if (found) {
          this.editingRule = JSON.parse(JSON.stringify(found));
          this._normalizeEditingRule(this.editingRule);
          this.render();
        }
      });
    });

    this.panelEl.querySelectorAll('[data-del-rule]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const ruleId = btn.dataset.delRule;
        await this.spatialStreamClient?.deleteAutomationRule?.(ruleId);
        this.setStatus('Regola eliminata.', 'info');
        await this.refreshBootstrapData();
      });
    });
  }

  _normalizeEditingRule(rule) {
    if (!rule) return;
    if (!Array.isArray(rule.pre_triggers)) rule.pre_triggers = [];
    if (!Array.isArray(rule.triggers)) rule.triggers = [];
    if (!Array.isArray(rule.actions)) rule.actions = [];
    if (!rule.trigger_logic) rule.trigger_logic = 'or';
    if (!Number.isFinite(Number(rule.trigger_window_s))) rule.trigger_window_s = 10.0;
    if (!rule.trigger_correlation_scope) rule.trigger_correlation_scope = 'same_subject';
    rule.log_blocked_evaluations = Boolean(rule.log_blocked_evaluations);
    if (!rule.condition) {
      rule.condition = {
        condition_id: uid('cnd'),
        type: 'and',
        children: [],
        params: {},
      };
    }
  }

  _createDefaultRuleDraft() {
    const firstZoneId = this.zones[0]?.zone_id || '';
    return {
      rule_id: uid('rule'),
      name: 'Nuova automazione',
      description: '',
      enabled: true,
      execution_mode: 'single',
      cooldown_s: 5.0,
      pre_triggers: [],
      trigger_logic: 'or',
      trigger_window_s: 10.0,
      trigger_correlation_scope: 'same_subject',
      log_blocked_evaluations: false,
      triggers: [
        {
          trigger_id: uid('trg'),
          type: 'zone_presence',
          enabled: true,
          subject_filter: {
            classes: ['person'],
            face_mode: 'unknown',
            identities: [],
            plate_mode: 'any',
            plates: [],
            biometric_grace_s: 1.2,
          },
          params: {
            zone_id: firstZoneId,
            event: 'enter',
            min_dwell_s: 0,
          },
        },
      ],
      condition: {
        condition_id: uid('cnd'),
        type: 'and',
        children: [
          {
            condition_id: uid('cnd'),
            type: 'entity_state',
            children: [],
            params: {
              entity_id: 'sh3d.allarme',
              operator: '==',
              value: 'on',
            },
          },
        ],
        params: {},
      },
      actions: [
        {
          action_id: uid('act'),
          type: 'ui_alert',
          params: {
            title: 'Allarme area 3D',
            message: 'Rilevato {{ track.identity }} in {{ trigger.zone_name }}',
            severity: 'critical',
            sound: true,
          },
          then_actions: [],
          else_actions: [],
        },
      ],
    };
  }

  _renderRuleEditor() {
    const r = this.editingRule;
    return `
      <div class="auto-editor">
        <div class="auto-editor-bar">
          <button type="button" class="auto-btn ghost sm" id="btn-auto-rule-back">
            ${icon('chevron-left', { size: 14 })} <span>Indietro</span>
          </button>
          <button type="button" class="auto-btn primary sm" id="btn-auto-rule-save">
            ${icon('check', { size: 14 })} <span>Salva regola</span>
          </button>
        </div>

        <section class="auto-block">
          <div class="auto-grid-2">
            <label class="auto-field span-2">
              <span>Nome regola</span>
              <input type="text" id="rule-inp-name" value="${escapeHtml(r.name)}" placeholder="Es. Allarme giardino" />
            </label>
            <label class="auto-field span-2">
              <span>Note (opzionale)</span>
              <input type="text" id="rule-inp-desc" value="${escapeHtml(r.description || '')}" placeholder="Descrizione sintetica" />
            </label>
            <label class="auto-field">
              <span>Esecuzione</span>
              <select id="rule-inp-exec-mode">
                <option value="single" ${r.execution_mode === 'single' ? 'selected' : ''}>Singola (ignora se attiva)</option>
                <option value="restart" ${r.execution_mode === 'restart' ? 'selected' : ''}>Riavvia se riscatta</option>
                <option value="parallel" ${r.execution_mode === 'parallel' ? 'selected' : ''}>Parallela</option>
                <option value="queued" ${r.execution_mode === 'queued' ? 'selected' : ''}>In coda (sequenziale)</option>
              </select>
            </label>
            <label class="auto-field">
              <span>Cooldown (s)</span>
              <input type="number" id="rule-inp-cooldown" min="0" max="86400" step="0.5" value="${Number(r.cooldown_s ?? 3)}" />
            </label>
            <label class="auto-check-row span-2">
              <input type="checkbox" id="rule-inp-log-blocked" ${r.log_blocked_evaluations ? 'checked' : ''} />
              <span>Logga valutazioni bloccate (diagnostica)</span>
            </label>
          </div>
        </section>

        <section class="auto-block">
          <div class="auto-block-header">
            <h3 class="auto-block-title">Pre-Trigger / Sequenza (opzionale)</h3>
            <button type="button" class="auto-btn tonal xs" id="btn-rule-add-pretrigger">
              ${icon('plus', { size: 12 })} <span>Pre-Trigger</span>
            </button>
          </div>
          ${
            Array.isArray(r.pre_triggers) && r.pre_triggers.length > 0
              ? `<div class="auto-stack" id="rule-pretriggers-stack">
                   ${r.pre_triggers.map((stg, sIdx) => this._renderPreTriggerStageHtml(stg, sIdx, r.pre_triggers.length)).join('')}
                 </div>`
              : `<p class="auto-hint-text">Aggiungi un pre-trigger per armare una finestra d'attesa (es. veicolo ≥ 0,5 m/s → attende max 10s → rileva targa in whitelist).</p>`
          }
        </section>

        <section class="auto-block">
          <div class="auto-block-header">
            <h3 class="auto-block-title">Quando scatta (Trigger)</h3>
            <button type="button" class="auto-btn tonal xs" id="btn-rule-add-trigger">
              ${icon('plus', { size: 12 })} <span>Trigger</span>
            </button>
          </div>
          ${
            r.triggers.length > 1 || r.trigger_logic === 'and_within'
              ? `<div class="auto-trigger-logic-bar">
                   <div class="auto-grid-2">
                     <label class="auto-field ${r.trigger_logic === 'and_within' ? '' : 'span-2'}">
                       <span>Logica trigger</span>
                       <select id="rule-inp-trigger-logic">
                         <option value="or" ${(!r.trigger_logic || r.trigger_logic === 'or') ? 'selected' : ''}>OR · Uno qualsiasi</option>
                         <option value="and_within" ${r.trigger_logic === 'and_within' ? 'selected' : ''}>AND · Tutti entro finestra</option>
                       </select>
                     </label>
                     ${
                       r.trigger_logic === 'and_within'
                         ? `<label class="auto-field">
                              <span>Finestra (s)</span>
                              <input type="number" min="0.5" max="3600" step="0.5" id="rule-inp-trigger-window" value="${Number(r.trigger_window_s ?? 10)}" />
                            </label>
                            <label class="auto-field span-2">
                              <span>Correlazione</span>
                              <select id="rule-inp-trigger-corr">
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
            ${r.triggers.map((t, idx) => this._renderTriggerItemHtml(t, `main:${idx}`)).join('')}
          </div>
        </section>

        <section class="auto-block">
          <div class="auto-block-header">
            <h3 class="auto-block-title">Condizioni (AND / OR / NOT)</h3>
          </div>
          <div class="auto-cond-root">
            ${this._renderConditionNodeHtml(r.condition, 'root', true)}
          </div>
        </section>

        <section class="auto-block">
          <div class="auto-block-header">
            <h3 class="auto-block-title">Azioni</h3>
            <button type="button" class="auto-btn tonal xs" id="btn-rule-add-action">
              ${icon('plus', { size: 12 })} <span>Azione</span>
            </button>
          </div>
          <div class="auto-stack" id="rule-actions-stack">
            ${r.actions.map((a, idx) => this._renderActionItemHtml(a, `${idx}`)).join('')}
          </div>
        </section>
      </div>
    `;
  }

  _renderPreTriggerStageHtml(stage, sIdx, totalStages) {
    const triggers = Array.isArray(stage.triggers) ? stage.triggers : [];
    const matchMode = stage.match_mode || 'any';
    const corrScope = stage.correlation_scope || 'same_subject';
    const stageName = stage.name || `Pre-trigger ${sIdx + 1}`;
    return `
      <div class="auto-pretrigger-card" data-pre-stage-idx="${sIdx}">
        <div class="auto-pretrigger-head">
          <span class="auto-pretrigger-badge">⚡ Fase ${sIdx + 1}</span>
          <input type="text" class="auto-pretrigger-name-inp" data-pre-field="${sIdx}:name" value="${escapeHtml(stageName)}" placeholder="Nome pre-trigger" />
          <button type="button" class="auto-btn icon-only danger xs" data-del-pre-idx="${sIdx}" title="Rimuovi pre-trigger" aria-label="Rimuovi pre-trigger">
            ${icon('x', { size: 13 })}
          </button>
        </div>

        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Attesa max (s)</span>
            <input type="number" min="0.5" max="3600" step="0.5" data-pre-field="${sIdx}:max_wait_s" value="${Number(stage.max_wait_s ?? 10)}" />
          </label>
          <label class="auto-field">
            <span>Ritardo min (s)</span>
            <input type="number" min="0" max="3600" step="0.5" data-pre-field="${sIdx}:min_delay_s" value="${Number(stage.min_delay_s ?? 0)}" />
          </label>
          <label class="auto-field">
            <span>Correlazione</span>
            <select data-pre-field="${sIdx}:correlation_scope">
              <option value="same_subject" ${corrScope === 'same_subject' ? 'selected' : ''}>Stesso soggetto</option>
              <option value="same_track" ${corrScope === 'same_track' ? 'selected' : ''}>Stessa traccia / ID</option>
              <option value="same_scene_event" ${corrScope === 'same_scene_event' ? 'selected' : ''}>Stesso episodio scena</option>
              <option value="any" ${corrScope === 'any' ? 'selected' : ''}>Qualsiasi (cross-domain)</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Logica stage</span>
            <select data-pre-field="${sIdx}:match_mode">
              <option value="any" ${matchMode === 'any' ? 'selected' : ''}>OR · Uno qualsiasi</option>
              <option value="all" ${matchMode === 'all' ? 'selected' : ''}>AND · Tutti entro finestra</option>
            </select>
          </label>
          ${
            matchMode === 'all'
              ? `<label class="auto-field span-2">
                   <span>Finestra stage AND (s)</span>
                   <input type="number" min="0.5" max="3600" step="0.5" data-pre-field="${sIdx}:stage_window_s" value="${Number(stage.stage_window_s ?? 10)}" />
                 </label>`
              : ''
          }
          <label class="auto-check-row">
            <input type="checkbox" data-pre-bool="${sIdx}:refresh_on_rearm" ${stage.refresh_on_rearm !== false ? 'checked' : ''} />
            <span>Rinnova finestra se attivo</span>
          </label>
          <label class="auto-check-row">
            <input type="checkbox" data-pre-bool="${sIdx}:consume_on_fire" ${stage.consume_on_fire !== false ? 'checked' : ''} />
            <span>Consuma allo scatto</span>
          </label>
        </div>

        <div class="auto-block-header">
          <span class="auto-notif-label">Trigger di questa fase</span>
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
          ${triggers.map((t, tIdx) => this._renderTriggerItemHtml(t, `pre:${sIdx}:${tIdx}`)).join('')}
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
        ↓ Attende max ${Number(stage.max_wait_s ?? 10)}s → ${sIdx + 1 < totalStages ? `Fase ${sIdx + 2}` : 'Trigger principali'} ↓
      </div>
    `;
  }

  _renderTriggerItemHtml(trig, pathStr) {
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

    const polygonOptions = this.zones
      .filter((z) => z.geometry_type === 'polygon')
      .map((z) => `<option value="${escapeHtml(z.zone_id)}" ${p.zone_id === z.zone_id ? 'selected' : ''}>${escapeHtml(z.name)}</option>`)
      .join('');

    const allZoneOptions = this.zones
      .map((z) => `<option value="${escapeHtml(z.zone_id)}" ${(p.perimeter_id || p.zone_id) === z.zone_id ? 'selected' : ''}>${escapeHtml(z.name)} (${z.geometry_type === 'perimeter' ? 'Perimetro' : 'Area'})</option>`)
      .join('');

    let specificFieldsHtml = '';

    if (tType === 'zone_presence') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Area poligonale</span>
            <div class="auto-input-with-btn">
              <select data-trig-param="${escapeHtml(pathStr)}:zone_id">
                <option value="">Seleziona area...</option>
                ${polygonOptions}
              </select>
              <button type="button" class="auto-btn tonal xs" data-quick-new-zone="polygon" title="Disegna nuova area nel 3D">
                ${icon('plus', { size: 12 })} <span>Disegna 3D</span>
              </button>
            </div>
          </label>
          <label class="auto-field">
            <span>Evento</span>
            <select data-trig-param="${escapeHtml(pathStr)}:event">
              <option value="enter" ${p.event === 'enter' ? 'selected' : ''}>Entrata</option>
              <option value="present" ${p.event === 'present' ? 'selected' : ''}>Presenza / Riconoscimento in area</option>
              <option value="exit" ${p.event === 'exit' ? 'selected' : ''}>Uscita</option>
              <option value="dwell" ${p.event === 'dwell' ? 'selected' : ''}>Stazionamento</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Permanenza min (s)</span>
            <input type="number" min="0" max="3600" step="0.5" data-trig-param="${escapeHtml(pathStr)}:min_dwell_s" value="${Number(p.min_dwell_s ?? 0)}" />
          </label>
        </div>
      `;
    } else if (tType === 'perimeter_crossing') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Perimetro / linea 3D</span>
            <div class="auto-input-with-btn">
              <select data-trig-param="${escapeHtml(pathStr)}:perimeter_id">
                <option value="">Seleziona perimetro...</option>
                ${allZoneOptions}
              </select>
              <button type="button" class="auto-btn tonal xs" data-quick-new-zone="perimeter" title="Disegna nuovo perimetro nel 3D">
                ${icon('plus', { size: 12 })} <span>Disegna 3D</span>
              </button>
            </div>
          </label>
          <label class="auto-field span-2">
            <span>Verso di attraversamento</span>
            <select data-trig-param="${escapeHtml(pathStr)}:direction">
              <option value="a_to_b" ${p.direction === 'a_to_b' ? 'selected' : ''}>A → B (verso freccia 3D)</option>
              <option value="b_to_a" ${p.direction === 'b_to_a' ? 'selected' : ''}>B → A (opposto alla freccia)</option>
              <option value="both" ${(!p.direction || p.direction === 'both') ? 'selected' : ''}>Entrambi i versi (A ↔ B)</option>
            </select>
          </label>
        </div>
      `;
    } else if (tType === 'zone_transition') {
      const fromOpts = this.zones
        .filter((z) => z.geometry_type === 'polygon')
        .map((z) => `<option value="${escapeHtml(z.zone_id)}" ${p.from_zone_id === z.zone_id ? 'selected' : ''}>${escapeHtml(z.name)}</option>`)
        .join('');
      const toOpts = this.zones
        .filter((z) => z.geometry_type === 'polygon')
        .map((z) => `<option value="${escapeHtml(z.zone_id)}" ${p.to_zone_id === z.zone_id ? 'selected' : ''}>${escapeHtml(z.name)}</option>`)
        .join('');
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Da Area A</span>
            <select data-trig-param="${escapeHtml(pathStr)}:from_zone_id">
              <option value="">Seleziona...</option>
              ${fromOpts}
            </select>
          </label>
          <label class="auto-field">
            <span>Ad Area B</span>
            <select data-trig-param="${escapeHtml(pathStr)}:to_zone_id">
              <option value="">Seleziona...</option>
              ${toOpts}
            </select>
          </label>
          <label class="auto-field">
            <span>Transito max (s)</span>
            <input type="number" min="1" max="600" step="1" data-trig-param="${escapeHtml(pathStr)}:max_transit_s" value="${Number(p.max_transit_s ?? 20)}" />
          </label>
          <label class="auto-field">
            <span>Vel. min (m/s)</span>
            <input type="number" min="0" max="30" step="0.1" data-trig-param="${escapeHtml(pathStr)}:min_speed_mps" value="${Number(p.min_speed_mps ?? 0)}" />
          </label>
        </div>
      `;
    } else if (tType === 'kinematic_vector') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Area di riferimento</span>
            <select data-trig-param="${escapeHtml(pathStr)}:zone_id">
              <option value="">Ovunque nella scena 3D</option>
              ${polygonOptions}
            </select>
          </label>
          <label class="auto-field span-2">
            <span>Direzione azimut (0°=Est, 90°=Sud, 180°=Ovest, 270°=Nord)</span>
            <div class="auto-input-with-btn">
              <input type="number" min="0" max="359" step="5" placeholder="Qualsiasi direzione" data-trig-param="${escapeHtml(pathStr)}:target_azimuth_deg" value="${p.target_azimuth_deg ?? ''}" />
              <button type="button" class="auto-btn tonal xs" data-pick-direction-3d="${escapeHtml(pathStr)}" title="Clicca 2 punti nel 3D per orientare il vettore direzione">
                ${icon('compass', { size: 12 })} <span>Punta 3D</span>
              </button>
            </div>
          </label>
          <label class="auto-field">
            <span>Tolleranza (±°)</span>
            <input type="number" min="5" max="180" step="5" data-trig-param="${escapeHtml(pathStr)}:azimuth_tolerance_deg" value="${Number(p.azimuth_tolerance_deg ?? 35)}" />
          </label>
          <label class="auto-field">
            <span>Durata min (s)</span>
            <input type="number" min="0.2" max="120" step="0.1" data-trig-param="${escapeHtml(pathStr)}:min_duration_s" value="${Number(p.min_duration_s ?? 1.0)}" />
          </label>
          <label class="auto-field">
            <span>Vel. min (m/s)</span>
            <input type="number" min="0" max="40" step="0.1" data-trig-param="${escapeHtml(pathStr)}:min_speed_mps" value="${Number(p.min_speed_mps ?? 0.5)}" />
          </label>
          <label class="auto-field">
            <span>Vel. max (m/s)</span>
            <input type="number" min="0" max="40" step="0.1" placeholder="Illimitata" data-trig-param="${escapeHtml(pathStr)}:max_speed_mps" value="${p.max_speed_mps ?? ''}" />
          </label>
        </div>
      `;
    } else if (tType === 'time_schedule') {
      const mode = p.mode || 'fixed_time';
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Riferimento</span>
            <select data-trig-param="${escapeHtml(pathStr)}:mode">
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
                   <input type="time" data-trig-param="${escapeHtml(pathStr)}:at" value="${escapeHtml(p.at || '22:00')}" />
                 </label>`
              : mode === 'interval'
                ? `<label class="auto-field">
                     <span>Ogni (secondi)</span>
                     <input type="number" min="5" max="86400" step="5" data-trig-param="${escapeHtml(pathStr)}:interval_seconds" value="${Number(p.interval_seconds ?? 60)}" />
                   </label>`
                : `<label class="auto-field">
                     <span>Offset (min, ±)</span>
                     <input type="number" min="-360" max="360" step="5" data-trig-param="${escapeHtml(pathStr)}:offset_minutes" value="${Number(p.offset_minutes ?? 0)}" />
                   </label>`
          }
        </div>
      `;
    } else if (tType === 'entity_state_change') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>ID Entità (<code>sh3d.*</code> o Home Assistant)</span>
            <input type="text" list="auto-all-entities-datalist" data-trig-param="${escapeHtml(pathStr)}:entity_id" value="${escapeHtml(p.entity_id || 'sh3d.allarme_perimetrale')}" placeholder="Es. sh3d.allarme_perimetrale o switch.cancello" />
          </label>
          <label class="auto-field">
            <span>Da stato (opz.)</span>
            <input type="text" data-trig-param="${escapeHtml(pathStr)}:from_state" value="${escapeHtml(p.from_state || '')}" placeholder="Qualsiasi" />
          </label>
          <label class="auto-field">
            <span>A stato</span>
            <input type="text" data-trig-param="${escapeHtml(pathStr)}:to_state" value="${escapeHtml(p.to_state || 'on')}" placeholder="on" />
          </label>
          <label class="auto-field span-2">
            <span>Mantenuto per almeno (s)</span>
            <input type="number" min="0" max="3600" step="1" data-trig-param="${escapeHtml(pathStr)}:for_duration_s" value="${Number(p.for_duration_s ?? 0)}" />
          </label>
        </div>
      `;
    } else if (tType === 'biometric_detection') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Modalità</span>
            <select data-trig-param="${escapeHtml(pathStr)}:modality">
              <option value="any" ${(!p.modality || p.modality === 'any') ? 'selected' : ''}>Volto o targa</option>
              <option value="face" ${p.modality === 'face' ? 'selected' : ''}>Solo volto</option>
              <option value="alpr" ${p.modality === 'alpr' ? 'selected' : ''}>Solo targa</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Camera (opz.)</span>
            <input type="text" list="auto-cameras-datalist" data-trig-param="${escapeHtml(pathStr)}:camera_id" value="${escapeHtml(p.camera_id || '')}" placeholder="Tutte" />
          </label>
          <label class="auto-field span-2">
            <span>Area 3D (opz.)</span>
            <select data-trig-param="${escapeHtml(pathStr)}:zone_id">
              <option value="">Ovunque nella scena 3D</option>
              ${polygonOptions}
            </select>
          </label>
          <label class="auto-check-row span-2">
            <input type="checkbox" data-trig-bool="${escapeHtml(pathStr)}:require_locked" ${p.require_locked !== false ? 'checked' : ''} />
            <span>Solo riconoscimento confermato (consenso K frame / sconosciuto finale)</span>
          </label>
        </div>
      `;
    } else if (tType === 'proximity_3d') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Coord. X (m)</span>
            <input type="number" step="0.1" data-trig-param="${escapeHtml(pathStr)}:target_x" value="${Number(p.target_x ?? 0)}" />
          </label>
          <label class="auto-field">
            <span>Coord. Z (m)</span>
            <input type="number" step="0.1" data-trig-param="${escapeHtml(pathStr)}:target_z" value="${Number(p.target_z ?? 0)}" />
          </label>
          <label class="auto-field">
            <span>Raggio (m)</span>
            <input type="number" min="0.2" max="50" step="0.2" data-trig-param="${escapeHtml(pathStr)}:radius_m" value="${Number(p.radius_m ?? 2.0)}" />
          </label>
          <label class="auto-field">
            <span>Permanenza (s)</span>
            <input type="number" min="0" max="600" step="0.5" data-trig-param="${escapeHtml(pathStr)}:min_dwell_s" value="${Number(p.min_dwell_s ?? 1.0)}" />
          </label>
        </div>
      `;
    } else if (tType === 'scene_event') {
      specificFieldsHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Fase episodio</span>
            <select data-trig-param="${escapeHtml(pathStr)}:event">
              <option value="started" ${(!p.event || p.event === 'started') ? 'selected' : ''}>Inizio episodio</option>
              <option value="importance_escalated" ${p.event === 'importance_escalated' ? 'selected' : ''}>Escalation ad Allerta</option>
              <option value="closed" ${p.event === 'closed' ? 'selected' : ''}>Chiusura episodio</option>
              <option value="any" ${p.event === 'any' ? 'selected' : ''}>Qualsiasi transizione</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Importanza</span>
            <select data-trig-param="${escapeHtml(pathStr)}:importance">
              <option value="any" ${(!p.importance || p.importance === 'any') ? 'selected' : ''}>Qualsiasi</option>
              <option value="alert" ${p.importance === 'alert' ? 'selected' : ''}>Allerta</option>
              <option value="notable" ${p.importance === 'notable' ? 'selected' : ''}>Rilevante</option>
              <option value="routine" ${p.importance === 'routine' ? 'selected' : ''}>Routine</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Area 3D (opz.)</span>
            <select data-trig-param="${escapeHtml(pathStr)}:zone_id">
              <option value="">Tutte</option>
              ${polygonOptions}
            </select>
          </label>
          <label class="auto-field">
            <span>Soggetti minimi</span>
            <input type="number" min="0" max="20" step="1" data-trig-param="${escapeHtml(pathStr)}:min_subjects" value="${Number(p.min_subjects ?? 0)}" />
          </label>
        </div>
      `;
    }

    return `
      <div class="auto-node-surface">
        <div class="auto-node-bar">
          <select class="auto-node-type-select" data-trig-type-path="${escapeHtml(pathStr)}">
            ${Object.entries(TRIGGER_TYPE_LABELS)
              .map(([k, label]) => `<option value="${k}" ${tType === k ? 'selected' : ''}>${escapeHtml(label)}</option>`)
              .join('')}
          </select>
          <button type="button" class="auto-btn icon-only danger xs" data-del-trig-path="${escapeHtml(pathStr)}" title="Rimuovi trigger" aria-label="Rimuovi trigger">
            ${icon('x', { size: 13 })}
          </button>
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

    const savedIdChips = this.identities
      .map((item) => {
        const name = item.name;
        const active = selectedIds.some((s) => s.toLowerCase() === name.toLowerCase());
        return `<button type="button" class="auto-chip ${active ? 'active' : ''}" data-trig-id-chip="${escapeHtml(pathStr)}:${escapeHtml(name)}">${escapeHtml(name)}</button>`;
      })
      .join('');

    const savedPlateChips = this.plates
      .map((item) => {
        const plate = String(item.plate || '').toUpperCase();
        if (!plate) return '';
        const label = item.owner_name ? `${plate} · ${item.owner_name}` : plate;
        const active = selectedPlates.some((s) => s.toUpperCase() === plate);
        return `<button type="button" class="auto-chip ${active ? 'active' : ''}" data-trig-plate-chip="${escapeHtml(pathStr)}:${escapeHtml(plate)}">${escapeHtml(label)}</button>`;
      })
      .filter(Boolean)
      .join('');

    return `
      <div class="auto-filter-divider">
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Soggetto</span>
            <select data-trig-sf="${escapeHtml(pathStr)}:classes">
              <option value="any" ${currentClass === 'any' ? 'selected' : ''}>Qualsiasi</option>
              <option value="person" ${currentClass === 'person' ? 'selected' : ''}>Persone</option>
              <option value="vehicle" ${currentClass === 'vehicle' ? 'selected' : ''}>Veicoli</option>
              <option value="dog" ${currentClass === 'dog' ? 'selected' : ''}>Animali</option>
              <option value="bicycle" ${currentClass === 'bicycle' ? 'selected' : ''}>Biciclette</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Filtro volto</span>
            <select data-trig-sf="${escapeHtml(pathStr)}:face_mode">
              <option value="any" ${faceMode === 'any' ? 'selected' : ''}>Chiunque</option>
              <option value="unknown" ${faceMode === 'unknown' ? 'selected' : ''}>Solo sconosciuti</option>
              <option value="known" ${faceMode === 'known' ? 'selected' : ''}>Volti registrati</option>
              <option value="include" ${faceMode === 'include' ? 'selected' : ''}>Solo specifici...</option>
              <option value="exclude" ${faceMode === 'exclude' ? 'selected' : ''}>Escludi specifici...</option>
            </select>
          </label>
          ${
            faceMode === 'include' || faceMode === 'exclude'
              ? `<div class="auto-field span-2">
                   <span>Persone (${faceMode === 'include' ? 'incluse' : 'escluse'})</span>
                   ${savedIdChips ? `<div class="auto-chips-wrap">${savedIdChips}</div>` : ''}
                   <input type="text" data-trig-sf="${escapeHtml(pathStr)}:identities" value="${escapeHtml(selectedIds.join(', '))}" placeholder="Nomi separati da virgola" />
                 </div>`
              : ''
          }
          <label class="auto-field">
            <span>Filtro targa</span>
            <select data-trig-sf="${escapeHtml(pathStr)}:plate_mode">
              <option value="any" ${plateMode === 'any' ? 'selected' : ''}>Qualsiasi</option>
              <option value="whitelisted" ${plateMode === 'whitelisted' ? 'selected' : ''}>In whitelist</option>
              <option value="not_whitelisted" ${plateMode === 'not_whitelisted' ? 'selected' : ''}>Non in whitelist</option>
              <option value="include" ${plateMode === 'include' ? 'selected' : ''}>Specifiche...</option>
              <option value="exclude" ${plateMode === 'exclude' ? 'selected' : ''}>Escludi...</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Grazia biometria (s)</span>
            <input type="number" min="0" max="60" step="0.2" data-trig-sf="${escapeHtml(pathStr)}:biometric_grace_s" value="${Number(sf.biometric_grace_s ?? 1.2)}" />
          </label>
          ${
            plateMode === 'include' || plateMode === 'exclude'
              ? `<div class="auto-field span-2">
                   <span>Targhe (${plateMode === 'include' ? 'incluse' : 'escluse'})</span>
                   ${savedPlateChips ? `<div class="auto-chips-wrap">${savedPlateChips}</div>` : ''}
                   <input type="text" data-trig-sf="${escapeHtml(pathStr)}:plates" value="${escapeHtml(selectedPlates.join(', '))}" placeholder="Es. AB123CD" />
                 </div>`
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
            <select class="auto-cond-op-select" data-cond-type-path="${escapeHtml(pathStr)}">
              <option value="and" ${cType === 'and' ? 'selected' : ''}>AND · Tutte vere</option>
              <option value="or" ${cType === 'or' ? 'selected' : ''}>OR · Almeno una vera</option>
              <option value="not" ${cType === 'not' ? 'selected' : ''}>NOT · Inverti</option>
              <option value="xor" ${cType === 'xor' ? 'selected' : ''}>XOR · Solo una vera</option>
            </select>
            <div class="auto-cond-actions">
              <button type="button" class="auto-btn tonal xs" data-cond-add-leaf="${escapeHtml(pathStr)}">
                ${icon('plus', { size: 11 })} <span>Condizione</span>
              </button>
              <button type="button" class="auto-btn ghost xs" data-cond-add-group="${escapeHtml(pathStr)}">
                ${icon('plus', { size: 11 })} <span>Gruppo</span>
              </button>
              ${
                !isRoot
                  ? `<button type="button" class="auto-btn icon-only danger xs" data-cond-del-path="${escapeHtml(pathStr)}" title="Rimuovi gruppo">
                       ${icon('x', { size: 12 })}
                     </button>`
                  : ''
              }
            </div>
          </div>
          <div class="auto-cond-children">
            ${
              children.length === 0
                ? `<div class="auto-cond-empty">Nessun vincolo aggiuntivo (sempre verificata).</div>`
                : children.map((ch, idx) => this._renderConditionNodeHtml(ch, `${pathStr}.${idx}`, false)).join('')
            }
          </div>
        </div>
      `;
    }

    const p = node.params || {};
    const polygonOptions = this.zones
      .filter((z) => z.geometry_type === 'polygon')
      .map((z) => `<option value="${escapeHtml(z.zone_id)}" ${p.zone_id === z.zone_id ? 'selected' : ''}>${escapeHtml(z.name)}</option>`)
      .join('');

    let leafFields = '';
    if (cType === 'entity_state') {
      leafFields = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Entità (<code>sh3d.*</code> o Home Assistant)</span>
            <input type="text" list="auto-all-entities-datalist" data-cond-param="${escapeHtml(pathStr)}:entity_id" value="${escapeHtml(p.entity_id || 'sh3d.allarme_perimetrale')}" />
          </label>
          <label class="auto-field">
            <span>Confronto</span>
            <select data-cond-param="${escapeHtml(pathStr)}:operator">
              <option value="==" ${(!p.operator || p.operator === '==') ? 'selected' : ''}>Uguale (=)</option>
              <option value="!=" ${p.operator === '!=' ? 'selected' : ''}>Diverso (≠)</option>
              <option value=">" ${p.operator === '>' ? 'selected' : ''}>Maggiore (&gt;)</option>
              <option value=">=" ${p.operator === '>=' ? 'selected' : ''}>Maggiore o uguale (≥)</option>
              <option value="<" ${p.operator === '<' ? 'selected' : ''}>Minore (&lt;)</option>
              <option value="in" ${p.operator === 'in' ? 'selected' : ''}>In lista (a, b)</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Valore</span>
            <input type="text" data-cond-param="${escapeHtml(pathStr)}:value" value="${escapeHtml(p.value ?? 'on')}" />
          </label>
        </div>
      `;
    } else if (cType === 'time_window') {
      leafFields = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Dalle ore</span>
            <input type="time" data-cond-param="${escapeHtml(pathStr)}:after_hhmm" value="${escapeHtml(p.after_hhmm || '')}" />
          </label>
          <label class="auto-field">
            <span>Alle ore</span>
            <input type="time" data-cond-param="${escapeHtml(pathStr)}:before_hhmm" value="${escapeHtml(p.before_hhmm || '')}" />
          </label>
          <label class="auto-field span-2">
            <span>Sole</span>
            <select data-cond-param="${escapeHtml(pathStr)}:sun_state">
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
            <select data-cond-param="${escapeHtml(pathStr)}:zone_id">
              <option value="">Seleziona area...</option>
              ${polygonOptions}
            </select>
          </label>
          <label class="auto-field">
            <span>Confronto presenti</span>
            <select data-cond-param="${escapeHtml(pathStr)}:operator">
              <option value=">=" ${(!p.operator || p.operator === '>=') ? 'selected' : ''}>Almeno (≥)</option>
              <option value="==" ${p.operator === '==' ? 'selected' : ''}>Esattamente (=)</option>
              <option value="<=" ${p.operator === '<=' ? 'selected' : ''}>Al massimo (≤)</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Numero soggetti</span>
            <input type="number" min="0" max="50" step="1" data-cond-param="${escapeHtml(pathStr)}:count" value="${Number(p.count ?? 1)}" />
          </label>
        </div>
      `;
    } else if (cType === 'track_kinematics') {
      const evalMode = p.evaluation_mode || 'mean';
      leafFields = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Modalità velocità</span>
            <select data-cond-param="${escapeHtml(pathStr)}:evaluation_mode">
              <option value="mean" ${evalMode === 'mean' ? 'selected' : ''}>Media nella finestra</option>
              <option value="peak_in_window" ${evalMode === 'peak_in_window' ? 'selected' : ''}>Picco nella finestra (lookback)</option>
              <option value="min_in_window" ${evalMode === 'min_in_window' ? 'selected' : ''}>Minimo nella finestra</option>
              <option value="current" ${evalMode === 'current' ? 'selected' : ''}>Istantanea attuale</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Finestra (s)</span>
            <input type="number" min="0.5" max="120" step="0.5" data-cond-param="${escapeHtml(pathStr)}:window_s" value="${Number(p.window_s ?? 2)}" />
          </label>
          <label class="auto-field">
            <span>Vel. min (m/s)</span>
            <input type="number" min="0" max="35" step="0.1" placeholder="Qualsiasi" data-cond-param="${escapeHtml(pathStr)}:min_speed_mps" value="${p.min_speed_mps ?? ''}" />
          </label>
          <label class="auto-field">
            <span>Vel. max (m/s)</span>
            <input type="number" min="0" max="35" step="0.1" placeholder="Illimitata" data-cond-param="${escapeHtml(pathStr)}:max_speed_mps" value="${p.max_speed_mps ?? ''}" />
          </label>
          <label class="auto-field">
            <span>Azimut (°)</span>
            <input type="number" min="0" max="359" step="5" placeholder="Qualsiasi" data-cond-param="${escapeHtml(pathStr)}:target_azimuth_deg" value="${p.target_azimuth_deg ?? ''}" />
          </label>
          <label class="auto-field">
            <span>Tolleranza (±°)</span>
            <input type="number" min="5" max="180" step="5" data-cond-param="${escapeHtml(pathStr)}:azimuth_tolerance_deg" value="${Number(p.azimuth_tolerance_deg ?? 35)}" />
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
            <select data-cond-param="${escapeHtml(pathStr)}:target">
              <option value="trigger_track" ${(!p.target || p.target === 'trigger_track') ? 'selected' : ''}>Soggetto del trigger</option>
              <option value="any_active" ${p.target === 'any_active' ? 'selected' : ''}>Almeno un soggetto attivo</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Soggetto</span>
            <select data-cond-param="${escapeHtml(pathStr)}:classes">
              <option value="any" ${curCls === 'any' ? 'selected' : ''}>Qualsiasi</option>
              <option value="person" ${curCls === 'person' ? 'selected' : ''}>Persone</option>
              <option value="vehicle" ${curCls === 'vehicle' ? 'selected' : ''}>Veicoli</option>
              <option value="dog" ${curCls === 'dog' ? 'selected' : ''}>Animali</option>
              <option value="bicycle" ${curCls === 'bicycle' ? 'selected' : ''}>Biciclette</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Filtro volto</span>
            <select data-cond-param="${escapeHtml(pathStr)}:face_mode">
              <option value="any" ${fMode === 'any' ? 'selected' : ''}>Chiunque</option>
              <option value="unknown" ${fMode === 'unknown' ? 'selected' : ''}>Solo sconosciuti</option>
              <option value="known" ${fMode === 'known' ? 'selected' : ''}>Volti registrati</option>
              <option value="include" ${fMode === 'include' ? 'selected' : ''}>Solo specifici...</option>
              <option value="exclude" ${fMode === 'exclude' ? 'selected' : ''}>Escludi specifici...</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Filtro targa</span>
            <select data-cond-param="${escapeHtml(pathStr)}:plate_mode">
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
                   <input type="text" data-cond-param="${escapeHtml(pathStr)}:identities" value="${escapeHtml(idsList.join(', '))}" placeholder="Nicola, Maria" />
                 </label>`
              : ''
          }
          ${
            pMode === 'include' || pMode === 'exclude'
              ? `<label class="auto-field span-2">
                   <span>Targhe (separate da virgola)</span>
                   <input type="text" data-cond-param="${escapeHtml(pathStr)}:plates" value="${escapeHtml(platesList.join(', '))}" placeholder="AB123CD" />
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
            <select data-cond-param="${escapeHtml(pathStr)}:importance">
              <option value="any" ${(!p.importance || p.importance === 'any') ? 'selected' : ''}>Qualsiasi</option>
              <option value="alert" ${p.importance === 'alert' ? 'selected' : ''}>Allerta</option>
              <option value="notable" ${p.importance === 'notable' ? 'selected' : ''}>Rilevante</option>
              <option value="routine" ${p.importance === 'routine' ? 'selected' : ''}>Routine</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Soggetti minimi</span>
            <input type="number" min="0" max="20" step="1" data-cond-param="${escapeHtml(pathStr)}:min_subjects" value="${p.min_subjects ?? ''}" placeholder="Qualsiasi" />
          </label>
          <label class="auto-field">
            <span>Sconosciuti presenti</span>
            <select data-cond-param="${escapeHtml(pathStr)}:has_unknown_person">
              <option value="any" ${(!p.has_unknown_person || p.has_unknown_person === 'any') ? 'selected' : ''}>Indifferente</option>
              <option value="yes" ${p.has_unknown_person === 'yes' ? 'selected' : ''}>Sì</option>
              <option value="no" ${p.has_unknown_person === 'no' ? 'selected' : ''}>No</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Targa in whitelist</span>
            <select data-cond-param="${escapeHtml(pathStr)}:has_whitelisted_plate">
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
            <select data-cond-param="${escapeHtml(pathStr)}:zone_id">
              <option value="">Seleziona area...</option>
              ${polygonOptions}
            </select>
          </label>
          <label class="auto-field">
            <span>Entro gli ultimi (s)</span>
            <input type="number" min="0" max="600" step="0.5" data-cond-param="${escapeHtml(pathStr)}:within_s" value="${Number(p.within_s ?? 10)}" />
          </label>
          <label class="auto-field">
            <span>Permanenza min (s)</span>
            <input type="number" min="0" max="600" step="0.5" data-cond-param="${escapeHtml(pathStr)}:min_dwell_s" value="${Number(p.min_dwell_s ?? 0)}" />
          </label>
        </div>
      `;
    }

    return `
      <div class="auto-node-surface is-compact">
        <div class="auto-node-bar">
          <select class="auto-node-type-select" data-cond-type-path="${escapeHtml(pathStr)}">
            <option value="entity_state" ${cType === 'entity_state' ? 'selected' : ''}>Stato entità</option>
            <option value="time_window" ${cType === 'time_window' ? 'selected' : ''}>Fascia oraria / Sole</option>
            <option value="zone_occupancy" ${cType === 'zone_occupancy' ? 'selected' : ''}>Occupazione area 3D</option>
            <option value="track_kinematics" ${cType === 'track_kinematics' ? 'selected' : ''}>Velocità / direzione soggetto</option>
            <option value="subject_filter" ${cType === 'subject_filter' ? 'selected' : ''}>Filtro soggetto / biometria</option>
            <option value="scene_event" ${cType === 'scene_event' ? 'selected' : ''}>Stato episodio scena</option>
            <option value="recent_zone_visit" ${cType === 'recent_zone_visit' ? 'selected' : ''}>Passaggio recente in area 3D</option>
          </select>
          <button type="button" class="auto-btn icon-only danger xs" data-cond-del-path="${escapeHtml(pathStr)}" title="Rimuovi condizione">
            ${icon('x', { size: 12 })}
          </button>
        </div>
        ${leafFields}
      </div>
    `;
  }

  _renderActionItemHtml(act, pathStr) {
    const aType = act.type || 'set_virtual_entity';
    const p = act.params || {};

    const virtualEntityOpts = this.virtualEntities
      .map((ve) => `<option value="${escapeHtml(ve.entity_id)}" ${p.entity_id === ve.entity_id ? 'selected' : ''}>${escapeHtml(ve.name)} (${escapeHtml(ve.entity_id)})</option>`)
      .join('');

    let bodyHtml = '';
    if (aType === 'set_virtual_entity') {
      bodyHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>Entità interna (<code>sh3d.*</code>)</span>
            <select data-act-param="${escapeHtml(pathStr)}:entity_id">
              ${virtualEntityOpts}
            </select>
          </label>
          <label class="auto-field">
            <span>Operazione</span>
            <select data-act-param="${escapeHtml(pathStr)}:operation">
              <option value="turn_on" ${p.operation === 'turn_on' ? 'selected' : ''}>Attiva (ON)</option>
              <option value="turn_off" ${p.operation === 'turn_off' ? 'selected' : ''}>Disattiva (OFF)</option>
              <option value="toggle" ${p.operation === 'toggle' ? 'selected' : ''}>Inverti (Toggle)</option>
              <option value="set" ${p.operation === 'set' ? 'selected' : ''}>Imposta valore</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Valore</span>
            <input type="text" data-act-param="${escapeHtml(pathStr)}:state" value="${escapeHtml(p.state ?? 'on')}" />
          </label>
        </div>
      `;
    } else if (aType === 'call_ha_service') {
      const svcDataStr =
        p.service_data && typeof p.service_data === 'object' && Object.keys(p.service_data).length > 0
          ? JSON.stringify(p.service_data)
          : '';
      bodyHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Servizio HA</span>
            <input type="text" data-act-param="${escapeHtml(pathStr)}:service" value="${escapeHtml(p.service || 'light.turn_on')}" placeholder="light.turn_on" />
          </label>
          <label class="auto-field">
            <span>Entity ID</span>
            <input type="text" list="auto-all-entities-datalist" data-act-param="${escapeHtml(pathStr)}:entity_id" value="${escapeHtml(p.entity_id || 'light.luci_esterne')}" placeholder="light.luci_esterne" />
          </label>
          <label class="auto-field span-2">
            <span>Dati JSON opzionali (<code>service_data</code>)</span>
            <input type="text" data-act-json="${escapeHtml(pathStr)}:service_data" value="${escapeHtml(svcDataStr)}" placeholder='es. {"brightness_pct": 80}' />
          </label>
        </div>
      `;
    } else if (aType === 'send_notification') {
      const mobileTargets = Array.isArray(p.mobile_targets)
        ? p.mobile_targets
        : String(p.mobile_targets || '')
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean);
      const tvTargets = Array.isArray(p.tv_targets)
        ? p.tv_targets
        : String(p.tv_targets || '')
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean);
      const ttsTargets = Array.isArray(p.tts_targets)
        ? p.tts_targets
        : String(p.tts_targets || '')
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean);

      const disc = this.haDiscovery || {};
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
      const ttsListId = `auto-tts-entities-${pathStr.replace(/[^a-zA-Z0-9_-]/g, '_')}`;

      bodyHtml = `
        <div class="auto-notif-builder">
          <div class="auto-grid-2">
            <label class="auto-field">
              <span>Priorità notifica</span>
              <select data-act-param="${escapeHtml(pathStr)}:priority">
                <option value="silent" ${prio === 'silent' ? 'selected' : ''}>Silenziosa (senza suono)</option>
                <option value="normal" ${prio === 'normal' ? 'selected' : ''}>Normale</option>
                <option value="critical" ${prio === 'critical' ? 'selected' : ''}>Critica (bypassa DND)</option>
              </select>
            </label>
            <label class="auto-field">
              <span>Immagine allegata</span>
              <select data-act-param="${escapeHtml(pathStr)}:image_mode">
                <option value="annotated" ${imgMode === 'annotated' ? 'selected' : ''}>Frame migliore + box nomi</option>
                <option value="raw" ${imgMode === 'raw' ? 'selected' : ''}>Frame originale pulito</option>
                <option value="crop" ${imgMode === 'crop' ? 'selected' : ''}>Solo ritaglio volto/targa</option>
                <option value="none" ${imgMode === 'none' ? 'selected' : ''}>Nessuna immagine</option>
              </select>
            </label>
          </div>

          <div class="auto-notif-group">
            <span class="auto-notif-label">Telefoni / Tablet (HA Companion)</span>
            ${renderChips(mobileDisc, mobileTargets, 'mobile_targets', 'service')}
            <input type="text" data-act-list="${escapeHtml(pathStr)}:mobile_targets" value="${escapeHtml(mobileTargets.join(', '))}" placeholder="notify.mobile_app_pixel_8a, notify.mobile_app_..." />
          </div>

          <div class="auto-grid-2">
            <label class="auto-field">
              <span>Testo notifica</span>
              <select data-act-param="${escapeHtml(pathStr)}:message_mode">
                <option value="auto_scene" ${msgMode === 'auto_scene' ? 'selected' : ''}>Frase automatica (persone + targhe)</option>
                <option value="custom" ${msgMode === 'custom' ? 'selected' : ''}>Testo personalizzato</option>
              </select>
            </label>
            <label class="auto-field">
              <span>Luogo (es. al cancelletto)</span>
              <input type="text" data-act-param="${escapeHtml(pathStr)}:location_label" value="${escapeHtml(p.location_label || '')}" placeholder="al cancelletto / in cortile" />
            </label>
            <label class="auto-field">
              <span>Titolo notifica</span>
              <input type="text" data-act-param="${escapeHtml(pathStr)}:title" value="${escapeHtml(p.title || '')}" placeholder="Smart Home 3D" />
            </label>
            <label class="auto-field">
              <span>Tag aggiornamento (vuoto = episodio)</span>
              <input type="text" data-act-param="${escapeHtml(pathStr)}:tag" value="${escapeHtml(p.tag || '')}" placeholder="es. notifica_cancelletto" />
            </label>
            ${
              msgMode === 'custom'
                ? `<label class="auto-field span-2">
                     <span>Messaggio personalizzato (supporta <code>{{ scene.summary }}</code>, <code>{{ track.identity }}</code>)</span>
                     <input type="text" data-act-param="${escapeHtml(pathStr)}:message" value="${escapeHtml(p.message || '')}" placeholder="{{ scene.summary }}" />
                   </label>`
                : ''
            }
          </div>

          <label class="auto-check-row">
            <input type="checkbox" data-act-bool="${escapeHtml(pathStr)}:update_on_biometrics" ${p.update_on_biometrics !== false ? 'checked' : ''} />
            <span>Aggiorna silenziosamente la notifica sul telefono se il volto o la targa vengono riconosciuti dopo</span>
          </label>

          <div class="auto-notif-group">
            <div class="auto-block-header">
              <span class="auto-notif-label">Pulsanti interattivi notifica</span>
              <div class="auto-notif-preset-bar">
                <button type="button" class="auto-btn ghost xs" data-act-notif-btn-preset="${escapeHtml(pathStr)}:gate">+ Apri cancelletto</button>
                <button type="button" class="auto-btn ghost xs" data-act-notif-btn-preset="${escapeHtml(pathStr)}:alarm_off">+ Spento</button>
                <button type="button" class="auto-btn ghost xs" data-act-notif-btn-preset="${escapeHtml(pathStr)}:alarm_silent">+ Silenzioso</button>
                <button type="button" class="auto-btn tonal xs" data-act-notif-btn-add="${escapeHtml(pathStr)}">${icon('plus', { size: 11 })} <span>Pulsante</span></button>
              </div>
            </div>
            <div class="auto-notif-buttons-list">
              ${btnList
                .map(
                  (b, bIdx) => `
                <div class="auto-notif-btn-row">
                  <input type="text" data-act-notif-btn-field="${escapeHtml(pathStr)}:${bIdx}:title" value="${escapeHtml(b.title || '')}" placeholder="Etichetta (es. Apri cancelletto)" />
                  <input type="text" data-act-notif-btn-field="${escapeHtml(pathStr)}:${bIdx}:action" value="${escapeHtml(b.action || '')}" placeholder="Azione (es. SH3D_ALARM_SPENTO o SH3D_CALL_SERVICE:...)" />
                  <button type="button" class="auto-btn icon-only danger xs" data-act-notif-btn-del="${escapeHtml(pathStr)}:${bIdx}" title="Rimuovi pulsante">${icon('x', { size: 12 })}</button>
                </div>
              `
                )
                .join('')}
            </div>
          </div>

          <div class="auto-notif-group">
            <span class="auto-notif-label">Nest Hub / Speaker TTS & Foto</span>
            ${renderChips(mediaPlayersDisc, ttsTargets, 'tts_targets', 'entity_id')}
            <div class="auto-grid-2">
              <label class="auto-field">
                <span>Media Player (separati da virgola)</span>
                <input type="text" data-act-list="${escapeHtml(pathStr)}:tts_targets" value="${escapeHtml(ttsTargets.join(', '))}" placeholder="media_player.nest_hub_cucina" />
              </label>
              <label class="auto-field">
                <span>Motore TTS HA</span>
                <input type="text" list="${ttsListId}" data-act-param="${escapeHtml(pathStr)}:tts_entity" value="${escapeHtml(p.tts_entity || 'tts.google_translate_en_com')}" placeholder="tts.google_translate_en_com" />
                <datalist id="${ttsListId}">
                  ${ttsEntitiesDisc.map((t) => `<option value="${escapeHtml(t.entity_id)}">${escapeHtml(t.name)}</option>`).join('')}
                </datalist>
              </label>
            </div>
            <div class="auto-grid-2">
              <label class="auto-check-row">
                <input type="checkbox" data-act-bool="${escapeHtml(pathStr)}:display_show_image" ${p.display_show_image !== false ? 'checked' : ''} />
                <span>Mostra foto sul display dopo il TTS</span>
              </label>
              <label class="auto-field">
                <span>Durata foto display (sec)</span>
                <input type="number" min="5" max="120" step="1" data-act-param="${escapeHtml(pathStr)}:display_duration_s" value="${Number(p.display_duration_s ?? 25)}" />
              </label>
            </div>
          </div>

          <div class="auto-notif-group">
            <span class="auto-notif-label">TV (LG webOS / Toast)</span>
            ${renderChips(tvDisc, tvTargets, 'tv_targets', 'service')}
            <input type="text" data-act-list="${escapeHtml(pathStr)}:tv_targets" value="${escapeHtml(tvTargets.join(', '))}" placeholder="notify.lg_tv_cucina" />
            <label class="auto-check-row">
              <input type="checkbox" data-act-bool="${escapeHtml(pathStr)}:tv_only_when_on" ${p.tv_only_when_on !== false ? 'checked' : ''} />
              <span>Invia alla TV solo quando è accesa</span>
            </label>
          </div>
        </div>
      `;
    } else if (aType === 'ui_alert') {
      bodyHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Titolo</span>
            <input type="text" data-act-param="${escapeHtml(pathStr)}:title" value="${escapeHtml(p.title || 'Allarme 3D')}" />
          </label>
          <label class="auto-field">
            <span>Livello</span>
            <select data-act-param="${escapeHtml(pathStr)}:severity">
              <option value="critical" ${p.severity === 'critical' ? 'selected' : ''}>Critico + Sirena</option>
              <option value="warning" ${p.severity === 'warning' ? 'selected' : ''}>Avviso</option>
              <option value="info" ${p.severity === 'info' ? 'selected' : ''}>Notifica</option>
            </select>
          </label>
          <label class="auto-field span-2">
            <span>Messaggio (es. <code>{{ track.identity }}</code>, <code>{{ trigger.zone_name }}</code>)</span>
            <input type="text" data-act-param="${escapeHtml(pathStr)}:message" value="${escapeHtml(p.message || '{{ trigger.summary }}')}" />
          </label>
        </div>
      `;
    } else if (aType === 'delay') {
      bodyHtml = `
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>Secondi di attesa</span>
            <input type="number" min="0.5" max="3600" step="0.5" data-act-param="${escapeHtml(pathStr)}:seconds" value="${Number(p.seconds ?? 10)}" />
          </label>
        </div>
      `;
    } else if (aType === 'webhook') {
      bodyHtml = `
        <div class="auto-grid-2">
          <label class="auto-field span-2">
            <span>URL Webhook (HTTP POST)</span>
            <input type="url" data-act-param="${escapeHtml(pathStr)}:url" value="${escapeHtml(p.url || '')}" placeholder="https://..." />
          </label>
        </div>
      `;
    } else if (aType === 'if_then_else') {
      if (!act.if_condition) {
        act.if_condition = {
          condition_id: uid('cnd'),
          type: 'entity_state',
          children: [],
          params: { entity_id: 'sh3d.allarme_perimetrale', operator: '==', value: 'on' },
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
      <div class="auto-node-surface">
        <div class="auto-node-bar">
          <select class="auto-node-type-select" data-act-type-path="${escapeHtml(pathStr)}">
            ${Object.entries(ACTION_TYPE_LABELS)
              .map(([k, label]) => `<option value="${k}" ${aType === k ? 'selected' : ''}>${escapeHtml(label)}</option>`)
              .join('')}
          </select>
          <button type="button" class="auto-btn icon-only danger xs" data-del-act-path="${escapeHtml(pathStr)}" title="Rimuovi azione">
            ${icon('x', { size: 13 })}
          </button>
        </div>
        ${bodyHtml}
      </div>
    `;
  }

  _resolveTrigger(pathStr) {
    const r = this.editingRule;
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

  _bindRuleEditorEvents() {
    const r = this.editingRule;
    if (!r) return;
    this._normalizeEditingRule(r);

    this.panelEl.querySelector('#btn-auto-rule-back')?.addEventListener('click', () => {
      this.editingRule = null;
      this.zoneRenderer?.hideDirectionCone();
      this.render();
    });

    this.panelEl.querySelector('#rule-inp-name')?.addEventListener('input', (e) => {
      r.name = e.target.value;
    });
    this.panelEl.querySelector('#rule-inp-desc')?.addEventListener('input', (e) => {
      r.description = e.target.value;
    });
    this.panelEl.querySelector('#rule-inp-exec-mode')?.addEventListener('change', (e) => {
      r.execution_mode = e.target.value;
    });
    this.panelEl.querySelector('#rule-inp-cooldown')?.addEventListener('input', (e) => {
      r.cooldown_s = Math.max(0, parseFloat(e.target.value) || 0);
    });
    this.panelEl.querySelector('#rule-inp-log-blocked')?.addEventListener('change', (e) => {
      r.log_blocked_evaluations = Boolean(e.target.checked);
    });

    this.panelEl.querySelector('#rule-inp-trigger-logic')?.addEventListener('change', (e) => {
      r.trigger_logic = e.target.value;
      this.render();
    });
    this.panelEl.querySelector('#rule-inp-trigger-window')?.addEventListener('input', (e) => {
      r.trigger_window_s = Math.max(0.5, parseFloat(e.target.value) || 10.0);
    });
    this.panelEl.querySelector('#rule-inp-trigger-corr')?.addEventListener('change', (e) => {
      r.trigger_correlation_scope = e.target.value;
    });

    // Pre-trigger stages controls
    this.panelEl.querySelector('#btn-rule-add-pretrigger')?.addEventListener('click', () => {
      r.pre_triggers.push({
        stage_id: uid('pre'),
        name: `Pre-trigger ${r.pre_triggers.length + 1}`,
        enabled: true,
        match_mode: 'any',
        max_wait_s: 10.0,
        min_delay_s: 0.0,
        stage_window_s: 10.0,
        correlation_scope: 'same_subject',
        consume_on_fire: true,
        refresh_on_rearm: true,
        condition: null,
        triggers: [
          {
            trigger_id: uid('trg'),
            type: 'kinematic_vector',
            enabled: true,
            subject_filter: { classes: ['vehicle'], face_mode: 'any', identities: [], plate_mode: 'any', plates: [], biometric_grace_s: 1.2 },
            params: { zone_id: '', target_azimuth_deg: null, azimuth_tolerance_deg: 35, min_duration_s: 0.5, min_speed_mps: 0.5 },
          },
        ],
      });
      this.render();
    });

    this.panelEl.querySelectorAll('[data-del-pre-idx]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sIdx = Number(btn.dataset.delPreIdx);
        r.pre_triggers.splice(sIdx, 1);
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-pre-field]').forEach((inp) => {
      const handler = () => {
        const lastColon = inp.dataset.preField.lastIndexOf(':');
        const sIdx = Number(inp.dataset.preField.slice(0, lastColon));
        const key = inp.dataset.preField.slice(lastColon + 1);
        const stg = r.pre_triggers[sIdx];
        if (!stg) return;
        let val = inp.value;
        if (inp.type === 'number') {
          val = val === '' ? 0 : parseFloat(val);
        }
        stg[key] = val;
        if (key === 'match_mode') {
          this.render();
        } else if (key === 'max_wait_s') {
          const card = inp.closest('.auto-pretrigger-card');
          const conn = card?.nextElementSibling;
          if (conn && conn.classList.contains('auto-pretrigger-connector')) {
            const nextLabel = sIdx + 1 < r.pre_triggers.length ? `Fase ${sIdx + 2}` : 'Trigger principali';
            conn.textContent = `↓ Attende max ${Number(val || 10)}s → ${nextLabel} ↓`;
          }
        }
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });

    this.panelEl.querySelectorAll('[data-pre-bool]').forEach((chk) => {
      chk.addEventListener('change', () => {
        const lastColon = chk.dataset.preBool.lastIndexOf(':');
        const sIdx = Number(chk.dataset.preBool.slice(0, lastColon));
        const key = chk.dataset.preBool.slice(lastColon + 1);
        const stg = r.pre_triggers[sIdx];
        if (!stg) return;
        stg[key] = Boolean(chk.checked);
      });
    });

    this.panelEl.querySelectorAll('[data-pre-add-trig]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sIdx = Number(btn.dataset.preAddTrig);
        const stg = r.pre_triggers[sIdx];
        if (!stg) return;
        stg.triggers = stg.triggers || [];
        stg.triggers.push({
          trigger_id: uid('trg'),
          type: 'zone_presence',
          enabled: true,
          subject_filter: { classes: ['vehicle'], face_mode: 'any', identities: [], plate_mode: 'any', plates: [], biometric_grace_s: 1.2 },
          params: { zone_id: this.zones[0]?.zone_id || '', event: 'enter', min_dwell_s: 0 },
        });
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-pre-toggle-cond]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sIdx = Number(btn.dataset.preToggleCond);
        const stg = r.pre_triggers[sIdx];
        if (!stg) return;
        if (stg.condition) {
          stg.condition = null;
        } else {
          stg.condition = {
            condition_id: uid('cnd'),
            type: 'and',
            children: [],
            params: {},
          };
        }
        this.render();
      });
    });

    this.panelEl.querySelector('#btn-rule-add-trigger')?.addEventListener('click', () => {
      r.triggers.push({
        trigger_id: uid('trg'),
        type: 'zone_presence',
        enabled: true,
        subject_filter: { classes: ['person'], face_mode: 'any', identities: [], plate_mode: 'any', plates: [], biometric_grace_s: 1.2 },
        params: { zone_id: this.zones[0]?.zone_id || '', event: 'enter', min_dwell_s: 0 },
      });
      this.render();
    });

    this.panelEl.querySelectorAll('[data-del-trig-path]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const { list, idx } = this._resolveTrigger(btn.dataset.delTrigPath);
        if (Array.isArray(list) && idx >= 0) {
          list.splice(idx, 1);
          this.render();
        }
      });
    });

    this.panelEl.querySelectorAll('[data-trig-type-path]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const { trig } = this._resolveTrigger(sel.dataset.trigTypePath);
        if (!trig) return;
        const newType = sel.value;
        trig.type = newType;
        trig.params = this._defaultTriggerParamsForType(newType);
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-trig-param]').forEach((inp) => {
      const handler = () => {
        const lastColon = inp.dataset.trigParam.lastIndexOf(':');
        const pathStr = inp.dataset.trigParam.slice(0, lastColon);
        const key = inp.dataset.trigParam.slice(lastColon + 1);
        const { trig } = this._resolveTrigger(pathStr);
        if (!trig) return;
        let val = inp.value;
        if (inp.type === 'number') {
          val = val === '' ? null : parseFloat(val);
        }
        trig.params = trig.params || {};
        trig.params[key] = val;

        if (key === 'mode') {
          this.render();
        } else if (
          trig.type === 'kinematic_vector' &&
          (key === 'target_azimuth_deg' || key === 'azimuth_tolerance_deg' || key === 'zone_id')
        ) {
          const az = trig.params.target_azimuth_deg;
          if (az === null || az === undefined || az === '') {
            this.zoneRenderer?.hideDirectionCone();
          } else {
            this.zoneRenderer?.showDirectionCone({
              azimuthDeg: az,
              toleranceDeg: trig.params.azimuth_tolerance_deg,
              zoneId: trig.params.zone_id,
            });
          }
        }
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });

    this.panelEl.querySelectorAll('[data-trig-bool]').forEach((chk) => {
      chk.addEventListener('change', () => {
        const lastColon = chk.dataset.trigBool.lastIndexOf(':');
        const pathStr = chk.dataset.trigBool.slice(0, lastColon);
        const key = chk.dataset.trigBool.slice(lastColon + 1);
        const { trig } = this._resolveTrigger(pathStr);
        if (!trig) return;
        trig.params = trig.params || {};
        trig.params[key] = Boolean(chk.checked);
      });
    });

    this.panelEl.querySelectorAll('[data-quick-new-zone]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const gType = btn.dataset.quickNewZone;
        this.activeTab = 'zones';
        this._startNewZoneDraft(gType);
      });
    });

    this.panelEl.querySelectorAll('[data-pick-direction-3d]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const { trig } = this._resolveTrigger(btn.dataset.pickDirection3d);
        if (!trig) return;
        this.setCollapsed(true);
        this.setStatus('Clicca nel 3D il punto di partenza e poi il punto verso cui punta la direzione.', 'info');
        this.zoneRenderer?.startDirectionPicking({
          onDirectionPicked: ({ azimuthDeg }) => {
            trig.params.target_azimuth_deg = azimuthDeg;
            this.setCollapsed(false);
            this.setStatus(`Direzione impostata a ${azimuthDeg}°`, 'success');
            this.render();
          },
        });
      });
    });

    this.panelEl.querySelectorAll('[data-trig-sf]').forEach((inp) => {
      const handler = () => {
        const lastColon = inp.dataset.trigSf.lastIndexOf(':');
        const pathStr = inp.dataset.trigSf.slice(0, lastColon);
        const key = inp.dataset.trigSf.slice(lastColon + 1);
        const { trig } = this._resolveTrigger(pathStr);
        if (!trig) return;
        trig.subject_filter = trig.subject_filter || {};
        if (key === 'classes') {
          trig.subject_filter.classes = inp.value === 'any' ? [] : [inp.value];
        } else if (key === 'identities' || key === 'plates') {
          trig.subject_filter[key] = inp.value
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean);
        } else if (key === 'biometric_grace_s') {
          trig.subject_filter.biometric_grace_s = Math.max(0, parseFloat(inp.value) || 0);
        } else {
          trig.subject_filter[key] = inp.value;
          if (key === 'face_mode' || key === 'plate_mode') {
            this.render();
          }
        }
      };
      inp.addEventListener('change', handler);
      if (inp.tagName === 'INPUT') inp.addEventListener('input', handler);
    });

    this.panelEl.querySelectorAll('[data-trig-id-chip]').forEach((chip) => {
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
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-trig-plate-chip]').forEach((chip) => {
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
        this.render();
      });
    });

    this._bindConditionTreeEvents();
    this._bindActionsTreeEvents();

    this.panelEl.querySelector('#btn-auto-rule-save')?.addEventListener('click', async () => {
      if (!r.name || !r.name.trim()) {
        this.setStatus('Inserisci un nome per la regola.', 'error');
        return;
      }
      const res = await this.spatialStreamClient?.upsertAutomationRule?.(r);
      if (res?.status === 'ok') {
        this.editingRule = null;
        this.zoneRenderer?.hideDirectionCone();
        this.setStatus('Regola salvata.', 'success');
        await this.refreshBootstrapData();
      } else {
        this.setStatus('Errore durante il salvataggio.', 'error');
      }
    });
  }

  _defaultTriggerParamsForType(tType) {
    const firstPoly = this.zones.find((z) => z.geometry_type === 'polygon')?.zone_id || '';
    const firstAny = this.zones[0]?.zone_id || '';
    if (tType === 'zone_presence') return { zone_id: firstPoly, event: 'enter', min_dwell_s: 0 };
    if (tType === 'perimeter_crossing') return { perimeter_id: firstAny, direction: 'a_to_b' };
    if (tType === 'zone_transition') return { from_zone_id: firstPoly, to_zone_id: '', max_transit_s: 20, min_speed_mps: 0 };
    if (tType === 'kinematic_vector') return { zone_id: '', target_azimuth_deg: null, azimuth_tolerance_deg: 35, min_duration_s: 1.0, min_speed_mps: 0.5 };
    if (tType === 'time_schedule') return { mode: 'fixed_time', at: '22:00', offset_minutes: 0 };
    if (tType === 'entity_state_change') return { entity_id: 'sh3d.allarme_perimetrale', from_state: '', to_state: 'on', for_duration_s: 0 };
    if (tType === 'biometric_detection') return { modality: 'any', camera_id: '', zone_id: '', require_locked: true };
    if (tType === 'proximity_3d') return { target_x: 0, target_z: 0, radius_m: 2.0, min_dwell_s: 1.0 };
    if (tType === 'scene_event') return { event: 'started', importance: 'any', zone_id: '', min_subjects: 0 };
    return {};
  }

  _resolveConditionNode(pathStr) {
    if (pathStr.startsWith('pre_cond:')) {
      const sub = pathStr.slice('pre_cond:'.length);
      const parts = sub.split('.');
      const stg = this.editingRule?.pre_triggers?.[Number(parts[0])];
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
    let curr = this.editingRule?.condition;
    let parent = null;
    let lastIdx = -1;
    for (let i = 1; i < parts.length; i++) {
      parent = curr;
      lastIdx = Number(parts[i]);
      curr = curr?.children?.[lastIdx];
    }
    return { node: curr, parent, idx: lastIdx };
  }

  _bindConditionTreeEvents() {
    this.panelEl.querySelectorAll('[data-cond-type-path]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const { node } = this._resolveConditionNode(sel.dataset.condTypePath);
        if (!node) return;
        const nextType = sel.value;
        node.type = nextType;
        if (['and', 'or', 'not', 'xor'].includes(nextType)) {
          node.children = node.children || [];
        } else if (nextType === 'entity_state') {
          node.params = { entity_id: 'sh3d.allarme_perimetrale', operator: '==', value: 'on' };
        } else if (nextType === 'time_window') {
          node.params = { after_hhmm: '', before_hhmm: '', sun_state: 'any' };
        } else if (nextType === 'zone_occupancy') {
          node.params = { zone_id: this.zones[0]?.zone_id || '', operator: '>=', count: 1 };
        } else if (nextType === 'track_kinematics') {
          node.params = { evaluation_mode: 'peak_in_window', window_s: 10.0, min_speed_mps: 0.5, target_azimuth_deg: null, azimuth_tolerance_deg: 35 };
        } else if (nextType === 'subject_filter') {
          node.params = { target: 'trigger_track', classes: [], face_mode: 'any', identities: [], plate_mode: 'any', plates: [] };
        } else if (nextType === 'scene_event') {
          node.params = { importance: 'any', has_unknown_person: 'any', has_whitelisted_plate: 'any' };
        } else if (nextType === 'recent_zone_visit') {
          node.params = { zone_id: this.zones[0]?.zone_id || '', within_s: 10.0, min_dwell_s: 0.0 };
        }
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-cond-add-leaf]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const { node } = this._resolveConditionNode(btn.dataset.condAddLeaf);
        if (!node) return;
        node.children = node.children || [];
        node.children.push({
          condition_id: uid('cnd'),
          type: 'entity_state',
          children: [],
          params: { entity_id: 'sh3d.allarme_perimetrale', operator: '==', value: 'on' },
        });
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-cond-add-group]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const { node } = this._resolveConditionNode(btn.dataset.condAddGroup);
        if (!node) return;
        node.children = node.children || [];
        node.children.push({
          condition_id: uid('cnd'),
          type: 'or',
          children: [],
          params: {},
        });
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-cond-del-path]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const { parent, idx } = this._resolveConditionNode(btn.dataset.condDelPath);
        if (parent && Array.isArray(parent.children) && idx >= 0) {
          parent.children.splice(idx, 1);
          this.render();
        }
      });
    });

    this.panelEl.querySelectorAll('[data-cond-param]').forEach((inp) => {
      const handler = () => {
        const lastColon = inp.dataset.condParam.lastIndexOf(':');
        const pathStr = inp.dataset.condParam.slice(0, lastColon);
        const key = inp.dataset.condParam.slice(lastColon + 1);
        const { node } = this._resolveConditionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        if (node.type === 'subject_filter') {
          if (key === 'classes') {
            node.params.classes = inp.value === 'any' ? [] : [inp.value];
          } else if (key === 'identities' || key === 'plates') {
            node.params[key] = String(inp.value || '')
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean);
          } else {
            node.params[key] = inp.value;
            if (key === 'face_mode' || key === 'plate_mode') {
              this.render();
            }
          }
          return;
        }
        node.params[key] = inp.type === 'number' ? (inp.value === '' ? null : parseFloat(inp.value)) : inp.value;
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });
  }

  _resolveActionListAndIndex(pathStr) {
    const parts = pathStr.split('.');
    let list = this.editingRule?.actions;
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

  _bindActionsTreeEvents() {
    this.panelEl.querySelector('#btn-rule-add-action')?.addEventListener('click', () => {
      this.editingRule.actions.push({
        action_id: uid('act'),
        type: 'call_ha_service',
        params: { service: 'light.turn_on', entity_id: 'light.luci_esterne' },
        then_actions: [],
        else_actions: [],
      });
      this.render();
    });

    this.panelEl.querySelectorAll('[data-act-type-path]').forEach((sel) => {
      sel.addEventListener('change', () => {
        const node = this._resolveActionNode(sel.dataset.actTypePath);
        if (!node) return;
        node.type = sel.value;
        if (node.type === 'set_virtual_entity') {
          node.params = { entity_id: this.virtualEntities[0]?.entity_id || 'sh3d.sirena_allarme', operation: 'turn_on', state: 'on' };
        } else if (node.type === 'call_ha_service') {
          node.params = { service: 'light.turn_on', entity_id: 'light.luci_esterne' };
        } else if (node.type === 'send_notification') {
          node.params = {
            mobile_targets: [],
            tv_targets: [],
            tts_targets: [],
            tts_entity: this.haDiscovery?.tts_entities?.[0]?.entity_id || 'tts.google_translate_en_com',
            priority: 'normal',
            image_mode: 'annotated',
            message_mode: 'auto_scene',
            title: 'Smart Home 3D',
            location_label: '',
            tag: '',
            update_on_biometrics: true,
            display_show_image: true,
            display_duration_s: 25,
            tv_only_when_on: true,
            actions: [],
          };
        } else if (node.type === 'ui_alert') {
          node.params = { title: 'Avviso 3D', message: '{{ trigger.summary }}', severity: 'warning', sound: true };
        } else if (node.type === 'delay') {
          node.params = { seconds: 10 };
        } else if (node.type === 'if_then_else') {
          node.if_condition = node.if_condition || {
            condition_id: uid('cnd'),
            type: 'entity_state',
            children: [],
            params: { entity_id: 'sh3d.allarme_perimetrale', operator: '==', value: 'on' },
          };
          node.then_actions = node.then_actions || [];
          node.else_actions = node.else_actions || [];
        }
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-del-act-path]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const { list, idx } = this._resolveActionListAndIndex(btn.dataset.delActPath);
        if (Array.isArray(list) && idx >= 0) {
          list.splice(idx, 1);
          this.render();
        }
      });
    });

    this.panelEl.querySelectorAll('[data-act-add-sub]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const [pathStr, branch] = btn.dataset.actAddSub.split(':');
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        const targetArr = branch === 'else' ? (node.else_actions = node.else_actions || []) : (node.then_actions = node.then_actions || []);
        targetArr.push({
          action_id: uid('act'),
          type: 'call_ha_service',
          params: { service: 'light.turn_on', entity_id: 'light.luci_esterne' },
          then_actions: [],
          else_actions: [],
        });
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-act-param]').forEach((inp) => {
      const handler = () => {
        const lastColon = inp.dataset.actParam.lastIndexOf(':');
        const pathStr = inp.dataset.actParam.slice(0, lastColon);
        const key = inp.dataset.actParam.slice(lastColon + 1);
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        node.params[key] = inp.type === 'number' ? parseFloat(inp.value) || 0 : inp.value;
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });

    this.panelEl.querySelectorAll('[data-act-bool]').forEach((chk) => {
      chk.addEventListener('change', () => {
        const lastColon = chk.dataset.actBool.lastIndexOf(':');
        const pathStr = chk.dataset.actBool.slice(0, lastColon);
        const key = chk.dataset.actBool.slice(lastColon + 1);
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        node.params[key] = Boolean(chk.checked);
      });
    });

    this.panelEl.querySelectorAll('[data-act-list]').forEach((inp) => {
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
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });

    this.panelEl.querySelectorAll('[data-act-json]').forEach((inp) => {
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
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });

    this.panelEl.querySelectorAll('[data-act-toggle-target]').forEach((btn) => {
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
        if (existingIdx >= 0) {
          arr.splice(existingIdx, 1);
        } else {
          arr.push(targetVal);
        }
        node.params[listKey] = arr;
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-act-notif-btn-add]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const node = this._resolveActionNode(btn.dataset.actNotifBtnAdd);
        if (!node) return;
        node.params = node.params || {};
        node.params.actions = Array.isArray(node.params.actions) ? node.params.actions : [];
        node.params.actions.push({ title: 'Azione', action: 'SH3D_ALARM_SPENTO' });
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-act-notif-btn-preset]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const [pathStr, preset] = btn.dataset.actNotifBtnPreset.split(':');
        const node = this._resolveActionNode(pathStr);
        if (!node) return;
        node.params = node.params || {};
        node.params.actions = Array.isArray(node.params.actions) ? node.params.actions : [];
        const gateCand = this.haDiscovery?.action_entities?.find((e) =>
          String(e.entity_id).includes('cancelletto') || String(e.entity_id).includes('gate')
        )?.entity_id;
        const presetMap = {
          gate: { title: 'Apri cancelletto', action: `SH3D_CALL_SERVICE:switch.turn_on:${gateCand || 'switch.cancelletto'}` },
          alarm_off: { title: 'Allarme Spento', action: 'SH3D_ALARM_SPENTO' },
          alarm_silent: { title: 'Modalità Silenziosa', action: 'SH3D_ALARM_SILENZIOSO' },
        };
        if (presetMap[preset]) {
          node.params.actions.push(presetMap[preset]);
          this.render();
        }
      });
    });

    this.panelEl.querySelectorAll('[data-act-notif-btn-del]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const lastColon = btn.dataset.actNotifBtnDel.lastIndexOf(':');
        const pathStr = btn.dataset.actNotifBtnDel.slice(0, lastColon);
        const idx = parseInt(btn.dataset.actNotifBtnDel.slice(lastColon + 1), 10);
        const node = this._resolveActionNode(pathStr);
        if (!node || !Array.isArray(node.params?.actions) || !Number.isFinite(idx)) return;
        node.params.actions.splice(idx, 1);
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-act-notif-btn-field]').forEach((inp) => {
      const handler = () => {
        const parts = inp.dataset.actNotifBtnField.split(':');
        if (parts.length < 3) return;
        const pathStr = parts[0];
        const idx = parseInt(parts[1], 10);
        const field = parts[2];
        const node = this._resolveActionNode(pathStr);
        if (!node || !Array.isArray(node.params?.actions) || !node.params.actions[idx]) return;
        node.params.actions[idx][field] = inp.value;
      };
      inp.addEventListener('input', handler);
      inp.addEventListener('change', handler);
    });
  }

  // =========================================================================
  // TAB 2: 2.5D POLYGONAL ZONES & ORIENTED PERIMETERS
  // =========================================================================

  _renderZonesList() {
    const itemsHtml =
      this.zones.length === 0
        ? `<div class="auto-empty-state">
             <p class="auto-empty-title">Nessun'area o perimetro salvato</p>
             <span class="auto-empty-sub">Avvia il disegno e clicca direttamente sul terreno della scena 3D per posizionare i vertici.</span>
           </div>`
        : this.zones
            .map((z) => {
              const isPerim = z.geometry_type === 'perimeter';
              return `
                <div class="auto-list-item" data-zone-card="${escapeHtml(z.zone_id)}">
                  <div class="auto-item-main">
                    <div class="auto-item-info">
                      <div class="auto-item-title-row">
                        <span class="auto-color-dot" style="background:${escapeHtml(z.color || '#38bdf8')}"></span>
                        <h4 class="auto-item-title">${escapeHtml(z.name)}</h4>
                      </div>
                      <p class="auto-item-sub">
                        ${isPerim ? 'Perimetro orientato' : 'Area poligonale'} · ${z.vertices?.length || 0} vertici · Y [${z.y_min}..${z.y_max}m]
                      </p>
                    </div>
                  </div>
                  <div class="auto-item-footer">
                    <span class="auto-item-stat">${escapeHtml(z.zone_id)}</span>
                    <div class="auto-item-actions">
                      <button type="button" class="auto-btn ghost xs" data-focus-zone="${escapeHtml(z.zone_id)}">
                        <span>Evidenzia</span>
                      </button>
                      <button type="button" class="auto-btn tonal xs" data-edit-zone="${escapeHtml(z.zone_id)}">
                        <span>Modifica</span>
                      </button>
                      <button type="button" class="auto-btn icon-only danger xs" data-del-zone="${escapeHtml(z.zone_id)}" title="Elimina" aria-label="Elimina">
                        ${icon('x', { size: 13 })}
                      </button>
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

  _startNewZoneDraft(geometryType = 'polygon') {
    const isPerim = geometryType === 'perimeter';
    this.editingZone = {
      zone_id: uid(isPerim ? 'perim' : 'zone'),
      name: isPerim ? 'Nuovo perimetro' : 'Nuova area',
      geometry_type: isPerim ? 'perimeter' : 'polygon',
      vertices: [],
      y_min: -1.5,
      y_max: 4.0,
      normal_flipped: false,
      hysteresis_m: 0.12,
      color: isPerim ? '#f43f5e' : '#38bdf8',
      enabled: true,
    };
    if (typeof window !== 'undefined' && window.innerWidth <= 900) {
      this.isCollapsed = true;
    }
    this._activate3DZoneDrawing();
    this.render();
  }

  _activate3DZoneDrawing() {
    if (!this.editingZone) return;
    this.zoneRenderer?.setZonesVisible(true);
    this.zoneRenderer?.startDrawing({
      geometryType: this.editingZone.geometry_type,
      color: this.editingZone.color,
      normalFlipped: this.editingZone.normal_flipped,
      initialVertices: this.editingZone.vertices,
      onVerticesChanged: (verts) => {
        if (this.editingZone) {
          this.editingZone.vertices = verts;
          const countEl = this.panelEl?.querySelector('#zone-vertices-count');
          if (countEl) countEl.textContent = `${verts.length} vertici posizionati`;
          const collapsedCountEl = this.panelEl?.querySelector('#zone-collapsed-vertices-count');
          if (collapsedCountEl) collapsedCountEl.textContent = `${verts.length} pt`;
        }
      },
    });
  }

  _bindZonesListEvents() {
    this.panelEl.querySelector('#btn-auto-new-polygon')?.addEventListener('click', () => {
      this._startNewZoneDraft('polygon');
    });
    this.panelEl.querySelector('#btn-auto-new-perimeter')?.addEventListener('click', () => {
      this._startNewZoneDraft('perimeter');
    });

    this.panelEl.querySelectorAll('[data-focus-zone]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const zid = btn.dataset.focusZone;
        this.zoneRenderer?.flashZoneAlert(zid, 'warning', 3500);
      });
    });

    this.panelEl.querySelectorAll('[data-edit-zone]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const found = this.zones.find((z) => z.zone_id === btn.dataset.editZone);
        if (found) {
          this.editingZone = JSON.parse(JSON.stringify(found));
          this._activate3DZoneDrawing();
          this.render();
        }
      });
    });

    this.panelEl.querySelectorAll('[data-del-zone]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const zid = btn.dataset.delZone;
        await this.spatialStreamClient?.deleteAutomationZone?.(zid);
        this.setStatus('Geometria eliminata.', 'info');
        await this.refreshBootstrapData();
      });
    });
  }

  _renderZoneEditor() {
    const z = this.editingZone;
    const isPerim = z.geometry_type === 'perimeter';
    const minVerts = isPerim ? 2 : 3;

    return `
      <div class="auto-editor">
        <div class="auto-editor-bar">
          <button type="button" class="auto-btn ghost sm" id="btn-zone-back">
            ${icon('chevron-left', { size: 14 })} <span>Annulla</span>
          </button>
          <button type="button" class="auto-btn primary sm" id="btn-zone-save">
            ${icon('check', { size: 14 })} <span>Salva ${isPerim ? 'perimetro' : 'area'}</span>
          </button>
        </div>

        <div class="auto-draw-callout">
          <div class="auto-draw-callout-head">
            ${icon('crosshair', { size: 15 })}
            <span>Clicca sul terreno 3D per posizionare i vertici</span>
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

        <section class="auto-block">
          <div class="auto-grid-2">
            <label class="auto-field span-2">
              <span>Nome</span>
              <input type="text" id="zone-inp-name" value="${escapeHtml(z.name)}" />
            </label>
            <label class="auto-field">
              <span>Geometria</span>
              <select id="zone-inp-gtype">
                <option value="polygon" ${!isPerim ? 'selected' : ''}>Area poligonale</option>
                <option value="perimeter" ${isPerim ? 'selected' : ''}>Perimetro / linea</option>
              </select>
            </label>
            <label class="auto-field">
              <span>Colore 3D</span>
              <input type="color" id="zone-inp-color" value="${escapeHtml(z.color || '#38bdf8')}" />
            </label>
            <label class="auto-field">
              <span>Quota Y min (m)</span>
              <input type="number" step="0.2" id="zone-inp-ymin" value="${Number(z.y_min ?? -1.5)}" />
            </label>
            <label class="auto-field">
              <span>Quota Y max (m)</span>
              <input type="number" step="0.2" id="zone-inp-ymax" value="${Number(z.y_max ?? 4.0)}" />
            </label>
          </div>
        </section>
      </div>
    `;
  }

  _bindZoneEditorEvents() {
    const z = this.editingZone;
    if (!z) return;

    this.panelEl.querySelector('#btn-zone-back')?.addEventListener('click', () => {
      this.zoneRenderer?.stopDrawing();
      this.editingZone = null;
      this.render();
    });

    this.panelEl.querySelector('#zone-inp-name')?.addEventListener('input', (e) => {
      z.name = e.target.value;
    });
    this.panelEl.querySelector('#zone-inp-gtype')?.addEventListener('change', (e) => {
      z.geometry_type = e.target.value;
      this._activate3DZoneDrawing();
      this.render();
    });
    this.panelEl.querySelector('#zone-inp-color')?.addEventListener('input', (e) => {
      z.color = e.target.value;
      if (this.zoneRenderer) {
        this.zoneRenderer.draftColor = z.color;
        this.zoneRenderer.rebuildDraftVisual();
      }
    });
    this.panelEl.querySelector('#zone-inp-ymin')?.addEventListener('input', (e) => {
      z.y_min = parseFloat(e.target.value) || -2.0;
    });
    this.panelEl.querySelector('#zone-inp-ymax')?.addEventListener('input', (e) => {
      z.y_max = parseFloat(e.target.value) || 4.5;
    });

    this.panelEl.querySelector('#btn-zone-collapse-to-draw')?.addEventListener('click', () => {
      this.setCollapsed(true);
    });
    this.panelEl.querySelector('#btn-zone-undo-vertex')?.addEventListener('click', () => {
      this.zoneRenderer?.undoLastDraftVertex();
    });
    this.panelEl.querySelector('#btn-zone-clear-vertices')?.addEventListener('click', () => {
      this.zoneRenderer?.clearDraftVertices();
    });
    this.panelEl.querySelector('#btn-zone-flip-normal')?.addEventListener('click', () => {
      z.normal_flipped = !z.normal_flipped;
      if (this.zoneRenderer) {
        this.zoneRenderer.draftNormalFlipped = z.normal_flipped;
        this.zoneRenderer.rebuildDraftVisual();
      }
    });

    this.panelEl.querySelector('#btn-zone-save')?.addEventListener('click', () => {
      this._saveEditingZone();
    });
  }

  async _saveEditingZone() {
    const z = this.editingZone;
    if (!z) return;
    const minV = z.geometry_type === 'perimeter' ? 2 : 3;
    if (!Array.isArray(z.vertices) || z.vertices.length < minV) {
      this.setCollapsed(false);
      this.setStatus(`Posiziona almeno ${minV} vertici nel modello 3D.`, 'error');
      return;
    }
    const res = await this.spatialStreamClient?.upsertAutomationZone?.(z);
    if (res?.status === 'ok') {
      this.zoneRenderer?.stopDrawing();
      this.editingZone = null;
      this.setCollapsed(false);
      this.setStatus('Geometria 3D salvata.', 'success');
      await this.refreshBootstrapData();
    } else {
      this.setCollapsed(false);
      this.setStatus('Errore durante il salvataggio.', 'error');
    }
  }

  // =========================================================================
  // TAB 3: INTERNAL PROGRAM VIRTUAL ENTITIES (sh3d.*)
  // =========================================================================

  _parseOptionsText(raw) {
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

  _renderVirtualEntitiesTab() {
    const draft = this.newEntityDraft || {
      entity_id: '',
      name: '',
      domain: 'switch',
      state: 'off',
      optionsText: 'Spento, Silenzioso, Acceso',
    };
    const draftDomain = draft.domain || 'switch';
    const parsedOptions = this._parseOptionsText(draft.optionsText);
    const effectiveOptions = parsedOptions.length > 0 ? parsedOptions : ['opzione_1', 'opzione_2'];
    const selectedInitialState =
      draftDomain === 'select'
        ? (effectiveOptions.includes(draft.state) ? draft.state : effectiveOptions[0])
        : draftDomain === 'switch'
          ? (String(draft.state).toLowerCase() === 'on' ? 'on' : 'off')
          : (draft.state ?? '');

    const rowsHtml = this.virtualEntities
      .map((ve) => {
        const isSwitch = ve.domain === 'switch' || ve.domain === 'boolean';
        const isSelect = ve.domain === 'select' && Array.isArray(ve.options) && ve.options.length > 0;
        const isOn = String(ve.state).toLowerCase() === 'on';

        let controlHtml = '';
        if (isSwitch) {
          controlHtml = `
            <button type="button" class="auto-btn ${isOn ? 'primary' : 'tonal'} xs" data-ve-toggle="${escapeHtml(ve.entity_id)}">
              <span>${isOn ? 'ON' : 'OFF'}</span>
            </button>
          `;
        } else if (isSelect) {
          controlHtml = `
            <select class="auto-ve-inline-select" data-ve-select="${escapeHtml(ve.entity_id)}">
              ${ve.options.map((opt) => `<option value="${escapeHtml(opt)}" ${ve.state === opt ? 'selected' : ''}>${escapeHtml(opt)}</option>`).join('')}
            </select>
          `;
        } else {
          controlHtml = `
            <div class="auto-input-with-btn">
              <input type="text" class="auto-ve-inline-input" data-ve-val-inp="${escapeHtml(ve.entity_id)}" value="${escapeHtml(ve.state)}" />
              <button type="button" class="auto-btn tonal xs" data-ve-set-btn="${escapeHtml(ve.entity_id)}">OK</button>
            </div>
          `;
        }

        return `
          <div class="auto-list-item">
            <div class="auto-item-main">
              <div class="auto-item-info">
                <div class="auto-item-title-row">
                  <span class="auto-status-dot ${isOn ? 'on' : 'off'}"></span>
                  <h4 class="auto-item-title">${escapeHtml(ve.name)}</h4>
                </div>
                <code class="auto-entity-code">${escapeHtml(ve.entity_id)}</code>
              </div>
              <div class="auto-item-actions">
                ${controlHtml}
                <button type="button" class="auto-btn icon-only ghost xs" data-ve-edit="${escapeHtml(ve.entity_id)}" title="Modifica entità">
                  ${icon('sliders-horizontal', { size: 12 })}
                </button>
                <button type="button" class="auto-btn icon-only danger xs" data-ve-del="${escapeHtml(ve.entity_id)}" title="Elimina entità">
                  ${icon('x', { size: 13 })}
                </button>
              </div>
            </div>
          </div>
        `;
      })
      .join('');

    let initialStateControlHtml = '';
    if (draftDomain === 'switch') {
      initialStateControlHtml = `
        <select id="ve-new-state">
          <option value="off" ${selectedInitialState === 'off' ? 'selected' : ''}>off</option>
          <option value="on" ${selectedInitialState === 'on' ? 'selected' : ''}>on</option>
        </select>
      `;
    } else if (draftDomain === 'select') {
      initialStateControlHtml = `
        <select id="ve-new-state">
          ${effectiveOptions.map((opt) => `<option value="${escapeHtml(opt)}" ${selectedInitialState === opt ? 'selected' : ''}>${escapeHtml(opt)}</option>`).join('')}
        </select>
      `;
    } else if (draftDomain === 'number') {
      initialStateControlHtml = `<input type="number" step="any" id="ve-new-state" value="${escapeHtml(selectedInitialState || '0')}" />`;
    } else {
      initialStateControlHtml = `<input type="text" id="ve-new-state" value="${escapeHtml(selectedInitialState)}" placeholder="Valore iniziale" />`;
    }

    return `
      <section class="auto-block is-first">
        <div class="auto-block-header">
          <h3 class="auto-block-title">Nuova o modifica entità (sh3d.*)</h3>
        </div>
        <div class="auto-grid-2">
          <label class="auto-field">
            <span>ID entità</span>
            <input type="text" id="ve-new-id" value="${escapeHtml(draft.entity_id)}" placeholder="sh3d.allarme_notte" />
          </label>
          <label class="auto-field">
            <span>Nome</span>
            <input type="text" id="ve-new-name" value="${escapeHtml(draft.name)}" placeholder="Allarme Notturno" />
          </label>
          <label class="auto-field">
            <span>Tipo</span>
            <select id="ve-new-domain">
              <option value="switch" ${draftDomain === 'switch' ? 'selected' : ''}>Interruttore ON/OFF</option>
              <option value="select" ${draftDomain === 'select' ? 'selected' : ''}>Selettore modalità</option>
              <option value="number" ${draftDomain === 'number' ? 'selected' : ''}>Valore numerico</option>
              <option value="sensor" ${draftDomain === 'sensor' ? 'selected' : ''}>Testo / stato</option>
            </select>
          </label>
          <label class="auto-field">
            <span>Stato iniziale</span>
            ${initialStateControlHtml}
          </label>
          ${
            draftDomain === 'select'
              ? `<label class="auto-field span-2">
                   <span>Stati possibili (separati da virgola)</span>
                   <input type="text" id="ve-new-options" value="${escapeHtml(draft.optionsText)}" placeholder="es. Spento, Silenzioso, Acceso" />
                 </label>`
              : ''
          }
        </div>
        <button type="button" class="auto-btn tonal sm full" id="btn-ve-create">
          ${icon('plus', { size: 14 })} <span>Salva entità</span>
        </button>
      </section>

      <div class="auto-list">
        ${rowsHtml}
      </div>
    `;
  }

  _bindVirtualEntitiesEvents() {
    const draft = this.newEntityDraft;
    const idInp = this.panelEl.querySelector('#ve-new-id');
    const nameInp = this.panelEl.querySelector('#ve-new-name');
    const domainSel = this.panelEl.querySelector('#ve-new-domain');
    const stateInp = this.panelEl.querySelector('#ve-new-state');
    const optionsInp = this.panelEl.querySelector('#ve-new-options');

    idInp?.addEventListener('input', (e) => {
      draft.entity_id = e.target.value;
    });
    nameInp?.addEventListener('input', (e) => {
      draft.name = e.target.value;
    });
    stateInp?.addEventListener('input', (e) => {
      draft.state = e.target.value;
    });
    stateInp?.addEventListener('change', (e) => {
      draft.state = e.target.value;
    });

    domainSel?.addEventListener('change', (e) => {
      const nextDomain = e.target.value;
      draft.domain = nextDomain;
      if (nextDomain === 'switch') {
        draft.state = 'off';
      } else if (nextDomain === 'select') {
        const opts = this._parseOptionsText(draft.optionsText);
        if (opts.length === 0) {
          draft.optionsText = 'Spento, Silenzioso, Acceso';
          draft.state = 'Spento';
        } else if (!opts.includes(draft.state)) {
          draft.state = opts[0];
        }
      } else if (nextDomain === 'number') {
        draft.state = Number.isFinite(Number(draft.state)) && draft.state !== '' ? draft.state : '0';
      }
      this.render();
    });

    optionsInp?.addEventListener('input', (e) => {
      draft.optionsText = e.target.value;
      const opts = this._parseOptionsText(draft.optionsText);
      const stateSelectEl = this.panelEl.querySelector('#ve-new-state');
      if (stateSelectEl && stateSelectEl.tagName === 'SELECT') {
        const effective = opts.length > 0 ? opts : ['opzione_1', 'opzione_2'];
        if (!effective.includes(draft.state)) {
          draft.state = effective[0];
        }
        stateSelectEl.innerHTML = effective
          .map((opt) => `<option value="${escapeHtml(opt)}" ${draft.state === opt ? 'selected' : ''}>${escapeHtml(opt)}</option>`)
          .join('');
      }
    });

    this.panelEl.querySelector('#btn-ve-create')?.addEventListener('click', async () => {
      const rawId = (draft.entity_id || '').trim();
      const rawName = (draft.name || '').trim();
      const domain = draft.domain || 'switch';
      let state = String(draft.state ?? '').trim();
      let options = [];

      if (!rawId || !rawName) {
        this.setStatus('Specifica ID e nome per la nuova entità.', 'error');
        return;
      }

      if (domain === 'select') {
        options = this._parseOptionsText(draft.optionsText);
        if (options.length < 2) {
          this.setStatus('Inserisci almeno 2 stati possibili separati da virgola per il selettore.', 'error');
          return;
        }
        if (!state || !options.includes(state)) {
          state = options[0];
        }
      } else if (!state) {
        state = domain === 'number' ? '0' : 'off';
      }

      const res = await this.spatialStreamClient?.upsertVirtualEntity?.({
        entity_id: rawId,
        name: rawName,
        domain,
        state,
        options,
      });
      if (res?.status === 'ok') {
        this.newEntityDraft = {
          entity_id: '',
          name: '',
          domain: 'switch',
          state: 'off',
          optionsText: 'disarmed, armed_home, armed_away',
        };
        this.setStatus(`Entità ${res.entity.entity_id} salvata.`, 'success');
        await this.refreshBootstrapData();
      } else {
        this.setStatus('Errore durante il salvataggio dell\'entità.', 'error');
      }
    });

    this.panelEl.querySelectorAll('[data-ve-edit]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const eid = btn.dataset.veEdit;
        const found = this.virtualEntities.find((e) => e.entity_id === eid);
        if (!found) return;
        this.newEntityDraft = {
          entity_id: found.entity_id,
          name: found.name,
          domain: found.domain === 'boolean' ? 'switch' : (found.domain || 'switch'),
          state: String(found.state ?? ''),
          optionsText: Array.isArray(found.options) && found.options.length > 0
            ? found.options.join(', ')
            : 'disarmed, armed_home, armed_away',
        };
        this.render();
      });
    });

    this.panelEl.querySelectorAll('[data-ve-toggle]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const eid = btn.dataset.veToggle;
        await this.spatialStreamClient?.setVirtualEntityState?.(eid, { operation: 'toggle' });
        await this.refreshBootstrapData();
      });
    });

    this.panelEl.querySelectorAll('[data-ve-select]').forEach((sel) => {
      sel.addEventListener('change', async () => {
        const eid = sel.dataset.veSelect;
        await this.spatialStreamClient?.setVirtualEntityState?.(eid, { state: sel.value, operation: 'set' });
        await this.refreshBootstrapData();
      });
    });

    this.panelEl.querySelectorAll('[data-ve-set-btn]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const eid = btn.dataset.veSetBtn;
        const inp = this.panelEl.querySelector(`[data-ve-val-inp="${eid}"]`);
        if (!inp) return;
        await this.spatialStreamClient?.setVirtualEntityState?.(eid, { state: inp.value, operation: 'set' });
        await this.refreshBootstrapData();
      });
    });

    this.panelEl.querySelectorAll('[data-ve-del]').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const eid = btn.dataset.veDel;
        await this.spatialStreamClient?.deleteVirtualEntity?.(eid);
        await this.refreshBootstrapData();
      });
    });
  }

  // =========================================================================
  // TAB 4: LIVE EXECUTION LOGS
  // =========================================================================

  _renderLogsTab() {
    const itemsHtml =
      this.logs.length === 0
        ? `<div class="auto-empty-state">
             <p class="auto-empty-title">Nessun evento registrato</p>
             <span class="auto-empty-sub">Le attivazioni delle regole appariranno qui in tempo reale.</span>
           </div>`
        : this.logs
            .map((l) => {
              const dtStr = new Date((l.timestamp || 0) * 1000).toLocaleTimeString('it-IT');
              const actionsCount = Array.isArray(l.actions_executed) ? l.actions_executed.length : 0;
              const statusKey = l.status || 'executed';
              const statusLabel = statusKey === 'condition_blocked' ? 'Bloccata' : statusKey === 'error' ? 'Errore' : 'Eseguita';
              const preSum = l.details?.pre_trigger_summary ? ` · Pre: ${l.details.pre_trigger_summary}` : '';
              return `
                <div class="auto-list-item">
                  <div class="auto-item-main">
                    <div class="auto-item-info">
                      <div class="auto-item-title-row">
                        <span class="auto-log-status-pill is-${escapeHtml(statusKey)}">${statusLabel}</span>
                        <h4 class="auto-item-title">${escapeHtml(l.rule_name)}</h4>
                      </div>
                      <p class="auto-item-sub">${escapeHtml(l.trigger_summary)}</p>
                    </div>
                    <span class="auto-item-time">${escapeHtml(dtStr)}</span>
                  </div>
                  <div class="auto-item-footer">
                    <span class="auto-item-stat">${escapeHtml(l.trigger_type)} · ${actionsCount} azioni${l.identity ? ` · ${escapeHtml(l.identity)}` : ''}${l.plate ? ` · ${escapeHtml(l.plate)}` : ''}${escapeHtml(preSum)}</span>
                  </div>
                </div>
              `;
            })
            .join('');

    return `
      ${
        this.logs.length > 0
          ? `<div class="auto-toolbar-row">
               <button type="button" class="auto-btn ghost xs" id="btn-auto-clear-logs">
                 ${icon('rotate-ccw', { size: 12 })} <span>Svuota registro</span>
               </button>
             </div>`
          : ''
      }
      <div class="auto-list">
        ${itemsHtml}
      </div>
    `;
  }

  _bindLogsEvents() {
    this.panelEl.querySelector('#btn-auto-clear-logs')?.addEventListener('click', async () => {
      await this.spatialStreamClient?.clearAutomationLogs?.();
      this.logs = [];
      this.render();
    });
  }
}
