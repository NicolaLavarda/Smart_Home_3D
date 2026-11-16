import { icon } from './icons.js';

export class TopBar {
  constructor(domContainer, {
    sceneManager,
    cameraController,
    cameraProjector,
    interactionManager,
    haClient,
    calibrationAssistant = null,
    assetLoader = null,
    deviceModals = null,
  }) {
    this.container = domContainer;
    this.sceneManager = sceneManager;
    this.cameraController = cameraController;
    this.cameraProjector = cameraProjector;
    this.interactionManager = interactionManager;
    this.haClient = haClient;
    this.calibrationAssistant = calibrationAssistant;
    this.assetLoader = assetLoader;
    this.deviceModals = deviceModals;
    this._setQuickNavCollapsed = null;

    this.initUI();
    this.bindEvents();
  }

  initUI() {
    this.container.innerHTML = `
      <div class="top-bar-left glass">
        <div class="logo-badge">
          <div class="logo-icon">3D</div>
          <div class="logo-text-group">
            <div class="logo-title">SMART HOME</div>
            <div class="ha-status-badge" id="ha-badge">
              <span class="ha-dot mock" id="ha-dot"></span>
              <span id="ha-text">Connessione HA...</span>
            </div>
          </div>
        </div>
      </div>

      <div class="top-bar-controls glass">
        <button class="btn-icon-text" id="btn-toggle-night" title="Alterna modalità Giorno e Notte" aria-label="Alterna modalità Giorno e Notte">
          ${icon('moon', { size: 15 })} <span class="top-btn-label" id="night-text">Notte</span>
        </button>

        <button class="btn-icon-text" id="btn-toggle-frustums" title="Mostra/Nascondi coni visivi telecamere" aria-label="Mostra o nascondi copertura telecamere">
          ${icon('cctv', { size: 15 })} <span class="top-btn-label">Copertura Camere</span>
        </button>

        <button class="btn-icon-text" id="btn-toggle-badges" title="Mostra/Nascondi badge dei dispositivi" aria-label="Mostra o nascondi badge dei dispositivi">
          ${icon('tag', { size: 15 })} <span class="top-btn-label">Badge Dispositivi</span>
        </button>

        <div class="settings-dropdown-wrap" id="settings-dropdown-wrap">
          <button class="btn-icon-text btn-settings-gear" id="btn-settings-menu" title="Impostazioni" aria-label="Impostazioni" aria-haspopup="true" aria-expanded="false">
            ${icon('settings', { size: 16 })}
            ${icon('chevron-down', { size: 13, className: 'settings-chevron' })}
          </button>
          <div class="top-settings-dropdown glass" id="top-settings-dropdown">
            <button class="settings-dropdown-item" id="btn-open-cam-calib" title="Apri calibrazione ottica POV su Cam_Carraio">
              ${icon('sliders-horizontal', { size: 15 })}
              <span>Calibra Cam</span>
            </button>
          </div>
        </div>
      </div>
    `;

    this.haDot = this.container.querySelector('#ha-dot');
    this.haText = this.container.querySelector('#ha-text');
    this.nightBtn = this.container.querySelector('#btn-toggle-night');
    this.frustumsBtn = this.container.querySelector('#btn-toggle-frustums');
    this.settingsBtn = this.container.querySelector('#btn-settings-menu');
    this.settingsDropdown = this.container.querySelector('#top-settings-dropdown');
    this.calibBtn = this.container.querySelector('#btn-open-cam-calib');
    this.badgesBtn = this.container.querySelector('#btn-toggle-badges');

    // Ascolta lo stato di HA
    this.haClient.onStatusChange((status, details) => {
      this.haDot.className = `ha-dot ${status}`;
      this.haText.textContent = details || status.toUpperCase();
    });
  }

  closeSettingsDropdown() {
    this.settingsDropdown?.classList.remove('open');
    this.settingsBtn?.classList.remove('active');
    this.settingsBtn?.setAttribute('aria-expanded', 'false');
  }

  bindEvents() {
    // Toggle Notte / Giorno
    this.nightBtn.addEventListener('click', () => {
      const isNight = !this.sceneManager.isNightMode;
      this.sceneManager.setNightMode(isNight);
      this.nightBtn.classList.toggle('active', isNight);
      this.nightBtn.innerHTML = isNight
        ? `${icon('sun', { size: 15 })} <span class="top-btn-label" id="night-text">Giorno</span>`
        : `${icon('moon', { size: 15 })} <span class="top-btn-label" id="night-text">Notte</span>`;
    });

    // Toggle Frustum Telecamere
    this.frustumsBtn.addEventListener('click', () => {
      const isVisible = this.cameraProjector.toggleFrustums();
      this.frustumsBtn.classList.toggle('active', isVisible);
    });

    // Menu Impostazioni a Tendina
    this.settingsBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      const willOpen = !this.settingsDropdown.classList.contains('open');
      this.settingsDropdown.classList.toggle('open', willOpen);
      this.settingsBtn.classList.toggle('active', willOpen);
      this.settingsBtn.setAttribute('aria-expanded', String(willOpen));
      if (willOpen && this.calibBtn) {
        this.calibBtn.classList.toggle('active', Boolean(this.calibrationAssistant?.isOpen));
      }
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest('#settings-dropdown-wrap')) {
        this.closeSettingsDropdown();
      }
    });

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.closeSettingsDropdown();
      }
    });

    // Apertura Calibrazione Ottica POV Cam_Carraio
    this.calibBtn?.addEventListener('click', () => {
      this.closeSettingsDropdown();
      if (!this.calibrationAssistant) return;
      if (this.calibrationAssistant.isOpen) {
        this.calibrationAssistant.close();
        this.calibBtn.classList.remove('active');
        return;
      }
      this.deviceModals?.close();
      if (window.innerWidth <= 1024) {
        this.setQuickNavCollapsed(true);
      }
      this.calibBtn.classList.add('active');
      const camNode = this.assetLoader?.cameras?.get('Cam_Carraio');
      if (camNode && this.cameraController) {
        this.cameraController.flyToCameraPOV(camNode, 1.1, () => {
          this.calibrationAssistant.open('Cam_Carraio');
        });
      } else {
        this.calibrationAssistant.open('Cam_Carraio');
      }
    });

    // Toggle Badges Dispositivi
    this.badgesBtn.addEventListener('click', () => {
      const isVisible = this.interactionManager.toggleBadges();
      this.badgesBtn.classList.toggle('active', isVisible);
    });

    // Quicknav laterale per viste
    this.setupQuickNav();
  }

  setupQuickNav() {
    const quicknav = document.createElement('div');
    quicknav.className = 'side-quicknav glass';
    quicknav.innerHTML = `
      <div class="side-header" id="quicknav-header-toggle" role="button" tabindex="0" title="Comprimi / Espandi Viste Rapide">
        <span class="side-header-left">
          ${icon('compass', { size: 14, className: 'side-header-icon' })}
          <span class="side-header-title">Viste Rapide</span>
        </span>
        <span class="side-collapse-icon" id="quicknav-collapse-icon">
          ${icon('chevron-left', { size: 14 })}
        </span>
      </div>
      <div class="quicknav-list">
        <button class="quicknav-btn active" data-preset="overview">${icon('globe', { size: 15 })}<span>Panoramica</span></button>
        <button class="quicknav-btn" data-preset="carraio_cam">${icon('cctv', { size: 15 })}<span>POV Telecamera Carraio</span></button>
        <button class="quicknav-btn" data-preset="gate">${icon('door-open', { size: 15 })}<span>Cancello & Accessi</span></button>
        <button class="quicknav-btn" data-preset="garden">${icon('trees', { size: 15 })}<span>Giardino & Lampioncini</span></button>
        <button class="quicknav-btn" data-preset="irrigation_area1">${icon('droplets', { size: 15 })}<span>Impianto Irrigazione</span></button>
        <button class="quicknav-btn" data-preset="living">${icon('sofa', { size: 15 })}<span>Salotto</span></button>
        <button class="quicknav-btn" data-preset="dining">${icon('utensils', { size: 15 })}<span>Sala da pranzo</span></button>
        <button class="quicknav-btn" data-preset="kitchen">${icon('cooking-pot', { size: 15 })}<span>Cucina</span></button>
        <button class="quicknav-btn" data-preset="laundry">${icon('flame', { size: 15 })}<span>Impianto Termico</span></button>
        <button class="quicknav-btn" data-preset="topdown">${icon('compass', { size: 15 })}<span>Pianta Zenitale</span></button>
      </div>
    `;
    document.querySelector('.ui-layer').appendChild(quicknav);

    const headerToggle = quicknav.querySelector('#quicknav-header-toggle');
    const collapseIconEl = quicknav.querySelector('#quicknav-collapse-icon');

    const setCollapsed = (collapsed) => {
      quicknav.classList.toggle('collapsed', collapsed);
      collapseIconEl.innerHTML = icon(collapsed ? 'chevron-right' : 'chevron-left', { size: 14 });
      headerToggle.title = collapsed ? 'Espandi Viste Rapide' : 'Comprimi Viste Rapide';
    };
    this._setQuickNavCollapsed = setCollapsed;

    // Su tablet e smartphone parte compresso per lasciare libera la scena 3D
    if (window.innerWidth <= 1024) {
      setCollapsed(true);
    }

    headerToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      setCollapsed(!quicknav.classList.contains('collapsed'));
    });

    headerToggle.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setCollapsed(!quicknav.classList.contains('collapsed'));
      }
    });

    quicknav.addEventListener('click', () => {
      if (quicknav.classList.contains('collapsed')) {
        setCollapsed(false);
      }
    });

    const buttons = quicknav.querySelectorAll('.quicknav-btn');
    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        buttons.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        const preset = btn.dataset.preset;
        if (preset === 'carraio_cam') {
          const camNode = this.assetLoader?.cameras?.get('Cam_Carraio');
          if (camNode) {
            this.cameraController.flyToCameraPOV(camNode, 1.3);
            return;
          }
        }
        this.cameraController.flyToPreset(preset);
      });
    });
  }

  setQuickNavCollapsed(collapsed) {
    if (this._setQuickNavCollapsed) {
      this._setQuickNavCollapsed(Boolean(collapsed));
    }
  }
}

