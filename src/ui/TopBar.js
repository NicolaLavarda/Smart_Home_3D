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
            <div class="settings-user-card" id="top-user-profile">
              <div class="settings-user-meta">
                <span class="settings-user-name" id="top-user-name">Non connesso</span>
                <span class="role-pill guest" id="top-user-role">Ospite</span>
              </div>
            </div>
            <div class="settings-dropdown-divider" id="top-settings-divider"></div>
            <button class="settings-dropdown-item" id="btn-open-cam-calib" title="Apri calibrazione ottica POV su Cam_Carraio" hidden disabled style="display: none;">
              ${icon('sliders-horizontal', { size: 15 })}
              <span>Calibra Cam</span>
            </button>
            <button class="settings-dropdown-item auth-login" id="btn-ha-auth-action" title="Accedi con Home Assistant">
              ${icon('log-in', { size: 15 })}
              <span>Accedi con Home Assistant</span>
            </button>
            <div class="settings-dropdown-divider"></div>
            <div class="settings-perf-stats" id="top-perf-stats" style="padding: 4px 10px 6px; font-size: 10px; line-height: 1.35; color: #94a3b8; word-break: break-word;">v2-opt</div>
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
    this.userProfileEl = this.container.querySelector('#top-user-profile');
    this.userNameEl = this.container.querySelector('#top-user-name');
    this.userRoleEl = this.container.querySelector('#top-user-role');
    this.calibBtn = this.container.querySelector('#btn-open-cam-calib');
    this.authActionBtn = this.container.querySelector('#btn-ha-auth-action');
    this.badgesBtn = this.container.querySelector('#btn-toggle-badges');
    this.perfStatsEl = this.container.querySelector('#top-perf-stats');

    this.updateAuthUI();

    // Ascolta lo stato di HA
    this.haClient.onStatusChange((status, details) => {
      this.haDot.className = `ha-dot ${status}`;
      if (status === 'auth_required') {
        this.haText.textContent = details || 'Accesso richiesto';
      } else {
        this.haText.textContent = details || status.toUpperCase();
      }
    });

    this.haClient.onAuthChange?.((authState) => {
      this.updateAuthUI(authState);
    });
  }

  updateAuthUI(authState = null) {
    const isAdmin = Boolean(authState?.isAdmin ?? this.haClient?.isAdmin);
    const user = authState?.user ?? this.haClient?.currentUser ?? null;
    const isMock = Boolean(authState?.isMockMode ?? this.haClient?.isMockMode);
    const isAuthenticated = Boolean(
      authState?.authenticated ??
      ((this.haClient?.authStatus === 'authenticated' || this.haClient?.connection || this.haClient?.currentUser) && !isMock)
    );

    if (this.userNameEl) {
      if (isAuthenticated) {
        this.userNameEl.textContent = user?.name || 'Utente HA';
      } else if (isMock) {
        this.userNameEl.textContent = 'Demo Locale';
      } else {
        this.userNameEl.textContent = 'Non connesso';
      }
    }

    if (this.userRoleEl) {
      if (isAuthenticated && isAdmin) {
        this.userRoleEl.textContent = 'Admin';
        this.userRoleEl.className = 'role-pill admin';
      } else if (isAuthenticated) {
        this.userRoleEl.textContent = 'Residente';
        this.userRoleEl.className = 'role-pill resident';
      } else if (isMock) {
        this.userRoleEl.textContent = 'Demo Locale';
        this.userRoleEl.className = 'role-pill guest';
      } else {
        this.userRoleEl.textContent = 'Ospite';
        this.userRoleEl.className = 'role-pill guest';
      }
    }

    if (this.calibBtn) {
      this.calibBtn.hidden = !isAdmin;
      this.calibBtn.disabled = !isAdmin;
      this.calibBtn.style.display = isAdmin ? '' : 'none';
      if (!isAdmin) {
        this.calibBtn.classList.remove('active');
      }
    }

    if (!isAdmin && this.calibrationAssistant?.isOpen) {
      this.calibrationAssistant.close();
    }

    if (this.authActionBtn) {
      if (isAuthenticated) {
        this.authActionBtn.className = 'settings-dropdown-item auth-logout';
        this.authActionBtn.title = 'Disconnetti sessione Home Assistant';
        this.authActionBtn.innerHTML = `${icon('log-out', { size: 15 })} <span>Esci</span>`;
      } else {
        this.authActionBtn.className = 'settings-dropdown-item auth-login';
        this.authActionBtn.title = 'Accedi con Home Assistant';
        this.authActionBtn.innerHTML = `${icon('log-in', { size: 15 })} <span>Accedi con Home Assistant</span>`;
      }
    }
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
      if (willOpen && this.perfStatsEl && typeof this.sceneManager?.getPerfStats === 'function') {
        const s = this.sceneManager.getPerfStats();
        const gpuShort = String(s.gpu || 'unknown').replace(/^ANGLE \(([^,]+),\s*/i, '').replace(/\)$/, '').slice(0, 42);
        this.perfStatsEl.textContent = `${s.build} • ${s.fps} FPS • ${s.calls} calls • dpr ${s.dpr} • ${gpuShort}`;
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

    // Apertura Calibrazione Ottica POV Cam_Carraio (solo Admin)
    this.calibBtn?.addEventListener('click', () => {
      this.closeSettingsDropdown();
      if (!this.haClient?.isAdmin) return;
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

    // Azione Login / Logout Home Assistant
    this.authActionBtn?.addEventListener('click', async () => {
      this.closeSettingsDropdown();
      const isMock = Boolean(this.haClient?.isMockMode);
      const isAuthenticated = Boolean(
        (this.haClient?.authStatus === 'authenticated' || this.haClient?.connection || this.haClient?.currentUser) && !isMock
      );
      if (isAuthenticated) {
        await this.haClient?.logout?.();
      } else {
        await this.haClient?.loginWithOAuth?.();
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
    (document.querySelector('.ui-layer') || document.body)?.appendChild(quicknav);

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

