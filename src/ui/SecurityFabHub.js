import { icon } from './icons.js';
import { RecordingPlaybackStatus } from '../video/recordings/index.js';

function pad2(n) {
  return String(Math.max(0, Math.floor(n))).padStart(2, '0');
}

function formatDateInput(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function formatTimeInput(date) {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

function formatTimeInputHHMM(date) {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function parseLocalDateTime(dateStr, timeStr) {
  if (!dateStr || typeof dateStr !== 'string') return null;
  const dParts = dateStr.split('-').map((v) => parseInt(v, 10));
  if (dParts.length !== 3 || dParts.some((n) => !Number.isFinite(n))) return null;
  const tParts = String(timeStr || '12:00').split(':').map((v) => parseInt(v, 10));
  const hh = Number.isFinite(tParts[0]) ? tParts[0] : 12;
  const mm = Number.isFinite(tParts[1]) ? tParts[1] : 0;
  const ss = Number.isFinite(tParts[2]) ? tParts[2] : 0;
  const dt = new Date(dParts[0], dParts[1] - 1, dParts[2], hh, mm, ss, 0);
  return Number.isNaN(dt.getTime()) ? null : dt;
}

function formatShortDateTime(unixSec) {
  if (!Number.isFinite(unixSec)) return '--:--:--';
  const dt = new Date(unixSec * 1000);
  return dt.toLocaleTimeString('it-IT', { hour12: false });
}

function formatFullDateTime(unixSec) {
  if (!Number.isFinite(unixSec)) return '--/-- --:--:--';
  const dt = new Date(unixSec * 1000);
  const day = `${pad2(dt.getDate())}/${pad2(dt.getMonth() + 1)}`;
  return `${day} ${formatTimeInput(dt)}`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * SecurityFabHub
 *
 * Interfaccia Material 3 "Sicurezza" attivata dal pulsante FAB in basso a sinistra.
 * Integra in un unico hub moderno:
 * 1. Riquadri video multi-camera (live o replay storico sincronizzato) con supporto
 *    nativo per più telecamere e rapporti d'aspetto misti (16:9 standard e 180° panoramici).
 * 2. Sezione Cronologia & Time-Machine: selezione dinamica di giorno e orario, finestra
 *    temporale, istogramma di densità 3D, controllo velocità (1x/2x/5x) e sincronizzazione
 *    simultanea tra registrazioni video (con gestione robusta schermo nero se assente) e
 *    ricostruzione 3D di persone/veicoli tramite TrajectoryRenderer.
 * 3. Modalità compatta "Striscia in basso" (Filmstrip Dock): riduce il pannello a una
 *    striscia orizzontale sul bordo inferiore per lasciare libero il 3D, mantenendo i
 *    riquadri in proporzione esatta senza tagli e scorrevoli destra-sinistra.
 */
export class SecurityFabHub {
  constructor(domContainer, {
    cameraCatalog,
    videoStreamManager,
    recordingManager,
    trajectoryRenderer,
    spatialStreamClient,
    cameraController,
    assetLoader,
    deviceModals,
    haClient = null,
    onStateChange = null,
  } = {}) {
    this.container = domContainer;
    this.cameraCatalog = cameraCatalog;
    this.videoStreamManager = videoStreamManager;
    this.recordingManager = recordingManager;
    this.trajectoryRenderer = trajectoryRenderer;
    this.spatialStreamClient = spatialStreamClient;
    this.cameraController = cameraController;
    this.assetLoader = assetLoader;
    this.deviceModals = deviceModals;
    this.haClient = haClient || null;
    this.onStateChange = typeof onStateChange === 'function' ? onStateChange : null;

    // Stato UI: 'closed' | 'expanded' | 'strip'
    this.panelState = 'closed';
    // Modalità: 'live' | 'replay' | 'settings'
    this.mode = 'live';
    // Layout griglia: 'proportional' (default: 2 normali affiancate + 180° a tutta larghezza una sotto l'altra) | 'compact' (2×2)
    this.gridLayoutMode = this._loadSavedGridLayoutMode();

    // Stato Playback & Cronologia
    this.entitiesVisible = false;
    this.isPlaying = false;
    this.playbackSpeed = 1.0;
    this.windowSpanSec = 3600; // Default finestra 1 ora centrata/allineata all'orario scelto
    const nowUnix = Math.floor(Date.now() / 1000);
    this.windowEndUnix = nowUnix;
    this.windowStartUnix = nowUnix - this.windowSpanSec;
    this.currentUnix = nowUnix - 120;

    this.densityBins = [];
    this.recordingSegmentsByCam = new Map();
    this.liveStreamUnsubs = new Map(); // cameraId -> unsubscribe fn
    this.tileElements = new Map();     // cameraId -> { card, video, badge, meta, noRecOverlay, noRecTime, noRecReason }
    this._modeListeners = new Set();
    this._replaySlotListeners = new Set();
    this._liveConnected = false;
    this._hasAutoLoadedRealHistory = false;
    this._activeTrackCount = 0;
    this._historyRecordCount = 0;
    this._historyEntityCount = 0;
    this._historyDensityTotal = 0;
    this._historyBackendOnline = false;
    this._loadedTracksStartUnix = null;
    this._loadedTracksEndUnix = null;
    this._historyLoadSeq = 0;
    this._sliceReloadTimer = null;
    this._densityResizeObserver = null;
    this._lastUiSyncPerf = 0;

    this.bioFilters = { identity: '', plate: '', unknownOnly: false };
    this.recentLiveBioEvents = [];
    this.historyBioEvents = [];
    this.bioIdentitiesList = [];
    this.bioPlatesList = [];
    this._biometricsStatus = null;
    this._activeHitlEvent = null;
    this._bioPlateTimer = null;
    this._unsubBioEvents = null;
    this._unsubAutoEvents = null;
    this._unsubHaAuth = null;

    this._alarmEntityId = 'sh3d.allarme';
    this._alarmEntity = null;
    this._alarmModalOpen = false;
    this._alarmLoading = false;
    this._alarmBusy = false;

    this._onKeyDown = (e) => {
      if (e.key === 'Escape') {
        if (this._alarmModalOpen) {
          this.closeAlarmModal();
          return;
        }
        if (this.panelState === 'expanded') {
          this.close();
        }
      }
    };

    this.initUI();
    this.bindEvents();
    this.bindSpatialClient();
    this.syncCameraTiles();
    this._syncAdminControls();

    if (this.haClient && typeof this.haClient.onAuthChange === 'function') {
      this._unsubHaAuth = this.haClient.onAuthChange(() => {
        this._syncAdminControls();
      });
    }

    if (this.cameraCatalog && typeof this.cameraCatalog.onChange === 'function') {
      this._unsubCatalog = this.cameraCatalog.onChange(() => {
        this.syncCameraTiles();
        if (this.panelState !== 'closed') {
          if (this.mode === 'live') this.connectAllLiveStreams();
          else if (this.mode === 'replay') this.bindAllHistoricalSlotsAndSeek(true);
        }
      });
    }
  }

  get isOpen() {
    return this.panelState !== 'closed';
  }

  get isExpanded() {
    return this.panelState === 'expanded';
  }

  get isStrip() {
    return this.panelState === 'strip';
  }

  _loadSavedGridLayoutMode() {
    try {
      if (typeof localStorage !== 'undefined') {
        const saved = localStorage.getItem('sh3d_sec_grid_layout');
        if (saved === 'compact' || saved === 'proportional') {
          return saved;
        }
      }
    } catch {}
    return 'proportional';
  }

  setGridLayoutMode(nextMode, { persist = true } = {}) {
    const mode = nextMode === 'compact' ? 'compact' : 'proportional';
    this.gridLayoutMode = mode;
    const isCompact = mode === 'compact';

    if (this.camerasTrackEl) {
      this.camerasTrackEl.classList.toggle('layout-compact', isCompact);
      this.camerasTrackEl.dataset.layoutMode = mode;
    }

    if (this.settingsLayoutPropBtn) {
      this.settingsLayoutPropBtn.classList.toggle('active', !isCompact);
      this.settingsLayoutPropBtn.setAttribute('aria-pressed', String(!isCompact));
    }
    if (this.settingsLayoutCompactBtn) {
      this.settingsLayoutCompactBtn.classList.toggle('active', isCompact);
      this.settingsLayoutCompactBtn.setAttribute('aria-pressed', String(isCompact));
    }

    if (persist) {
      try {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem('sh3d_sec_grid_layout', mode);
        }
      } catch {}
    }
  }

  onModeChange(listener) {
    if (typeof listener !== 'function') return () => {};
    this._modeListeners.add(listener);
    return () => this._modeListeners.delete(listener);
  }

  onReplaySlotStateChange(listener) {
    if (typeof listener !== 'function') return () => {};
    this._replaySlotListeners.add(listener);
    return () => this._replaySlotListeners.delete(listener);
  }

  getReplayTileInfo(cameraId) {
    if (this.panelState === 'closed' || this.mode !== 'replay') return null;
    const tile = this.tileElements.get(cameraId);
    if (!tile || !tile.videoEl) return null;
    return {
      videoEl: tile.activeReplayVideoEl || tile.videoEl,
      status: tile.lastReplayState?.status || RecordingPlaybackStatus.IDLE,
      state: tile.lastReplayState || null,
    };
  }

  initUI() {
    if (!this.container) return;

    this.container.innerHTML = `
      <section class="m3-security-panel" id="m3-security-panel" role="dialog" aria-label="Centrale Sicurezza e Cronologia" aria-hidden="true">
        <header class="m3-sec-header">
          <div class="m3-sec-title-group">
            <span class="m3-sec-header-icon">${icon('shield-check', { size: 18 })}</span>
            <div class="m3-sec-title-copy">
              <h2 class="m3-sec-title">Sicurezza</h2>
              <span class="m3-sec-status-line" id="sec-status-summary">Live multi-camera</span>
            </div>
          </div>

          <div class="m3-segmented" role="tablist" aria-label="Modalità telecamere, cronologia e impostazioni">
            <button type="button" class="m3-seg-btn active" id="btn-sec-mode-live" role="tab" aria-selected="true" aria-controls="sec-cameras-viewport">
              <span class="m3-live-dot" aria-hidden="true"></span>
              <span>Live</span>
            </button>
            <button type="button" class="m3-seg-btn" id="btn-sec-mode-replay" role="tab" aria-selected="false" aria-controls="sec-history-section">
              ${icon('history', { size: 14 })}
              <span>Cronologia</span>
            </button>
            <button type="button" class="m3-seg-btn" id="btn-sec-mode-settings" role="tab" aria-selected="false" aria-controls="sec-settings-section">
              ${icon('settings', { size: 14 })}
              <span>Impostazioni</span>
            </button>
          </div>

          <div class="m3-sec-header-actions">
            <button
              type="button"
              class="m3-icon-btn m3-alarm-header-btn"
              id="btn-sec-alarm-control"
              title="Gestisci stato allarme (sh3d.allarme)"
              aria-label="Gestisci stato allarme sh3d.allarme"
            >
              ${icon('shield-alert', { size: 15 })}
              <span class="m3-alarm-btn-label" id="sec-alarm-btn-label">Allarme</span>
            </button>
            <button type="button" class="m3-icon-btn m3-strip-toggle-btn" id="btn-sec-strip-toggle" title="Riduci a striscia in basso per vedere tutto il 3D" aria-label="Riduci a striscia in basso">
              ${icon('panel-bottom-close', { size: 17 })}
            </button>
            <button type="button" class="m3-icon-btn" id="btn-sec-close" title="Chiudi pannello Sicurezza" aria-label="Chiudi Sicurezza">
              ${icon('x', { size: 17 })}
            </button>
          </div>
        </header>

        <!-- Barra compatta visibile solo nella modalità Striscia in basso -->
        <div class="m3-strip-toolbar" id="sec-strip-toolbar">
          <div class="m3-strip-left">
            <button type="button" class="m3-strip-pill active" id="btn-strip-mode-toggle" title="Alterna Live / Cronologia">
              <span class="m3-live-dot" aria-hidden="true"></span>
              <span id="strip-mode-label">LIVE</span>
            </button>
            <button type="button" class="m3-strip-mini-btn" id="btn-strip-play" title="Play / Pausa cronologia" hidden>
              ${icon('play', { size: 14 })}
            </button>
            <span class="m3-strip-clock" id="strip-clock-display">LIVE</span>
          </div>
          <div class="m3-strip-right">
            <button type="button" class="m3-strip-mini-btn" id="btn-strip-entities" title="Mostra/Nascondi persone e veicoli 3D">
              ${icon('eye-off', { size: 14 })}
            </button>
            <button type="button" class="m3-strip-mini-btn accent" id="btn-strip-expand" title="Espandi pannello Sicurezza">
              ${icon('panel-bottom-open', { size: 15 })}
              <span>Espandi</span>
            </button>
            <button type="button" class="m3-strip-mini-btn" id="btn-strip-close" aria-label="Chiudi striscia telecamere">
              ${icon('x', { size: 15 })}
            </button>
          </div>
        </div>

        <!-- Corpo unificato scorrevole (Live + Cronologia + Impostazioni; trasparente in modalità striscia) -->
        <div class="m3-sec-body" id="sec-panel-body">
          <!-- Sezione Video Multi-Camera (rimane montata e fluida tra espanso e striscia!) -->
          <div class="m3-sec-cameras-viewport" id="sec-cameras-viewport">
            <div class="m3-sec-cameras-track" id="sec-cameras-track"></div>
          </div>

          <!-- Striscia Live Riconoscimenti Biometrici (nascosta se vuota o fuori da Live) -->
          <div class="m3-sec-bio-live-strip" id="sec-bio-live-strip" hidden aria-label="Ultimi riconoscimenti biometrici"></div>

          <!-- Sezione Cronologia & Ricostruzione 3D (visibile solo in modalità Cronologia) -->
          <div class="m3-sec-history-section" id="sec-history-section" role="tabpanel" hidden>
          <div class="m3-history-top-row">
            <div class="m3-day-chips" role="group" aria-label="Selezione giorno rapida">
              <button type="button" class="m3-chip active" data-day-offset="0">Oggi</button>
              <button type="button" class="m3-chip" data-day-offset="1">Ieri</button>
              <button type="button" class="m3-chip" data-day-offset="2">2 gg fa</button>
            </div>

            <div class="m3-datetime-inputs">
              <label class="m3-input-pill" title="Seleziona giorno">
                ${icon('calendar', { size: 14 })}
                <input type="date" id="sec-date-input" aria-label="Giorno cronologia" />
              </label>
              <label class="m3-input-pill" title="Seleziona orario">
                ${icon('clock', { size: 14 })}
                <input type="time" id="sec-time-input" aria-label="Orario cronologia" />
              </label>
            </div>
          </div>

          <div class="m3-bio-filters-row" id="sec-bio-filters" role="search" aria-label="Filtri cronologia biometrici">
            <label class="m3-bio-filter-pill" title="Filtra per persona riconosciuta">
              ${icon('user-check', { size: 13 })}
              <select id="sec-filter-identity" class="m3-bio-select" aria-label="Filtra per persona">
                <option value="">Tutte le persone</option>
                <option value="__unknown__">Solo sconosciuti</option>
              </select>
            </label>
            <label class="m3-bio-filter-pill m3-bio-plate-pill" title="Filtra per numero di targa">
              ${icon('tag', { size: 13 })}
              <input type="text" id="sec-filter-plate" class="m3-bio-input" placeholder="Targa (es. AB123CD)" aria-label="Filtra per targa" maxlength="12" />
            </label>
            <button type="button" class="m3-bio-clear-btn" id="btn-sec-bio-filter-clear" hidden title="Azzera filtri biometrici" aria-label="Azzera filtri biometrici">
              ${icon('x', { size: 13 })}
            </button>
          </div>

          <div class="m3-history-scrubber-card">
            <div class="m3-scrubber-meta-row">
              <span class="m3-scrubber-clock" id="sec-replay-clock">--:--:--</span>
              <span class="m3-scrubber-entities" id="sec-entity-stats">0 rilevazioni 3D</span>
              <div class="m3-span-chips" role="group" aria-label="Ampiezza finestra temporale">
                <button type="button" class="m3-mini-chip" data-span="900">15m</button>
                <button type="button" class="m3-mini-chip active" data-span="3600">1h</button>
                <button type="button" class="m3-mini-chip" data-span="21600">6h</button>
                <button type="button" class="m3-mini-chip" data-span="86400">24h</button>
              </div>
            </div>

            <div class="m3-scrubber-track-wrap">
              <canvas id="sec-density-canvas" class="m3-density-canvas" height="32" title="Clicca su una barra per saltare a quell'orario"></canvas>
              <input type="range" min="0" max="3600" step="1" value="3480" class="m3-timeline-slider" id="sec-timeline-slider" aria-label="Cursore temporale cronologia" />
            </div>

            <div class="m3-playback-controls-row">
              <div class="m3-playback-left">
                <button type="button" class="m3-ctrl-btn" id="btn-sec-entities-3d" title="Mostra/Nascondi persone e veicoli ricostruiti nel 3D" aria-pressed="false">
                  ${icon('eye-off', { size: 16 })}
                </button>
                <button type="button" class="m3-ctrl-btn" id="btn-sec-step-back" title="Indietro di 30 secondi">
                  ${icon('skip-back', { size: 15 })}
                </button>
                <button type="button" class="m3-ctrl-btn m3-ctrl-play" id="btn-sec-play-pause" title="Play / Pausa">
                  ${icon('play', { size: 16 })}
                </button>
                <button type="button" class="m3-ctrl-btn" id="btn-sec-step-fwd" title="Avanti di 30 secondi">
                  ${icon('skip-forward', { size: 15 })}
                </button>
              </div>

              <div class="m3-playback-right">
                <div class="m3-speed-group" role="group" aria-label="Velocità di riproduzione">
                  <button type="button" class="m3-speed-btn active" data-speed="1">1x</button>
                  <button type="button" class="m3-speed-btn" data-speed="2">2x</button>
                  <button type="button" class="m3-speed-btn" data-speed="5">5x</button>
                </div>
              </div>
            </div>
          </div>

          <div class="m3-bio-events-wrap" id="sec-bio-events-wrap" hidden>
            <div class="m3-bio-events-header">
              <span class="m3-bio-events-title">${icon('shield-check', { size: 14 })} <span>Eventi riconosciuti</span></span>
              <div class="m3-bio-events-header-actions">
                <span class="m3-bio-events-count" id="sec-bio-events-count">0</span>
                <button
                  type="button"
                  class="m3-bio-admin-toggle"
                  id="btn-sec-bio-admin"
                  hidden
                  disabled
                  style="display: none;"
                  title="Apri impostazioni whitelist targhe e galleria volti (solo Admin)"
                  aria-label="Gestisci biometria e whitelist in Impostazioni"
                >
                  ${icon('sliders-horizontal', { size: 13 })}
                  <span>Gestisci</span>
                </button>
              </div>
            </div>
            <div class="m3-admin-status-msg" id="sec-bio-hitl-msg" hidden></div>
            <div class="m3-bio-hitl-editor" id="sec-bio-hitl-editor" hidden></div>
            <div class="m3-bio-events-list" id="sec-bio-events-list"></div>
          </div>

          <div class="m3-storage-footer" id="sec-storage-footer">
            ${icon('hard-drive', { size: 13 })}
            <span id="sec-storage-label">Archivio NVR predisposto • Pronto per HDD PC o SD camera</span>
          </div>
        </div>

        <!-- Sezione Impostazioni modulare ed estensibile (visibile in modalità Impostazioni) -->
        <div class="m3-sec-settings-section" id="sec-settings-section" role="tabpanel" hidden>
          <div class="m3-settings-stack" id="sec-settings-stack">
            <div class="m3-admin-status-msg" id="sec-admin-bio-msg" hidden></div>

            <section class="m3-settings-group" aria-labelledby="sec-settings-view-title">
              <div class="m3-settings-group-head">
                <span class="m3-settings-group-icon">${icon('layout-grid', { size: 15 })}</span>
                <div class="m3-settings-group-copy">
                  <h3 class="m3-settings-group-title" id="sec-settings-view-title">Visualizzazione e sistema</h3>
                  <p class="m3-settings-group-sub">Preferenze griglia multi-camera e stato moduli sicurezza</p>
                </div>
              </div>

              <div class="m3-settings-row">
                <div class="m3-settings-row-copy">
                  <span class="m3-settings-row-label">Disposizione griglia video</span>
                  <span class="m3-settings-row-hint">Formato panoramico intero oppure griglia 2×2 compatta</span>
                </div>
                <div class="m3-settings-choice" role="group" aria-label="Disposizione griglia telecamere">
                  <button type="button" class="m3-settings-choice-btn active" id="btn-sec-settings-layout-prop" data-settings-layout="proportional" aria-pressed="true">
                    Proporzionata
                  </button>
                  <button type="button" class="m3-settings-choice-btn" id="btn-sec-settings-layout-compact" data-settings-layout="compact" aria-pressed="false">
                    Compatta 2×2
                  </button>
                </div>
              </div>

              <div class="m3-settings-status-grid">
                <div class="m3-settings-status-item">
                  <span class="m3-settings-status-label">${icon('hard-drive', { size: 13 })} <span>Archivio NVR</span></span>
                  <span class="m3-settings-status-val" id="sec-settings-nvr-status">In verifica...</span>
                </div>
                <div class="m3-settings-status-item">
                  <span class="m3-settings-status-label">${icon('activity', { size: 13 })} <span>Biometria 3D</span></span>
                  <span class="m3-settings-status-val" id="sec-settings-bio-status">In verifica...</span>
                </div>
              </div>
            </section>

            <div class="m3-settings-resident-note" id="sec-settings-resident-note" role="note">
              ${icon('info', { size: 15 })}
              <span>La gestione di whitelist targhe, galleria volti e manutenzione archivio è riservata agli amministratori.</span>
            </div>

            <div class="m3-bio-admin-panel" id="sec-bio-admin-panel" hidden style="display: none;">
              <section class="m3-settings-group" aria-labelledby="sec-settings-plates-title">
                <div class="m3-settings-group-head">
                  <span class="m3-settings-group-icon">${icon('car', { size: 15 })}</span>
                  <div class="m3-settings-group-copy">
                    <h3 class="m3-settings-group-title" id="sec-settings-plates-title">Whitelist targhe autorizzate</h3>
                    <p class="m3-settings-group-sub">I veicoli autorizzati vengono evidenziati automaticamente in verde</p>
                  </div>
                  <span class="m3-settings-count-pill" id="sec-admin-plates-count">0</span>
                </div>

                <div class="m3-admin-plate-form">
                  <input type="text" id="sec-admin-plate-input" placeholder="Targa (AB123CD)" maxlength="12" aria-label="Nuova targa whitelist" />
                  <input type="text" id="sec-admin-plate-owner" placeholder="Proprietario" maxlength="64" aria-label="Proprietario targa" />
                  <input type="text" id="sec-admin-plate-vehicle" placeholder="Auto (opzionale)" maxlength="48" aria-label="Modello veicolo" />
                  <button type="button" class="m3-admin-btn primary" id="btn-sec-admin-plate-add" disabled title="Aggiungi o aggiorna targa in whitelist">
                    ${icon('plus', { size: 14 })}
                    <span>Salva targa</span>
                  </button>
                </div>
                <div class="m3-admin-list" id="sec-admin-plates-list"></div>
              </section>

              <section class="m3-settings-group" aria-labelledby="sec-settings-gallery-title">
                <div class="m3-settings-group-head">
                  <span class="m3-settings-group-icon">${icon('user-check', { size: 15 })}</span>
                  <div class="m3-settings-group-copy">
                    <h3 class="m3-settings-group-title" id="sec-settings-gallery-title">Galleria volti registrati</h3>
                    <p class="m3-settings-group-sub">Profili biometrici usati per il riconoscimento su Live e Cronologia</p>
                  </div>
                  <span class="m3-settings-count-pill" id="sec-admin-identities-count">0</span>
                  <button type="button" class="m3-admin-btn" id="btn-sec-admin-reload-gallery" disabled title="Ricarica indice volti da disco">
                    ${icon('refresh-cw', { size: 13 })}
                    <span>Ricarica</span>
                  </button>
                </div>
                <div class="m3-admin-list" id="sec-admin-identities-list"></div>
              </section>

              <section class="m3-settings-group" aria-labelledby="sec-settings-maint-title">
                <div class="m3-settings-group-head">
                  <span class="m3-settings-group-icon">${icon('hard-drive', { size: 15 })}</span>
                  <div class="m3-settings-group-copy">
                    <h3 class="m3-settings-group-title" id="sec-settings-maint-title">Manutenzione archivio crop</h3>
                    <p class="m3-settings-group-sub">Elimina dal disco i ritagli oltre la finestra di conservazione</p>
                  </div>
                </div>
                <div class="m3-settings-row">
                  <div class="m3-settings-row-copy">
                    <span class="m3-settings-row-label">Pulizia crop biometrici scaduti</span>
                    <span class="m3-settings-row-hint">Operazione sicura: mantiene intatti eventi storici e profili registrati</span>
                  </div>
                  <button type="button" class="m3-admin-btn" id="btn-sec-admin-prune-crops" disabled title="Elimina crop scaduti da disco">
                    ${icon('refresh-cw', { size: 13 })}
                    <span>Pulisci ora</span>
                  </button>
                </div>
              </section>
            </div>
            <!-- Nuove sezioni Impostazioni (es. notifiche, soglie, privacy) possono essere aggiunte qui come .m3-settings-group -->
          </div>
        </div>
        </div>

      </section>

      <button
        type="button"
        class="m3-fab m3-fab-security"
        id="btn-security-fab"
        aria-expanded="false"
        aria-controls="m3-security-panel"
        title="Apri interfaccia Sicurezza e Cronologia"
      >
        <span class="m3-fab-icon" id="sec-fab-icon">${icon('shield-check', { size: 22 })}</span>
        <span class="m3-fab-label">Sicurezza</span>
        <span class="m3-fab-badge" id="sec-fab-cam-count">1</span>
      </button>

      <div class="m3-alarm-modal-overlay" id="sec-alarm-modal-overlay" hidden aria-hidden="true">
        <div class="m3-alarm-modal" id="sec-alarm-modal" role="dialog" aria-modal="true" aria-labelledby="sec-alarm-modal-title">
          <header class="m3-alarm-modal-header">
            <div class="m3-alarm-modal-title-wrap">
              <span class="m3-alarm-modal-icon">${icon('siren', { size: 22 })}</span>
              <div class="m3-alarm-modal-copy">
                <h3 class="m3-alarm-modal-title" id="sec-alarm-modal-title">Allarme Casa</h3>
                <code class="m3-alarm-modal-eid">sh3d.allarme</code>
              </div>
            </div>
            <button type="button" class="m3-icon-btn" id="btn-sec-alarm-modal-close" title="Chiudi finestra allarme" aria-label="Chiudi finestra allarme">
              ${icon('x', { size: 18 })}
            </button>
          </header>
          <div class="m3-alarm-modal-body" id="sec-alarm-modal-body"></div>
        </div>
      </div>
    `;

    this.panelEl = this.container.querySelector('#m3-security-panel');
    this.fabBtn = this.container.querySelector('#btn-security-fab');
    this.fabIconEl = this.container.querySelector('#sec-fab-icon');
    this.fabCountEl = this.container.querySelector('#sec-fab-cam-count');
    this.camerasTrackEl = this.container.querySelector('#sec-cameras-track');
    this.statusSummaryEl = this.container.querySelector('#sec-status-summary');

    this.liveBtn = this.container.querySelector('#btn-sec-mode-live');
    this.replayBtn = this.container.querySelector('#btn-sec-mode-replay');
    this.settingsBtn = this.container.querySelector('#btn-sec-mode-settings');
    this.panelBodyEl = this.container.querySelector('#sec-panel-body');
    this.alarmControlBtn = this.container.querySelector('#btn-sec-alarm-control');
    this.alarmBtnLabelEl = this.container.querySelector('#sec-alarm-btn-label');
    this.alarmModalOverlayEl = this.container.querySelector('#sec-alarm-modal-overlay');
    this.alarmModalEl = this.container.querySelector('#sec-alarm-modal');
    this.alarmModalTitleEl = this.container.querySelector('#sec-alarm-modal-title');
    this.alarmModalBodyEl = this.container.querySelector('#sec-alarm-modal-body');
    this.alarmModalCloseBtn = this.container.querySelector('#btn-sec-alarm-modal-close');
    this.stripToggleBtn = this.container.querySelector('#btn-sec-strip-toggle');
    this.closeBtn = this.container.querySelector('#btn-sec-close');

    // Strip controls
    this.stripModeBtn = this.container.querySelector('#btn-strip-mode-toggle');
    this.stripModeLabel = this.container.querySelector('#strip-mode-label');
    this.stripPlayBtn = this.container.querySelector('#btn-strip-play');
    this.stripClockEl = this.container.querySelector('#strip-clock-display');
    this.stripEntitiesBtn = this.container.querySelector('#btn-strip-entities');
    this.stripExpandBtn = this.container.querySelector('#btn-strip-expand');
    this.stripCloseBtn = this.container.querySelector('#btn-strip-close');

    // History controls
    this.historySectionEl = this.container.querySelector('#sec-history-section');
    this.dateInput = this.container.querySelector('#sec-date-input');
    this.timeInput = this.container.querySelector('#sec-time-input');
    this.replayClockEl = this.container.querySelector('#sec-replay-clock');
    this.entityStatsEl = this.container.querySelector('#sec-entity-stats');
    this.densityCanvas = this.container.querySelector('#sec-density-canvas');
    this.slider = this.container.querySelector('#sec-timeline-slider');
    this.playPauseBtn = this.container.querySelector('#btn-sec-play-pause');
    this.entities3dBtn = this.container.querySelector('#btn-sec-entities-3d');
    this.stepBackBtn = this.container.querySelector('#btn-sec-step-back');
    this.stepFwdBtn = this.container.querySelector('#btn-sec-step-fwd');
    this.storageLabelEl = this.container.querySelector('#sec-storage-label');

    this.bioLiveStripEl = this.container.querySelector('#sec-bio-live-strip');
    this.identityFilterSelect = this.container.querySelector('#sec-filter-identity');
    this.plateFilterInput = this.container.querySelector('#sec-filter-plate');
    this.clearBioFilterBtn = this.container.querySelector('#btn-sec-bio-filter-clear');
    this.bioEventsWrapEl = this.container.querySelector('#sec-bio-events-wrap');
    this.bioEventsCountEl = this.container.querySelector('#sec-bio-events-count');
    this.bioEventsListEl = this.container.querySelector('#sec-bio-events-list');

    this.bioAdminToggleBtn = this.container.querySelector('#btn-sec-bio-admin');
    this.bioHitlMsgEl = this.container.querySelector('#sec-bio-hitl-msg');
    this.bioHitlEditorEl = this.container.querySelector('#sec-bio-hitl-editor');

    // Settings & Admin controls
    this.settingsSectionEl = this.container.querySelector('#sec-settings-section');
    this.settingsLayoutPropBtn = this.container.querySelector('#btn-sec-settings-layout-prop');
    this.settingsLayoutCompactBtn = this.container.querySelector('#btn-sec-settings-layout-compact');
    this.settingsNvrStatusEl = this.container.querySelector('#sec-settings-nvr-status');
    this.settingsBioStatusEl = this.container.querySelector('#sec-settings-bio-status');
    this.settingsResidentNoteEl = this.container.querySelector('#sec-settings-resident-note');
    this.bioAdminPanelEl = this.container.querySelector('#sec-bio-admin-panel');
    this.adminBioMsgEl = this.container.querySelector('#sec-admin-bio-msg');
    this.adminPlatesCountEl = this.container.querySelector('#sec-admin-plates-count');
    this.adminPlateInput = this.container.querySelector('#sec-admin-plate-input');
    this.adminPlateOwnerInput = this.container.querySelector('#sec-admin-plate-owner');
    this.adminPlateVehicleInput = this.container.querySelector('#sec-admin-plate-vehicle');
    this.adminPlateAddBtn = this.container.querySelector('#btn-sec-admin-plate-add');
    this.adminPlatesListEl = this.container.querySelector('#sec-admin-plates-list');
    this.adminIdentitiesCountEl = this.container.querySelector('#sec-admin-identities-count');
    this.adminReloadGalleryBtn = this.container.querySelector('#btn-sec-admin-reload-gallery');
    this.adminIdentitiesListEl = this.container.querySelector('#sec-admin-identities-list');
    this.adminPruneCropsBtn = this.container.querySelector('#btn-sec-admin-prune-crops');

    this._syncDateTimeInputsFromUnix(this.currentUnix);
    this._syncSliderBounds();
  }

  bindEvents() {
    if (!this.container) return;

    this.fabBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      if (this.panelState === 'closed') {
        this.openExpanded();
      } else {
        this.close();
      }
    });

    this.panelEl?.addEventListener('click', (e) => {
      e.stopPropagation();
    });

    this.closeBtn?.addEventListener('click', () => this.close());
    this.stripCloseBtn?.addEventListener('click', () => this.close());

    this.stripToggleBtn?.addEventListener('click', () => {
      if (this.panelState === 'strip') this.openExpanded();
      else this.minimizeToStrip();
    });

    this.alarmControlBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      void this.openAlarmModal();
    });

    this.alarmModalCloseBtn?.addEventListener('click', () => this.closeAlarmModal());
    this.alarmModalOverlayEl?.addEventListener('click', (e) => {
      if (e.target === this.alarmModalOverlayEl) {
        this.closeAlarmModal();
      }
    });
    this.alarmModalEl?.addEventListener('click', (e) => {
      e.stopPropagation();
    });

    this.stripExpandBtn?.addEventListener('click', () => this.openExpanded());

    this.liveBtn?.addEventListener('click', () => this.setMode('live'));
    this.replayBtn?.addEventListener('click', () => this.setMode('replay'));
    this.settingsBtn?.addEventListener('click', () => this.setMode('settings'));
    this.stripModeBtn?.addEventListener('click', () => {
      this.setMode(this.mode === 'live' ? 'replay' : 'live');
    });

    this.settingsLayoutPropBtn?.addEventListener('click', () => {
      this.setGridLayoutMode('proportional');
    });
    this.settingsLayoutCompactBtn?.addEventListener('click', () => {
      this.setGridLayoutMode('compact');
    });

    // Quick Day Chips
    this.container.querySelectorAll('[data-day-offset]').forEach((chip) => {
      chip.addEventListener('click', () => {
        const offsetDays = parseInt(chip.dataset.dayOffset, 10) || 0;
        const target = new Date();
        target.setDate(target.getDate() - offsetDays);
        if (offsetDays === 0) {
          // Oggi: punta a 2 minuti fa per consultare gli eventi recenti
          target.setTime(Date.now() - 120 * 1000);
        } else {
          // Giorni precedenti: mantiene l'ora scelta nell'input time
          const parts = (this.timeInput?.value || '12:00').split(':').map((v) => parseInt(v, 10));
          const hh = Number.isFinite(parts[0]) ? parts[0] : 12;
          const mm = Number.isFinite(parts[1]) ? parts[1] : 0;
          const ss = Number.isFinite(parts[2]) ? parts[2] : 0;
          target.setHours(hh, mm, ss, 0);
        }
        this._highlightDayChip(offsetDays);
        this.jumpToUnixTimestamp(Math.floor(target.getTime() / 1000), { switchToReplay: true, reloadWindow: true });
      });
    });

    // Date & Time pickers (parsing esplicito in orario locale compatibile con Android/iOS/Desktop)
    const onDateTimeChanged = () => {
      const parsed = parseLocalDateTime(this.dateInput?.value, this.timeInput?.value || '12:00');
      if (!parsed) return;
      this._highlightDayChip(null);
      this.jumpToUnixTimestamp(Math.floor(parsed.getTime() / 1000), { switchToReplay: true, reloadWindow: true });
    };

    this.dateInput?.addEventListener('change', onDateTimeChanged);
    this.timeInput?.addEventListener('change', onDateTimeChanged);

    // Click diretto sull'istogramma di densità per saltare subito su una barra/picco di attività
    this.densityCanvas?.addEventListener('click', (e) => {
      const rect = this.densityCanvas.getBoundingClientRect?.();
      if (!rect || rect.width <= 0) return;
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const span = Math.max(1, this.windowEndUnix - this.windowStartUnix);
      const targetUnix = Math.floor(this.windowStartUnix + ratio * span);
      this.jumpToUnixTimestamp(targetUnix, { switchToReplay: true, reloadWindow: false });
    });

    if (typeof ResizeObserver !== 'undefined' && this.densityCanvas) {
      this._densityResizeObserver = new ResizeObserver(() => {
        if (this.mode === 'replay' && this.panelState === 'expanded') {
          this.drawDensityCanvas();
        }
      });
      this._densityResizeObserver.observe(this.densityCanvas);
    }

    // Finestra temporale (15m / 1h / 6h / 24h)
    this.container.querySelectorAll('[data-span]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const span = parseInt(btn.dataset.span, 10) || 3600;
        this.container.querySelectorAll('[data-span]').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        this.windowSpanSec = span;
        this.jumpToUnixTimestamp(this.currentUnix, { switchToReplay: this.mode === 'replay', reloadWindow: true });
      });
    });

    // Timeline Scrubber
    this.slider?.addEventListener('input', (e) => {
      const offsetVal = parseFloat(e.target.value) || 0;
      if (this.mode !== 'replay') {
        this.setMode('replay', { skipInitialLoad: true });
      }
      this.currentUnix = this.windowStartUnix + offsetVal;
      this._syncDateTimeInputsFromUnix(this.currentUnix);
      this._updateReplayClockUI();
      this._renderReplayFrameAtCurrentUnix();
      this._scheduleSliceReloadIfNeeded(180);
      this.recordingManager?.seekAllToTimestamp?.(this.currentUnix, { immediate: false });
    });

    this.slider?.addEventListener('change', () => {
      if (this.mode === 'replay') {
        this._scheduleSliceReloadIfNeeded(0);
      }
    });

    // Play/Pause & Step
    const togglePlay = () => {
      if (this.mode !== 'replay') {
        this.setMode('replay');
      }
      this.setPlaying(!this.isPlaying);
    };
    this.playPauseBtn?.addEventListener('click', togglePlay);
    this.stripPlayBtn?.addEventListener('click', togglePlay);

    this.stepBackBtn?.addEventListener('click', () => {
      this._nudgeTime(-30);
    });
    this.stepFwdBtn?.addEventListener('click', () => {
      this._nudgeTime(30);
    });

    // Speed
    this.container.querySelectorAll('.m3-speed-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.container.querySelectorAll('.m3-speed-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        this.playbackSpeed = parseFloat(btn.dataset.speed) || 1.0;
        this.recordingManager?.setPlaybackRate?.(this.playbackSpeed);
      });
    });

    // Toggle 3D Entities Visibility
    const toggleEntities = () => this.setEntitiesVisible(!this.entitiesVisible);
    this.entities3dBtn?.addEventListener('click', toggleEntities);
    this.stripEntitiesBtn?.addEventListener('click', toggleEntities);

    // Filtri biometrici semantici (Persona / Sconosciuti / Targa)
    this.identityFilterSelect?.addEventListener('change', () => {
      const val = String(this.identityFilterSelect.value || '');
      this.bioFilters.unknownOnly = val === '__unknown__';
      this.bioFilters.identity = this.bioFilters.unknownOnly ? '' : val;
      this._onBioFiltersChanged();
    });

    this.plateFilterInput?.addEventListener('input', () => {
      if (this._bioPlateTimer) clearTimeout(this._bioPlateTimer);
      this._bioPlateTimer = setTimeout(() => {
        this._bioPlateTimer = null;
        this.bioFilters.plate = String(this.plateFilterInput?.value || '').trim().toUpperCase();
        this._onBioFiltersChanged();
      }, 280);
    });

    this.plateFilterInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        if (this._bioPlateTimer) {
          clearTimeout(this._bioPlateTimer);
          this._bioPlateTimer = null;
        }
        this.bioFilters.plate = String(this.plateFilterInput?.value || '').trim().toUpperCase();
        this._onBioFiltersChanged();
      }
    });

    this.clearBioFilterBtn?.addEventListener('click', () => {
      if (this._bioPlateTimer) {
        clearTimeout(this._bioPlateTimer);
        this._bioPlateTimer = null;
      }
      this.bioFilters = { identity: '', plate: '', unknownOnly: false };
      if (this.identityFilterSelect) this.identityFilterSelect.value = '';
      if (this.plateFilterInput) this.plateFilterInput.value = '';
      this._onBioFiltersChanged();
    });

    const handleBioJumpClick = (e) => {
      const targetBtn = e.target?.closest?.('[data-jump-ts]');
      if (!targetBtn) return;
      const ts = Number(targetBtn.dataset.jumpTs);
      if (Number.isFinite(ts) && ts > 0) {
        this.jumpToUnixTimestamp(ts, { switchToReplay: true, reloadWindow: false });
      }
    };
    this.bioLiveStripEl?.addEventListener('click', handleBioJumpClick);
    this.bioEventsListEl?.addEventListener('click', (e) => {
      const hitlBtn = e.target?.closest?.('[data-hitl-event-id]');
      if (hitlBtn) {
        e.stopPropagation();
        if (!this._isAdmin()) return;
        const rawId = hitlBtn.getAttribute?.('data-hitl-event-id') ?? hitlBtn.dataset?.hitlEventId;
        const evId = Number(rawId);
        const found = this.historyBioEvents.find((item) => Number(item.id) === evId);
        if (found) this._openHitlEditor(found);
        return;
      }
      handleBioJumpClick(e);
    });

    this.bioAdminToggleBtn?.addEventListener('click', async () => {
      if (!this._isAdmin()) return;
      await this.setMode('settings');
    });

    this.adminPruneCropsBtn?.addEventListener('click', async () => {
      if (!this._isAdmin() || typeof this.spatialStreamClient?.pruneBiometricCrops !== 'function') return;
      this.adminPruneCropsBtn.disabled = true;
      try {
        const res = await this.spatialStreamClient.pruneBiometricCrops().catch(() => null);
        if (res?.status === 'ok') {
          const pruned = Number(res.pruned ?? res.deleted ?? 0);
          this._setAdminMessage(`Pulizia completata (${pruned} crop scaduti rimossi)`, false);
          await this._refreshBiometricsStatusSummary();
        } else {
          this._setAdminMessage('Errore durante la pulizia dei crop biometrici', true);
        }
      } finally {
        if (this.adminPruneCropsBtn) {
          this.adminPruneCropsBtn.disabled = !this._isAdmin();
        }
      }
    });

    this.bioHitlEditorEl?.addEventListener('click', (e) => {
      if (e.target?.closest?.('#btn-sec-hitl-cancel')) {
        this._closeHitlEditor();
        return;
      }
      if (e.target?.closest?.('#btn-sec-hitl-save')) {
        this._submitHitlEditor();
      }
    });

    this.adminPlateAddBtn?.addEventListener('click', async () => {
      if (!this._isAdmin() || typeof this.spatialStreamClient?.upsertBiometricPlate !== 'function') return;
      const plate = String(this.adminPlateInput?.value || '').trim().toUpperCase();
      const ownerName = String(this.adminPlateOwnerInput?.value || '').trim();
      const vehicleLabel = String(this.adminPlateVehicleInput?.value || '').trim() || null;
      if (!plate || !ownerName) {
        this._setAdminMessage('Inserisci targa e proprietario', true);
        return;
      }
      const res = await this.spatialStreamClient
        .upsertBiometricPlate({ plate, owner_name: ownerName, vehicle_label: vehicleLabel })
        .catch(() => null);
      if (res?.status === 'ok') {
        if (this.adminPlateInput) this.adminPlateInput.value = '';
        if (this.adminPlateOwnerInput) this.adminPlateOwnerInput.value = '';
        if (this.adminPlateVehicleInput) this.adminPlateVehicleInput.value = '';
        this.bioPlatesList = Array.isArray(res.plates) ? res.plates : this.bioPlatesList;
        this._renderAdminPlates();
        this._setAdminMessage(`Targa ${plate} salvata in whitelist`, false);
      } else {
        this._setAdminMessage('Errore salvataggio targa in whitelist', true);
      }
    });

    this.adminPlatesListEl?.addEventListener('click', async (e) => {
      const delBtn = e.target?.closest?.('[data-del-plate]');
      if (!delBtn || !this._isAdmin() || typeof this.spatialStreamClient?.deleteBiometricPlate !== 'function') return;
      const plate = String(delBtn.getAttribute?.('data-del-plate') ?? delBtn.dataset?.delPlate ?? '').trim();
      if (!plate) return;
      const res = await this.spatialStreamClient.deleteBiometricPlate(plate).catch(() => null);
      if (res?.status === 'ok') {
        this.bioPlatesList = Array.isArray(res.plates) ? res.plates : this.bioPlatesList.filter((p) => p.plate !== plate);
        this._renderAdminPlates();
        this._setAdminMessage(`Targa ${plate} rimossa`, false);
      }
    });

    this.adminReloadGalleryBtn?.addEventListener('click', async () => {
      if (!this._isAdmin() || typeof this.spatialStreamClient?.reloadBiometricIdentities !== 'function') return;
      const res = await this.spatialStreamClient.reloadBiometricIdentities().catch(() => null);
      if (res?.status === 'ok') {
        this.bioIdentitiesList = Array.isArray(res.identities) ? res.identities : this.bioIdentitiesList;
        this._renderAdminIdentities();
        await this._loadBiometricIdentitiesOptions();
        this._setAdminMessage(`Galleria ricaricata (${this.bioIdentitiesList.length} persone)`, false);
      }
    });

    this.adminIdentitiesListEl?.addEventListener('click', async (e) => {
      const delBtn = e.target?.closest?.('[data-del-identity]');
      if (!delBtn || !this._isAdmin() || typeof this.spatialStreamClient?.deleteBiometricIdentity !== 'function') return;
      const personName = String(delBtn.getAttribute?.('data-del-identity') ?? delBtn.dataset?.delIdentity ?? '').trim();
      if (!personName) return;
      const res = await this.spatialStreamClient.deleteBiometricIdentity(personName).catch(() => null);
      if (res?.status === 'ok') {
        this.bioIdentitiesList = this.bioIdentitiesList.filter((i) => i.name !== personName);
        this._renderAdminIdentities();
        await this._loadBiometricIdentitiesOptions();
        this._setAdminMessage(`Identita ${personName} rimossa`, false);
      }
    });

    window.addEventListener('keydown', this._onKeyDown);
  }

  bindSpatialClient() {
    if (!this.spatialStreamClient) return;

    this.spatialStreamClient.onStatusChange((connected, meta) => {
      const rawMode = (meta?.ingestion_mode || this.spatialStreamClient.lastStatusPayload?.ingestion_mode || '').toLowerCase();
      const isRealServer = Boolean(connected && rawMode && rawMode !== 'synthetic');

      if (isRealServer) {
        this.setEntitiesVisible(true);
        if (this.mode === 'live') {
          this.trajectoryRenderer?.setLiveMode?.(true);
        }
      }
      this._updateStatusSummary();
    });

    this.spatialStreamClient.onFrame((frame) => {
      if (this.mode !== 'live') return;
      const tracks = frame.active_tracks || [];
      this._activeTrackCount = tracks.length;
      this.trajectoryRenderer?.updateLiveTracks?.(tracks, frame.timestamp);

      const nowPerf = performance.now();
      if (nowPerf - this._lastUiSyncPerf > 250) {
        this._lastUiSyncPerf = nowPerf;
        if (this.entityStatsEl) {
          this.entityStatsEl.textContent = `${tracks.length} entità 3D live`;
        }
        if (this.stripClockEl && this.mode === 'live') {
          this.stripClockEl.textContent = `LIVE ${formatShortDateTime(frame.timestamp || Date.now() / 1000)}`;
        }
      }
    });

    if (typeof this.spatialStreamClient.onBiometricEvent === 'function') {
      this._unsubBioEvents = this.spatialStreamClient.onBiometricEvent((ev) => {
        this._pushLiveBiometricEvent(ev);
      });
    }

    if (typeof this.spatialStreamClient.onAutomationEvent === 'function') {
      this._unsubAutoEvents = this.spatialStreamClient.onAutomationEvent((msg) => {
        if (msg?.type === 'virtual_entity_updated' && msg.entity?.entity_id === this._alarmEntityId) {
          this._setAlarmEntityState(msg.entity);
        } else if (msg?.type === 'virtual_entities_list' && Array.isArray(msg.entities)) {
          const found = msg.entities.find((e) => e.entity_id === this._alarmEntityId) || null;
          this._setAlarmEntityState(found);
        }
      });
    }

    this.spatialStreamClient.onStatusChange((connected) => {
      if (connected) {
        void this.refreshAlarmEntity();
      }
    });

    if (this.spatialStreamClient.connected) {
      void this.refreshAlarmEntity();
    }
  }

  /**
   * Crea o aggiorna i riquadri video per tutte le telecamere nel CameraCatalog.
   * Ordina sempre prima le telecamere standard (affiancate in riga 1) e poi le panoramiche 180°
   * (una sotto l'altra a tutta larghezza in modalità proporzionata, o in 2×2 in modalità compatta).
   */
  syncCameraTiles() {
    if (!this.camerasTrackEl || !this.cameraCatalog) return;

    const cameras = this.cameraCatalog.getCameras().slice().sort((a, b) => {
      const pa = a.isPanoramic180 ? 1 : 0;
      const pb = b.isPanoramic180 ? 1 : 0;
      return pa - pb;
    });
    if (this.fabCountEl) {
      this.fabCountEl.textContent = String(cameras.length);
    }

    // Rimuovi slot vecchi se non più presenti
    const nextIds = new Set(cameras.map((c) => c.id));
    for (const [camId, tile] of this.tileElements.entries()) {
      if (!nextIds.has(camId)) {
        this.disconnectLiveForCamera(camId);
        this.recordingManager?.unregisterSlot?.(camId);
        tile.card.remove();
        this.tileElements.delete(camId);
      }
    }

    // Aggiungi o aggiorna card per ogni telecamera rispettando l'ordine (standard prima, 180° poi)
    cameras.forEach((cam, targetIdx) => {
      if (this.tileElements.has(cam.id)) {
        const existing = this.tileElements.get(cam.id);
        existing.cam = cam;
        existing.card.style.setProperty('--cam-aspect', String(cam.aspectRatio));
        existing.card.classList.toggle('is-panoramic', Boolean(cam.isPanoramic180));
        if (this.camerasTrackEl.children[targetIdx] !== existing.card) {
          this.camerasTrackEl.insertBefore(existing.card, this.camerasTrackEl.children[targetIdx] || null);
        }
        return;
      }

      const card = document.createElement('article');
      card.className = `m3-cam-tile${cam.isPanoramic180 ? ' is-panoramic' : ''}`;
      card.dataset.cameraId = cam.id;
      card.style.setProperty('--cam-aspect', String(cam.aspectRatio));

      card.innerHTML = `
        <video class="m3-cam-video" autoplay muted playsinline crossorigin="use-credentials"></video>
        <video class="m3-cam-video-buffer" muted playsinline crossorigin="use-credentials" aria-hidden="true"></video>
        <div class="m3-cam-dark-state" hidden>
          <span class="m3-dark-icon">${icon('video-off', { size: 22 })}</span>
          <span class="m3-dark-title">Nessuna registrazione</span>
          <span class="m3-dark-time">--:--:--</span>
        </div>
        <div class="m3-cam-overlay-top">
          <span class="m3-cam-name">${cam.shortName}${cam.isPanoramic180 ? ' 180°' : ''}</span>
        </div>
        <div class="m3-cam-overlay-actions">
          <button type="button" class="m3-cam-action-btn" data-cam-action="pov" title="Inquadra visuale 3D di ${cam.shortName}" aria-label="Vista 3D ${cam.shortName}">
            ${icon('crosshair', { size: 13 })}
          </button>
          <button type="button" class="m3-cam-action-btn" data-cam-action="details" title="Dettagli e calibrazione ${cam.shortName}" aria-label="Dettagli ${cam.shortName}">
            ${icon('sliders-horizontal', { size: 13 })}
          </button>
        </div>
      `;

      const videoEl = card.querySelector('.m3-cam-video');
      const bufferVideoEl = card.querySelector('.m3-cam-video-buffer');
      const badgeEl = card.querySelector('.m3-cam-badge');
      const darkStateEl = card.querySelector('.m3-cam-dark-state');
      const darkTimeEl = card.querySelector('.m3-dark-time');
      const darkTitleEl = card.querySelector('.m3-dark-title');

      const tileEntry = {
        cam,
        card,
        videoEl,
        bufferVideoEl,
        activeReplayVideoEl: videoEl,
        badgeEl,
        darkStateEl,
        darkTimeEl,
        darkTitleEl,
        lastReplayState: null,
      };

      // Aggiorna dinamicamente il rapporto d'aspetto reale appena il browser decodifica/ridimensiona il video,
      // senza mai declassare a 16:9 una telecamera 180° nota dal manifest (es. su frame fallback temporanei).
      const syncAspectFromVideo = () => {
        if (videoEl.videoWidth > 0 && videoEl.videoHeight > 0) {
          const naturalAspect = videoEl.videoWidth / videoEl.videoHeight;
          if (Number.isFinite(naturalAspect) && naturalAspect > 0.4 && naturalAspect < 6.0) {
            const isKnownPano = Boolean(tileEntry.cam?.isPanoramic180);
            const effectiveAspect = isKnownPano && naturalAspect < 2.2
              ? tileEntry.cam.aspectRatio
              : naturalAspect;
            card.style.setProperty('--cam-aspect', effectiveAspect.toFixed(4));
            card.classList.toggle('is-panoramic', Boolean(isKnownPano || naturalAspect >= 2.2));
          }
        }
      };
      videoEl.addEventListener('loadedmetadata', syncAspectFromVideo);
      videoEl.addEventListener('resize', syncAspectFromVideo);

      card.querySelector('[data-cam-action="pov"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        this._flyToCamera3D(tileEntry.cam);
      });

      card.querySelector('[data-cam-action="details"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        if (tileEntry.cam.entityId && this.deviceModals?.open) {
          if (this.panelState === 'expanded' && window.innerWidth <= 1024) {
            this.minimizeToStrip();
          }
          this.deviceModals.open(tileEntry.cam.entityId);
        }
      });

      if (this.camerasTrackEl.children[targetIdx]) {
        this.camerasTrackEl.insertBefore(card, this.camerasTrackEl.children[targetIdx]);
      } else {
        this.camerasTrackEl.appendChild(card);
      }
      this.tileElements.set(cam.id, tileEntry);
    });

    this.camerasTrackEl.dataset.camCount = String(cameras.length);
    this.setGridLayoutMode(this.gridLayoutMode, { persist: false });
  }

  _flyToCamera3D(cam) {
    const camNode = this.assetLoader?.cameras?.get?.(cam.blenderCameraName);
    if (camNode && this.cameraController?.flyToCameraPOV) {
      if (this.panelState === 'expanded') {
        this.minimizeToStrip();
      }
      this.cameraController.flyToCameraPOV(camNode, 1.25, null, { cameraName: cam.blenderCameraName });
    } else if (cam.blenderCameraName === 'Cam_Carraio') {
      this.cameraController?.flyToPreset?.('carraio_cam', 1.2);
    }
  }

  // --- Gestione Stati Pannello (closed | expanded | strip) ---

  openExpanded() {
    const wasClosed = this.panelState === 'closed';
    this.panelState = 'expanded';
    this.container.classList.add('open');
    this.container.classList.remove('mode-strip');
    this.panelEl?.classList.add('open');
    this.panelEl?.classList.remove('mode-strip');
    this.panelEl?.setAttribute('aria-hidden', 'false');
    this.fabBtn?.classList.add('active');
    this.fabBtn?.setAttribute('aria-expanded', 'true');
    if (this.fabIconEl) {
      this.fabIconEl.innerHTML = icon('x', { size: 22 });
    }

    if (wasClosed) {
      this._onPanelOpened();
    }
    requestAnimationFrame(() => this.drawDensityCanvas());
    this.onStateChange?.(this.panelState);
  }

  minimizeToStrip() {
    const wasClosed = this.panelState === 'closed';
    this.panelState = 'strip';
    this.container.classList.add('open', 'mode-strip');
    this.panelEl?.classList.add('open', 'mode-strip');
    this.panelEl?.setAttribute('aria-hidden', 'false');
    this.fabBtn?.classList.remove('active');
    this.fabBtn?.setAttribute('aria-expanded', 'true');
    if (this.fabIconEl) {
      this.fabIconEl.innerHTML = icon('shield-check', { size: 22 });
    }

    if (this.mode === 'settings') {
      void this.setMode('live');
    } else if (wasClosed) {
      this._onPanelOpened();
    }
    this.onStateChange?.(this.panelState);
  }

  close() {
    if (this.panelState === 'closed') return;
    this.panelState = 'closed';
    this.container.classList.remove('open', 'mode-strip');
    this.panelEl?.classList.remove('open', 'mode-strip');
    this.panelEl?.setAttribute('aria-hidden', 'true');
    this.fabBtn?.classList.remove('active');
    this.fabBtn?.setAttribute('aria-expanded', 'false');
    if (this.fabIconEl) {
      this.fabIconEl.innerHTML = icon('shield-check', { size: 22 });
    }

    // Mantieni vivi in background i 4 flussi live delle telecamere anche a pannello chiuso,
    // così la riapertura di Sicurezza, il Modale camera, la Vista POV 3D e la Calibrazione
    // sono istantanei (0ms) senza mai ricaricare lo stream da zero.
    if (this.mode === 'replay') {
      this.recordingManager?.detachAll?.();
      this.setPlaying(false);
    }
    this.onStateChange?.(this.panelState);
  }

  async _onPanelOpened() {
    this.syncCameraTiles();
    this._refreshStorageHealth();
    this._loadBiometricIdentitiesOptions();
    this._refreshRecentLiveBioEvents();

    if (this.mode === 'live') {
      await this.connectAllLiveStreams();
    } else if (this.mode === 'replay') {
      if (!Number.isFinite(this._loadedTracksStartUnix)) {
        await this.loadHistoricalWindowAround(this.currentUnix);
      }
      await this.bindAllHistoricalSlotsAndSeek(true);
    } else if (this.mode === 'settings') {
      await this._refreshSettingsTabData();
    }
  }

  async _refreshStorageHealth() {
    if (!this.recordingManager) return;
    const summary = await this.recordingManager.getStorageSummary().catch(() => null);
    if (!summary) return;
    const primary = summary.providers?.[0];
    const detailText = summary.configured && primary
      ? (primary.detail || 'Archivio NVR attivo')
      : 'Archivio NVR predisposto • Schermo scuro automatico se assente';
    if (this.storageLabelEl) {
      this.storageLabelEl.textContent = detailText;
    }
    if (this.settingsNvrStatusEl) {
      this.settingsNvrStatusEl.textContent = summary.configured
        ? (primary?.detail || 'Attivo')
        : 'Predisposto (solo live)';
    }
  }

  // --- Modalità Live vs Cronologia vs Impostazioni ---

  async setMode(nextMode, { skipInitialLoad = false } = {}) {
    const mode = nextMode === 'replay' ? 'replay' : nextMode === 'settings' ? 'settings' : 'live';
    const prevMode = this.mode;
    this.mode = mode;

    const isLive = mode === 'live';
    const isReplay = mode === 'replay';
    const isSettings = mode === 'settings';

    this.liveBtn?.classList.toggle('active', isLive);
    this.liveBtn?.setAttribute('aria-selected', String(isLive));
    this.replayBtn?.classList.toggle('active', isReplay);
    this.replayBtn?.setAttribute('aria-selected', String(isReplay));
    this.settingsBtn?.classList.toggle('active', isSettings);
    this.settingsBtn?.setAttribute('aria-selected', String(isSettings));

    this.panelEl?.classList.toggle('mode-replay', isReplay);
    this.panelEl?.classList.toggle('mode-settings', isSettings);
    this.container?.classList.toggle('mode-settings', isSettings);

    if (this.historySectionEl) {
      this.historySectionEl.hidden = !isReplay;
    }
    if (this.settingsSectionEl) {
      this.settingsSectionEl.hidden = !isSettings;
    }
    if (this.panelBodyEl && prevMode !== mode) {
      this.panelBodyEl.scrollTop = 0;
    }
    if (!isReplay) {
      this._closeHitlEditor();
    }
    this._setAdminMessage('', false);

    if (this.stripModeBtn) {
      this.stripModeBtn.classList.toggle('active', !isReplay);
    }
    if (this.stripModeLabel) {
      this.stripModeLabel.textContent = isReplay ? 'REPLAY' : 'LIVE';
    }
    if (this.stripPlayBtn) {
      this.stripPlayBtn.hidden = !isReplay;
    }

    if (isLive) {
      this.setPlaying(false);
      this.recordingManager?.detachAll?.();
      for (const tile of this.tileElements.values()) {
        tile.activeReplayVideoEl = tile.videoEl;
      }

      const backendOnline = Boolean(this.spatialStreamClient?.connected);
      this.trajectoryRenderer?.setLiveMode?.(backendOnline);

      if (this.stripClockEl) {
        this.stripClockEl.textContent = 'LIVE';
      }
      this._updateStatusSummary();
      this._renderLiveBioStrip();

      if (this.panelState !== 'closed') {
        await this.connectAllLiveStreams();
      }
    } else if (isReplay) {
      // Passaggio a Cronologia / Replay Storico
      this.disconnectAllLiveStreams();
      this.trajectoryRenderer?.setLiveMode?.(false);
      this.setEntitiesVisible(true);
      this._renderLiveBioStrip();

      if (!skipInitialLoad) {
        const nowUnix = Math.floor(Date.now() / 1000);
        if (!this._hasAutoLoadedRealHistory) {
          this._hasAutoLoadedRealHistory = true;
          this.currentUnix = nowUnix - 120;
        }
        await this.loadHistoricalWindowAround(this.currentUnix);
      }

      if (this.panelState !== 'closed') {
        await this.bindAllHistoricalSlotsAndSeek(true);
      }
      this._updateReplayClockUI();
      this._updateStatusSummary();
      requestAnimationFrame(() => this.drawDensityCanvas());
    } else {
      // Passaggio a Impostazioni (mantiene vivi eventuali stream Live a costo 0ms su ritorno a Live)
      this.setPlaying(false);
      this.recordingManager?.detachAll?.();
      this._renderLiveBioStrip();
      this._updateStatusSummary();
      await this._refreshSettingsTabData();
    }

    this._modeListeners.forEach((fn) => {
      try {
        fn(this.mode);
      } catch (err) {
        console.warn('[SecurityFabHub] Errore listener onModeChange:', err);
      }
    });
  }

  // --- Live Video Multi-Camera ---

  async connectAllLiveStreams() {
    if (!this.videoStreamManager) return;
    this._liveConnected = true;

    const tasks = [];
    for (const [camId, tile] of this.tileElements.entries()) {
      tasks.push(this._connectLiveTile(camId, tile));
    }
    await Promise.all(tasks);
  }

  async _connectLiveTile(camId, tile) {
    if (!tile || !tile.videoEl) return;

    const streamName = tile.cam.getStreamName('sub');

    // Se è già in corso una connessione per questo tile, attendila senza lanciarne una seconda!
    if (tile._connectPromise) {
      return await tile._connectPromise;
    }

    // Se questo tile ha già uno stream live attivo (WebRTC / MSE / HA Live), riusalo a 0ms senza disconnetterlo!
    const existingProvider = this.videoStreamManager?.getActiveProvider?.(tile.videoEl);
    const isAlreadyLive = Boolean(
      existingProvider &&
      existingProvider.connected &&
      (existingProvider.mode === 'webrtc' || existingProvider.mode === 'mse' || existingProvider.hasLiveHaFrames)
    );
    if (isAlreadyLive) {
      this._setTileDarkState(tile, false);
      this._applyLiveProviderBadge(tile, existingProvider.getStatus());
      tile.videoEl.play?.().catch(() => {});
      return;
    }

    this.disconnectLiveForCamera(camId);

    this._setTileDarkState(tile, false);
    this._setTileBadge(tile, 'CONNESSIONE...', 'connecting');

    const work = (async () => {
      try {
        const provider = await this.videoStreamManager.attachToVideoElement(
          streamName,
          tile.videoEl,
          'auto',
          {
            cameraEntityId: tile.cam.entityId,
            cameraName: tile.cam.id,
            cameraLabel: tile.cam.cameraModel || tile.cam.name,
            cameraIp: tile.cam.cameraIp,
            aspectRatio: tile.cam.aspectRatio,
            isPanoramic180: tile.cam.isPanoramic180,
          }
        );
        if (this.mode !== 'live') {
          this.videoStreamManager.detachFromVideoElement(tile.videoEl);
          return;
        }

        this._applyLiveProviderBadge(tile, provider.getStatus());

        if (typeof provider.onStatusChange === 'function') {
          const unsub = provider.onStatusChange((st) => {
            if (this.mode === 'live') {
              this._applyLiveProviderBadge(tile, st);
            }
          });
          this.liveStreamUnsubs.set(camId, unsub);
        }
      } catch {
        this._setTileBadge(tile, 'OFFLINE', 'offline');
        this._setTileDarkState(tile, true, 'Telecamera non raggiungibile', 'Verifica connessione stream');
      }
    })();

    tile._connectPromise = work;
    try {
      await work;
    } finally {
      if (tile._connectPromise === work) {
        tile._connectPromise = null;
      }
    }
  }

  _applyLiveProviderBadge(tile, status) {
    if (!status) return;
    if (status.mode === 'webrtc') {
      this._setTileBadge(tile, 'WEBRTC LIVE', 'live');
    } else if (status.mode === 'mse') {
      this._setTileBadge(tile, 'MSE LIVE', 'live');
    } else if (status.hasLiveHaFrames) {
      this._setTileBadge(tile, status.isTailscale ? 'HA REMOTO' : 'HA LIVE', 'live');
    } else {
      this._setTileBadge(tile, 'STANDBY', 'standby');
    }
  }

  disconnectLiveForCamera(camId) {
    const unsub = this.liveStreamUnsubs.get(camId);
    if (typeof unsub === 'function') {
      unsub();
      this.liveStreamUnsubs.delete(camId);
    }
    const tile = this.tileElements.get(camId);
    if (tile?.videoEl && this.videoStreamManager) {
      this.videoStreamManager.detachFromVideoElement(tile.videoEl);
    }
  }

  disconnectAllLiveStreams() {
    this._liveConnected = false;
    for (const camId of Array.from(this.tileElements.keys())) {
      this.disconnectLiveForCamera(camId);
    }
  }

  // --- Replay Storico Video + Ricostruzione 3D ---

  async bindAllHistoricalSlotsAndSeek(immediate = true) {
    if (!this.recordingManager) return;

    for (const [camId, tile] of this.tileElements.entries()) {
      this.recordingManager.registerSlot(
        tile.cam.recordingCameraId,
        tile.videoEl,
        (state) => {
          this._handleHistoricalSlotState(tile, state);
        },
        {
          bufferVideoEl: tile.bufferVideoEl || null,
          onActiveVideoChange: (activeEl) => {
            tile.activeReplayVideoEl = activeEl || tile.videoEl;
          },
        }
      );
    }

    this.recordingManager.setPlaybackRate(this.playbackSpeed);
    this.recordingManager.setPlaying(this.isPlaying);
    await this.recordingManager.seekAllToTimestamp(this.currentUnix, { immediate });
  }

  _handleHistoricalSlotState(tile, state) {
    if (!tile || this.mode !== 'replay') return;
    tile.lastReplayState = state;
    if (state.activeVideoEl) {
      tile.activeReplayVideoEl = state.activeVideoEl;
    }
    const tsLabel = formatShortDateTime(state.timestampUnix || this.currentUnix);

    if (state.status === RecordingPlaybackStatus.PLAYING || state.status === RecordingPlaybackStatus.PAUSED) {
      this._setTileDarkState(tile, false);
      const isMainTier = (state.streamTier || state.segment?.streamTier) === 'main';
      const baseLabel = state.status === RecordingPlaybackStatus.PLAYING ? 'REPLAY' : 'PAUSA';
      this._setTileBadge(tile, isMainTier ? `${baseLabel} HD` : baseLabel, isMainTier ? 'replay is-hd' : 'replay');
    } else if (state.status === RecordingPlaybackStatus.LOADING) {
      this._setTileBadge(tile, 'CARICAMENTO', 'connecting');
    } else {
      // Gestione robusta assenza video a quell'ora: schermo nero/scuro pulito
      this._setTileBadge(tile, 'NO VIDEO', 'norec');
      this._setTileDarkState(tile, true, 'Nessuna registrazione a quest\'ora', tsLabel);
    }

    this._replaySlotListeners.forEach((fn) => {
      try {
        fn(tile.cam.id, state);
      } catch (err) {
        console.warn('[SecurityFabHub] Errore listener onReplaySlotStateChange:', err);
      }
    });
  }

  _setTileDarkState(tile, show, title = 'Nessuna registrazione', timeText = '') {
    if (!tile?.darkStateEl) return;
    tile.card.classList.toggle('is-no-recording', Boolean(show));
    tile.darkStateEl.hidden = !show;
    if (show) {
      if (tile.darkTitleEl) tile.darkTitleEl.textContent = title;
      if (tile.darkTimeEl) tile.darkTimeEl.textContent = timeText || formatShortDateTime(this.currentUnix);
    }
  }

  _setTileBadge(tile, text, variant = 'live') {
    if (!tile?.badgeEl) return;
    tile.badgeEl.textContent = text;
    tile.badgeEl.className = `m3-cam-badge ${variant}`;
  }

  async jumpToUnixTimestamp(unixSec, { switchToReplay = true, reloadWindow = true } = {}) {
    this.currentUnix = Math.floor(unixSec);

    if (switchToReplay && this.mode !== 'replay') {
      await this.setMode('replay', { skipInitialLoad: true });
    }

    const outsideWindow = this.currentUnix < this.windowStartUnix || this.currentUnix > this.windowEndUnix;
    if (reloadWindow || outsideWindow) {
      await this.loadHistoricalWindowAround(this.currentUnix);
    } else {
      this._syncDateTimeInputsFromUnix(this.currentUnix);
      this._syncSliderValue();
      if (this._needsTrackSliceReload(this.currentUnix)) {
        await this.loadTracksSliceAround(this.currentUnix);
      }
    }

    this._updateReplayClockUI();
    this._renderReplayFrameAtCurrentUnix();
    if (this.panelState !== 'closed' && this.mode === 'replay') {
      await this.bindAllHistoricalSlotsAndSeek(true);
    }
  }

  _computeTrackSliceBounds(targetUnix) {
    // Su finestre brevi (15m) carica l'intera finestra; su 1h/6h/24h carica un buffer
    // ad alta risoluzione (±15 min) centrato sull'orario richiesto per evitare troncamenti da LIMIT SQLite.
    if (this.windowSpanSec <= 1800) {
      return { sliceStart: this.windowStartUnix, sliceEnd: this.windowEndUnix };
    }
    const halfSlice = 900;
    const sliceStart = Math.max(this.windowStartUnix, Math.floor(targetUnix - halfSlice));
    const sliceEnd = Math.min(this.windowEndUnix, Math.ceil(targetUnix + halfSlice));
    return { sliceStart, sliceEnd };
  }

  _needsTrackSliceReload(targetUnix) {
    if (!Number.isFinite(this._loadedTracksStartUnix) || !Number.isFinite(this._loadedTracksEndUnix)) {
      return true;
    }
    const margin = this.windowSpanSec <= 1800 ? 0 : 45;
    const nearLeft = targetUnix < this._loadedTracksStartUnix + margin && this._loadedTracksStartUnix > this.windowStartUnix;
    const nearRight = targetUnix > this._loadedTracksEndUnix - margin && this._loadedTracksEndUnix < this.windowEndUnix;
    return targetUnix < this._loadedTracksStartUnix || targetUnix > this._loadedTracksEndUnix || nearLeft || nearRight;
  }

  _scheduleSliceReloadIfNeeded(delayMs = 180) {
    if (!this.spatialStreamClient || !this._needsTrackSliceReload(this.currentUnix)) return;
    if (this._sliceReloadTimer) {
      clearTimeout(this._sliceReloadTimer);
      this._sliceReloadTimer = null;
    }
    if (delayMs <= 0) {
      this.loadTracksSliceAround(this.currentUnix);
      return;
    }
    this._sliceReloadTimer = setTimeout(() => {
      this._sliceReloadTimer = null;
      if (this.mode === 'replay') {
        this.loadTracksSliceAround(this.currentUnix);
      }
    }, delayMs);
  }

  async _fetchTracksCentered(targetUnix) {
    if (!this.spatialStreamClient || typeof this.spatialStreamClient.fetchTracks !== 'function') {
      return { tracksRes: null, sliceStart: this.windowStartUnix, sliceEnd: this.windowEndUnix };
    }

    const TRACK_LIMIT = 15000;
    const activeFilters = this._getActiveBioFilterParams();
    let { sliceStart, sliceEnd } = this._computeTrackSliceBounds(targetUnix);
    let tracksRes = await (
      activeFilters
        ? this.spatialStreamClient.fetchTracks(sliceStart, sliceEnd, null, TRACK_LIMIT, activeFilters)
        : this.spatialStreamClient.fetchTracks(sliceStart, sliceEnd, null, TRACK_LIMIT)
    ).catch(() => null);

    // Protezione anti-troncamento: se la prima metà della slice (es. auto parcheggiata tutta la notte)
    // satura il LIMIT prima di raggiungere targetUnix, riesegue una query mirata attorno a targetUnix.
    if (
      tracksRes &&
      Array.isArray(tracksRes.detections) &&
      tracksRes.detections.length >= TRACK_LIMIT - 100
    ) {
      const lastTs = tracksRes.t_max ?? tracksRes.detections[tracksRes.detections.length - 1]?.timestamp;
      if (Number.isFinite(lastTs) && lastTs < targetUnix - 5) {
        sliceStart = Math.max(this.windowStartUnix, Math.floor(targetUnix - 120));
        sliceEnd = Math.min(this.windowEndUnix, Math.ceil(targetUnix + 180));
        const focused = await (
          activeFilters
            ? this.spatialStreamClient.fetchTracks(sliceStart, sliceEnd, null, TRACK_LIMIT, activeFilters)
            : this.spatialStreamClient.fetchTracks(sliceStart, sliceEnd, null, TRACK_LIMIT)
        ).catch(() => null);
        if (focused) {
          tracksRes = focused;
        }
      }
    }

    return { tracksRes, sliceStart, sliceEnd };
  }

  _applyLoadedTracks(tracksRes, sliceStart, sliceEnd) {
    this._loadedTracksStartUnix = sliceStart;
    this._loadedTracksEndUnix = sliceEnd;

    if (tracksRes && Array.isArray(tracksRes.detections) && tracksRes.detections.length > 0) {
      const origin = this.windowStartUnix;
      const mapped = tracksRes.detections.map((d) => ({
        id: d.track_id,
        class: d.class_label,
        identity: d.identity,
        identity_confidence: d.identity_confidence,
        plate: d.plate,
        plate_confidence: d.plate_confidence,
        plate_whitelisted: d.plate_whitelisted,
        plate_owner: d.plate_owner,
        biometric_locked: d.biometric_locked,
        best_crop_id: d.best_crop_id,
        confidence: d.confidence,
        x: d.x,
        y: d.y,
        z: d.z,
        vx: d.vx || 0,
        vz: d.vz || 0,
        t: d.timestamp - origin,
        camera_id: d.camera_sources?.[0] || 'Cam_Carraio',
        camera_sources: d.camera_sources || ['Cam_Carraio'],
      }));

      this.trajectoryRenderer?.loadDetections?.(mapped);
      this._historyRecordCount = mapped.length;
      this._historyEntityCount = new Set(mapped.map((m) => m.id)).size;
      return true;
    }

    this._historyRecordCount = 0;
    this._historyEntityCount = 0;
    this.trajectoryRenderer?.clearHistorical?.();
    return false;
  }

  async loadTracksSliceAround(targetUnix) {
    const seq = ++this._historyLoadSeq;
    const { tracksRes, sliceStart, sliceEnd } = await this._fetchTracksCentered(targetUnix);
    if (seq !== this._historyLoadSeq || this.mode !== 'replay') return;

    if (tracksRes !== null) {
      this._historyBackendOnline = true;
    }
    this._applyLoadedTracks(tracksRes, sliceStart, sliceEnd);
    this._renderReplayFrameAtCurrentUnix();
  }

  async loadHistoricalWindowAround(centerOrEndUnix) {
    const nowUnix = Math.floor(Date.now() / 1000);
    const half = Math.floor(this.windowSpanSec / 2);

    // Se l'orario richiesto è vicino ad adesso, ancoriamo la fine della finestra a 'nowUnix'
    if (nowUnix - centerOrEndUnix <= half) {
      this.windowEndUnix = nowUnix;
      this.windowStartUnix = nowUnix - this.windowSpanSec;
    } else {
      this.windowStartUnix = centerOrEndUnix - half;
      this.windowEndUnix = centerOrEndUnix + half;
    }

    this.currentUnix = Math.max(this.windowStartUnix, Math.min(this.windowEndUnix, centerOrEndUnix));
    this._syncDateTimeInputsFromUnix(this.currentUnix);
    this._syncSliderBounds();
    this._syncSliderValue();

    const seq = ++this._historyLoadSeq;

    // 1. Esegui in parallelo query segmenti NVR, istogramma densità su tutta la finestra e tracce 3D centrate
    //    Nota: le API REST storiche funzionano anche se il WebSocket live è momentaneamente in riconnessione!
    const hasSpatialRest = Boolean(
      this.spatialStreamClient &&
      typeof this.spatialStreamClient.fetchTracks === 'function' &&
      typeof this.spatialStreamClient.fetchTimelineDensity === 'function'
    );

    const [segmentsMap, densityRes, sliceResult, bioEventsRes] = await Promise.all([
      this.recordingManager
        ? this.recordingManager.queryAllSegments(this.windowStartUnix, this.windowEndUnix).catch(() => new Map())
        : Promise.resolve(new Map()),
      hasSpatialRest
        ? this.spatialStreamClient.fetchTimelineDensity(this.windowStartUnix, this.windowEndUnix, 80).catch(() => null)
        : Promise.resolve(null),
      hasSpatialRest
        ? this._fetchTracksCentered(this.currentUnix)
        : Promise.resolve({ tracksRes: null, sliceStart: this.windowStartUnix, sliceEnd: this.windowEndUnix }),
      this._fetchBiometricEventsInWindow(this.windowStartUnix, this.windowEndUnix),
    ]);

    if (seq !== this._historyLoadSeq) return;

    this.recordingSegmentsByCam = segmentsMap || new Map();

    // Aggiorna l'istogramma indipendentemente dal numero di tracce nella slice corrente
    if (densityRes && Array.isArray(densityRes.bins)) {
      this.densityBins = densityRes.bins;
      this._historyDensityTotal = densityRes.bins.reduce((acc, b) => acc + (Number(b?.count) || 0), 0);
    } else {
      this.densityBins = [];
      this._historyDensityTotal = 0;
    }

    this._historyBackendOnline = Boolean(
      densityRes !== null || sliceResult?.tracksRes !== null || this.spatialStreamClient?.connected
    );

    this._applyLoadedTracks(sliceResult?.tracksRes || null, sliceResult.sliceStart, sliceResult.sliceEnd);
    this._applyBiometricEventsWindow(bioEventsRes);
    this._renderReplayFrameAtCurrentUnix();
    requestAnimationFrame(() => this.drawDensityCanvas());
  }

  _renderReplayFrameAtCurrentUnix() {
    const visibleNow = this.trajectoryRenderer?.updateAtTime?.(this.currentUnix - this.windowStartUnix) ?? 0;

    if (this.entityStatsEl) {
      if (!this._historyBackendOnline) {
        this.entityStatsEl.textContent = 'Servizio cronologia 3D non connesso';
      } else if (visibleNow > 0) {
        const word = visibleNow === 1 ? 'oggetto 3D attivo' : 'oggetti 3D attivi';
        this.entityStatsEl.textContent = `${visibleNow} ${word} (${this._historyEntityCount} in fascia)`;
      } else if (this._historyEntityCount > 0) {
        this.entityStatsEl.textContent = `${this._historyEntityCount} entità nella fascia • Sposta sulle barre`;
      } else if (this._historyDensityTotal > 0) {
        this.entityStatsEl.textContent = 'Attività presente • Clicca sulle barre azzurre';
      } else {
        this.entityStatsEl.textContent = 'Nessun passaggio 3D in questa fascia';
      }
    }

    this.drawDensityCanvas();
  }

  _nudgeTime(deltaSec) {
    if (this.mode !== 'replay') {
      this.setMode('replay');
    }
    const nextUnix = this.currentUnix + deltaSec;
    const outOfWindow = nextUnix < this.windowStartUnix || nextUnix > this.windowEndUnix;
    this.jumpToUnixTimestamp(nextUnix, { switchToReplay: true, reloadWindow: outOfWindow });
  }

  setPlaying(playing) {
    this.isPlaying = Boolean(playing);
    const ic = icon(this.isPlaying ? 'pause' : 'play', { size: 16 });
    const icSmall = icon(this.isPlaying ? 'pause' : 'play', { size: 14 });
    if (this.playPauseBtn) this.playPauseBtn.innerHTML = ic;
    if (this.stripPlayBtn) this.stripPlayBtn.innerHTML = icSmall;
    this.recordingManager?.setPlaying?.(this.isPlaying);
  }

  setEntitiesVisible(visible) {
    this.entitiesVisible = Boolean(visible);
    this.trajectoryRenderer?.setEntitiesVisible?.(this.entitiesVisible);

    const icName = this.entitiesVisible ? 'eye' : 'eye-off';
    if (this.entities3dBtn) {
      this.entities3dBtn.classList.toggle('active', this.entitiesVisible);
      this.entities3dBtn.setAttribute('aria-pressed', String(this.entitiesVisible));
      this.entities3dBtn.innerHTML = icon(icName, { size: 16 });
    }
    if (this.stripEntitiesBtn) {
      this.stripEntitiesBtn.classList.toggle('active', this.entitiesVisible);
      this.stripEntitiesBtn.innerHTML = icon(icName, { size: 14 });
    }
    if (this.entitiesVisible && this.mode === 'replay') {
      this._renderReplayFrameAtCurrentUnix();
    }
  }

  /**
   * Chiamato ad ogni frame dal render loop Three.js (`SceneManager.addUpdateCallback`)
   */
  update(delta) {
    if (this.mode === 'live' && this.spatialStreamClient?.connected) {
      this.trajectoryRenderer?.interpolateLive?.(delta);
      return;
    }

    if (this.mode !== 'replay' || !this.isPlaying) return;

    this.currentUnix += delta * this.playbackSpeed;
    if (this.currentUnix > this.windowEndUnix) {
      this.currentUnix = this.windowStartUnix;
    }

    this._syncSliderValue();
    this.trajectoryRenderer?.updateAtTime?.(this.currentUnix - this.windowStartUnix);
    this.recordingManager?.syncPlaybackTick?.(this.currentUnix);

    const nowPerf = performance.now();
    if (nowPerf - this._lastUiSyncPerf > 200) {
      this._lastUiSyncPerf = nowPerf;
      this._updateReplayClockUI();
      this._syncDateTimeInputsFromUnix(this.currentUnix);
      this.drawDensityCanvas();
      this._scheduleSliceReloadIfNeeded(100);
    }
  }

  // --- Helper UI & Canvas ---

  _highlightDayChip(offsetDays) {
    this.container.querySelectorAll('[data-day-offset]').forEach((chip) => {
      const val = parseInt(chip.dataset.dayOffset, 10);
      chip.classList.toggle('active', offsetDays !== null && val === offsetDays);
    });
  }

  _syncDateTimeInputsFromUnix(unixSec) {
    if (!Number.isFinite(unixSec)) return;
    const dt = new Date(unixSec * 1000);
    if (this.dateInput && document.activeElement !== this.dateInput) {
      this.dateInput.value = formatDateInput(dt);
    }
    if (this.timeInput && document.activeElement !== this.timeInput) {
      this.timeInput.value = formatTimeInputHHMM(dt);
    }
  }

  _syncSliderBounds() {
    if (!this.slider) return;
    this.slider.min = '0';
    this.slider.max = String(Math.max(10, this.windowEndUnix - this.windowStartUnix));
    this.slider.step = '1';
  }

  _syncSliderValue() {
    if (!this.slider) return;
    const rel = Math.max(0, this.currentUnix - this.windowStartUnix);
    this.slider.value = String(rel);
  }

  _updateReplayClockUI() {
    const text = formatFullDateTime(this.currentUnix);
    if (this.replayClockEl) this.replayClockEl.textContent = text;
    if (this.stripClockEl && this.mode === 'replay') {
      this.stripClockEl.textContent = formatShortDateTime(this.currentUnix);
    }
  }

  _updateStatusSummary() {
    if (!this.statusSummaryEl) return;
    const count = this.cameraCatalog?.getCameras?.()?.length || 1;
    const camWord = count === 1 ? '1 camera' : `${count} camere`;
    const spatialOnline = Boolean(this.spatialStreamClient?.connected || this._historyBackendOnline);
    if (this.mode === 'live') {
      this.statusSummaryEl.textContent = `${camWord} • ${spatialOnline ? 'Spatial 3D attivo' : 'Live video'}`;
    } else if (this.mode === 'settings') {
      this.statusSummaryEl.textContent = this._isAdmin()
        ? 'Preferenze & Amministrazione'
        : 'Preferenze visualizzazione';
    } else {
      this.statusSummaryEl.textContent = `${camWord} • Cronologia & Replay 3D`;
    }
  }

  drawDensityCanvas() {
    const canvas = this.densityCanvas;
    if (!canvas) return;
    const rectWidth = Math.max(canvas.clientWidth || 0, 260);
    if (canvas.width !== rectWidth) canvas.width = rectWidth;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const span = Math.max(1, this.windowEndUnix - this.windowStartUnix);

    // 1. Fascia inferiore segmenti video registrati: Sub H24 (smeraldo) + Eventi Main HD (ambra)
    if (this.recordingSegmentsByCam && this.recordingSegmentsByCam.size > 0) {
      ctx.fillStyle = 'rgba(16, 185, 129, 0.48)';
      for (const segments of this.recordingSegmentsByCam.values()) {
        for (const seg of segments) {
          if (seg.streamTier === 'main') continue;
          const x0 = Math.max(0, ((seg.startUnix - this.windowStartUnix) / span) * w);
          const x1 = Math.min(w, ((seg.endUnix - this.windowStartUnix) / span) * w);
          if (x1 > x0) {
            ctx.fillRect(x0, h - 4, Math.max(2, x1 - x0), 4);
          }
        }
      }
      ctx.fillStyle = 'rgba(245, 158, 11, 0.92)';
      for (const segments of this.recordingSegmentsByCam.values()) {
        for (const seg of segments) {
          if (seg.streamTier !== 'main' && !seg.hasMotion) continue;
          const x0 = Math.max(0, ((seg.startUnix - this.windowStartUnix) / span) * w);
          const x1 = Math.min(w, ((seg.endUnix - this.windowStartUnix) / span) * w);
          if (x1 > x0) {
            ctx.fillRect(x0, h - 6, Math.max(3, x1 - x0), 6);
          }
        }
      }
    }

    // 2. Istogramma rilevazioni 3D SQLite (ciano con scala logaritmica così anche i passaggi brevi sono evidenti)
    const bins = this.densityBins;
    if (bins && bins.length > 0) {
      const maxCount = Math.max(1, ...bins.map((b) => b.count || 0));
      const logMax = Math.log1p(maxCount);
      const barW = w / bins.length;
      bins.forEach((b, idx) => {
        const count = b.count || 0;
        if (count <= 0) return;
        const ratio = logMax > 0 ? Math.log1p(count) / logMax : 0;
        const barH = Math.max(4, ratio * (h - 7));
        ctx.fillStyle = ratio > 0.55 ? 'rgba(56, 189, 248, 0.95)' : 'rgba(56, 189, 248, 0.58)';
        ctx.fillRect(idx * barW + 0.75, h - 5 - barH, Math.max(2, barW - 1.5), barH);
      });
    }

    // 3. Cursore verticale (playhead) dell'orario selezionato sull'istogramma
    const cursorRatio = Math.max(0, Math.min(1, (this.currentUnix - this.windowStartUnix) / span));
    const cursorX = Math.round(cursorRatio * (w - 2)) + 1;
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(cursorX - 1, 0, 2, h);
  }

  // --- Biometria Live & Filtri Semantici Cronologia ---

  _hasActiveBioFilters() {
    return Boolean(this.bioFilters.identity || this.bioFilters.plate || this.bioFilters.unknownOnly);
  }

  _getActiveBioFilterParams() {
    if (!this._hasActiveBioFilters()) return null;
    return {
      identity: this.bioFilters.identity || '',
      plate: this.bioFilters.plate || '',
      unknownOnly: Boolean(this.bioFilters.unknownOnly),
    };
  }

  async _onBioFiltersChanged() {
    if (this.clearBioFilterBtn) {
      this.clearBioFilterBtn.hidden = !this._hasActiveBioFilters();
    }
    if (this.mode === 'replay') {
      await Promise.all([
        this.loadTracksSliceAround(this.currentUnix),
        this._refreshBiometricEventsForWindow(),
      ]);
    }
  }

  _resolveEventCropUrl(ev) {
    if (!ev) return null;
    if (ev.crop_url) return ev.crop_url;
    if (ev.best_crop_id && typeof this.spatialStreamClient?.getBiometricCropUrl === 'function') {
      return this.spatialStreamClient.getBiometricCropUrl(ev.best_crop_id);
    }
    return null;
  }

  _pushLiveBiometricEvent(ev) {
    if (!ev) return;
    const dedupKey = `${ev.track_id ?? ''}_${ev.modality || ''}`;
    const filtered = this.recentLiveBioEvents.filter(
      (item) => `${item.track_id ?? ''}_${item.modality || ''}` !== dedupKey
    );
    filtered.unshift(ev);
    this.recentLiveBioEvents = filtered.slice(0, 4);
    this._renderLiveBioStrip();
  }

  _renderLiveBioStrip() {
    if (!this.bioLiveStripEl) return;
    if (this.mode !== 'live' || this.recentLiveBioEvents.length === 0) {
      this.bioLiveStripEl.hidden = true;
      this.bioLiveStripEl.innerHTML = '';
      return;
    }

    this.bioLiveStripEl.innerHTML = this.recentLiveBioEvents
      .map((ev) => {
        const isAlpr = ev.modality === 'alpr' || Boolean(ev.plate);
        const rawLabel = isAlpr
          ? (ev.plate_owner ? `${ev.plate || ''} · ${ev.plate_owner}` : ev.plate || 'Targa sconosciuta')
          : (ev.identity || 'Sconosciuto');
        const isAuth = isAlpr
          ? ev.plate_whitelisted === true
          : Boolean(ev.identity && ev.identity !== 'Sconosciuto');
        const isGuest = isAlpr && ev.plate_whitelisted === false;
        const camShort = String(ev.camera_id || '').replace(/^Cam_/i, '');
        const cropUrl = this._resolveEventCropUrl(ev);
        const lockHtml = ev.biometric_locked ? icon('lock', { size: 11 }) : '';
        return `
          <button
            type="button"
            class="m3-bio-chip ${isAuth ? 'is-authorized' : isGuest ? 'is-guest' : ''}"
            data-jump-ts="${Number(ev.timestamp) || 0}"
            title="Vai a questo evento nella Cronologia"
          >
            ${cropUrl ? `<img class="m3-bio-chip-thumb" src="${escapeHtml(cropUrl)}" crossorigin="use-credentials" alt="" loading="lazy" />` : ''}
            <span class="m3-bio-chip-copy">
              <span class="m3-bio-chip-title">${icon(isAlpr ? 'car' : 'user-check', { size: 12 })} <span>${escapeHtml(rawLabel)}</span> ${lockHtml}</span>
              <span class="m3-bio-chip-meta">${escapeHtml(camShort)} · ${escapeHtml(formatShortDateTime(ev.timestamp))}</span>
            </span>
          </button>
        `;
      })
      .join('');
    this.bioLiveStripEl.hidden = false;
  }

  async _loadBiometricIdentitiesOptions() {
    if (!this.identityFilterSelect || typeof this.spatialStreamClient?.fetchBiometricIdentities !== 'function') {
      return;
    }
    const res = await this.spatialStreamClient.fetchBiometricIdentities().catch(() => null);
    if (!res || !Array.isArray(res.identities)) return;

    this.bioIdentitiesList = res.identities;
    const prevValue = this.bioFilters.unknownOnly ? '__unknown__' : this.bioFilters.identity;
    const baseOptions = [
      { value: '', label: 'Tutte le persone' },
      { value: '__unknown__', label: 'Solo sconosciuti' },
    ];
    for (const item of res.identities) {
      if (item?.name) {
        baseOptions.push({ value: String(item.name), label: String(item.name) });
      }
    }

    this.identityFilterSelect.innerHTML = '';
    for (const optCfg of baseOptions) {
      const opt = document.createElement('option');
      opt.value = optCfg.value;
      opt.textContent = optCfg.label;
      this.identityFilterSelect.appendChild(opt);
    }
    if (baseOptions.some((o) => o.value === prevValue)) {
      this.identityFilterSelect.value = prevValue;
    }
  }

  async _refreshRecentLiveBioEvents() {
    if (typeof this.spatialStreamClient?.fetchBiometricEvents !== 'function') return;
    const res = await this.spatialStreamClient.fetchBiometricEvents({ limit: 4 }).catch(() => null);
    if (res && Array.isArray(res.events) && res.events.length > 0 && this.recentLiveBioEvents.length === 0) {
      this.recentLiveBioEvents = res.events.slice(0, 4);
      this._renderLiveBioStrip();
    }
  }

  async _fetchBiometricEventsInWindow(tStart, tEnd) {
    if (typeof this.spatialStreamClient?.fetchBiometricEvents !== 'function') {
      return null;
    }
    return await this.spatialStreamClient
      .fetchBiometricEvents({
        tStart,
        tEnd,
        identity: this.bioFilters.identity || null,
        plate: this.bioFilters.plate || null,
        limit: 40,
      })
      .catch(() => null);
  }

  async _refreshBiometricEventsForWindow() {
    const res = await this._fetchBiometricEventsInWindow(this.windowStartUnix, this.windowEndUnix);
    this._applyBiometricEventsWindow(res);
  }

  _applyBiometricEventsWindow(res) {
    let items = Array.isArray(res?.events) ? res.events : [];
    if (this.bioFilters.unknownOnly) {
      items = items.filter((ev) => !ev.identity && !ev.plate);
    }
    this.historyBioEvents = items;
    this._renderBioEventsList(items);
  }

  _isAdmin() {
    return Boolean(this.haClient?.isAdmin);
  }

  _syncAdminControls() {
    const isAdmin = this._isAdmin();
    if (this.bioAdminToggleBtn) {
      this.bioAdminToggleBtn.hidden = !isAdmin;
      this.bioAdminToggleBtn.disabled = !isAdmin;
      this.bioAdminToggleBtn.style.display = isAdmin ? '' : 'none';
    }
    if (this.settingsResidentNoteEl) {
      this.settingsResidentNoteEl.hidden = isAdmin;
      this.settingsResidentNoteEl.style.display = isAdmin ? 'none' : '';
    }

    for (const btn of [this.adminPlateAddBtn, this.adminReloadGalleryBtn, this.adminPruneCropsBtn]) {
      if (btn) btn.disabled = !isAdmin;
    }
    for (const inp of [this.adminPlateInput, this.adminPlateOwnerInput, this.adminPlateVehicleInput]) {
      if (inp) inp.disabled = !isAdmin;
    }

    if (!isAdmin) {
      this._closeHitlEditor();
      if (this.bioAdminPanelEl) {
        this.bioAdminPanelEl.hidden = true;
        this.bioAdminPanelEl.style.display = 'none';
      }
      if (this.adminPlatesListEl) this.adminPlatesListEl.innerHTML = '';
      if (this.adminIdentitiesListEl) this.adminIdentitiesListEl.innerHTML = '';
      this._setAdminMessage('', false);
    } else {
      if (this.bioAdminPanelEl) {
        this.bioAdminPanelEl.hidden = false;
        this.bioAdminPanelEl.style.display = '';
      }
      if (this.mode === 'settings' && this.panelState !== 'closed') {
        void this._refreshAdminLists();
      }
    }

    if (this.mode === 'settings') {
      this._updateStatusSummary();
    }
    this._renderBioEventsList(this.historyBioEvents);
  }

  async _refreshSettingsTabData() {
    const tasks = [
      this._refreshStorageHealth(),
      this._refreshBiometricsStatusSummary(),
    ];
    if (this._isAdmin()) {
      tasks.push(this._refreshAdminLists());
    }
    await Promise.all(tasks);
  }

  async _refreshBiometricsStatusSummary() {
    if (!this.settingsBioStatusEl) return;
    if (typeof this.spatialStreamClient?.fetchBiometricsStatus !== 'function') {
      this.settingsBioStatusEl.textContent = this.spatialStreamClient?.connected ? 'Connesso' : 'Offline';
      return;
    }
    const status = await this.spatialStreamClient.fetchBiometricsStatus().catch(() => null);
    this._biometricsStatus = status;
    if (!status) {
      this.settingsBioStatusEl.textContent = this.spatialStreamClient?.connected ? 'Attivo' : 'Server offline';
      return;
    }
    const faceReady = Boolean(status.face_ready || status.face_enabled || status.enabled);
    const alprReady = Boolean(status.alpr_ready || status.alpr_enabled || status.enabled);
    const idCount = Number(status.identities_count ?? this.bioIdentitiesList.length ?? 0);
    const plateCount = Number(status.plates_count ?? this.bioPlatesList.length ?? 0);
    if (!faceReady && !alprReady && status.enabled === false) {
      this.settingsBioStatusEl.textContent = 'Disattivo da config';
    } else {
      this.settingsBioStatusEl.textContent = `Attivo · ${idCount} volti · ${plateCount} targhe`;
    }
  }

  _setAdminMessage(text, isError = false) {
    const targets = [this.adminBioMsgEl, this.bioHitlMsgEl].filter(Boolean);
    for (const el of targets) {
      if (!text) {
        el.hidden = true;
        el.textContent = '';
        el.classList.remove('is-error');
      } else {
        el.textContent = String(text);
        el.classList.toggle('is-error', Boolean(isError));
        el.hidden = false;
      }
    }
  }

  _closeHitlEditor() {
    this._activeHitlEvent = null;
    if (this.bioHitlEditorEl) {
      this.bioHitlEditorEl.hidden = true;
      this.bioHitlEditorEl.innerHTML = '';
    }
  }

  _openHitlEditor(ev) {
    if (!this._isAdmin() || !this.bioHitlEditorEl || !ev) return;
    this._activeHitlEvent = ev;
    const isAlpr = ev.modality === 'alpr' || Boolean(ev.plate || ev.plate_raw);
    const cropUrl = this._resolveEventCropUrl(ev);

    if (isAlpr) {
      const prefillPlate = String(ev.plate || ev.plate_raw || '').trim().toUpperCase();
      const prefillOwner = String(ev.plate_owner || '').trim();
      const wlChecked = ev.plate_whitelisted === true;
      this.bioHitlEditorEl.innerHTML = `
        <div class="m3-hitl-head">
          ${cropUrl ? `<img class="m3-hitl-thumb" src="${escapeHtml(cropUrl)}" crossorigin="use-credentials" alt="" />` : ''}
          <span>Assegna o correggi targa (Track #${Number(ev.track_id) || 0})</span>
        </div>
        <div class="m3-hitl-fields">
          <input type="text" id="sec-hitl-plate-input" value="${escapeHtml(prefillPlate)}" placeholder="Targa (es. AB123CD)" maxlength="12" aria-label="Targa" />
          <label class="m3-hitl-check">
            <input type="checkbox" id="sec-hitl-whitelist-check" ${wlChecked ? 'checked' : ''} />
            <span>Aggiungi alla whitelist autorizzata</span>
          </label>
          <input type="text" id="sec-hitl-owner-input" value="${escapeHtml(prefillOwner)}" placeholder="Proprietario (se in whitelist)" maxlength="64" aria-label="Proprietario" />
          <input type="text" id="sec-hitl-vehicle-input" value="" placeholder="Modello veicolo (opzionale)" maxlength="48" aria-label="Veicolo" />
        </div>
        <div class="m3-hitl-actions">
          <button type="button" class="m3-hitl-btn-cancel" id="btn-sec-hitl-cancel">${icon('x', { size: 12 })} <span>Annulla</span></button>
          <button type="button" class="m3-hitl-btn-save" id="btn-sec-hitl-save">${icon('check', { size: 12 })} <span>Salva targa</span></button>
        </div>
      `;
      const wlEl = this.bioHitlEditorEl.querySelector('#sec-hitl-whitelist-check');
      if (wlEl) wlEl.checked = wlChecked;
    } else {
      const prefillId = String(ev.identity || '').trim();
      this.bioHitlEditorEl.innerHTML = `
        <div class="m3-hitl-head">
          ${cropUrl ? `<img class="m3-hitl-thumb" src="${escapeHtml(cropUrl)}" crossorigin="use-credentials" alt="" />` : ''}
          <span>Assegna persona riconosciuta (Track #${Number(ev.track_id) || 0})</span>
        </div>
        <div class="m3-hitl-fields">
          <input type="text" id="sec-hitl-identity-input" value="${escapeHtml(prefillId)}" placeholder="Nome persona (es. Nicola)" maxlength="64" aria-label="Nome persona" />
          <label class="m3-hitl-check">
            <input type="checkbox" id="sec-hitl-enroll-check" checked />
            <span>Aggiungi questo volto alla galleria per futuri riconoscimenti</span>
          </label>
        </div>
        <div class="m3-hitl-actions">
          <button type="button" class="m3-hitl-btn-cancel" id="btn-sec-hitl-cancel">${icon('x', { size: 12 })} <span>Annulla</span></button>
          <button type="button" class="m3-hitl-btn-save" id="btn-sec-hitl-save">${icon('check', { size: 12 })} <span>Salva persona</span></button>
        </div>
      `;
      const enrollEl = this.bioHitlEditorEl.querySelector('#sec-hitl-enroll-check');
      if (enrollEl) enrollEl.checked = true;
    }
    this.bioHitlEditorEl.hidden = false;
  }

  async _submitHitlEditor() {
    if (!this._isAdmin() || !this._activeHitlEvent || typeof this.spatialStreamClient?.assignBiometricEvent !== 'function') {
      return;
    }
    const ev = this._activeHitlEvent;
    const isAlpr = ev.modality === 'alpr' || Boolean(ev.plate || ev.plate_raw);
    let payload;
    if (isAlpr) {
      const plate = String(this.bioHitlEditorEl?.querySelector('#sec-hitl-plate-input')?.value || '').trim().toUpperCase();
      const wlEl = this.bioHitlEditorEl?.querySelector('#sec-hitl-whitelist-check');
      const addToWhitelist = Boolean(wlEl?.checked ?? wlEl?.hasAttribute?.('checked'));
      const ownerName = String(this.bioHitlEditorEl?.querySelector('#sec-hitl-owner-input')?.value || '').trim();
      const vehicleLabel = String(this.bioHitlEditorEl?.querySelector('#sec-hitl-vehicle-input')?.value || '').trim() || null;
      if (!plate) {
        this._setAdminMessage('Inserisci una targa valida', true);
        return;
      }
      if (addToWhitelist && !ownerName) {
        this._setAdminMessage('Inserisci il proprietario per aggiungere la targa alla whitelist', true);
        return;
      }
      payload = {
        plate,
        add_to_whitelist: addToWhitelist,
        owner_name: ownerName || null,
        vehicle_label: vehicleLabel,
      };
    } else {
      const identity = String(this.bioHitlEditorEl?.querySelector('#sec-hitl-identity-input')?.value || '').trim();
      const enrollEl = this.bioHitlEditorEl?.querySelector('#sec-hitl-enroll-check');
      const enrollCrop = enrollEl ? Boolean(enrollEl.checked ?? enrollEl.hasAttribute?.('checked')) : true;
      if (!identity) {
        this._setAdminMessage('Inserisci il nome della persona', true);
        return;
      }
      payload = { identity, enroll_crop: enrollCrop };
    }

    const res = await this.spatialStreamClient.assignBiometricEvent(ev.id, payload).catch(() => null);
    if (!res || res.status !== 'ok') {
      this._setAdminMessage('Salvataggio assegnazione HITL non riuscito', true);
      return;
    }

    this._closeHitlEditor();
    this._setAdminMessage(res.enroll_note || 'Evento biometrico aggiornato e storicizzato', false);
    await Promise.all([
      this._refreshBiometricEventsForWindow(),
      this._loadBiometricIdentitiesOptions(),
      this.mode === 'settings' ? this._refreshAdminLists() : Promise.resolve(),
    ]);
  }

  async _refreshAdminLists() {
    if (!this._isAdmin()) return;
    const [platesRes, idRes] = await Promise.all([
      typeof this.spatialStreamClient?.fetchBiometricPlates === 'function'
        ? this.spatialStreamClient.fetchBiometricPlates().catch(() => null)
        : Promise.resolve(null),
      typeof this.spatialStreamClient?.fetchBiometricIdentities === 'function'
        ? this.spatialStreamClient.fetchBiometricIdentities().catch(() => null)
        : Promise.resolve(null),
    ]);
    if (platesRes && Array.isArray(platesRes.plates)) {
      this.bioPlatesList = platesRes.plates;
      this._renderAdminPlates();
    }
    if (idRes && Array.isArray(idRes.identities)) {
      this.bioIdentitiesList = idRes.identities;
      this._renderAdminIdentities();
    }
  }

  _renderAdminPlates() {
    if (this.adminPlatesCountEl) {
      this.adminPlatesCountEl.textContent = String(this.bioPlatesList.length);
    }
    if (!this.adminPlatesListEl) return;
    if (!this._isAdmin() || this.bioPlatesList.length === 0) {
      this.adminPlatesListEl.innerHTML = '<div class="m3-bio-empty">Nessuna targa autorizzata in whitelist</div>';
      return;
    }
    this.adminPlatesListEl.innerHTML = this.bioPlatesList
      .map((p) => {
        const plate = String(p.plate || '');
        const owner = String(p.owner_name || '');
        const label = p.vehicle_label ? String(p.vehicle_label) : '';
        return `
          <div class="m3-admin-item">
            <div class="m3-admin-item-main">
              <span class="spatial-plate-pill is-authorized"><span class="spatial-plate-eu">I</span><span>${escapeHtml(plate)}</span></span>
              <span class="m3-admin-item-copy">
                <strong>${escapeHtml(owner)}</strong>${label ? `<span class="m3-admin-item-sub"> · ${escapeHtml(label)}</span>` : ''}
              </span>
            </div>
            <button type="button" class="m3-admin-del-btn" data-del-plate="${escapeHtml(plate)}" title="Rimuovi targa ${escapeHtml(plate)}" aria-label="Rimuovi targa ${escapeHtml(plate)}">
              ${icon('x', { size: 14 })}
            </button>
          </div>
        `;
      })
      .join('');
  }

  _renderAdminIdentities() {
    if (this.adminIdentitiesCountEl) {
      this.adminIdentitiesCountEl.textContent = String(this.bioIdentitiesList.length);
    }
    if (!this.adminIdentitiesListEl) return;
    if (!this._isAdmin() || this.bioIdentitiesList.length === 0) {
      this.adminIdentitiesListEl.innerHTML = '<div class="m3-bio-empty">Nessun volto registrato in galleria</div>';
      return;
    }
    this.adminIdentitiesListEl.innerHTML = this.bioIdentitiesList
      .map((item) => {
        const name = String(item.name || '');
        const samples = Number(item.samples_count) || 0;
        const sampleWord = samples === 1 ? '1 campione' : `${samples} campioni`;
        return `
          <div class="m3-admin-item">
            <div class="m3-admin-item-main">
              <span class="m3-admin-avatar-badge" aria-hidden="true">${icon('user-check', { size: 13 })}</span>
              <span class="m3-admin-item-copy">
                <strong>${escapeHtml(name)}</strong>
                <span class="m3-admin-item-sub"> · ${sampleWord}</span>
              </span>
            </div>
            <button type="button" class="m3-admin-del-btn" data-del-identity="${escapeHtml(name)}" title="Rimuovi persona ${escapeHtml(name)}" aria-label="Rimuovi persona ${escapeHtml(name)}">
              ${icon('x', { size: 14 })}
            </button>
          </div>
        `;
      })
      .join('');
  }

  _renderBioEventsList(events) {
    if (!this.bioEventsWrapEl || !this.bioEventsListEl) return;
    const isAdmin = this._isAdmin();
    const hasFilter = this._hasActiveBioFilters();
    if (this.bioEventsCountEl) {
      this.bioEventsCountEl.textContent = String(events.length);
    }

    if (events.length === 0) {
      if (!hasFilter && !isAdmin) {
        this.bioEventsWrapEl.hidden = true;
        this.bioEventsListEl.innerHTML = '';
        return;
      }
      this.bioEventsListEl.innerHTML = '<div class="m3-bio-empty">Nessun evento biometrico corrispondente</div>';
      this.bioEventsWrapEl.hidden = false;
      return;
    }

    this.bioEventsListEl.innerHTML = events
      .map((ev) => {
        const isAlpr = ev.modality === 'alpr' || Boolean(ev.plate || ev.plate_raw);
        const cropUrl = this._resolveEventCropUrl(ev);
        const plateHtml = ev.plate
          ? `<span class="spatial-plate-pill ${ev.plate_whitelisted === true ? 'is-authorized' : ev.plate_whitelisted === false ? 'is-guest' : ''}"><span class="spatial-plate-eu">I</span><span>${escapeHtml(ev.plate)}</span></span>`
          : '';
        const mainText = isAlpr
          ? (ev.plate_owner || (ev.plate ? 'Veicolo' : 'Targa non letta'))
          : (ev.identity || 'Sconosciuto');
        const camShort = String(ev.camera_id || '').replace(/^Cam_/i, '');
        const lockHtml = ev.biometric_locked ? icon('lock', { size: 11 }) : '';
        const reviewedHtml = ev.reviewed_by ? '<span class="m3-bio-reviewed-tag">Verificato</span>' : '';
        const hitlBtnHtml = isAdmin && ev.id
          ? `<button type="button" class="m3-bio-hitl-btn" data-hitl-event-id="${Number(ev.id)}" title="Assegna o correggi riconoscimento (Admin)" aria-label="Assegna riconoscimento">${icon('user-check', { size: 13 })}</button>`
          : '';
        return `
          <div class="m3-bio-event-row">
            <button type="button" class="m3-bio-event-card" data-jump-ts="${Number(ev.timestamp) || 0}">
              ${cropUrl ? `<img class="m3-bio-event-thumb" src="${escapeHtml(cropUrl)}" crossorigin="use-credentials" alt="" loading="lazy" />` : ''}
              <span class="m3-bio-event-body">
                <span class="m3-bio-event-main">${icon(isAlpr ? 'car' : 'user-check', { size: 12 })} <span>${escapeHtml(mainText)}</span> ${plateHtml} ${lockHtml} ${reviewedHtml}</span>
                <span class="m3-bio-event-sub">${escapeHtml(camShort)} · ${escapeHtml(formatFullDateTime(ev.timestamp))}</span>
              </span>
            </button>
            ${hitlBtnHtml}
          </div>
        `;
      })
      .join('');
    this.bioEventsWrapEl.hidden = false;
  }

  dispose() {
    window.removeEventListener('keydown', this._onKeyDown);
    if (this._bioPlateTimer) {
      clearTimeout(this._bioPlateTimer);
      this._bioPlateTimer = null;
    }
    if (typeof this._unsubBioEvents === 'function') {
      this._unsubBioEvents();
      this._unsubBioEvents = null;
    }
    if (typeof this._unsubAutoEvents === 'function') {
      this._unsubAutoEvents();
      this._unsubAutoEvents = null;
    }
    if (typeof this._unsubHaAuth === 'function') {
      this._unsubHaAuth();
      this._unsubHaAuth = null;
    }
    if (this._sliceReloadTimer) {
      clearTimeout(this._sliceReloadTimer);
      this._sliceReloadTimer = null;
    }
    if (this._densityResizeObserver) {
      this._densityResizeObserver.disconnect();
      this._densityResizeObserver = null;
    }
    if (typeof this._unsubCatalog === 'function') {
      this._unsubCatalog();
    }
    this.disconnectAllLiveStreams();
    this.recordingManager?.detachAll?.();
  }

  // --- Controllo Rapido Allarme Famiglia (`sh3d.allarme`) ---

  _isAlarmEntityActiveState(entity) {
    if (!entity) return false;
    const st = String(entity.state ?? '').trim().toLowerCase();
    return Boolean(st && !['off', 'false', '0', 'disarmed', 'disarmato', 'spento', 'idle', 'none'].includes(st));
  }

  _setAlarmEntityState(entity) {
    this._alarmEntity = entity || null;
    const isActive = this._isAlarmEntityActiveState(this._alarmEntity);
    if (this.alarmControlBtn) {
      this.alarmControlBtn.classList.toggle('is-armed', isActive);
      const stText = this._alarmEntity?.state ? ` (${this._alarmEntity.state})` : '';
      this.alarmControlBtn.title = `Gestisci stato allarme sh3d.allarme${stText}`;
    }
    if (this.alarmBtnLabelEl) {
      this.alarmBtnLabelEl.textContent = isActive ? String(this._alarmEntity.state).toUpperCase() : 'Allarme';
    }
    if (this._alarmModalOpen) {
      this._renderAlarmModalBody();
    }
  }

  async refreshAlarmEntity() {
    if (typeof this.spatialStreamClient?.fetchVirtualEntities !== 'function') return null;
    this._alarmLoading = true;
    if (this._alarmModalOpen) this._renderAlarmModalBody();
    const res = await this.spatialStreamClient.fetchVirtualEntities().catch(() => null);
    this._alarmLoading = false;
    if (res && Array.isArray(res.virtual_entities)) {
      const found = res.virtual_entities.find((e) => e.entity_id === this._alarmEntityId) || null;
      this._setAlarmEntityState(found);
      return found;
    }
    if (this._alarmModalOpen) this._renderAlarmModalBody();
    return this._alarmEntity;
  }

  async openAlarmModal() {
    if (!this.alarmModalOverlayEl) return;
    this._alarmModalOpen = true;
    this.container?.classList.add('alarm-modal-open');
    this.alarmModalOverlayEl.hidden = false;
    this.alarmModalOverlayEl.setAttribute('aria-hidden', 'false');
    this._renderAlarmModalBody();
    await this.refreshAlarmEntity();
  }

  closeAlarmModal() {
    if (!this.alarmModalOverlayEl) return;
    this._alarmModalOpen = false;
    this.container?.classList.remove('alarm-modal-open');
    this.alarmModalOverlayEl.hidden = true;
    this.alarmModalOverlayEl.setAttribute('aria-hidden', 'true');
  }

  async _applyAlarmEntityState({ state = null, operation = 'set' } = {}) {
    if (this._alarmBusy || typeof this.spatialStreamClient?.setVirtualEntityState !== 'function') return;
    this._alarmBusy = true;
    this._renderAlarmModalBody();
    try {
      const res = await this.spatialStreamClient.setVirtualEntityState(this._alarmEntityId, {
        state,
        operation,
      });
      if (res?.entity) {
        this._setAlarmEntityState(res.entity);
      }
    } finally {
      this._alarmBusy = false;
      if (this._alarmModalOpen) {
        this._renderAlarmModalBody();
      }
    }
  }

  _renderAlarmModalBody() {
    if (!this.alarmModalBodyEl) return;
    const entity = this._alarmEntity;
    if (this.alarmModalTitleEl) {
      this.alarmModalTitleEl.textContent = entity?.name || 'Allarme Casa';
    }

    if (this._alarmLoading && !entity) {
      this.alarmModalBodyEl.innerHTML = `
        <div class="m3-alarm-empty">
          <div class="m3-alarm-empty-title">Caricamento stato allarme...</div>
        </div>
      `;
      return;
    }

    if (!entity) {
      this.alarmModalBodyEl.innerHTML = `
        <div class="m3-alarm-empty">
          <div class="m3-alarm-empty-icon">${icon('shield-alert', { size: 36 })}</div>
          <div class="m3-alarm-empty-title">Entità <code>sh3d.allarme</code> non ancora creata</div>
          <p class="m3-alarm-empty-sub">
            L'amministratore può crearla da <strong>Impostazioni → Automazioni → Entità</strong> con ID <code>sh3d.allarme</code> (tipo Interruttore ON/OFF, Selettore modalità, ecc.).
          </p>
        </div>
      `;
      return;
    }

    const domain = String(entity.domain || 'switch').toLowerCase();
    const currState = String(entity.state ?? '');
    const isActive = this._isAlarmEntityActiveState(entity);
    const disabledAttr = this._alarmBusy ? 'disabled' : '';

    let controlBlockHtml = '';

    if (domain === 'switch' || domain === 'boolean') {
      const isOn = currState.toLowerCase() === 'on' || currState.toLowerCase() === 'true';
      controlBlockHtml = `
        <div class="m3-alarm-switch-panel ${isOn ? 'is-on' : 'is-off'}">
          <div class="m3-alarm-state-hero">
            <span class="m3-alarm-state-dot ${isOn ? 'on' : 'off'}"></span>
            <span class="m3-alarm-state-text">${isOn ? 'ALLARME ATTIVO (ON)' : 'ALLARME DISATTIVO (OFF)'}</span>
          </div>
          <button
            type="button"
            class="m3-alarm-big-switch ${isOn ? 'checked' : ''}"
            id="btn-alarm-modal-switch"
            role="switch"
            aria-checked="${isOn}"
            aria-label="Attiva o disattiva allarme"
            ${disabledAttr}
          >
            <span class="m3-alarm-big-switch-thumb"></span>
          </button>
          <div class="m3-alarm-action-pair">
            <button
              type="button"
              class="m3-alarm-mode-btn ${isOn ? 'active-danger' : ''}"
              id="btn-alarm-modal-on"
              ${disabledAttr}
            >
              ${icon('shield-alert', { size: 18 })}
              <span>ATTIVA</span>
            </button>
            <button
              type="button"
              class="m3-alarm-mode-btn ${!isOn ? 'active-safe' : ''}"
              id="btn-alarm-modal-off"
              ${disabledAttr}
            >
              ${icon('shield-check', { size: 18 })}
              <span>DISATTIVA</span>
            </button>
          </div>
        </div>
      `;
    } else if (domain === 'select' && Array.isArray(entity.options) && entity.options.length > 0) {
      const optionsHtml = entity.options
        .map((opt) => {
          const isSelected = currState === opt;
          return `
            <button
              type="button"
              class="m3-alarm-option-item ${isSelected ? 'selected' : ''}"
              data-alarm-option="${escapeHtml(opt)}"
              role="radio"
              aria-checked="${isSelected}"
              ${disabledAttr}
            >
              <span class="m3-alarm-option-radio"></span>
              <span class="m3-alarm-option-label">${escapeHtml(opt)}</span>
              ${isSelected ? `<span class="m3-alarm-option-check">${icon('check', { size: 18 })}</span>` : ''}
            </button>
          `;
        })
        .join('');

      controlBlockHtml = `
        <div class="m3-alarm-select-panel">
          <div class="m3-alarm-state-hero">
            <span class="m3-alarm-state-dot ${isActive ? 'on' : 'off'}"></span>
            <span class="m3-alarm-state-text">Stato attuale: <strong>${escapeHtml(currState)}</strong></span>
          </div>
          <div class="m3-alarm-options-list" role="radiogroup" aria-label="Seleziona modalità allarme">
            ${optionsHtml}
          </div>
        </div>
      `;
    } else if (domain === 'number') {
      controlBlockHtml = `
        <div class="m3-alarm-input-panel">
          <div class="m3-alarm-state-hero">
            <span class="m3-alarm-state-dot ${isActive ? 'on' : 'off'}"></span>
            <span class="m3-alarm-state-text">Valore attuale: <strong>${escapeHtml(currState)}</strong></span>
          </div>
          <div class="m3-alarm-input-row">
            <input type="number" step="any" class="m3-alarm-large-input" id="inp-alarm-modal-value" value="${escapeHtml(currState)}" ${disabledAttr} />
            <button type="button" class="m3-alarm-submit-btn" id="btn-alarm-modal-apply" ${disabledAttr}>Applica</button>
          </div>
        </div>
      `;
    } else {
      controlBlockHtml = `
        <div class="m3-alarm-input-panel">
          <div class="m3-alarm-state-hero">
            <span class="m3-alarm-state-dot ${isActive ? 'on' : 'off'}"></span>
            <span class="m3-alarm-state-text">Stato attuale: <strong>${escapeHtml(currState)}</strong></span>
          </div>
          <div class="m3-alarm-input-row">
            <input type="text" class="m3-alarm-large-input" id="inp-alarm-modal-value" value="${escapeHtml(currState)}" ${disabledAttr} />
            <button type="button" class="m3-alarm-submit-btn" id="btn-alarm-modal-apply" ${disabledAttr}>Imposta</button>
          </div>
        </div>
      `;
    }

    this.alarmModalBodyEl.innerHTML = controlBlockHtml;

    this.alarmModalBodyEl.querySelector('#btn-alarm-modal-switch')?.addEventListener('click', () => {
      void this._applyAlarmEntityState({ operation: 'toggle' });
    });
    this.alarmModalBodyEl.querySelector('#btn-alarm-modal-on')?.addEventListener('click', () => {
      void this._applyAlarmEntityState({ state: 'on', operation: 'turn_on' });
    });
    this.alarmModalBodyEl.querySelector('#btn-alarm-modal-off')?.addEventListener('click', () => {
      void this._applyAlarmEntityState({ state: 'off', operation: 'turn_off' });
    });
    this.alarmModalBodyEl.querySelectorAll('[data-alarm-option]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const nextOpt = btn.dataset.alarmOption;
        if (nextOpt !== undefined) {
          void this._applyAlarmEntityState({ state: nextOpt, operation: 'set' });
        }
      });
    });
    this.alarmModalBodyEl.querySelector('#btn-alarm-modal-apply')?.addEventListener('click', () => {
      const val = this.alarmModalBodyEl.querySelector('#inp-alarm-modal-value')?.value ?? '';
      void this._applyAlarmEntityState({ state: val, operation: 'set' });
    });
  }
}
