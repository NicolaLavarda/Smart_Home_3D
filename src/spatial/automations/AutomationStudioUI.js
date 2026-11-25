import { icon } from '../../ui/icons.js';
import {
  DEFAULT_SELECT_OPTIONS_TEXT,
  buildSnapshot,
  createBlankRuleDraft,
  escapeHtml,
  isDirtySnapshot,
  normalizeRule,
  normalizeZone,
  pickDistinctZoneColor,
} from './RuleDraftModel.js';
import { RuleEditorView } from './RuleEditorView.js';
import { ZonesEntitiesLogsViews } from './ZonesEntitiesLogsViews.js';

/**
 * AutomationStudioUI
 *
 * Persistent 3-part spatial automation drawer:
 * - Header (title, sun/draw status, collapse, close) + Segmented Tabs + Status Bar
 * - Scroll-preserving Body (delegates to RuleEditorView & ZonesEntitiesLogsViews)
 * - Sticky Footer (2-step Delete, dirty indicator, Annulla, Primary Save CTA)
 * - 3-way Unsaved-Changes Confirmation Dialog
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
    this.isEditingNewRule = false;
    this.ruleSnapshot = '';

    this.editingZone = null;
    this.isEditingNewZone = false;
    this.zoneSnapshot = '';
    this.pendingZoneReturn = null;

    this.editingEntity = null;
    this.isEditingNewEntity = false;
    this.entitySnapshot = '';
    this._entityIdManuallyEdited = false;

    this.statusMessage = null;
    this._footerConfirmDelete = false;
    this._pendingConfirmAction = null;
    this._openDetailsIds = new Set();

    this.onOpenCallback = null;
    this.onCloseCallback = null;

    this.ruleEditorView = new RuleEditorView(this);
    this.listViews = new ZonesEntitiesLogsViews(this);

    this.zoneRenderer?.setZonesVisible(false);
    this._initDOM();
    this._bindPersistentShellEvents();
    this._bindGlobalListeners();
  }

  get isEditing() {
    return Boolean(this.editingRule || this.editingZone || this.editingEntity);
  }

  setLifecycleHooks({ onOpen, onClose } = {}) {
    this.onOpenCallback = typeof onOpen === 'function' ? onOpen : null;
    this.onCloseCallback = typeof onClose === 'function' ? onClose : null;
  }

  // =========================================================================
  // PERSISTENT SHELL INITIALIZATION
  // =========================================================================

  _initDOM() {
    this.panelEl = document.createElement('section');
    this.panelEl.id = 'sh3d-automation-studio';
    this.panelEl.className = 'auto-studio-drawer';
    this.panelEl.setAttribute('role', 'dialog');
    this.panelEl.setAttribute('aria-label', 'Automazioni');
    this.panelEl.setAttribute('aria-hidden', 'true');
    this.panelEl.hidden = true;

    this.panelEl.innerHTML = `
      <header class="auto-studio-header" id="auto-header-toggle" title="Tocca per ridurre in basso o espandere">
        <div class="auto-header-copy">
          <h2 class="auto-header-title" id="auto-header-title">Automazioni</h2>
          <span class="auto-header-sub" id="auto-header-sub">Aree 3D visibili in scena</span>
        </div>
        <div class="auto-header-actions">
          <button
            type="button"
            class="auto-close-btn auto-collapse-btn"
            id="btn-auto-collapse"
            aria-expanded="true"
            title="Riduci in basso per vedere e toccare il 3D"
            aria-label="Riduci o espandi pannello Automazioni"
          >
            ${icon('chevron-down', { size: 17 })}
          </button>
          <button type="button" class="auto-close-btn" id="btn-auto-close" title="Chiudi Automazioni" aria-label="Chiudi Automazioni">
            ${icon('x', { size: 17 })}
          </button>
        </div>
      </header>

      <div class="auto-collapsed-draw-bar" id="auto-collapsed-draw-bar" hidden>
        <span class="auto-collapsed-draw-count" id="zone-collapsed-vertices-count">0 pt</span>
        <div class="auto-collapsed-draw-actions">
          <button type="button" class="auto-btn ghost xs" id="btn-collapsed-zone-undo" title="Annulla ultimo punto">
            ${icon('rotate-ccw', { size: 12 })} <span>Annulla</span>
          </button>
          <button type="button" class="auto-btn tonal xs" id="btn-collapsed-zone-flip" title="Inverti verso freccia A↔B" hidden>
            ${icon('refresh-cw', { size: 12 })} <span>A↔B</span>
          </button>
          <button type="button" class="auto-btn primary xs" id="btn-collapsed-zone-save">
            ${icon('check', { size: 12 })} <span>Salva</span>
          </button>
        </div>
      </div>

      <div class="auto-tabs-bar" id="auto-tabs-bar">
        <nav class="auto-segmented-tabs" role="tablist" aria-label="Sezioni automazioni">
          <button type="button" class="auto-seg-tab active" data-tab="rules" role="tab" aria-selected="true">
            <span>Regole</span>
            <span class="auto-tab-count" data-tab-count="rules">0</span>
          </button>
          <button type="button" class="auto-seg-tab" data-tab="zones" role="tab" aria-selected="false">
            <span>Aree 3D</span>
            <span class="auto-tab-count" data-tab-count="zones">0</span>
          </button>
          <button type="button" class="auto-seg-tab" data-tab="entities" role="tab" aria-selected="false">
            <span>Entità</span>
            <span class="auto-tab-count" data-tab-count="entities">0</span>
          </button>
          <button type="button" class="auto-seg-tab" data-tab="logs" role="tab" aria-selected="false">
            <span>Attività</span>
            <span class="auto-tab-count" data-tab-count="logs">0</span>
          </button>
        </nav>
      </div>

      <div id="auto-studio-status-bar" class="auto-status-bar info" role="status" aria-live="polite" hidden></div>

      <div class="auto-studio-body" id="auto-studio-body"></div>

      <footer class="auto-footer" id="auto-studio-footer" hidden></footer>

      <div class="sh3d-confirm-backdrop" id="auto-confirm-backdrop" hidden></div>

      <datalist id="auto-all-entities-datalist"></datalist>
      <datalist id="auto-cameras-datalist"></datalist>
    `;

    this.uiLayer.appendChild(this.panelEl);

    this.headerTitleEl = this.panelEl.querySelector('#auto-header-title');
    this.headerSubEl = this.panelEl.querySelector('#auto-header-sub');
    this.collapseBtnEl = this.panelEl.querySelector('#btn-auto-collapse');
    this.collapsedDrawBarEl = this.panelEl.querySelector('#auto-collapsed-draw-bar');
    this.collapsedCountEl = this.panelEl.querySelector('#zone-collapsed-vertices-count');
    this.collapsedFlipBtnEl = this.panelEl.querySelector('#btn-collapsed-zone-flip');
    this.statusBarEl = this.panelEl.querySelector('#auto-studio-status-bar');
    this.bodyEl = this.panelEl.querySelector('#auto-studio-body');
    this.footerEl = this.panelEl.querySelector('#auto-studio-footer');
    this.confirmBackdropEl = this.panelEl.querySelector('#auto-confirm-backdrop');
    this.allEntitiesDatalistEl = this.panelEl.querySelector('#auto-all-entities-datalist');
    this.camerasDatalistEl = this.panelEl.querySelector('#auto-cameras-datalist');

    this.alertBannerEl = document.createElement('div');
    this.alertBannerEl.id = 'sh3d-automation-alert-banner';
    this.alertBannerEl.className = 'auto-live-alert-banner';
    this.alertBannerEl.hidden = true;
    this.uiLayer.appendChild(this.alertBannerEl);
  }

  _bindPersistentShellEvents() {
    this.panelEl.querySelector('#btn-auto-close')?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.close();
    });

    this.collapseBtnEl?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleCollapsed();
    });

    this.panelEl.querySelector('#auto-header-toggle')?.addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      this.toggleCollapsed();
    });

    this.panelEl.querySelector('#btn-collapsed-zone-undo')?.addEventListener('click', () => {
      this.zoneRenderer?.undoLastDraftVertex?.();
    });

    this.panelEl.querySelector('#btn-collapsed-zone-flip')?.addEventListener('click', () => {
      if (!this.editingZone) return;
      this.editingZone.normal_flipped = !this.editingZone.normal_flipped;
      if (this.zoneRenderer) {
        this.zoneRenderer.draftNormalFlipped = this.editingZone.normal_flipped;
        this.zoneRenderer.rebuildDraftVisual?.();
      }
      this._updateDirtyIndicator();
    });

    this.panelEl.querySelector('#btn-collapsed-zone-save')?.addEventListener('click', () => {
      this._saveEditingZone();
    });

    this.panelEl.querySelectorAll('.auto-seg-tab[data-tab]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this._requestSwitchTab(btn.dataset.tab);
      });
    });

    this._onDocumentKeyDown = (e) => {
      if (!this.isOpen || e.key !== 'Escape') return;
      e.preventDefault();
      e.stopPropagation();
      if (this._pendingConfirmAction) {
        this._closeDirtyConfirm();
        return;
      }
      if (this.isEditing) {
        this._requestExitEditor();
        return;
      }
      this.close();
    };
    document.addEventListener('keydown', this._onDocumentKeyDown);
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
        this._refreshDatalists();
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

  // =========================================================================
  // DATA BOOTSTRAP & WEBSOCKET HANDLERS (NEVER CLOBBER ACTIVE EDITORS)
  // =========================================================================

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
      this._updateHeaderChrome();
      this._updateTabsChrome();
      this._refreshDatalists();
      if (!this.isEditing) {
        this.renderBodyPreservingScroll();
      }
    }
  }

  _handleBackendAutomationMessage(msg) {
    if (!msg || typeof msg !== 'object') return;

    if (msg.type === 'automation_zones_updated' && Array.isArray(msg.zones)) {
      this.zones = msg.zones;
      this.zoneRenderer?.setZones(this.zones);
      this.zoneRenderer?.setZonesVisible(this.isOpen);
      if (this.isOpen) {
        this._updateTabsChrome();
        if (!this.isEditing && this.activeTab === 'zones') {
          this.renderBodyPreservingScroll();
        }
      }
      return;
    }

    if (msg.type === 'automation_rules_updated' && Array.isArray(msg.rules)) {
      this.rules = msg.rules;
      if (this.isOpen) {
        this._updateTabsChrome();
        if (!this.isEditing && this.activeTab === 'rules') {
          this.renderBodyPreservingScroll();
        }
      }
      return;
    }

    if (msg.type === 'automation_pretrigger_updated') {
      this.armedStates = Array.isArray(msg.armed_states) ? msg.armed_states : [];
      if (this.isOpen && !this.isEditing && this.activeTab === 'rules') {
        this.renderBodyPreservingScroll();
      }
      return;
    }

    if (msg.type === 'virtual_entity_updated' && msg.entity) {
      const idx = this.virtualEntities.findIndex((e) => e.entity_id === msg.entity.entity_id);
      if (idx >= 0) this.virtualEntities[idx] = msg.entity;
      else this.virtualEntities.push(msg.entity);
      if (this.isOpen) {
        this._updateTabsChrome();
        this._refreshDatalists();
        if (!this.isEditing && this.activeTab === 'entities') {
          this.renderBodyPreservingScroll();
        }
      }
      return;
    }

    if (msg.type === 'virtual_entities_list' && Array.isArray(msg.entities)) {
      this.virtualEntities = msg.entities;
      if (this.isOpen) {
        this._updateTabsChrome();
        this._refreshDatalists();
        if (!this.isEditing && this.activeTab === 'entities') {
          this.renderBodyPreservingScroll();
        }
      }
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
      if (this.isOpen) {
        this._updateTabsChrome();
        if (!this.isEditing && (this.activeTab === 'logs' || this.activeTab === 'rules')) {
          this.renderBodyPreservingScroll();
        }
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

  // =========================================================================
  // LIVE ALERT BANNER & AUDIO
  // =========================================================================

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

  // =========================================================================
  // LIFECYCLE: OPEN, CLOSE, COLLAPSE, STATUS
  // =========================================================================

  async open(initialTab = null) {
    if (initialTab && ['rules', 'zones', 'entities', 'logs'].includes(initialTab)) {
      this.activeTab = initialTab;
    }
    this.isOpen = true;
    this.isCollapsed = false;
    this.panelEl.hidden = false;
    this.panelEl.removeAttribute('aria-hidden');
    this.panelEl.classList.add('open');
    this.panelEl.classList.remove('collapsed');
    this.uiLayer?.classList?.add('studio-open');
    this.zoneRenderer?.setZonesVisible(true);
    this.onOpenCallback?.();
    this.renderBodyPreservingScroll();
    await this.refreshBootstrapData();
  }

  close({ force = false } = {}) {
    if (!this.isOpen) return true;
    if (!force && this.isDirty()) {
      this._openDirtyConfirm({ type: 'close' });
      return false;
    }

    const activeEl = typeof document !== 'undefined' ? document.activeElement : null;
    if (activeEl && this.panelEl.contains(activeEl)) {
      activeEl.blur?.();
    }

    this.isOpen = false;
    this.isCollapsed = false;
    this._clearEditorState();
    this._closeDirtyConfirm();
    this.setStatus(null);

    this.zoneRenderer?.stopDrawing?.();
    this.zoneRenderer?.hideDirectionCone?.();
    this.zoneRenderer?.setHighlightedZone?.(null);
    this.zoneRenderer?.setZonesVisible?.(false);

    this.uiLayer?.classList?.remove('studio-open');
    this.panelEl.classList.remove('open', 'collapsed');
    this.panelEl.hidden = true;
    this.panelEl.setAttribute('aria-hidden', 'true');
    this.onCloseCallback?.();
    return true;
  }

  setCollapsed(collapsed) {
    this.isCollapsed = Boolean(collapsed);
    if (!this.panelEl) return;
    this.panelEl.classList.toggle('collapsed', this.isCollapsed);
    if (this.collapseBtnEl) {
      this.collapseBtnEl.innerHTML = icon(this.isCollapsed ? 'chevron-up' : 'chevron-down', { size: 17 });
      this.collapseBtnEl.title = this.isCollapsed
        ? 'Espandi pannello Automazioni'
        : 'Riduci in basso per vedere e toccare il 3D';
      this.collapseBtnEl.setAttribute('aria-expanded', String(!this.isCollapsed));
    }
  }

  toggleCollapsed() {
    this.setCollapsed(!this.isCollapsed);
  }

  toggle() {
    if (this.isOpen) return this.close();
    return this.open();
  }

  setStatus(text, type = 'info') {
    this.statusMessage = text ? { text, type } : null;
    if (!this.statusBarEl) return;
    if (!this.statusMessage) {
      this.statusBarEl.hidden = true;
      this.statusBarEl.textContent = '';
    } else {
      this.statusBarEl.hidden = false;
      this.statusBarEl.className = `auto-status-bar ${this.statusMessage.type}`;
      this.statusBarEl.textContent = this.statusMessage.text;
    }
  }

  // =========================================================================
  // PERSISTENT SHELL CHROME & SCROLL-PRESERVING RENDER
  // =========================================================================

  render() {
    this.renderBodyPreservingScroll();
  }

  renderBodyPreservingScroll({ scrollToNewSelector = null } = {}) {
    if (!this.isOpen || !this.panelEl || !this.bodyEl) return;

    const prevScrollTop = typeof this.bodyEl.scrollTop === 'number' ? this.bodyEl.scrollTop : 0;

    this.panelEl.classList.toggle('collapsed', this.isCollapsed);
    this._updateHeaderChrome();
    this._updateTabsChrome();
    this._refreshDatalists();

    this.bodyEl.innerHTML = this._renderActiveTabContent();
    this.bodyEl.scrollTop = prevScrollTop;

    this._bindActiveTabEvents();
    this._updateFooterChrome();

    if (scrollToNewSelector) {
      const target = this.bodyEl.querySelector(scrollToNewSelector);
      target?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
    }
  }

  _updateHeaderChrome() {
    if (!this.headerTitleEl || !this.headerSubEl) return;
    const sunLine = this.editingZone
      ? 'Disegno 3D attivo · Tocca il modello 3D per aggiungere punti'
      : this.sunInfo
        ? `Alba ${this.sunInfo.sunrise_hhmm} · Tramonto ${this.sunInfo.sunset_hhmm}`
        : 'Aree 3D visibili in scena';

    this.headerTitleEl.textContent = this.editingZone
      ? (this.editingZone.name || 'Disegno Area 3D')
      : 'Automazioni';
    this.headerSubEl.textContent = sunLine;

    if (this.collapsedDrawBarEl) {
      if (this.editingZone) {
        this.collapsedDrawBarEl.hidden = false;
        if (this.collapsedCountEl) {
          this.collapsedCountEl.textContent = `${this.editingZone.vertices.length} pt`;
        }
        if (this.collapsedFlipBtnEl) {
          this.collapsedFlipBtnEl.hidden = this.editingZone.geometry_type !== 'perimeter';
        }
      } else {
        this.collapsedDrawBarEl.hidden = true;
      }
    }
  }

  _updateTabsChrome() {
    const counts = {
      rules: this.rules.length,
      zones: this.zones.length,
      entities: this.virtualEntities.length,
      logs: this.logs.length,
    };
    this.panelEl.querySelectorAll('.auto-seg-tab[data-tab]').forEach((btn) => {
      const t = btn.dataset.tab;
      const isActive = this.activeTab === t;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', String(isActive));
      const countEl = btn.querySelector(`[data-tab-count="${t}"]`);
      if (countEl) countEl.textContent = String(counts[t] ?? 0);
    });
  }

  _refreshDatalists() {
    if (this.allEntitiesDatalistEl) {
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
      this.allEntitiesDatalistEl.innerHTML = options.join('');
    }
    if (this.camerasDatalistEl) {
      this.camerasDatalistEl.innerHTML = this.cameras
        .map((cam) => `<option value="${escapeHtml(cam)}"></option>`)
        .join('');
    }
  }

  _renderActiveTabContent() {
    if (this.activeTab === 'rules') {
      return this.editingRule ? this.ruleEditorView.render() : this.listViews.renderRulesList();
    }
    if (this.activeTab === 'zones') {
      return this.editingZone ? this.listViews.renderZoneEditor() : this.listViews.renderZonesList();
    }
    if (this.activeTab === 'entities') {
      return this.editingEntity ? this.listViews.renderEntityEditor() : this.listViews.renderEntitiesList();
    }
    return this.listViews.renderLogsTab();
  }

  _bindActiveTabEvents() {
    if (this.activeTab === 'rules') {
      if (this.editingRule) this.ruleEditorView.bindEvents();
      else this.listViews.bindRulesListEvents();
    } else if (this.activeTab === 'zones') {
      if (this.editingZone) this.listViews.bindZoneEditorEvents();
      else this.listViews.bindZonesListEvents();
    } else if (this.activeTab === 'entities') {
      if (this.editingEntity) this.listViews.bindEntityEditorEvents();
      else this.listViews.bindEntitiesListEvents();
    } else if (this.activeTab === 'logs') {
      this.listViews.bindLogsEvents();
    }
  }

  // =========================================================================
  // STICKY FOOTER & DIRTY-STATE MANAGEMENT
  // =========================================================================

  isDirty() {
    if (this.editingRule) return isDirtySnapshot(this.ruleSnapshot, this.editingRule);
    if (this.editingZone) return isDirtySnapshot(this.zoneSnapshot, this.editingZone);
    if (this.editingEntity) return isDirtySnapshot(this.entitySnapshot, this.editingEntity);
    return false;
  }

  _updateDirtyIndicator() {
    const dot = this.footerEl?.querySelector('#auto-dirty-indicator');
    if (dot) {
      dot.hidden = !this.isDirty();
    }
  }

  _updateFooterChrome() {
    if (!this.footerEl) return;
    if (!this.isEditing) {
      this.footerEl.hidden = true;
      this.footerEl.innerHTML = '';
      return;
    }

    this.footerEl.hidden = false;
    const dirty = this.isDirty();

    let saveBtnId = 'btn-auto-rule-save';
    let saveLabel = 'Salva regola';
    let canDelete = !this.isEditingNewRule;

    if (this.editingZone) {
      saveBtnId = 'btn-zone-save';
      saveLabel = this.editingZone.geometry_type === 'perimeter' ? 'Salva perimetro' : 'Salva area';
      canDelete = !this.isEditingNewZone && !this.pendingZoneReturn;
    } else if (this.editingEntity) {
      saveBtnId = 'btn-ve-save';
      saveLabel = 'Salva entità';
      canDelete = !this.isEditingNewEntity;
    }

    const leftHtml = canDelete
      ? this._footerConfirmDelete
        ? `<div class="auto-footer-del-group">
             <button type="button" class="auto-btn danger sm" id="btn-auto-editor-delete-confirm">Conferma elimina</button>
             <button type="button" class="auto-btn ghost sm" id="btn-auto-editor-delete-cancel">Annulla</button>
           </div>`
        : `<button type="button" class="auto-btn danger sm" id="btn-auto-editor-delete" title="Elimina" aria-label="Elimina">
             ${icon('trash-2', { size: 13 })} <span>Elimina</span>
           </button>`
      : `<span class="auto-dirty-pill" id="auto-dirty-indicator" ${dirty ? '' : 'hidden'}>Non salvato</span>`;

    const dirtyRightHtml = canDelete
      ? `<span class="auto-dirty-pill" id="auto-dirty-indicator" ${dirty ? '' : 'hidden'}>Non salvato</span>`
      : '';

    this.footerEl.innerHTML = `
      <div class="auto-footer-left">
        ${leftHtml}
      </div>
      <div class="auto-footer-right">
        ${dirtyRightHtml}
        <button type="button" class="auto-btn ghost sm" id="btn-auto-editor-cancel">Annulla</button>
        <button type="button" class="auto-btn primary sm" id="${saveBtnId}">
          ${icon('check', { size: 14 })} <span>${escapeHtml(saveLabel)}</span>
        </button>
      </div>
    `;

    this.footerEl.querySelector('#btn-auto-editor-cancel')?.addEventListener('click', () => {
      this._requestExitEditor();
    });

    this.footerEl.querySelector('#btn-auto-editor-delete')?.addEventListener('click', () => {
      this._footerConfirmDelete = true;
      this._updateFooterChrome();
    });
    this.footerEl.querySelector('#btn-auto-editor-delete-cancel')?.addEventListener('click', () => {
      this._footerConfirmDelete = false;
      this._updateFooterChrome();
    });
    this.footerEl.querySelector('#btn-auto-editor-delete-confirm')?.addEventListener('click', async () => {
      this._footerConfirmDelete = false;
      await this._deleteCurrentEditorItem();
    });

    this.footerEl.querySelector(`#${saveBtnId}`)?.addEventListener('click', async () => {
      await this._saveCurrentEditor();
    });
  }

  _clearEditorState() {
    this.editingRule = null;
    this.isEditingNewRule = false;
    this.ruleSnapshot = '';

    this.editingZone = null;
    this.isEditingNewZone = false;
    this.zoneSnapshot = '';
    this.pendingZoneReturn = null;

    this.editingEntity = null;
    this.isEditingNewEntity = false;
    this.entitySnapshot = '';
    this._entityIdManuallyEdited = false;

    this._footerConfirmDelete = false;
    this._openDetailsIds.clear();
  }

  _discardCurrentEditor() {
    if (this.editingZone && this.pendingZoneReturn) {
      this.zoneRenderer?.stopDrawing?.();
      this.setCollapsed(false);
      const ret = this.pendingZoneReturn;
      this.pendingZoneReturn = null;
      this.editingZone = null;
      this.isEditingNewZone = false;
      this.zoneSnapshot = '';

      this.editingRule = ret.rule;
      this.ruleSnapshot = ret.snapshot;
      this.isEditingNewRule = ret.isNew;
      this.activeTab = 'rules';
      return;
    }

    this.zoneRenderer?.stopDrawing?.();
    this.zoneRenderer?.hideDirectionCone?.();
    this.setCollapsed(false);
    this._clearEditorState();
  }

  _requestExitEditor() {
    if (!this.isEditing) return;
    if (this.isDirty()) {
      this._openDirtyConfirm({ type: 'exit_editor' });
      return;
    }
    this._discardCurrentEditor();
    this.renderBodyPreservingScroll();
  }

  _requestSwitchTab(targetTab) {
    if (!targetTab) return;
    if (targetTab === this.activeTab && !this.isEditing) return;

    if (this.isEditing && this.isDirty()) {
      this._openDirtyConfirm({ type: 'switch_tab', tab: targetTab });
      return;
    }
    this._executeSwitchTab(targetTab);
  }

  _executeSwitchTab(targetTab) {
    this.zoneRenderer?.stopDrawing?.();
    this.zoneRenderer?.hideDirectionCone?.();
    this.setCollapsed(false);
    this._clearEditorState();
    this.listViews.confirmDeleteKey = null;
    this.setStatus(null);
    this.activeTab = targetTab;
    this.renderBodyPreservingScroll();
  }

  _openDirtyConfirm(pendingAction) {
    if (!this.confirmBackdropEl) return;
    this._pendingConfirmAction = pendingAction;
    this.confirmBackdropEl.hidden = false;
    this.confirmBackdropEl.innerHTML = `
      <div class="sh3d-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="auto-confirm-title" aria-describedby="auto-confirm-msg">
        <h3 class="sh3d-confirm-title" id="auto-confirm-title">Modifiche non salvate</h3>
        <p class="sh3d-confirm-msg" id="auto-confirm-msg">Vuoi salvare le modifiche prima di uscire?</p>
        <div class="sh3d-confirm-actions">
          <button type="button" class="sh3d-confirm-btn primary" id="btn-confirm-save-exit">Salva ed esci</button>
          <button type="button" class="sh3d-confirm-btn danger" id="btn-confirm-discard-exit">Scarta modifiche</button>
          <button type="button" class="sh3d-confirm-btn" id="btn-confirm-continue">Continua a modificare</button>
        </div>
      </div>
    `;

    this.confirmBackdropEl.querySelector('#btn-confirm-save-exit')?.addEventListener('click', async () => {
      const action = this._pendingConfirmAction;
      const saved = await this._saveCurrentEditor();
      if (!saved) {
        this._closeDirtyConfirm();
        return;
      }
      this._closeDirtyConfirm();
      this._applyPendingActionAfterResolution(action);
    });

    this.confirmBackdropEl.querySelector('#btn-confirm-discard-exit')?.addEventListener('click', () => {
      const action = this._pendingConfirmAction;
      this._closeDirtyConfirm();
      this._discardCurrentEditor();
      this._applyPendingActionAfterResolution(action);
    });

    this.confirmBackdropEl.querySelector('#btn-confirm-continue')?.addEventListener('click', () => {
      this._closeDirtyConfirm();
    });

    this.confirmBackdropEl.querySelector('#btn-confirm-continue')?.focus?.();
  }

  _closeDirtyConfirm() {
    this._pendingConfirmAction = null;
    if (this.confirmBackdropEl) {
      this.confirmBackdropEl.hidden = true;
      this.confirmBackdropEl.innerHTML = '';
    }
  }

  _applyPendingActionAfterResolution(action) {
    if (!action) return;
    if (action.type === 'close') {
      this.close({ force: true });
    } else if (action.type === 'switch_tab') {
      this._executeSwitchTab(action.tab);
    } else if (action.type === 'exit_editor') {
      this.renderBodyPreservingScroll();
    }
  }

  // =========================================================================
  // EDITOR ENTRYPOINTS & CRUD HANDLERS
  // =========================================================================

  startNewRule() {
    this._clearEditorState();
    this.activeTab = 'rules';
    this.editingRule = createBlankRuleDraft();
    this.isEditingNewRule = true;
    this.ruleSnapshot = buildSnapshot(this.editingRule);
    this.renderBodyPreservingScroll();
  }

  startEditRule(ruleId) {
    const found = this.rules.find((r) => r.rule_id === ruleId);
    if (!found) return;
    this._clearEditorState();
    this.activeTab = 'rules';
    this.editingRule = normalizeRule(JSON.parse(JSON.stringify(found)));
    this.isEditingNewRule = false;
    this.ruleSnapshot = buildSnapshot(this.editingRule);
    this.renderBodyPreservingScroll();
  }

  _startZoneDraftFromRule({ geometryType = 'polygon', targetPath = 'main:0', targetKey = 'zone_id' } = {}) {
    const ruleStash = {
      rule: this.editingRule,
      snapshot: this.ruleSnapshot,
      isNew: this.isEditingNewRule,
      targetPath,
      targetKey,
    };
    this.editingRule = null;
    this.zoneRenderer?.hideDirectionCone();
    this.pendingZoneReturn = ruleStash;
    this.activeTab = 'zones';
    this._initNewZoneEditor(geometryType);
  }

  startNewZoneDraft(geometryType = 'polygon') {
    this._clearEditorState();
    this.activeTab = 'zones';
    this._initNewZoneEditor(geometryType);
  }

  _initNewZoneEditor(geometryType = 'polygon') {
    const isPerim = geometryType === 'perimeter';
    this.editingZone = normalizeZone(
      {
        name: isPerim ? 'Nuovo perimetro' : 'Nuova area',
        geometry_type: isPerim ? 'perimeter' : 'polygon',
        vertices: [],
        y_min: -1.5,
        y_max: 4.0,
        normal_flipped: false,
        hysteresis_m: 0.12,
        color: pickDistinctZoneColor(this.zones, geometryType),
        enabled: true,
      },
      this.zones
    );
    this.isEditingNewZone = true;
    this.zoneSnapshot = buildSnapshot(this.editingZone);
    if (typeof window !== 'undefined' && window.innerWidth <= 900) {
      this.isCollapsed = true;
    }
    this._activate3DZoneDrawing();
    this.renderBodyPreservingScroll();
  }

  startEditZone(zoneId) {
    const found = this.zones.find((z) => z.zone_id === zoneId);
    if (!found) return;
    this._clearEditorState();
    this.activeTab = 'zones';
    this.editingZone = normalizeZone(JSON.parse(JSON.stringify(found)), this.zones);
    this.isEditingNewZone = false;
    this.zoneSnapshot = buildSnapshot(this.editingZone);
    this._activate3DZoneDrawing();
    this.renderBodyPreservingScroll();
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
          const countEl = this.bodyEl?.querySelector('#zone-vertices-count');
          if (countEl) countEl.textContent = `${verts.length} vertici posizionati`;
          if (this.collapsedCountEl) this.collapsedCountEl.textContent = `${verts.length} pt`;
          this._updateDirtyIndicator();
        }
      },
    });
  }

  startNewEntity() {
    this._clearEditorState();
    this.activeTab = 'entities';
    this.editingEntity = {
      entity_id: '',
      name: '',
      domain: 'switch',
      state: 'off',
      optionsText: DEFAULT_SELECT_OPTIONS_TEXT,
    };
    this.isEditingNewEntity = true;
    this._entityIdManuallyEdited = false;
    this.entitySnapshot = buildSnapshot(this.editingEntity);
    this.renderBodyPreservingScroll();
  }

  startEditEntity(entityId) {
    const found = this.virtualEntities.find((e) => e.entity_id === entityId);
    if (!found) return;
    this._clearEditorState();
    this.activeTab = 'entities';
    this.editingEntity = {
      entity_id: found.entity_id,
      name: found.name,
      domain: found.domain === 'boolean' ? 'switch' : (found.domain || 'switch'),
      state: String(found.state ?? ''),
      optionsText:
        Array.isArray(found.options) && found.options.length > 0
          ? found.options.join(', ')
          : DEFAULT_SELECT_OPTIONS_TEXT,
    };
    this.isEditingNewEntity = false;
    this._entityIdManuallyEdited = true;
    this.entitySnapshot = buildSnapshot(this.editingEntity);
    this.renderBodyPreservingScroll();
  }

  async _saveCurrentEditor() {
    if (this.editingRule) return await this._saveEditingRule();
    if (this.editingZone) return await this._saveEditingZone();
    if (this.editingEntity) return await this._saveEditingEntity();
    return true;
  }

  async _deleteCurrentEditorItem() {
    if (this.editingRule && !this.isEditingNewRule) {
      const id = this.editingRule.rule_id;
      await this.spatialStreamClient?.deleteAutomationRule?.(id);
      this._clearEditorState();
      this.setStatus('Regola eliminata.', 'info');
      await this.refreshBootstrapData();
      this.renderBodyPreservingScroll();
      return;
    }
    if (this.editingZone && !this.isEditingNewZone) {
      const id = this.editingZone.zone_id;
      this.zoneRenderer?.stopDrawing?.();
      await this.spatialStreamClient?.deleteAutomationZone?.(id);
      this._clearEditorState();
      this.setStatus('Geometria eliminata.', 'info');
      await this.refreshBootstrapData();
      this.renderBodyPreservingScroll();
      return;
    }
    if (this.editingEntity && !this.isEditingNewEntity) {
      const id = this.editingEntity.entity_id;
      await this.spatialStreamClient?.deleteVirtualEntity?.(id);
      this._clearEditorState();
      this.setStatus(`Entità ${id} eliminata.`, 'info');
      await this.refreshBootstrapData();
      this.renderBodyPreservingScroll();
    }
  }

  async _saveEditingRule() {
    const r = this.editingRule;
    if (!r) return false;
    if (!r.name || !r.name.trim()) {
      this.setStatus('Inserisci un nome per la regola.', 'error');
      this.bodyEl?.querySelector('#rule-inp-name')?.focus?.();
      return false;
    }
    const res = await this.spatialStreamClient?.upsertAutomationRule?.(r);
    if (res?.status === 'ok') {
      this._clearEditorState();
      this.zoneRenderer?.hideDirectionCone();
      this.setStatus('Regola salvata.', 'success');
      await this.refreshBootstrapData();
      this.renderBodyPreservingScroll();
      return true;
    }
    this.setStatus('Errore durante il salvataggio.', 'error');
    return false;
  }

  async _saveEditingZone() {
    const z = this.editingZone;
    if (!z) return false;
    const minV = z.geometry_type === 'perimeter' ? 2 : 3;
    if (!Array.isArray(z.vertices) || z.vertices.length < minV) {
      this.setCollapsed(false);
      this.setStatus(`Posiziona almeno ${minV} vertici nel modello 3D.`, 'error');
      return false;
    }
    const res = await this.spatialStreamClient?.upsertAutomationZone?.(z);
    if (res?.status === 'ok') {
      const savedId = res.zone?.zone_id || z.zone_id;
      this.zoneRenderer?.stopDrawing?.();
      this.setCollapsed(false);

      if (this.pendingZoneReturn) {
        const ret = this.pendingZoneReturn;
        this.pendingZoneReturn = null;
        this.editingZone = null;
        this.isEditingNewZone = false;
        this.zoneSnapshot = '';

        this.editingRule = ret.rule;
        this.ruleSnapshot = ret.snapshot;
        this.isEditingNewRule = ret.isNew;
        this.activeTab = 'rules';
        const { trig } = this.ruleEditorView._resolveTrigger(ret.targetPath);
        if (trig) {
          trig.params = trig.params || {};
          trig.params[ret.targetKey] = savedId;
        }
        this.setStatus('Geometria 3D salvata e collegata alla regola.', 'success');
        await this.refreshBootstrapData();
        this.renderBodyPreservingScroll();
        return true;
      }

      this._clearEditorState();
      this.setStatus('Geometria 3D salvata.', 'success');
      await this.refreshBootstrapData();
      this.renderBodyPreservingScroll();
      return true;
    }
    this.setCollapsed(false);
    this.setStatus('Errore durante il salvataggio.', 'error');
    return false;
  }

  async _saveEditingEntity() {
    const draft = this.editingEntity;
    if (!draft) return false;
    const rawId = (draft.entity_id || '').trim();
    const rawName = (draft.name || '').trim();
    const domain = draft.domain || 'switch';
    let state = String(draft.state ?? '').trim();
    let options = [];

    if (!rawId || !rawName) {
      this.setStatus('Specifica nome e ID per l’entità.', 'error');
      return false;
    }

    if (domain === 'select') {
      options = this.listViews.parseOptionsText(draft.optionsText);
      if (options.length < 2) {
        this.setStatus('Inserisci almeno 2 stati possibili separati da virgola.', 'error');
        return false;
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
      this._clearEditorState();
      this.setStatus(`Entità ${res.entity?.entity_id || rawId} salvata.`, 'success');
      await this.refreshBootstrapData();
      this.renderBodyPreservingScroll();
      return true;
    }
    this.setStatus('Errore durante il salvataggio dell’entità.', 'error');
    return false;
  }
}
