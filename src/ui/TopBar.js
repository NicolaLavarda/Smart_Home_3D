export class TopBar {
  constructor(domContainer, {
    sceneManager,
    cameraController,
    cameraProjector,
    interactionManager,
    haClient,
    calibrationAssistant = null,
    assetLoader = null,
  }) {
    this.container = domContainer;
    this.sceneManager = sceneManager;
    this.cameraController = cameraController;
    this.cameraProjector = cameraProjector;
    this.interactionManager = interactionManager;
    this.haClient = haClient;
    this.calibrationAssistant = calibrationAssistant;
    this.assetLoader = assetLoader;

    this.initUI();
    this.bindEvents();
  }

  initUI() {
    this.container.innerHTML = `
      <div class="top-bar-left">
        <div class="logo-badge">
          <div class="logo-icon">3D</div>
          <div>
            <div class="logo-title">SMART HOME DIGITAL TWIN</div>
            <div class="logo-subtitle">Three.js • SSoT • Spatial CV (x,y,z,t)</div>
          </div>
        </div>

        <div class="ha-status-badge" id="ha-badge">
          <span class="ha-dot mock" id="ha-dot"></span>
          <span id="ha-text">Inizializzazione...</span>
        </div>
      </div>

      <div class="top-bar-controls">
        <button class="btn-icon-text" id="btn-toggle-night" title="Alterna modalità Giorno e Notte">
          🌙 <span id="night-text">Notte</span>
        </button>

        <button class="btn-icon-text" id="btn-toggle-frustums" title="Mostra/Nascondi coni visivi telecamere">
          📹 <span>Copertura Camere</span>
        </button>

        <button class="btn-icon-text" id="btn-open-cam-calib" title="Apri calibrazione ottica POV su Cam_Carraio">
          📐 <span>Calibra Cam</span>
        </button>

        <button class="btn-icon-text" id="btn-toggle-badges" title="Mostra/Nascondi badge dei dispositivi">
          🏷️ <span>Badge Dispositivi</span>
        </button>

        <div style="position: relative;">
          <button class="btn-icon-text" id="btn-view-menu">
            🧭 <span>Viste ▾</span>
          </button>
        </div>
      </div>
    `;

    this.haDot = this.container.querySelector('#ha-dot');
    this.haText = this.container.querySelector('#ha-text');
    this.nightBtn = this.container.querySelector('#btn-toggle-night');
    this.nightText = this.container.querySelector('#night-text');
    this.frustumsBtn = this.container.querySelector('#btn-toggle-frustums');
    this.calibBtn = this.container.querySelector('#btn-open-cam-calib');
    this.badgesBtn = this.container.querySelector('#btn-toggle-badges');

    // Ascolta lo stato di HA
    this.haClient.onStatusChange((status, details) => {
      this.haDot.className = `ha-dot ${status}`;
      this.haText.textContent = details || status.toUpperCase();
    });
  }

  bindEvents() {
    // Toggle Notte / Giorno
    this.nightBtn.addEventListener('click', () => {
      const isNight = !this.sceneManager.isNightMode;
      this.sceneManager.setNightMode(isNight);
      this.nightBtn.classList.toggle('active', isNight);
      this.nightText.textContent = isNight ? 'Giorno' : 'Notte';
      this.nightBtn.innerHTML = isNight ? '☀️ <span>Giorno</span>' : '🌙 <span>Notte</span>';
    });

    // Toggle Frustum Telecamere
    this.frustumsBtn.addEventListener('click', () => {
      const isVisible = this.cameraProjector.toggleFrustums();
      this.frustumsBtn.classList.toggle('active', isVisible);
    });

    // Apertura Calibrazione Ottica POV Cam_Carraio
    this.calibBtn?.addEventListener('click', () => {
      if (!this.calibrationAssistant) return;
      if (this.calibrationAssistant.isOpen) {
        this.calibrationAssistant.close();
        this.calibBtn.classList.remove('active');
        return;
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
      <div class="side-header">Viste Rapide</div>
      <button class="quicknav-btn active" data-preset="overview">🌐 Panoramica</button>
      <button class="quicknav-btn" data-preset="carraio_cam">📹 POV Telecamera Carraio</button>
      <button class="quicknav-btn" data-preset="gate">🚪 Cancello & Accessi</button>
      <button class="quicknav-btn" data-preset="garden">🌳 Giardino & Lampioncini</button>
      <button class="quicknav-btn" data-preset="irrigation_area1">💧 Impianto Irrigazione</button>
      <button class="quicknav-btn" data-preset="living">🛋️ Salotto</button>
      <button class="quicknav-btn" data-preset="dining">🍽️ Sala da pranzo</button>
      <button class="quicknav-btn" data-preset="kitchen">🍳 Cucina</button>
      <button class="quicknav-btn" data-preset="laundry">🧺 Impianto Termico</button>
      <button class="quicknav-btn" data-preset="topdown">📐 Pianta Zenitale</button>
    `;
    document.querySelector('.ui-layer').appendChild(quicknav);

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
}

