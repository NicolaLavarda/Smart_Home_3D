import { IVideoStreamProvider } from './IVideoStreamProvider.js';

/**
 * HaSnapshotFallbackStream
 *
 * Provider di fallback garantito:
 * 1. Se Home Assistant fornisce `entity_picture` valida sull'entità camera, la aggiorna periodicamente.
 * 2. Altrimenti genera un feed diagnostico animato su Canvas (640x360 @ 15fps) con mirino ottico
 *    e stato della Reolink RLC-540A (192.168.86.47), così il player modale e THREE.VideoTexture
 *    restano sempre operativi senza errori WebGL anche prima di inserire la password Reolink.
 */
export class HaSnapshotFallbackStream extends IVideoStreamProvider {
  constructor(streamName, options = {}) {
    super(streamName, options);
    this.mode = 'snapshot';
    this.haClient = options.haClient || null;
    this.cameraEntityId = options.cameraEntityId || 'camera.carraio_scorrevole';
    this.canvas = null;
    this.ctx = null;
    this.timerId = null;
    this.snapshotTimerId = null;
    this.capturedStream = null;
    this.lastImage = null;
    this.frameCounter = 0;
  }

  async connect(videoElement) {
    if (!videoElement) throw new Error('HTMLVideoElement richiesto');
    this.disconnect();
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

  startHaSnapshotPolling() {
    if (!this.haClient || this.haClient.isMockMode) return;
    const poll = () => {
      const entity = this.haClient.entities?.[this.cameraEntityId];
      const pic = entity?.attributes?.entity_picture;
      if (!pic) return;
      const base = (this.haClient.url || this.haClient.localUrl || '').replace(/\/+$/, '');
      if (!base) return;
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        this.lastImage = img;
      };
      img.src = `${base}${pic}${pic.includes('?') ? '&' : '?'}t=${Date.now()}`;
    };
    poll();
    this.snapshotTimerId = setInterval(poll, 1500);
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
      ctx.font = 'bold 17px "Segoe UI", system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('REOLINK RLC-540A • STREAM DIAGNOSTICO / STANDBY', w / 2, h / 2 - 58);

      ctx.fillStyle = '#94a3b8';
      ctx.font = '13px monospace';
      ctx.fillText(`Stream: ${this.streamName} • IP 192.168.86.47`, w / 2, h / 2 + 64);
      ctx.fillText('Abilita RTSP/FLV su Reolink & inserisci password in .env per video live', w / 2, h / 2 + 86);
    }

    // Timestamp OSD in alto
    const nowStr = new Date().toLocaleTimeString('it-IT', { hour12: false });
    ctx.fillStyle = 'rgba(15, 23, 42, 0.72)';
    ctx.fillRect(14, 14, 240, 26);
    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 12px monospace';
    ctx.textAlign = 'left';
    ctx.fillText(`CAM_CARRAIO • ${nowStr}`, 22, 31);
  }

  disconnect() {
    this.connected = false;
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
    if (this.videoElement && this.videoElement.srcObject) {
      this.videoElement.srcObject = null;
    }
    this.notifyStatus();
  }
}

