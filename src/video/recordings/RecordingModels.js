/**
 * RecordingModels
 *
 * Oggetti di dominio immutabili per il sottosistema di registrazione video NVR / Edge SD.
 */

export const RecordingPlaybackStatus = Object.freeze({
  IDLE: 'idle',
  LOADING: 'loading',
  PLAYING: 'playing',
  PAUSED: 'paused',
  NO_RECORDING: 'no_recording',
  UNAVAILABLE: 'unavailable',
  ERROR: 'error',
});

export class RecordingSegment {
  constructor({
    id = '',
    cameraId,
    startUnix,
    endUnix,
    streamUrl = '',
    format = 'mp4',
    storageType = 'pc_nvr_hdd',
    hasMotion = false,
    sizeBytes = 0,
    metadata = {},
  }) {
    this.id = String(id || `${cameraId}_${Math.floor(startUnix)}`);
    this.cameraId = String(cameraId);
    this.startUnix = Number(startUnix);
    this.endUnix = Number(endUnix);
    this.durationSec = Math.max(0, this.endUnix - this.startUnix);
    this.streamUrl = String(streamUrl || '');
    this.format = String(format || 'mp4');
    this.storageType = String(storageType || 'pc_nvr_hdd');
    this.hasMotion = Boolean(hasMotion);
    this.sizeBytes = Number(sizeBytes) || 0;
    this.metadata = metadata || {};
  }

  containsTimestamp(timestampUnix, toleranceSec = 0.25) {
    return timestampUnix >= this.startUnix - toleranceSec && timestampUnix <= this.endUnix + toleranceSec;
  }

  getOffsetSeconds(timestampUnix) {
    return Math.max(0, Math.min(this.durationSec, timestampUnix - this.startUnix));
  }
}

export class PlaybackResolution {
  constructor({
    available = false,
    cameraId = '',
    requestedUnix = 0,
    segment = null,
    seekOffsetSec = 0,
    streamUrl = null,
    reason = 'no_recording',
    storageType = 'none',
  } = {}) {
    this.available = Boolean(available);
    this.cameraId = String(cameraId);
    this.requestedUnix = Number(requestedUnix) || 0;
    this.segment = segment instanceof RecordingSegment ? segment : (segment ? new RecordingSegment(segment) : null);
    this.seekOffsetSec = Number(seekOffsetSec) || 0;
    this.streamUrl = streamUrl || this.segment?.streamUrl || null;
    this.reason = String(reason || (this.available ? 'ok' : 'no_recording'));
    this.storageType = String(storageType || this.segment?.storageType || 'none');
  }
}
