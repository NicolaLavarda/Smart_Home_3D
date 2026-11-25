import { deviceRegistry } from '../devices/DeviceRegistry.js';
import { icon } from '../ui/icons.js';

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

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
    this.container.setAttribute('role', 'dialog');
    this.container.setAttribute('aria-labelledby', 'modal-title');
    this.container.innerHTML = `
      <div class="modal-header" id="modal-header-toggle" role="button" tabindex="0" aria-expanded="true" title="Clicca per comprimere / espandere">
        <div class="modal-title-box">
          <h3 id="modal-title">Dispositivo</h3>
          <span id="modal-subtitle"></span>
        </div>
        <div class="modal-header-actions">
          <span class="modal-collapse-chevron" id="modal-collapse-icon">${icon('chevron-up', { size: 15 })}</span>
          <button type="button" class="btn-close" id="modal-close-btn" title="Chiudi" aria-label="Chiudi pannello">${icon('x', { size: 15 })}</button>
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

    this.modalHeader.addEventListener('keydown', (e) => {
      if (e.target?.closest?.('#modal-close-btn')) return;
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.setCollapsed(!this.container.classList.contains('collapsed'));
      }
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
    this.modalHeader?.setAttribute('aria-expanded', String(!this.isCollapsed));
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

    // 1. Verifica se esiste un controller dedicato nel registro decentralizzato (es. Smart TV, Lavastoviglie, Irrigazione, Telecamere)
    const customController = deviceRegistry.findControllerForEntity(entityId);
    if (customController) {
      const entity =
        (customController.getEntity ? customController.getEntity(entityId) : null) ||
        this.haClient.getEntity(entityId) || {
          entity_id: entityId,
          state: 'unknown',
          attributes: { friendly_name: customController.name || entityId },
        };

      const headerInfo =
        typeof customController.getModalHeaderInfo === 'function'
          ? customController.getModalHeaderInfo(entityId, entity)
          : null;

      this.modalTitle.textContent = headerInfo?.title || customController.name || entity.attributes?.friendly_name || 'Dispositivo';
      this._setSubtitle(headerInfo?.subtitle ?? customController.subtitle ?? '');

      customController.renderModal(this.modalContent, entity, {
        entityId,
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
    if (typeof document !== 'undefined' && this.container?.contains?.(document.activeElement)) {
      document.activeElement?.blur?.();
    }
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
    const title = escapeHtml(entity.attributes.media_title || 'Nessun media in esecuzione');
    const app = escapeHtml(entity.attributes.app_name || 'TV Salotto');
    const stateLabel = escapeHtml(String(entity.state || '').toUpperCase());

    this.modalContent.innerHTML = `
      <div class="control-row">
        <div class="modal-media-info">
          <div class="modal-media-title">${title}</div>
          <div class="modal-media-sub">${app}</div>
        </div>
        <span class="ha-status-badge">
          <span class="ha-dot ${isPlaying ? 'online' : 'offline'}"></span>
          ${stateLabel}
        </span>
      </div>

      <div class="control-row">
        <label>Controllo Riproduzione</label>
        <button type="button" class="btn-action-primary" id="tv-play-btn">
          ${isPlaying ? `${icon('pause', { size: 14 })} <span>Sospendi</span>` : `${icon('play', { size: 14 })} <span>Riproduci</span>`}
        </button>
      </div>

      <div class="control-row control-row--stack">
        <div class="control-row-head">
          <label for="tv-volume-slider">Volume</label>
          <span id="tv-vol-label" class="control-row-value">${volume}%</span>
        </div>
        <input type="range" min="0" max="100" value="${volume}" id="tv-volume-slider" name="tv-volume-slider" class="timeline-slider" />
      </div>

      <button type="button" class="btn-icon-text btn-full-width" id="tv-power-btn">
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
    const safeCamName = escapeHtml(camName || 'Nessuna camera 3D diretta');

    this.modalContent.innerHTML = `
      <div class="camera-preview-stream">
        <span class="live-badge">LIVE STREAM</span>
        <div class="cam-fallback-preview">
          <div class="cam-fallback-icon">${icon('cctv', { size: 28 })}</div>
          <div>H.265 / WebRTC Stream Attivo</div>
          <div class="cam-fallback-meta">
            1920×1080 @ 25fps • WebRTC
          </div>
        </div>
      </div>

      <div class="control-row">
        <label>Telecamera 3D Associata</label>
        <span class="modal-mono-value">${safeCamName}</span>
      </div>

      <button type="button" class="btn-action-primary btn-full-width" id="btn-camera-pov">
        ${icon('crosshair', { size: 15 })} <span>Entra nella vista POV di questa telecamera</span>
      </button>

      <div class="cam-fallback-hint">
        Allinea la navigazione 3D alla visuale e al campo visivo della telecamera.
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
        <button type="button" class="btn-action-primary" id="light-toggle-btn">
          ${isOn ? 'Spegni' : 'Accendi'}
        </button>
      </div>

      <div class="control-row control-row--stack">
        <div class="control-row-head">
          <label for="light-bright-slider">Luminosità</label>
          <span id="light-bright-label" class="control-row-value">${brightness}%</span>
        </div>
        <input type="range" min="1" max="100" value="${brightness}" id="light-bright-slider" name="light-bright-slider" class="timeline-slider" />
      </div>

      <div class="control-row control-row--stack">
        <label>Colore Tonalità</label>
        <div class="color-presets-row">
          <button type="button" class="btn-icon-text color-preset color-preset--warm" data-rgb="[255, 220, 160]">Caldo</button>
          <button type="button" class="btn-icon-text color-preset color-preset--neutral" data-rgb="[255, 255, 255]">Neutro</button>
          <button type="button" class="btn-icon-text color-preset color-preset--cool" data-rgb="[180, 220, 255]">Freddo</button>
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
    const safeState = escapeHtml(entity.state);
    this.modalContent.innerHTML = `
      <div class="control-row">
        <label>Stato Corrente</label>
        <span class="modal-state-value">${safeState}</span>
      </div>
      <button type="button" class="btn-action-primary btn-full-width" id="generic-toggle-btn">Cambia stato</button>
    `;
    this.modalContent.querySelector('#generic-toggle-btn').addEventListener('click', () => {
      const domain = entity.entity_id.split('.')[0];
      this.haClient.callService(domain, 'toggle', { entity_id: entity.entity_id });
      setTimeout(() => this.open(entity.entity_id), 150);
    });
  }

  findMatchingBlenderCameraName(cameraEntityId) {
    if (!this.assetLoader?.manifest?.cameras) return 'Cam_Carraio';
    const cameras = this.assetLoader.manifest.cameras;
    for (const [name, camData] of Object.entries(cameras)) {
      if (camData?.ha_camera_entity === cameraEntityId) {
        return name;
      }
    }
    const slug = String(cameraEntityId || '').toLowerCase().replace(/^camera\./, '').replace(/_(scorrevole|trasparente|fluente|main|sub)$/i, '');
    for (const [name, camData] of Object.entries(cameras)) {
      if (!camData?.ha_camera_entity && !camData?.is_real_security_camera) continue;
      const camSlug = name.replace(/^Cam_/i, '').toLowerCase();
      if (slug && (camSlug === slug || String(camData?.stream_id || '').toLowerCase().startsWith(slug))) {
        return name;
      }
    }
    return 'Cam_Carraio';
  }
}

