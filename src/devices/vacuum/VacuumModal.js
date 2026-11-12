/**
 * VacuumModal
 * 
 * Interfaccia grafica fedele alla card Home Assistant dell'Ecovacs Deebot X1 Turbo:
 * - Titolo grande con stato live ("Alla base", "In pulizia", "Ritorno alla base", "In pausa")
 * - Subheader con orario relativo e indicatore percentuale batteria con icona dinamica
 * - Illustrazione grafica vettoriale SVG del robot aspirapolvere e della dock
 * - Griglia comandi rapidi (Play, Pausa/Stop, Ritorno alla base, Localizza)
 * - Pillole di stato e impostazione rapida:
 *   • Velocità Ventola ("Fan speed": Silenzioso / Normale / Massima / Max+)
 *   • Mappa e Modalità ("In pulizia": Per area / Piano terra)
 * - Scheda "Live 3D & MQTT":
 *   • Telemetria in streaming continuo da MQTT (`homeassistant/deebot/pose`)
 *   • Offset live da base $(\Delta X, \Delta Z)$ e angolo di navigazione
 *   • Coordinate 3D assolute nel digital twin
 * - Scheda "Avanzate" (Flusso acqua mocio, Boost tappeti, Modalità avanzata, Rilocalizza)
 * - Scheda "Manutenzione" (Barre usura Spazzole, Filtro, Mocio, Sensori)
 * - Scheda "Statistiche" (Area pulita, Durata, Pulizie totali)
 */
export class VacuumModal {
  constructor(controller) {
    this.controller = controller;
    this.container = null;
    this.context = null;
    this.fanSpeedDropdownOpen = false;
    this.waterFlowDropdownOpen = false;
    this.activeTab = 'controls'; // 'controls' | 'telemetry' | 'consumables' | 'stats'
  }

  render(container, context = {}) {
    this.container = container;
    this.context = context;
    this.renderContent();
  }

  renderContent() {
    if (!this.container) return;

    const rawState = this.controller.getRawState().toLowerCase();
    const stateLabel = this.controller.getStateLabel();
    const battery = this.controller.getBattery();
    const fanSpeed = this.controller.getFanSpeed();
    const fanSpeedLabel = this.controller.getFanSpeedLabel();
    const waterFlow = this.controller.getWaterFlow();
    const activeMap = this.controller.getActiveMap();
    const areaCleaned = this.controller.getAreaCleaned();
    const duration = this.controller.getCleaningDuration();
    const totalArea = this.controller.getTotalAreaCleaned();
    const totalCleanings = this.controller.getTotalCleanings();
    const isMop = this.controller.isMopAttached();
    const carpetBoost = this.controller.isCarpetBoostOn();
    const advMode = this.controller.isAdvancedModeOn();
    const consumables = this.controller.getConsumables();
    const lastTelem = this.controller.lastTelemetry;
    const isMqttLive = this.controller.mqttConnected && (Date.now() - this.controller.lastMqttTimestamp < 6000);

    const isCleaning = rawState === 'cleaning';
    const isReturning = rawState === 'returning';
    const isPaused = rawState === 'paused';

    // Icona batteria dinamica
    let batteryColor = '#10b981'; // verde
    if (battery <= 20) batteryColor = '#ef4444'; // rosso
    else if (battery <= 50) batteryColor = '#f59e0b'; // giallo

    this.container.innerHTML = `
      <div class="deebot-card">
        <!-- 1. Header Card (Stato e Batteria) -->
        <div class="deebot-header-box">
          <div class="deebot-title-wrap">
            <h2 class="deebot-main-title">${stateLabel}</h2>
            <div class="deebot-subtitle">
              ${isCleaning ? 'Sessione di pulizia in corso' : (isReturning ? 'Rientro al dock' : 'Pronto per la pulizia')}
            </div>
          </div>
          <div class="deebot-battery-badge" title="Livello Batteria: ${battery}%">
            <span class="battery-pct">${battery}%</span>
            <div class="battery-icon-svg" style="color: ${batteryColor};">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="2" y="7" width="16" height="10" rx="2" ry="2"></rect>
                <line x1="22" y1="11" x2="22" y2="13"></line>
                <rect x="4" y="9" width="${Math.max(1, Math.round((battery / 100) * 12))}" height="6" fill="currentColor" stroke="none" rx="1"></rect>
              </svg>
            </div>
          </div>
        </div>

        <!-- 2. Hero Graphic Illustration (Robot & Base) -->
        <div class="deebot-hero-visual">
          <div class="deebot-circle-back ${isCleaning ? 'cleaning-glow' : (isReturning ? 'returning-glow' : '')}">
            <svg class="deebot-svg-art" viewBox="0 0 160 160" width="140" height="140">
              <!-- Cerchio base robot -->
              <circle cx="80" cy="74" r="54" fill="none" stroke="currentColor" stroke-width="2.5" class="robot-outline"></circle>
              <!-- Arco bumper superiore -->
              <path d="M38 68 A48 48 0 0 1 122 68" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" class="robot-bumper"></path>
              <!-- Torretta laser LiDAR centrale -->
              <circle cx="80" cy="68" r="14" fill="none" stroke="currentColor" stroke-width="2" class="robot-lidar"></circle>
              <circle cx="80" cy="68" r="6" fill="currentColor" class="robot-lidar-eye"></circle>
              <!-- Pulsante power / anello LED -->
              <circle cx="80" cy="98" r="4" fill="none" stroke="currentColor" stroke-width="2" class="robot-btn ${isCleaning ? 'glow-btn' : ''}"></circle>
              <!-- Dock / Stazione di ricarica inferiore -->
              <rect x="56" y="120" width="48" height="18" rx="6" fill="none" stroke="currentColor" stroke-width="2.5" class="robot-dock"></rect>
            </svg>
          </div>
        </div>

        <!-- 3. Controlli Rapidi (4 Pulsanti Quadrati con Icone SVG) -->
        <div class="deebot-actions-row">
          <!-- Play / Avvia Pulizia -->
          <button class="btn-deebot-action ${isCleaning ? 'active' : ''}" id="btn-vac-play" title="Avvia o riprendi pulizia">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="6 4 20 12 6 20 6 4"></polygon>
            </svg>
          </button>

          <!-- Pausa / Stop -->
          <button class="btn-deebot-action ${isPaused ? 'active' : ''}" id="btn-vac-pause" title="Metti in pausa">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="5" width="4" height="14" rx="1"></rect>
              <rect x="14" y="5" width="4" height="14" rx="1"></rect>
            </svg>
          </button>

          <!-- Ritorno alla base / Dock -->
          <button class="btn-deebot-action ${isReturning ? 'active' : ''}" id="btn-vac-dock" title="Ritorna alla stazione di ricarica">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
              <polyline points="9 22 9 12 15 12 15 22"></polyline>
              <polyline points="12 15 9 12 12 9"></polyline>
            </svg>
          </button>

          <!-- Localizza con segnale sonoro -->
          <button class="btn-deebot-action" id="btn-vac-locate" title="Emetti suono di localizzazione">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
              <circle cx="12" cy="10" r="3" fill="currentColor"></circle>
            </svg>
          </button>
        </div>

        <!-- 4. Pillole di Stato & Regolazione Rapida (Fan speed + Modalità) -->
        <div class="deebot-pills-row">
          <!-- Fan Speed Pill -->
          <div class="deebot-pill-dropdown-wrap">
            <button class="deebot-pill-btn" id="btn-fan-speed-pill" title="Modifica velocità aspirazione">
              <div class="pill-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 12c-2-2-2-5 0-7s5-2 7 0-2 5-7 7z"></path>
                  <path d="M12 12c2 2 5 2 7 0s2-5 0-7-5 2-7 7z"></path>
                  <path d="M12 12c-2 2-2 5 0 7s5 2 7 0-2-5-7-7z"></path>
                  <path d="M12 12c2-2 5-2 7 0s2 5 0 7-5-2-7-7z"></path>
                </svg>
              </div>
              <div class="pill-text-block">
                <span class="pill-label">Fan speed</span>
                <span class="pill-value">${fanSpeedLabel}</span>
              </div>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="pill-chevron">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
            </button>

            <!-- Menu a tendina velocità ventola -->
            <div class="deebot-dropdown-menu ${this.fanSpeedDropdownOpen ? 'open' : ''}" id="menu-fan-speed">
              <div class="dropdown-item ${fanSpeed === 'quiet' ? 'selected' : ''}" data-speed="quiet">
                <span>Silenzioso</span>
                ${fanSpeed === 'quiet' ? '<span class="check-icon">✓</span>' : ''}
              </div>
              <div class="dropdown-item ${fanSpeed === 'normal' ? 'selected' : ''}" data-speed="normal">
                <span>Normale</span>
                ${fanSpeed === 'normal' ? '<span class="check-icon">✓</span>' : ''}
              </div>
              <div class="dropdown-item ${fanSpeed === 'max' ? 'selected' : ''}" data-speed="max">
                <span>Massima</span>
                ${fanSpeed === 'max' ? '<span class="check-icon">✓</span>' : ''}
              </div>
              <div class="dropdown-item ${fanSpeed === 'max_plus' ? 'selected' : ''}" data-speed="max_plus">
                <span>Max+ (Turbo)</span>
                ${fanSpeed === 'max_plus' ? '<span class="check-icon">✓</span>' : ''}
              </div>
            </div>
          </div>

          <!-- Mappa & Modalità Pill -->
          <div class="deebot-pill-btn" id="btn-mode-pill">
            <div class="pill-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="7" height="7"></rect>
                <rect x="14" y="3" width="7" height="7"></rect>
                <rect x="14" y="14" width="7" height="7"></rect>
                <rect x="3" y="14" width="7" height="7"></rect>
              </svg>
            </div>
            <div class="pill-text-block">
              <span class="pill-label">In pulizia</span>
              <span class="pill-value">${activeMap}</span>
            </div>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="pill-chevron">
              <polyline points="9 18 15 12 9 6"></polyline>
            </svg>
          </div>
        </div>

        <!-- 5. Navigazione Schede (Avanzate, Live MQTT, Manutenzione, Statistiche) -->
        <div class="deebot-tabs-bar">
          <button class="deebot-tab-btn ${this.activeTab === 'controls' ? 'active' : ''}" data-tab="controls">
            Avanzate
          </button>
          <button class="deebot-tab-btn ${this.activeTab === 'telemetry' ? 'active' : ''}" data-tab="telemetry">
            Live 3D & MQTT
          </button>
          <button class="deebot-tab-btn ${this.activeTab === 'consumables' ? 'active' : ''}" data-tab="consumables">
            Manutenzione
          </button>
          <button class="deebot-tab-btn ${this.activeTab === 'stats' ? 'active' : ''}" data-tab="stats">
            Statistiche
          </button>
        </div>

        <!-- TAB CONTENT: AVANZATE -->
        <div class="deebot-tab-pane ${this.activeTab === 'controls' ? 'active' : ''}">
          <!-- Flusso d'Acqua Mocio -->
          <div class="deebot-feature-row">
            <div class="feature-label-group">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2">
                <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"></path>
              </svg>
              <div>
                <div class="feature-title">Flusso d'Acqua Mocio</div>
                <div class="feature-sub">Stato: ${isMop ? 'Mocio montato' : 'Mocio non rilevato'}</div>
              </div>
            </div>
            <div class="water-flow-selector">
              <button class="btn-flow-chip ${waterFlow === 'low' ? 'active' : ''}" data-flow="low">Basso</button>
              <button class="btn-flow-chip ${waterFlow === 'medium' ? 'active' : ''}" data-flow="medium">Medio</button>
              <button class="btn-flow-chip ${waterFlow === 'high' ? 'active' : ''}" data-flow="high">Alto</button>
            </div>
          </div>

          <!-- Boost Tappeti -->
          <div class="deebot-feature-row">
            <div class="feature-label-group">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#a855f7" stroke-width="2">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path>
              </svg>
              <div>
                <div class="feature-title">Potenziamento Tappeto</div>
                <div class="feature-sub">Aumenta l'aspirazione su moquette</div>
              </div>
            </div>
            <label class="custom-ha-switch">
              <input type="checkbox" id="chk-carpet-boost" ${carpetBoost ? 'checked' : ''}>
              <span class="switch-track"><span class="switch-thumb"></span></span>
            </label>
          </div>

          <!-- Modalità Avanzata -->
          <div class="deebot-feature-row">
            <div class="feature-label-group">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
              <div>
                <div class="feature-title">Modalità Avanzata</div>
                <div class="feature-sub">Mappe salvate e pulizia per area</div>
              </div>
            </div>
            <label class="custom-ha-switch">
              <input type="checkbox" id="chk-adv-mode" ${advMode ? 'checked' : ''}>
              <span class="switch-track"><span class="switch-thumb"></span></span>
            </label>
          </div>

          <!-- Pulsante Rilocalizza & Inquadra 3D -->
          <div class="deebot-footer-actions">
            <button class="btn-deebot-secondary" id="btn-vac-relocate">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10"></polyline>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
              </svg>
              <span>Rilocalizza</span>
            </button>
            <button class="btn-deebot-secondary highlight" id="btn-vac-fly">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon>
              </svg>
              <span>Inquadra nel 3D</span>
            </button>
          </div>
        </div>

        <!-- TAB CONTENT: LIVE TELEMETRIA 3D & MQTT -->
        <div class="deebot-tab-pane ${this.activeTab === 'telemetry' ? 'active' : ''}">
          <div class="deebot-telemetry-box">
            <div class="telemetry-status-header">
              <div class="mqtt-indicator-pill ${isMqttLive || lastTelem?.simulated ? 'online' : 'waiting'}">
                <span class="mqtt-pulse-dot"></span>
                <span id="telem-status-label">${isMqttLive ? 'MQTT Live Streaming' : (lastTelem?.simulated ? 'Simulazione 3D Demo' : 'MQTT Standby')}</span>
              </div>
              <span class="telemetry-topic-tag">${this.controller.mqttTopic}</span>
            </div>

            <!-- Griglia Coordinate Real-Time -->
            <div class="telemetry-coords-grid">
              <div class="telemetry-card">
                <span class="coord-label">&Delta;X dalla Base</span>
                <span class="coord-val" id="telem-dx">${lastTelem?.deltaX_m !== undefined ? (lastTelem.deltaX_m >= 0 ? '+' : '') + lastTelem.deltaX_m + ' m' : '0.00 m'}</span>
                <span class="coord-sub">Spostamento ovest</span>
              </div>
              <div class="telemetry-card">
                <span class="coord-label">&Delta;Z dalla Base</span>
                <span class="coord-val" id="telem-dz">${lastTelem?.deltaZ_m !== undefined ? (lastTelem.deltaZ_m >= 0 ? '+' : '') + lastTelem.deltaZ_m + ' m' : '0.00 m'}</span>
                <span class="coord-sub">Spostamento sud</span>
              </div>
              <div class="telemetry-card">
                <span class="coord-label">Orientamento Yaw</span>
                <span class="coord-val" id="telem-angle">${lastTelem?.angleDeg !== undefined ? lastTelem.angleDeg + '&deg;' : '0&deg;'}</span>
                <span class="coord-sub">Rotazione LiDAR</span>
              </div>
              <div class="telemetry-card">
                <span class="coord-label">Posizione 3D</span>
                <span class="coord-val" id="telem-3d-pos">${lastTelem?.targetX ? `${lastTelem.targetX}, ${lastTelem.targetZ}` : '13.63, 1.65'}</span>
                <span class="coord-sub">World Coordinates</span>
              </div>
            </div>

            <!-- Selettore Rapido di Scala & Calibrazione -->
            <div class="telemetry-calibration-bar" style="margin-top: 10px; padding: 8px 10px; background: rgba(255,255,255,0.03); border-radius: 8px; border: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: space-between;">
              <span style="font-size: 11px; color: var(--ha-subtext);">Scala Calibrazione:</span>
              <div style="display: flex; gap: 6px;">
                <button class="btn-deebot-chip ${this.controller.calibration.scale === 1.0 ? 'active' : ''}" data-calib-scale="1.0" title="Scala reale 1:1 metrica">1.0x (Reale 1:1)</button>
                <button class="btn-deebot-chip ${this.controller.calibration.scale === 0.9 ? 'active' : ''}" data-calib-scale="0.9" title="Riduzione 10%">0.9x</button>
                <button class="btn-deebot-chip ${this.controller.calibration.scale === 0.75 ? 'active' : ''}" data-calib-scale="0.75">0.75x</button>
                <button class="btn-deebot-chip ${this.controller.calibration.scale === 0.5 ? 'active' : ''}" data-calib-scale="0.5">0.5x</button>
              </div>
            </div>

            <!-- Inquadratura Dinamica Follow Robot -->
            <button class="btn-deebot-secondary highlight" id="btn-telem-follow" style="width: 100%; margin-top: 8px;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon>
              </svg>
              <span>Segui Deebot nel 3D in Tempo Reale</span>
            </button>
          </div>
        </div>

        <!-- TAB CONTENT: CONSUMABILI / USURA -->
        <div class="deebot-tab-pane ${this.activeTab === 'consumables' ? 'active' : ''}">
          <div class="consumables-grid">
            ${this.renderConsumableBar('Spazzola Principale', consumables.mainBrush, 'Durata residua')}
            ${this.renderConsumableBar('Spazzola Laterale', consumables.sideBrush, 'Durata residua')}
            ${this.renderConsumableBar('Filtro Polvere', consumables.filter, 'Durata residua')}
            ${this.renderConsumableBar('Mocio Rotondo', consumables.roundMop, 'Durata residua')}
            ${this.renderConsumableBar('Cura Sensori / Torretta', consumables.unitCare, 'Pulizia ottiche')}
          </div>
        </div>

        <!-- TAB CONTENT: STATISTICHE -->
        <div class="deebot-tab-pane ${this.activeTab === 'stats' ? 'active' : ''}">
          <div class="deebot-stats-grid">
            <div class="deebot-stat-card">
              <span class="stat-num">${areaCleaned}</span>
              <span class="stat-unit">m²</span>
              <span class="stat-lbl">Ultima Area Pulita</span>
            </div>
            <div class="deebot-stat-card">
              <span class="stat-num">${duration}</span>
              <span class="stat-unit">min</span>
              <span class="stat-lbl">Durata Ultimo Ciclo</span>
            </div>
            <div class="deebot-stat-card">
              <span class="stat-num">${totalArea.toLocaleString('it-IT')}</span>
              <span class="stat-unit">m²</span>
              <span class="stat-lbl">Area Totale Storica</span>
            </div>
            <div class="deebot-stat-card">
              <span class="stat-num">${totalCleanings}</span>
              <span class="stat-unit">volte</span>
              <span class="stat-lbl">Cicli di Pulizia Totali</span>
            </div>
          </div>
        </div>

      </div>
    `;

    this.bindEvents();
  }

  renderConsumableBar(title, pct, sub) {
    let colorClass = 'bar-good';
    if (pct < 15) colorClass = 'bar-critical';
    else if (pct < 40) colorClass = 'bar-warning';

    return `
      <div class="consumable-item">
        <div class="consumable-head">
          <div>
            <span class="consumable-title">${title}</span>
            <span class="consumable-sub">${sub}</span>
          </div>
          <span class="consumable-pct ${colorClass}">${pct}%</span>
        </div>
        <div class="consumable-track">
          <div class="consumable-fill ${colorClass}" style="width: ${pct}%;"></div>
        </div>
      </div>
    `;
  }

  bindEvents() {
    if (!this.container) return;

    // Azioni Primarie (Play, Pausa, Dock, Locate)
    this.container.querySelector('#btn-vac-play')?.addEventListener('click', () => {
      this.controller.start();
    });
    this.container.querySelector('#btn-vac-pause')?.addEventListener('click', () => {
      this.controller.pause();
    });
    this.container.querySelector('#btn-vac-dock')?.addEventListener('click', () => {
      this.controller.returnToBase();
    });
    this.container.querySelector('#btn-vac-locate')?.addEventListener('click', () => {
      this.controller.locate();
    });

    // Toggle Dropdown Velocità Ventola
    const btnFan = this.container.querySelector('#btn-fan-speed-pill');
    btnFan?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.fanSpeedDropdownOpen = !this.fanSpeedDropdownOpen;
      const menu = this.container.querySelector('#menu-fan-speed');
      if (menu) menu.classList.toggle('open', this.fanSpeedDropdownOpen);
    });

    // Selezione Velocità Ventola
    this.container.querySelectorAll('[data-speed]').forEach((el) => {
      el.addEventListener('click', () => {
        const speed = el.dataset.speed;
        this.controller.setFanSpeed(speed);
        this.fanSpeedDropdownOpen = false;
        this.renderContent();
      });
    });

    // Selezione Flusso d'Acqua
    this.container.querySelectorAll('[data-flow]').forEach((el) => {
      el.addEventListener('click', () => {
        const flow = el.dataset.flow;
        this.controller.setWaterFlow(flow);
        this.renderContent();
      });
    });

    // Switch Tappeti & Modalità Avanzata
    this.container.querySelector('#chk-carpet-boost')?.addEventListener('change', () => {
      this.controller.toggleCarpetBoost();
    });
    this.container.querySelector('#chk-adv-mode')?.addEventListener('change', () => {
      this.controller.toggleAdvancedMode();
    });

    // Pulsanti Secondari
    this.container.querySelector('#btn-vac-relocate')?.addEventListener('click', () => {
      this.controller.relocate();
    });
    this.container.querySelector('#btn-vac-fly')?.addEventListener('click', () => {
      this.controller.zoomToRobot();
    });
    this.container.querySelector('#btn-telem-follow')?.addEventListener('click', () => {
      this.controller.zoomToRobot();
    });

    // Calibrazione Scala Mappatura
    this.container.querySelectorAll('[data-calib-scale]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const scale = parseFloat(btn.dataset.calibScale);
        this.controller.setCalibrationScale(scale);
        this.renderContent();
      });
    });

    // Navigazione Schede
    this.container.querySelectorAll('[data-tab]').forEach((tabBtn) => {
      tabBtn.addEventListener('click', () => {
        this.activeTab = tabBtn.dataset.tab;
        this.renderContent();
      });
    });

    // Chiudi dropdown al click esterno
    const handleOutsideClick = (e) => {
      if (this.fanSpeedDropdownOpen && !e.target.closest('#btn-fan-speed-pill') && !e.target.closest('#menu-fan-speed')) {
        this.fanSpeedDropdownOpen = false;
        const menu = this.container?.querySelector('#menu-fan-speed');
        if (menu) menu.classList.remove('open');
      }
    };
    document.addEventListener('click', handleOutsideClick, { once: true });
  }

  updateLive() {
    this.renderContent();
  }

  updateTelemetry(telem) {
    if (!this.container) return;

    // Aggiornamento selettivo leggero dei valori testuali (zero flickers)
    const dxEl = this.container.querySelector('#telem-dx');
    const dzEl = this.container.querySelector('#telem-dz');
    const angleEl = this.container.querySelector('#telem-angle');
    const pos3dEl = this.container.querySelector('#telem-3d-pos');
    const statusLabel = this.container.querySelector('#telem-status-label');
    const indicatorPill = this.container.querySelector('.mqtt-indicator-pill');

    if (dxEl && telem.deltaX_m !== undefined) {
      dxEl.textContent = (telem.deltaX_m >= 0 ? '+' : '') + telem.deltaX_m + ' m';
    }
    if (dzEl && telem.deltaZ_m !== undefined) {
      dzEl.textContent = (telem.deltaZ_m >= 0 ? '+' : '') + telem.deltaZ_m + ' m';
    }
    if (angleEl && telem.angleDeg !== undefined) {
      angleEl.innerHTML = telem.angleDeg + '&deg;';
    }
    if (pos3dEl && telem.targetX && telem.targetZ) {
      pos3dEl.textContent = `${telem.targetX}, ${telem.targetZ}`;
    }
    if (indicatorPill && statusLabel) {
      indicatorPill.className = 'mqtt-indicator-pill online';
      statusLabel.textContent = telem.simulated ? 'Simulazione 3D Demo' : 'MQTT Live Streaming';
    }
  }
}
