import { icon } from '../../ui/icons.js';

const CAMERA_CONTROL_SPECS = {
  spotlight: {
    domain: 'light',
    exactSuffixes: ['faretto', 'floodlight'],
    fallbackRe: /(faretto|floodlight)/i,
  },
  spotlightBrightness: {
    domain: 'number',
    exactSuffixes: ['accendi_la_luminosita_del_faretto', 'luminosita_del_faretto', 'floodlight_brightness'],
    fallbackRe: /(luminosit.*faretto|floodlight.*brightness)/i,
  },
  spotlightMode: {
    domain: 'select',
    exactSuffixes: ['modalita_faretto', 'floodlight_mode'],
    fallbackRe: /(modalit.*faretto|floodlight.*mode)/i,
  },
  siren: {
    domain: 'siren',
    exactSuffixes: ['sirena', 'siren'],
    fallbackRe: /(sirena|siren)/i,
    excludeRe: /evento|event/i,
  },
  sirenOnEvent: {
    domain: 'switch',
    exactSuffixes: ['sirena_su_evento', 'siren_on_event'],
    fallbackRe: /(sirena.*evento|siren.*event)/i,
  },
  irNight: {
    domain: 'switch',
    exactSuffixes: ['infrared_lights_in_night_mode', 'luce_infrarossi_modalita_notturna', 'ir_lights'],
    fallbackRe: /(infrared|infrarossi|ir_light)/i,
  },
  dayNightMode: {
    domain: 'select',
    exactSuffixes: ['modalita_giorno_notte', 'day_night_mode'],
    fallbackRe: /(modalit.*giorno|day.*night.*mode)/i,
  },
  dayNightState: {
    domain: 'sensor',
    exactSuffixes: ['day_night_state', 'stato_giorno_notte'],
    fallbackRe: /(day_night_state|stato_giorno_notte)/i,
  },
  pushNotifications: {
    domain: 'switch',
    exactSuffixes: ['notifiche_push', 'push_notifications'],
    fallbackRe: /(notifiche.*push|push.*notif)/i,
  },
  record: {
    domain: 'switch',
    exactSuffixes: ['registra', 'record'],
    fallbackRe: /_(registra|record)$/i,
    excludeRe: /audio/i,
  },
  recordAudio: {
    domain: 'switch',
    exactSuffixes: ['registra_audio', 'record_audio'],
    fallbackRe: /(registra_audio|record_audio)/i,
  },
  reboot: {
    domain: 'button',
    exactSuffixes: ['riavvia', 'restart', 'reboot'],
    fallbackRe: /(riavvia|restart|reboot)/i,
  },
  detectPerson: {
    domain: 'binary_sensor',
    exactSuffixes: ['persona', 'person'],
    fallbackRe: /(persona|person)/i,
  },
  detectVehicle: {
    domain: 'binary_sensor',
    exactSuffixes: ['veicolo', 'vehicle'],
    fallbackRe: /(veicolo|vehicle)/i,
  },
  detectAnimal: {
    domain: 'binary_sensor',
    exactSuffixes: ['animale', 'animal', 'pet'],
    fallbackRe: /(animale|animal|pet)/i,
  },
  detectMotion: {
    domain: 'binary_sensor',
    exactSuffixes: ['movimento', 'motion'],
    fallbackRe: /(movimento|motion)/i,
  },
};

const QUICK_SWITCH_ITEMS = [
  { key: 'irNight', id: 'cam-sw-ir', iconName: 'eye', label: 'Infrarossi Notte' },
  { key: 'pushNotifications', id: 'cam-sw-push', iconName: 'bell', label: 'Notifiche Push' },
  { key: 'record', id: 'cam-sw-record', iconName: 'video', label: 'Registrazione' },
  { key: 'recordAudio', id: 'cam-sw-audio', iconName: 'mic', label: 'Microfono' },
];

const AI_BADGE_ITEMS = [
  { key: 'detectPerson', iconName: 'user', label: 'Persona' },
  { key: 'detectVehicle', iconName: 'car', label: 'Veicolo' },
  { key: 'detectAnimal', iconName: 'dog', label: 'Animale' },
  { key: 'detectMotion', iconName: 'activity', label: 'Movimento' },
];

const OPTION_LABELS_IT = {
  off: 'Spento',
  on: 'Acceso',
  auto: 'Automatica',
  schedule: 'Programmato',
  adaptive: 'Adattivo',
  color: 'A Colori',
  black_and_white: 'Bianco/Nero',
  night: 'Notte',
  day: 'Giorno',
};

function stripCameraSlug(entityId) {
  return String(entityId || '')
    .toLowerCase()
    .replace(/^camera\./, '')
    .replace(/_(scorrevole|fluente|trasparente|chiaro|fluent|clear|main|sub)$/i, '');
}

function formatOptionLabel(option) {
  const key = String(option || '').trim().toLowerCase();
  if (OPTION_LABELS_IT[key]) return OPTION_LABELS_IT[key];
  return String(option || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

/**
 * Risolve dinamicamente tutte le entità Home Assistant della telecamera selezionata
 * supportando prefissi diretti (`carraio_*`) o prefissati per zona (`giardino_portico_*`).
 */
export function resolveCameraControlEntities(entities = {}, { entityId, camName, haClient } = {}) {
  const zoneSlug = String(camName || 'Cam_Carraio').replace(/^Cam_/i, '').toLowerCase() || 'carraio';
  const resolvedCamId =
    (typeof haClient?.resolveCameraEntityId === 'function' ? haClient.resolveCameraEntityId(entityId) : null) ||
    entityId ||
    '';

  const candidates = [];
  for (const s of [stripCameraSlug(resolvedCamId), stripCameraSlug(entityId), zoneSlug, `giardino_${zoneSlug}`]) {
    if (s && !candidates.includes(s)) candidates.push(s);
  }

  const allIds = Object.keys(entities || {});
  const resolved = {};

  for (const [role, spec] of Object.entries(CAMERA_CONTROL_SPECS)) {
    let foundId = null;

    // 1. Ricerca esatta per suffisso noto sui prefissi della camera
    for (const prefix of candidates) {
      for (const suffix of spec.exactSuffixes) {
        const candidateId = `${spec.domain}.${prefix}_${suffix}`;
        if (entities && Object.prototype.hasOwnProperty.call(entities, candidateId)) {
          foundId = candidateId;
          break;
        }
      }
      if (foundId) break;
    }

    // 2. Fallback per regex confinata a dominio + prefisso camera
    if (!foundId && allIds.length > 0) {
      for (const prefix of candidates) {
        const prefixDot = `${spec.domain}.${prefix}_`;
        foundId = allIds.find((id) => {
          if (!id.startsWith(prefixDot)) return false;
          if (spec.excludeRe && spec.excludeRe.test(id)) return false;
          return spec.fallbackRe.test(id);
        }) || null;
        if (foundId) break;
      }
    }

    resolved[role] = foundId || `${spec.domain}.${candidates[0] || zoneSlug}_${spec.exactSuffixes[0]}`;
  }

  return resolved;
}

/**
 * SecurityCameraModal
 *
 * Pannello modale OOP singola telecamera:
 * - Player live WebRTC / MSE a bassa latenza + badge latenza
 * - Selettore flusso Main / Sub e riconnessione rapida
 * - Deck dinamico di controllo Home Assistant (Faretto LED, Luminosità, Sirena/Allarme, Sensori AI, Visione & Audio)
 */
export class SecurityCameraModal {
  constructor(controller) {
    this.controller = controller;
    this.container = null;
    this.videoEl = null;
    this.latencyEl = null;
    this.activeStreamName = 'carraio_main';
    this.mainStreamName = 'carraio_main';
    this.subStreamName = 'carraio_sub';
    this._unsubscribeStatus = null;
    this._unsubscribeAuth = null;
    this._unsubscribeEntities = null;
    this._connectSeq = 0;
    this._camIp = '192.168.86.47';
    this._camName = 'Cam_Carraio';
    this._entityId = 'camera.carraio_scorrevole';
    this._camLabel = 'Reolink RLC-540A';
    this._controlEntityIds = {};
    this._latestEntities = {};
    this._optimisticStates = new Map();
    this._isSlidingBrightness = false;
    this._rebootArmed = false;
    this._rebootArmTimer = null;
  }

  async render(container, context = {}, entity = null) {
    this._clearSubscriptionsAndTimers();
    this.container = container;

    const assetLoader = context.assetLoader || this.controller.assetLoader;
    const entityId =
      entity?.entity_id ||
      context.entityId ||
      this.controller.activeEntityId ||
      this.controller.primaryEntityId ||
      'camera.carraio_scorrevole';
    const camName = this.controller.findMatchingBlenderCameraName(entityId);
    const manifestCam = assetLoader?.manifest?.cameras?.[camName];
    const slugFallback = camName.replace(/^Cam_/i, '').toLowerCase() || 'carraio';

    const mainStream = manifestCam?.stream_id || (camName === 'Cam_Carraio' ? 'carraio_main' : `${slugFallback}_main`);
    const subStream = manifestCam?.sub_stream_id || (camName === 'Cam_Carraio' ? 'carraio_sub' : `${slugFallback}_sub`);
    const mainLabel = manifestCam?.main_stream_label || (camName === 'Cam_Carraio' ? 'Main 5MP' : 'Main HD');
    const subLabel = manifestCam?.sub_stream_label || 'Sub 640×360';

    const labelModelMatch = typeof manifestCam?.ha_label === 'string' ? manifestCam.ha_label.match(/\(([^)]+)\)/) : null;
    const cameraModel =
      manifestCam?.camera_model ||
      (labelModelMatch ? labelModelMatch[1] : null) ||
      (camName === 'Cam_Carraio' ? 'RLC-540A' : 'Telecamera IP');

    const fovH = manifestCam?.fov_h_deg ?? 80;
    const isPano180 =
      Boolean(manifestCam?.is_panoramic_180) ||
      String(manifestCam?.optical_model || '').toLowerCase().includes('equirectangular') ||
      Number(fovH) >= 150;
    const camIp = manifestCam?.camera_ip || (camName === 'Cam_Carraio' ? '192.168.86.47' : 'LAN');

    this._camIp = camIp;
    this._camName = camName;
    this._entityId = manifestCam?.ha_camera_entity || entityId;
    this._camLabel = manifestCam?.ha_label || cameraModel;
    this.mainStreamName = mainStream;
    this.subStreamName = subStream;
    this.activeStreamName = mainStream;

    const haClient = this.controller.haClient || context.haClient;
    this._latestEntities = this._getEntitiesSnapshot(haClient);
    this._controlEntityIds = resolveCameraControlEntities(this._latestEntities, {
      entityId: this._entityId,
      camName,
      haClient,
    });

    container.innerHTML = `
      <div class="camera-preview-stream${isPano180 ? ' is-panoramic' : ''}" id="cam-preview-wrapper">
        <video id="cam-modal-video" autoplay muted playsinline style="width:100%;height:100%;object-fit:${isPano180 ? 'contain' : 'cover'};display:block;"></video>
        <span class="cam-latency-badge" id="cam-latency-badge">-- ms</span>
      </div>

      <div class="control-row" style="gap: 8px;">
        <div style="display:flex;gap:6px;flex:1;">
          <button class="btn-icon-text stream-quality-btn active" data-stream="${mainStream}" style="flex:1;justify-content:center;padding:6px 8px;font-size:11px;">
            ${mainLabel}
          </button>
          <button class="btn-icon-text stream-quality-btn" data-stream="${subStream}" style="flex:1;justify-content:center;padding:6px 8px;font-size:11px;">
            ${subLabel}
          </button>
        </div>
        <button class="btn-icon-text" id="btn-cam-reconnect" title="Riconnetti stream" style="padding:6px 10px;font-size:11px;">
          ${icon('refresh-cw', { size: 13 })} <span>Riconnetti</span>
        </button>
      </div>

      <div class="cam-ctrl-deck" id="cam-ha-controls">
        <div class="cam-ctrl-ai-strip" id="cam-ai-strip" aria-label="Stato rilevamenti AI">
          <div class="cam-ctrl-ai-pills">
            ${AI_BADGE_ITEMS.map((item) => `
              <span class="cam-ctrl-ai-pill" data-ai-key="${item.key}">
                ${icon(item.iconName, { size: 13 })}
                <span>${item.label}</span>
              </span>
            `).join('')}
          </div>
          <span class="cam-ctrl-daynight-pill" id="cam-daynight-chip">
            ${icon('moon', { size: 13 })}
            <span id="cam-daynight-label">Notte</span>
          </span>
        </div>

        <div class="cam-ctrl-hero-grid">
          <section class="cam-ctrl-card cam-ctrl-card--spotlight" id="cam-card-spotlight">
            <div class="cam-ctrl-card-head">
              <div class="cam-ctrl-card-title-wrap">
                <span class="cam-ctrl-icon-badge cam-ctrl-icon-badge--amber" id="cam-spotlight-icon">
                  ${icon('lightbulb', { size: 16 })}
                </span>
                <div>
                  <h4 class="cam-ctrl-card-title">Faretto LED</h4>
                  <span class="cam-ctrl-card-status" id="cam-spotlight-status">Spento</span>
                </div>
              </div>
              <button
                type="button"
                class="m3-switch"
                id="btn-cam-spotlight-toggle"
                role="switch"
                aria-checked="false"
                aria-label="Accendi o spegni faretto LED"
              >
                <span class="m3-switch-thumb"></span>
              </button>
            </div>

            <div class="cam-ctrl-slider-row" id="cam-spotlight-brightness-row">
              <span class="cam-ctrl-slider-icon">${icon('sun', { size: 14 })}</span>
              <input
                type="range"
                id="cam-spotlight-brightness"
                class="timeline-slider cam-ctrl-slider"
                min="0"
                max="100"
                step="1"
                value="70"
                aria-label="Luminosità faretto LED"
              />
              <span class="cam-ctrl-slider-value" id="cam-spotlight-brightness-val">70%</span>
            </div>

            <div class="cam-ctrl-chip-row" id="cam-spotlight-modes" role="group" aria-label="Modalità faretto LED"></div>
          </section>

          <section class="cam-ctrl-card cam-ctrl-card--siren" id="cam-card-siren">
            <div class="cam-ctrl-card-head">
              <div class="cam-ctrl-card-title-wrap">
                <span class="cam-ctrl-icon-badge cam-ctrl-icon-badge--crimson" id="cam-siren-icon">
                  ${icon('shield-alert', { size: 16 })}
                </span>
                <div>
                  <h4 class="cam-ctrl-card-title">Allarme Sirena</h4>
                  <span class="cam-ctrl-card-status" id="cam-siren-status">Pronta</span>
                </div>
              </div>
              <span class="cam-ctrl-state-dot" id="cam-siren-state-dot" aria-hidden="true"></span>
            </div>

            <button
              type="button"
              class="cam-ctrl-siren-cta"
              id="btn-cam-siren-toggle"
              aria-pressed="false"
            >
              ${icon('siren', { size: 16 })}
              <span id="cam-siren-cta-label">Attiva Sirena</span>
            </button>

            <div class="cam-ctrl-sub-toggle" id="cam-siren-event-row">
              <span class="cam-ctrl-sub-label">
                ${icon('bell-ring', { size: 13 })}
                <span>Suono su evento</span>
              </span>
              <button
                type="button"
                class="m3-switch m3-switch--compact"
                id="btn-cam-siren-event"
                role="switch"
                aria-checked="false"
                aria-label="Attiva sirena automatica su evento"
              >
                <span class="m3-switch-thumb"></span>
              </button>
            </div>
          </section>
        </div>

        <section class="cam-ctrl-card cam-ctrl-card--quick">
          <div class="cam-ctrl-card-head">
            <h4 class="cam-ctrl-card-title">Sicurezza, Visione & Audio</h4>
            <div class="cam-ctrl-chip-row cam-ctrl-chip-row--inline" id="cam-daynight-modes" role="group" aria-label="Modalità giorno e notte"></div>
          </div>

          <div class="cam-ctrl-tiles-grid" id="cam-quick-switches">
            ${QUICK_SWITCH_ITEMS.map((item) => `
              <button
                type="button"
                class="cam-ctrl-tile"
                id="${item.id}"
                data-ctrl-key="${item.key}"
                role="switch"
                aria-checked="false"
              >
                <span class="cam-ctrl-tile-icon">${icon(item.iconName, { size: 16 })}</span>
                <span class="cam-ctrl-tile-meta">
                  <span class="cam-ctrl-tile-label">${item.label}</span>
                  <span class="cam-ctrl-tile-state">Spento</span>
                </span>
              </button>
            `).join('')}
          </div>
        </section>

        <button
          type="button"
          class="cam-ctrl-reboot-btn"
          id="btn-cam-reboot"
          hidden
          disabled
          style="display:none;"
        >
          ${icon('rotate-cw', { size: 14 })}
          <span id="cam-reboot-label">Riavvia Telecamera</span>
        </button>
      </div>
    `;

    this.videoEl = container.querySelector('#cam-modal-video');
    this.latencyEl = container.querySelector('#cam-latency-badge');

    // Qualità Main / Sub
    container.querySelectorAll('.stream-quality-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const targetStream = btn.dataset.stream;
        const isExplicitMain = targetStream === this.mainStreamName;
        this._syncQualityButtons(targetStream);
        this.activeStreamName = targetStream;
        await this.connectStream(this.activeStreamName, {
          forceReconnect: isExplicitMain,
          allowSubReuse: !isExplicitMain,
        });
      });
    });

    // Riconnetti forzato
    container.querySelector('#btn-cam-reconnect')?.addEventListener('click', () => {
      this.connectStream(this.activeStreamName, {
        forceReconnect: true,
        allowSubReuse: this.activeStreamName === this.subStreamName,
      });
    });

    this._bindHaControls(container, haClient);
    this._syncControlsFromEntities(this._latestEntities, haClient);

    // RBAC: Riavvio camera riservato ad Admin
    const applyRbacVisibility = (adminFlag) => {
      const rebootBtn = this.container?.querySelector('#btn-cam-reboot');
      if (!rebootBtn) return;
      const allowed = Boolean(adminFlag);
      const hasRebootEntity = Boolean(this._getEntity('reboot'));
      const showBtn = allowed && (hasRebootEntity || Object.keys(this._latestEntities).length === 0);
      rebootBtn.hidden = !allowed;
      rebootBtn.disabled = !allowed;
      rebootBtn.style.display = showBtn ? '' : 'none';
    };
    applyRbacVisibility(haClient?.isAdmin);
    if (typeof haClient?.onAuthChange === 'function') {
      this._unsubscribeAuth = haClient.onAuthChange((authState) => {
        applyRbacVisibility(authState?.isAdmin ?? haClient?.isAdmin);
      });
    }

    if (typeof haClient?.subscribeEntities === 'function') {
      this._unsubscribeEntities = haClient.subscribeEntities((entities) => {
        if (!this.container || this.container !== container) return;
        this._latestEntities = entities || {};
        this._controlEntityIds = resolveCameraControlEntities(this._latestEntities, {
          entityId: this._entityId,
          camName: this._camName,
          haClient,
        });
        this._syncControlsFromEntities(this._latestEntities, haClient);
        applyRbacVisibility(haClient?.isAdmin);
      });
    }

    // Collega il flusso video (istantaneo a 0ms se caldo nel pool o con preview sub immediata!)
    await this.connectStream(this.activeStreamName);
  }

  _getEntitiesSnapshot(haClient) {
    if (!haClient) return {};
    if (haClient.isMockMode && haClient.mockEntities) return haClient.mockEntities;
    const live = haClient.entities && Object.keys(haClient.entities).length > 0 ? haClient.entities : null;
    return live || haClient.mockEntities || {};
  }

  _getEntity(role) {
    const id = this._controlEntityIds[role];
    if (!id) return null;
    const raw = this._latestEntities?.[id] || null;
    if (!raw) return null;
    const optimistic = this._optimisticStates.get(id);
    if (optimistic) {
      if (Date.now() > optimistic.expiresAt || raw.state === optimistic.targetState) {
        this._optimisticStates.delete(id);
      } else {
        return { ...raw, state: optimistic.targetState };
      }
    }
    return raw;
  }

  _dispatchService(haClient, domain, service, serviceData, optimisticState = null) {
    if (!haClient || typeof haClient.callService !== 'function') return;
    const entityId = serviceData?.entity_id;
    if (entityId && optimisticState !== null && optimisticState !== undefined) {
      this._optimisticStates.set(entityId, {
        targetState: String(optimisticState),
        expiresAt: Date.now() + 1400,
      });
      this._syncControlsFromEntities(this._latestEntities, haClient);
    }
    haClient.callService(domain, service, serviceData);
  }

  _bindHaControls(container, haClient) {
    // 1. Toggle Faretto LED
    container.querySelector('#btn-cam-spotlight-toggle')?.addEventListener('click', () => {
      const entity = this._getEntity('spotlight');
      const entityId = this._controlEntityIds.spotlight;
      if (!entity || entity.state === 'unavailable') return;
      const nextService = entity.state === 'on' ? 'turn_off' : 'turn_on';
      const nextState = nextService === 'turn_on' ? 'on' : 'off';
      this._dispatchService(haClient, 'light', nextService, { entity_id: entityId }, nextState);
    });

    // 2. Slider Luminosità Faretto
    const slider = container.querySelector('#cam-spotlight-brightness');
    const sliderValEl = container.querySelector('#cam-spotlight-brightness-val');
    if (slider) {
      slider.addEventListener('input', () => {
        this._isSlidingBrightness = true;
        if (sliderValEl) sliderValEl.textContent = `${Math.round(Number(slider.value) || 0)}%`;
      });
      slider.addEventListener('change', () => {
        this._isSlidingBrightness = false;
        const pct = Math.max(0, Math.min(100, Math.round(Number(slider.value) || 0)));
        const numEntity = this._getEntity('spotlightBrightness');
        if (numEntity) {
          this._dispatchService(
            haClient,
            'number',
            'set_value',
            { entity_id: numEntity.entity_id, value: pct },
            String(pct)
          );
          return;
        }
        const lightEntity = this._getEntity('spotlight');
        if (lightEntity) {
          this._dispatchService(
            haClient,
            'light',
            pct > 0 ? 'turn_on' : 'turn_off',
            pct > 0
              ? { entity_id: lightEntity.entity_id, brightness: Math.round((pct / 100) * 255) }
              : { entity_id: lightEntity.entity_id },
            pct > 0 ? 'on' : 'off'
          );
        }
      });
    }

    // 3. Modalità Faretto (event delegation su container chips)
    container.querySelector('#cam-spotlight-modes')?.addEventListener('click', (ev) => {
      const chip = ev.target?.closest?.('[data-option]');
      if (!chip || chip.disabled) return;
      const option = chip.dataset.option;
      const entity = this._getEntity('spotlightMode');
      if (!entity || !option) return;
      this._dispatchService(
        haClient,
        'select',
        'select_option',
        { entity_id: entity.entity_id, option },
        option
      );
    });

    // 4. Sirena manuale
    container.querySelector('#btn-cam-siren-toggle')?.addEventListener('click', () => {
      const entity = this._getEntity('siren');
      if (!entity || entity.state === 'unavailable') return;
      const isOn = entity.state === 'on';
      const nextService = isOn ? 'turn_off' : 'turn_on';
      this._dispatchService(
        haClient,
        'siren',
        nextService,
        { entity_id: entity.entity_id },
        isOn ? 'off' : 'on'
      );
    });

    // 5. Sirena automatica su evento
    container.querySelector('#btn-cam-siren-event')?.addEventListener('click', () => {
      const entity = this._getEntity('sirenOnEvent');
      if (!entity || entity.state === 'unavailable') return;
      const nextState = entity.state === 'on' ? 'off' : 'on';
      this._dispatchService(
        haClient,
        'switch',
        'toggle',
        { entity_id: entity.entity_id },
        nextState
      );
    });

    // 6. Griglia 2x2 Switch Rapidi (Infrarossi, Notifiche, Registrazione, Microfono)
    container.querySelector('#cam-quick-switches')?.addEventListener('click', (ev) => {
      const tile = ev.target?.closest?.('.cam-ctrl-tile[data-ctrl-key]');
      if (!tile || tile.disabled) return;
      const roleKey = tile.dataset.ctrlKey;
      const entity = this._getEntity(roleKey);
      if (!entity || entity.state === 'unavailable') return;
      const nextState = entity.state === 'on' ? 'off' : 'on';
      this._dispatchService(
        haClient,
        'switch',
        'toggle',
        { entity_id: entity.entity_id },
        nextState
      );
    });

    // 7. Modalità Giorno/Notte (event delegation)
    container.querySelector('#cam-daynight-modes')?.addEventListener('click', (ev) => {
      const chip = ev.target?.closest?.('[data-option]');
      if (!chip || chip.disabled) return;
      const option = chip.dataset.option;
      const entity = this._getEntity('dayNightMode');
      if (!entity || !option) return;
      this._dispatchService(
        haClient,
        'select',
        'select_option',
        { entity_id: entity.entity_id, option },
        option
      );
    });

    // 8. Riavvio Camera con conferma a 2 passaggi (solo Admin)
    container.querySelector('#btn-cam-reboot')?.addEventListener('click', () => {
      if (!haClient?.isAdmin) return;
      const entity = this._getEntity('reboot');
      const rebootBtn = this.container?.querySelector('#btn-cam-reboot');
      const labelEl = this.container?.querySelector('#cam-reboot-label');
      if (!entity || !rebootBtn) return;

      if (!this._rebootArmed) {
        this._rebootArmed = true;
        rebootBtn.classList.add('is-armed');
        if (labelEl) labelEl.textContent = 'Conferma riavvio camera';
        if (this._rebootArmTimer) clearTimeout(this._rebootArmTimer);
        this._rebootArmTimer = setTimeout(() => {
          this._rebootArmed = false;
          rebootBtn.classList.remove('is-armed');
          if (labelEl) labelEl.textContent = 'Riavvia Telecamera';
        }, 4000);
        return;
      }

      this._rebootArmed = false;
      if (this._rebootArmTimer) clearTimeout(this._rebootArmTimer);
      rebootBtn.classList.remove('is-armed');
      rebootBtn.disabled = true;
      if (labelEl) labelEl.textContent = 'Riavvio inviato...';
      this._dispatchService(haClient, 'button', 'press', { entity_id: entity.entity_id });
      this._rebootArmTimer = setTimeout(() => {
        if (!this.container) return;
        rebootBtn.disabled = !haClient?.isAdmin;
        if (labelEl) labelEl.textContent = 'Riavvia Telecamera';
      }, 3000);
    });
  }

  _syncControlsFromEntities(entities, haClient) {
    if (!this.container) return;
    const hasEntityMap = Boolean(entities && Object.keys(entities).length > 0);

    // 1. Strip AI + Giorno/Notte
    this.container.querySelectorAll('.cam-ctrl-ai-pill[data-ai-key]').forEach((pill) => {
      const entity = this._getEntity(pill.dataset.aiKey);
      const isDetected = entity?.state === 'on';
      pill.classList.toggle('is-detected', isDetected);
      pill.classList.toggle('is-unavailable', hasEntityMap && !entity);
    });

    const dayNightEnt = this._getEntity('dayNightState');
    const dayNightChip = this.container.querySelector('#cam-daynight-chip');
    const dayNightLabel = this.container.querySelector('#cam-daynight-label');
    if (dayNightChip && dayNightLabel) {
      const isNight = !dayNightEnt || String(dayNightEnt.state).toLowerCase() === 'night';
      dayNightLabel.textContent = dayNightEnt ? formatOptionLabel(dayNightEnt.state) : 'Stato ND';
      dayNightChip.classList.toggle('is-day', !isNight && Boolean(dayNightEnt));
    }

    // 2. Faretto LED
    const spotlightEnt = this._getEntity('spotlight');
    const spotlightCard = this.container.querySelector('#cam-card-spotlight');
    const spotlightBtn = this.container.querySelector('#btn-cam-spotlight-toggle');
    const spotlightStatusEl = this.container.querySelector('#cam-spotlight-status');
    const numEnt = this._getEntity('spotlightBrightness');
    const slider = this.container.querySelector('#cam-spotlight-brightness');
    const sliderValEl = this.container.querySelector('#cam-spotlight-brightness-val');
    const sliderRow = this.container.querySelector('#cam-spotlight-brightness-row');

    const spotlightOn = spotlightEnt?.state === 'on';
    const spotlightMissing = !spotlightEnt || spotlightEnt.state === 'unavailable';
    let pct = 70;
    if (numEnt && !Number.isNaN(Number(numEnt.state))) {
      pct = Math.max(0, Math.min(100, Math.round(Number(numEnt.state))));
    } else if (spotlightEnt?.attributes?.brightness !== undefined) {
      pct = Math.max(0, Math.min(100, Math.round((Number(spotlightEnt.attributes.brightness) / 255) * 100)));
    }

    spotlightCard?.classList.toggle('is-active', spotlightOn);
    spotlightCard?.classList.toggle('is-unavailable', spotlightMissing);
    if (spotlightBtn) {
      spotlightBtn.classList.toggle('checked', spotlightOn);
      spotlightBtn.setAttribute('aria-checked', spotlightOn ? 'true' : 'false');
      spotlightBtn.disabled = spotlightMissing;
    }
    if (spotlightStatusEl) {
      spotlightStatusEl.textContent = spotlightMissing
        ? 'Non disponibile'
        : spotlightOn
          ? `Acceso · ${pct}%`
          : `Spento · ${pct}%`;
    }
    if (slider && !this._isSlidingBrightness) {
      slider.value = String(pct);
      slider.disabled = spotlightMissing && !numEnt;
    }
    if (sliderValEl && !this._isSlidingBrightness) {
      sliderValEl.textContent = `${pct}%`;
    }
    if (sliderRow) {
      sliderRow.style.display = (numEnt || spotlightEnt) ? '' : 'none';
    }

    const spotlightModeEnt = this._getEntity('spotlightMode');
    this._renderModeChips(
      this.container.querySelector('#cam-spotlight-modes'),
      spotlightModeEnt,
      ['off', 'auto', 'schedule']
    );

    // 3. Sirena & Deterrenza
    const sirenEnt = this._getEntity('siren');
    const sirenCard = this.container.querySelector('#cam-card-siren');
    const sirenBtn = this.container.querySelector('#btn-cam-siren-toggle');
    const sirenCtaLabel = this.container.querySelector('#cam-siren-cta-label');
    const sirenStatusEl = this.container.querySelector('#cam-siren-status');
    const sirenDot = this.container.querySelector('#cam-siren-state-dot');

    const sirenOn = sirenEnt?.state === 'on';
    const sirenMissing = !sirenEnt || sirenEnt.state === 'unavailable';
    sirenCard?.classList.toggle('is-active', sirenOn);
    sirenCard?.classList.toggle('is-unavailable', sirenMissing);
    sirenDot?.classList.toggle('is-on', sirenOn);
    if (sirenBtn) {
      sirenBtn.classList.toggle('is-active', sirenOn);
      sirenBtn.setAttribute('aria-pressed', sirenOn ? 'true' : 'false');
      sirenBtn.disabled = sirenMissing;
    }
    if (sirenCtaLabel) {
      sirenCtaLabel.textContent = sirenMissing
        ? 'Sirena non disponibile'
        : sirenOn
          ? 'Ferma Sirena'
          : 'Attiva Sirena';
    }
    if (sirenStatusEl) {
      sirenStatusEl.textContent = sirenMissing ? 'Non disponibile' : sirenOn ? 'Allarme attivo' : 'Pronta';
    }

    const sirenEventEnt = this._getEntity('sirenOnEvent');
    const sirenEventRow = this.container.querySelector('#cam-siren-event-row');
    const sirenEventBtn = this.container.querySelector('#btn-cam-siren-event');
    if (sirenEventBtn && sirenEventRow) {
      const eventOn = sirenEventEnt?.state === 'on';
      const eventMissing = !sirenEventEnt || sirenEventEnt.state === 'unavailable';
      sirenEventRow.classList.toggle('is-unavailable', eventMissing);
      sirenEventBtn.classList.toggle('checked', eventOn);
      sirenEventBtn.setAttribute('aria-checked', eventOn ? 'true' : 'false');
      sirenEventBtn.disabled = eventMissing;
    }

    // 4. Tile Switches (Infrarossi, Notifiche, Registrazione, Audio)
    this.container.querySelectorAll('.cam-ctrl-tile[data-ctrl-key]').forEach((tile) => {
      const ent = this._getEntity(tile.dataset.ctrlKey);
      const isOn = ent?.state === 'on';
      const isMissing = !ent || ent.state === 'unavailable';
      tile.classList.toggle('is-on', isOn);
      tile.classList.toggle('is-unavailable', isMissing);
      tile.setAttribute('aria-checked', isOn ? 'true' : 'false');
      tile.disabled = isMissing;
      const stateEl = tile.querySelector('.cam-ctrl-tile-state');
      if (stateEl) {
        stateEl.textContent = isMissing ? 'N/D' : isOn ? 'Attivo' : 'Spento';
      }
    });

    // 5. Modalità Giorno/Notte chips
    this._renderModeChips(
      this.container.querySelector('#cam-daynight-modes'),
      this._getEntity('dayNightMode'),
      ['auto', 'color', 'black_and_white']
    );

    // 6. RBAC Riavvio Button stato entità
    const rebootBtn = this.container.querySelector('#btn-cam-reboot');
    const rebootEnt = this._getEntity('reboot');
    if (rebootBtn && !haClient?.isAdmin) {
      rebootBtn.hidden = true;
      rebootBtn.disabled = true;
      rebootBtn.style.display = 'none';
    } else if (rebootBtn && rebootEnt?.state === 'unavailable') {
      rebootBtn.disabled = true;
    }
  }

  _renderModeChips(containerEl, selectEntity, fallbackOptions = []) {
    if (!containerEl) return;
    const isMissing = !selectEntity || selectEntity.state === 'unavailable';
    const options =
      Array.isArray(selectEntity?.attributes?.options) && selectEntity.attributes.options.length > 0
        ? selectEntity.attributes.options
        : fallbackOptions;
    const activeOption = selectEntity?.state;

    containerEl.innerHTML = options
      .map((opt) => {
        const isActive = !isMissing && opt === activeOption;
        return `
          <button
            type="button"
            class="cam-ctrl-chip${isActive ? ' active' : ''}"
            data-option="${opt}"
            ${isMissing ? 'disabled' : ''}
            aria-pressed="${isActive ? 'true' : 'false'}"
          >${formatOptionLabel(opt)}</button>
        `;
      })
      .join('');
  }

  _syncQualityButtons(activeStream) {
    if (!this.container) return;
    this.container.querySelectorAll('.stream-quality-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.stream === activeStream);
    });
  }

  updateStreamStatusUI(status) {
    if (this.latencyEl && status) {
      this.latencyEl.textContent = `${status.latencyMs ?? 0} ms`;
    }
  }

  async connectStream(streamName, { forceReconnect = false, allowSubReuse = true } = {}) {
    const vsm = this.controller.videoStreamManager;
    if (!vsm || !this.videoEl) return;

    const seq = ++this._connectSeq;
    this._lastFallbackToSub = false;

    if (this._unsubscribeStatus) {
      this._unsubscribeStatus();
      this._unsubscribeStatus = null;
    }

    try {
      const provider = await vsm.attachToVideoElement(streamName, this.videoEl, 'auto', {
        cameraEntityId: this._entityId,
        cameraName: this._camName,
        cameraLabel: this._camLabel,
        cameraIp: this._camIp,
        forceReconnect,
        allowSubReuse,
      });

      if (seq !== this._connectSeq || !this.container) return;

      const activeStreamName = provider.streamName || streamName;
      const didFallbackToSub = Boolean(activeStreamName !== streamName && activeStreamName === this.subStreamName);
      this._lastFallbackToSub = didFallbackToSub;
      if (didFallbackToSub) {
        this._syncQualityButtons(this.subStreamName);
      }

      this.updateStreamStatusUI(provider.getStatus());

      if (typeof provider.onStatusChange === 'function') {
        this._unsubscribeStatus = provider.onStatusChange((st) => {
          if (seq === this._connectSeq && this.container && st.connected) {
            this.updateStreamStatusUI(st);
          }
        });
      }
    } catch {
      if (seq === this._connectSeq && this.latencyEl) {
        this.latencyEl.textContent = '-- ms';
      }
    }
  }

  _clearSubscriptionsAndTimers() {
    if (this._unsubscribeStatus) {
      this._unsubscribeStatus();
      this._unsubscribeStatus = null;
    }
    if (this._unsubscribeAuth) {
      this._unsubscribeAuth();
      this._unsubscribeAuth = null;
    }
    if (this._unsubscribeEntities) {
      this._unsubscribeEntities();
      this._unsubscribeEntities = null;
    }
    if (this._rebootArmTimer) {
      clearTimeout(this._rebootArmTimer);
      this._rebootArmTimer = null;
    }
    this._rebootArmed = false;
    this._isSlidingBrightness = false;
    this._optimisticStates.clear();
  }

  destroy() {
    this._connectSeq += 1;
    this._clearSubscriptionsAndTimers();
    if (this.videoEl && this.controller.videoStreamManager) {
      this.controller.videoStreamManager.detachFromVideoElement(this.videoEl);
    }
    this.videoEl = null;
    this.latencyEl = null;
    this.container = null;
  }
}
