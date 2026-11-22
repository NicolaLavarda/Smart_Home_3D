function isProdSameOrigin() {
  let isProdBuild = false;
  try { isProdBuild = Boolean(import.meta.env.PROD); } catch {}
  const isHttps = typeof window !== 'undefined' && window.location?.protocol === 'https:';
  return isProdBuild || isHttps;
}

/**
 * SpatialStreamClient
 *
 * Client centralizzato per la comunicazione in tempo reale (WebSocket /ws/spatial)
 * e storica/configurazione (REST /api/v1/*) con il microservizio Python `spatial_server`.
 */
export class SpatialStreamClient {
  constructor(baseUrl = null) {
    const prodMode = isProdSameOrigin();
    let envUrl = '';
    try {
      if (!import.meta.env.PROD) {
        envUrl = import.meta.env.VITE_SPATIAL_SERVER_URL || '';
      }
    } catch {}
    const defaultHost = typeof window !== 'undefined' && window.location?.hostname ? window.location.hostname : '127.0.0.1';

    if (baseUrl !== null) {
      this.baseUrl = String(baseUrl).replace(/\/+$/, '');
    } else if (prodMode) {
      this.baseUrl = '';
    } else {
      this.baseUrl = (envUrl || `http://${defaultHost}:8765`).replace(/\/+$/, '');
    }

    if (this.baseUrl === '' && typeof window !== 'undefined' && window.location?.host) {
      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      this.wsUrl = `${wsProto}//${window.location.host}/ws/spatial`;
    } else if (this.baseUrl === '') {
      this.wsUrl = '/ws/spatial';
    } else {
      this.wsUrl = this.baseUrl.replace(/^http/i, 'ws') + '/ws/spatial';
    }

    this.ws = null;
    this.connected = false;
    this.shouldReconnect = false;
    this.reconnectDelayMs = 1500;
    this.maxReconnectDelayMs = 15000;
    this.reconnectTimer = null;

    this.authToken = null;
    this.isAuthenticated = false;
    this._tokenProvider = null;
    this._authRetryCount = 0;

    this.frameListeners = new Set();
    this.statusListeners = new Set();
    this.authErrorListeners = new Set();
    this.calibrationListeners = new Set();
    this.lastStatusPayload = null;
  }

  setTokenProvider(fn) {
    this._tokenProvider = typeof fn === 'function' ? fn : null;
  }

  onAuthError(callback) {
    this.authErrorListeners.add(callback);
    return () => this.authErrorListeners.delete(callback);
  }

  _emitAuthError(info) {
    this.authErrorListeners.forEach((cb) => {
      try {
        cb(info);
      } catch (e) {
        console.warn('[SpatialStreamClient] Errore listener authError:', e);
      }
    });
  }

  onFrame(callback) {
    this.frameListeners.add(callback);
    return () => this.frameListeners.delete(callback);
  }

  onStatusChange(callback) {
    this.statusListeners.add(callback);
    return () => this.statusListeners.delete(callback);
  }

  onCalibrationUpdate(callback) {
    this.calibrationListeners.add(callback);
    return () => this.calibrationListeners.delete(callback);
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
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
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
      this._authRetryCount = 0;
      this.emitStatus(true, this.lastStatusPayload);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'spatial_frame') {
          this.frameListeners.forEach((cb) => cb(msg));
        } else if (msg.type === 'server_status') {
          this.emitStatus(true, msg);
        } else if (msg.type === 'calibration_updated') {
          this.calibrationListeners.forEach((cb) => {
            try {
              cb(msg);
            } catch (e) {
              console.warn('[SpatialStreamClient] Errore listener calibration_updated:', e);
            }
          });
        }
      } catch (err) {
        console.warn('[SpatialStreamClient] Payload WS non valido:', err);
      }
    };

    this.ws.onclose = async (event) => {
      this.ws = null;
      this.emitStatus(false, this.lastStatusPayload);

      if (event?.code === 4401) {
        this.isAuthenticated = false;
        if (this.shouldReconnect && this._authRetryCount < 1 && typeof this._tokenProvider === 'function') {
          this._authRetryCount += 1;
          try {
            const token = await this._tokenProvider();
            const session = token ? await this.authenticateWithHaToken(token, { resetRetry: false }) : false;
            if ((session === true || session?.authenticated) && this.shouldReconnect) {
              if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
              this.reconnectTimer = setTimeout(() => {
                this.reconnectTimer = null;
                if (this.shouldReconnect) {
                  this.connectWebSocket();
                }
              }, 500);
              return;
            }
          } catch {}
        }
        this.shouldReconnect = false;
        this._emitAuthError({ source: 'ws', code: 4401 });
        return;
      }

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
    const {
      headers: customHeaders,
      timeoutMs = 5000,
      skipAuthRetry = false,
      ...fetchOptions
    } = options;

    const hasCustomAuth = Boolean(
      customHeaders &&
      (Object.prototype.hasOwnProperty.call(customHeaders, 'Authorization') ||
        Object.prototype.hasOwnProperty.call(customHeaders, 'authorization'))
    );

    const headers = {
      'Content-Type': 'application/json',
      ...(this.authToken && !hasCustomAuth ? { Authorization: `Bearer ${this.authToken}` } : {}),
      ...(customHeaders || {}),
    };

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    let resp;
    try {
      resp = await fetch(`${this.baseUrl}${path}`, {
        credentials: 'include',
        ...fetchOptions,
        headers,
        signal: controller.signal,
      });
    } catch {
      return null;
    } finally {
      clearTimeout(timeoutId);
    }

    if (resp.status === 401) {
      if (!skipAuthRetry && typeof this._tokenProvider === 'function') {
        try {
          const freshToken = await this._tokenProvider();
          if (freshToken) {
            const session = await this.authenticateWithHaToken(freshToken);
            if (session === true || session?.authenticated) {
              return await this.requestJson(path, { ...options, skipAuthRetry: true });
            }
          }
        } catch {}
      }
      this.isAuthenticated = false;
      this._emitAuthError({ source: 'http', status: 401, path });
      return null;
    }

    if (!resp.ok) {
      console.warn(`[SpatialStreamClient] Richiesta fallita (${resp.status}) su ${path}`);
      return null;
    }

    try {
      return await resp.json();
    } catch {
      return null;
    }
  }

  async authenticateWithHaToken(accessToken, { resetRetry = true } = {}) {
    if (!accessToken) return false;
    this.authToken = accessToken;
    const res = await this.requestJson('/api/v1/auth/session', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ token: accessToken }),
      skipAuthRetry: true,
    });
    this.isAuthenticated = Boolean(res?.authenticated);
    if (this.isAuthenticated && resetRetry) {
      this._authRetryCount = 0;
    }
    return this.isAuthenticated;
  }

  async logout() {
    this.disconnect();
    await this.requestJson('/api/v1/auth/logout', {
      method: 'POST',
      skipAuthRetry: true,
    }).catch(() => null);
    this.authToken = null;
    this.isAuthenticated = false;
    this.lastStatusPayload = null;
    this._authRetryCount = 0;
  }

  async fetchStatus() {
    const data = await this.requestJson('/api/v1/status', { method: 'GET', timeoutMs: 2500 });
    if (data) {
      this.lastStatusPayload = data;
    }
    return data;
  }

  async fetchTracks(tStart, tEnd, classes = null, limit = 15000) {
    const params = new URLSearchParams({
      t_start: String(tStart),
      t_end: String(tEnd),
      limit: String(Math.max(1, Math.min(20000, Number(limit) || 15000))),
    });
    if (Array.isArray(classes) && classes.length > 0) {
      params.set('classes', classes.join(','));
    }
    return await this.requestJson(`/api/v1/tracks?${params.toString()}`, { method: 'GET', timeoutMs: 12000 });
  }

  async fetchTimelineDensity(tStart, tEnd, buckets = 80) {
    const params = new URLSearchParams({
      t_start: String(tStart),
      t_end: String(tEnd),
      buckets: String(buckets),
    });
    return await this.requestJson(`/api/v1/timeline-density?${params.toString()}`, { method: 'GET', timeoutMs: 10000 });
  }

  async fetchAllCameraCalibrations() {
    return await this.requestJson('/api/v1/calibrations', {
      method: 'GET',
      cache: 'no-store',
      timeoutMs: 6000,
    });
  }

  async fetchCameraCalibration(cameraId) {
    return await this.requestJson(`/api/v1/calibration/${encodeURIComponent(cameraId)}`, {
      method: 'GET',
      cache: 'no-store',
    });
  }

  async updateCameraCalibration(cameraId, payload) {
    return await this.requestJson(`/api/v1/calibration/${encodeURIComponent(cameraId)}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async resetCameraCalibration(cameraId) {
    return await this.requestJson(`/api/v1/calibration/${encodeURIComponent(cameraId)}`, {
      method: 'DELETE',
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

