import { icon } from '../ui/icons.js';

export class TimelineController {
  constructor(domContainer, trajectoryRenderer, cameraProjector) {
    this.container = domContainer;
    this.trajectoryRenderer = trajectoryRenderer;
    this.cameraProjector = cameraProjector;
    this.spatialStreamClient = null;

    this.isCollapsed = true;
    this.entitiesVisible = false;
    this.isLive = false;
    this.isPlaying = false;
    this.playbackSpeed = 1.0;
    this.currentTime = 0;
    this.minTime = 0;
    this.maxTime = 60;
    this.replayOriginUnix = null;
    this.hasAutoSwitchedLive = false;
    this.densityBins = [];
    this.densityTimer = null;

    this.initUI();
    this.generateSyntheticScenario();
    this.setCollapsed(true);
    this.setEntitiesVisible(false);
  }

  initUI() {
    this.container.innerHTML = `
      <div class="timeline-header">
        <div class="timeline-info" id="timeline-collapse-toggle" role="button" tabindex="0" title="Espandi Timeline">
          <span class="timeline-title-wrap">
            ${icon('history', { size: 15 })}
            <span class="timeline-title-text">SPATIAL REPLAY ENGINE</span>
          </span>
          <span class="spatial-status-pill" id="spatial-status-pill">DEMO LOCALE</span>
          <span id="timeline-entity-count" style="color: var(--text-muted); font-size: 11px;">0 Rilevazioni</span>
          <span class="timeline-collapse-icon" id="timeline-collapse-icon">${icon('chevron-up', { size: 14 })}</span>
        </div>
        <div class="timeline-mode-toggle">
          <button class="mode-btn active" id="btn-mode-replay">Replay Storico</button>
          <button class="mode-btn" id="btn-mode-live">Live Stream</button>
        </div>
      </div>

      <div class="timeline-controls-row">
        <button class="btn-timeline-visibility" id="btn-toggle-entities" title="Mostra/Nascondi persone e veicoli ricostruiti nel 3D">${icon('eye-off', { size: 15 })}</button>
        <button class="btn-timeline-play" id="btn-play-pause" title="Play / Pausa">${icon('play', { size: 15 })}</button>

        <div class="timeline-slider-wrap">
          <canvas id="timeline-density-canvas" class="timeline-density-canvas" height="22"></canvas>
          <input type="range" min="0" max="60" step="0.1" value="0" class="timeline-slider" id="timeline-range-slider" />
        </div>

        <div class="timeline-time-display" id="timeline-clock">00:00.0s</div>

        <div class="speed-selector">
          <button class="speed-btn active" data-speed="1">1x</button>
          <button class="speed-btn" data-speed="2">2x</button>
          <button class="speed-btn" data-speed="5">5x</button>
        </div>
      </div>
    `;

    this.slider = this.container.querySelector('#timeline-range-slider');
    this.clockDisplay = this.container.querySelector('#timeline-clock');
    this.toggleEntitiesBtn = this.container.querySelector('#btn-toggle-entities');
    this.playBtn = this.container.querySelector('#btn-play-pause');
    this.entityCountEl = this.container.querySelector('#timeline-entity-count');
    this.statusPill = this.container.querySelector('#spatial-status-pill');
    this.densityCanvas = this.container.querySelector('#timeline-density-canvas');
    this.replayModeBtn = this.container.querySelector('#btn-mode-replay');
    this.liveModeBtn = this.container.querySelector('#btn-mode-live');
    this.collapseToggle = this.container.querySelector('#timeline-collapse-toggle');
    this.collapseIcon = this.container.querySelector('#timeline-collapse-icon');

    this.collapseToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      this.setCollapsed(!this.container.classList.contains('collapsed'));
    });

    this.collapseToggle.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.setCollapsed(!this.container.classList.contains('collapsed'));
      }
    });

    this.container.addEventListener('click', () => {
      if (this.container.classList.contains('collapsed')) {
        this.setCollapsed(false);
      }
    });

    this.toggleEntitiesBtn.addEventListener('click', () => this.toggleEntitiesVisible());
    this.playBtn.addEventListener('click', () => this.togglePlay());
    this.slider.addEventListener('input', (e) => {
      this.currentTime = parseFloat(e.target.value);
      this.updateClockDisplay();
      this.trajectoryRenderer.updateAtTime(this.currentTime);
    });

    this.replayModeBtn.addEventListener('click', () => this.setMode(false));
    this.liveModeBtn.addEventListener('click', () => this.setMode(true));

    this.container.querySelectorAll('.speed-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.container.querySelectorAll('.speed-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        this.playbackSpeed = parseFloat(btn.dataset.speed);
      });
    });
  }

  setSpatialStreamClient(spatialStreamClient) {
    this.spatialStreamClient = spatialStreamClient;
    if (!spatialStreamClient) return;

    spatialStreamClient.onStatusChange((connected, meta) => {
      if (connected) {
        const rawMode = (meta?.ingestion_mode || spatialStreamClient.lastStatusPayload?.ingestion_mode || '').toLowerCase();
        const mode = (rawMode || 'LIVE').toUpperCase();
        const isRealServer = Boolean(rawMode && rawMode !== 'synthetic');
        this.statusPill.textContent = `SPATIAL ${mode}`;
        this.statusPill.classList.add('online');

        if (isRealServer) {
          this.container.classList.remove('demo-inactive');
          this.setEntitiesVisible(true);
          if (!this.hasAutoSwitchedLive) {
            this.hasAutoSwitchedLive = true;
            this.setMode(true);
          }
        } else {
          this.setEntitiesVisible(false);
          this.isPlaying = false;
          this.playBtn.innerHTML = icon('play', { size: 15 });
          this.container.classList.add('demo-inactive');
        }
        this.refreshDensityHistogram();
        if (!this.densityTimer) {
          this.densityTimer = setInterval(() => this.refreshDensityHistogram(), 15000);
        }
      } else {
        this.statusPill.textContent = 'DEMO LOCALE';
        this.statusPill.classList.remove('online');
        this.setEntitiesVisible(false);
        this.isPlaying = false;
        this.playBtn.innerHTML = icon('play', { size: 15 });
        this.container.classList.add('demo-inactive');
      }
    });

    spatialStreamClient.onFrame((frame) => {
      if (!this.isLive) return;
      const tracks = frame.active_tracks || [];
      const mode = (frame.ingestion_mode || 'synthetic').toUpperCase();
      this.statusPill.textContent = `SPATIAL ${mode}`;
      this.statusPill.classList.add('online');

      this.trajectoryRenderer.updateLiveTracks(tracks, frame.timestamp);
      this.entityCountEl.textContent = `${tracks.length} Entità Live`;

      const dt = new Date((frame.timestamp || Date.now() / 1000) * 1000);
      this.clockDisplay.textContent = `LIVE ${dt.toLocaleTimeString('it-IT')}`;
    });
  }

  hasRealIngestion() {
    const mode = (this.spatialStreamClient?.lastStatusPayload?.ingestion_mode || '').toLowerCase();
    return Boolean(this.spatialStreamClient?.connected && mode && mode !== 'synthetic');
  }

  setEntitiesVisible(visible) {
    this.entitiesVisible = Boolean(visible);
    this.trajectoryRenderer.setEntitiesVisible(this.entitiesVisible);

    if (this.toggleEntitiesBtn) {
      this.toggleEntitiesBtn.classList.toggle('active', this.entitiesVisible);
      this.toggleEntitiesBtn.innerHTML = icon(this.entitiesVisible ? 'eye' : 'eye-off', { size: 15 });
      this.toggleEntitiesBtn.title = this.entitiesVisible
        ? 'Nascondi persone e veicoli ricostruiti nel 3D'
        : 'Mostra persone e veicoli ricostruiti nel 3D';
    }

    const isRealConnected = this.hasRealIngestion();
    this.container.classList.toggle('demo-inactive', !isRealConnected && !this.entitiesVisible);

    if (this.entitiesVisible && !this.isLive) {
      this.trajectoryRenderer.updateAtTime(this.currentTime);
    }
  }

  toggleEntitiesVisible() {
    this.setEntitiesVisible(!this.entitiesVisible);
  }

  setCollapsed(collapsed) {
    this.isCollapsed = Boolean(collapsed);
    this.container.classList.toggle('collapsed', this.isCollapsed);
    if (this.collapseIcon) {
      this.collapseIcon.innerHTML = icon(this.isCollapsed ? 'chevron-up' : 'chevron-down', { size: 14 });
    }
    if (this.collapseToggle) {
      this.collapseToggle.title = this.isCollapsed ? 'Espandi Timeline' : 'Comprimi Timeline';
    }
    if (!this.isCollapsed) {
      requestAnimationFrame(() => this.drawDensityCanvas());
    }
  }

  async setMode(isLive) {
    this.isLive = Boolean(isLive);
    if (this.isLive) {
      this.liveModeBtn.classList.add('active');
      this.replayModeBtn.classList.remove('active');
      this.isPlaying = true;
      this.playBtn.innerHTML = icon('pause', { size: 15 });
      this.slider.disabled = true;
      this.slider.style.opacity = '0.5';

      const backendOnline = Boolean(this.spatialStreamClient?.connected);
      this.trajectoryRenderer.setLiveMode(backendOnline);
      if (backendOnline) {
        this.clockDisplay.textContent = 'LIVE --:--:--';
        if (this.hasRealIngestion()) {
          this.entityCountEl.textContent = '0 Entità Live';
        }
      }
    } else {
      this.replayModeBtn.classList.add('active');
      this.liveModeBtn.classList.remove('active');
      this.slider.disabled = false;
      this.slider.style.opacity = '1.0';
      this.trajectoryRenderer.setLiveMode(false);
      this.replayOriginUnix = null;

      await this.loadHistoricalFromServer();
      this.updateClockDisplay();
      this.trajectoryRenderer.updateAtTime(this.currentTime);
    }
  }

  async refreshDensityHistogram() {
    if (!this.spatialStreamClient?.connected) return;
    const now = Date.now() / 1000;
    const res = await this.spatialStreamClient.fetchTimelineDensity(now - 300, now, 60);
    if (res && Array.isArray(res.bins)) {
      this.densityBins = res.bins;
      this.drawDensityCanvas();
    }
  }

  drawDensityCanvas() {
    const canvas = this.densityCanvas;
    if (!canvas) return;
    const rectWidth = canvas.clientWidth || 320;
    if (canvas.width !== rectWidth) canvas.width = rectWidth;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const bins = this.densityBins;
    if (!bins || bins.length === 0) return;

    const maxCount = Math.max(1, ...bins.map((b) => b.count || 0));
    const barW = w / bins.length;
    bins.forEach((b, idx) => {
      const ratio = (b.count || 0) / maxCount;
      const barH = Math.max(2, ratio * (h - 3));
      ctx.fillStyle = ratio > 0.6 ? 'rgba(56, 189, 248, 0.85)' : 'rgba(6, 182, 212, 0.42)';
      ctx.fillRect(idx * barW + 0.5, h - barH, Math.max(1, barW - 1), barH);
    });
  }

  async loadHistoricalFromServer() {
    if (!this.spatialStreamClient?.connected) return false;
    const now = Date.now() / 1000;
    const tStart = now - 300;
    const res = await this.spatialStreamClient.fetchTracks(tStart, now);
    await this.refreshDensityHistogram();

    if (res && Array.isArray(res.detections) && res.detections.length > 0) {
      const origin = res.t_min ?? res.detections[0].timestamp;
      const end = res.t_max ?? res.detections[res.detections.length - 1].timestamp;
      const span = Math.max(10, end - origin);

      this.replayOriginUnix = origin;
      this.minTime = 0;
      this.maxTime = Number(span.toFixed(1));
      this.currentTime = 0;
      this.slider.min = '0';
      this.slider.max = String(this.maxTime);
      this.slider.value = '0';

      const mapped = res.detections.map((d) => ({
        id: d.track_id,
        class: d.class_label,
        identity: d.identity,
        identity_confidence: d.identity_confidence,
        plate: d.plate,
        plate_confidence: d.plate_confidence,
        plate_whitelisted: d.plate_whitelisted,
        plate_owner: d.plate_owner,
        biometric_locked: d.biometric_locked,
        best_crop_id: d.best_crop_id,
        confidence: d.confidence,
        x: d.x,
        y: d.y,
        z: d.z,
        vx: d.vx || 0,
        vz: d.vz || 0,
        t: d.timestamp - origin,
        camera_id: d.camera_sources?.[0] || 'Cam_Carraio',
        camera_sources: d.camera_sources || ['Cam_Carraio'],
      }));

      this.trajectoryRenderer.loadDetections(mapped);
      const uniqueIds = new Set(mapped.map((m) => m.id)).size;
      this.entityCountEl.textContent = `${mapped.length} Record SQLite (${uniqueIds} Entità)`;
      return true;
    }
    return false;
  }

  togglePlay() {
    this.isPlaying = !this.isPlaying;
    this.playBtn.innerHTML = icon(this.isPlaying ? 'pause' : 'play', { size: 15 });
  }

  update(delta) {
    if (this.isLive && this.spatialStreamClient?.connected) {
      this.trajectoryRenderer.interpolateLive(delta);
      return;
    }

    if (!this.isPlaying) return;

    this.currentTime += delta * this.playbackSpeed;
    if (this.currentTime > this.maxTime) {
      this.currentTime = this.minTime;
    }

    this.slider.value = this.currentTime;
    this.updateClockDisplay();
    this.trajectoryRenderer.updateAtTime(this.currentTime);
  }

  updateClockDisplay() {
    if (this.replayOriginUnix) {
      const dt = new Date((this.replayOriginUnix + this.currentTime) * 1000);
      this.clockDisplay.textContent = dt.toLocaleTimeString('it-IT');
      return;
    }
    const totalSecs = this.currentTime;
    const mins = Math.floor(totalSecs / 60);
    const secs = (totalSecs % 60).toFixed(1);
    this.clockDisplay.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(4, '0')}s`;
  }

  generateSyntheticScenario() {
    // Coordinate verificate su house_optimized.glb (Three.js +Z = Sud/Strada, X = Est/Ovest)
    const detections = [];

    // Persona 101: entra dal cancelletto pedonale e percorre Walkway_Pedestrian_Pavement verso il portico
    const pathPerson = [
      { t: 0,  x: -4.2, y: 0.05, z: 10.5, identity: 'Nicola' },
      { t: 5,  x: -3.6, y: 0.05, z: 8.2,  identity: 'Nicola' },
      { t: 10, x: -3.0, y: 0.05, z: 6.0,  identity: 'Nicola' },
      { t: 15, x: -2.4, y: 0.05, z: 4.0,  identity: 'Nicola' },
      { t: 20, x: -1.8, y: 0.05, z: 2.2,  identity: 'Nicola' },
      { t: 25, x: -1.0, y: 0.05, z: 1.0,  identity: 'Nicola' },
      { t: 40, x: -1.0, y: 0.05, z: 1.0,  identity: 'Nicola' },
    ];

    // Auto 202: entra dal cancello carrabile su Driveway_Gravel verso il garage
    const pathCar = [
      { t: 12, x: -2.5, y: 0.05, z: 18.0 },
      { t: 18, x: -2.8, y: 0.05, z: 14.5 },
      { t: 24, x: -3.2, y: 0.05, z: 11.0 },
      { t: 30, x: -3.5, y: 0.05, z: 7.5 },
      { t: 38, x: -3.5, y: 0.05, z: 4.5 },
      { t: 60, x: -3.5, y: 0.05, z: 4.5 },
    ];

    // Persona 303: passeggia davanti al vialetto in ghiaia
    const pathPerson2 = [
      { t: 32, x: -5.8, y: 0.05, z: 12.0, identity: 'Ospite' },
      { t: 40, x: -4.2, y: 0.05, z: 11.2, identity: 'Ospite' },
      { t: 48, x: -2.0, y: 0.05, z: 9.8,  identity: 'Ospite' },
      { t: 56, x: 0.2,  y: 0.05, z: 7.5,  identity: 'Ospite' },
      { t: 60, x: 0.5,  y: 0.05, z: 6.2,  identity: 'Ospite' },
    ];

    function samplePath(id, cls, path, camId) {
      for (let i = 0; i < path.length - 1; i++) {
        const p1 = path[i];
        const p2 = path[i + 1];
        const step = 0.5;
        for (let t = p1.t; t < p2.t; t += step) {
          const factor = (t - p1.t) / (p2.t - p1.t);
          detections.push({
            id,
            class: cls,
            identity: p1.identity || null,
            x: p1.x + (p2.x - p1.x) * factor,
            y: p1.y + (p2.y - p1.y) * factor,
            z: p1.z + (p2.z - p1.z) * factor,
            t: parseFloat(t.toFixed(2)),
            camera_id: camId,
          });
        }
      }
    }

    samplePath('101', 'person', pathPerson, 'Cam_Carraio');
    samplePath('202', 'car', pathCar, 'Cam_Carraio');
    samplePath('303', 'person', pathPerson2, 'Cam_Carraio');

    this.trajectoryRenderer.loadDetections(detections);
    this.entityCountEl.textContent = `${detections.length} Rilevazioni Demo (3 Entità)`;
  }
}
