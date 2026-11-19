import { IVideoStreamProvider } from './IVideoStreamProvider.js';

function isProdSameOriginMode() {
  let isProdBuild = false;
  try { isProdBuild = Boolean(import.meta.env.PROD); } catch {}
  const isHttps = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  return isProdBuild || isHttps;
}

function getMediaSourceConstructor() {
  const win = typeof window !== 'undefined' ? window : {};
  const g = typeof globalThis !== 'undefined' ? globalThis : {};
  return (
    win.ManagedMediaSource ||
    g.ManagedMediaSource ||
    win.MediaSource ||
    g.MediaSource ||
    (typeof ManagedMediaSource !== 'undefined' ? ManagedMediaSource : null) ||
    (typeof MediaSource !== 'undefined' ? MediaSource : null)
  );
}

/**
 * Go2RtcMSEStream
 *
 * Provider di streaming via Media Source Extensions (fMP4 su WebSocket go2rtc).
 * Supporta anche ManagedMediaSource su iOS 17+ Safari/PWA.
 */
export class Go2RtcMSEStream extends IVideoStreamProvider {
  constructor(streamName, options = {}) {
    super(streamName, options);
    this.mode = 'mse';
    const prodSameOrigin = isProdSameOriginMode();
    const origin = typeof window !== 'undefined' && window.location?.origin ? window.location.origin : '';
    let devGo2rtcUrl = '';
    try {
      if (!import.meta.env.PROD) {
        devGo2rtcUrl = import.meta.env.VITE_GO2RTC_URL || import.meta.env.VITE_GO2RTC_TAILSCALE_URL || '';
      }
    } catch {}
    const fallbackUrl = prodSameOrigin
      ? (origin ? `${origin}/go2rtc` : '/go2rtc')
      : (devGo2rtcUrl || 'http://localhost:1984');
    this.baseUrl = (options.go2rtcUrl || fallbackUrl).replace(/\/+$/, '');
    this.timeoutMs = options.timeoutMs ?? 4500;
    this.ws = null;
    this.mediaSource = null;
    this.sourceBuffer = null;
    this.queue = [];
    this.objectUrl = null;
    this._aborted = false;
    this._connectTimer = null;
  }

  getSupportedCodecs() {
    const MS = getMediaSourceConstructor();
    if (!MS || typeof MS.isTypeSupported !== 'function') return '';
    const candidates = [
      'avc1.640029', // H.264 High L4.1
      'avc1.64002A', // H.264 High L4.2
      'avc1.42E01E', // H.264 Baseline
      'hvc1.1.6.L153.B0', // H.265 / HEVC
      'mp4a.40.2', // AAC
      'opus',
    ];
    return candidates
      .filter((c) => {
        const mime = c.startsWith('mp4a') || c === 'opus'
          ? `audio/mp4; codecs="${c}"`
          : `video/mp4; codecs="${c}"`;
        return MS.isTypeSupported(mime);
      })
      .join(',');
  }

  async connect(videoElement) {
    if (!videoElement) throw new Error('HTMLVideoElement richiesto');
    const MS = getMediaSourceConstructor();
    if (!MS) {
      this.lastError = 'MediaSource / ManagedMediaSource non supportate';
      return false;
    }

    this.disconnect();
    this._aborted = false;
    this.videoElement = videoElement;
    const t0 = performance.now();

    let wsBase = this.baseUrl;
    if (wsBase.startsWith('/') && typeof window !== 'undefined' && window.location?.host) {
      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      wsBase = `${wsProto}//${window.location.host}${wsBase}`;
    } else {
      wsBase = wsBase.replace(/^http/i, 'ws');
    }
    const wsUrl = `${wsBase}/api/ws?src=${encodeURIComponent(this.streamName)}`;

    try {
      await new Promise((resolve, reject) => {
        this._connectTimer = setTimeout(() => {
          reject(new Error(`Timeout MSE (${this.timeoutMs}ms) per '${this.streamName}'`));
        }, this.timeoutMs);

        const ms = new MS();
        this.mediaSource = ms;
        this.videoElement.disableRemotePlayback = true;
        this.videoElement.muted = true;
        this.videoElement.playsInline = true;

        ms.addEventListener('sourceopen', () => {
          if (this._aborted) return;
          const ws = new WebSocket(wsUrl);
          ws.binaryType = 'arraybuffer';
          this.ws = ws;

          ws.onopen = () => {
            ws.send(JSON.stringify({ type: 'mse', value: this.getSupportedCodecs() }));
          };

          ws.onerror = () => {
            clearTimeout(this._connectTimer);
            this._connectTimer = null;
            reject(new Error('Errore connessione WebSocket MSE go2rtc'));
          };

          ws.onclose = () => {
            if (!this.connected) {
              clearTimeout(this._connectTimer);
              this._connectTimer = null;
              reject(new Error('WebSocket MSE chiuso prima dello stream'));
            }
          };

          ws.onmessage = (ev) => {
            if (this._aborted) return;
            if (typeof ev.data === 'string') {
              let msg;
              try {
                msg = JSON.parse(ev.data);
              } catch {
                console.warn('[Go2RtcMSEStream] Messaggio testuale non JSON:', ev.data);
                return;
              }
              if (msg.type === 'mse' && msg.value) {
                try {
                  this.sourceBuffer = ms.addSourceBuffer(msg.value);
                  this.sourceBuffer.mode = 'segments';
                  this.sourceBuffer.addEventListener('updateend', () => this.flushQueue());
                } catch (sbErr) {
                  clearTimeout(this._connectTimer);
                  this._connectTimer = null;
                  reject(sbErr);
                }
              } else if (msg.type === 'error') {
                clearTimeout(this._connectTimer);
                this._connectTimer = null;
                reject(new Error(msg.value || 'Errore MSE go2rtc'));
              }
              return;
            }

            // Frame binario fMP4
            this.queue.push(new Uint8Array(ev.data));
            this.flushQueue();

            if (!this.connected) {
              this.connected = true;
              this.latencyMs = Math.round(performance.now() - t0);
              this.lastError = null;
              clearTimeout(this._connectTimer);
              this._connectTimer = null;
              this.videoElement.play().catch(() => {});
              this.notifyStatus();
              resolve();
            }
          };
        });

        if (typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function') {
          try {
            this.objectUrl = URL.createObjectURL(ms);
            this.videoElement.src = this.objectUrl;
          } catch {
            this.objectUrl = null;
            this.videoElement.srcObject = ms;
          }
        } else {
          this.videoElement.srcObject = ms;
        }
      });
      return true;
    } catch (err) {
      this.lastError = err?.message || 'Errore MSE go2rtc';
      this.disconnect();
      return false;
    }
  }

  flushQueue() {
    if (!this.sourceBuffer || this.sourceBuffer.updating || this.queue.length === 0) return;
    if (this.mediaSource && this.mediaSource.readyState !== 'open') return;

    try {
      const chunk = this.queue.shift();
      this.sourceBuffer.appendBuffer(chunk);

      // Mantieni la latenza sotto i 2 secondi
      if (this.videoElement && this.videoElement.buffered.length > 0) {
        const end = this.videoElement.buffered.end(this.videoElement.buffered.length - 1);
        if (end - this.videoElement.currentTime > 2.2) {
          this.videoElement.currentTime = end - 0.3;
        }
      }
    } catch (err) {
      this.queue = [];
    }
  }

  disconnect() {
    this._aborted = true;
    this.connected = false;
    this.queue = [];
    if (this._connectTimer) {
      clearTimeout(this._connectTimer);
      this._connectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {}
      this.ws = null;
    }
    if (this.mediaSource && this.mediaSource.readyState === 'open') {
      try {
        this.mediaSource.endOfStream();
      } catch {}
    }
    this.mediaSource = null;
    this.sourceBuffer = null;
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
      this.objectUrl = null;
    }
    if (this.videoElement) {
      this.videoElement.removeAttribute('src');
      if (this.videoElement.srcObject) {
        this.videoElement.srcObject = null;
      }
    }
    this.notifyStatus();
  }
}

