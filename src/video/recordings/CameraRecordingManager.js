import { PlaybackResolution, RecordingPlaybackStatus } from './RecordingModels.js';

/**
 * CameraRecordingManager
 *
 * Orchestratore OOP per la riproduzione storica sincronizzata multi-telecamera.
 * Responsabilità:
 * - Gestisce una catena ordinata di `IRecordingProvider` (es. HDD NVR su PC -> Edge SD camera).
 * - Mantiene gli slot video registrati dall'interfaccia Sicurezza (`cameraId -> slot`).
 * - Sincronizza seek, play/pause e velocità (1x, 2x, 5x) di tutte le telecamere con la timeline 3D.
 * - Garantisce transizioni robuste allo stato `NO_RECORDING` (riquadro nero/scuro) quando
 *   non esiste una registrazione all'orario richiesto, senza mai rompere il player o il 3D.
 */
export class CameraRecordingManager {
  constructor(options = {}) {
    this.providers = Array.isArray(options.providers) ? [...options.providers] : [];
    this.cameraCatalog = options.cameraCatalog || null;
    this.slots = new Map(); // cameraId -> { cameraId, videoElement, onStateChange, activeProvider, activeSegment, status }
    this.segmentCache = new Map(); // `${cameraId}:${dayKey}` -> Array<RecordingSegment>
    this.isPlaying = false;
    this.playbackRate = 1.0;
    this.currentTimestampUnix = null;
    this._seekVersion = 0;
    this._debounceTimer = null;
  }

  addProvider(provider) {
    if (provider && !this.providers.includes(provider)) {
      this.providers.push(provider);
    }
  }

  setProviders(providers) {
    this.providers = Array.isArray(providers) ? [...providers] : [];
  }

  /**
   * Registra un riquadro video nel gestore storico.
   * Supporta sia `registerSlot(cameraId, videoEl, cb)` sia slot ausiliari con chiave dedicata
   * (`registerSlot('pov_overlay:Cam_Portico', videoEl, cb, { cameraId: 'Cam_Portico' })`).
   */
  registerSlot(slotKey, videoElement, onStateChange = null, options = {}) {
    this.unregisterSlot(slotKey);
    const cameraId = options?.cameraId || slotKey;
    const slot = {
      slotKey,
      cameraId,
      videoElement,
      onStateChange: typeof onStateChange === 'function' ? onStateChange : null,
      activeProvider: null,
      activeSegment: null,
      status: RecordingPlaybackStatus.IDLE,
    };
    this.slots.set(slotKey, slot);
    return slot;
  }

  unregisterSlot(slotKey) {
    const existing = this.slots.get(slotKey);
    if (!existing) return;
    if (existing.activeProvider && existing.videoElement) {
      existing.activeProvider.detach(existing.videoElement);
    }
    this.slots.delete(slotKey);
  }

  async syncSlotToTimestamp(slotKey, timestampUnix) {
    const slot = this.slots.get(slotKey);
    if (!slot) return;
    this.currentTimestampUnix = Number(timestampUnix);
    await this._syncSlotToTimestamp(slot, this.currentTimestampUnix, this._seekVersion);
  }

  detachAll() {
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer);
      this._debounceTimer = null;
    }
    this._seekVersion += 1;
    for (const slot of this.slots.values()) {
      if (slot.activeProvider && slot.videoElement) {
        slot.activeProvider.detach(slot.videoElement);
      }
      slot.activeProvider = null;
      slot.activeSegment = null;
      slot.status = RecordingPlaybackStatus.IDLE;
    }
  }

  async getStorageSummary() {
    const results = [];
    for (const provider of this.providers) {
      const health = await provider.getHealthStatus().catch(() => ({
        configured: false,
        online: false,
        storageType: provider.storageType,
        detail: 'Non raggiungibile',
      }));
      results.push({ name: provider.name, ...health });
    }
    const configured = results.some((r) => r.configured);
    return { configured, providers: results };
  }

  /**
   * Recupera i segmenti disponibili per tutte le telecamere registrate nell'intervallo [startUnix, endUnix]
   * (usato per evidenziare sulla timeline dove esistono clip registrate).
   */
  async queryAllSegments(startUnix, endUnix) {
    const byCamera = new Map();
    const cameraIds = this.cameraCatalog
      ? this.cameraCatalog.getCameras().map((c) => c.recordingCameraId)
      : Array.from(this.slots.keys());

    await Promise.all(
      cameraIds.map(async (cameraId) => {
        for (const provider of this.providers) {
          const segments = await provider.querySegments(cameraId, startUnix, endUnix).catch(() => []);
          if (segments && segments.length > 0) {
            byCamera.set(cameraId, segments);
            return;
          }
        }
        byCamera.set(cameraId, []);
      })
    );
    return byCamera;
  }

  /**
   * Sincronizza tutti gli slot video al timestamp Unix richiesto.
   * Supporta debounce per lo scrubbing fluido della timeline senza saturare la rete.
   */
  seekAllToTimestamp(timestampUnix, { immediate = false } = {}) {
    this.currentTimestampUnix = Number(timestampUnix);
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer);
      this._debounceTimer = null;
    }

    if (immediate) {
      return this._executeSeekAll(this.currentTimestampUnix);
    }

    return new Promise((resolve) => {
      this._debounceTimer = setTimeout(async () => {
        this._debounceTimer = null;
        await this._executeSeekAll(this.currentTimestampUnix);
        resolve();
      }, 140);
    });
  }

  async _executeSeekAll(timestampUnix) {
    const version = ++this._seekVersion;
    const tasks = [];
    for (const slot of this.slots.values()) {
      tasks.push(this._syncSlotToTimestamp(slot, timestampUnix, version));
    }
    await Promise.all(tasks);
  }

  async _syncSlotToTimestamp(slot, timestampUnix, version) {
    if (!slot || !slot.videoElement) return;

    // Fast path: se lo slot sta già riproducendo un segmento che contiene timestampUnix,
    // aggiorniamo solo videoElement.currentTime localmente senza chiamate di rete.
    if (slot.activeProvider && slot.activeSegment && slot.activeSegment.containsTimestamp(timestampUnix)) {
      const targetOffset = slot.activeSegment.getOffsetSeconds(timestampUnix);
      const drift = Math.abs((slot.videoElement.currentTime || 0) - targetOffset);
      if (drift > 0.75) {
        try {
          slot.videoElement.currentTime = targetOffset;
        } catch {}
      }
      slot.activeProvider.setPlaybackRate(slot.videoElement, this.playbackRate);
      slot.activeProvider.setPaused(slot.videoElement, !this.isPlaying);
      this._emitSlotState(slot, {
        status: this.isPlaying ? RecordingPlaybackStatus.PLAYING : RecordingPlaybackStatus.PAUSED,
        timestampUnix,
        segment: slot.activeSegment,
        reason: 'ok',
      });
      return;
    }

    this._emitSlotState(slot, {
      status: RecordingPlaybackStatus.LOADING,
      timestampUnix,
      segment: null,
      reason: 'loading',
    });

    let lastResolution = new PlaybackResolution({
      available: false,
      cameraId: slot.cameraId,
      requestedUnix: timestampUnix,
      reason: this.providers.length === 0 ? 'no_provider_configured' : 'no_recording',
    });

    for (const provider of this.providers) {
      if (version !== this._seekVersion) return;
      try {
        const res = await provider.attachHistoricalVideo(slot.cameraId, slot.videoElement, timestampUnix, {
          autoplay: this.isPlaying,
          playbackRate: this.playbackRate,
        });
        if (version !== this._seekVersion) return;

        if (res && res.available) {
          if (slot.activeProvider && slot.activeProvider !== provider) {
            slot.activeProvider.detach(slot.videoElement);
          }
          slot.activeProvider = provider;
          slot.activeSegment = res.segment;
          this._emitSlotState(slot, {
            status: this.isPlaying ? RecordingPlaybackStatus.PLAYING : RecordingPlaybackStatus.PAUSED,
            timestampUnix,
            segment: res.segment,
            reason: 'ok',
            storageType: res.storageType,
          });
          return;
        }
        if (res) lastResolution = res;
      } catch {
        // Continua verso il provider successivo nella catena
      }
    }

    if (version !== this._seekVersion) return;

    // Nessun provider ha video registrato per questo timestamp -> stato scuro/nero robusto
    if (slot.activeProvider) {
      slot.activeProvider.detach(slot.videoElement);
    }
    slot.activeProvider = null;
    slot.activeSegment = null;
    this._emitSlotState(slot, {
      status: RecordingPlaybackStatus.NO_RECORDING,
      timestampUnix,
      segment: null,
      reason: lastResolution.reason || 'no_recording',
      storageType: lastResolution.storageType || 'none',
    });
  }

  /**
   * Avanzamento sincrono chiamato dal render loop quando il replay storico è in riproduzione:
   * verifica se siamo usciti dal segmento corrente (passaggio automatico a segmento successivo o schermo nero).
   */
  syncPlaybackTick(timestampUnix) {
    this.currentTimestampUnix = Number(timestampUnix);
    if (!this.isPlaying) return;

    for (const slot of this.slots.values()) {
      if (slot.activeSegment && !slot.activeSegment.containsTimestamp(timestampUnix, 0.5)) {
        // Usciti dal segmento corrente: risolve il segmento successivo o passa a NO_RECORDING
        this._syncSlotToTimestamp(slot, timestampUnix, this._seekVersion);
      }
    }
  }

  setPlaying(playing) {
    this.isPlaying = Boolean(playing);
    for (const slot of this.slots.values()) {
      if (slot.activeProvider && slot.videoElement && slot.activeSegment) {
        slot.activeProvider.setPaused(slot.videoElement, !this.isPlaying);
        this._emitSlotState(slot, {
          status: this.isPlaying ? RecordingPlaybackStatus.PLAYING : RecordingPlaybackStatus.PAUSED,
          timestampUnix: this.currentTimestampUnix,
          segment: slot.activeSegment,
          reason: 'ok',
        });
      }
    }
  }

  setPlaybackRate(rate) {
    this.playbackRate = Math.max(0.25, Math.min(8.0, Number(rate) || 1.0));
    for (const slot of this.slots.values()) {
      if (slot.activeProvider && slot.videoElement) {
        slot.activeProvider.setPlaybackRate(slot.videoElement, this.playbackRate);
      }
    }
  }

  _emitSlotState(slot, payload) {
    slot.status = payload.status;
    if (slot.onStateChange) {
      try {
        slot.onStateChange(payload);
      } catch (err) {
        console.warn('[CameraRecordingManager] Errore callback stato slot:', err);
      }
    }
  }
}
