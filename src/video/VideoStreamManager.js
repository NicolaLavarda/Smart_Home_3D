import * as THREE from 'three';
import { Go2RtcWebRTCStream } from './Go2RtcWebRTCStream.js';
import { Go2RtcMSEStream } from './Go2RtcMSEStream.js';
import { HaSnapshotFallbackStream } from './HaSnapshotFallbackStream.js';

/**
 * VideoStreamManager
 *
 * Factory & Orchestratore per i flussi video live:
 * Gestisce il fallback automatico WebRTC (sub-second) -> MSE (WebSocket fMP4) -> Snapshot/Diagnostico,
 * e fornisce istanze riutilizzabili di THREE.VideoTexture per la proiezione 3D sul frustum POV.
 */
export class VideoStreamManager {
  constructor(options = {}) {
    this.go2rtcUrl = (options.go2rtcUrl || import.meta.env.VITE_GO2RTC_URL || 'http://localhost:1984').replace(/\/+$/, '');
    this.haClient = options.haClient || null;
    this.activeElementProviders = new WeakMap();
    this.textureEntries = new Map(); // streamName -> { videoElement, texture, provider, refCount }
  }

  setHAClient(haClient) {
    this.haClient = haClient;
  }

  /**
   * Collega lo stream migliore disponibile all'elemento <video> passato.
   */
  async attachToVideoElement(streamName, videoElement, preferredMode = 'auto') {
    if (!videoElement) throw new Error('HTMLVideoElement mancante');

    const prevProvider = this.activeElementProviders.get(videoElement);
    if (prevProvider) {
      prevProvider.disconnect();
      this.activeElementProviders.delete(videoElement);
    }

    const candidates = this.buildProviderChain(streamName, preferredMode);
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

  buildProviderChain(streamName, preferredMode = 'auto') {
    const opts = {
      go2rtcUrl: this.go2rtcUrl,
      haClient: this.haClient,
      cameraEntityId: 'camera.carraio_scorrevole',
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
  async acquireVideoTexture(streamName = 'carraio_main', preferredMode = 'auto') {
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

    const provider = await this.attachToVideoElement(streamName, videoElement, preferredMode);
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

