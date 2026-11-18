/**
 * SpatialStreamClient
 *
 * Client centralizzato per la comunicazione in tempo reale (WebSocket /ws/spatial)
 * e storica/configurazione (REST /api/v1/*) con il microservizio Python `spatial_server`.
 */
export class SpatialStreamClient {
  constructor(baseUrl = null) {
    const envUrl = typeof import.meta !== 'undefined' && import.meta.env?.VITE_SPATIAL_SERVER_URL;
    const defaultHost = typeof window !== 'undefined' && window.location?.hostname ? window.location.hostname : '127.0.0.1';
    this.baseUrl = (baseUrl || envUrl || `http://${defaultHost}:8765`).replace(/\/+$/, '');
    this.wsUrl = this.baseUrl.replace(/^http/i, 'ws') + '/ws/spatial';

    this.ws = null;
    this.connected = false;
    this.shouldReconnect = false;
    this.reconnectDelayMs = 1500;
    this.maxReconnectDelayMs = 15000;
    this.reconnectTimer = null;

    this.frameListeners = new Set();
    this.statusListeners = new Set();
    this.lastStatusPayload = null;
  }

  onFrame(callback) {
    this.frameListeners.add(callback);
    return () => this.frameListeners.delete(callback);
  }

  onStatusChange(callback) {
    this.statusListeners.add(callback);
    return () => this.statusListeners.delete(callback);
  }

  emitStatus(connected, meta = null) {
    this.connected = connected;
    if (meta) this.lastStatusPayload = meta;
    this.statusListeners.forEach((cb) => {
      try {
        cb(connected, meta);
      } catch (e) {
        console.warn('[SpatialStreamClient] Errore listener stato:', e);
      }
    });
  }

  connectWebSocket() {
    this.shouldReconnect = true;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      this.ws = new WebSocket(this.wsUrl);
    } catch (err) {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectDelayMs = 1500;
      this.emitStatus(true, this.lastStatusPayload);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'spatial_frame') {
          this.frameListeners.forEach((cb) => cb(msg));
        } else if (msg.type === 'server_status') {
          this.emitStatus(true, msg);
        }
      } catch (err) {
        console.warn('[SpatialStreamClient] Payload WS non valido:', err);
      }
    };

    this.ws.onclose = () => {
      this.ws = null;
      this.emitStatus(false, this.lastStatusPayload);
      if (this.shouldReconnect) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      // onclose gestirà lo stato e il backoff
    };
  }

  scheduleReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.shouldReconnect) {
        this.connectWebSocket();
      }
    }, this.reconnectDelayMs);
    this.reconnectDelayMs = Math.min(this.reconnectDelayMs * 1.8, this.maxReconnectDelayMs);
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {}
      this.ws = null;
    }
    this.emitStatus(false, null);
  }

  async requestJson(path, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), options.timeoutMs || 5000);
    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
        signal: controller.signal,
        ...options,
      });
      if (!resp.ok) {
        return null;
      }
      return await resp.json();
    } catch {
      return null;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async fetchStatus() {
    const data = await this.requestJson('/api/v1/status', { method: 'GET', timeoutMs: 2500 });
    if (data) {
      this.lastStatusPayload = data;
    }
    return data;
  }

  async fetchTracks(tStart, tEnd, classes = null) {
    const params = new URLSearchParams({
      t_start: String(tStart),
      t_end: String(tEnd),
    });
    if (Array.isArray(classes) && classes.length > 0) {
      params.set('classes', classes.join(','));
    }
    return await this.requestJson(`/api/v1/tracks?${params.toString()}`, { method: 'GET', timeoutMs: 6000 });
  }

  async fetchTimelineDensity(tStart, tEnd, buckets = 60) {
    const params = new URLSearchParams({
      t_start: String(tStart),
      t_end: String(tEnd),
      buckets: String(buckets),
    });
    return await this.requestJson(`/api/v1/timeline-density?${params.toString()}`, { method: 'GET', timeoutMs: 4000 });
  }

  async fetchCameraCalibration(cameraId) {
    return await this.requestJson(`/api/v1/calibration/${encodeURIComponent(cameraId)}`, { method: 'GET' });
  }

  async updateCameraCalibration(cameraId, payload) {
    return await this.requestJson(`/api/v1/calibration/${encodeURIComponent(cameraId)}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async solvePnP(payload) {
    return await this.requestJson('/api/v1/calibration/solve-pnp', {
      method: 'POST',
      body: JSON.stringify(payload),
      timeoutMs: 8000,
    });
  }

  async setIngestionMode(mode) {
    const res = await this.requestJson('/api/v1/ingestion/mode', {
      method: 'POST',
      body: JSON.stringify({ mode }),
    });
    if (res && res.status === 'ok') {
      this.emitStatus(this.connected, {
        ...(this.lastStatusPayload || {}),
        ingestion_mode: res.ingestion_mode,
      });
    }
    return res;
  }
}

