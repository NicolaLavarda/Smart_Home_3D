import * as THREE from 'three';
import { Go2RtcWebRTCStream } from './Go2RtcWebRTCStream.js';
import { Go2RtcMSEStream } from './Go2RtcMSEStream.js';
import { HaSnapshotFallbackStream } from './HaSnapshotFallbackStream.js';

function isProdSameOriginMode() {
  let isProdBuild = false;
  try { isProdBuild = Boolean(import.meta.env.PROD); } catch {}
  const isHttps = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  return isProdBuild || isHttps;
}

/**
 * VideoStreamManager
 *
 * Factory & Orchestratore per i flussi video live:
 * Gestisce il fallback automatico WebRTC (sub-second) -> MSE (WebSocket fMP4) -> Snapshot/Diagnostico,
 * e fornisce istanze riutilizzabili di THREE.VideoTexture per la proiezione 3D sul frustum POV.
 */
export class VideoStreamManager {
  constructor(options = {}) {
    const prodSameOrigin = isProdSameOriginMode();
    const origin = typeof window !== 'undefined' && window.location?.origin ? window.location.origin : '';
    const defaultHost = typeof window !== 'undefined' && window.location?.hostname ? window.location.hostname : '127.0.0.1';

    let envGo2rtcUrl = '';
    let envGo2rtcTailscale = '';
    let envSpatialUrl = '';
    try {
      if (!import.meta.env.PROD) {
        envGo2rtcUrl = import.meta.env.VITE_GO2RTC_URL || '';
        envGo2rtcTailscale = import.meta.env.VITE_GO2RTC_TAILSCALE_URL || '';
        envSpatialUrl = import.meta.env.VITE_SPATIAL_SERVER_URL || '';
      }
    } catch {}

    if (typeof options.go2rtcUrl === 'string' && options.go2rtcUrl.trim()) {
      this.go2rtcUrl = options.go2rtcUrl.trim().replace(/\/+$/, '');
    } else if (prodSameOrigin) {
      this.go2rtcUrl = (origin ? `${origin}/go2rtc` : '/go2rtc').replace(/\/+$/, '');
    } else {
      this.go2rtcUrl = (envGo2rtcUrl || 'http://localhost:1984').replace(/\/+$/, '');
    }

    if (typeof options.go2rtcTailscaleUrl === 'string' && options.go2rtcTailscaleUrl.trim()) {
      this.go2rtcTailscaleUrl = options.go2rtcTailscaleUrl.trim().replace(/\/+$/, '');
    } else if (prodSameOrigin) {
      this.go2rtcTailscaleUrl = '';
    } else {
      this.go2rtcTailscaleUrl = envGo2rtcTailscale.replace(/\/+$/, '');
    }

    if (typeof options.spatialServerUrl === 'string') {
      this.spatialServerUrl = options.spatialServerUrl.replace(/\/+$/, '');
    } else if (prodSameOrigin) {
      this.spatialServerUrl = '';
    } else {
      this.spatialServerUrl = (envSpatialUrl || `http://${defaultHost}:8765`).replace(/\/+$/, '');
    }

    this.haClient = options.haClient || null;
    this.cameraCatalog = options.cameraCatalog || null;
    this.activeElementProviders = new WeakMap();
    this.textureEntries = new Map(); // streamName -> { videoElement, texture, provider, refCount }
  }

  setCameraCatalog(cameraCatalog) {
    this.cameraCatalog = cameraCatalog;
  }

  setHAClient(haClient) {
    this.haClient = haClient;
  }

  setSpatialServerUrl(url) {
    if (typeof url === 'string') {
      this.spatialServerUrl = url.replace(/\/+$/, '');
    }
  }

  /**
   * Collega lo stream migliore disponibile all'elemento <video> passato.
   */
  async attachToVideoElement(streamName, videoElement, preferredMode = 'auto', extraOptions = {}) {
    if (!videoElement) throw new Error('HTMLVideoElement mancante');

    const prevProvider = this.activeElementProviders.get(videoElement);
    if (prevProvider) {
      prevProvider.disconnect();
      this.activeElementProviders.delete(videoElement);
    }

    const candidates = this.buildProviderChain(streamName, preferredMode, extraOptions);
    for (const provider of candidates) {
      const ok = await provider.connect(videoElement);
      if (ok) {
        this.activeElementProviders.set(videoElement, provider);
        console.log(`[VideoStreamManager] '${streamName}' connesso in modalità '${provider.mode.toUpperCase()}' (${provider.latencyMs}ms)`);
        return provider;
      }
    }

    throw new Error(`Impossibile avviare alcuno stream per '${streamName}'`);
  }

  buildProviderChain(streamName, preferredMode = 'auto', extraOptions = {}) {
    const isTailscale = Boolean(this.haClient?.isTailscale);
    const activeGo2RtcUrl = (isTailscale && this.go2rtcTailscaleUrl)
      ? this.go2rtcTailscaleUrl
      : this.go2rtcUrl;
    const isLocalGo2Rtc = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/|$)/i.test(activeGo2RtcUrl);
    const timeoutMs = (isTailscale && isLocalGo2Rtc) ? 1500 : undefined;

    const catalogEntry = this.cameraCatalog?.findByStreamName?.(streamName) || null;
    const resolvedCameraEntityId =
      extraOptions.cameraEntityId ||
      catalogEntry?.entityId ||
      'camera.carraio_scorrevole';

    const opts = {
      go2rtcUrl: activeGo2RtcUrl,
      haClient: this.haClient,
      spatialServerUrl: this.spatialServerUrl,
      cameraEntityId: resolvedCameraEntityId,
      cameraName: extraOptions.cameraName || catalogEntry?.id || 'Cam_Carraio',
      cameraLabel: extraOptions.cameraLabel || catalogEntry?.cameraModel || catalogEntry?.name || 'REOLINK RLC-540A',
      cameraIp: extraOptions.cameraIp || catalogEntry?.cameraIp || '192.168.86.47',
      ...(timeoutMs ? { timeoutMs } : {}),
    };

    if (preferredMode === 'webrtc') {
      return [new Go2RtcWebRTCStream(streamName, opts), new HaSnapshotFallbackStream(streamName, opts)];
    }
    if (preferredMode === 'mse') {
      return [new Go2RtcMSEStream(streamName, opts), new HaSnapshotFallbackStream(streamName, opts)];
    }
    if (preferredMode === 'snapshot') {
      return [new HaSnapshotFallbackStream(streamName, opts)];
    }

    return [
      new Go2RtcWebRTCStream(streamName, opts),
      new Go2RtcMSEStream(streamName, opts),
      new HaSnapshotFallbackStream(streamName, opts),
    ];
  }

  detachFromVideoElement(videoElement) {
    if (!videoElement) return;
    const provider = this.activeElementProviders.get(videoElement);
    if (provider) {
      provider.disconnect();
      this.activeElementProviders.delete(videoElement);
    }
  }

  /**
   * Acquisisce (o riusa) una THREE.VideoTexture per la proiezione 3D sul frustum POV.
   */
  async acquireVideoTexture(streamName = 'carraio_main', preferredMode = 'auto', extraOptions = {}) {
    const existing = this.textureEntries.get(streamName);
    if (existing && existing.provider?.connected) {
      existing.refCount += 1;
      return existing;
    }

    const videoElement = document.createElement('video');
    videoElement.muted = true;
    videoElement.autoplay = true;
    videoElement.playsInline = true;
    videoElement.crossOrigin = 'anonymous';

    const provider = await this.attachToVideoElement(streamName, videoElement, preferredMode, extraOptions);
    const texture = new THREE.VideoTexture(videoElement);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.generateMipmaps = false;

    const entry = { streamName, videoElement, texture, provider, refCount: 1 };
    this.textureEntries.set(streamName, entry);
    return entry;
  }

  releaseVideoTexture(streamName) {
    const entry = this.textureEntries.get(streamName);
    if (!entry) return;
    entry.refCount -= 1;
    if (entry.refCount <= 0) {
      this.detachFromVideoElement(entry.videoElement);
      entry.texture.dispose();
      this.textureEntries.delete(streamName);
    }
  }

  disposeAll() {
    for (const [name, entry] of this.textureEntries.entries()) {
      this.detachFromVideoElement(entry.videoElement);
      entry.texture.dispose();
      this.textureEntries.delete(name);
    }
  }
}

