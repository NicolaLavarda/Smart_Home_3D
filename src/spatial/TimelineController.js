export class TimelineController {
  constructor(domContainer, trajectoryRenderer, cameraProjector) {
    this.container = domContainer;
    this.trajectoryRenderer = trajectoryRenderer;
    this.cameraProjector = cameraProjector;

    this.isLive = false;
    this.isPlaying = true;
    this.playbackSpeed = 1.0;
    this.currentTime = 0;
    this.minTime = 0;
    this.maxTime = 60; // 60 secondi di scenario test

    this.initUI();
    this.generateSyntheticScenario();
  }

  initUI() {
    this.container.innerHTML = `
      <div class="timeline-header">
        <div class="timeline-info">
          <span style="font-weight: 600; color: var(--accent-cyan);">SPATIAL REPLAY ENGINE</span>
          <span id="timeline-entity-count" style="color: var(--text-muted); font-size: 11px;">0 Rilevazioni</span>
        </div>
        <div class="timeline-mode-toggle">
          <button class="mode-btn active" id="btn-mode-replay">Replay Storico</button>
          <button class="mode-btn" id="btn-mode-live">Live Stream</button>
        </div>
      </div>

      <div class="timeline-controls-row">
        <button class="btn-timeline-play" id="btn-play-pause">⏸</button>
        
        <div class="timeline-slider-wrap">
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
    this.playBtn = this.container.querySelector('#btn-play-pause');
    this.entityCountEl = this.container.querySelector('#timeline-entity-count');
    this.replayModeBtn = this.container.querySelector('#btn-mode-replay');
    this.liveModeBtn = this.container.querySelector('#btn-mode-live');

    // Event listeners
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

  setMode(isLive) {
    this.isLive = isLive;
    if (isLive) {
      this.liveModeBtn.classList.add('active');
      this.replayModeBtn.classList.remove('active');
      this.isPlaying = true;
      this.playBtn.textContent = '⏸';
      this.slider.disabled = true;
      this.slider.style.opacity = '0.5';
    } else {
      this.replayModeBtn.classList.add('active');
      this.liveModeBtn.classList.remove('active');
      this.slider.disabled = false;
      this.slider.style.opacity = '1.0';
    }
  }

  togglePlay() {
    this.isPlaying = !this.isPlaying;
    this.playBtn.textContent = this.isPlaying ? '⏸' : '▶';
  }

  update(delta) {
    if (!this.isPlaying) return;

    if (this.isLive) {
      // In modalità live scorre in loop continuo sui dati sintetici
      this.currentTime += delta * this.playbackSpeed;
      if (this.currentTime > this.maxTime) {
        this.currentTime = this.minTime;
      }
    } else {
      this.currentTime += delta * this.playbackSpeed;
      if (this.currentTime > this.maxTime) {
        this.currentTime = this.minTime;
      }
    }

    this.slider.value = this.currentTime;
    this.updateClockDisplay();
    this.trajectoryRenderer.updateAtTime(this.currentTime);
  }

  updateClockDisplay() {
    const totalSecs = this.currentTime;
    const mins = Math.floor(totalSecs / 60);
    const secs = (totalSecs % 60).toFixed(1);
    this.clockDisplay.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(4, '0')}s`;
  }

  generateSyntheticScenario() {
    // Genera dati sintetici realistici:
    // Coordinate del modello: cancello ingresso ~ (-10, 0), portico ~ (0, -4), casa ingresso ~ (3, -5), garage ~ (0, -15)
    const detections = [];

    // Persona 101: entra dal cancello pedonale, cammina lungo il vialetto e sale sul portico
    const pathPerson = [
      { t: 0,  x: -8.5, y: 0.05, z: 2.0 },
      { t: 5,  x: -6.5, y: 0.05, z: 0.5 },
      { t: 10, x: -4.5, y: 0.05, z: -1.5 },
      { t: 15, x: -2.5, y: 0.05, z: -3.5 },
      { t: 20, x: -0.5, y: 0.08, z: -4.5 },
      { t: 25, x: 1.5,  y: 0.08, z: -5.0 },
      { t: 30, x: 3.5,  y: 0.08, z: -5.2 },
      { t: 40, x: 3.5,  y: 0.08, z: -5.2 }, // Sosta davanti alla porta
    ];

    // Auto 202: entra dal cancello carrabile, percorre il vialetto in ghiaia e parcheggia davanti al garage
    const pathCar = [
      { t: 12, x: -8.0, y: 0.05, z: 5.5 },
      { t: 16, x: -6.0, y: 0.05, z: 3.0 },
      { t: 20, x: -4.0, y: 0.05, z: 0.0 },
      { t: 25, x: -2.0, y: 0.05, z: -4.0 },
      { t: 30, x: -1.0, y: 0.05, z: -9.0 },
      { t: 35, x: -0.5, y: 0.05, z: -14.0 },
      { t: 40, x: 0.0,  y: 0.05, z: -17.5 },
      { t: 60, x: 0.0,  y: 0.05, z: -17.5 }, // Parcheggiata davanti al garage
    ];

    // Persona 303: esce dal garage e passeggia sul prato del giardino est
    const pathPerson2 = [
      { t: 35, x: 2.0,  y: 0.05, z: -17.0 },
      { t: 40, x: 4.5,  y: 0.05, z: -15.0 },
      { t: 45, x: 7.0,  y: 0.05, z: -12.0 },
      { t: 50, x: 9.0,  y: 0.05, z: -9.0 },
      { t: 55, x: 10.5, y: 0.05, z: -6.0 },
      { t: 60, x: 10.5, y: 0.05, z: -4.0 },
    ];

    // Campionamento fitto (ogni 0.5 secondi)
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
    this.entityCountEl.textContent = `${detections.length} Rilevazioni (3 Entità)`;
  }
}

