import { icon } from './icons.js';
import { deviceRegistry } from '../devices/DeviceRegistry.js';

const VIEW_ITEMS = [
  {
    id: 'overview',
    label: 'Panoramica',
    subtitle: 'Vista casa completa',
    icon: 'globe',
    preset: 'overview',
  },
  {
    id: 'topdown',
    label: 'Pianta',
    subtitle: 'Vista zenitale',
    icon: 'map',
    preset: 'topdown',
  },
  {
    id: 'garden',
    label: 'Giardino',
    subtitle: 'Esterni e luci',
    icon: 'trees',
    preset: 'garden',
  },
  {
    id: 'living',
    label: 'Salotto',
    subtitle: 'Zona living',
    icon: 'sofa',
    preset: 'living',
  },
  {
    id: 'dining',
    label: 'Sala da Pranzo',
    subtitle: 'Tavolo e camino',
    icon: 'utensils',
    preset: 'dining',
  },
  {
    id: 'kitchen',
    label: 'Cucina',
    subtitle: 'Isola e piano lavoro',
    icon: 'cooking-pot',
    preset: 'kitchen',
  },
];

const DEVICE_ITEMS = [
  {
    id: 'thermal',
    label: 'Impianto Termico',
    icon: 'flame',
    preset: 'device_thermal',
    entityId: 'switch.smart_switch_caldaia',
    tone: 'warm',
  },
  {
    id: 'irrigation',
    label: 'Irrigazione',
    icon: 'droplets',
    preset: 'device_irrigation',
    entityId: 'input_boolean.irrigazione_attiva',
    tone: 'cyan',
  },
  {
    id: 'tv',
    label: 'TV',
    icon: 'tv',
    preset: 'device_tv',
    entityId: 'media_player.lg_webos_smart_tv',
    tone: 'indigo',
  },
  {
    id: 'dishwasher',
    label: 'Lavastoviglie',
    icon: 'sparkles',
    preset: 'device_dishwasher',
    entityId: 'sensor.lavastoviglie_stato_di_funzionamento',
    tone: 'teal',
  },
  {
    id: 'deebot',
    label: 'Deebot',
    icon: 'bot',
    preset: 'device_deebot',
    entityId: 'vacuum.deebot',
    tone: 'emerald',
  },
];

/**
 * NavigationFabHub
 *
 * Pulsante FAB Material 3 in basso a destra che sostituisce il vecchio pannello
 * "Viste Rapide" in alto a sinistra.
 * Espande un pannello con pulsanti grandi su 2 colonne divisi in 2 sezioni:
 * 1. Viste (Panoramica, Pianta, Giardino, Salotto, Sala da Pranzo, Cucina)
 * 2. Dispositivi & Centri di Controllo (Impianto Termico, Irrigazione, TV, Lavastoviglie, Deebot)
 *    con volo automatico su inquadratura contestuale + apertura immediata del pannello di gestione.
 */
export class NavigationFabHub {
  constructor(domContainer, {
    cameraController,
    deviceModals,
    haClient,
    onOpenChange = null,
  } = {}) {
    this.container = domContainer;
    this.cameraController = cameraController;
    this.deviceModals = deviceModals;
    this.haClient = haClient;
    this.onOpenChange = typeof onOpenChange === 'function' ? onOpenChange : null;

    this.isOpen = false;
    this.activeViewId = 'overview';
    this.activeDeviceId = null;

    this._onDocClick = this._handleDocumentClick.bind(this);
    this._onKeyDown = this._handleKeyDown.bind(this);
    this._unsubscribeEntities = null;

    this.initUI();
    this.bindEvents();
  }

  initUI() {
    if (!this.container) return;

    const viewsHtml = VIEW_ITEMS.map((item) => `
      <button
        type="button"
        class="m3-hub-tile m3-hub-tile-view ${item.id === this.activeViewId ? 'active' : ''}"
        data-hub-view="${item.id}"
        data-preset="${item.preset}"
      >
        <span class="m3-tile-icon">${icon(item.icon, { size: 22 })}</span>
        <span class="m3-tile-copy">
          <span class="m3-tile-title">${item.label}</span>
          <span class="m3-tile-sub">${item.subtitle}</span>
        </span>
      </button>
    `).join('');

    const devicesHtml = DEVICE_ITEMS.map((item) => `
      <button
        type="button"
        class="m3-hub-tile m3-hub-tile-device tone-${item.tone}"
        data-hub-device="${item.id}"
        data-preset="${item.preset}"
        data-entity="${item.entityId}"
      >
        <span class="m3-tile-icon">${icon(item.icon, { size: 22 })}</span>
        <span class="m3-tile-copy">
          <span class="m3-tile-title">${item.label}</span>
          <span class="m3-tile-sub" data-device-status="${item.id}">Apri gestione</span>
        </span>
        <span class="m3-tile-dot" data-device-dot="${item.id}" aria-hidden="true"></span>
      </button>
    `).join('');

    this.container.innerHTML = `
      <div class="m3-nav-sheet" id="m3-nav-sheet" role="dialog" aria-label="Viste e Dispositivi" aria-hidden="true">
        <div class="m3-sheet-header">
          <h2 class="m3-sheet-title">Esplora e Controlla</h2>
          <button type="button" class="m3-icon-btn" id="btn-nav-hub-close" aria-label="Chiudi menu viste e dispositivi">
            ${icon('x', { size: 18 })}
          </button>
        </div>

        <div class="m3-sheet-scroll">
          <section class="m3-hub-section" aria-labelledby="nav-sec-views">
            <h3 class="m3-section-heading" id="nav-sec-views">
              ${icon('compass', { size: 15 })}
              <span>Viste</span>
            </h3>
            <div class="m3-hub-grid-2col">
              ${viewsHtml}
            </div>
          </section>

          <section class="m3-hub-section" aria-labelledby="nav-sec-devices">
            <h3 class="m3-section-heading" id="nav-sec-devices">
              ${icon('layout-grid', { size: 15 })}
              <span>Dispositivi &amp; Controllo</span>
            </h3>
            <div class="m3-hub-grid-2col">
              ${devicesHtml}
            </div>
          </section>
        </div>
      </div>

      <button
        type="button"
        class="m3-fab m3-fab-primary m3-fab-nav"
        id="btn-nav-fab"
        aria-expanded="false"
        aria-controls="m3-nav-sheet"
        title="Apri Viste e Dispositivi"
      >
        <span class="m3-fab-icon" id="nav-fab-icon">${icon('layout-grid', { size: 22 })}</span>
        <span class="m3-fab-label">Viste &amp; Controlli</span>
      </button>
    `;

    this.sheetEl = this.container.querySelector('#m3-nav-sheet');
    this.fabBtn = this.container.querySelector('#btn-nav-fab');
    this.fabIconEl = this.container.querySelector('#nav-fab-icon');
    this.closeBtn = this.container.querySelector('#btn-nav-hub-close');
  }

  bindEvents() {
    if (!this.container) return;

    this.fabBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggle();
    });

    this.closeBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.close();
    });

    this.sheetEl?.addEventListener('click', (e) => {
      e.stopPropagation();
    });

    // Click sulle Viste (Sezione 1)
    this.container.querySelectorAll('[data-hub-view]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const viewId = btn.dataset.hubView;
        const preset = btn.dataset.preset;
        this.selectView(viewId, preset);
      });
    });

    // Click sui Dispositivi / Centri di Controllo (Sezione 2)
    this.container.querySelectorAll('[data-hub-device]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const deviceId = btn.dataset.hubDevice;
        const preset = btn.dataset.preset;
        const entityId = btn.dataset.entity;
        this.selectDevice(deviceId, preset, entityId);
      });
    });

    document.addEventListener('click', this._onDocClick);
    window.addEventListener('keydown', this._onKeyDown);

    // Aggiornamenti live di stato sui pulsanti grandi dei dispositivi
    if (this.haClient && typeof this.haClient.subscribeEntities === 'function') {
      this._unsubscribeEntities = this.haClient.subscribeEntities((entities) => {
        this.refreshDeviceLiveStates(entities);
      });
    }
  }

  _handleDocumentClick(e) {
    if (!this.isOpen) return;
    if (!this.container.contains(e.target)) {
      this.close();
    }
  }

  _handleKeyDown(e) {
    if (e.key === 'Escape' && this.isOpen) {
      this.close();
    }
  }

  toggle() {
    if (this.isOpen) this.close();
    else this.open();
  }

  open() {
    if (this.isOpen) return;
    this.isOpen = true;
    this.container.classList.add('open');
    this.sheetEl?.classList.add('open');
    this.sheetEl?.setAttribute('aria-hidden', 'false');
    this.fabBtn?.classList.add('active');
    this.fabBtn?.setAttribute('aria-expanded', 'true');
    if (this.fabIconEl) {
      this.fabIconEl.innerHTML = icon('x', { size: 22 });
    }
    this.refreshDeviceLiveStates(this.haClient?.entities || this.haClient?.mockEntities);
    this.onOpenChange?.(true);
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this.container.classList.remove('open');
    this.sheetEl?.classList.remove('open');
    this.sheetEl?.setAttribute('aria-hidden', 'true');
    this.fabBtn?.classList.remove('active');
    this.fabBtn?.setAttribute('aria-expanded', 'false');
    if (this.fabIconEl) {
      this.fabIconEl.innerHTML = icon('layout-grid', { size: 22 });
    }
    this.onOpenChange?.(false);
  }

  selectView(viewId, preset) {
    this.activeViewId = viewId;
    this.activeDeviceId = null;
    this._syncActiveClasses();

    // Chiudi un eventuale pannello dispositivo per mostrare l'ambiente scelto senza ostacoli
    this.deviceModals?.close?.();
    this.cameraController?.flyToPreset?.(preset, 1.15);
    this.close();
  }

  selectDevice(deviceId, preset, entityId) {
    this.activeDeviceId = deviceId;
    this.activeViewId = null;
    this._syncActiveClasses();

    // 1. Sposta subito la vista su un'inquadratura contestuale dedicata al dispositivo
    if (deviceId === 'deebot') {
      const vacCtrl = deviceRegistry.get('vacuum');
      const hasCoords = Boolean(vacCtrl && typeof vacCtrl.hasRobotCoordinates === 'function' && vacCtrl.hasRobotCoordinates());
      const zoomed = hasCoords && typeof vacCtrl.zoomToRobot === 'function'
        ? vacCtrl.zoomToRobot(this.cameraController)
        : false;
      if (!zoomed) {
        // Fallback alla vista statica solo se le coordinate 3D/MQTT del robot non sono disponibili
        this.cameraController?.flyToPreset?.(preset, 1.15);
      }
    } else {
      this.cameraController?.flyToPreset?.(preset, 1.15);
    }

    // 2. Chiudi il menu FAB e apri subito di default il relativo pannello di gestione
    this.close();
    if (entityId && this.deviceModals?.open) {
      this.deviceModals.open(entityId);
    }
  }

  _syncActiveClasses() {
    this.container.querySelectorAll('[data-hub-view]').forEach((el) => {
      el.classList.toggle('active', el.dataset.hubView === this.activeViewId);
    });
    this.container.querySelectorAll('[data-hub-device]').forEach((el) => {
      el.classList.toggle('active', el.dataset.hubDevice === this.activeDeviceId);
    });
  }

  refreshDeviceLiveStates(entities) {
    if (!this.container) return;

    const updateTile = (id, text, isRunning) => {
      const subEl = this.container.querySelector(`[data-device-status="${id}"]`);
      const btnEl = this.container.querySelector(`[data-hub-device="${id}"]`);
      if (subEl && text) subEl.textContent = text;
      if (btnEl) btnEl.classList.toggle('is-running', Boolean(isRunning));
    };

    // 1. Impianto Termico
    const thermalCtrl = deviceRegistry.get('thermal');
    if (thermalCtrl) {
      updateTile('thermal', thermalCtrl.getSummaryLabel(), thermalCtrl.isBoilerOn());
    } else if (entities) {
      const boilerOn = entities['switch.smart_switch_caldaia']?.state === 'on';
      const tHigh = parseFloat(entities['sensor.temperatura_accumulo_alto']?.state);
      const label = Number.isFinite(tHigh)
        ? `${boilerOn ? 'Caldaia ON' : 'Caldaia OFF'} • ${tHigh.toFixed(1)}°C`
        : (boilerOn ? 'Caldaia ON' : 'Caldaia OFF');
      updateTile('thermal', label, boilerOn);
    }

    // 2. Irrigazione
    const irrigCtrl = deviceRegistry.get('irrigation');
    if (irrigCtrl) {
      const activeZones = [1, 2, 3].filter((z) => irrigCtrl.isAreaValveOn(z)).length;
      const cycleOn = irrigCtrl.isCycleActive();
      const label = activeZones > 0
        ? `${activeZones} ${activeZones === 1 ? 'zona attiva' : 'zone attive'}`
        : (cycleOn ? 'Ciclo attivo' : 'Spento • 3 zone');
      updateTile('irrigation', label, activeZones > 0 || cycleOn);
    }

    // 3. Smart TV
    const tvCtrl = deviceRegistry.get('tv');
    if (tvCtrl) {
      const isOn = tvCtrl.isPoweredOn();
      const ent = tvCtrl.getEntity();
      const source = ent?.attributes?.app_name || ent?.attributes?.source || 'Accesa';
      updateTile('tv', isOn ? source : 'Spenta', isOn);
    }

    // 4. Lavastoviglie
    const dishCtrl = deviceRegistry.get('dishwasher');
    if (dishCtrl) {
      const status = dishCtrl.getStatus();
      const sLow = String(status).toLowerCase();
      const progress = dishCtrl.getProgress();
      const isRunning = sLow === 'running' || sLow === 'in funzione';
      const label = isRunning && progress > 0 ? `In corso • ${progress}%` : status;
      updateTile('dishwasher', label, isRunning);
    }

    // 5. Deebot
    const vacCtrl = deviceRegistry.get('vacuum');
    if (vacCtrl) {
      const raw = vacCtrl.getRawState().toLowerCase();
      const batt = vacCtrl.getBattery();
      const stateLbl = vacCtrl.getStateLabel();
      updateTile('deebot', `${stateLbl} • ${batt}%`, raw === 'cleaning' || raw === 'returning');
    }
  }

  dispose() {
    document.removeEventListener('click', this._onDocClick);
    window.removeEventListener('keydown', this._onKeyDown);
    if (typeof this._unsubscribeEntities === 'function') {
      this._unsubscribeEntities();
      this._unsubscribeEntities = null;
    }
  }
}
