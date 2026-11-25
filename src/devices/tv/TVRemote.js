import { WEBOS_COMMANDS } from './webos_commands.js';
import { icon } from '../../ui/icons.js';

/**
 * TVRemote
 * 
 * Componente UI che renderizza il telecomando virtuale stile "LG Magic Remote".
 * Espone controlli tattili completi che invocano le API native di LG webOS
 * e i servizi Home Assistant associati.
 */
export class TVRemote {
  constructor(tvController) {
    this.controller = tvController;
    this.container = document.createElement('div');
    this.container.className = 'tv-remote-wrapper';
  }

  render() {
    const isTvOn = this.controller.isPoweredOn();

    this.container.innerHTML = `
      <div class="tv-remote-chassis">
        <!-- Top Status Bar & Power -->
        <div class="remote-top-bar">
          <div class="remote-brand-box">
            <img src="/logos/lg-webos.svg" class="remote-lg-logo" alt="LG webOS" />
            <span class="remote-brand-text">Magic Remote</span>
          </div>
          <div class="remote-led ${isTvOn ? 'led-on' : 'led-off'}"></div>
        </div>

        <div class="remote-row remote-header-buttons">
          <button type="button" class="remote-btn btn-power" id="r-btn-power" title="Accendi / Spegni TV" aria-label="Accendi o spegni TV">
            ${icon('power', { size: 17 })}
          </button>
          <button type="button" class="remote-btn btn-util" id="r-btn-screen-toggle" title="Spegni/Accendi solo Schermo (Eco)">
            <span class="remote-eco-label">ECO</span>
          </button>
          <button type="button" class="remote-btn btn-util" id="r-btn-input" title="Cambia Ingresso Sorgente">
            INPUT
          </button>
        </div>

        <!-- Tastierino Numerico -->
        <div class="remote-numpad">
          <button type="button" class="remote-btn btn-num" data-num="1">1</button>
          <button type="button" class="remote-btn btn-num" data-num="2">2</button>
          <button type="button" class="remote-btn btn-num" data-num="3">3</button>
          <button type="button" class="remote-btn btn-num" data-num="4">4</button>
          <button type="button" class="remote-btn btn-num" data-num="5">5</button>
          <button type="button" class="remote-btn btn-num" data-num="6">6</button>
          <button type="button" class="remote-btn btn-num" data-num="7">7</button>
          <button type="button" class="remote-btn btn-num" data-num="8">8</button>
          <button type="button" class="remote-btn btn-num" data-num="9">9</button>
          <button type="button" class="remote-btn btn-num btn-num--zero" data-num="0">0</button>
          <button type="button" class="remote-btn btn-util btn-small" id="r-btn-del" title="Cancella">DEL</button>
        </div>

        <!-- Volume e Canali Rockers -->
        <div class="remote-rockers-grid">
          <div class="rocker-column">
            <button type="button" class="remote-btn btn-rocker" id="r-btn-vol-up" title="Volume Su">VOL +</button>
            <button type="button" class="remote-btn btn-rocker-sub" id="r-btn-mute" title="Mute Audio">MUTE</button>
            <button type="button" class="remote-btn btn-rocker" id="r-btn-vol-down" title="Volume Giù">VOL -</button>
          </div>

          <div class="rocker-center">
            <button type="button" class="remote-btn btn-icon-round" id="r-btn-home" title="Home Dashboard" aria-label="Home Dashboard">
              ${icon('home', { size: 16, strokeWidth: 2.2 })}
            </button>
            <button type="button" class="remote-btn btn-icon-round" id="r-btn-back" title="Indietro / Esci" aria-label="Indietro">
              ${icon('chevron-left', { size: 16, strokeWidth: 2.2 })}
            </button>
          </div>

          <div class="rocker-column rocker-column--channels">
            <button type="button" class="remote-btn btn-rocker" id="r-btn-ch-up" title="Canale Su"><span>CH</span> ${icon('chevron-up', { size: 13 })}</button>
            <button type="button" class="remote-btn btn-rocker" id="r-btn-ch-down" title="Canale Giù"><span>CH</span> ${icon('chevron-down', { size: 13 })}</button>
          </div>
        </div>

        <!-- Anello di Navigazione D-Pad / Magic Wheel -->
        <div class="remote-dpad-container">
          <div class="remote-dpad-ring">
            <button class="dpad-btn dpad-up" id="r-btn-nav-up" title="Freccia Su">${icon('chevron-up', { size: 16 })}</button>
            <button class="dpad-btn dpad-down" id="r-btn-nav-down" title="Freccia Giù">${icon('chevron-down', { size: 16 })}</button>
            <button class="dpad-btn dpad-left" id="r-btn-nav-left" title="Freccia Sinistra">${icon('chevron-left', { size: 16 })}</button>
            <button class="dpad-btn dpad-right" id="r-btn-nav-right" title="Freccia Destra">${icon('chevron-right', { size: 16 })}</button>
            <button class="dpad-center-ok" id="r-btn-nav-ok" title="OK / Enter">
              <span>OK</span>
            </button>
          </div>
        </div>

        <!-- Controlli Riproduzione Media -->
        <div class="remote-playback-bar">
          <button class="remote-btn btn-media" id="r-btn-rew" title="Indietro Veloce">${icon('rewind', { size: 14 })}</button>
          <button class="remote-btn btn-media btn-play" id="r-btn-play" title="Play">${icon('play', { size: 14, fill: 'currentColor' })}</button>
          <button class="remote-btn btn-media" id="r-btn-pause" title="Pausa">${icon('pause', { size: 14, fill: 'currentColor' })}</button>
          <button class="remote-btn btn-media" id="r-btn-ff" title="Avanti Veloce">${icon('fast-forward', { size: 14 })}</button>
          <button class="remote-btn btn-media" id="r-btn-stop" title="Stop">${icon('square', { size: 13, fill: 'currentColor' })}</button>
        </div>

        <!-- Tasti Rapidi Piattaforme Streaming con Loghi Ufficiali -->
        <div class="remote-brand-buttons">
          <button class="remote-app-btn app-netflix" data-source="Netflix" title="Apri Netflix">
            <img src="/logos/netflix.svg" class="remote-app-logo" alt="Netflix" />
          </button>
          <button class="remote-app-btn app-prime" data-source="Prime Video" title="Apri Prime Video">
            <img src="/logos/prime-video.svg" class="remote-app-logo" alt="Prime Video" />
          </button>
          <button class="remote-app-btn app-disney" data-source="Disney+" title="Apri Disney+">
            <img src="/logos/disney-plus.svg" class="remote-app-logo" alt="Disney+" />
          </button>
          <button class="remote-app-btn app-youtube" data-source="YouTube" title="Apri YouTube">
            <img src="/logos/youtube.svg" class="remote-app-logo" alt="YouTube" />
          </button>
        </div>

        <!-- Sezione Messaggio su schermo TV e Browser -->
        <div class="remote-advanced-section">
          <div class="advanced-title">Messaggio su schermo TV</div>
          
          <div class="advanced-input-group">
            <input type="text" id="r-input-toast" name="r-input-toast" aria-label="Messaggio da mostrare su schermo TV" placeholder="Scrivi messaggio per la TV..." class="remote-text-input" />
            <button type="button" class="btn-action-sm" id="r-btn-send-toast">Invia</button>
          </div>

          <div class="advanced-input-group">
            <input type="text" id="r-input-url" name="r-input-url" aria-label="Indirizzo web da aprire sulla TV" value="https://www.google.com" placeholder="https://..." class="remote-text-input" />
            <button type="button" class="btn-action-sm" id="r-btn-open-url">Apri Web</button>
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
    return this.container;
  }

  bindEvents() {
    // 1. Accensione / Spegnimento TV
    const powerBtn = this.container.querySelector('#r-btn-power');
    powerBtn.addEventListener('click', () => {
      this.controller.togglePower();
    });

    // 2. Spegnimento / Accensione schermo (Eco)
    const screenBtn = this.container.querySelector('#r-btn-screen-toggle');
    screenBtn.addEventListener('click', () => {
      this.controller.toggleScreenDisplay();
    });

    // 3. Selezione Ingresso (Switch input)
    const inputBtn = this.container.querySelector('#r-btn-input');
    inputBtn.addEventListener('click', () => {
      this.controller.sendWebOSCommand(WEBOS_COMMANDS.SET_INPUT);
    });

    // 4. Tastierino Numerico
    this.container.querySelectorAll('.btn-num').forEach((btn) => {
      btn.addEventListener('click', () => {
        const num = btn.dataset.num;
        this.controller.sendKeyInput(num);
      });
    });

    const delBtn = this.container.querySelector('#r-btn-del');
    delBtn.addEventListener('click', () => {
      this.controller.sendWebOSCommand(WEBOS_COMMANDS.SEND_DELETE);
    });

    // 5. Volume e Mute
    this.container.querySelector('#r-btn-vol-up').addEventListener('click', () => {
      this.controller.volumeUp();
    });
    this.container.querySelector('#r-btn-vol-down').addEventListener('click', () => {
      this.controller.volumeDown();
    });
    this.container.querySelector('#r-btn-mute').addEventListener('click', () => {
      this.controller.toggleMute();
    });

    // 6. Canali TV
    this.container.querySelector('#r-btn-ch-up').addEventListener('click', () => {
      this.controller.channelUp();
    });
    this.container.querySelector('#r-btn-ch-down').addEventListener('click', () => {
      this.controller.channelDown();
    });

    // 7. Navigazione D-Pad & Wheel
    this.container.querySelector('#r-btn-nav-up').addEventListener('click', () => this.controller.sendButton('UP'));
    this.container.querySelector('#r-btn-nav-down').addEventListener('click', () => this.controller.sendButton('DOWN'));
    this.container.querySelector('#r-btn-nav-left').addEventListener('click', () => this.controller.sendButton('LEFT'));
    this.container.querySelector('#r-btn-nav-right').addEventListener('click', () => this.controller.sendButton('RIGHT'));
    this.container.querySelector('#r-btn-nav-ok').addEventListener('click', () => {
      this.controller.sendWebOSCommand(WEBOS_COMMANDS.SEND_ENTER);
    });

    this.container.querySelector('#r-btn-home').addEventListener('click', () => {
      this.controller.sendButton('HOME');
    });
    this.container.querySelector('#r-btn-back').addEventListener('click', () => {
      this.controller.sendButton('BACK');
    });

    // 8. Controlli Media Playback
    this.container.querySelector('#r-btn-play').addEventListener('click', () => {
      this.controller.sendWebOSCommand(WEBOS_COMMANDS.MEDIA_PLAY);
    });
    this.container.querySelector('#r-btn-pause').addEventListener('click', () => {
      this.controller.sendWebOSCommand(WEBOS_COMMANDS.MEDIA_PAUSE);
    });
    this.container.querySelector('#r-btn-stop').addEventListener('click', () => {
      this.controller.sendWebOSCommand(WEBOS_COMMANDS.MEDIA_STOP);
    });
    this.container.querySelector('#r-btn-rew').addEventListener('click', () => {
      this.controller.sendWebOSCommand(WEBOS_COMMANDS.MEDIA_REWIND);
    });
    this.container.querySelector('#r-btn-ff').addEventListener('click', () => {
      this.controller.sendWebOSCommand(WEBOS_COMMANDS.MEDIA_FAST_FORWARD);
    });

    // 9. Tasti Rapidi App Streaming
    this.container.querySelectorAll('.remote-app-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const source = btn.dataset.source;
        this.controller.selectSource(source);
      });
    });

    // 10. Funzioni Avanzate webOS (Toast e Web URL)
    const toastInput = this.container.querySelector('#r-input-toast');
    const toastBtn = this.container.querySelector('#r-btn-send-toast');
    toastBtn.addEventListener('click', () => {
      const msg = toastInput.value.trim();
      if (msg) {
        this.controller.showToast(msg);
        toastInput.value = '';
      }
    });

    const urlInput = this.container.querySelector('#r-input-url');
    const urlBtn = this.container.querySelector('#r-btn-open-url');
    urlBtn.addEventListener('click', () => {
      const url = urlInput.value.trim();
      if (url) {
        this.controller.openUrl(url);
      }
    });
  }
}

