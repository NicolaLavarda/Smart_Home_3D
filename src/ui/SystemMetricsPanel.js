import { icon } from './icons.js';

const TIME_WINDOWS = [
  { id: '1m', label: '1m', windowS: 60 },
  { id: '5m', label: '5m', windowS: 300 },
  { id: '15m', label: '15m', windowS: 900 },
  { id: '1h', label: '1h', windowS: 3600 },
  { id: '6h', label: '6h', windowS: 21600 },
  { id: '24h', label: '24h', windowS: 86400 },
  { id: '7d', label: '7g', windowS: 604800 },
];

const TIER_LABELS_IT = {
  person: 'Persona',
  vehicle: 'Veicolo',
  idle: 'Riposo',
  even: 'Fisso',
};

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fmtNum(val, decimals = 1, fallback = 'N/D') {
  const num = Number(val);
  return val !== null && val !== undefined && Number.isFinite(num)
    ? num.toFixed(decimals)
    : fallback;
}

function formatAxisTime(unixSec, windowS) {
  if (!Number.isFinite(unixSec)) return '--:--';
  const dt = new Date(unixSec * 1000);
  if (windowS >= 86400) {
    const dd = String(dt.getDate()).padStart(2, '0');
    const mm = String(dt.getMonth() + 1).padStart(2, '0');
    const hh = String(dt.getHours()).padStart(2, '0');
    const min = String(dt.getMinutes()).padStart(2, '0');
    return `${dd}/${mm} ${hh}:${min}`;
  }
  if (windowS <= 900) {
    return dt.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }
  return dt.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function resolveRefreshMs(windowS) {
  if (windowS <= 900) return 2500;
  if (windowS <= 3600) return 10000;
  return 30000;
}

function buildSvgChart({
  chartId,
  series,
  lines,
  windowS,
  unit = '',
  fixedMin = 0,
  fixedMax = null,
  decimals = 1,
}) {
  const W = 480;
  const H = 128;
  const padL = 36;
  const padR = 10;
  const padT = 10;
  const padB = 22;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const validPoints = Array.isArray(series) ? series : [];
  if (validPoints.length === 0) {
    return `
      <div class="sys-chart-empty">In attesa dei primi campioni...</div>
    `;
  }

  let yMin = fixedMin !== null ? Number(fixedMin) : Infinity;
  let yMax = fixedMax !== null ? Number(fixedMax) : -Infinity;

  for (const pt of validPoints) {
    for (const ln of lines) {
      const raw = pt[ln.key];
      if (raw === null || raw === undefined) continue;
      const v = Number(raw);
      if (!Number.isFinite(v)) continue;
      if (fixedMin === null && v < yMin) yMin = v;
      if (fixedMax === null && v > yMax) yMax = v;
    }
  }

  if (!Number.isFinite(yMin)) yMin = 0;
  if (!Number.isFinite(yMax) || yMax <= yMin) {
    yMax = yMin + (unit === '%' ? 100 : 4);
  }
  if (fixedMax === null) {
    yMax = yMax * 1.15;
    if (yMax < 1) yMax = 1;
  }

  const tMin = Number(validPoints[0].t ?? validPoints[0].timestamp ?? 0);
  const tMax = Number(validPoints[validPoints.length - 1].t ?? validPoints[validPoints.length - 1].timestamp ?? tMin + 1);
  const tSpan = Math.max(1, tMax - tMin);
  const ySpan = Math.max(1e-6, yMax - yMin);

  const mapX = (t, idx) => {
    if (validPoints.length === 1) return padL + plotW * 0.5;
    if (tSpan <= 1) return padL + (idx / (validPoints.length - 1)) * plotW;
    return padL + ((t - tMin) / tSpan) * plotW;
  };
  const mapY = (v) => padT + plotH - ((Math.max(yMin, Math.min(yMax, v)) - yMin) / ySpan) * plotH;

  // Gridlines (3 horizontal steps)
  const gridSteps = [0, 0.5, 1];
  const gridHtml = gridSteps
    .map((frac) => {
      const y = (padT + plotH * (1 - frac)).toFixed(1);
      const valLabel = (yMin + ySpan * frac).toFixed(unit === '%' || ySpan >= 10 ? 0 : 1);
      return `
        <line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" class="sys-chart-grid" />
        <text x="${padL - 5}" y="${Number(y) + 3}" text-anchor="end" class="sys-chart-axis-txt">${escapeHtml(valLabel)}</text>
      `;
    })
    .join('');

  // Series paths
  const pathsHtml = lines
    .map((ln, lineIdx) => {
      const coords = [];
      for (let i = 0; i < validPoints.length; i += 1) {
        const pt = validPoints[i];
        const raw = pt[ln.key];
        if (raw === null || raw === undefined) continue;
        const val = Number(raw);
        if (!Number.isFinite(val)) continue;
        const t = Number(pt.t ?? pt.timestamp ?? 0);
        coords.push([mapX(t, i), mapY(val)]);
      }
      if (coords.length === 0) return '';
      if (coords.length === 1) {
        return `<circle cx="${coords[0][0].toFixed(1)}" cy="${coords[0][1].toFixed(1)}" r="3" fill="${ln.color}" />`;
      }
      const d = coords
        .map(([x, y], idx) => `${idx === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
        .join(' ');
      let areaHtml = '';
      if (lineIdx === 0 && ln.area !== false) {
        const baseY = (padT + plotH).toFixed(1);
        const areaD = `${d} L${coords[coords.length - 1][0].toFixed(1)},${baseY} L${coords[0][0].toFixed(1)},${baseY} Z`;
        areaHtml = `<path d="${areaD}" fill="${ln.color}" fill-opacity="0.11" stroke="none" />`;
      }
      const dashAttr = ln.dashed ? 'stroke-dasharray="4 3"' : '';
      return `
        ${areaHtml}
        <path d="${d}" fill="none" stroke="${ln.color}" stroke-width="${ln.width || 1.8}" stroke-linecap="round" stroke-linejoin="round" ${dashAttr} />
      `;
    })
    .join('');

  const tMid = tMin + tSpan * 0.5;
  const xLabelsHtml = `
    <text x="${padL}" y="${H - 4}" text-anchor="start" class="sys-chart-axis-txt">${escapeHtml(formatAxisTime(tMin, windowS))}</text>
    <text x="${(padL + plotW * 0.5).toFixed(1)}" y="${H - 4}" text-anchor="middle" class="sys-chart-axis-txt">${escapeHtml(formatAxisTime(tMid, windowS))}</text>
    <text x="${W - padR}" y="${H - 4}" text-anchor="end" class="sys-chart-axis-txt">${escapeHtml(formatAxisTime(tMax, windowS))}</text>
  `;

  return `
    <div class="sys-chart-svg-wrap" data-chart-wrap="${escapeHtml(chartId)}">
      <svg class="sys-chart-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(chartId)}">
        ${gridHtml}
        ${pathsHtml}
        ${xLabelsHtml}
        <line class="sys-chart-hover-line" x1="0" y1="${padT}" x2="0" y2="${padT + plotH}" hidden />
      </svg>
      <div class="sys-chart-tooltip" hidden></div>
    </div>
  `;
}

/**
 * SystemMetricsPanel
 *
 * Pannello diagnostico Admin-only per monitorare carico CPU/GPU/RAM del PC fisso,
 * FPS reali e target di riconoscimento (persone, veicoli, animali, biometria) e
 * le entità esposte verso Home Assistant e Automation Engine.
 */
export class SystemMetricsPanel {
  constructor({ spatialStreamClient, haClient, uiLayer = null } = {}) {
    this.spatialStreamClient = spatialStreamClient || null;
    this.haClient = haClient || null;
    this.uiLayer = uiLayer || (typeof document !== 'undefined' ? document.body : null);

    this.isOpen = false;
    this.isCollapsed = false;
    this.windowS = 300; // Default 5 min
    this.data = null;
    this.isLoading = false;
    this.errorText = '';
    this._entitiesOpen = false;
    this._pollTimer = null;
    this._copiedEntityId = null;
    this._copyTimer = null;

    this.onOpenCallback = null;
    this.onCloseCallback = null;

    this._onVisibilityChange = () => {
      if (!this.isOpen) return;
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') {
        this._stopPolling();
      } else {
        void this.refresh();
        this._restartPolling();
      }
    };

    this._onKeyDown = (e) => {
      if (this.isOpen && e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        this.close();
      }
    };

    this._initDOM();
    this._bindShellEvents();
  }

  setLifecycleHooks({ onOpen, onClose } = {}) {
    this.onOpenCallback = typeof onOpen === 'function' ? onOpen : null;
    this.onCloseCallback = typeof onClose === 'function' ? onClose : null;
  }

  _initDOM() {
    if (typeof document === 'undefined' || !this.uiLayer) return;

    this.panelEl = document.createElement('section');
    this.panelEl.id = 'sh3d-system-metrics-panel';
    this.panelEl.className = 'sys-metrics-drawer';
    this.panelEl.setAttribute('role', 'dialog');
    this.panelEl.setAttribute('aria-label', 'Prestazioni Server e FPS');
    this.panelEl.setAttribute('aria-hidden', 'true');
    this.panelEl.hidden = true;

    const windowsHtml = TIME_WINDOWS.map((w) => `
      <button
        type="button"
        class="sys-win-btn ${w.windowS === this.windowS ? 'active' : ''}"
        data-metrics-window="${w.windowS}"
        aria-pressed="${w.windowS === this.windowS ? 'true' : 'false'}"
      >${w.label}</button>
    `).join('');

    this.panelEl.innerHTML = `
      <header class="sys-metrics-header" id="sys-metrics-header-toggle" title="Tocca per ridurre o espandere">
        <div class="sys-metrics-header-copy">
          <div class="sys-metrics-title-row">
            <span class="sys-metrics-title-icon">${icon('activity', { size: 16 })}</span>
            <h2 class="sys-metrics-title">Prestazioni &amp; FPS Server</h2>
            <span class="sys-live-pill" id="sys-metrics-live-pill">LIVE</span>
          </div>
          <span class="sys-metrics-sub" id="sys-metrics-subtitle">Caricamento telemetria...</span>
        </div>
        <div class="sys-metrics-header-actions">
          <button
            type="button"
            class="sys-icon-btn"
            id="btn-sys-metrics-refresh"
            title="Aggiorna grafici ora"
            aria-label="Aggiorna grafici"
          >
            ${icon('refresh-cw', { size: 15 })}
          </button>
          <button
            type="button"
            class="sys-icon-btn"
            id="btn-sys-metrics-collapse"
            aria-expanded="true"
            title="Riduci pannello"
            aria-label="Riduci o espandi pannello Prestazioni"
          >
            ${icon('chevron-down', { size: 16 })}
          </button>
          <button
            type="button"
            class="sys-icon-btn"
            id="btn-sys-metrics-close"
            title="Chiudi Prestazioni Server"
            aria-label="Chiudi Prestazioni Server"
          >
            ${icon('x', { size: 16 })}
          </button>
        </div>
      </header>

      <div class="sys-metrics-toolbar">
        <div class="sys-win-group" role="group" aria-label="Intervallo temporale grafici">
          ${windowsHtml}
        </div>
        <span class="sys-metrics-res-badge" id="sys-metrics-res-badge">--</span>
      </div>

      <div class="sys-metrics-body" id="sys-metrics-body"></div>
    `;

    this.uiLayer.appendChild(this.panelEl);
    this.subtitleEl = this.panelEl.querySelector('#sys-metrics-subtitle');
    this.livePillEl = this.panelEl.querySelector('#sys-metrics-live-pill');
    this.resBadgeEl = this.panelEl.querySelector('#sys-metrics-res-badge');
    this.bodyEl = this.panelEl.querySelector('#sys-metrics-body');
    this.collapseBtnEl = this.panelEl.querySelector('#btn-sys-metrics-collapse');
    this.refreshBtnEl = this.panelEl.querySelector('#btn-sys-metrics-refresh');
    this.closeBtnEl = this.panelEl.querySelector('#btn-sys-metrics-close');
  }

  _bindShellEvents() {
    if (!this.panelEl) return;

    this.closeBtnEl?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.close();
    });

    this.collapseBtnEl?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.setCollapsed(!this.isCollapsed);
    });

    this.panelEl.querySelector('#sys-metrics-header-toggle')?.addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      this.setCollapsed(!this.isCollapsed);
    });

    this.refreshBtnEl?.addEventListener('click', (e) => {
      e.stopPropagation();
      void this.refresh();
    });

    this.panelEl.querySelectorAll('[data-metrics-window]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const nextWin = Number(btn.dataset.metricsWindow);
        if (!Number.isFinite(nextWin) || nextWin <= 0) return;
        this.setWindow(nextWin);
      });
    });

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', this._onVisibilityChange);
    }
    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', this._onKeyDown);
    }
  }

  setCollapsed(collapsed) {
    this.isCollapsed = Boolean(collapsed);
    this.panelEl?.classList.toggle('collapsed', this.isCollapsed);
    this.collapseBtnEl?.setAttribute('aria-expanded', String(!this.isCollapsed));
    if (this.collapseBtnEl) {
      this.collapseBtnEl.innerHTML = icon(this.isCollapsed ? 'chevron-up' : 'chevron-down', { size: 16 });
    }
  }

  setWindow(windowS) {
    this.windowS = Number(windowS) || 300;
    this.panelEl?.querySelectorAll('[data-metrics-window]').forEach((btn) => {
      const isMatch = Number(btn.dataset.metricsWindow) === this.windowS;
      btn.classList.toggle('active', isMatch);
      btn.setAttribute('aria-pressed', String(isMatch));
    });
    void this.refresh();
    if (this.isOpen) {
      this._restartPolling();
    }
  }

  open() {
    if (!this.haClient?.isAdmin && !this.haClient?.isMockMode) return;
    if (this.isOpen) return;
    this.isOpen = true;
    this.setCollapsed(false);
    if (this.panelEl) {
      this.panelEl.hidden = false;
      this.panelEl.setAttribute('aria-hidden', 'false');
      this.panelEl.classList.add('open');
    }
    this.onOpenCallback?.();
    void this.refresh();
    this._restartPolling();
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this._stopPolling();
    if (typeof document !== 'undefined' && this.panelEl?.contains?.(document.activeElement)) {
      document.activeElement?.blur?.();
      document.getElementById('btn-open-system-metrics')?.focus?.();
    }
    if (this.panelEl) {
      this.panelEl.classList.remove('open');
      this.panelEl.setAttribute('aria-hidden', 'true');
      this.panelEl.hidden = true;
    }
    this.onCloseCallback?.();
  }

  _stopPolling() {
    if (this._pollTimer) {
      clearInterval(this._pollTimer);
      this._pollTimer = null;
    }
  }

  _restartPolling() {
    this._stopPolling();
    if (!this.isOpen) return;
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
    const intervalMs = resolveRefreshMs(this.windowS);
    this._pollTimer = setInterval(() => {
      if (this.isOpen) {
        void this.refresh({ silent: true });
      }
    }, intervalMs);
  }

  _buildMockPreviewPayload() {
    const now = Date.now() / 1000;
    const count = 60;
    const step = this.windowS / count;
    const series = [];
    for (let i = 0; i <= count; i += 1) {
      const t = now - (count - i) * step;
      const wave = Math.sin(i * 0.28);
      const wave2 = Math.cos(i * 0.19);
      const cpu = 22 + 9 * wave + 4 * wave2;
      const gpu = 18 + 7 * Math.sin(i * 0.35 + 0.8);
      const ram = 64 + 1.2 * wave2;
      const cvTot = 5.2 + 1.4 * Math.max(0, wave);
      const cvPers = wave > 0.2 ? 3.2 + 0.6 * wave : 0.0;
      const cvVeh = wave2 > 0.3 ? 1.8 : 0.0;
      series.push({
        t,
        timestamp: t,
        cpu_pct: Number(cpu.toFixed(1)),
        gpu_pct: Number(gpu.toFixed(1)),
        gpu_mem_mb: 312.4,
        ram_pct: Number(ram.toFixed(1)),
        ram_used_mb: 5180,
        proc_cpu_pct: Number((cpu * 0.38).toFixed(1)),
        proc_rss_mb: 342.0,
        cv_fps_total: Number(cvTot.toFixed(2)),
        cv_fps_target: 7.0,
        cv_fps_person: Number(cvPers.toFixed(2)),
        cv_fps_vehicle: Number(cvVeh.toFixed(2)),
        cv_fps_idle: Number(Math.max(0, cvTot - cvPers - cvVeh).toFixed(2)),
        cv_infer_ms: Number((44 + 8 * Math.abs(wave)).toFixed(1)),
        cv_infer_ms_max: Number((58 + 10 * Math.abs(wave)).toFixed(1)),
        person_det_fps: cvPers > 0 ? 1.8 : 0.0,
        vehicle_det_fps: cvVeh > 0 ? 1.0 : 0.0,
        animal_det_fps: 0.0,
        bio_fps: cvPers > 0 ? 0.6 : 0.0,
        bio_face_ms: 48.0,
        bio_alpr_ms: 62.0,
        bio_queue: 0,
        tracks_total: (cvPers > 0 ? 1 : 0) + (cvVeh > 0 ? 1 : 0),
        tracks_person: cvPers > 0 ? 1 : 0,
        tracks_vehicle: cvVeh > 0 ? 1 : 0,
        tracks_animal: 0,
        nvr_ram_mb: 0.0,
        ws_clients: 1,
        cameras: {
          Cam_Carraio: { actual_fps: 1.2, target_fps: 1.2, infer_ms: 43.0, tier: 'idle', rtsp_connected: true },
          Cam_Portico: { actual_fps: cvPers > 0 ? 3.5 : 1.2, target_fps: cvPers > 0 ? 3.5 : 1.2, infer_ms: 46.0, tier: cvPers > 0 ? 'person' : 'idle', rtsp_connected: true },
        },
      });
    }
    const latest = series[series.length - 1];
    return {
      status: 'ok',
      is_mock_preview: true,
      window_s: this.windowS,
      source: 'mock',
      resolution_s: Number(step.toFixed(1)),
      current: { ...latest, openvino_backend: 'Anteprima demo', gpu_backend: 'demo', ram_total_mb: 8079 },
      entities: [
        { entity_id: 'sensor.sh3d_pc_cpu', name: 'PC Fisso CPU', state: latest.cpu_pct, unit_of_measurement: '%' },
        { entity_id: 'sensor.sh3d_pc_gpu', name: 'PC Fisso GPU', state: latest.gpu_pct, unit_of_measurement: '%' },
        { entity_id: 'sensor.sh3d_pc_ram', name: 'PC Fisso RAM', state: latest.ram_pct, unit_of_measurement: '%' },
        { entity_id: 'sensor.sh3d_cv_fps_totale', name: 'CV FPS Totale', state: latest.cv_fps_total, unit_of_measurement: 'FPS' },
      ],
      series,
      summary: {
        samples_count: series.length,
        ram_samples_count: series.length,
        db_samples_count: 0,
        sample_interval_s: 2.0,
        persist_interval_s: 15.0,
        retention_days: 7,
        db_size_estimate_mb: 0.0,
        cpu_avg: 22.0,
        cpu_max: 35.0,
        gpu_avg: 18.0,
        gpu_max: 25.0,
        ram_avg: 64.0,
        cv_fps_avg: 5.4,
        cv_fps_max: 6.6,
        infer_ms_avg: 47.0,
      },
      bridges: { ha_bridge_connected: false, mqtt_bridge_connected: false, ha_publish_interval_s: 15.0 },
    };
  }

  async refresh({ silent = false } = {}) {
    if (this.isLoading) return;
    this.isLoading = true;
    this.errorText = '';
    if (!silent && this.refreshBtnEl) {
      this.refreshBtnEl.classList.add('spinning');
    }
    try {
      let res = null;
      if (typeof this.spatialStreamClient?.fetchMetricsHistory === 'function') {
        res = await this.spatialStreamClient.fetchMetricsHistory({ windowS: this.windowS, maxPoints: 180 });
      }
      if (res && res.status === 'ok') {
        this.data = res;
      } else if (this.haClient?.isMockMode) {
        this.data = this._buildMockPreviewPayload();
      } else {
        this.errorText = 'Impossibile raggiungere la telemetria di spatial_server.';
      }
    } catch {
      if (this.haClient?.isMockMode) {
        this.data = this._buildMockPreviewPayload();
      } else {
        this.errorText = 'Errore durante il caricamento dei grafici.';
      }
    } finally {
      this.isLoading = false;
      this.refreshBtnEl?.classList.remove('spinning');
      this.render();
    }
  }

  render() {
    if (!this.bodyEl) return;

    if (!this.data && this.errorText) {
      if (this.livePillEl) {
        this.livePillEl.textContent = 'OFFLINE';
        this.livePillEl.className = 'sys-live-pill offline';
      }
      this.bodyEl.innerHTML = `
        <div class="sh3d-empty-state">
          <span class="sh3d-empty-icon">${icon('alert-triangle', { size: 18 })}</span>
          <div class="sh3d-empty-title">Telemetria non disponibile</div>
          <div class="sh3d-empty-hint">${escapeHtml(this.errorText)}</div>
        </div>
      `;
      return;
    }

    if (!this.data) {
      this.bodyEl.innerHTML = `<div class="sys-loading">Caricamento metriche...</div>`;
      return;
    }

    const d = this.data;
    const cur = d.current || {};
    const sum = d.summary || {};
    const series = d.series || [];
    const entities = d.entities || [];
    const bridges = d.bridges || {};
    const isMock = Boolean(d.is_mock_preview);

    if (this.livePillEl) {
      this.livePillEl.textContent = isMock ? 'DEMO' : 'LIVE';
      this.livePillEl.className = `sys-live-pill ${isMock ? 'demo' : 'online'}`;
    }
    if (this.subtitleEl) {
      const rawBackend = String(cur.openvino_backend || cur.ingestion_mode || 'spatial_server');
      const backendStr = rawBackend.replace(/\(\(([^()]+)\)\)/g, '($1)');
      const retDays = sum.retention_days ?? 7;
      this.subtitleEl.textContent = `${backendStr} · camp. ${sum.sample_interval_s ?? 2}s · DB ${retDays}g (${fmtNum(sum.db_size_estimate_mb, 2, '0.00')} MB)`;
    }
    if (this.resBadgeEl) {
      const srcLabel = d.source === 'sqlite' ? 'SQLite' : d.source === 'mixed' ? 'RAM+DB' : d.source === 'mock' ? 'Demo' : 'RAM';
      this.resBadgeEl.textContent = `${series.length} pt · ~${fmtNum(d.resolution_s, 0, '2')}s · ${srcLabel}`;
    }

    const ramUsedGb = cur.ram_used_mb ? (cur.ram_used_mb / 1024).toFixed(1) : '0.0';
    const ramTotGb = cur.ram_total_mb ? (cur.ram_total_mb / 1024).toFixed(1) : '8.0';
    const gpuAvailable = cur.gpu_pct !== null && cur.gpu_pct !== undefined;

    const kpiHtml = `
      <div class="sys-kpi-grid">
        <div class="sys-kpi-card">
          <div class="sys-kpi-label">CPU PC Fisso</div>
          <div class="sys-kpi-value">${fmtNum(cur.cpu_pct, 1)}%</div>
          <div class="sys-kpi-sub">Python: ${fmtNum(cur.proc_cpu_pct, 1)}% · Max ${fmtNum(sum.cpu_max, 1)}%</div>
        </div>
        <div class="sys-kpi-card">
          <div class="sys-kpi-label">GPU PC Fisso</div>
          <div class="sys-kpi-value">${gpuAvailable ? `${fmtNum(cur.gpu_pct, 1)}%` : 'N/D'}</div>
          <div class="sys-kpi-sub">${cur.gpu_mem_mb != null ? `VRAM/Sh: ${fmtNum(cur.gpu_mem_mb, 0)} MB` : escapeHtml(cur.gpu_backend || 'iGPU')}</div>
        </div>
        <div class="sys-kpi-card">
          <div class="sys-kpi-label">RAM PC Fisso</div>
          <div class="sys-kpi-value">${fmtNum(cur.ram_pct, 1)}%</div>
          <div class="sys-kpi-sub">${ramUsedGb}/${ramTotGb} GB · Py ${fmtNum(cur.proc_rss_mb, 0)} MB</div>
        </div>
        <div class="sys-kpi-card">
          <div class="sys-kpi-label">FPS Riconoscimento</div>
          <div class="sys-kpi-value">${fmtNum(cur.cv_fps_total, 1)} <span class="sys-kpi-unit">FPS</span></div>
          <div class="sys-kpi-sub">Target ${fmtNum(cur.cv_fps_target, 1)} · ${fmtNum(cur.cv_infer_ms, 0)} ms</div>
        </div>
      </div>
    `;

    // Chart 1: CPU / GPU / RAM %
    const hwChartSvg = buildSvgChart({
      chartId: 'Carico CPU, GPU e RAM',
      series,
      windowS: this.windowS,
      unit: '%',
      fixedMin: 0,
      fixedMax: 100,
      lines: [
        { key: 'cpu_pct', label: 'CPU PC', color: '#38bdf8', width: 2 },
        { key: 'gpu_pct', label: 'GPU PC', color: '#34d399', width: 2 },
        { key: 'ram_pct', label: 'RAM PC', color: '#f59e0b', width: 1.6, area: false },
        { key: 'proc_cpu_pct', label: 'CPU Server', color: '#cbd5e1', width: 1.3, dashed: true, area: false },
      ],
    });

    // Chart 2: CV FPS (total, target, person, vehicle)
    const fpsChartSvg = buildSvgChart({
      chartId: 'FPS Riconoscimento CV',
      series,
      windowS: this.windowS,
      unit: ' FPS',
      fixedMin: 0,
      fixedMax: null,
      lines: [
        { key: 'cv_fps_total', label: 'FPS Totale', color: '#38bdf8', width: 2 },
        { key: 'cv_fps_person', label: 'Persone', color: '#34d399', width: 1.7, area: false },
        { key: 'cv_fps_vehicle', label: 'Veicoli', color: '#f59e0b', width: 1.7, area: false },
        { key: 'cv_fps_target', label: 'Target Budget', color: '#94a3b8', width: 1.3, dashed: true, area: false },
      ],
    });

    const camEntries = Object.entries(cur.cameras || {});
    const offlineErrors = [];
    const camsHtml = camEntries.length
      ? `<div class="sys-cam-strip">
          ${camEntries
            .map(([camId, info]) => {
              const tier = String(info.tier || 'idle');
              const rtspDown = info.rtsp_connected === false;
              const tierLabel = rtspDown ? 'RTSP OFF' : (TIER_LABELS_IT[tier] || tier);
              if (rtspDown && info.last_error) {
                offlineErrors.push(`${camId.replace(/^Cam_/, '')}: ${info.last_error}`);
              }
              return `
                <div class="sys-cam-pill tier-${escapeHtml(tier)} ${rtspDown ? 'rtsp-offline' : ''}"${info.last_error ? ` title="${escapeHtml(info.last_error)}"` : ''}>
                  <span class="sys-cam-name">${escapeHtml(camId.replace(/^Cam_/, ''))}</span>
                  <span class="sys-cam-vals">${fmtNum(info.actual_fps, 1)}/${fmtNum(info.target_fps, 1)} FPS · ${fmtNum(info.infer_ms, 0)}ms</span>
                  <span class="sys-cam-tier">${escapeHtml(tierLabel)}</span>
                </div>
              `;
            })
            .join('')}
        </div>${offlineErrors.length ? `<div class="sys-cam-err-note">${escapeHtml(offlineErrors[0])}</div>` : ''}`
      : '';

    // Chart 3: Inference Latency & Biometrics
    const latChartSvg = buildSvgChart({
      chartId: 'Latenza Inferenza CV',
      series,
      windowS: this.windowS,
      unit: ' ms',
      fixedMin: 0,
      fixedMax: null,
      lines: [
        { key: 'cv_infer_ms', label: 'YOLO Media (ms)', color: '#38bdf8', width: 2 },
        { key: 'cv_infer_ms_max', label: 'YOLO Picco (ms)', color: '#fb7185', width: 1.4, dashed: true, area: false },
        { key: 'bio_face_ms', label: 'Volti ONNX (ms)', color: '#34d399', width: 1.5, area: false },
        { key: 'bio_alpr_ms', label: 'Targhe ALPR (ms)', color: '#f59e0b', width: 1.5, area: false },
      ],
    });

    // Chart 4: Active Subjects & Detection Throughput
    const detChartSvg = buildSvgChart({
      chartId: 'Soggetti Tracciati e Rilevamenti',
      series,
      windowS: this.windowS,
      unit: '',
      fixedMin: 0,
      fixedMax: null,
      lines: [
        { key: 'tracks_person', label: 'Persone attive', color: '#34d399', width: 1.9 },
        { key: 'tracks_vehicle', label: 'Veicoli attivi', color: '#f59e0b', width: 1.8, area: false },
        { key: 'tracks_animal', label: 'Animali attivi', color: '#2dd4bf', width: 1.5, area: false },
        { key: 'bio_fps', label: 'Biometria (FPS)', color: '#38bdf8', width: 1.4, dashed: true, area: false },
      ],
    });

    const entitiesRowsHtml = entities
      .map((ent) => {
        const eid = String(ent.entity_id || '');
        const unit = ent.unit_of_measurement ? ` ${ent.unit_of_measurement}` : '';
        const copied = this._copiedEntityId === eid;
        return `
          <div class="sys-entity-row">
            <div class="sys-entity-meta">
              <span class="sys-entity-name">${escapeHtml(ent.name)}</span>
              <code class="sys-entity-id">${escapeHtml(eid)}</code>
            </div>
            <div class="sys-entity-right">
              <span class="sys-entity-val">${escapeHtml(ent.state)}${escapeHtml(unit)}</span>
              <button
                type="button"
                class="sys-copy-btn ${copied ? 'copied' : ''}"
                data-copy-entity="${escapeHtml(eid)}"
                title="Copia ID entità"
                aria-label="Copia ${escapeHtml(eid)}"
              >
                ${icon(copied ? 'check' : 'copy', { size: 13 })}
              </button>
            </div>
          </div>
        `;
      })
      .join('');

    const preserveScrollTop = this.bodyEl.scrollTop;

    this.bodyEl.innerHTML = `
      ${kpiHtml}

      <section class="sys-chart-card">
        <div class="sys-chart-head">
          <h3 class="sys-chart-title">Carico PC Fisso (CPU, GPU, RAM)</h3>
          <span class="sys-chart-stat">CPU avg ${fmtNum(sum.cpu_avg, 1)}% · GPU avg ${sum.gpu_avg != null ? `${fmtNum(sum.gpu_avg, 1)}%` : 'N/D'}</span>
        </div>
        ${hwChartSvg}
        <div class="sys-legend">
          <span class="sys-leg-item"><i style="background:#38bdf8"></i>CPU PC</span>
          <span class="sys-leg-item"><i style="background:#34d399"></i>GPU PC</span>
          <span class="sys-leg-item"><i style="background:#f59e0b"></i>RAM PC</span>
          <span class="sys-leg-item"><i style="background:#cbd5e1"></i>CPU Server</span>
        </div>
      </section>

      <section class="sys-chart-card">
        <div class="sys-chart-head">
          <h3 class="sys-chart-title">FPS Riconoscimento (Persone / Veicoli / Idle)</h3>
          <span class="sys-chart-stat">Avg ${fmtNum(sum.cv_fps_avg, 1)} · Max ${fmtNum(sum.cv_fps_max, 1)} FPS</span>
        </div>
        ${fpsChartSvg}
        <div class="sys-legend">
          <span class="sys-leg-item"><i style="background:#38bdf8"></i>Totale</span>
          <span class="sys-leg-item"><i style="background:#34d399"></i>Persone</span>
          <span class="sys-leg-item"><i style="background:#f59e0b"></i>Veicoli</span>
          <span class="sys-leg-item"><i style="background:#94a3b8"></i>Target budget</span>
        </div>
        ${camsHtml}
      </section>

      <section class="sys-chart-card">
        <div class="sys-chart-head">
          <h3 class="sys-chart-title">Latenza Inferenza &amp; Biometria ONNX</h3>
          <span class="sys-chart-stat">YOLO ${fmtNum(cur.cv_infer_ms, 0)}ms · Face ${fmtNum(cur.bio_face_ms, 0)}ms · ALPR ${fmtNum(cur.bio_alpr_ms, 0)}ms</span>
        </div>
        ${latChartSvg}
        <div class="sys-legend">
          <span class="sys-leg-item"><i style="background:#38bdf8"></i>YOLO media</span>
          <span class="sys-leg-item"><i style="background:#fb7185"></i>YOLO picco</span>
          <span class="sys-leg-item"><i style="background:#34d399"></i>Volti Face</span>
          <span class="sys-leg-item"><i style="background:#f59e0b"></i>Targhe ALPR</span>
        </div>
      </section>

      <section class="sys-chart-card">
        <div class="sys-chart-head">
          <h3 class="sys-chart-title">Soggetti Tracciati &amp; Throughput Biometria</h3>
          <span class="sys-chart-stat">Det/s P:${fmtNum(cur.person_det_fps, 1)} V:${fmtNum(cur.vehicle_det_fps, 1)} · Coda bio: ${cur.bio_queue ?? 0}</span>
        </div>
        ${detChartSvg}
        <div class="sys-legend">
          <span class="sys-leg-item"><i style="background:#34d399"></i>Persone</span>
          <span class="sys-leg-item"><i style="background:#f59e0b"></i>Veicoli</span>
          <span class="sys-leg-item"><i style="background:#2dd4bf"></i>Animali</span>
          <span class="sys-leg-item"><i style="background:#38bdf8"></i>Biometria FPS</span>
        </div>
      </section>

      <details class="sys-entities-details" id="sys-metrics-entities-details" ${this._entitiesOpen ? 'open' : ''}>
        <summary class="sys-entities-summary">
          <span>Entità esposte (${entities.length})</span>
          <span class="sys-bridge-pills">
            <span class="sys-bridge-pill ${bridges.ha_bridge_connected ? 'on' : ''}">HA ${bridges.ha_bridge_connected ? 'OK' : 'Off'}</span>
            <span class="sys-bridge-pill ${bridges.mqtt_bridge_connected ? 'on' : ''}">MQTT ${bridges.mqtt_bridge_connected ? 'OK' : 'Off'}</span>
          </span>
        </summary>
        <div class="sys-entities-list">
          ${entitiesRowsHtml}
        </div>
      </details>
    `;

    this.bodyEl.scrollTop = preserveScrollTop;
    this._bindBodyInteractions(series);
  }

  _bindBodyInteractions(series) {
    if (!this.bodyEl) return;

    const detEl = this.bodyEl.querySelector('#sys-metrics-entities-details');
    detEl?.addEventListener('toggle', () => {
      this._entitiesOpen = Boolean(detEl.open);
    });

    this.bodyEl.querySelectorAll('[data-copy-entity]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const eid = btn.dataset.copyEntity;
        if (!eid) return;
        try {
          if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
            void navigator.clipboard.writeText(eid);
          }
        } catch {}
        this._copiedEntityId = eid;
        if (this._copyTimer) clearTimeout(this._copyTimer);
        this._copyTimer = setTimeout(() => {
          this._copiedEntityId = null;
          if (this.isOpen) this.render();
        }, 1600);
        this.render();
      });
    });

    // Interactive hover/pointer scrubbing on charts
    const chartMeta = [
      {
        title: 'Carico CPU, GPU e RAM',
        format: (pt) =>
          `CPU ${fmtNum(pt.cpu_pct, 1)}% · GPU ${pt.gpu_pct != null ? `${fmtNum(pt.gpu_pct, 1)}%` : 'N/D'} · RAM ${fmtNum(pt.ram_pct, 1)}%`,
      },
      {
        title: 'FPS Riconoscimento CV',
        format: (pt) =>
          `Tot ${fmtNum(pt.cv_fps_total, 1)} · Pers ${fmtNum(pt.cv_fps_person, 1)} · Veic ${fmtNum(pt.cv_fps_vehicle, 1)} FPS`,
      },
      {
        title: 'Latenza Inferenza CV',
        format: (pt) =>
          `YOLO ${fmtNum(pt.cv_infer_ms, 0)}ms (max ${fmtNum(pt.cv_infer_ms_max, 0)}ms) · Face ${fmtNum(pt.bio_face_ms, 0)}ms`,
      },
      {
        title: 'Soggetti Tracciati e Rilevamenti',
        format: (pt) =>
          `Pers ${fmtNum(pt.tracks_person, 0)} · Veic ${fmtNum(pt.tracks_vehicle, 0)} · Bio ${fmtNum(pt.bio_fps, 1)} FPS`,
      },
    ];

    if (!Array.isArray(series) || series.length === 0) return;
    this.bodyEl.querySelectorAll('[data-chart-wrap]').forEach((wrap) => {
      const chartId = wrap.dataset.chartWrap;
      const meta = chartMeta.find((m) => m.title === chartId);
      const svg = wrap.querySelector('.sys-chart-svg');
      const hoverLine = wrap.querySelector('.sys-chart-hover-line');
      const tooltip = wrap.querySelector('.sys-chart-tooltip');
      if (!svg || !hoverLine || !tooltip || !meta) return;

      const updateAtClientX = (clientX) => {
        const rect = svg.getBoundingClientRect?.();
        if (!rect || rect.width <= 0) return;
        const relX = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const svgX = relX * 480;
        const plotFrac = Math.max(0, Math.min(1, (svgX - 36) / (480 - 36 - 10)));
        const idx = Math.max(0, Math.min(series.length - 1, Math.round(plotFrac * (series.length - 1))));
        const pt = series[idx];
        const lineX = 36 + (series.length === 1 ? 0.5 : idx / (series.length - 1)) * (480 - 36 - 10);
        hoverLine.setAttribute('x1', lineX.toFixed(1));
        hoverLine.setAttribute('x2', lineX.toFixed(1));
        hoverLine.hidden = false;
        const tsLabel = formatAxisTime(Number(pt.t ?? pt.timestamp ?? 0), this.windowS);
        tooltip.textContent = `${tsLabel} · ${meta.format(pt)}`;
        tooltip.hidden = false;
      };

      wrap.addEventListener('pointermove', (e) => updateAtClientX(e.clientX));
      wrap.addEventListener('pointerdown', (e) => updateAtClientX(e.clientX));
      wrap.addEventListener('pointerleave', () => {
        hoverLine.hidden = true;
        tooltip.hidden = true;
      });
    });
  }

  dispose() {
    this._stopPolling();
    if (this._copyTimer) clearTimeout(this._copyTimer);
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this._onVisibilityChange);
    }
    if (typeof window !== 'undefined') {
      window.removeEventListener('keydown', this._onKeyDown);
    }
    this.panelEl?.remove?.();
  }
}
