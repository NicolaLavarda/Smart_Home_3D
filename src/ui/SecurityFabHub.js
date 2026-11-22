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
    this.onStateChange = typeof onStateChange === 'function' ? onStateChange : null;

    // Stato UI: 'closed' | 'expanded' | 'strip'
    this.panelState = 'closed';
    // Modalità: 'live' | 'replay'
    this.mode = 'live';

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

    this._onKeyDown = (e) => {
      if (e.key === 'Escape' && this.panelState === 'expanded') {
        this.close();
      }
    };

    this.initUI();
    this.bindEvents();
    this.bindSpatialClient();
    this.syncCameraTiles();

    if (this.cameraCatalog && typeof this.cameraCatalog.onChange === 'function') {
      this._unsubCatalog = this.cameraCatalog.onChange(() => {
        this.syncCameraTiles();
        if (this.panelState !== 'closed') {
          if (this.mode === 'live') this.connectAllLiveStreams();
          else this.bindAllHistoricalSlotsAndSeek(true);
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
      videoEl: tile.videoEl,
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

          <div class="m3-segmented" role="tablist" aria-label="Modalità telecamere e 3D">
            <button type="button" class="m3-seg-btn active" id="btn-sec-mode-live" role="tab" aria-selected="true">
              <span class="m3-live-dot" aria-hidden="true"></span>
              <span>Live</span>
            </button>
            <button type="button" class="m3-seg-btn" id="btn-sec-mode-replay" role="tab" aria-selected="false">
              ${icon('history', { size: 14 })}
              <span>Cronologia</span>
            </button>
          </div>

          <div class="m3-sec-header-actions">
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

        <!-- Sezione Video Multi-Camera (rimane montata e fluida tra espanso e striscia!) -->
        <div class="m3-sec-cameras-viewport" id="sec-cameras-viewport">
          <div class="m3-sec-cameras-track" id="sec-cameras-track"></div>
        </div>

        <!-- Sezione Cronologia & Ricostruzione 3D (visibile solo in modalità Cronologia) -->
        <div class="m3-sec-history-section" id="sec-history-section" hidden>
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

          <div class="m3-storage-footer" id="sec-storage-footer">
            ${icon('hard-drive', { size: 13 })}
            <span id="sec-storage-label">Archivio NVR predisposto • Pronto per HDD PC o SD camera</span>
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
    `;

    this.panelEl = this.container.querySelector('#m3-security-panel');
    this.fabBtn = this.container.querySelector('#btn-security-fab');
    this.fabIconEl = this.container.querySelector('#sec-fab-icon');
    this.fabCountEl = this.container.querySelector('#sec-fab-cam-count');
    this.camerasTrackEl = this.container.querySelector('#sec-cameras-track');
    this.statusSummaryEl = this.container.querySelector('#sec-status-summary');

    this.liveBtn = this.container.querySelector('#btn-sec-mode-live');
    this.replayBtn = this.container.querySelector('#btn-sec-mode-replay');
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

    this.stripExpandBtn?.addEventListener('click', () => this.openExpanded());

    this.liveBtn?.addEventListener('click', () => this.setMode('live'));
    this.replayBtn?.addEventListener('click', () => this.setMode('replay'));
    this.stripModeBtn?.addEventListener('click', () => {
      this.setMode(this.mode === 'live' ? 'replay' : 'live');
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
  }

  /**
   * Crea o aggiorna i riquadri video per tutte le telecamere nel CameraCatalog.
   * Ogni riquadro mantiene il proprio aspect-ratio nativo (es. 16:9 o 180° panoramico).
   */
  syncCameraTiles() {
    if (!this.camerasTrackEl || !this.cameraCatalog) return;

    const cameras = this.cameraCatalog.getCameras();
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

    // Aggiungi o aggiorna card per ogni telecamera
    cameras.forEach((cam) => {
      if (this.tileElements.has(cam.id)) {
        const existing = this.tileElements.get(cam.id);
        existing.cam = cam;
        existing.card.style.setProperty('--cam-aspect', String(cam.aspectRatio));
        existing.card.classList.toggle('is-panoramic', cam.isPanoramic180);
        return;
      }

      const card = document.createElement('article');
      card.className = `m3-cam-tile${cam.isPanoramic180 ? ' is-panoramic' : ''}`;
      card.dataset.cameraId = cam.id;
      card.style.setProperty('--cam-aspect', String(cam.aspectRatio));

      card.innerHTML = `
        <video class="m3-cam-video" autoplay muted playsinline crossorigin="use-credentials"></video>
        <div class="m3-cam-dark-state" hidden>
          <span class="m3-dark-icon">${icon('video-off', { size: 22 })}</span>
          <span class="m3-dark-title">Nessuna registrazione</span>
          <span class="m3-dark-time">--:--:--</span>
        </div>
        <div class="m3-cam-overlay-top">
          <span class="m3-cam-name">${cam.shortName}${cam.isPanoramic180 ? ' 180°' : ''}</span>
          <span class="m3-cam-badge live">STANDBY</span>
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
      const badgeEl = card.querySelector('.m3-cam-badge');
      const darkStateEl = card.querySelector('.m3-cam-dark-state');
      const darkTimeEl = card.querySelector('.m3-dark-time');
      const darkTitleEl = card.querySelector('.m3-dark-title');

      // Aggiorna dinamicamente il rapporto d'aspetto reale appena il browser decodifica i metadati video
      // (garantisce 0 tagli sia per 16:9 sia per 180° panoramici 32:9 / 3.2:1!)
      videoEl.addEventListener('loadedmetadata', () => {
        if (videoEl.videoWidth > 0 && videoEl.videoHeight > 0) {
          const naturalAspect = videoEl.videoWidth / videoEl.videoHeight;
          if (Number.isFinite(naturalAspect) && naturalAspect > 0.4 && naturalAspect < 6.0) {
            card.style.setProperty('--cam-aspect', naturalAspect.toFixed(4));
            card.classList.toggle('is-panoramic', naturalAspect >= 2.2);
          }
        }
      });

      card.querySelector('[data-cam-action="pov"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        this._flyToCamera3D(cam);
      });

      card.querySelector('[data-cam-action="details"]')?.addEventListener('click', (e) => {
        e.stopPropagation();
        if (cam.entityId && this.deviceModals?.open) {
          if (this.panelState === 'expanded' && window.innerWidth <= 1024) {
            this.minimizeToStrip();
          }
          this.deviceModals.open(cam.entityId);
        }
      });

      this.camerasTrackEl.appendChild(card);
      this.tileElements.set(cam.id, {
        cam,
        card,
        videoEl,
        badgeEl,
        darkStateEl,
        darkTimeEl,
        darkTitleEl,
        lastReplayState: null,
      });
    });

    this.camerasTrackEl.dataset.camCount = String(cameras.length);
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

    if (wasClosed) {
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

    // Libera banda e risorse video quando chiuso
    this.disconnectAllLiveStreams();
    this.recordingManager?.detachAll?.();
    this.setPlaying(false);
    this.onStateChange?.(this.panelState);
  }

  async _onPanelOpened() {
    this.syncCameraTiles();
    this._refreshStorageHealth();

    if (this.mode === 'live') {
      await this.connectAllLiveStreams();
    } else {
      if (!Number.isFinite(this._loadedTracksStartUnix)) {
        await this.loadHistoricalWindowAround(this.currentUnix);
      }
      await this.bindAllHistoricalSlotsAndSeek(true);
    }
  }

  async _refreshStorageHealth() {
    if (!this.recordingManager || !this.storageLabelEl) return;
    const summary = await this.recordingManager.getStorageSummary().catch(() => null);
    if (!summary) return;
    const primary = summary.providers?.[0];
    if (summary.configured && primary) {
      this.storageLabelEl.textContent = primary.detail || 'Archivio NVR attivo';
    } else {
      this.storageLabelEl.textContent = 'Archivio NVR predisposto • Schermo scuro automatico se assente';
    }
  }

  // --- Modalità Live vs Cronologia (Replay Storico) ---

  async setMode(nextMode, { skipInitialLoad = false } = {}) {
    const mode = nextMode === 'replay' ? 'replay' : 'live';
    this.mode = mode;

    const isLive = mode === 'live';
    this.liveBtn?.classList.toggle('active', isLive);
    this.liveBtn?.setAttribute('aria-selected', String(isLive));
    this.replayBtn?.classList.toggle('active', !isLive);
    this.replayBtn?.setAttribute('aria-selected', String(!isLive));
    this.panelEl?.classList.toggle('mode-replay', !isLive);
    if (this.historySectionEl) {
      this.historySectionEl.hidden = isLive;
    }

    if (this.stripModeBtn) {
      this.stripModeBtn.classList.toggle('active', isLive);
    }
    if (this.stripModeLabel) {
      this.stripModeLabel.textContent = isLive ? 'LIVE' : 'REPLAY';
    }
    if (this.stripPlayBtn) {
      this.stripPlayBtn.hidden = isLive;
    }

    if (isLive) {
      this.setPlaying(false);
      this.recordingManager?.detachAll?.();

      const backendOnline = Boolean(this.spatialStreamClient?.connected);
      this.trajectoryRenderer?.setLiveMode?.(backendOnline);

      if (this.stripClockEl) {
        this.stripClockEl.textContent = 'LIVE';
      }
      this._updateStatusSummary();

      if (this.panelState !== 'closed') {
        await this.connectAllLiveStreams();
      }
    } else {
      // Passaggio a Cronologia / Replay Storico
      this.disconnectAllLiveStreams();
      this.trajectoryRenderer?.setLiveMode?.(false);
      this.setEntitiesVisible(true);

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
    this.disconnectLiveForCamera(camId);

    this._setTileDarkState(tile, false);
    this._setTileBadge(tile, 'CONNESSIONE...', 'connecting');

    // In griglia/striscia multi-camera preferiamo sub stream se presente per latenza ultra-bassa e consumi ridotti
    const streamName = tile.cam.getStreamName('sub');
    try {
      const provider = await this.videoStreamManager.attachToVideoElement(
        streamName,
        tile.videoEl,
        'auto',
        { cameraEntityId: tile.cam.entityId }
      );
      if (this.mode !== 'live' || this.panelState === 'closed') {
        this.videoStreamManager.detachFromVideoElement(tile.videoEl);
        return;
      }

      this._applyLiveProviderBadge(tile, provider.getStatus());

      if (typeof provider.onStatusChange === 'function') {
        const unsub = provider.onStatusChange((st) => {
          if (this.mode === 'live' && this.panelState !== 'closed') {
            this._applyLiveProviderBadge(tile, st);
          }
        });
        this.liveStreamUnsubs.set(camId, unsub);
      }
    } catch {
      this._setTileBadge(tile, 'OFFLINE', 'offline');
      this._setTileDarkState(tile, true, 'Telecamera non raggiungibile', 'Verifica connessione stream');
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
      this.recordingManager.registerSlot(tile.cam.recordingCameraId, tile.videoEl, (state) => {
        this._handleHistoricalSlotState(tile, state);
      });
    }

    this.recordingManager.setPlaybackRate(this.playbackSpeed);
    this.recordingManager.setPlaying(this.isPlaying);
    await this.recordingManager.seekAllToTimestamp(this.currentUnix, { immediate });
  }

  _handleHistoricalSlotState(tile, state) {
    if (!tile || this.mode !== 'replay') return;
    tile.lastReplayState = state;
    const tsLabel = formatShortDateTime(state.timestampUnix || this.currentUnix);

    if (state.status === RecordingPlaybackStatus.PLAYING || state.status === RecordingPlaybackStatus.PAUSED) {
      this._setTileDarkState(tile, false);
      this._setTileBadge(tile, state.status === RecordingPlaybackStatus.PLAYING ? 'REPLAY' : 'PAUSA', 'replay');
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
    let { sliceStart, sliceEnd } = this._computeTrackSliceBounds(targetUnix);
    let tracksRes = await this.spatialStreamClient
      .fetchTracks(sliceStart, sliceEnd, null, TRACK_LIMIT)
      .catch(() => null);

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
        const focused = await this.spatialStreamClient
          .fetchTracks(sliceStart, sliceEnd, null, TRACK_LIMIT)
          .catch(() => null);
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
        confidence: d.confidence,
        x: d.x,
        y: d.y,
        z: d.z,
        vx: d.vx || 0,
        vz: d.vz || 0,
        t: d.timestamp - origin,
        camera_id: d.camera_sources?.[0] || 'Cam_Carraio',
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

    const [segmentsMap, densityRes, sliceResult] = await Promise.all([
      this.recordingManager
        ? this.recordingManager.queryAllSegments(this.windowStartUnix, this.windowEndUnix).catch(() => new Map())
        : Promise.resolve(new Map()),
      hasSpatialRest
        ? this.spatialStreamClient.fetchTimelineDensity(this.windowStartUnix, this.windowEndUnix, 80).catch(() => null)
        : Promise.resolve(null),
      hasSpatialRest
        ? this._fetchTracksCentered(this.currentUnix)
        : Promise.resolve({ tracksRes: null, sliceStart: this.windowStartUnix, sliceEnd: this.windowEndUnix }),
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

    // 1. Fascia inferiore segmenti video registrati (verde smeraldo)
    if (this.recordingSegmentsByCam && this.recordingSegmentsByCam.size > 0) {
      ctx.fillStyle = 'rgba(16, 185, 129, 0.55)';
      for (const segments of this.recordingSegmentsByCam.values()) {
        for (const seg of segments) {
          const x0 = Math.max(0, ((seg.startUnix - this.windowStartUnix) / span) * w);
          const x1 = Math.min(w, ((seg.endUnix - this.windowStartUnix) / span) * w);
          if (x1 > x0) {
            ctx.fillRect(x0, h - 4, Math.max(2, x1 - x0), 4);
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

  dispose() {
    window.removeEventListener('keydown', this._onKeyDown);
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
}
