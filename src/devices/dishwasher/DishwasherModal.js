/**
 * DishwasherModal
 * 
 * Interfaccia grafica completa e rifinita per la Lavastoviglie Smart:
 * - Card hero con stato di funzionamento live, orario di fine stimato e barra di avanzamento
 * - Pulsanti di alimentazione (Accendi/Spegni), Avvio Programma e Stop
 * - Selezione rapida dei programmi (Auto, Eco, Intensivo, Quick, Silenzioso, Bicchieri)
 * - Tasti di commutazione opzioni (Asciugatura Extra, Mezzo Carico, Igiene+, Velocità+, Silence)
 * - Indicatori di diagnostica e consumabili (Sale, Brillantante, Sensore Porta)
 * 
 * 100% icone vettoriali SVG pulite, zero emoji, stile glassmorphic coordinato alla Smart TV.
 */
export class DishwasherModal {
  constructor(controller) {
    this.controller = controller;
    this.container = null;
  }

  render(container) {
    this.container = container;
    const isPoweredOn = this.controller.isPoweredOn();
    const status = this.controller.getStatus();
    const program = this.controller.getProgram();
    const endTime = this.controller.getEndTime();
    const progress = this.controller.getProgress();
    const isDoorOpen = this.controller.isDoorOpen();
    const isSaltLow = this.controller.isSaltLow();
    const isRinseAidLow = this.controller.isRinseAidLow();

    const stLower = status.toLowerCase();
    const isRunning = stLower === 'running' || stLower === 'in funzione' || progress > 0;
    const isFinished = stLower === 'finito' || stLower === 'completed';

    // Status badge style
    let badgeClass = 'status-ready';
    let badgeText = status.toUpperCase();
    if (isRunning) {
      badgeClass = 'status-running';
      badgeText = 'IN FUNZIONE';
    } else if (isFinished) {
      badgeClass = 'status-finished';
      badgeText = 'LAVAGGIO COMPLETATO';
    } else if (!isPoweredOn || stLower === 'off' || stLower === 'non disponibile') {
      badgeClass = 'status-off';
      badgeText = 'SPENTA';
    }

    container.innerHTML = `
      <!-- Hero Status Card -->
      <div class="dishwasher-hero-card">
        <div class="hero-top-row">
          <div class="dishwasher-badge">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2"></rect>
              <line x1="3" y1="8" x2="21" y2="8"></line>
              <circle cx="7" cy="5.5" r="1" fill="currentColor"></circle>
              <circle cx="10" cy="5.5" r="1" fill="currentColor"></circle>
              <circle cx="12" cy="14" r="3"></circle>
              <path d="M12 11v-1"></path>
              <path d="M12 18v-1"></path>
            </svg>
            <span>Lavastoviglie</span>
          </div>

          <div class="ha-status-badge ${badgeClass}">
            <span class="ha-dot ${isRunning ? 'online' : (isPoweredOn ? 'online' : 'offline')}"></span>
            <span>${badgeText}</span>
          </div>
        </div>

        <div class="hero-program-box">
          <div class="hero-program-title">${program}</div>
          <div class="hero-meta-row">
            <span class="meta-item">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
              <span>Fine: <strong>${endTime}</strong></span>
            </span>
            <span class="meta-item ${isDoorOpen ? 'alert' : ''}">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18M6 21V3h12v18M14 12v.01"></path></svg>
              <span>Porta: <strong>${isDoorOpen ? 'Aperta' : 'Chiusa'}</strong></span>
            </span>
          </div>
        </div>

        <!-- Barra di Avanzamento -->
        <div class="hero-progress-section">
          <div class="progress-labels">
            <span>Avanzamento Ciclo</span>
            <span class="progress-pct">${progress}%</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill ${isRunning ? 'active' : ''}" style="width: ${progress}%;"></div>
          </div>
        </div>
      </div>

      <!-- Azioni Primarie (Power, Avvio, Stop) -->
      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 8px;">
        <label>Controlli Rapidi</label>
        <div class="dishwasher-actions-grid">
          <!-- Power Button -->
          <button class="btn-dish-action ${isPoweredOn ? 'btn-power-off' : 'btn-power-on'}" id="btn-dish-power">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path>
              <line x1="12" y1="2" x2="12" y2="12"></line>
            </svg>
            <span>${isPoweredOn ? 'Spegni' : 'Accendi'}</span>
          </button>

          <!-- Start Program Button -->
          <button class="btn-dish-action btn-start-prog" id="btn-dish-start">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="5 3 19 12 5 21 5 3"></polygon>
            </svg>
            <span>Avvia</span>
          </button>

          <!-- Stop Program Button -->
          <button class="btn-dish-action btn-stop-prog" id="btn-dish-stop">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
              <rect x="5" y="5" width="14" height="14" rx="2"></rect>
            </svg>
            <span>Ferma</span>
          </button>
        </div>
      </div>

      <!-- Selezione Programma -->
      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 8px;">
        <label>Selezione Programma di Lavaggio</label>
        <div class="programs-chips-grid">
          ${this.renderProgramChip('Auto 45°-65°C', 'Dishcare.Dishwasher.Program.Auto2', program)}
          ${this.renderProgramChip('Eco 50°C', 'Dishcare.Dishwasher.Program.Eco50', program)}
          ${this.renderProgramChip('Intensivo 70°C', 'Dishcare.Dishwasher.Program.Intensiv70', program)}
          ${this.renderProgramChip('1h Quick 65°C', 'Dishcare.Dishwasher.Program.Quick65', program)}
          ${this.renderProgramChip('Silenzioso 50°C', 'Dishcare.Dishwasher.Program.NightWash', program)}
          ${this.renderProgramChip('Bicchieri 40°C', 'Dishcare.Dishwasher.Program.Glass40', program)}
        </div>
      </div>

      <!-- Opzioni Speciali e Funzioni Aggiuntive -->
      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 8px;">
        <label>Opzioni e Funzioni Speciali</label>
        <div class="options-toggle-grid">
          ${this.renderOptionButton(
            'switch.lavastoviglie_extra_dry',
            'Asciugatura Extra',
            `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2"></path></svg>`
          )}
          ${this.renderOptionButton(
            'switch.lavastoviglie_half_load',
            'Mezzo Carico',
            `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a10 10 0 0 1 0 20Z" fill="currentColor"></path></svg>`
          )}
          ${this.renderOptionButton(
            'switch.lavastoviglie_hygiene',
            'Igiene+',
            `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><line x1="12" y1="8" x2="12" y2="14"></line><line x1="9" y1="11" x2="15" y2="11"></line></svg>`
          )}
          ${this.renderOptionButton(
            'switch.lavastoviglie_vario_speed',
            'Velocità+ (Vario)',
            `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>`
          )}
          ${this.renderOptionButton(
            'switch.lavastoviglie_silence_on_demand',
            'Silence on Demand',
            `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"></path><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>`
          )}
        </div>
      </div>

      <!-- Diagnostica e Consumabili -->
      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 8px;">
        <label>Stato Consumabili e Sensori</label>
        <div class="consumables-row">
          <div class="consumable-pill ${isSaltLow ? 'warning' : 'ok'}">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="9"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            <div>
              <div class="consumable-label">Sale</div>
              <div class="consumable-val">${isSaltLow ? 'Da Ricaricare' : 'Livello OK'}</div>
            </div>
          </div>

          <div class="consumable-pill ${isRinseAidLow ? 'warning' : 'ok'}">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"></path>
            </svg>
            <div>
              <div class="consumable-label">Brillantante</div>
              <div class="consumable-val">${isRinseAidLow ? 'Da Ricaricare' : 'Livello OK'}</div>
            </div>
          </div>

          <div class="consumable-pill ${isDoorOpen ? 'info' : 'ok'}" id="btn-toggle-door-modal" style="cursor: pointer;" title="Clicca per testare l'apertura/chiusura della porta 3D (40°)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 21h18M6 21V3h12v18M14 12v.01"></path>
            </svg>
            <div>
              <div class="consumable-label">Sportello (Porta)</div>
              <div class="consumable-val">${isDoorOpen ? 'Aperto (40°)' : 'Chiuso'}</div>
            </div>
          </div>
        </div>
      </div>
    `;

    this.bindEvents(container);
  }

  renderProgramChip(label, optionValue, currentProgram) {
    const isActive = currentProgram.toLowerCase().includes(label.toLowerCase().slice(0, 4));
    return `
      <button class="program-chip ${isActive ? 'active' : ''}" data-program-option="${optionValue}">
        <span>${label}</span>
      </button>
    `;
  }

  renderOptionButton(entityId, label, svgIcon) {
    const isActive = this.controller.isOptionActive(entityId);
    return `
      <button class="option-btn ${isActive ? 'active' : ''}" data-entity-id="${entityId}">
        <span class="option-icon">${svgIcon}</span>
        <span class="option-label">${label}</span>
        <span class="option-indicator ${isActive ? 'on' : 'off'}"></span>
      </button>
    `;
  }

  bindEvents(container) {
    // 1. Alimentazione
    const powerBtn = container.querySelector('#btn-dish-power');
    if (powerBtn) {
      powerBtn.addEventListener('click', () => {
        this.controller.togglePower();
        setTimeout(() => this.render(container), 250);
      });
    }

    // 2. Avvio Programma
    const startBtn = container.querySelector('#btn-dish-start');
    if (startBtn) {
      startBtn.addEventListener('click', () => {
        this.controller.startProgram();
        setTimeout(() => this.render(container), 350);
      });
    }

    // 3. Stop Programma
    const stopBtn = container.querySelector('#btn-dish-stop');
    if (stopBtn) {
      stopBtn.addEventListener('click', () => {
        this.controller.stopProgram();
        setTimeout(() => this.render(container), 250);
      });
    }

    // 4. Selezione Programma
    container.querySelectorAll('.program-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const option = chip.dataset.programOption;
        this.controller.selectProgram(option);
        setTimeout(() => this.render(container), 250);
      });
    });

    // 5. Opzioni Speciali
    container.querySelectorAll('.option-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const entityId = btn.dataset.entityId;
        this.controller.toggleOption(entityId);
        setTimeout(() => this.render(container), 200);
      });
    });

    // 6. Test Sportello / Porta (40°)
    const doorBtn = container.querySelector('#btn-toggle-door-modal');
    if (doorBtn) {
      doorBtn.addEventListener('click', () => {
        this.controller.toggleDoor();
        setTimeout(() => this.render(container), 150);
      });
    }
  }

  updateLive() {
    if (this.container) {
      this.render(this.container);
    }
  }
}

