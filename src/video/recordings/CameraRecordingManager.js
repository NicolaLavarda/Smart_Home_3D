import { DualVideoBufferController } from './DualVideoBufferController.js';
import { PlaybackResolution, RecordingPlaybackStatus } from './RecordingModels.js';

/**
 * CameraRecordingManager
 *
 * Orchestratore OOP per la riproduzione storica sincronizzata multi-telecamera.
 * Responsabilità:
 * - Gestisce una catena ordinata di `IRecordingProvider` (es. HDD NVR su PC -> Edge SD camera).
 * - Mantiene gli slot video registrati dall'interfaccia Sicurezza (`cameraId -> slot`) con doppio buffer.
 * - Precarica in standby il segmento successivo (`Sub -> Main` o `Main -> Sub`) e commuta senza schermo nero.
 * - Sincronizza seek, play/pause e velocità (1x, 2x, 5x) di tutte le telecamere con la timeline 3D.
 */
export class CameraRecordingManager {
  constructor(options = {}) {
    this.providers = Array.isArray(options.providers) ? [...options.providers] : [];
    this.cameraCatalog = options.cameraCatalog || null;
    this.preloadLookaheadSec = Math.max(1.0, Number(options.preloadLookaheadSec) || 3.0);
    this.slots = new Map();
    this.segmentCache = new Map();
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
   * Registra un riquadro video nel gestore storico (con supporto opzionale doppio `<video>`).
   */
  registerSlot(slotKey, videoElement, onStateChange = null, options = {}) {
    this.unregisterSlot(slotKey);
    const cameraId = options?.cameraId || slotKey;
    const bufferController = new DualVideoBufferController({
      primaryVideoEl: videoElement,
      bufferVideoEl: options?.bufferVideoEl || null,
      onActiveVideoChange: options?.onActiveVideoChange || null,
    });
    const slot = {
      slotKey,
      cameraId,
      videoElement,
      bufferController,
      onStateChange: typeof onStateChange === 'function' ? onStateChange : null,
      activeProvider: null,
      activeSegment: null,
      activeResolution: null,
      status: RecordingPlaybackStatus.IDLE,
      _isSwapping: false,
      _refreshingLookahead: false,
    };
    this.slots.set(slotKey, slot);
    return slot;
  }

  unregisterSlot(slotKey) {
    const existing = this.slots.get(slotKey);
    if (!existing) return;
    if (existing.activeProvider) {
      existing.activeProvider.detach(existing.bufferController.getActiveVideo());
      if (existing.bufferController.getStandbyVideo()) {
        existing.activeProvider.detach(existing.bufferController.getStandbyVideo());
      }
    }
    existing.bufferController.detachAll();
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
      if (slot.activeProvider) {
        slot.activeProvider.detach(slot.bufferController.getActiveVideo());
        if (slot.bufferController.getStandbyVideo()) {
          slot.activeProvider.detach(slot.bufferController.getStandbyVideo());
        }
      }
      slot.bufferController.detachAll();
      slot.activeProvider = null;
      slot.activeSegment = null;
      slot.activeResolution = null;
      slot._isSwapping = false;
      slot._refreshingLookahead = false;
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
   * Recupera i segmenti disponibili per tutte le telecamere registrate nell'intervallo [startUnix, endUnix].
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
    if (!slot || !slot.bufferController?.getActiveVideo()) return;
    const activeVideoEl = slot.bufferController.getActiveVideo();

    const insideEffective = slot.activeResolution
      ? slot.activeResolution.containsEffectiveTimestamp(timestampUnix)
      : Boolean(slot.activeSegment && slot.activeSegment.containsTimestamp(timestampUnix));

    if (slot.activeProvider && slot.activeSegment && insideEffective) {
      const targetOffset = slot.activeSegment.getOffsetSeconds(timestampUnix);
      const drift = Math.abs((activeVideoEl.currentTime || 0) - targetOffset);
      if (drift > 0.45) {
        try {
          activeVideoEl.currentTime = targetOffset;
        } catch {}
      }
      slot.activeProvider.setPlaybackRate(activeVideoEl, this.playbackRate);
      slot.activeProvider.setPaused(activeVideoEl, !this.isPlaying);
      this._emitSlotState(slot, {
        status: this.isPlaying ? RecordingPlaybackStatus.PLAYING : RecordingPlaybackStatus.PAUSED,
        timestampUnix,
        segment: slot.activeSegment,
        resolution: slot.activeResolution,
        activeVideoEl,
        streamTier: slot.activeSegment.streamTier || 'sub',
        reason: 'ok',
      });
      return;
    }

    this._emitSlotState(slot, {
      status: RecordingPlaybackStatus.LOADING,
      timestampUnix,
      segment: null,
      activeVideoEl,
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
        const targetEl = slot.bufferController.getActiveVideo();
        const res = await provider.attachHistoricalVideo(slot.cameraId, targetEl, timestampUnix, {
          autoplay: this.isPlaying,
          playbackRate: this.playbackRate,
        });
        if (version !== this._seekVersion) return;

        if (res && res.available) {
          if (slot.activeProvider && slot.activeProvider !== provider) {
            slot.activeProvider.detach(targetEl);
          }
          slot.activeProvider = provider;
          slot.activeSegment = res.segment;
          slot.activeResolution = res;
          this._emitSlotState(slot, {
            status: this.isPlaying ? RecordingPlaybackStatus.PLAYING : RecordingPlaybackStatus.PAUSED,
            timestampUnix,
            segment: res.segment,
            resolution: res,
            activeVideoEl: targetEl,
            streamTier: res.segment?.streamTier || 'sub',
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

    if (slot.activeProvider) {
      slot.activeProvider.detach(slot.bufferController.getActiveVideo());
    }
    slot.bufferController.detachAll();
    slot.activeProvider = null;
    slot.activeSegment = null;
    slot.activeResolution = null;
    this._emitSlotState(slot, {
      status: RecordingPlaybackStatus.NO_RECORDING,
      timestampUnix,
      segment: null,
      activeVideoEl: slot.bufferController.getActiveVideo(),
      reason: lastResolution.reason || 'no_recording',
      storageType: lastResolution.storageType || 'none',
    });
  }

  async _refreshSlotLookahead(slot, probeTimestampUnix, expectedSegmentId, seekVersion) {
    if (!slot.activeProvider || slot._refreshingLookahead) return;
    if (typeof slot.activeProvider.resolvePlayback !== 'function') return;
    slot._refreshingLookahead = true;
    try {
      const allowHevc = DualVideoBufferController.detectBrowserHevcSupport(slot.bufferController.getActiveVideo());
      const freshRes = await slot.activeProvider.resolvePlayback(slot.cameraId, probeTimestampUnix, { allowHevc });
      if (seekVersion !== this._seekVersion) return;
      if (freshRes?.available && freshRes.segment?.id === expectedSegmentId) {
        slot.activeResolution = freshRes;
      }
    } catch {
      // Mantiene la risoluzione provvisoria fino al prossimo cambio
    } finally {
      slot._refreshingLookahead = false;
    }
  }

  /**
   * Avanzamento sincrono dal render loop durante il replay storico:
   * - Precarica il segmento successivo sul buffer standby negli ultimi N secondi
   * - Esegue lo swap istantaneo zero-gap al confine Sub <-> Main o tra segmenti contigui
   * - Mantiene allineato currentTime entro 0.55s rispetto alla timeline 3D
   */
  syncPlaybackTick(timestampUnix) {
    this.currentTimestampUnix = Number(timestampUnix);
    if (!this.isPlaying) return;

    const lookaheadWindow = this.preloadLookaheadSec * Math.max(1.0, this.playbackRate);

    for (const slot of this.slots.values()) {
      if (!slot.activeSegment || slot._isSwapping) continue;
      const activeVideoEl = slot.bufferController.getActiveVideo();
      const res = slot.activeResolution;
      const nextSeg = res?.nextSegment || null;
      const switchAt = res?.switchAtUnix ?? res?.effectiveEndUnix ?? slot.activeSegment.endUnix;

      // 1. Pre-caricamento anticipato nello standby <video>
      if (
        nextSeg &&
        nextSeg.streamUrl &&
        slot.bufferController.hasDualBuffer() &&
        Number.isFinite(switchAt)
      ) {
        const timeToSwitch = switchAt - timestampUnix;
        if (timeToSwitch > 0 && timeToSwitch <= lookaheadWindow) {
          slot.bufferController.preloadStandby(
            nextSeg.streamUrl,
            res?.nextSeekOffsetSec ?? 0,
            nextSeg.id,
            { playbackRate: this.playbackRate }
          );
        }
      }

      // 2. Verifica confine temporale di fine effettiva (switch a Main o ritorno a Sub)
      const effectiveEnd = res?.effectiveEndUnix ?? slot.activeSegment.endUnix;
      if (timestampUnix >= effectiveEnd - 0.08) {
        if (nextSeg && nextSeg.streamUrl && slot.bufferController.isStandbyReadyFor(nextSeg.id, nextSeg.streamUrl)) {
          const nextOffset = Math.max(0, timestampUnix - nextSeg.startUnix);
          const swappedEl = slot.bufferController.commitStandbySwap(nextOffset, {
            autoplay: this.isPlaying,
            playbackRate: this.playbackRate,
          });
          if (swappedEl) {
            slot.activeSegment = nextSeg;
            slot.activeResolution = new PlaybackResolution({
              available: true,
              cameraId: slot.cameraId,
              requestedUnix: timestampUnix,
              segment: nextSeg,
              seekOffsetSec: nextOffset,
              streamUrl: nextSeg.streamUrl,
              reason: 'ok',
              storageType: nextSeg.storageType,
              effectiveEndUnix: nextSeg.endUnix,
            });
            this._emitSlotState(slot, {
              status: this.isPlaying ? RecordingPlaybackStatus.PLAYING : RecordingPlaybackStatus.PAUSED,
              timestampUnix,
              segment: nextSeg,
              resolution: slot.activeResolution,
              activeVideoEl: swappedEl,
              streamTier: nextSeg.streamTier || 'sub',
              reason: 'ok',
              storageType: nextSeg.storageType,
            });
            void this._refreshSlotLookahead(slot, timestampUnix + 0.15, nextSeg.id, this._seekVersion);
            continue;
          }
        }

        // Fallback se il buffer standby non era ancora pronto o se il provider è a buffer singolo
        slot._isSwapping = true;
        void this._syncSlotToTimestamp(slot, timestampUnix, this._seekVersion).finally(() => {
          slot._isSwapping = false;
        });
        continue;
      }

      // 3. Correzione drift leggera durante riproduzione continua
      if (activeVideoEl && slot.activeSegment.containsTimestamp(timestampUnix, 0.5)) {
        const expectedOffset = slot.activeSegment.getOffsetSeconds(timestampUnix);
        const drift = Math.abs((activeVideoEl.currentTime || 0) - expectedOffset);
        if (drift > 0.55) {
          try {
            activeVideoEl.currentTime = expectedOffset;
          } catch {}
        }
      }
    }
  }

  setPlaying(playing) {
    this.isPlaying = Boolean(playing);
    for (const slot of this.slots.values()) {
      const activeVideoEl = slot.bufferController.getActiveVideo();
      if (slot.activeProvider && activeVideoEl && slot.activeSegment) {
        slot.activeProvider.setPaused(activeVideoEl, !this.isPlaying);
        this._emitSlotState(slot, {
          status: this.isPlaying ? RecordingPlaybackStatus.PLAYING : RecordingPlaybackStatus.PAUSED,
          timestampUnix: this.currentTimestampUnix,
          segment: slot.activeSegment,
          resolution: slot.activeResolution,
          activeVideoEl,
          streamTier: slot.activeSegment.streamTier || 'sub',
          reason: 'ok',
        });
      }
    }
  }

  setPlaybackRate(rate) {
    this.playbackRate = Math.max(0.25, Math.min(8.0, Number(rate) || 1.0));
    for (const slot of this.slots.values()) {
      const activeVideoEl = slot.bufferController.getActiveVideo();
      if (slot.activeProvider && activeVideoEl) {
        slot.activeProvider.setPlaybackRate(activeVideoEl, this.playbackRate);
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
