/**
 * IrrigationModal
 * 
 * Interfaccia grafica di classe elevata per l'Impianto di Irrigazione Smart.
 * Ispirata al design system della Smart TV e della Lavastoviglie, riproduce
 * e potenzia le funzionalità della card Home Assistant personalizzata dell'utente:
 * 
 * - Hero Status Card con metriche live (Aree attive, Gettini in funzione, Durata ciclo programmato)
 * - Pulsante Principale Hero "Avvia Ciclo" / "Ferma Irrigazione" (`input_boolean.irrigazione_attiva`)
 * - Card di zona per Area 1, Area 2, Area 3 con:
 *   • Toggle di abilitazione nel ciclo (`input_boolean.area_1/2/3`)
 *   • Regolazione durata in minuti con stepper `+` / `-` e input numerico (`input_number.tempo_area_1/2/3`)
 *   • Controllo manuale diretto della valvola/switch (`switch.smart_switch_area1/2/3`)
 *   • Inquadratura telecamera Three.js dedicata per zoomare istantaneamente sui gettini
 * - Scorciatoie di navigazione 3D (Pianta Zenitale, Panoramica Giardino)
 * 
 * 100% SVG vettoriale pulito, zero emoji, stile glassmorphic coordinato.
 */
export class IrrigationModal {
  constructor(controller) {
    this.controller = controller;
    this.container = null;
    this.context = null;
  }

  render(container, context = {}) {
    this.container = container;
    this.context = context;

    const isCycleActive = this.controller.isCycleActive();
    const area1Enabled = this.controller.isAreaEnabled(1);
    const area2Enabled = this.controller.isAreaEnabled(2);
    const area3Enabled = this.controller.isAreaEnabled(3);

    const time1 = this.controller.getAreaTime(1);
    const time2 = this.controller.getAreaTime(2);
    const time3 = this.controller.getAreaTime(3);

    const valve1 = this.controller.isAreaValveOn(1);
    const valve2 = this.controller.isAreaValveOn(2);
    const valve3 = this.controller.isAreaValveOn(3);

    const anyValveOn = valve1 || valve2 || valve3;
    const enabledCount = (area1Enabled ? 1 : 0) + (area2Enabled ? 1 : 0) + (area3Enabled ? 1 : 0);
    const totalMinutes = this.controller.getTotalDurationMinutes();

    // Stato complessivo Hero
    let statusClass = 'status-off';
    let statusText = 'IMPIANTO A RIPOSO';
    if (isCycleActive) {
      statusClass = 'status-running';
      statusText = 'CICLO PROGRAMMATO ATTIVO';
    } else if (anyValveOn) {
      statusClass = 'status-running';
      statusText = 'IRRIGAZIONE MANUALE ATTIVA';
    }

    container.innerHTML = `
      <!-- Hero Status Card -->
      <div class="irrigation-hero-card">
        <div class="hero-top-row">
          <div class="irrigation-badge">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"></path>
            </svg>
            <span>Controllo Irrigazione</span>
          </div>

          <div class="ha-status-badge ${statusClass}">
            <span class="ha-dot ${anyValveOn || isCycleActive ? 'online' : 'offline'}"></span>
            <span>${statusText}</span>
          </div>
        </div>

        <div class="irrigation-stats-grid">
          <div class="irrigation-stat-box">
            <span class="stat-label">Aree Abilitate</span>
            <span class="stat-value"><strong>${enabledCount}</strong> / 3</span>
          </div>
          <div class="irrigation-stat-box">
            <span class="stat-label">Durata Totale</span>
            <span class="stat-value"><strong>${totalMinutes}</strong> min</span>
          </div>
        </div>

        ${anyValveOn || isCycleActive ? `
          <div class="irrigation-water-anim">
            <div class="water-pulse-dot"></div>
            <div class="water-pulse-dot delay"></div>
            <span>Irrigazione in corso</span>
          </div>
        ` : ''}
      </div>

      <!-- Pulsante Principale Hero: Avvia/Ferma Ciclo (input_boolean.irrigazione_attiva) -->
      <section class="modal-section">
        <button type="button" id="btn-master-cycle" class="btn-irrigation-master ${isCycleActive ? 'active-stop' : 'idle-start'}">
          <svg class="master-btn-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            ${isCycleActive ? `
              <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"></rect>
            ` : `
              <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" fill="currentColor"></path>
            `}
          </svg>
          <div class="master-btn-texts">
            <div class="master-btn-title">${isCycleActive ? 'Ferma Irrigazione' : 'Avvia Ciclo Irrigazione'}</div>
            <div class="master-btn-sub">${isCycleActive ? 'Ciclo in corso • Clicca per arrestare' : 'Avvia l\'irrigazione sequenziale programmata'}</div>
          </div>
        </button>
      </section>

      <!-- Sezione Zone del Giardino -->
      <section class="modal-section">
        <h4 class="modal-section-title">Zone Giardino</h4>

        <div class="irrigation-zones-stack">
          
          <!-- ZONA 1: PRATO SUD -->
          <div class="irrigation-zone-item ${area1Enabled ? 'enabled' : 'disabled'} ${valve1 ? 'valve-on' : ''}">
            <div class="zone-header-row">
              <div class="zone-identity">
                <div class="zone-icon-box ${valve1 ? 'active' : ''}">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="3"></circle>
                    <path d="M3 12h6M15 12h6M12 3v6M12 15v6"></path>
                  </svg>
                </div>
                <div class="zone-title-text">Area 1 • Prato Sud</div>
              </div>

              <!-- Switch Abilitazione Zona nel Ciclo -->
              <label class="custom-ha-switch" for="chk-area-1" title="Abilita/Disabilita Area 1 nel ciclo programmato">
                <input type="checkbox" class="native-raw" id="chk-area-1" name="chk-area-1" aria-label="Abilita Area 1 nel ciclo" ${area1Enabled ? 'checked' : ''}>
                <span class="switch-track">
                  <span class="switch-thumb"></span>
                </span>
              </label>
            </div>

            <div class="zone-controls-row">
              <!-- Stepper Durata Minuti (multipli di 5) -->
              <div class="duration-stepper-box">
                <button type="button" class="btn-time-step" data-step-area="1" data-delta="-5" title="-5 min" aria-label="Riduci durata Area 1">-</button>
                <div class="time-input-wrap">
                  <input type="number" id="num-time-1" name="num-time-1" min="5" max="120" step="5" value="${time1}" class="time-number-input" aria-label="Durata Area 1 in minuti">
                  <span class="time-unit">min</span>
                </div>
                <button type="button" class="btn-time-step" data-step-area="1" data-delta="5" title="+5 min" aria-label="Aumenta durata Area 1">+</button>
              </div>

              <!-- Pulsante Valvola Manuale Rapida (Icona Goccia d'Acqua) -->
              <button type="button" class="btn-valve-trigger ${valve1 ? 'on' : ''}" data-valve-area="1" title="Attiva/Disattiva Area 1 manualmente">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="${valve1 ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"></path>
                </svg>
                <span>${valve1 ? 'Attiva' : 'Manuale'}</span>
              </button>

              <!-- Inquadra Camera 3D -->
              <button type="button" class="btn-zone-fly" data-fly="area1" title="Inquadra l'Area 1 nel modello 3D" aria-label="Inquadra Area 1 nel modello 3D">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
                  <circle cx="12" cy="13" r="4"></circle>
                </svg>
              </button>
            </div>
          </div>

          <!-- ZONA 2: CORTE EST -->
          <div class="irrigation-zone-item ${area2Enabled ? 'enabled' : 'disabled'} ${valve2 ? 'valve-on' : ''}">
            <div class="zone-header-row">
              <div class="zone-identity">
                <div class="zone-icon-box ${valve2 ? 'active' : ''}">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="3"></circle>
                    <path d="M3 12h6M15 12h6M12 3v6M12 15v6"></path>
                  </svg>
                </div>
                <div class="zone-title-text">Area 2 • Corte Est</div>
              </div>

              <!-- Switch Abilitazione Zona nel Ciclo -->
              <label class="custom-ha-switch" for="chk-area-2" title="Abilita/Disabilita Area 2 nel ciclo programmato">
                <input type="checkbox" class="native-raw" id="chk-area-2" name="chk-area-2" aria-label="Abilita Area 2 nel ciclo" ${area2Enabled ? 'checked' : ''}>
                <span class="switch-track">
                  <span class="switch-thumb"></span>
                </span>
              </label>
            </div>

            <div class="zone-controls-row">
              <!-- Stepper Durata Minuti (multipli di 5) -->
              <div class="duration-stepper-box">
                <button type="button" class="btn-time-step" data-step-area="2" data-delta="-5" title="-5 min" aria-label="Riduci durata Area 2">-</button>
                <div class="time-input-wrap">
                  <input type="number" id="num-time-2" name="num-time-2" min="5" max="120" step="5" value="${time2}" class="time-number-input" aria-label="Durata Area 2 in minuti">
                  <span class="time-unit">min</span>
                </div>
                <button type="button" class="btn-time-step" data-step-area="2" data-delta="5" title="+5 min" aria-label="Aumenta durata Area 2">+</button>
              </div>

              <!-- Pulsante Valvola Manuale Rapida (Icona Goccia d'Acqua) -->
              <button type="button" class="btn-valve-trigger ${valve2 ? 'on' : ''}" data-valve-area="2" title="Attiva/Disattiva Area 2 manualmente">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="${valve2 ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"></path>
                </svg>
                <span>${valve2 ? 'Attiva' : 'Manuale'}</span>
              </button>

              <!-- Inquadra Camera 3D -->
              <button type="button" class="btn-zone-fly" data-fly="area2" title="Inquadra l'Area 2 nel modello 3D" aria-label="Inquadra Area 2 nel modello 3D">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
                  <circle cx="12" cy="13" r="4"></circle>
                </svg>
              </button>
            </div>
          </div>

          <!-- ZONA 3: PRATO NORD & VIALE -->
          <div class="irrigation-zone-item ${area3Enabled ? 'enabled' : 'disabled'} ${valve3 ? 'valve-on' : ''}">
            <div class="zone-header-row">
              <div class="zone-identity">
                <div class="zone-icon-box ${valve3 ? 'active' : ''}">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="3"></circle>
                    <path d="M3 12h6M15 12h6M12 3v6M12 15v6"></path>
                  </svg>
                </div>
                <div class="zone-title-text">Area 3 • Nord & Viale</div>
              </div>

              <!-- Switch Abilitazione Zona nel Ciclo -->
              <label class="custom-ha-switch" for="chk-area-3" title="Abilita/Disabilita Area 3 nel ciclo programmato">
                <input type="checkbox" class="native-raw" id="chk-area-3" name="chk-area-3" aria-label="Abilita Area 3 nel ciclo" ${area3Enabled ? 'checked' : ''}>
                <span class="switch-track">
                  <span class="switch-thumb"></span>
                </span>
              </label>
            </div>

            <div class="zone-controls-row">
              <!-- Stepper Durata Minuti (multipli di 5) -->
              <div class="duration-stepper-box">
                <button type="button" class="btn-time-step" data-step-area="3" data-delta="-5" title="-5 min" aria-label="Riduci durata Area 3">-</button>
                <div class="time-input-wrap">
                  <input type="number" id="num-time-3" name="num-time-3" min="5" max="120" step="5" value="${time3}" class="time-number-input" aria-label="Durata Area 3 in minuti">
                  <span class="time-unit">min</span>
                </div>
                <button type="button" class="btn-time-step" data-step-area="3" data-delta="5" title="+5 min" aria-label="Aumenta durata Area 3">+</button>
              </div>

              <!-- Pulsante Valvola Manuale Rapida (Icona Goccia d'Acqua) -->
              <button type="button" class="btn-valve-trigger ${valve3 ? 'on' : ''}" data-valve-area="3" title="Attiva/Disattiva Area 3 manualmente">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="${valve3 ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"></path>
                </svg>
                <span>${valve3 ? 'Attiva' : 'Manuale'}</span>
              </button>

              <!-- Inquadra Camera 3D -->
              <button type="button" class="btn-zone-fly" data-fly="area3" title="Inquadra l'Area 3 nel modello 3D" aria-label="Inquadra Area 3 nel modello 3D">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
                  <circle cx="12" cy="13" r="4"></circle>
                </svg>
              </button>
            </div>
          </div>

        </div>
      </section>

      <!-- Azioni Rapide Valvole & Inquadrature 3D -->
      <section class="modal-section">
        <h4 class="modal-section-title">Azioni Rapide & Telecamere</h4>
        
        <button type="button" class="btn-irrigation-stop-all" id="btn-valves-all-off" title="Chiude immediatamente tutte le valvole del giardino">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y1="9" x2="9" y2="15"></line>
            <line x1="9" y1="9" x2="15" y2="15"></line>
          </svg>
          <span>Spegni Tutte le Valvole</span>
        </button>

        <div class="irrigation-views-grid">
          <button type="button" class="btn-irrigation-quick" data-fly="topdown">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2"></rect>
              <path d="M3 9h18M9 21V9"></path>
            </svg>
            <span>Pianta Zenitale</span>
          </button>
          <button type="button" class="btn-irrigation-quick" data-fly="garden">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"></path>
            </svg>
            <span>Panoramica Giardino</span>
          </button>
        </div>
      </section>
    `;

    this.bindEvents();
  }

  bindEvents() {
    if (!this.container) return;

    // Master Cycle Button
    const btnMaster = this.container.querySelector('#btn-master-cycle');
    if (btnMaster) {
      btnMaster.addEventListener('click', () => {
        this.controller.toggleCycle();
      });
    }

    // Toggle Abilitazione Aree (input_boolean.area_1, area_2, area_3)
    [1, 2, 3].forEach((areaNum) => {
      const chk = this.container.querySelector(`#chk-area-${areaNum}`);
      if (chk) {
        chk.addEventListener('change', () => {
          this.controller.toggleAreaEnable(areaNum);
        });
      }

      // Input numerico minuti
      const numInput = this.container.querySelector(`#num-time-${areaNum}`);
      if (numInput) {
        numInput.addEventListener('change', (e) => {
          const val = parseFloat(e.target.value);
          if (!isNaN(val)) {
            this.controller.setAreaTime(areaNum, val);
          }
        });
      }

      // Pulsante manuale valvola fisica
      const valveBtn = this.container.querySelector(`[data-valve-area="${areaNum}"]`);
      if (valveBtn) {
        valveBtn.addEventListener('click', () => {
          this.controller.toggleAreaValve(areaNum);
        });
      }
    });

    // Stepper + / - minuti (multipli di 5)
    const stepBtns = this.container.querySelectorAll('[data-step-area]');
    stepBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const areaNum = parseInt(btn.dataset.stepArea, 10);
        const delta = parseInt(btn.dataset.delta, 10);
        this.controller.stepAreaTime(areaNum, delta);
      });
    });

    // Spegni Tutte le Valvole
    const btnValvesOff = this.container.querySelector('#btn-valves-all-off');
    if (btnValvesOff) {
      btnValvesOff.addEventListener('click', () => {
        this.controller.turnOffAllValves();
      });
    }

    // Inquadrature 3D
    const flyBtns = this.container.querySelectorAll('[data-fly]');
    flyBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const preset = btn.dataset.fly;
        this.flyToPreset(preset);
      });
    });
  }

  flyToPreset(preset) {
    const camCtrl = this.context?.cameraController;
    if (!camCtrl) return;

    if (preset === 'topdown') {
      camCtrl.flyToPreset('topdown');
    } else if (preset === 'garden') {
      camCtrl.flyToPreset('garden');
    } else if (preset === 'area1') {
      camCtrl.flyTo(
        { x: 3.0, y: 12.0, z: 35.0 },
        { x: 3.0, y: 0.0, z: 24.5 },
        1.0
      );
    } else if (preset === 'area2') {
      camCtrl.flyTo(
        { x: 10.0, y: 11.0, z: 3.5 },
        { x: 10.0, y: 0.0, z: 13.0 },
        1.0
      );
    } else if (preset === 'area3') {
      camCtrl.flyTo(
        { x: -14.0, y: 11.0, z: 8.5 },
        { x: -2.0, y: 0.0, z: 8.5 },
        1.0
      );
    }
  }

  updateLiveState() {
    if (!this.controller.isModalOpen || !this.container || !this.context) {
      return;
    }

    // Aggiorna solo se l'utente non sta digitando in un campo di input numerico
    const activeEl = document.activeElement;
    if (activeEl && activeEl.classList.contains('time-number-input')) {
      return;
    }

    this.render(this.container, this.context);
  }
}
