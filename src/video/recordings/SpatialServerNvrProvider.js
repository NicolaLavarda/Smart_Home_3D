import { DualVideoBufferController } from './DualVideoBufferController.js';
import { IRecordingProvider } from './IRecordingProvider.js';
import { PlaybackResolution, RecordingSegment } from './RecordingModels.js';

/**
 * SpatialServerNvrProvider
 *
 * Provider concreto per la modalità "Hard Disk Videosorveglianza su PC / NVR locale".
 * Comunica con gli endpoint REST del microservizio Python `spatial_server`
 * (`/api/v1/recordings/*`), compatibile con architettura Dual-Tier (Sub H24 + Main Event)
 * e supporto HTTP Range Seeking istantaneo + lookahead per doppio buffer.
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

  _hydrateSegment(rawSeg, fallbackCameraId = '') {
    if (!rawSeg) return null;
    return new RecordingSegment({
      id: rawSeg.id,
      cameraId: rawSeg.camera_id || fallbackCameraId,
      startUnix: rawSeg.start_unix,
      endUnix: rawSeg.end_unix,
      streamUrl: this._normalizeUrl(rawSeg.stream_url),
      format: rawSeg.format || 'mp4',
      storageType: rawSeg.storage_type || this.storageType,
      hasMotion: Boolean(rawSeg.has_motion),
      sizeBytes: rawSeg.size_bytes || 0,
      metadata: rawSeg.metadata || {},
      streamTier: rawSeg.stream_tier || (rawSeg.has_motion ? 'main' : 'sub'),
      codec: rawSeg.codec || 'h264',
      width: rawSeg.width || 0,
      height: rawSeg.height || 0,
    });
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

    const recorder = res.recorder || null;
    const storageStats = res.storage_stats || null;
    let detail = 'Archivio NVR predisposto (nessun disco configurato in SPATIAL_NVR_STORAGE_DIR)';
    if (res.configured) {
      const freeGb = recorder?.last_prune?.disk_free_gb;
      const freeLabel = Number.isFinite(freeGb) ? ` • ${freeGb} GB liberi` : '';
      if (recorder?.state === 'running') {
        detail = `NVR Dual-Tier attivo (RAM pre-buffer ${recorder.ram_buffer_total_mb ?? 0} MB${freeLabel})`;
      } else if (recorder?.state === 'missing_pyav') {
        detail = `Archivio NVR attivo (${res.storage_dir || 'HDD locale'}) • Recorder in attesa di PyAV`;
      } else {
        detail = `Archivio NVR attivo (${res.storage_dir || 'HDD locale'}${freeLabel})`;
      }
    }

    return {
      configured: Boolean(res.configured),
      online: true,
      storageType: res.storage_type || this.storageType,
      cameras: res.cameras || [],
      recorder,
      storageStats,
      detail,
    };
  }

  async querySegments(cameraId, startUnix, endUnix, opts = {}) {
    const params = new URLSearchParams({
      t_start: String(startUnix),
      t_end: String(endUnix),
    });
    if (opts.tier === 'sub' || opts.tier === 'main') {
      params.set('tier', opts.tier);
    }
    const res = await this._requestJson(
      `/api/v1/recordings/${encodeURIComponent(cameraId)}/segments?${params.toString()}`
    );
    if (!res || !Array.isArray(res.segments)) {
      return [];
    }
    return res.segments.map((seg) => this._hydrateSegment(seg, cameraId)).filter(Boolean);
  }

  async resolvePlayback(cameraId, timestampUnix, opts = {}) {
    const params = new URLSearchParams({ t: String(timestampUnix) });
    if (opts.allowHevc === false) {
      params.set('allow_hevc', '0');
    }
    if (opts.preferTier === 'sub' || opts.preferTier === 'main') {
      params.set('prefer_tier', opts.preferTier);
    }
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

    const segment = this._hydrateSegment(res.segment, cameraId);
    const nextSegment = this._hydrateSegment(res.next_segment, cameraId);

    return new PlaybackResolution({
      available: Boolean(segment?.streamUrl),
      cameraId,
      requestedUnix: timestampUnix,
      segment,
      seekOffsetSec: Number(res.seek_offset_sec ?? segment.getOffsetSeconds(timestampUnix)),
      streamUrl: segment?.streamUrl || null,
      reason: segment?.streamUrl ? 'ok' : 'missing_stream_url',
      storageType: segment?.storageType || this.storageType,
      effectiveEndUnix: res.effective_end_unix ?? segment?.endUnix ?? null,
      switchAtUnix: res.switch_at_unix ?? null,
      nextSegment,
      nextSeekOffsetSec: Number(res.next_seek_offset_sec ?? 0),
      fallbackReason: res.fallback_reason || null,
    });
  }

  async attachHistoricalVideo(cameraId, videoElement, timestampUnix, opts = {}) {
    if (!videoElement) {
      return new PlaybackResolution({ available: false, cameraId, requestedUnix: timestampUnix, reason: 'missing_element' });
    }

    const allowHevc = opts.allowHevc !== undefined
      ? Boolean(opts.allowHevc)
      : DualVideoBufferController.detectBrowserHevcSupport(videoElement);

    const resolution = await this.resolvePlayback(cameraId, timestampUnix, {
      allowHevc,
      preferTier: opts.preferTier,
    });
    if (!resolution.available || !resolution.streamUrl) {
      this.detach(videoElement);
      return resolution;
    }

    const prevState = this._elementState.get(videoElement);
    const sameSegment = prevState && prevState.segmentId === resolution.segment.id && prevState.streamUrl === resolution.streamUrl;

    videoElement.muted = true;
    videoElement.playsInline = true;
    videoElement.crossOrigin = 'use-credentials';

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
        let timer = null;
        const cleanup = () => {
          videoElement.removeEventListener?.('loadedmetadata', onLoaded);
          videoElement.removeEventListener?.('error', onLoaded);
        };
        const done = () => {
          if (settled) return;
          settled = true;
          if (timer) {
            clearTimeout(timer);
            timer = null;
          }
          cleanup();
          resolve();
        };
        const onLoaded = () => done();
        timer = setTimeout(done, 1500);
        videoElement.addEventListener('loadedmetadata', onLoaded);
        videoElement.addEventListener('error', onLoaded);
      });
    }

    try {
      const targetTime = Math.max(0, resolution.seekOffsetSec);
      if (Math.abs((videoElement.currentTime || 0) - targetTime) > 0.35 || !sameSegment) {
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
