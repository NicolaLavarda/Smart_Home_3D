import { IRecordingProvider } from './IRecordingProvider.js';
import { PlaybackResolution } from './RecordingModels.js';

/**
 * EdgeCameraSdProvider
 *
 * Provider concreto predisposto per la modalità "SSD / MicroSD a bordo di ogni telecamera"
 * (es. Reolink Media Source tramite Home Assistant WebSocket `media_source/browse_media`
 * e `media_source/resolve_media`, oppure proxy VOD Reolink).
 *
 * Mantiene la medesima interfaccia di SpatialServerNvrProvider così da consentire
 * il cambio trasparente di strategia o l'utilizzo ibrido (fallback su SD se HDD offline).
 */
export class EdgeCameraSdProvider extends IRecordingProvider {
  constructor(options = {}) {
    super('EdgeCameraSdProvider', {
      storageType: 'camera_edge_sd',
      ...options,
    });
    this.haClient = options.haClient || null;
    this.mediaContentIdResolver = typeof options.mediaContentIdResolver === 'function'
      ? options.mediaContentIdResolver
      : null;
  }

  async getHealthStatus() {
    const connected = Boolean(this.haClient?.connection && !this.haClient?.isMockMode);
    return {
      configured: Boolean(this.mediaContentIdResolver),
      online: connected,
      storageType: this.storageType,
      detail: connected
        ? 'Adapter Edge SD (Home Assistant Media Source) pronto per il collegamento'
        : 'Home Assistant non connesso in modalità live',
    };
  }

  async querySegments(_cameraId, _startUnix, _endUnix) {
    // Predisposto per l'integrazione con HA `media_source/browse_media` (es. media-source://reolink/...)
    return [];
  }

  async resolvePlayback(cameraId, timestampUnix) {
    if (!this.haClient?.connection || !this.mediaContentIdResolver) {
      return new PlaybackResolution({
        available: false,
        cameraId,
        requestedUnix: timestampUnix,
        reason: 'edge_sd_not_configured',
        storageType: this.storageType,
      });
    }

    try {
      const contentId = await this.mediaContentIdResolver(cameraId, timestampUnix);
      if (!contentId) {
        return new PlaybackResolution({
          available: false,
          cameraId,
          requestedUnix: timestampUnix,
          reason: 'no_recording',
          storageType: this.storageType,
        });
      }
      const resolved = await this.haClient.connection.sendMessagePromise({
        type: 'media_source/resolve_media',
        media_content_id: contentId,
      });
      if (!resolved?.url) {
        return new PlaybackResolution({
          available: false,
          cameraId,
          requestedUnix: timestampUnix,
          reason: 'no_recording',
          storageType: this.storageType,
        });
      }
      return new PlaybackResolution({
        available: true,
        cameraId,
        requestedUnix: timestampUnix,
        streamUrl: resolved.url,
        seekOffsetSec: 0,
        reason: 'ok',
        storageType: this.storageType,
      });
    } catch {
      return new PlaybackResolution({
        available: false,
        cameraId,
        requestedUnix: timestampUnix,
        reason: 'edge_sd_error',
        storageType: this.storageType,
      });
    }
  }

  async attachHistoricalVideo(cameraId, videoElement, timestampUnix, opts = {}) {
    const resolution = await this.resolvePlayback(cameraId, timestampUnix);
    if (!resolution.available || !resolution.streamUrl) {
      this.detach(videoElement);
      return resolution;
    }
    videoElement.muted = true;
    videoElement.playsInline = true;
    videoElement.src = resolution.streamUrl;
    if (opts.playbackRate) {
      this.setPlaybackRate(videoElement, opts.playbackRate);
    }
    if (opts.autoplay) {
      videoElement.play().catch(() => {});
    }
    return resolution;
  }
}
