export class DeviceModals {
  constructor(modalContainer, haClient, cameraController, assetLoader) {
    this.container = modalContainer;
    this.haClient = haClient;
    this.cameraController = cameraController;
    this.assetLoader = assetLoader;
    this.currentEntityId = null;

    this.initUI();
  }

  initUI() {
    this.container.innerHTML = `
      <div class="modal-header">
        <div class="modal-title-box">
          <h3 id="modal-title">Dispositivo</h3>
          <span id="modal-subtitle">entity_id</span>
        </div>
        <button class="btn-close" id="modal-close-btn">&times;</button>
      </div>
      <div class="modal-controls" id="modal-content">
        <!-- Contenuto dinamico iniettato in base al dominio -->
      </div>
    `;

    this.modalTitle = this.container.querySelector('#modal-title');
    this.modalSubtitle = this.container.querySelector('#modal-subtitle');
    this.modalContent = this.container.querySelector('#modal-content');
    this.closeBtn = this.container.querySelector('#modal-close-btn');

    this.closeBtn.addEventListener('click', () => this.close());
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.close();
    });
  }

  open(entityId) {
    this.currentEntityId = entityId;
    const entity = this.haClient.getEntity(entityId) || {
      entity_id: entityId,
      state: 'unknown',
      attributes: { friendly_name: entityId },
    };

    const domain = entityId.split('.')[0];
    this.modalTitle.textContent = entity.attributes.friendly_name || entityId;
    this.modalSubtitle.textContent = entityId;

    if (domain === 'media_player') {
      this.renderTVModal(entity);
    } else if (domain === 'camera') {
      this.renderCameraModal(entity);
    } else if (domain === 'light') {
      this.renderLightModal(entity);
    } else {
      this.renderGenericModal(entity);
    }

    this.container.classList.add('open');
  }

  close() {
    this.container.classList.remove('open');
    this.currentEntityId = null;
  }

  renderTVModal(entity) {
    const isPlaying = entity.state === 'playing';
    const volume = Math.round((entity.attributes.volume_level ?? 0.5) * 100);
    const title = entity.attributes.media_title || 'Nessun media in esecuzione';
    const app = entity.attributes.app_name || 'TV Salotto';

    this.modalContent.innerHTML = `
      <div class="control-row">
        <div>
          <div style="font-weight: 600; font-size: 14px;">${title}</div>
          <div style="font-size: 12px; color: var(--text-muted);">${app}</div>
        </div>
        <span class="ha-status-badge">
          <span class="ha-dot ${isPlaying ? 'online' : 'offline'}"></span>
          ${entity.state.toUpperCase()}
        </span>
      </div>

      <div class="control-row">
        <label>Controllo Riproduzione</label>
        <button class="btn-action-primary" id="tv-play-btn">
          ${isPlaying ? '⏸ Sospendi' : '▶ Riproduci'}
        </button>
      </div>

      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 8px;">
        <div style="display: flex; justify-content: space-between;">
          <label>Volume</label>
          <span id="tv-vol-label" style="font-size: 12px; font-family: var(--font-mono);">${volume}%</span>
        </div>
        <input type="range" min="0" max="100" value="${volume}" id="tv-volume-slider" class="timeline-slider" />
      </div>

      <button class="btn-icon-text" id="tv-power-btn" style="width: 100%; justify-content: center;">
        ⏻ Spegni / Accendi TV
      </button>
    `;

    this.modalContent.querySelector('#tv-play-btn').addEventListener('click', () => {
      this.haClient.callService('media_player', 'media_play_pause', { entity_id: entity.entity_id });
      setTimeout(() => this.open(entity.entity_id), 150);
    });

    this.modalContent.querySelector('#tv-power-btn').addEventListener('click', () => {
      this.haClient.callService('media_player', 'toggle', { entity_id: entity.entity_id });
      setTimeout(() => this.open(entity.entity_id), 150);
    });

    const volSlider = this.modalContent.querySelector('#tv-volume-slider');
    volSlider.addEventListener('input', (e) => {
      const v = parseInt(e.target.value, 10);
      this.modalContent.querySelector('#tv-vol-label').textContent = `${v}%`;
      this.haClient.callService('media_player', 'volume_set', {
        entity_id: entity.entity_id,
        volume_level: v / 100,
      });
    });
  }

  renderCameraModal(entity) {
    const camName = this.findMatchingBlenderCameraName(entity.entity_id);
    const camNode = camName ? this.assetLoader.cameras.get(camName) : null;

    this.modalContent.innerHTML = `
      <div class="camera-preview-stream">
        <span class="live-badge">LIVE STREAM</span>
        <div style="text-align: center; color: var(--text-muted); font-size: 12px; padding: 20px;">
          <div style="font-size: 24px; margin-bottom: 6px;">📹</div>
          <div>H.265 / WebRTC Stream Attivo</div>
          <div style="font-family: var(--font-mono); font-size: 11px; margin-top: 4px; color: var(--accent-cyan);">
            1920x1080 @ 25fps • Frigate AI
          </div>
        </div>
      </div>

      <div class="control-row">
        <label>Telecamera 3D Associata</label>
        <span style="font-family: var(--font-mono); font-size: 12px; color: var(--text-main);">
          ${camName || 'Nessuna camera 3D diretta'}
        </span>
      </div>

      <button class="btn-action-primary" id="btn-camera-pov" style="width: 100%;">
        🎯 Entra nella vista POV di questa telecamera
      </button>

      <div style="font-size: 11px; color: var(--text-muted); line-height: 1.4; text-align: center;">
        Allinea dolcemente la navigazione 3D alla visuale e al campo visivo (FOV) della telecamera reale esportata da Blender.
      </div>
    `;

    const povBtn = this.modalContent.querySelector('#btn-camera-pov');
    if (camNode) {
      povBtn.addEventListener('click', () => {
        this.cameraController.flyToCameraPOV(camNode, 1.5, () => {
          this.close();
        });
      });
    } else {
      povBtn.disabled = true;
      povBtn.textContent = 'Camera POV non trovata nella scena';
    }
  }

  renderLightModal(entity) {
    const isOn = entity.state === 'on';
    const brightness = Math.round(((entity.attributes.brightness ?? 255) / 255) * 100);

    this.modalContent.innerHTML = `
      <div class="control-row">
        <label>Stato Luce</label>
        <button class="btn-action-primary" id="light-toggle-btn">
          ${isOn ? 'Spegni' : 'Accendi'}
        </button>
      </div>

      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 8px;">
        <div style="display: flex; justify-content: space-between;">
          <label>Luminosità</label>
          <span id="light-bright-label" style="font-size: 12px; font-family: var(--font-mono);">${brightness}%</span>
        </div>
        <input type="range" min="1" max="100" value="${brightness}" id="light-bright-slider" class="timeline-slider" />
      </div>

      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 8px;">
        <label>Colore Tonalità</label>
        <div style="display: flex; gap: 8px;">
          <button class="btn-icon-text color-preset" data-rgb="[255, 220, 160]" style="flex: 1; background: #ffe4b5; color: #000;">Caldo</button>
          <button class="btn-icon-text color-preset" data-rgb="[255, 255, 255]" style="flex: 1; background: #ffffff; color: #000;">Neutro</button>
          <button class="btn-icon-text color-preset" data-rgb="[180, 220, 255]" style="flex: 1; background: #bfdbfe; color: #000;">Freddo</button>
        </div>
      </div>
    `;

    this.modalContent.querySelector('#light-toggle-btn').addEventListener('click', () => {
      this.haClient.callService('light', 'toggle', { entity_id: entity.entity_id });
      setTimeout(() => this.open(entity.entity_id), 150);
    });

    const bSlider = this.modalContent.querySelector('#light-bright-slider');
    bSlider.addEventListener('input', (e) => {
      const v = parseInt(e.target.value, 10);
      this.modalContent.querySelector('#light-bright-label').textContent = `${v}%`;
      this.haClient.callService('light', 'turn_on', {
        entity_id: entity.entity_id,
        brightness: Math.round((v / 100) * 255),
      });
    });

    this.modalContent.querySelectorAll('.color-preset').forEach((btn) => {
      btn.addEventListener('click', () => {
        const rgb = JSON.parse(btn.dataset.rgb);
        this.haClient.callService('light', 'turn_on', {
          entity_id: entity.entity_id,
          rgb_color: rgb,
        });
      });
    });
  }

  renderGenericModal(entity) {
    this.modalContent.innerHTML = `
      <div class="control-row">
        <label>Stato Corrente</label>
        <span style="font-weight: 600;">${entity.state}</span>
      </div>
      <button class="btn-action-primary" id="generic-toggle-btn">Toggle Stato</button>
    `;
    this.modalContent.querySelector('#generic-toggle-btn').addEventListener('click', () => {
      const domain = entity.entity_id.split('.')[0];
      this.haClient.callService(domain, 'toggle', { entity_id: entity.entity_id });
      setTimeout(() => this.open(entity.entity_id), 150);
    });
  }

  findMatchingBlenderCameraName(cameraEntityId) {
    if (!this.assetLoader.manifest || !this.assetLoader.manifest.cameras) return 'Cam_Carraio';
    for (const [name, camData] of Object.entries(this.assetLoader.manifest.cameras)) {
      if (camData.ha_camera_entity === cameraEntityId || (camData.ha_camera_entity && cameraEntityId.includes('carraio'))) {
        return name;
      }
    }
    return 'Cam_Carraio';
  }
}

