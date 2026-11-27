import { icon } from './icons.js';

export class TopBar {
  constructor(domContainer, {
    sceneManager,
    cameraController,
    cameraProjector,
    interactionManager,
    haClient,
    calibrationAssistant = null,
    automationStudio = null,
    systemMetricsPanel = null,
    assetLoader = null,
    deviceModals = null,
    cameraCatalog = null,
  }) {
    this.container = domContainer;
    this.sceneManager = sceneManager;
    this.cameraController = cameraController;
    this.cameraProjector = cameraProjector;
    this.interactionManager = interactionManager;
    this.haClient = haClient;
    this.calibrationAssistant = calibrationAssistant;
    this.automationStudio = automationStudio;
    this.systemMetricsPanel = systemMetricsPanel;
    this.assetLoader = assetLoader;
    this.deviceModals = deviceModals;
    this.cameraCatalog = cameraCatalog;
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
        <button class="btn-icon-text" id="btn-toggle-night" title="Alterna modalità Giorno e Notte" aria-label="Alterna modalità Giorno e Notte" aria-pressed="false">
          ${icon('moon', { size: 15 })} <span class="top-btn-label" id="night-text">Notte</span>
        </button>

        <button class="btn-icon-text" id="btn-toggle-frustums" data-coverage-mode="off" title="Copertura telecamere: disattivata (clicca per 3D)" aria-label="Copertura telecamere: disattivata" aria-pressed="false">
          ${icon('cctv', { size: 15 })} <span class="top-btn-label" id="frustums-text">Copertura Camere</span>
        </button>

        <button class="btn-icon-text" id="btn-toggle-badges" title="Mostra/Nascondi badge dei dispositivi" aria-label="Mostra o nascondi badge dei dispositivi" aria-pressed="false">
          ${icon('tag', { size: 15 })} <span class="top-btn-label">Badge Dispositivi</span>
        </button>

        <div class="settings-dropdown-wrap" id="settings-dropdown-wrap">
          <button class="btn-icon-text btn-settings-gear" id="btn-settings-menu" title="Impostazioni" aria-label="Impostazioni" aria-haspopup="menu" aria-expanded="false">
            ${icon('settings', { size: 16 })}
            ${icon('chevron-down', { size: 13, className: 'settings-chevron' })}
          </button>
          <div class="top-settings-dropdown glass" id="top-settings-dropdown" role="menu" aria-label="Menu impostazioni">
            <div class="settings-user-card" id="top-user-profile">
              <div class="settings-user-meta">
                <span class="settings-user-name" id="top-user-name">Non connesso</span>
                <span class="role-pill guest" id="top-user-role">Ospite</span>
              </div>
            </div>
            <div class="settings-dropdown-divider" id="top-settings-divider"></div>
            <button class="settings-dropdown-item" id="btn-open-automations" role="menuitem" title="Apri Automazioni Spaziali 3D, Aree e Perimetri" hidden disabled style="display: none;">
              ${icon('zap', { size: 15 })}
              <span>Automazioni</span>
            </button>
            <button class="settings-dropdown-item" id="btn-open-cam-calib" role="menuitem" title="Apri calibrazione ottica POV telecamere" hidden disabled style="display: none;">
              ${icon('sliders-horizontal', { size: 15 })}
              <span>Calibra Cam</span>
            </button>
            <button class="settings-dropdown-item" id="btn-open-system-metrics" role="menuitem" title="Apri monitoraggio CPU, GPU e FPS riconoscimento del server" hidden disabled style="display: none;">
              ${icon('activity', { size: 15 })}
              <span>Prestazioni Server</span>
            </button>
            <button class="settings-dropdown-item auth-login" id="btn-ha-auth-action" role="menuitem" title="Accedi con Home Assistant">
              ${icon('log-in', { size: 15 })}
              <span>Accedi con Home Assistant</span>
            </button>
            <div class="settings-dropdown-divider" id="top-perf-divider" hidden style="display: none;"></div>
            <details class="settings-perf-details" id="top-perf-details" hidden style="display: none;">
              <summary class="settings-perf-summary">Diagnostica grafica</summary>
              <div class="settings-perf-stats" id="top-perf-stats">v3-hd</div>
            </details>
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
    this.automationsBtn = this.container.querySelector('#btn-open-automations');
    this.calibBtn = this.container.querySelector('#btn-open-cam-calib');
    this.metricsBtn = this.container.querySelector('#btn-open-system-metrics');
    this.authActionBtn = this.container.querySelector('#btn-ha-auth-action');
    this.badgesBtn = this.container.querySelector('#btn-toggle-badges');
    this.perfDividerEl = this.container.querySelector('#top-perf-divider');
    this.perfDetailsEl = this.container.querySelector('#top-perf-details');
    this.perfStatsEl = this.container.querySelector('#top-perf-stats');

    this.nightBtn?.setAttribute('aria-pressed', String(Boolean(this.sceneManager?.isNightMode)));
    this.badgesBtn?.setAttribute('aria-pressed', String(Boolean(this.interactionManager?.badgesVisible)));
    this.updateFrustumsButtonUI(this.cameraProjector?.getFrustumMode?.() || 'off');
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

    if (this.automationsBtn) {
      const canManageAutomations = isAdmin || isMock;
      this.automationsBtn.hidden = !canManageAutomations;
      this.automationsBtn.disabled = !canManageAutomations;
      this.automationsBtn.style.display = canManageAutomations ? '' : 'none';
      if (!canManageAutomations) {
        this.automationsBtn.classList.remove('active');
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

    if (this.metricsBtn) {
      const canViewMetrics = isAdmin || isMock;
      this.metricsBtn.hidden = !canViewMetrics;
      this.metricsBtn.disabled = !canViewMetrics;
      this.metricsBtn.style.display = canViewMetrics ? '' : 'none';
      if (!canViewMetrics) {
        this.metricsBtn.classList.remove('active');
      }
    }

    if (this.perfDetailsEl) {
      this.perfDetailsEl.hidden = !isAdmin;
      this.perfDetailsEl.style.display = isAdmin ? '' : 'none';
      if (!isAdmin) {
        this.perfDetailsEl.open = false;
      }
    }
    if (this.perfDividerEl) {
      this.perfDividerEl.hidden = !isAdmin;
      this.perfDividerEl.style.display = isAdmin ? '' : 'none';
    }

    if (!isAdmin && !isMock && this.automationStudio?.isOpen) {
      this.automationStudio.close();
    }
    if (!isAdmin && !isMock && this.systemMetricsPanel?.isOpen) {
      this.systemMetricsPanel.close();
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

  updateFrustumsButtonUI(mode = 'off') {
    if (!this.frustumsBtn) return;
    const normalized = mode === '3d' || mode === '2d' ? mode : 'off';
    const labelEl = this.frustumsBtn.querySelector('#frustums-text') || this.frustumsBtn.querySelector('.top-btn-label');

    this.frustumsBtn.dataset.coverageMode = normalized;
    this.frustumsBtn.classList.toggle('active', normalized !== 'off');
    this.frustumsBtn.classList.toggle('active-2d', normalized === '2d');
    this.frustumsBtn.setAttribute('aria-pressed', String(normalized !== 'off'));

    if (normalized === '3d') {
      if (labelEl) labelEl.textContent = 'Copertura 3D';
      this.frustumsBtn.title = 'Copertura telecamere 3D (clicca per vista 2D al suolo)';
      this.frustumsBtn.setAttribute('aria-label', 'Copertura telecamere 3D');
    } else if (normalized === '2d') {
      if (labelEl) labelEl.textContent = 'Copertura 2D';
      this.frustumsBtn.title = 'Copertura telecamere 2D al suolo (clicca per disattivare)';
      this.frustumsBtn.setAttribute('aria-label', 'Copertura telecamere 2D al suolo');
    } else {
      if (labelEl) labelEl.textContent = 'Copertura Camere';
      this.frustumsBtn.title = 'Copertura telecamere disattivata (clicca per vista 3D)';
      this.frustumsBtn.setAttribute('aria-label', 'Copertura telecamere disattivata');
    }
  }

  closeSettingsDropdown() {
    this.settingsDropdown?.classList.remove('open');
    this.container?.classList.remove('dropdown-open');
    this.settingsBtn?.classList.remove('active');
    this.settingsBtn?.setAttribute('aria-expanded', 'false');
  }

  bindEvents() {
    // Toggle Notte / Giorno
    this.nightBtn.addEventListener('click', () => {
      const isNight = !this.sceneManager.isNightMode;
      this.sceneManager.setNightMode(isNight);
      this.nightBtn.classList.toggle('active', isNight);
      this.nightBtn.setAttribute('aria-pressed', String(isNight));
      this.nightBtn.innerHTML = isNight
        ? `${icon('sun', { size: 15 })} <span class="top-btn-label" id="night-text">Giorno</span>`
        : `${icon('moon', { size: 15 })} <span class="top-btn-label" id="night-text">Notte</span>`;
    });

    // Toggle Frustum Telecamere (3 stati: off -> 3d -> 2d -> off)
    this.frustumsBtn.addEventListener('click', () => {
      const nextMode =
        typeof this.cameraProjector?.cycleFrustumMode === 'function'
          ? this.cameraProjector.cycleFrustumMode()
          : (this.cameraProjector?.toggleFrustums?.() ? '3d' : 'off');
      this.updateFrustumsButtonUI(nextMode);
    });

    // Menu Impostazioni a Tendina
    this.settingsBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      const willOpen = !this.settingsDropdown.classList.contains('open');
      this.settingsDropdown.classList.toggle('open', willOpen);
      this.container?.classList.toggle('dropdown-open', willOpen);
      this.settingsBtn.classList.toggle('active', willOpen);
      this.settingsBtn.setAttribute('aria-expanded', String(willOpen));
      if (willOpen && this.automationsBtn) {
        this.automationsBtn.classList.toggle('active', Boolean(this.automationStudio?.isOpen));
      }
      if (willOpen && this.calibBtn) {
        this.calibBtn.classList.toggle('active', Boolean(this.calibrationAssistant?.isOpen));
      }
      if (willOpen && this.metricsBtn) {
        this.metricsBtn.classList.toggle('active', Boolean(this.systemMetricsPanel?.isOpen));
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

    // Apertura Automation Studio 3D (sopra Calibra Cam)
    this.automationsBtn?.addEventListener('click', () => {
      this.closeSettingsDropdown();
      if (!this.haClient?.isAdmin && !this.haClient?.isMockMode) return;
      if (!this.automationStudio) return;
      if (this.automationStudio.isOpen) {
        this.automationStudio.close();
        this.automationsBtn.classList.remove('active');
        return;
      }
      this.deviceModals?.close();
      if (this.calibrationAssistant?.isOpen) {
        this.calibrationAssistant.close();
      }
      this.automationsBtn.classList.add('active');
      this.automationStudio.open();
    });

    // Apertura Calibrazione Ottica POV multi-camera (solo Admin)
    this.calibBtn?.addEventListener('click', () => {
      this.closeSettingsDropdown();
      if (!this.haClient?.isAdmin) return;
      if (!this.calibrationAssistant) return;
      if (this.calibrationAssistant.isOpen) {
        this.calibrationAssistant.close();
        this.calibBtn.classList.remove('active');
        return;
      }

      const targetCam = this._resolveCalibrationTargetCamera();
      const alreadyInTargetPov = this.cameraController?.activePovCameraName === targetCam;

      this.deviceModals?.close();
      if (window.innerWidth <= 1024) {
        this.setQuickNavCollapsed(true);
      }
      this.calibBtn.classList.add('active');

      const camNode = this.assetLoader?.cameras?.get?.(targetCam);
      if (camNode && this.cameraController && !alreadyInTargetPov) {
        this.cameraController.flyToCameraPOV(
          camNode,
          1.1,
          () => {
            this.calibrationAssistant.open(targetCam);
          },
          { forCalibration: true, cameraName: targetCam }
        );
      } else {
        this.calibrationAssistant.open(targetCam);
      }
    });

    // Apertura Pannello Prestazioni Server & FPS (sotto Calibra Cam)
    this.metricsBtn?.addEventListener('click', () => {
      this.closeSettingsDropdown();
      if (!this.haClient?.isAdmin && !this.haClient?.isMockMode) return;
      if (!this.systemMetricsPanel) return;
      if (this.systemMetricsPanel.isOpen) {
        this.systemMetricsPanel.close();
        this.metricsBtn.classList.remove('active');
        return;
      }
      this.deviceModals?.close();
      if (this.calibrationAssistant?.isOpen) {
        this.calibrationAssistant.close();
      }
      if (this.automationStudio?.isOpen) {
        this.automationStudio.close();
      }
      this.metricsBtn.classList.add('active');
      this.systemMetricsPanel.open();
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
      this.badgesBtn.setAttribute('aria-pressed', String(Boolean(isVisible)));
    });
  }

  _resolveCalibrationTargetCamera() {
    const activePov = this.cameraController?.activePovCameraName;
    if (activePov) {
      return activePov;
    }
    const openEntity = this.deviceModals?.currentEntityId;
    if (typeof openEntity === 'string' && openEntity.startsWith('camera.')) {
      const matched = this.deviceModals?.findMatchingBlenderCameraName?.(openEntity);
      if (matched) return matched;
    }
    const lastCalib = this.calibrationAssistant?.activeCameraName;
    if (lastCalib && (this.assetLoader?.cameras?.has?.(lastCalib) || this.assetLoader?.manifest?.cameras?.[lastCalib])) {
      return lastCalib;
    }
    const catalogFirst = this.cameraCatalog?.getCameras?.()?.[0]?.blenderCameraName;
    if (catalogFirst) return catalogFirst;
    return 'Cam_Carraio';
  }

  /**
   * Metodo mantenuto per retrocompatibilità dopo la migrazione delle viste
   * al nuovo FAB Material 3 in basso a destra (NavigationFabHub).
   */
  setQuickNavCollapsed(_collapsed) {}
}

