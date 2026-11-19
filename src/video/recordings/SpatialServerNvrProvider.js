import { IRecordingProvider } from './IRecordingProvider.js';
import { PlaybackResolution, RecordingSegment } from './RecordingModels.js';

/**
 * SpatialServerNvrProvider
 *
 * Provider concreto per la modalità "Hard Disk Videosorveglianza su PC / NVR locale".
 * Comunica con gli endpoint REST del microservizio Python `spatial_server`
 * (`/api/v1/recordings/*`), compatibile con segmenti MP4/fMP4 salvati sul disco del PC
 * da ffmpeg/go2rtc/Frigate con supporto HTTP Range Seeking istantaneo.
 */
export class SpatialServerNvrProvider extends IRecordingProvider {
  constructor(options = {}) {
    super('SpatialServerNvrProvider', {
      storageType: 'pc_nvr_hdd',
      ...options,
    });
    this.spatialStreamClient = options.spatialStreamClient || null;
    this.baseUrl = typeof options.baseUrl === 'string'
      ? options.baseUrl.replace(/\/+$/, '')
      : (this.spatialStreamClient?.baseUrl || '');
    this._elementState = new WeakMap(); // videoElement -> { segmentId, streamUrl }
  }

  _resolveBaseUrl() {
    if (this.spatialStreamClient && typeof this.spatialStreamClient.baseUrl === 'string') {
      return this.spatialStreamClient.baseUrl.replace(/\/+$/, '');
    }
    return this.baseUrl;
  }

  async _requestJson(path) {
    if (this.spatialStreamClient && typeof this.spatialStreamClient.requestJson === 'function') {
      return await this.spatialStreamClient.requestJson(path, { method: 'GET', timeoutMs: 4000 });
    }
    try {
      const resp = await fetch(`${this._resolveBaseUrl()}${path}`, {
        method: 'GET',
        credentials: 'include',
      });
      if (!resp.ok) return null;
      return await resp.json();
    } catch {
      return null;
    }
  }

  _normalizeUrl(rawUrl) {
    if (!rawUrl) return null;
    if (/^https?:\/\//i.test(rawUrl)) return rawUrl;
    const base = this._resolveBaseUrl();
    const path = rawUrl.startsWith('/') ? rawUrl : `/${rawUrl}`;
    return `${base}${path}`;
  }

  async getHealthStatus() {
    const res = await this._requestJson('/api/v1/recordings/status');
    if (!res) {
      return {
        configured: false,
        online: false,
        storageType: this.storageType,
        detail: 'Servizio NVR non raggiungibile',
      };
    }
    return {
      configured: Boolean(res.configured),
      online: true,
      storageType: res.storage_type || this.storageType,
      cameras: res.cameras || [],
      detail: res.configured
        ? `Archivio NVR attivo (${res.storage_dir || 'HDD locale'})`
        : 'Archivio NVR predisposto (nessun disco configurato in SPATIAL_NVR_STORAGE_DIR)',
    };
  }

  async querySegments(cameraId, startUnix, endUnix) {
    const params = new URLSearchParams({
      t_start: String(startUnix),
      t_end: String(endUnix),
    });
    const res = await this._requestJson(
      `/api/v1/recordings/${encodeURIComponent(cameraId)}/segments?${params.toString()}`
    );
    if (!res || !Array.isArray(res.segments)) {
      return [];
    }
    return res.segments.map((seg) => new RecordingSegment({
      id: seg.id,
      cameraId: seg.camera_id || cameraId,
      startUnix: seg.start_unix,
      endUnix: seg.end_unix,
      streamUrl: this._normalizeUrl(seg.stream_url),
      format: seg.format || 'mp4',
      storageType: seg.storage_type || this.storageType,
      hasMotion: Boolean(seg.has_motion),
      sizeBytes: seg.size_bytes || 0,
      metadata: seg.metadata || {},
    }));
  }

  async resolvePlayback(cameraId, timestampUnix) {
    const params = new URLSearchParams({ t: String(timestampUnix) });
    const res = await this._requestJson(
      `/api/v1/recordings/${encodeURIComponent(cameraId)}/resolve?${params.toString()}`
    );
    if (!res || !res.available || !res.segment) {
      return new PlaybackResolution({
        available: false,
        cameraId,
        requestedUnix: timestampUnix,
        reason: res?.reason || 'no_recording',
        storageType: this.storageType,
      });
    }

    const segment = new RecordingSegment({
      id: res.segment.id,
      cameraId: res.segment.camera_id || cameraId,
      startUnix: res.segment.start_unix,
      endUnix: res.segment.end_unix,
      streamUrl: this._normalizeUrl(res.segment.stream_url),
      format: res.segment.format || 'mp4',
      storageType: res.segment.storage_type || this.storageType,
      hasMotion: Boolean(res.segment.has_motion),
      sizeBytes: res.segment.size_bytes || 0,
      metadata: res.segment.metadata || {},
    });

    return new PlaybackResolution({
      available: Boolean(segment.streamUrl),
      cameraId,
      requestedUnix: timestampUnix,
      segment,
      seekOffsetSec: Number(res.seek_offset_sec ?? segment.getOffsetSeconds(timestampUnix)),
      streamUrl: segment.streamUrl,
      reason: segment.streamUrl ? 'ok' : 'missing_stream_url',
      storageType: segment.storageType,
    });
  }

  async attachHistoricalVideo(cameraId, videoElement, timestampUnix, opts = {}) {
    if (!videoElement) {
      return new PlaybackResolution({ available: false, cameraId, requestedUnix: timestampUnix, reason: 'missing_element' });
    }

    const resolution = await this.resolvePlayback(cameraId, timestampUnix);
    if (!resolution.available || !resolution.streamUrl) {
      this.detach(videoElement);
      return resolution;
    }

    const prevState = this._elementState.get(videoElement);
    const sameSegment = prevState && prevState.segmentId === resolution.segment.id && prevState.streamUrl === resolution.streamUrl;

    videoElement.muted = true;
    videoElement.playsInline = true;

    if (!sameSegment) {
      if (videoElement.srcObject) {
        videoElement.srcObject = null;
      }
      videoElement.src = resolution.streamUrl;
      this._elementState.set(videoElement, {
        segmentId: resolution.segment.id,
        streamUrl: resolution.streamUrl,
      });

      await new Promise((resolve) => {
        let settled = false;
        const done = () => {
          if (settled) return;
          settled = true;
          resolve();
        };
        const timer = setTimeout(done, 1500);
        const onLoaded = () => {
          clearTimeout(timer);
          done();
        };
        videoElement.addEventListener('loadedmetadata', onLoaded, { once: true });
        videoElement.addEventListener('error', onLoaded, { once: true });
      });
    }

    try {
      const targetTime = Math.max(0, resolution.seekOffsetSec);
      if (Math.abs((videoElement.currentTime || 0) - targetTime) > 0.65 || !sameSegment) {
        videoElement.currentTime = targetTime;
      }
    } catch {}

    if (opts.playbackRate) {
      this.setPlaybackRate(videoElement, opts.playbackRate);
    }

    if (opts.autoplay) {
      videoElement.play().catch(() => {});
    } else {
      videoElement.pause();
    }

    return resolution;
  }

  detach(videoElement) {
    this._elementState.delete(videoElement);
    super.detach(videoElement);
  }
}
