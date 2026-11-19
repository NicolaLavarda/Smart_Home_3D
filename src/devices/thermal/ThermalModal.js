import { icon } from '../../ui/icons.js';

function lerpChannel(a, b, t) {
  return Math.round(a + (b - a) * t);
}

function lerpRgb(c1, c2, t) {
  const k = Math.max(0, Math.min(1, t));
  return [
    lerpChannel(c1[0], c2[0], k),
    lerpChannel(c1[1], c2[1], k),
    lerpChannel(c1[2], c2[2], k),
  ];
}

function rgbStr(rgb, alpha = 1) {
  return alpha < 1
    ? `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`
    : `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

/**
 * ThermalModal
 *
 * Pannello Material 3 per l'Impianto Termico:
 * 1. Tab "Acqua Calda" (predefinita):
 *    - Minuti disponibili & Minuti di attesa
 *    - Stepper Minuti doccia desiderati
 *    - Controllo Caldaia (switch.smart_switch_caldaia)
 *    - Messaggio dinamico stato acqua calda / doccia in corso
 *    - Programma accensione & Programma spegnimento caldaia (orario + toggle automazione)
 * 2. Tab "Temperature":
 *    - Box Caldaia a tinta uniforme dinamica rispetto a `sensor.temperatura_calda_caldaia`
 *    - Box Accumulo Puffer sfumata (solo Accumulo Alto e Accumulo Basso) con colori dinamici
 *    - Metriche Litri Acqua Calda, Caldaia Oggi, Temperatura Esterna
 * 3. Tab "Parametri":
 *    - Parametri Doccia (Temperatura doccia stepper + Doccia selezionata)
 *    - Gestione automatica valvola e doccia (Temperatura calda caldaia, Valvola Automatica,
 *      Valvola Acqua Calda manuale condizionale visibile solo se Valvola Automatica è spenta,
 *      Gestione automatica acqua calda + guida di funzionamento)
 */
export class ThermalModal {
  constructor(controller) {
    this.controller = controller;
    this.container = null;
    this.context = null;
    this.activeTab = 'main'; // 'main' | 'temps' | 'params'
    this._lastShowerOptionsKey = '';
  }

  _formatTemp(temp) {
    return Number.isFinite(temp) ? `${temp.toFixed(1)}°C` : '--°C';
  }

  _formatNumeric(val, unit = '') {
    if (!Number.isFinite(val)) return `--${unit ? ` ${unit}` : ''}`;
    const formatted = Number.isInteger(val) ? String(val) : val.toFixed(1);
    return unit ? `${formatted} ${unit}` : formatted;
  }

  /**
   * Calcola i colori dinamici (riempimento box e colore testo/etichetta)
   * rispetto alla soglia `sensor.temperatura_calda_caldaia` (`refTemp`):
   * - `T > refTemp + 1.0°C` -> Rosso (sfumando verso rosso intenso)
   * - `refTemp - 0.5°C < T <= refTemp + 1.0°C` -> Arancione (sfumando gradualmente da ambra a rosso-arancio)
   * - `T <= refTemp - 0.5°C` -> Azzurro (sfumando gradualmente da celeste a ciano/blu freddo)
   */
  _computeThermalTone(temp, refTemp) {
    const ref = Number.isFinite(refTemp) ? refTemp : 45.0;
    if (!Number.isFinite(temp)) {
      return {
        zone: 'cool',
        fill: 'rgba(56, 189, 248, 0.72)',
        text: '#7dd3fc',
        border: 'rgba(56, 189, 248, 0.35)',
        rowBg: 'rgba(56, 189, 248, 0.08)',
      };
    }

    const delta = temp - ref;

    // Palette coerente con i gradienti Material 3 esistenti
    const RED_DEEP = [239, 68, 68];       // #ef4444
    const RED_WARM = [244, 86, 52];       // transizione al limite +1.0°C
    const ORANGE_MID = [249, 115, 22];    // #f97316
    const ORANGE_AMBER = [251, 146, 60];  // #fb923c al limite -0.5°C
    const CYAN_LIGHT = [56, 189, 248];    // #38bdf8 appena sotto -0.5°C
    const CYAN_MID = [6, 182, 212];       // #06b6d4
    const CYAN_DEEP = [2, 132, 199];      // #0284c7 molto freddo

    const TEXT_RED = [252, 165, 165];     // #fca5a5
    const TEXT_ORANGE = [253, 186, 116];  // #fdba74
    const TEXT_AMBER = [254, 215, 170];   // #fed7aa
    const TEXT_SKY = [186, 230, 253];     // #bae6fd
    const TEXT_CYAN = [103, 232, 249];    // #67e8f9

    let fillRgb;
    let textRgb;
    let zone;

    if (delta > 1.0) {
      zone = 'hot';
      const t = Math.min(1, (delta - 1.0) / 3.0);
      fillRgb = lerpRgb(RED_WARM, RED_DEEP, t);
      textRgb = lerpRgb([253, 175, 150], TEXT_RED, t);
    } else if (delta > -0.5) {
      zone = 'warm';
      const t = (delta + 0.5) / 1.5; // 0 a -0.5°C -> 1 a +1.0°C
      if (t < 0.5) {
        fillRgb = lerpRgb(ORANGE_AMBER, ORANGE_MID, t * 2);
        textRgb = lerpRgb(TEXT_AMBER, TEXT_ORANGE, t * 2);
      } else {
        fillRgb = lerpRgb(ORANGE_MID, RED_WARM, (t - 0.5) * 2);
        textRgb = lerpRgb(TEXT_ORANGE, [253, 175, 150], (t - 0.5) * 2);
      }
    } else {
      zone = 'cool';
      const below = -0.5 - delta; // >= 0
      if (below <= 3.5) {
        const t = below / 3.5;
        fillRgb = lerpRgb(CYAN_LIGHT, CYAN_MID, t);
        textRgb = lerpRgb(TEXT_SKY, TEXT_CYAN, t);
      } else {
        const t = Math.min(1, (below - 3.5) / 12.0);
        fillRgb = lerpRgb(CYAN_MID, CYAN_DEEP, t);
        textRgb = lerpRgb(TEXT_CYAN, [125, 211, 252], t);
      }
    }

    return {
      zone,
      fill: rgbStr(fillRgb, 0.86),
      text: rgbStr(textRgb),
      border: rgbStr(fillRgb, 0.42),
      rowBg: rgbStr(fillRgb, 0.1),
    };
  }

  _buildPufferGradient(highTemp, lowTemp, refTemp) {
    const highTone = this._computeThermalTone(highTemp, refTemp);
    const lowTone = this._computeThermalTone(lowTemp, refTemp);
    const ref = Number.isFinite(refTemp) ? refTemp : 45.0;

    if (
      Number.isFinite(highTemp) &&
      Number.isFinite(lowTemp) &&
      highTemp > ref + 1.0 &&
      lowTemp <= ref - 0.5 &&
      highTemp - lowTemp > 2.0
    ) {
      const ratio = (highTemp - ref) / (highTemp - lowTemp);
      const midPct = Math.max(18, Math.min(82, Math.round(ratio * 100)));
      return `linear-gradient(180deg, ${highTone.fill} 0%, rgba(249, 115, 22, 0.78) ${midPct}%, ${lowTone.fill} 100%)`;
    }

    return `linear-gradient(180deg, ${highTone.fill} 0%, ${lowTone.fill} 100%)`;
  }

  setTab(tabId) {
    const allowed = ['main', 'temps', 'params'];
    this.activeTab = allowed.includes(tabId) ? tabId : 'main';
    if (!this.container) return;

    this.container.querySelectorAll('[data-thermal-tab]').forEach((btn) => {
      const active = btn.dataset.thermalTab === this.activeTab;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-selected', String(active));
    });

    this.container.querySelectorAll('[data-thermal-panel]').forEach((panel) => {
      panel.hidden = panel.dataset.thermalPanel !== this.activeTab;
    });

    const scrollParent = this.container.closest('.modal-controls');
    if (scrollParent) scrollParent.scrollTop = 0;
  }

  render(container, context = {}) {
    this.container = container;
    this.context = context;
    this.activeTab = 'main';
    this._lastShowerOptionsKey = '';

    this.container.innerHTML = `
      <div class="thermal-panel">
        <!-- Navigazione Material 3 a 3 schede -->
        <div class="thermal-tabs" role="tablist" aria-label="Sezioni Impianto Termico">
          <button type="button" class="thermal-tab-btn active" data-thermal-tab="main" role="tab" aria-selected="true">
            ${icon('droplets', { size: 14 })}
            <span>Acqua Calda</span>
          </button>
          <button type="button" class="thermal-tab-btn" data-thermal-tab="temps" role="tab" aria-selected="false">
            ${icon('thermometer', { size: 14 })}
            <span>Temperature</span>
          </button>
          <button type="button" class="thermal-tab-btn" data-thermal-tab="params" role="tab" aria-selected="false">
            ${icon('sliders-horizontal', { size: 14 })}
            <span>Parametri</span>
          </button>
        </div>

        <!-- ==================== TAB 1: ACQUA CALDA (PRINCIPALE) ==================== -->
        <div class="thermal-tab-pane" data-thermal-panel="main">
          <div class="thermal-section-head">
            <span class="thermal-section-title">${icon('shower-head', { size: 14 })} Acqua Calda</span>
            <span class="thermal-live-pill" id="thermal-shower-active-pill" hidden>Doccia in corso</span>
          </div>

          <!-- Metriche principali: Minuti disponibili + Minuti di attesa -->
          <div class="thermal-kpi-grid">
            <div class="thermal-kpi-card highlight">
              <span class="thermal-kpi-label">Minuti disponibili</span>
              <span class="thermal-kpi-value" id="thermal-val-shower">-- min</span>
            </div>
            <div class="thermal-kpi-card">
              <span class="thermal-kpi-label">Minuti di attesa</span>
              <span class="thermal-kpi-value" id="thermal-val-wait">-- min</span>
            </div>
          </div>

          <!-- Minuti doccia desiderati (stepper) -->
          <div class="thermal-stepper-row">
            <div class="thermal-stepper-copy">
              <span class="m3-switch-title">Minuti doccia desiderati</span>
              <span class="m3-switch-sub">Target autonomia acqua calda</span>
            </div>
            <div class="m3-stepper-control">
              <button type="button" class="m3-stepper-btn" id="btn-thermal-desired-dec" aria-label="Riduci minuti doccia desiderati">
                ${icon('minus', { size: 15 })}
              </button>
              <span class="m3-stepper-val" id="thermal-val-desired">-- min</span>
              <button type="button" class="m3-stepper-btn" id="btn-thermal-desired-inc" aria-label="Aumenta minuti doccia desiderati">
                ${icon('plus', { size: 15 })}
              </button>
            </div>
          </div>

          <!-- Caldaia Toggle Banner -->
          <div class="thermal-status-banner" id="thermal-status-banner">
            <div class="thermal-status-icon" id="thermal-status-icon">${icon('flame', { size: 20 })}</div>
            <div class="thermal-status-copy">
              <div class="thermal-status-title" id="thermal-status-title">Caldaia</div>
              <div class="thermal-status-sub" id="thermal-status-sub">Interruttore caldaia</div>
            </div>
            <button type="button" class="m3-tonal-toggle" id="btn-thermal-boiler-toggle" aria-pressed="false">
              ${icon('power', { size: 15 })}
              <span id="thermal-boiler-btn-label">Accendi</span>
            </button>
          </div>

          <!-- Messaggio dinamico intelligente (logica card HA) -->
          <div class="thermal-advice-box" id="thermal-advice-box">
            <span class="thermal-advice-icon">${icon('info', { size: 16 })}</span>
            <p class="thermal-advice-text" id="thermal-advice-text">Caricamento stato acqua calda...</p>
          </div>

          <!-- Programmazione Accensione Caldaia -->
          <div class="thermal-section-head">
            <span class="thermal-section-title">${icon('clock', { size: 14 })} Programma accensione caldaia</span>
          </div>
          <div class="thermal-schedule-card">
            <label class="thermal-time-field" for="input-thermal-on-time">
              <span class="thermal-time-label">Orario accensione</span>
              <input type="time" id="input-thermal-on-time" class="thermal-time-input" aria-label="Orario accensione caldaia" />
            </label>
            <div class="thermal-schedule-toggle-wrap">
              <span class="thermal-schedule-state" id="thermal-sched-on-state">Disattiva</span>
              <button type="button" class="m3-switch" id="btn-thermal-sched-on" role="switch" aria-checked="false" aria-label="Accensione programmata caldaia">
                <span class="m3-switch-thumb"></span>
              </button>
            </div>
          </div>

          <!-- Programmazione Spegnimento Caldaia -->
          <div class="thermal-section-head">
            <span class="thermal-section-title">${icon('timer', { size: 14 })} Programma spegnimento caldaia</span>
          </div>
          <div class="thermal-schedule-card">
            <label class="thermal-time-field" for="input-thermal-off-time">
              <span class="thermal-time-label">Orario spegnimento</span>
              <input type="time" id="input-thermal-off-time" class="thermal-time-input" aria-label="Orario spegnimento caldaia" />
            </label>
            <div class="thermal-schedule-toggle-wrap">
              <span class="thermal-schedule-state" id="thermal-sched-off-state">Disattiva</span>
              <button type="button" class="m3-switch" id="btn-thermal-sched-off" role="switch" aria-checked="false" aria-label="Spegnimento programmato caldaia">
                <span class="m3-switch-thumb"></span>
              </button>
            </div>
          </div>
        </div>

        <!-- ==================== TAB 2: TEMPERATURE ==================== -->
        <div class="thermal-tab-pane" data-thermal-panel="temps" hidden>
          <div class="thermal-section-head">
            <span class="thermal-section-title">${icon('flame', { size: 14 })} Caldaia</span>
          </div>

          <!-- Box Caldaia a tinta uniforme (non sfumata), adattata al valore rispetto a temperatura calda caldaia -->
          <div class="thermal-stratification-box thermal-boiler-box">
            <div class="thermal-tank-visual thermal-boiler-visual" aria-hidden="true">
              <div class="thermal-boiler-fill" id="thermal-boiler-fill"></div>
              <span class="thermal-tank-tag center">CALDAIA</span>
            </div>

            <div class="thermal-readings-col single">
              <div class="thermal-reading-row" id="thermal-row-boiler">
                <span class="thermal-reading-label" id="thermal-lbl-boiler">${icon('flame', { size: 14 })} Temperatura Caldaia</span>
                <span class="thermal-reading-val" id="thermal-val-boiler">--°C</span>
              </div>
            </div>
          </div>

          <div class="thermal-section-head">
            <span class="thermal-section-title">${icon('thermometer', { size: 14 })} Accumulo</span>
          </div>

          <!-- Box Accumulo Puffer sfumata (solo Accumulo Alto e Accumulo Basso) -->
          <div class="thermal-stratification-box">
            <div class="thermal-tank-visual" aria-hidden="true">
              <div class="thermal-tank-fill" id="thermal-tank-fill"></div>
              <span class="thermal-tank-tag top">ALTO</span>
              <span class="thermal-tank-tag bottom">BASSO</span>
            </div>

            <div class="thermal-readings-col">
              <div class="thermal-reading-row" id="thermal-row-puffer-high">
                <span class="thermal-reading-label" id="thermal-lbl-puffer-high">${icon('thermometer', { size: 14 })} Accumulo Alto</span>
                <span class="thermal-reading-val" id="thermal-val-puffer-high">--°C</span>
              </div>
              <div class="thermal-reading-row" id="thermal-row-puffer-low">
                <span class="thermal-reading-label" id="thermal-lbl-puffer-low">${icon('waves', { size: 14 })} Accumulo Basso</span>
                <span class="thermal-reading-val" id="thermal-val-puffer-low">--°C</span>
              </div>
            </div>
          </div>

          <div class="thermal-metrics-strip">
            <div class="thermal-metric-cell">
              <span class="thermal-metric-icon">${icon('droplets', { size: 15 })}</span>
              <span class="thermal-metric-value" id="thermal-val-liters">-- L</span>
              <span class="thermal-metric-label">Acqua Calda</span>
            </div>
            <div class="thermal-metric-cell">
              <span class="thermal-metric-icon">${icon('clock', { size: 15 })}</span>
              <span class="thermal-metric-value" id="thermal-val-runtime">-- h</span>
              <span class="thermal-metric-label">Caldaia Oggi</span>
            </div>
            <div class="thermal-metric-cell">
              <span class="thermal-metric-icon">${icon('thermometer', { size: 15 })}</span>
              <span class="thermal-metric-value" id="thermal-val-outdoor">--°C</span>
              <span class="thermal-metric-label">Esterno</span>
            </div>
          </div>
        </div>

        <!-- ==================== TAB 3: PARAMETRI IMPIANTO TERMICO ==================== -->
        <div class="thermal-tab-pane" data-thermal-panel="params" hidden>
          <div class="thermal-section-head">
            <span class="thermal-section-title">${icon('shower-head', { size: 14 })} Parametri Doccia</span>
          </div>

          <!-- Temperatura doccia (stepper) -->
          <div class="thermal-stepper-row">
            <div class="thermal-stepper-copy">
              <span class="m3-switch-title">Temperatura doccia</span>
              <span class="m3-switch-sub">Temperatura target di erogazione</span>
            </div>
            <div class="m3-stepper-control">
              <button type="button" class="m3-stepper-btn" id="btn-thermal-temp-dec" aria-label="Riduci temperatura doccia">
                ${icon('minus', { size: 15 })}
              </button>
              <span class="m3-stepper-val" id="thermal-val-shower-temp">--°C</span>
              <button type="button" class="m3-stepper-btn" id="btn-thermal-temp-inc" aria-label="Aumenta temperatura doccia">
                ${icon('plus', { size: 15 })}
              </button>
            </div>
          </div>

          <!-- Doccia selezionata (input_select.doccia_selezionata) -->
          <div class="thermal-select-card">
            <div class="m3-switch-copy">
              <span class="m3-switch-title">Doccia selezionata</span>
              <span class="m3-switch-sub" id="thermal-shower-select-sub">Punto di prelievo attivo</span>
            </div>
            <div class="thermal-option-chips" id="thermal-shower-options"></div>
          </div>

          <div class="thermal-section-head">
            <span class="thermal-section-title">${icon('sliders-horizontal', { size: 14 })} Gestione automatica valvola e doccia</span>
          </div>

          <!-- Sensore Temperatura calda caldaia -->
          <div class="thermal-sensor-tile">
            <span class="thermal-reading-label">${icon('thermometer', { size: 15 })} Temperatura calda caldaia</span>
            <span class="thermal-reading-val" id="thermal-val-boiler-hot-params">--°C</span>
          </div>

          <div class="thermal-controls-list">
            <!-- Valvola Automatica (automation.controllo_valvola_acqua_calda) -->
            <div class="m3-switch-row">
              <div class="m3-switch-copy">
                <span class="m3-switch-title">Valvola Automatica</span>
                <span class="m3-switch-sub" id="thermal-auto-valve-sub">Selezione automatica caldaia / accumulo</span>
              </div>
              <button type="button" class="m3-switch" id="btn-thermal-auto-valve" role="switch" aria-checked="false" aria-label="Valvola Automatica">
                <span class="m3-switch-thumb"></span>
              </button>
            </div>

            <!-- Valvola Acqua Calda manuale: VISIBILE SOLO se Valvola Automatica è OFF -->
            <div class="m3-switch-row thermal-manual-valve-row" id="thermal-manual-valve-row" hidden>
              <div class="m3-switch-copy">
                <span class="m3-switch-title">Valvola Acqua Calda (Manuale)</span>
                <span class="m3-switch-sub" id="thermal-valve-sub">Pesca dall'accumulo</span>
              </div>
              <button type="button" class="m3-switch" id="btn-thermal-valve" role="switch" aria-checked="false" aria-label="Valvola Acqua Calda manuale">
                <span class="m3-switch-thumb"></span>
              </button>
            </div>

            <!-- Gestione automatica acqua calda (input_boolean.gestione_automatica_acqua_calda) -->
            <div class="m3-switch-row">
              <div class="m3-switch-copy">
                <span class="m3-switch-title">Gestione automatica acqua calda</span>
                <span class="m3-switch-sub" id="thermal-auto-sub">Spegnimento automatico per inerzia termica</span>
              </div>
              <button type="button" class="m3-switch" id="btn-thermal-auto" role="switch" aria-checked="false" aria-label="Gestione automatica acqua calda">
                <span class="m3-switch-thumb"></span>
              </button>
            </div>
          </div>

          <!-- Spiegazione funzionamento (collapsible pulita con testi esatti HA) -->
          <details class="thermal-info-details">
            <summary class="thermal-info-summary">
              ${icon('info', { size: 14 })}
              <span>Come funzionano Valvola e Gestione automatica</span>
            </summary>
            <div class="thermal-info-body">
              <div class="thermal-info-block">
                <strong>Valvola Automatica</strong>
                <ul>
                  <li><em>Attiva:</em> pesca acqua calda dalla caldaia o dall'accumulo in base a quale ha la temperatura maggiore (se entrambe superano la temperatura scelta, preferisce prima la caldaia che si raffredda più velocemente).</li>
                  <li><em>Disattiva:</em> abilita il controllo manuale della valvola (accesa pesca dalla caldaia, spenta dall'accumulo).</li>
                </ul>
              </div>
              <div class="thermal-info-block">
                <strong>Gestione automatica acqua calda</strong>
                <ul>
                  <li><em>Attiva:</em> la caldaia si spegne da sola quando sa di raggiungere per inerzia termica i "minuti doccia desiderati".</li>
                  <li><em>Disattiva:</em> la caldaia si accende e spegne solo manualmente.</li>
                </ul>
              </div>
            </div>
          </details>
        </div>
      </div>
    `;

    this._bindEvents();
    this.updateLive();
  }

  _bindEvents() {
    if (!this.container) return;

    // Tabs
    this.container.querySelectorAll('[data-thermal-tab]').forEach((btn) => {
      btn.addEventListener('click', () => this.setTab(btn.dataset.thermalTab));
    });

    // Main tab controls
    this.container.querySelector('#btn-thermal-desired-dec')?.addEventListener('click', () => {
      this.controller.stepDesiredShowerMinutes(-1);
    });
    this.container.querySelector('#btn-thermal-desired-inc')?.addEventListener('click', () => {
      this.controller.stepDesiredShowerMinutes(1);
    });
    this.container.querySelector('#btn-thermal-boiler-toggle')?.addEventListener('click', () => {
      this.controller.toggleBoiler();
    });

    // Schedules
    this.container.querySelector('#input-thermal-on-time')?.addEventListener('change', (e) => {
      this.controller.setBoilerScheduleOnTime(e.target.value);
    });
    this.container.querySelector('#btn-thermal-sched-on')?.addEventListener('click', () => {
      this.controller.toggleBoilerScheduleOn();
    });
    this.container.querySelector('#input-thermal-off-time')?.addEventListener('change', (e) => {
      this.controller.setBoilerScheduleOffTime(e.target.value);
    });
    this.container.querySelector('#btn-thermal-sched-off')?.addEventListener('click', () => {
      this.controller.toggleBoilerScheduleOff();
    });

    // Params tab controls
    this.container.querySelector('#btn-thermal-temp-dec')?.addEventListener('click', () => {
      this.controller.stepShowerTemp(-1);
    });
    this.container.querySelector('#btn-thermal-temp-inc')?.addEventListener('click', () => {
      this.controller.stepShowerTemp(1);
    });
    this.container.querySelector('#btn-thermal-auto-valve')?.addEventListener('click', () => {
      this.controller.toggleAutoValve();
    });
    this.container.querySelector('#btn-thermal-valve')?.addEventListener('click', () => {
      this.controller.toggleHotWaterValve();
    });
    this.container.querySelector('#btn-thermal-auto')?.addEventListener('click', () => {
      this.controller.toggleAutoManagement();
    });
  }

  _syncShowerOptionsUI(options, selected) {
    const wrap = this.container?.querySelector('#thermal-shower-options');
    if (!wrap) return;

    const optionsKey = options.join('||');
    if (optionsKey !== this._lastShowerOptionsKey) {
      this._lastShowerOptionsKey = optionsKey;
      wrap.innerHTML = '';

      if (options.length <= 4) {
        options.forEach((opt) => {
          const btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'thermal-option-chip';
          btn.dataset.showerOption = opt;
          btn.textContent = opt;
          btn.addEventListener('click', () => {
            this.controller.selectShower(opt);
          });
          wrap.appendChild(btn);
        });
      } else {
        const sel = document.createElement('select');
        sel.className = 'thermal-native-select';
        sel.id = 'select-thermal-shower';
        sel.setAttribute('aria-label', 'Doccia selezionata');
        options.forEach((opt) => {
          const o = document.createElement('option');
          o.value = opt;
          o.textContent = opt;
          sel.appendChild(o);
        });
        sel.addEventListener('change', (e) => {
          this.controller.selectShower(e.target.value);
        });
        wrap.appendChild(sel);
      }
    }

    const chips = wrap.querySelectorAll('[data-shower-option]');
    if (chips.length > 0) {
      chips.forEach((chip) => {
        const isSel = chip.dataset.showerOption === selected;
        chip.classList.toggle('active', isSel);
        chip.setAttribute('aria-pressed', String(isSel));
      });
    } else {
      const sel = wrap.querySelector('#select-thermal-shower');
      if (sel && document.activeElement !== sel) {
        sel.value = selected;
      }
    }
  }

  _applyRowTone(rowSel, lblSel, valSel, tone) {
    const rowEl = this.container?.querySelector(rowSel);
    const lblEl = this.container?.querySelector(lblSel);
    const valEl = this.container?.querySelector(valSel);
    if (rowEl) {
      rowEl.dataset.thermalZone = tone.zone;
      rowEl.style.background = tone.rowBg;
      rowEl.style.borderColor = tone.border;
    }
    if (lblEl) lblEl.style.color = tone.text;
    if (valEl) valEl.style.color = tone.text;
  }

  updateLive() {
    if (!this.container) return;

    const setText = (sel, val) => {
      const el = this.container.querySelector(sel);
      if (el) el.textContent = val;
    };
    const setSwitch = (sel, checked) => {
      const btn = this.container.querySelector(sel);
      if (btn) {
        btn.classList.toggle('checked', Boolean(checked));
        btn.setAttribute('aria-checked', String(Boolean(checked)));
      }
    };

    // --- Tab 1: Acqua Calda ---
    const boilerOn = this.controller.isBoilerOn();
    const showerActive = this.controller.isShowerInProgress();
    const showerMins = this.controller.getShowerMinutes();
    const waitMins = this.controller.getWaitMinutes();
    const desiredMins = this.controller.getDesiredShowerMinutes();
    const advice = this.controller.getSmartAdvice();

    const showerPill = this.container.querySelector('#thermal-shower-active-pill');
    if (showerPill) showerPill.hidden = !showerActive;

    setText('#thermal-val-shower', showerMins !== null ? `${Math.round(showerMins)} min` : '-- min');
    setText('#thermal-val-wait', waitMins !== null ? `${Math.round(waitMins)} min` : '-- min');
    setText('#thermal-val-desired', this._formatNumeric(desiredMins, 'min'));

    const banner = this.container.querySelector('#thermal-status-banner');
    if (banner) banner.classList.toggle('is-active', boilerOn);
    setText('#thermal-status-title', boilerOn ? 'Caldaia Accesa' : 'Caldaia Spenta');
    setText('#thermal-status-sub', boilerOn ? 'Riscaldamento sanitario attivo' : 'In standby');

    const boilerBtn = this.container.querySelector('#btn-thermal-boiler-toggle');
    if (boilerBtn) {
      boilerBtn.classList.toggle('active', boilerOn);
      boilerBtn.setAttribute('aria-pressed', String(boilerOn));
    }
    setText('#thermal-boiler-btn-label', boilerOn ? 'Spegni' : 'Accendi');

    const adviceBox = this.container.querySelector('#thermal-advice-box');
    if (adviceBox) {
      adviceBox.dataset.tone = advice.tone;
    }
    setText('#thermal-advice-text', advice.text);

    // Programmazioni caldaia
    const schedOnEnabled = this.controller.isBoilerScheduleOnEnabled();
    const schedOffEnabled = this.controller.isBoilerScheduleOffEnabled();
    const onTimeInput = this.container.querySelector('#input-thermal-on-time');
    if (onTimeInput && document.activeElement !== onTimeInput) {
      onTimeInput.value = this.controller.getBoilerScheduleOnTime();
    }
    setSwitch('#btn-thermal-sched-on', schedOnEnabled);
    setText('#thermal-sched-on-state', schedOnEnabled ? 'Attiva' : 'Disattiva');

    const offTimeInput = this.container.querySelector('#input-thermal-off-time');
    if (offTimeInput && document.activeElement !== offTimeInput) {
      offTimeInput.value = this.controller.getBoilerScheduleOffTime();
    }
    setSwitch('#btn-thermal-sched-off', schedOffEnabled);
    setText('#thermal-sched-off-state', schedOffEnabled ? 'Attiva' : 'Disattiva');

    // --- Tab 2: Temperature (colori dinamici rispetto a sensor.temperatura_calda_caldaia) ---
    const highTemp = this.controller.getPufferHighTemp();
    const lowTemp = this.controller.getPufferLowTemp();
    const boilerTemp = this.controller.getBoilerTemp();
    const refHotTemp = this.controller.getBoilerHotTemp();
    const liters = this.controller.getHotWaterLiters();
    const runtimeH = this.controller.getBoilerRuntimeHours();
    const outdoorTemp = this.controller.getOutdoorTemp();

    const boilerTone = this._computeThermalTone(boilerTemp, refHotTemp);
    const highTone = this._computeThermalTone(highTemp, refHotTemp);
    const lowTone = this._computeThermalTone(lowTemp, refHotTemp);

    setText('#thermal-val-boiler', this._formatTemp(boilerTemp));
    setText('#thermal-val-puffer-high', this._formatTemp(highTemp));
    setText('#thermal-val-puffer-low', this._formatTemp(lowTemp));
    setText('#thermal-val-liters', liters !== null ? `${Math.round(liters)} L` : '-- L');
    setText('#thermal-val-runtime', runtimeH !== null ? `${runtimeH.toFixed(1)} h` : '-- h');
    setText('#thermal-val-outdoor', this._formatTemp(outdoorTemp));

    // Box Caldaia a tinta uniforme (stesso colore pieno)
    const boilerFill = this.container.querySelector('#thermal-boiler-fill');
    if (boilerFill) {
      boilerFill.style.background = boilerTone.fill;
      boilerFill.dataset.thermalZone = boilerTone.zone;
    }
    this._applyRowTone('#thermal-row-boiler', '#thermal-lbl-boiler', '#thermal-val-boiler', boilerTone);

    // Box Puffer sfumata tra Accumulo Alto e Accumulo Basso
    const tankFill = this.container.querySelector('#thermal-tank-fill');
    if (tankFill) {
      tankFill.style.background = this._buildPufferGradient(highTemp, lowTemp, refHotTemp);
    }
    this._applyRowTone('#thermal-row-puffer-high', '#thermal-lbl-puffer-high', '#thermal-val-puffer-high', highTone);
    this._applyRowTone('#thermal-row-puffer-low', '#thermal-lbl-puffer-low', '#thermal-val-puffer-low', lowTone);

    // --- Tab 3: Parametri ---
    const showerTemp = this.controller.getShowerTemp();
    const selectedShower = this.controller.getSelectedShower();
    const showerOptions = this.controller.getShowerOptions();
    const autoValveOn = this.controller.isAutoValveOn();
    const showManualValve = this.controller.isManualValveVisible();
    const manualValveOn = this.controller.isHotWaterValveOn();
    const autoMgmtOn = this.controller.isAutoManagementOn();

    setText('#thermal-val-shower-temp', this._formatNumeric(showerTemp, '°C'));
    setText('#thermal-shower-select-sub', selectedShower);
    this._syncShowerOptionsUI(showerOptions, selectedShower);

    setText('#thermal-val-boiler-hot-params', this._formatTemp(refHotTemp));

    setSwitch('#btn-thermal-auto-valve', autoValveOn);
    setText(
      '#thermal-auto-valve-sub',
      autoValveOn ? 'Attiva • Scelta automatica sorgente' : 'Disattiva • Controllo manuale visibile'
    );

    const manualValveRow = this.container.querySelector('#thermal-manual-valve-row');
    if (manualValveRow) {
      manualValveRow.hidden = !showManualValve;
    }
    setSwitch('#btn-thermal-valve', manualValveOn);
    setText(
      '#thermal-valve-sub',
      manualValveOn ? 'Accesa • Pesca dalla caldaia' : 'Spenta • Pesca dall\'accumulo'
    );

    setSwitch('#btn-thermal-auto', autoMgmtOn);
    setText(
      '#thermal-auto-sub',
      autoMgmtOn ? 'Attiva • Spegnimento per inerzia termica' : 'Disattiva • Accensione/spegnimento manuali'
    );
  }
}
