import * as THREE from 'three';
import { Go2RtcWebRTCStream } from './Go2RtcWebRTCStream.js';
import { Go2RtcMSEStream } from './Go2RtcMSEStream.js';
import { HaSnapshotFallbackStream } from './HaSnapshotFallbackStream.js';

const DEFAULT_TEXTURE_GRACE_TTL_MS = 30_000;

function isProdSameOriginMode() {
  let isProdBuild = false;
  try { isProdBuild = Boolean(import.meta.env.PROD); } catch { }
  const isHttps = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  return isProdBuild || isHttps;
}

function unrefTimer(timer) {
  if (timer && typeof timer.unref === 'function') {
    try {
      timer.unref();
    } catch { }
  }
  return timer;
}

/**
 * VideoStreamManager
 *
 * Factory & Orchestratore per i flussi video live:
 * - Connette direttamente i provider (WebRTC -> MSE -> Snapshot) agli elementi <video>
 *   reali del DOM (come i 4 tile persistenti di SecurityFabHub), senza proxy offscreen.
 * - Mantiene in memoria le sessioni live attive (`primarySessions`) per condividerle
 *   a 0ms con SecurityCameraModal (clonando il MediaStream) e con Vista POV 3D /
 *   Calibrazione Ottica (avvolgendo direttamente il <video> già attivo in THREE.VideoTexture).
 * - Applica un Grace TTL (30s) su `releaseVideoTexture` così il passaggio tra
 *   Vista POV 3D e Calibrazione Ottica (`suspendForCalibration` -> `calibUI.open`)
 *   avviene in 0ms senza mai ricaricare lo stream.
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
    } catch { }

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
    this.mainIdleTtlMs = options.mainIdleTtlMs ?? DEFAULT_TEXTURE_GRACE_TTL_MS;

    this.activeElementProviders = new WeakMap(); // HTMLVideoElement -> provider
    this.pendingElementConnections = new WeakMap(); // HTMLVideoElement -> { streamName, promise }
    this.pendingStreamConnections = new Map();   // streamName -> { videoElement, promise }
    this.primarySessions = new Map();            // streamName -> { streamName, videoElement, provider, clones: Set<HTMLVideoElement> }
    this.cloneBindings = new WeakMap();          // HTMLVideoElement -> session
    this.textureEntries = new Map();             // streamName -> { streamName, videoElement, texture, provider, refCount, ownsVideoElement, idleTimer }
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

  getActiveProvider(videoElement) {
    if (!videoElement) return null;
    return this.activeElementProviders.get(videoElement) || null;
  }

  /**
   * Un provider è considerato realmente live e riutilizzabile se è connesso in WebRTC, MSE,
   * oppure se ha ricevuto veri frame snapshot da Home Assistant (MAI il canvas STANDBY).
   */
  _isProviderLive(provider) {
    if (!provider || !provider.connected) return false;
    if (provider.mode === 'webrtc' || provider.mode === 'mse') return true;
    if (provider.mode === 'snapshot' && Boolean(provider.hasLiveHaFrames)) return true;
    return false;
  }

  getWarmSubStreamName(streamName) {
    if (!streamName || typeof streamName !== 'string') return null;
    const entry = this.cameraCatalog?.findByStreamName?.(streamName) || null;
    if (entry && entry.mainStream === streamName && entry.subStream && entry.subStream !== streamName) {
      return entry.subStream;
    }
    if (/_main$/i.test(streamName)) {
      return streamName.replace(/_main$/i, '_sub');
    }
    return null;
  }

  isStreamReady(streamName) {
    return Boolean(this._findLiveSession(streamName, { allowSubReuse: true }));
  }

  isElementConnecting(videoElement, streamName = null) {
    if (!videoElement) return false;
    const pending = this.pendingElementConnections.get(videoElement);
    if (!pending) return false;
    return streamName ? pending.streamName === streamName : true;
  }

  _findLiveSession(streamName, { allowSubReuse = true } = {}) {
    const exact = this.primarySessions.get(streamName);
    if (exact && this._isProviderLive(exact.provider)) {
      return exact;
    }
    if (allowSubReuse) {
      const subName = this.getWarmSubStreamName(streamName);
      if (subName) {
        const subSession = this.primarySessions.get(subName);
        if (subSession && this._isProviderLive(subSession.provider)) {
          return subSession;
        }
      }
    }
    return null;
  }

  _attachCloneToSession(session, targetVideoEl) {
    if (!session || !session.provider || !targetVideoEl) return false;
    if (session.videoElement === targetVideoEl) return true;

    const provider = session.provider;
    let sharedStream = null;

    if (provider.mediaStream) {
      sharedStream = provider.mediaStream;
    } else if (provider.capturedStream) {
      sharedStream = provider.capturedStream;
    } else if (session.videoElement?.srcObject && typeof session.videoElement.srcObject.getTracks === 'function') {
      sharedStream = session.videoElement.srcObject;
    } else if (provider.mode === 'mse' && session.videoElement) {
      const capFn = session.videoElement.captureStream || session.videoElement.mozCaptureStream;
      if (typeof capFn === 'function') {
        try {
          const captured = capFn.call(session.videoElement);
          const tracks = typeof captured?.getVideoTracks === 'function'
            ? captured.getVideoTracks()
            : (typeof captured?.getTracks === 'function' ? captured.getTracks() : []);
          if (captured && tracks.length > 0) {
            sharedStream = captured;
          }
        } catch { }
      }
    }

    if (!sharedStream) return false;

    try {
      targetVideoEl.removeAttribute?.('src');
    } catch { }
    if (provider.mode === 'mse' || session.videoElement?.disableRemotePlayback) {
      targetVideoEl.disableRemotePlayback = true;
    }
    targetVideoEl.muted = true;
    targetVideoEl.playsInline = true;
    targetVideoEl.srcObject = sharedStream;
    targetVideoEl.play?.().catch(() => { });

    session.clones.add(targetVideoEl);
    this.cloneBindings.set(targetVideoEl, session);
    this.activeElementProviders.set(targetVideoEl, provider);
    return true;
  }

  _registerPrimarySession(streamName, videoElement, provider) {
    const existing = this.primarySessions.get(streamName);
    const clones = existing && existing.videoElement === videoElement ? existing.clones : new Set();
    const session = {
      streamName,
      videoElement,
      provider,
      clones,
    };
    this.primarySessions.set(streamName, session);
    return session;
  }

  /**
   * Collega lo stream migliore disponibile all'elemento <video> passato.
   * - Se l'elemento <video> ha già una sessione live attiva per quello stream, la mantiene a 0ms.
   * - Se un altro elemento <video> (es. il tile persistente di SecurityFabHub) ha già lo stream
   *   (o il relativo sub-stream) attivo e live, ne condivide il MediaStream a 0ms senza ricaricare.
   * - Altrimenti connette il provider direttamente all'elemento <video> (identico a HEAD).
   */
  async attachToVideoElement(streamName, videoElement, preferredMode = 'auto', extraOptions = {}) {
    if (!videoElement) throw new Error('HTMLVideoElement mancante');

    const forceReconnect = Boolean(extraOptions.forceReconnect);
    const allowSubReuse = extraOptions.allowSubReuse !== false;

    // 0. Se una connessione per lo stesso streamName è GIÀ in corso su questo esatto <video>,
    //    attendi la stessa Promise evitando connessioni duplicate concorrenti sullo stesso elemento!
    const pendingOnEl = this.pendingElementConnections.get(videoElement);
    if (!forceReconnect && pendingOnEl && pendingOnEl.streamName === streamName) {
      return await pendingOnEl.promise;
    }

    // 1. Se questo esatto <video> è già il titolare live dello stream richiesto, non disconnetterlo!
    const currentProvider = this.activeElementProviders.get(videoElement);
    const existingPrimary = this.primarySessions.get(streamName);
    if (
      !forceReconnect &&
      existingPrimary &&
      existingPrimary.videoElement === videoElement &&
      currentProvider === existingPrimary.provider &&
      this._isProviderLive(currentProvider) &&
      (preferredMode === 'auto' || currentProvider.mode === preferredMode)
    ) {
      videoElement.play?.().catch(() => { });
      return currentProvider;
    }

    // Pulisci eventuale binding precedente su questo elemento <video>
    this.detachFromVideoElement(videoElement);

    // 2. Riuso istantaneo a 0ms da una sessione live già attiva (es. SecurityFabHub -> SecurityCameraModal)
    if (!forceReconnect && preferredMode === 'auto') {
      let liveSession = this._findLiveSession(streamName, { allowSubReuse });
      if (!liveSession) {
        const subName = allowSubReuse ? this.getWarmSubStreamName(streamName) : null;
        const pendingPrimary = this.pendingStreamConnections.get(streamName) || (subName ? this.pendingStreamConnections.get(subName) : null);
        if (pendingPrimary && pendingPrimary.videoElement !== videoElement) {
          try {
            await pendingPrimary.promise;
          } catch { }
          liveSession = this._findLiveSession(streamName, { allowSubReuse });
        }
      }
      if (liveSession && liveSession.videoElement !== videoElement) {
        if (this._attachCloneToSession(liveSession, videoElement)) {
          return liveSession.provider;
        }
      }
    }

    // 3. Connessione diretta sul <video> passato (100% identica a HEAD), deduplicata per elemento
    const connectWork = (async () => {
      const candidates = this.buildProviderChain(streamName, preferredMode, extraOptions);
      const subStreamName = (preferredMode === 'auto' && this.cameraCatalog)
        ? this.getWarmSubStreamName(streamName)
        : null;

      // Se stiamo connettendo un *_main a freddo (es. 4K/16MP H.265) e WebRTC+MSE falliscono sul main,
      // proviamo WebRTC+MSE sul *_sub H.264 prima di cadere sul fallback Snapshot/STANDBY.
      const liveCandidates = subStreamName
        ? candidates.filter((p) => p.mode !== 'snapshot')
        : candidates;

      for (const provider of liveCandidates) {
        const ok = await provider.connect(videoElement);
        if (ok) {
          this.activeElementProviders.set(videoElement, provider);
          if (this._isProviderLive(provider)) {
            this._registerPrimarySession(streamName, videoElement, provider);
          } else if (typeof provider.onStatusChange === 'function') {
            provider.onStatusChange((st) => {
              if (st?.hasLiveHaFrames && this.activeElementProviders.get(videoElement) === provider) {
                this._registerPrimarySession(streamName, videoElement, provider);
              }
            });
          }
          console.log(`[VideoStreamManager] '${streamName}' connesso in modalità '${provider.mode.toUpperCase()}' (${provider.latencyMs}ms)`);
          return provider;
        }
      }

      if (subStreamName) {
        const liveSubSession = this.primarySessions.get(subStreamName);
        if (liveSubSession && this._isProviderLive(liveSubSession.provider) && liveSubSession.videoElement !== videoElement) {
          if (this._attachCloneToSession(liveSubSession, videoElement)) {
            return liveSubSession.provider;
          }
        }

        const subCandidates = this.buildProviderChain(subStreamName, 'auto', extraOptions).filter((p) => p.mode !== 'snapshot');
        for (const subProvider of subCandidates) {
          const ok = await subProvider.connect(videoElement);
          if (ok) {
            this.activeElementProviders.set(videoElement, subProvider);
            this._registerPrimarySession(subStreamName, videoElement, subProvider);
            console.log(`[VideoStreamManager] '${streamName}' -> fallback live '${subStreamName}' in modalità '${subProvider.mode.toUpperCase()}' (${subProvider.latencyMs}ms)`);
            return subProvider;
          }
        }

        const snapshotCandidates = candidates.filter((p) => p.mode === 'snapshot');
        for (const snapProvider of snapshotCandidates) {
          const ok = await snapProvider.connect(videoElement);
          if (ok) {
            this.activeElementProviders.set(videoElement, snapProvider);
            if (typeof snapProvider.onStatusChange === 'function') {
              snapProvider.onStatusChange((st) => {
                if (st?.hasLiveHaFrames && this.activeElementProviders.get(videoElement) === snapProvider) {
                  this._registerPrimarySession(streamName, videoElement, snapProvider);
                }
              });
            }
            console.log(`[VideoStreamManager] '${streamName}' connesso in modalità '${snapProvider.mode.toUpperCase()}' (${snapProvider.latencyMs}ms)`);
            return snapProvider;
          }
        }
      }

      throw new Error(`Impossibile avviare alcuno stream per '${streamName}'`);
    })();

    const pendingRecord = { streamName, videoElement, promise: connectWork };
    this.pendingElementConnections.set(videoElement, pendingRecord);
    if (!this.pendingStreamConnections.has(streamName)) {
      this.pendingStreamConnections.set(streamName, pendingRecord);
    }

    try {
      return await connectWork;
    } finally {
      if (this.pendingElementConnections.get(videoElement) === pendingRecord) {
        this.pendingElementConnections.delete(videoElement);
      }
      if (this.pendingStreamConnections.get(streamName) === pendingRecord) {
        this.pendingStreamConnections.delete(streamName);
      }
    }
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
      aspectRatio: extraOptions.aspectRatio || catalogEntry?.aspectRatio || (16 / 9),
      isPanoramic180: Boolean(extraOptions.isPanoramic180 ?? catalogEntry?.isPanoramic180),
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

    // 1. Se questo <video> era un clone di una sessione primaria (es. modale camera che si chiude),
    //    sgancia solo il clone lasciando intatto lo stream primario!
    const clonedSession = this.cloneBindings.get(videoElement);
    if (clonedSession) {
      clonedSession.clones.delete(videoElement);
      this.cloneBindings.delete(videoElement);
      this.activeElementProviders.delete(videoElement);
      try {
        if (videoElement.srcObject) {
          videoElement.srcObject = null;
        }
      } catch { }
      return;
    }

    // 2. Se era il <video> primario, disconnetti il provider e rimuovi la sessione primaria
    for (const [key, session] of this.primarySessions.entries()) {
      if (session.videoElement === videoElement) {
        for (const cloneEl of Array.from(session.clones)) {
          this.cloneBindings.delete(cloneEl);
          this.activeElementProviders.delete(cloneEl);
          try {
            if (cloneEl.srcObject) cloneEl.srcObject = null;
          } catch { }
        }
        session.clones.clear();
        this.primarySessions.delete(key);
      }
    }

    const provider = this.activeElementProviders.get(videoElement);
    if (provider) {
      provider.disconnect();
      this.activeElementProviders.delete(videoElement);
    }
  }

  _createThreeVideoTexture(videoElement) {
    const texture = new THREE.VideoTexture(videoElement);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.generateMipmaps = false;
    return texture;
  }

  /**
   * Acquisisce (o riusa a 0ms) una THREE.VideoTexture per la proiezione 3D sul frustum POV e Calibrazione:
   * 1. Se la texture per `streamName` è già in cache (es. passaggio POV -> Calibrazione entro il Grace TTL di 30s),
   *    la restituisce in 0ms incrementando `refCount`.
   * 2. Se esiste già un elemento `<video>` live attivo per questa telecamera (es. il tile di SecurityFabHub
   *    che sta riproducendo `*_sub`), avvolge direttamente quel `<video>` in una `THREE.VideoTexture` a 0ms
   *    senza aprire alcuna nuova connessione di rete.
   * 3. Altrimenti crea un elemento `<video>` dedicato e lo connette direttamente.
   */
  async acquireVideoTexture(streamName = 'carraio_main', preferredMode = 'auto', extraOptions = {}) {
    const existing = this.textureEntries.get(streamName);
    if (existing) {
      if (this._isProviderLive(existing.provider)) {
        if (existing.idleTimer) {
          clearTimeout(existing.idleTimer);
          existing.idleTimer = null;
        }
        existing.refCount += 1;
        return existing;
      }
      // Se era su un fallback STANDBY non live, rimuovilo per ritentare la connessione
      this._disposeTextureEntryImmediate(streamName, existing);
    }

    // Riusa a 0ms il <video> live già attivo (es. da SecurityFabHub) senza aprire nuove connessioni!
    if (preferredMode === 'auto' && !extraOptions.forceReconnect) {
      const liveSession = this._findLiveSession(streamName, { allowSubReuse: extraOptions.allowSubReuse !== false });
      if (liveSession && liveSession.videoElement) {
        const texture = this._createThreeVideoTexture(liveSession.videoElement);
        const entry = {
          streamName,
          activeStreamName: liveSession.streamName,
          videoElement: liveSession.videoElement,
          texture,
          provider: liveSession.provider,
          refCount: 1,
          ownsVideoElement: false,
          isFallbackToSub: Boolean(liveSession.streamName !== streamName),
          idleTimer: null,
        };
        this.textureEntries.set(streamName, entry);
        return entry;
      }
    }

    const videoElement = document.createElement('video');
    videoElement.muted = true;
    videoElement.autoplay = true;
    videoElement.playsInline = true;
    videoElement.crossOrigin = 'anonymous';

    const provider = await this.attachToVideoElement(streamName, videoElement, preferredMode, extraOptions);
    const texture = this._createThreeVideoTexture(videoElement);

    const entry = {
      streamName,
      activeStreamName: provider.streamName || streamName,
      videoElement,
      texture,
      provider,
      refCount: 1,
      ownsVideoElement: true,
      isFallbackToSub: Boolean(provider.streamName && provider.streamName !== streamName),
      idleTimer: null,
    };
    this.textureEntries.set(streamName, entry);
    return entry;
  }

  _disposeTextureEntryImmediate(streamName, entry) {
    if (!entry) return;
    if (entry.idleTimer) {
      clearTimeout(entry.idleTimer);
      entry.idleTimer = null;
    }
    if (entry.ownsVideoElement) {
      this.detachFromVideoElement(entry.videoElement);
    }
    try {
      entry.texture?.dispose?.();
    } catch { }
    if (this.textureEntries.get(streamName) === entry) {
      this.textureEntries.delete(streamName);
    }
  }

  releaseVideoTexture(streamName) {
    const entry = this.textureEntries.get(streamName);
    if (!entry) return;
    entry.refCount = Math.max(0, entry.refCount - 1);
    if (entry.refCount > 0) return;

    if (entry.idleTimer) {
      clearTimeout(entry.idleTimer);
      entry.idleTimer = null;
    }

    // Mantiene viva la texture per il Grace TTL (30s) se lo stream è realmente live,
    // così il passaggio POV -> Calibrazione (`suspendForCalibration` -> `calibUI.open`) è a 0ms!
    if (this.mainIdleTtlMs > 0 && this._isProviderLive(entry.provider)) {
      entry.idleTimer = unrefTimer(
        setTimeout(() => {
          entry.idleTimer = null;
          if (entry.refCount <= 0 && this.textureEntries.get(streamName) === entry) {
            this._disposeTextureEntryImmediate(streamName, entry);
          }
        }, this.mainIdleTtlMs)
      );
      return;
    }

    this._disposeTextureEntryImmediate(streamName, entry);
  }

  disposeAll() {
    for (const [name, entry] of Array.from(this.textureEntries.entries())) {
      this._disposeTextureEntryImmediate(name, entry);
    }
    for (const session of Array.from(this.primarySessions.values())) {
      this.detachFromVideoElement(session.videoElement);
    }
    this.primarySessions.clear();
  }
}
