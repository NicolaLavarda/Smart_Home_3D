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
    this.biometricEventListeners = new Set();
    this.automationEventListeners = new Set();
    this.sceneEventListeners = new Set();
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

  onBiometricEvent(callback) {
    this.biometricEventListeners.add(callback);
    return () => this.biometricEventListeners.delete(callback);
  }

  onAutomationEvent(callback) {
    this.automationEventListeners.add(callback);
    return () => this.automationEventListeners.delete(callback);
  }

  onSceneEvent(callback) {
    this.sceneEventListeners.add(callback);
    return () => this.sceneEventListeners.delete(callback);
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
        } else if (msg.type === 'biometric_event') {
          this.biometricEventListeners.forEach((cb) => {
            try {
              cb(msg);
            } catch (e) {
              console.warn('[SpatialStreamClient] Errore listener biometric_event:', e);
            }
          });
        } else if (msg.type === 'scene_event_updated') {
          this.sceneEventListeners.forEach((cb) => {
            try {
              cb(msg);
            } catch (e) {
              console.warn('[SpatialStreamClient] Errore listener scene_event_updated:', e);
            }
          });
        } else if (
          msg.type === 'automation_triggered' ||
          msg.type === 'automation_ui_alert' ||
          msg.type === 'automation_ha_service_call' ||
          msg.type === 'automation_zones_updated' ||
          msg.type === 'automation_rules_updated' ||
          msg.type === 'automation_pretrigger_updated' ||
          msg.type === 'virtual_entity_updated' ||
          msg.type === 'virtual_entities_list'
        ) {
          this.automationEventListeners.forEach((cb) => {
            try {
              cb(msg);
            } catch (e) {
              console.warn('[SpatialStreamClient] Errore listener automationEvent:', e);
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
      returnErrorPayload = false,
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
      if (returnErrorPayload) {
        let detail = `HTTP ${resp.status}`;
        try {
          const errBody = await resp.json();
          if (errBody && typeof errBody.detail === 'string') {
            detail = errBody.detail;
          }
        } catch {}
        return { status: 'error', http_status: resp.status, detail };
      }
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

  async fetchMetricsEntities() {
    return await this.requestJson('/api/v1/metrics/entities', {
      method: 'GET',
      cache: 'no-store',
      timeoutMs: 3500,
    });
  }

  async fetchMetricsHistory({ windowS = 300, maxPoints = 180 } = {}) {
    const params = new URLSearchParams({
      window_s: String(Math.max(30, Number(windowS) || 300)),
      max_points: String(Math.max(20, Math.min(500, Number(maxPoints) || 180))),
    });
    return await this.requestJson(`/api/v1/metrics/history?${params.toString()}`, {
      method: 'GET',
      cache: 'no-store',
      timeoutMs: 6000,
    });
  }

  async fetchTracks(tStart, tEnd, classes = null, limit = 15000, filters = null) {
    const params = new URLSearchParams({
      t_start: String(tStart),
      t_end: String(tEnd),
      limit: String(Math.max(1, Math.min(20000, Number(limit) || 15000))),
    });
    if (Array.isArray(classes) && classes.length > 0) {
      params.set('classes', classes.join(','));
    }
    if (filters && typeof filters === 'object') {
      if (typeof filters.identity === 'string' && filters.identity.trim()) {
        params.set('identity', filters.identity.trim());
      }
      if (typeof filters.plate === 'string' && filters.plate.trim()) {
        params.set('plate', filters.plate.trim().toUpperCase());
      }
      if (filters.unknownOnly) {
        params.set('unknown_only', 'true');
      }
    }
    return await this.requestJson(`/api/v1/tracks?${params.toString()}`, { method: 'GET', timeoutMs: 12000 });
  }

  async fetchBiometricsStatus() {
    return await this.requestJson('/api/v1/biometrics/status', {
      method: 'GET',
      cache: 'no-store',
      timeoutMs: 3000,
    });
  }

  async fetchBiometricEvents({
    tStart = null,
    tEnd = null,
    modality = null,
    status = null,
    identity = null,
    plate = null,
    trackId = null,
    limit = 100,
  } = {}) {
    const params = new URLSearchParams();
    if (Number.isFinite(tStart)) params.set('t_start', String(tStart));
    if (Number.isFinite(tEnd)) params.set('t_end', String(tEnd));
    if (modality) params.set('modality', String(modality));
    if (status) params.set('status', String(status));
    if (typeof identity === 'string' && identity.trim()) params.set('identity', identity.trim());
    if (typeof plate === 'string' && plate.trim()) params.set('plate', plate.trim().toUpperCase());
    if (Number.isFinite(trackId)) params.set('track_id', String(trackId));
    params.set('limit', String(Math.max(1, Math.min(1000, Number(limit) || 100))));
    const qs = params.toString();
    return await this.requestJson(`/api/v1/biometrics/events${qs ? `?${qs}` : ''}`, {
      method: 'GET',
      cache: 'no-store',
      timeoutMs: 8000,
    });
  }

  async fetchBiometricIdentities() {
    return await this.requestJson('/api/v1/biometrics/identities', {
      method: 'GET',
      cache: 'no-store',
      timeoutMs: 5000,
    });
  }

  async fetchBiometricPlates() {
    return await this.requestJson('/api/v1/biometrics/plates', {
      method: 'GET',
      cache: 'no-store',
      timeoutMs: 5000,
    });
  }

  getBiometricCropUrl(cropId) {
    const clean = String(cropId || '').trim();
    if (!clean) return null;
    return `${this.baseUrl}/api/v1/biometrics/crops/${encodeURIComponent(clean)}`;
  }

  async assignBiometricEvent(eventId, payload = {}) {
    return await this.requestJson(`/api/v1/biometrics/events/${encodeURIComponent(eventId)}/assign`, {
      method: 'POST',
      body: JSON.stringify(payload),
      cache: 'no-store',
      timeoutMs: 12000,
    });
  }

  async reloadBiometricIdentities() {
    return await this.requestJson('/api/v1/biometrics/identities/reload', {
      method: 'POST',
      cache: 'no-store',
      timeoutMs: 8000,
    });
  }

  async deleteBiometricIdentity(personName) {
    return await this.requestJson(`/api/v1/biometrics/identities/${encodeURIComponent(personName)}`, {
      method: 'DELETE',
      cache: 'no-store',
      timeoutMs: 8000,
    });
  }

  async upsertBiometricPlate({ plate, owner_name, vehicle_label = null, notes = null }) {
    return await this.requestJson('/api/v1/biometrics/plates', {
      method: 'PUT',
      body: JSON.stringify({ plate, owner_name, vehicle_label, notes }),
      cache: 'no-store',
      timeoutMs: 8000,
    });
  }

  async deleteBiometricPlate(plate) {
    return await this.requestJson(`/api/v1/biometrics/plates/${encodeURIComponent(plate)}`, {
      method: 'DELETE',
      cache: 'no-store',
      timeoutMs: 8000,
    });
  }

  async pruneBiometricCrops() {
    return await this.requestJson('/api/v1/biometrics/crops/prune', {
      method: 'POST',
      cache: 'no-store',
      timeoutMs: 15000,
    });
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
      returnErrorPayload: true,
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

  // =========================================================================
  // Spatial Automations, 2.5D Zones & Virtual Entities API
  // =========================================================================

  async fetchAutomationsBootstrap() {
    return await this.requestJson('/api/v1/automations/bootstrap', {
      method: 'GET',
      cache: 'no-store',
      timeoutMs: 6000,
    });
  }

  async fetchAutomationZones() {
    return await this.requestJson('/api/v1/automations/zones', {
      method: 'GET',
      cache: 'no-store',
    });
  }

  async upsertAutomationZone(zonePayload) {
    return await this.requestJson('/api/v1/automations/zones', {
      method: 'PUT',
      body: JSON.stringify(zonePayload),
      cache: 'no-store',
    });
  }

  async deleteAutomationZone(zoneId) {
    return await this.requestJson(`/api/v1/automations/zones/${encodeURIComponent(zoneId)}`, {
      method: 'DELETE',
      cache: 'no-store',
    });
  }

  async fetchVirtualEntities() {
    return await this.requestJson('/api/v1/automations/virtual-entities', {
      method: 'GET',
      cache: 'no-store',
    });
  }

  async upsertVirtualEntity(entityPayload) {
    return await this.requestJson('/api/v1/automations/virtual-entities', {
      method: 'PUT',
      body: JSON.stringify(entityPayload),
      cache: 'no-store',
    });
  }

  async setVirtualEntityState(entityId, { state = null, operation = 'set', attributes = null } = {}) {
    return await this.requestJson(`/api/v1/automations/virtual-entities/${encodeURIComponent(entityId)}/state`, {
      method: 'POST',
      body: JSON.stringify({ state, operation, attributes }),
      cache: 'no-store',
    });
  }

  async deleteVirtualEntity(entityId) {
    return await this.requestJson(`/api/v1/automations/virtual-entities/${encodeURIComponent(entityId)}`, {
      method: 'DELETE',
      cache: 'no-store',
    });
  }

  async fetchAutomationRules() {
    return await this.requestJson('/api/v1/automations/rules', {
      method: 'GET',
      cache: 'no-store',
    });
  }

  async upsertAutomationRule(rulePayload) {
    return await this.requestJson('/api/v1/automations/rules', {
      method: 'PUT',
      body: JSON.stringify(rulePayload),
      cache: 'no-store',
    });
  }

  async toggleAutomationRule(ruleId, enabled) {
    return await this.requestJson(`/api/v1/automations/rules/${encodeURIComponent(ruleId)}/toggle`, {
      method: 'POST',
      body: JSON.stringify({ enabled: Boolean(enabled) }),
      cache: 'no-store',
    });
  }

  async triggerAutomationRule(ruleId) {
    return await this.requestJson(`/api/v1/automations/rules/${encodeURIComponent(ruleId)}/trigger`, {
      method: 'POST',
      cache: 'no-store',
    });
  }

  async deleteAutomationRule(ruleId) {
    return await this.requestJson(`/api/v1/automations/rules/${encodeURIComponent(ruleId)}`, {
      method: 'DELETE',
      cache: 'no-store',
    });
  }

  async fetchAutomationLogs({ ruleId = null, limit = 80 } = {}) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (ruleId) params.set('rule_id', String(ruleId));
    return await this.requestJson(`/api/v1/automations/logs?${params.toString()}`, {
      method: 'GET',
      cache: 'no-store',
    });
  }

  async clearAutomationLogs() {
    return await this.requestJson('/api/v1/automations/logs', {
      method: 'DELETE',
      cache: 'no-store',
    });
  }

  async fetchAutomationArmedStates() {
    return await this.requestJson('/api/v1/automations/armed', {
      method: 'GET',
      cache: 'no-store',
    });
  }

  async fetchAutomationRuleDiagnostics(ruleId, limit = 30) {
    return await this.requestJson(`/api/v1/automations/rules/${encodeURIComponent(ruleId)}/diagnostics?limit=${Number(limit) || 30}`, {
      method: 'GET',
      cache: 'no-store',
    });
  }

  async fetchHaDiscovery() {
    return await this.requestJson('/api/v1/automations/ha-discovery', {
      method: 'GET',
      cache: 'no-store',
    });
  }

  async fetchSceneEvents({
    tStart = null,
    tEnd = null,
    importance = null,
    subjectClass = null,
    cameraId = null,
    zoneId = null,
    identity = null,
    plate = null,
    unknownOnly = false,
    limit = 60,
  } = {}) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (Number.isFinite(tStart)) params.set('t_start', String(tStart));
    if (Number.isFinite(tEnd)) params.set('t_end', String(tEnd));
    if (importance) params.set('importance', String(importance));
    if (subjectClass) params.set('subject_class', String(subjectClass));
    if (cameraId) params.set('camera_id', String(cameraId));
    if (zoneId) params.set('zone_id', String(zoneId));
    if (identity) params.set('identity', String(identity));
    if (plate) params.set('plate', String(plate));
    if (unknownOnly) params.set('unknown_only', 'true');
    return await this.requestJson(`/api/v1/events?${params.toString()}`, {
      method: 'GET',
      cache: 'no-store',
    });
  }

  async fetchSceneEvent(eventId) {
    if (!eventId) return null;
    return await this.requestJson(`/api/v1/events/${encodeURIComponent(eventId)}`, {
      method: 'GET',
      cache: 'no-store',
    });
  }

  async deleteSceneEvent(eventId) {
    return await this.requestJson(`/api/v1/events/${encodeURIComponent(eventId)}`, {
      method: 'DELETE',
      cache: 'no-store',
    });
  }

  resolveUrl(pathOrUrl) {
    const raw = String(pathOrUrl || '').trim();
    if (!raw) return '';
    if (/^https?:\/\//i.test(raw)) return raw;
    return `${this.baseUrl}${raw.startsWith('/') ? raw : `/${raw}`}`;
  }

  getSceneEventCoverUrl(eventId, variant = 'annotated', versionTs = null) {
    if (!eventId) return null;
    const filePart = variant === 'raw' ? 'cover.jpg' : 'annotated.jpg';
    const qs = Number.isFinite(Number(versionTs)) ? `?v=${Math.floor(Number(versionTs) * 10)}` : '';
    return this.resolveUrl(`/api/v1/events/${encodeURIComponent(eventId)}/${filePart}${qs}`);
  }

  syncHaStates(entitiesMap, { triggerOnDiff = true } = {}) {
    if (!entitiesMap || typeof entitiesMap !== 'object') return;
    const compact = {};
    for (const [eid, st] of Object.entries(entitiesMap)) {
      if (!st || typeof st !== 'object') continue;
      compact[eid] = {
        state: String(st.state ?? 'unknown'),
        attributes: st.attributes || {},
      };
    }
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(
          JSON.stringify({
            type: 'ha_states_sync',
            entities: compact,
            trigger_on_diff: triggerOnDiff,
          })
        );
        return;
      } catch {}
    }
    this.requestJson('/api/v1/automations/ha-states', {
      method: 'POST',
      body: JSON.stringify({ entities: compact, trigger_on_diff: triggerOnDiff }),
      cache: 'no-store',
    }).catch(() => null);
  }
}

