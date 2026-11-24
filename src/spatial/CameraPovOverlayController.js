import * as THREE from 'three';
import { icon } from '../ui/icons.js';
import { RecordingPlaybackStatus } from '../video/recordings/index.js';

const DEFAULT_POV_OPACITY = 0.48;

/**
 * CameraPovOverlayController
 *
 * Gestisce automaticamente la sovraimpressione semitrasparente del flusso video
 * (Live o Replay storico in base alla modalità impostata in SecurityFabHub)
 * ogni volta che l'utente aggancia la vista POV di una qualsiasi telecamera,
 * e la rimuove istantaneamente non appena l'utente esce dalla vista POV.
 *
 * Collabora senza conflitti con CalibrationAssistantUI (che prende il possesso
 * esclusivo dell'overlay durante la calibrazione ottica).
 */
export class CameraPovOverlayController {
  constructor({
    cameraController,
    cameraProjector,
    videoStreamManager,
    recordingManager = null,
    cameraCatalog = null,
    securityFabHub = null,
    calibrationAssistant = null,
    haClient = null,
    assetLoader = null,
    uiLayer = null,
    defaultOpacity = DEFAULT_POV_OPACITY,
  } = {}) {
    this.cameraController = cameraController || null;
    this.cameraProjector = cameraProjector || null;
    this.videoStreamManager = videoStreamManager || null;
    this.recordingManager = recordingManager || null;
    this.cameraCatalog = cameraCatalog || null;
    this.securityFabHub = securityFabHub || null;
    this.calibrationAssistant = calibrationAssistant || null;
    this.haClient = haClient || null;
    this.assetLoader = assetLoader || null;
    this.uiLayer = uiLayer || (typeof document !== 'undefined' ? document.querySelector('.ui-layer') || document.body : null);

    this.opacity = THREE.MathUtils.clamp(Number(defaultOpacity) || DEFAULT_POV_OPACITY, 0, 1);
    this.activeCameraName = null;
    this.activeSourceMode = null; // 'live' | 'replay'
    this.preferredLiveQuality = 'main'; // 'main' (con preview/fallback sub istantaneo) | 'sub' (fluido WebRTC)
    this._effectiveLiveQuality = 'main';
    this._povDocked = false;
    this._liveTextureEntry = null;
    this._liveStreamName = null;
    this._previewTextureActive = false;
    this._replayTexture = null;
    this._replayBoundVideoEl = null;
    this._replayAuxSlotKey = null;
    this._replayAuxVideoEl = null;
    this._replayBoundVideoEl = null;
    this._replayHasVideo = false;
    this._suspendedForCalibration = false;
    this._attachSeq = 0;

    this.hudEl = null;
    this._unsubs = [];

    this._bindSources();
  }

  _bindSources() {
    if (typeof this.cameraController?.onPovChange === 'function') {
      this._unsubs.push(
        this.cameraController.onPovChange((evt) => {
          this._handlePovChange(evt);
        })
      );
    }

    if (typeof this.securityFabHub?.onModeChange === 'function') {
      this._unsubs.push(
        this.securityFabHub.onModeChange((mode) => {
          if (this.activeCameraName && !this._isCalibrationActive()) {
            this._activateOverlayForCamera(this.activeCameraName, mode);
          }
        })
      );
    }

    if (typeof this.securityFabHub?.onReplaySlotStateChange === 'function') {
      this._unsubs.push(
        this.securityFabHub.onReplaySlotStateChange((camId, state) => {
          if (!this.activeCameraName || this.activeSourceMode !== 'replay' || this._isCalibrationActive()) return;
          if (camId !== this.activeCameraName) return;
          if (state?.activeVideoEl && state.activeVideoEl !== this._replayBoundVideoEl) {
            this._swapReplayOverlayVideoElement(this.activeCameraName, state.activeVideoEl);
          }
          this._applyReplayAvailabilityState(state);
        })
      );
    }
  }

  _isCalibrationActive() {
    return Boolean(this._suspendedForCalibration || this.calibrationAssistant?.isOpen);
  }

  _getCurrentSecurityMode() {
    return this.securityFabHub?.mode === 'replay' ? 'replay' : 'live';
  }

  _getCameraInfo(cameraName) {
    const manifestCam = this.assetLoader?.manifest?.cameras?.[cameraName] || null;
    const catalogCam = this.cameraCatalog?.getCameraById?.(cameraName) || null;
    const slug = String(cameraName || 'carraio').replace(/^Cam_/i, '').toLowerCase() || 'carraio';

    const mainStream =
      manifestCam?.stream_id ||
      catalogCam?.mainStream ||
      (cameraName === 'Cam_Carraio' ? 'carraio_main' : `${slug}_main`);

    const subStream =
      manifestCam?.sub_stream_id ||
      catalogCam?.subStream ||
      (cameraName === 'Cam_Carraio' ? 'carraio_sub' : `${slug}_sub`);

    const shortName =
      catalogCam?.shortName ||
      (cameraName === 'Cam_Carraio'
        ? 'Carraio'
        : String(manifestCam?.ha_label || cameraName)
            .replace(/^Telecamera\s+/i, '')
            .replace(/\s*\(.*?\)\s*/g, '')
            .trim() || cameraName);

    const entityId =
      manifestCam?.ha_camera_entity ||
      catalogCam?.entityId ||
      (cameraName === 'Cam_Carraio' ? 'camera.carraio_scorrevole' : `camera.${slug}`);

    const cameraLabel =
      manifestCam?.ha_label ||
      catalogCam?.name ||
      manifestCam?.camera_model ||
      shortName;

    const cameraIp = manifestCam?.camera_ip || catalogCam?.cameraIp || '';
    const recordingCameraId = catalogCam?.recordingCameraId || cameraName;

    return {
      cameraName,
      shortName,
      mainStream,
      subStream,
      entityId,
      cameraLabel,
      cameraIp,
      recordingCameraId,
    };
  }

  _handlePovChange(evt) {
    if (!evt) return;
    const { cameraName, phase, previousCameraName, forCalibration } = evt;

    if (phase === 'exited') {
      this.deactivate(previousCameraName || this.activeCameraName);
      return;
    }

    if (forCalibration || this._isCalibrationActive()) {
      this.deactivate(previousCameraName || this.activeCameraName);
      return;
    }

    const mode = this._getCurrentSecurityMode();

    if (phase === 'entering' && cameraName) {
      if (previousCameraName && previousCameraName !== cameraName) {
        this.deactivate(previousCameraName);
      }
      // Pre-acquisisce lo stream live GIA' durante il volo camera (1.25s) così all'arrivo l'overlay appare a 0ms!
      if (mode === 'live') {
        this._povDocked = false;
        this._activateOverlayForCamera(cameraName, 'live', { docked: false });
      }
      return;
    }

    if (phase === 'active' && cameraName) {
      this._povDocked = true;
      // Se stavamo già pre-acquisendo questa esatta telecamera in live durante 'entering', rivela subito senza ricaricare!
      if (this.activeCameraName === cameraName && this.activeSourceMode === mode) {
        const info = this._getCameraInfo(cameraName);
        this._ensureHudDOM();
        this._showHud(info, mode, mode === 'replay' ? 'loading' : 'live');
        if (mode === 'live' && (this._liveTextureEntry || this._previewTextureActive)) {
          this.cameraProjector?.setOverlayPOVMode?.(cameraName, true, this.opacity);
          this._updateHudModeBadge('live', 'LIVE');
        }
        return;
      }
      this._activateOverlayForCamera(cameraName, mode, { docked: true });
    }
  }

  /**
   * Chiamato quando SecurityFabHub cambia stato pannello (closed <-> strip <-> expanded)
   * per riagganciare il sorgente replay se l'utente chiude/apre il pannello restando in POV.
   */
  handleSecurityPanelStateChange() {
    if (!this.activeCameraName || this.activeSourceMode !== 'replay' || this._isCalibrationActive()) return;
    this._activateOverlayForCamera(this.activeCameraName, 'replay', { docked: this._povDocked });
  }

  suspendForCalibration() {
    this._suspendedForCalibration = true;
    this._teardownActiveResources({ hideProjectorOverlay: false });
    this._hideHud();
  }

  resumeAfterCalibration() {
    this._suspendedForCalibration = false;
  }

  async _activateOverlayForCamera(cameraName, mode = 'live', { docked = true } = {}) {
    const seq = ++this._attachSeq;
    const targetMode = mode === 'replay' ? 'replay' : 'live';

    if (this.activeCameraName && this.activeCameraName !== cameraName) {
      this._teardownActiveResources({ hideProjectorOverlay: true });
    } else {
      this._teardownActiveResources({ hideProjectorOverlay: false });
    }

    this.activeCameraName = cameraName;
    this.activeSourceMode = targetMode;
    this._povDocked = Boolean(docked);

    const info = this._getCameraInfo(cameraName);
    if (this._povDocked) {
      this._ensureHudDOM();
      this._showHud(info, targetMode, targetMode === 'replay' ? 'loading' : 'live');
    }

    if (targetMode === 'live') {
      await this._attachLiveOverlay(info, seq);
    } else {
      await this._attachReplayOverlay(info, seq);
    }
  }

  async _attachLiveOverlay(info, seq) {
    if (!this.videoStreamManager || !this.cameraProjector) return;
    const requestedStream = this.preferredLiveQuality === 'sub' ? info.subStream : info.mainStream;
    this._effectiveLiveQuality = this.preferredLiveQuality;
    this._syncHudQualityButton();

    try {
      const entry = await this.videoStreamManager.acquireVideoTexture(requestedStream, 'auto', {
        cameraEntityId: info.entityId,
        cameraName: info.cameraName,
        cameraLabel: info.cameraLabel,
        cameraIp: info.cameraIp,
        onImmediateTexture: (previewEntry) => {
          if (
            seq !== this._attachSeq ||
            this._isCalibrationActive() ||
            this.activeCameraName !== info.cameraName ||
            this.activeSourceMode !== 'live'
          ) {
            return;
          }
          this._previewTextureActive = true;
          this.cameraProjector.attachOverlayTexture(info.cameraName, previewEntry.texture);
          if (this._povDocked) {
            this.cameraProjector.setOverlayPOVMode(info.cameraName, true, this.opacity);
            this._updateHudModeBadge('live', 'LIVE');
          }
        },
      });

      if (seq !== this._attachSeq || this._isCalibrationActive() || this.activeCameraName !== info.cameraName || this.activeSourceMode !== 'live') {
        this.videoStreamManager.releaseVideoTexture(requestedStream);
        return;
      }

      this._previewTextureActive = false;
      this._liveTextureEntry = entry;
      this._liveStreamName = requestedStream;
      this._effectiveLiveQuality = entry.isFallbackToSub || requestedStream === info.subStream ? 'sub' : 'main';
      this._syncHudQualityButton();
      this.cameraProjector.attachOverlayTexture(info.cameraName, entry.texture);
      if (this._povDocked) {
        this.cameraProjector.setOverlayPOVMode(info.cameraName, true, this.opacity);
        this._updateHudModeBadge('live', 'LIVE');
      }
    } catch (err) {
      if (seq === this._attachSeq) {
        console.warn(`[CameraPovOverlayController] Impossibile collegare stream live '${requestedStream}':`, err);
        this._updateHudModeBadge('norec', 'OFFLINE');
      }
    }
  }

  async _attachReplayOverlay(info, seq) {
    if (!this.cameraProjector) return;

    const tileInfo = this.securityFabHub?.getReplayTileInfo?.(info.cameraName) || null;
    if (tileInfo?.videoEl) {
      const tex = this._createVideoTexture(tileInfo.videoEl);
      if (seq !== this._attachSeq || this._isCalibrationActive() || this.activeCameraName !== info.cameraName || this.activeSourceMode !== 'replay') {
        tex.dispose();
        return;
      }
      this._replayTexture = tex;
      this._replayBoundVideoEl = tileInfo.videoEl;
      this.cameraProjector.attachOverlayTexture(info.cameraName, tex);
      this._applyReplayAvailabilityState(tileInfo.state || { status: tileInfo.status });
      return;
    }

    // Fallback: pannello Sicurezza chiuso ma modalità impostata su Cronologia -> crea slot ausiliario sincronizzato
    if (!this.recordingManager || typeof document === 'undefined') {
      this._applyReplayAvailabilityState({ status: RecordingPlaybackStatus.NO_RECORDING });
      return;
    }

    const videoEl = document.createElement('video');
    videoEl.muted = true;
    videoEl.playsInline = true;
    videoEl.crossOrigin = 'use-credentials';

    const bufferEl = document.createElement('video');
    bufferEl.muted = true;
    bufferEl.playsInline = true;
    bufferEl.crossOrigin = 'use-credentials';

    const slotKey = `pov_overlay:${info.cameraName}`;
    this._replayAuxSlotKey = slotKey;
    this._replayAuxVideoEl = videoEl;
    this._replayBoundVideoEl = videoEl;

    const tex = this._createVideoTexture(videoEl);
    this._replayTexture = tex;
    this.cameraProjector.attachOverlayTexture(info.cameraName, tex);

    this.recordingManager.registerSlot(
      slotKey,
      videoEl,
      (state) => {
        if (seq !== this._attachSeq || this.activeCameraName !== info.cameraName || this.activeSourceMode !== 'replay') return;
        if (state?.activeVideoEl && state.activeVideoEl !== this._replayBoundVideoEl) {
          this._swapReplayOverlayVideoElement(info.cameraName, state.activeVideoEl);
        }
        this._applyReplayAvailabilityState(state);
      },
      {
        cameraId: info.recordingCameraId,
        bufferVideoEl: bufferEl,
      }
    );

    const targetUnix = Number.isFinite(this.securityFabHub?.currentUnix)
      ? this.securityFabHub.currentUnix
      : Math.floor(Date.now() / 1000) - 120;

    if (typeof this.recordingManager.syncSlotToTimestamp === 'function') {
      await this.recordingManager.syncSlotToTimestamp(slotKey, targetUnix);
    } else {
      await this.recordingManager.seekAllToTimestamp?.(targetUnix, { immediate: true });
    }
  }

  _swapReplayOverlayVideoElement(cameraName, nextVideoEl) {
    if (!cameraName || !nextVideoEl || !this.cameraProjector) return;
    const oldTex = this._replayTexture;
    const nextTex = this._createVideoTexture(nextVideoEl);
    this._replayTexture = nextTex;
    this._replayBoundVideoEl = nextVideoEl;
    this.cameraProjector.attachOverlayTexture(cameraName, nextTex);
    if (oldTex && oldTex !== nextTex) {
      try {
        oldTex.dispose();
      } catch {}
    }
  }

  _createVideoTexture(videoElement) {
    const texture = new THREE.VideoTexture(videoElement);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.generateMipmaps = false;
    return texture;
  }

  _applyReplayAvailabilityState(state) {
    if (!this.activeCameraName || !this.cameraProjector) return;
    const status = state?.status || RecordingPlaybackStatus.NO_RECORDING;
    const hasVideo =
      status === RecordingPlaybackStatus.PLAYING ||
      status === RecordingPlaybackStatus.PAUSED;

    this._replayHasVideo = hasVideo;

    if (hasVideo) {
      this.cameraProjector.setOverlayPOVMode(this.activeCameraName, true, this.opacity);
      this._updateHudModeBadge('replay', status === RecordingPlaybackStatus.PLAYING ? 'REPLAY' : 'REPLAY PAUSA');
    } else if (status === RecordingPlaybackStatus.LOADING) {
      this.cameraProjector.setOverlayPOVMode(this.activeCameraName, true, 0);
      this._updateHudModeBadge('loading', 'CARICAMENTO...');
    } else {
      // Nessuna registrazione a quest'orario: non oscura la scena 3D con un frame bloccato
      this.cameraProjector.setOverlayPOVMode(this.activeCameraName, false, 0);
      this._updateHudModeBadge('norec', 'NO REGISTRAZIONE');
    }
  }

  setOpacity(alpha) {
    this.opacity = THREE.MathUtils.clamp(Number(alpha), 0, 1);
    const pct = Math.round(this.opacity * 100);
    if (this.hudEl) {
      const slider = this.hudEl.querySelector('#pov-hud-opacity');
      const valEl = this.hudEl.querySelector('#pov-hud-opacity-val');
      if (slider) slider.value = String(pct);
      if (valEl) valEl.textContent = `${pct}%`;
    }
    if (this.activeCameraName && !this._isCalibrationActive()) {
      if (this.activeSourceMode === 'live' || this._replayHasVideo) {
        this.cameraProjector?.setOverlayOpacity?.(this.activeCameraName, this.opacity);
      }
    }
  }

  deactivate(cameraName = this.activeCameraName) {
    this._attachSeq += 1;
    const targetCam = cameraName || this.activeCameraName;
    this._teardownActiveResources({ hideProjectorOverlay: true, targetCameraName: targetCam });
    this.activeCameraName = null;
    this.activeSourceMode = null;
    this._replayHasVideo = false;
    this._hideHud();
  }

  _teardownActiveResources({ hideProjectorOverlay = true, targetCameraName = this.activeCameraName } = {}) {
    if (hideProjectorOverlay && targetCameraName && this.cameraProjector) {
      this.cameraProjector.setOverlayPOVMode(targetCameraName, false, 0);
      if (typeof this.cameraProjector.detachOverlayTexture === 'function') {
        this.cameraProjector.detachOverlayTexture(targetCameraName);
      }
    }

    if (this._liveTextureEntry && this._liveStreamName && this.videoStreamManager) {
      this.videoStreamManager.releaseVideoTexture(this._liveStreamName);
    }
    this._liveTextureEntry = null;
    this._liveStreamName = null;
    this._previewTextureActive = false;

    if (this._replayAuxSlotKey && this.recordingManager) {
      this.recordingManager.unregisterSlot(this._replayAuxSlotKey);
    }
    this._replayAuxSlotKey = null;
    this._replayAuxVideoEl = null;
    this._replayBoundVideoEl = null;

    if (this._replayTexture) {
      this._replayTexture.dispose();
      this._replayTexture = null;
    }
  }

  // --- Floating Minimal POV HUD Pill ---

  _ensureHudDOM() {
    if (this.hudEl || typeof document === 'undefined' || !this.uiLayer) return;

    const hud = document.createElement('div');
    hud.id = 'pov-overlay-hud';
    hud.className = 'pov-overlay-hud glass';
    hud.hidden = true;
    hud.innerHTML = `
      <div class="pov-hud-identity">
        <span class="pov-hud-mode-pill live" id="pov-hud-mode-pill">LIVE</span>
        <span class="pov-hud-cam-name" id="pov-hud-cam-name">Telecamera</span>
      </div>
      <div class="pov-hud-opacity-wrap" title="Trasparenza video sovraimpresso">
        <input type="range" id="pov-hud-opacity" min="0" max="100" value="${Math.round(this.opacity * 100)}" class="pov-hud-slider" aria-label="Opacità video POV" />
        <span class="pov-hud-opacity-val" id="pov-hud-opacity-val">${Math.round(this.opacity * 100)}%</span>
      </div>
      <div class="pov-hud-actions">
        <button type="button" class="pov-hud-btn pov-hud-quality-btn" id="btn-pov-quality" title="Alterna qualità flusso live (Fluido Sub / HD Main)">
          <span id="pov-hud-quality-label">HD</span>
        </button>
        <button type="button" class="pov-hud-btn exit" id="btn-pov-exit" title="Esci dalla vista POV">
          ${icon('x', { size: 14 })}
          <span>Esci</span>
        </button>
      </div>
    `;

    hud.addEventListener('pointerdown', (e) => e.stopPropagation());
    hud.addEventListener('click', (e) => e.stopPropagation());

    hud.querySelector('#pov-hud-opacity')?.addEventListener('input', (e) => {
      const pct = parseInt(e.target.value, 10);
      if (Number.isFinite(pct)) {
        this.setOpacity(pct / 100);
      }
    });

    hud.querySelector('#btn-pov-quality')?.addEventListener('click', () => {
      if (!this.activeCameraName || this.activeSourceMode !== 'live') return;
      this.preferredLiveQuality = this._effectiveLiveQuality === 'sub' ? 'main' : 'sub';
      this._activateOverlayForCamera(this.activeCameraName, 'live', { docked: true });
    });

    hud.querySelector('#btn-pov-exit')?.addEventListener('click', () => {
      this.cameraController?.exitCameraPOV?.({ reason: 'hud_exit' });
      this.cameraController?.flyToPreset?.('overview', 0.9);
    });

    this.uiLayer.appendChild(hud);
    this.hudEl = hud;
    this._syncHudQualityButton();
  }

  _syncHudQualityButton() {
    if (!this.hudEl) return;
    const btn = this.hudEl.querySelector('#btn-pov-quality');
    const lbl = this.hudEl.querySelector('#pov-hud-quality-label');
    if (!btn || !lbl) return;
    const isLive = this.activeSourceMode !== 'replay';
    btn.hidden = !isLive;
    btn.style.display = isLive ? '' : 'none';
    const isSub = this._effectiveLiveQuality === 'sub';
    lbl.textContent = isSub ? 'SD' : 'HD';
    btn.classList.toggle('is-sub', isSub);
    btn.title = isSub
      ? 'Flusso fluido WebRTC attivo • Clicca per provare HD Main'
      : 'Flusso HD Main attivo • Clicca per flusso fluido WebRTC (SD)';
  }

  _showHud(info, mode, badgeState = 'live') {
    if (!this.hudEl) return;
    const nameEl = this.hudEl.querySelector('#pov-hud-cam-name');
    if (nameEl) nameEl.textContent = info.shortName;
    this._updateHudModeBadge(badgeState, mode === 'replay' ? 'REPLAY' : 'LIVE');
    this._syncHudQualityButton();
    this.hudEl.hidden = false;
    this.hudEl.classList.add('visible');
  }

  _updateHudModeBadge(variant, text) {
    if (!this.hudEl) return;
    const badge = this.hudEl.querySelector('#pov-hud-mode-pill');
    if (!badge) return;
    badge.className = `pov-hud-mode-pill ${variant}`;
    badge.textContent = text;
  }

  _hideHud() {
    if (!this.hudEl) return;
    this.hudEl.classList.remove('visible');
    this.hudEl.hidden = true;
  }

  dispose() {
    this.deactivate();
    for (const unsub of this._unsubs) {
      try {
        unsub();
      } catch {}
    }
    this._unsubs = [];
    if (this.hudEl) {
      this.hudEl.remove();
      this.hudEl = null;
    }
  }
}
