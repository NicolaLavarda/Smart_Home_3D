import { deviceRegistry } from '../devices/DeviceRegistry.js';
import { icon } from '../ui/icons.js';

export class DeviceModals {
  constructor(modalContainer, haClient, cameraController, assetLoader) {
    this.container = modalContainer;
    this.haClient = haClient;
    this.cameraController = cameraController;
    this.assetLoader = assetLoader;
    this.currentEntityId = null;
    this.isCollapsed = false;
    this.onOpenCallback = null;
    this.onCloseCallback = null;

    this.initUI();
  }

  setLifecycleHooks({ onOpen, onClose } = {}) {
    this.onOpenCallback = typeof onOpen === 'function' ? onOpen : null;
    this.onCloseCallback = typeof onClose === 'function' ? onClose : null;
  }

  initUI() {
    this.container.innerHTML = `
      <div class="modal-header" id="modal-header-toggle" title="Clicca per comprimere / espandere">
        <div class="modal-title-box">
          <h3 id="modal-title">Dispositivo</h3>
          <span id="modal-subtitle"></span>
        </div>
        <div class="modal-header-actions">
          <span class="modal-collapse-chevron" id="modal-collapse-icon">${icon('chevron-up', { size: 15 })}</span>
          <button class="btn-close" id="modal-close-btn" title="Chiudi">${icon('x', { size: 15 })}</button>
        </div>
      </div>
      <div class="modal-controls" id="modal-content">
        <!-- Contenuto dinamico iniettato in base al dominio -->
      </div>
    `;

    this.modalHeader = this.container.querySelector('#modal-header-toggle');
    this.modalTitle = this.container.querySelector('#modal-title');
    this.modalSubtitle = this.container.querySelector('#modal-subtitle');
    this.modalContent = this.container.querySelector('#modal-content');
    this.collapseIcon = this.container.querySelector('#modal-collapse-icon');
    this.closeBtn = this.container.querySelector('#modal-close-btn');

    this.modalHeader.addEventListener('click', () => {
      this.setCollapsed(!this.container.classList.contains('collapsed'));
    });

    this.closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.close();
    });
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.close();
    });
  }

  setCollapsed(collapsed) {
    this.isCollapsed = Boolean(collapsed);
    this.container.classList.toggle('collapsed', this.isCollapsed);
    if (this.collapseIcon) {
      this.collapseIcon.innerHTML = icon(this.isCollapsed ? 'chevron-down' : 'chevron-up', { size: 15 });
    }
  }

  _setSubtitle(text) {
    if (!this.modalSubtitle) return;
    const clean = typeof text === 'string' ? text.trim() : '';
    this.modalSubtitle.textContent = clean;
    this.modalSubtitle.hidden = !clean;
  }

  _domainSubtitle(domain) {
    const labels = {
      light: 'Illuminazione',
      switch: 'Interruttore',
      cover: 'Accesso & Automazione',
      camera: 'Telecamera',
      media_player: 'Smart TV & Media',
      sensor: 'Sensore',
      climate: 'Climatizzazione',
    };
    return labels[domain] || '';
  }

  open(entityId) {
    if (!entityId) return;

    // Se c'è già un modale aperto (anche per un altro dispositivo),
    // chiudi e ripulisci prima completamente quello precedente
    if (this.currentEntityId) {
      this.close();
    }

    // Assicura che il contenitore sia completamente svuotato prima di iniettare il nuovo modale
    if (this.modalContent) {
      this.modalContent.innerHTML = '';
    }

    this.currentEntityId = entityId;

    // 1. Verifica se esiste un controller dedicato nel registro decentralizzato (es. Smart TV, Lavastoviglie, Irrigazione)
    const customController = deviceRegistry.findControllerForEntity(entityId);
    if (customController) {
      const entity = customController.getEntity ? customController.getEntity() : (this.haClient.getEntity(entityId) || {
        entity_id: entityId,
        state: 'unknown',
        attributes: { friendly_name: customController.name || entityId },
      });

      this.modalTitle.textContent = customController.name || entity.attributes?.friendly_name || 'Dispositivo';
      this._setSubtitle(customController.subtitle || '');

      customController.renderModal(this.modalContent, entity, {
        haClient: this.haClient,
        cameraController: this.cameraController,
        assetLoader: this.assetLoader,
        modal: this,
      });

      this.setCollapsed(false);
      this.container.classList.add('open');
      this.onOpenCallback?.(entityId);
      return;
    }

    // 2. Fallback sui controlli standard di dominio
    const entity = this.haClient.getEntity(entityId) || {
      entity_id: entityId,
      state: 'unknown',
      attributes: { friendly_name: entityId },
    };

    const domain = entityId.split('.')[0];
    this.modalTitle.textContent = entity.attributes?.friendly_name || 'Dispositivo';
    this._setSubtitle(this._domainSubtitle(domain));

    if (domain === 'media_player') {
      this.renderTVModal(entity);
    } else if (domain === 'camera') {
      this.renderCameraModal(entity);
    } else if (domain === 'light') {
      this.renderLightModal(entity);
    } else {
      this.renderGenericModal(entity);
    }

    this.setCollapsed(false);
    this.container.classList.add('open');
    this.onOpenCallback?.(entityId);
  }

  close() {
    const wasOpen = this.container.classList.contains('open');
    this.container.classList.remove('open');
    this.setCollapsed(false);
    if (this.currentEntityId) {
      const customController = deviceRegistry.findControllerForEntity(this.currentEntityId);
      if (customController && typeof customController.onModalClose === 'function') {
        customController.onModalClose();
      }
    }
    // Per sicurezza difensiva, invoca onModalClose su tutti i controller registrati
    if (deviceRegistry && deviceRegistry.controllers) {
      for (const ctrl of deviceRegistry.controllers.values()) {
        if (typeof ctrl.onModalClose === 'function') {
          ctrl.onModalClose();
        }
      }
    }
    if (this.modalContent) {
      this.modalContent.innerHTML = '';
    }
    this.currentEntityId = null;
    if (wasOpen) {
      this.onCloseCallback?.();
    }
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
          ${isPlaying ? `${icon('pause', { size: 14 })} <span>Sospendi</span>` : `${icon('play', { size: 14 })} <span>Riproduci</span>`}
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
        ${icon('power', { size: 15 })} <span>Spegni / Accendi TV</span>
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
          <div style="margin-bottom: 6px; color: var(--accent-cyan);">${icon('cctv', { size: 28 })}</div>
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
        ${icon('crosshair', { size: 15 })} <span>Entra nella vista POV di questa telecamera</span>
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

