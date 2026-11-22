import { IVideoStreamProvider } from './IVideoStreamProvider.js';

function isProdSameOriginMode() {
  let isProdBuild = false;
  try { isProdBuild = Boolean(import.meta.env.PROD); } catch {}
  const isHttps = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  return isProdBuild || isHttps;
}

/**
 * HaSnapshotFallbackStream
 *
 * Provider di fallback garantito:
 * 1. Usa i proxy same-origin / server-to-server (`/api/ha-camera/snapshot` su Vite dev
 *    e `/api/v1/ha-camera/snapshot/{entity_id}` su FastAPI) per recuperare i frame
 *    da Home Assistant (anche su Tailscale) senza blocchi CORS e con risoluzione
 *    automatica dell'entità camera reale.
 * 2. Altrimenti genera un feed diagnostico animato su Canvas (640x360 @ 15fps) con mirino ottico
 *    e stato della Reolink RLC-540A (192.168.86.47), così il player modale e THREE.VideoTexture
 *    restano sempre operativi senza errori WebGL.
 */
export class HaSnapshotFallbackStream extends IVideoStreamProvider {
  constructor(streamName, options = {}) {
    super(streamName, options);
    this.mode = 'snapshot';
    this.haClient = options.haClient || null;
    this.cameraEntityId = options.cameraEntityId || 'camera.carraio_scorrevole';
    this.resolvedEntityId = this.cameraEntityId;
    this.cameraName = String(options.cameraName || 'Cam_Carraio');
    this.cameraLabel = String(options.cameraLabel || 'REOLINK RLC-540A');
    this.cameraIp = String(options.cameraIp || '192.168.86.47');
    const prodSameOrigin = isProdSameOriginMode();
    const defaultHost = typeof window !== 'undefined' && window.location?.hostname ? window.location.hostname : '127.0.0.1';

    let envSpatialUrl = '';
    try {
      if (!import.meta.env.PROD) {
        envSpatialUrl = import.meta.env.VITE_SPATIAL_SERVER_URL || '';
      }
    } catch {}

    if (typeof options.spatialServerUrl === 'string') {
      this.spatialServerUrl = options.spatialServerUrl.replace(/\/+$/, '');
    } else if (prodSameOrigin) {
      this.spatialServerUrl = '';
    } else {
      this.spatialServerUrl = (envSpatialUrl || `http://${defaultHost}:8765`).replace(/\/+$/, '');
    }
    this.canvas = null;
    this.ctx = null;
    this.timerId = null;
    this.snapshotTimerId = null;
    this.capturedStream = null;
    this.lastImage = null;
    this.hasLiveHaFrames = false;
    this.lastHaError = null;
    this._fetching = false;
    this._aborted = false;
    this._fetchController = null;
    this.frameCounter = 0;
  }

  getStatus() {
    return {
      ...super.getStatus(),
      hasLiveHaFrames: this.hasLiveHaFrames,
      resolvedEntityId: this.resolvedEntityId,
      isTailscale: Boolean(this.haClient?.isTailscale),
      lastHaError: this.lastHaError,
    };
  }

  async connect(videoElement) {
    if (!videoElement) throw new Error('HTMLVideoElement richiesto');
    this.disconnect();
    this._aborted = false;
    this.videoElement = videoElement;

    this.canvas = document.createElement('canvas');
    this.canvas.width = 640;
    this.canvas.height = 360;
    this.ctx = this.canvas.getContext('2d');

    this.drawDiagnosticFrame();

    if (typeof this.canvas.captureStream === 'function') {
      this.capturedStream = this.canvas.captureStream(15);
      this.videoElement.srcObject = this.capturedStream;
    }
    this.videoElement.muted = true;
    this.videoElement.playsInline = true;
    await this.videoElement.play().catch(() => {});

    this.timerId = setInterval(() => this.drawDiagnosticFrame(), 66);
    this.startHaSnapshotPolling();

    this.connected = true;
    this.latencyMs = 65;
    this.lastError = null;
    this.notifyStatus();
    return true;
  }

  async _loadImageFromBlob(blob) {
    if (typeof createImageBitmap === 'function') {
      return await createImageBitmap(blob);
    }
    const objUrl = URL.createObjectURL(blob);
    return await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(objUrl);
        resolve(img);
      };
      img.onerror = (err) => {
        URL.revokeObjectURL(objUrl);
        reject(err);
      };
      img.src = objUrl;
    });
  }

  _releaseImage(img) {
    if (img && typeof img.close === 'function') {
      try {
        img.close();
      } catch {}
    }
  }

  startHaSnapshotPolling() {
    if (!this.haClient || this.haClient.isMockMode) return;

    const poll = async () => {
      if (this._aborted || this._fetching) return;
      if (!this.haClient || this.haClient.isMockMode) return;

      const entityId = typeof this.haClient.resolveCameraEntityId === 'function'
        ? this.haClient.resolveCameraEntityId(this.cameraEntityId)
        : this.cameraEntityId;
      this.resolvedEntityId = entityId;

      const activeHaUrl = typeof this.haClient.getActiveUrl === 'function'
        ? this.haClient.getActiveUrl()
        : (this.haClient.activeUrl || this.haClient.url || this.haClient.localUrl || '');

      const qsHaUrl = activeHaUrl ? `&ha_url=${encodeURIComponent(activeHaUrl)}` : '';
      const ts = Date.now();
      this._fetching = true;
      const t0 = performance.now();
      try {
        let accessToken = null;
        if (typeof this.haClient?.getAccessToken === 'function') {
          try {
            accessToken = await this.haClient.getAccessToken();
          } catch {
            accessToken = null;
          }
        } else if (this.haClient?.token) {
          accessToken = this.haClient.token;
        }
        if (this._aborted) return;

        const spatialParams = new URLSearchParams();
        if (activeHaUrl) spatialParams.set('ha_url', activeHaUrl);
        spatialParams.set('t', String(ts));
        const spatialSnapshotUrl = `${this.spatialServerUrl}/api/v1/ha-camera/snapshot/${encodeURIComponent(entityId)}?${spatialParams.toString()}`;

        const proxyCandidates = isProdSameOriginMode()
          ? [spatialSnapshotUrl]
          : [
              `/api/ha-camera/snapshot?entity_id=${encodeURIComponent(entityId)}${qsHaUrl}&t=${ts}`,
              spatialSnapshotUrl,
            ];

        let lastErr = null;
        for (const url of proxyCandidates) {
          if (this._aborted) return;
          this._fetchController = new AbortController();
          const timer = setTimeout(() => this._fetchController?.abort(), 3200);
          try {
            const headers = {};
            if (accessToken) {
              headers.Authorization = `Bearer ${accessToken}`;
            }
            const resp = await fetch(url, {
              cache: 'no-store',
              credentials: 'include',
              headers,
              signal: this._fetchController.signal,
            });
            clearTimeout(timer);

            if (!resp.ok) {
              const errText = await resp.text().catch(() => '');
              lastErr = `HTTP ${resp.status}${errText ? `: ${errText.slice(0, 80)}` : ''}`;
              continue;
            }

            const contentType = resp.headers?.get?.('content-type') || '';
            if (!contentType.toLowerCase().startsWith('image/')) {
              lastErr = `Risposta non immagine (${contentType || 'content-type mancante'})`;
              continue;
            }

            const blob = await resp.blob();
            if (!blob || blob.size === 0 || this._aborted) {
              lastErr = 'Frame JPEG vuoto';
              continue;
            }

            const nextImg = await this._loadImageFromBlob(blob);
            if (this._aborted) {
              this._releaseImage(nextImg);
              return;
            }

            const prevImg = this.lastImage;
            this.lastImage = nextImg;
            this._releaseImage(prevImg);

            const wasLive = this.hasLiveHaFrames;
            this.hasLiveHaFrames = true;
            this.lastHaError = null;
            this.latencyMs = Math.round(performance.now() - t0);
            if (!wasLive) {
              this.notifyStatus();
            }
            return;
          } catch (err) {
            clearTimeout(timer);
            lastErr = err?.message || 'Errore fetch snapshot HA';
          }
        }
        this.lastHaError = lastErr;
      } finally {
        this._fetchController = null;
        this._fetching = false;
      }
    };

    poll();
    this.snapshotTimerId = setInterval(poll, 650);
  }

  drawDiagnosticFrame() {
    if (!this.ctx || !this.canvas) return;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    this.frameCounter += 1;

    if (this.lastImage) {
      ctx.drawImage(this.lastImage, 0, 0, w, h);
    } else {
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, '#09111e');
      grad.addColorStop(0.55, '#0f172a');
      grad.addColorStop(1, '#111827');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);

      // Griglia ottica calibrata per allineamento POV
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.16)';
      ctx.lineWidth = 1;
      for (let x = 0; x <= w; x += 64) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y <= h; y += 45) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // Mirino centrale
      ctx.strokeStyle = 'rgba(6, 182, 212, 0.65)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(w / 2, h / 2, 28, 0, Math.PI * 2);
      ctx.moveTo(w / 2 - 42, h / 2);
      ctx.lineTo(w / 2 + 42, h / 2);
      ctx.moveTo(w / 2, h / 2 - 42);
      ctx.lineTo(w / 2, h / 2 + 42);
      ctx.stroke();

      // Linea scansione leggera
      const scanY = (this.frameCounter * 3) % h;
      ctx.fillStyle = 'rgba(6, 182, 212, 0.08)';
      ctx.fillRect(0, scanY, w, 6);

      ctx.fillStyle = '#e2e8f0';
      ctx.font = 'bold 16px "Segoe UI", system-ui, sans-serif';
      ctx.textAlign = 'center';

      const headerTitle = this.cameraLabel.toUpperCase();
      if (this.haClient?.isTailscale) {
        ctx.fillText(`${headerTitle} • MODALITÀ TAILSCALE REMOTA`, w / 2, h / 2 - 62);
        ctx.fillStyle = '#94a3b8';
        ctx.font = '12px monospace';
        ctx.fillText(`Stream: ${this.streamName} • Entità HA: ${this.resolvedEntityId}`, w / 2, h / 2 + 58);
        ctx.fillText('Attesa frame HA Bridge (o attiva Tailscale Subnet Router 192.168.86.0/24)', w / 2, h / 2 + 80);
        if (this.lastHaError) {
          ctx.fillStyle = '#fbbf24';
          ctx.fillText(`Dettaglio: ${this.lastHaError.slice(0, 68)}`, w / 2, h / 2 + 102);
        }
      } else {
        ctx.fillText(`${headerTitle} • STREAM DIAGNOSTICO / STANDBY`, w / 2, h / 2 - 58);
        ctx.fillStyle = '#94a3b8';
        ctx.font = '13px monospace';
        ctx.fillText(`Stream: ${this.streamName} • IP ${this.cameraIp}`, w / 2, h / 2 + 64);
        ctx.fillText('Abilita RTSP/FLV su Reolink & inserisci password in .env per video live', w / 2, h / 2 + 86);
      }
    }

    // Timestamp OSD in alto
    const nowStr = new Date().toLocaleTimeString('it-IT', { hour12: false });
    const modeTag = this.hasLiveHaFrames
      ? (this.haClient?.isTailscale ? 'HA TAILSCALE' : 'HA BRIDGE')
      : 'STANDBY';
    ctx.fillStyle = 'rgba(15, 23, 42, 0.72)';
    ctx.fillRect(14, 14, 290, 26);
    ctx.fillStyle = this.hasLiveHaFrames ? '#34d399' : '#38bdf8';
    ctx.font = 'bold 12px monospace';
    ctx.textAlign = 'left';
    ctx.fillText(`${this.cameraName.toUpperCase()} • ${modeTag} • ${nowStr}`, 22, 31);
  }

  disconnect() {
    this._aborted = true;
    this.connected = false;
    this.hasLiveHaFrames = false;
    this._fetching = false;
    if (this._fetchController) {
      try {
        this._fetchController.abort();
      } catch {}
      this._fetchController = null;
    }
    if (this.timerId) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
    if (this.snapshotTimerId) {
      clearInterval(this.snapshotTimerId);
      this.snapshotTimerId = null;
    }
    if (this.capturedStream) {
      this.capturedStream.getTracks().forEach((t) => t.stop());
      this.capturedStream = null;
    }
    this._releaseImage(this.lastImage);
    this.lastImage = null;
    if (this.videoElement && this.videoElement.srcObject) {
      this.videoElement.srcObject = null;
    }
    this.notifyStatus();
  }
}

