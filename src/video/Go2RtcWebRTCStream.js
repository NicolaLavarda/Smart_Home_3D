import { IVideoStreamProvider } from './IVideoStreamProvider.js';

function isProdSameOriginMode() {
  let isProdBuild = false;
  try { isProdBuild = Boolean(import.meta.env.PROD); } catch {}
  const isHttps = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  return isProdBuild || isHttps;
}

/**
 * Go2RtcWebRTCStream
 *
 * Provider a bassissima latenza (sub-secondo) tramite protocollo WebRTC (WHEP/SDP)
 * esposto nativamente da go2rtc sulla porta 1984 (o via reverse proxy /go2rtc in produzione).
 */
export class Go2RtcWebRTCStream extends IVideoStreamProvider {
  constructor(streamName, options = {}) {
    super(streamName, options);
    this.mode = 'webrtc';
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
    this.timeoutMs = options.timeoutMs ?? 2200;
    this.pc = null;
    this.mediaStream = null;
    this._aborted = false;
    this._trackTimer = null;
    this._fetchController = null;
  }

  async connect(videoElement) {
    if (!videoElement) throw new Error('HTMLVideoElement richiesto');
    if (typeof RTCPeerConnection === 'undefined') {
      this.lastError = 'RTCPeerConnection non supportato dal browser';
      return false;
    }

    this.disconnect();
    this._aborted = false;
    this.videoElement = videoElement;
    const t0 = performance.now();

    try {
      const pc = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
      });
      this.pc = pc;

      pc.addTransceiver('video', { direction: 'recvonly' });
      pc.addTransceiver('audio', { direction: 'recvonly' });

      const trackPromise = new Promise((resolve, reject) => {
        this._trackTimer = setTimeout(() => {
          reject(new Error(`Timeout WebRTC (${this.timeoutMs}ms) per '${this.streamName}'`));
        }, this.timeoutMs);

        pc.ontrack = (event) => {
          if (this._aborted) return;
          if (!this.mediaStream) {
            this.mediaStream = new MediaStream();
            this.videoElement.srcObject = this.mediaStream;
          }
          this.mediaStream.addTrack(event.track);
          if (event.track.kind === 'video') {
            clearTimeout(this._trackTimer);
            this._trackTimer = null;
            resolve();
          }
        };

        pc.onconnectionstatechange = () => {
          if (pc.connectionState === 'failed' || pc.connectionState === 'closed') {
            clearTimeout(this._trackTimer);
            this._trackTimer = null;
            reject(new Error(`WebRTC state: ${pc.connectionState}`));
          }
        };
      });
      trackPromise.catch(() => {});

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await this.waitForIceGathering(pc, Math.min(450, Math.floor(this.timeoutMs * 0.3)));

      const endpoint = `${this.baseUrl}/api/webrtc?src=${encodeURIComponent(this.streamName)}`;
      this._fetchController = new AbortController();
      const controller = this._fetchController;
      const fetchTimer = setTimeout(() => controller.abort(), this.timeoutMs);

      const response = await fetch(endpoint, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/sdp' },
        body: pc.localDescription?.sdp ?? offer?.sdp ?? '',
        signal: controller.signal,
      });
      clearTimeout(fetchTimer);

      if (!response.ok) {
        const msg = await response.text().catch(() => '');
        throw new Error(`go2rtc WebRTC HTTP ${response.status}: ${msg.slice(0, 120)}`);
      }

      const answerSdp = await response.text();
      if (this._aborted) return false;

      await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });
      await trackPromise;

      this.videoElement.muted = true;
      this.videoElement.playsInline = true;
      await this.videoElement.play().catch(() => {});

      this.connected = true;
      this.latencyMs = Math.round(performance.now() - t0);
      this.lastError = null;
      this.notifyStatus();
      return true;
    } catch (err) {
      this.lastError = err?.message || 'Errore WebRTC go2rtc';
      this.disconnect();
      return false;
    }
  }

  waitForIceGathering(pc, maxWaitMs = 450) {
    if (pc.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise((resolve) => {
      const timer = setTimeout(resolve, maxWaitMs);
      const check = () => {
        if (pc.iceGatheringState === 'complete') {
          clearTimeout(timer);
          pc.removeEventListener('icegatheringstatechange', check);
          resolve();
        }
      };
      pc.addEventListener('icegatheringstatechange', check);
    });
  }

  disconnect() {
    this._aborted = true;
    this.connected = false;
    if (this._trackTimer) {
      clearTimeout(this._trackTimer);
      this._trackTimer = null;
    }
    if (this._fetchController) {
      try {
        this._fetchController.abort();
      } catch {}
      this._fetchController = null;
    }
    if (this.pc) {
      try {
        this.pc.ontrack = null;
        this.pc.onconnectionstatechange = null;
        this.pc.close();
      } catch {}
      this.pc = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }
    if (this.videoElement && this.videoElement.srcObject) {
      this.videoElement.srcObject = null;
    }
    this.notifyStatus();
  }
}

