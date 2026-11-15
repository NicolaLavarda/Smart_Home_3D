import { IVideoStreamProvider } from './IVideoStreamProvider.js';

/**
 * Go2RtcMSEStream
 *
 * Provider di streaming via Media Source Extensions (fMP4 su WebSocket go2rtc).
 * Utilizzato come fallback automatico ad alta compatibilità se WebRTC è bloccato.
 */
export class Go2RtcMSEStream extends IVideoStreamProvider {
  constructor(streamName, options = {}) {
    super(streamName, options);
    this.mode = 'mse';
    this.baseUrl = (options.go2rtcUrl || import.meta.env.VITE_GO2RTC_URL || 'http://localhost:1984').replace(/\/+$/, '');
    this.timeoutMs = options.timeoutMs || 4500;
    this.ws = null;
    this.mediaSource = null;
    this.sourceBuffer = null;
    this.queue = [];
    this.objectUrl = null;
    this._aborted = false;
  }

  getSupportedCodecs() {
    if (typeof MediaSource === 'undefined') return '';
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
        return MediaSource.isTypeSupported(mime);
      })
      .join(',');
  }

  async connect(videoElement) {
    if (!videoElement) throw new Error('HTMLVideoElement richiesto');
    if (typeof MediaSource === 'undefined') {
      this.lastError = 'MediaSource Extensions non supportate';
      return false;
    }

    this.disconnect();
    this._aborted = false;
    this.videoElement = videoElement;
    const t0 = performance.now();

    const wsUrl = this.baseUrl.replace(/^http/i, 'ws') + `/api/ws?src=${encodeURIComponent(this.streamName)}`;

    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          reject(new Error(`Timeout MSE (${this.timeoutMs}ms) per '${this.streamName}'`));
        }, this.timeoutMs);

        const ms = new MediaSource();
        this.mediaSource = ms;
        this.objectUrl = URL.createObjectURL(ms);
        this.videoElement.src = this.objectUrl;
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
            clearTimeout(timer);
            reject(new Error('Errore connessione WebSocket MSE go2rtc'));
          };

          ws.onclose = () => {
            if (!this.connected) {
              clearTimeout(timer);
              reject(new Error('WebSocket MSE chiuso prima dello stream'));
            }
          };

          ws.onmessage = (ev) => {
            if (this._aborted) return;
            if (typeof ev.data === 'string') {
              try {
                const msg = JSON.parse(ev.data);
                if (msg.type === 'mse' && msg.value) {
                  this.sourceBuffer = ms.addSourceBuffer(msg.value);
                  this.sourceBuffer.mode = 'segments';
                  this.sourceBuffer.addEventListener('updateend', () => this.flushQueue());
                } else if (msg.type === 'error') {
                  clearTimeout(timer);
                  reject(new Error(msg.value || 'Errore MSE go2rtc'));
                }
              } catch (e) {
                console.warn('[Go2RtcMSEStream] Messaggio testuale non JSON:', ev.data);
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
              clearTimeout(timer);
              this.videoElement.play().catch(() => {});
              this.notifyStatus();
              resolve();
            }
          };
        });
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
    }
    this.notifyStatus();
  }
}

