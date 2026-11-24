/**
 * RecordingModels
 *
 * Oggetti di dominio immutabili per il sottosistema di registrazione video NVR / Edge SD
 * con supporto Dual-Tier (Sub H24 + Main Event) e lookahead zero-gap.
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
    streamTier = 'sub',
    codec = 'h264',
    width = 0,
    height = 0,
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
    this.streamTier = String(streamTier || 'sub').toLowerCase() === 'main' ? 'main' : 'sub';
    this.codec = String(codec || 'h264').toLowerCase();
    this.width = Number(width) || 0;
    this.height = Number(height) || 0;
  }

  isMainTier() {
    return this.streamTier === 'main';
  }

  isHevc() {
    return this.codec === 'hevc' || this.codec === 'h265' || this.codec === 'hvc1' || this.codec === 'hev1';
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
    effectiveEndUnix = null,
    switchAtUnix = null,
    nextSegment = null,
    nextSeekOffsetSec = 0,
    fallbackReason = null,
  } = {}) {
    this.available = Boolean(available);
    this.cameraId = String(cameraId);
    this.requestedUnix = Number(requestedUnix) || 0;
    this.segment = segment instanceof RecordingSegment ? segment : (segment ? new RecordingSegment(segment) : null);
    this.seekOffsetSec = Number(seekOffsetSec) || 0;
    this.streamUrl = streamUrl || this.segment?.streamUrl || null;
    this.reason = String(reason || (this.available ? 'ok' : 'no_recording'));
    this.storageType = String(storageType || this.segment?.storageType || 'none');

    const rawEffEnd = effectiveEndUnix !== null && effectiveEndUnix !== undefined
      ? Number(effectiveEndUnix)
      : (this.segment ? this.segment.endUnix : null);
    this.effectiveEndUnix = Number.isFinite(rawEffEnd) ? rawEffEnd : null;

    const rawSwitchAt = switchAtUnix !== null && switchAtUnix !== undefined ? Number(switchAtUnix) : null;
    this.switchAtUnix = Number.isFinite(rawSwitchAt) ? rawSwitchAt : null;

    this.nextSegment = nextSegment instanceof RecordingSegment
      ? nextSegment
      : (nextSegment ? new RecordingSegment(nextSegment) : null);
    this.nextSeekOffsetSec = Math.max(0, Number(nextSeekOffsetSec) || 0);
    this.fallbackReason = fallbackReason ? String(fallbackReason) : null;
  }

  containsEffectiveTimestamp(timestampUnix, toleranceSec = 0.25) {
    if (!this.segment) return false;
    const endBound = this.effectiveEndUnix !== null ? this.effectiveEndUnix : this.segment.endUnix;
    return timestampUnix >= this.segment.startUnix - toleranceSec && timestampUnix <= endBound + toleranceSec;
  }
}
