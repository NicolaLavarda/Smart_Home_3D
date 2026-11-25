import { AVAILABLE_SOURCES } from './webos_commands.js';
import { TVRemote } from './TVRemote.js';
import { icon } from '../../ui/icons.js';

/**
 * TVModal
 * 
 * Gestisce l'interfaccia utente completa per il controllo della TV:
 * - Stato live di riproduzione (Titolo film, canale DVB-T2, app attiva)
 * - Accensione tramite Wake-on-LAN e Spegnimento controllato
 * - Regolazione volume continua e mute
 * - Switch rapido tra sorgenti e canali popolari
 * - Pannello espandibile con il Telecomando Virtuale completo
 */
export class TVModal {
  constructor(tvController) {
    this.controller = tvController;
    this.remoteView = new TVRemote(tvController);
    this.container = null;
  }

  render(container) {
    this.container = container;
    const entity = this.controller.getEntity();
    const isPoweredOn = this.controller.isPoweredOn();
    const isPlaying = isPoweredOn && entity.state === 'playing';
    const volume = Math.round((entity.attributes?.volume_level ?? 0.45) * 100);
    const isMuted = entity.attributes?.is_volume_muted || false;
    const source = isPoweredOn
      ? (entity.attributes?.source || entity.attributes?.app_name || 'Live TV')
      : 'Standby / Spenta';
    const mediaTitle = isPoweredOn
      ? (entity.attributes?.media_title || entity.attributes?.media_channel || 'LG webOS Smart Hub')
      : 'TV Spenta';
    const channelName = isPoweredOn
      ? (entity.attributes?.media_channel || 'LG webOS Smart Hub')
      : 'Disconnessa dalla rete (Standby)';
    const statusText = isPoweredOn ? String(entity.state).toUpperCase() : 'SPENTA';

    // Helper per recuperare il logo SVG ufficiale del servizio
    const getServiceLogo = (s, on) => {
      if (!on) return '/logos/lg-webos.svg';
      const lower = s.toLowerCase();
      if (lower.includes('netflix')) return '/logos/netflix-n.svg';
      if (lower.includes('prime') || lower.includes('amazon')) return '/logos/prime-video.svg';
      if (lower.includes('youtube')) return '/logos/youtube.svg';
      if (lower.includes('disney')) return '/logos/disney-plus.svg';
      if (lower.includes('spotify') || lower.includes('musica')) return '/logos/spotify.svg';
      if (lower.includes('rai 1') || lower.includes('rai1')) return '/logos/rai1.svg';
      if (lower.includes('raiplay') || lower.includes('rai')) return '/logos/raiplay.svg';
      if (lower.includes('mediaset') || lower.includes('infinity')) return '/logos/mediaset.svg';
      if (lower.includes('browser') || lower.includes('google') || lower.includes('web')) return '/logos/google.svg';
      if (lower.includes('hdmi')) return '/logos/hdmi.svg';
      return '/logos/livetv.svg';
    };

    container.innerHTML = `
      <!-- Stato Riproduzione Corrente -->
      <div class="tv-now-playing-card">
        <div class="now-playing-header">
          <span class="tv-source-pill">
            <img src="${getServiceLogo(source, isPoweredOn)}" class="pill-service-logo" alt="${source}" />
            <span>${source}</span>
          </span>
          <span class="ha-status-badge">
            <span class="ha-dot ${isPoweredOn ? 'online' : 'offline'}"></span>
            ${statusText}
          </span>
        </div>

        <div class="now-playing-title-box">
          <div class="now-playing-title">${mediaTitle}</div>
          <div class="now-playing-channel">${channelName}</div>
        </div>

        ${isPoweredOn ? `
          <div class="tv-media-actions">
            <button type="button" class="btn-action-primary tv-play-action-btn" id="tv-modal-play-btn">
              ${isPlaying ? `${icon('pause', { size: 14 })} <span>Sospendi</span>` : `${icon('play', { size: 14 })} <span>Riproduci</span>`}
            </button>
            <button type="button" class="btn-icon-text tv-stop-action-btn" id="tv-modal-stop-btn" title="Stop" aria-label="Ferma riproduzione">
              ${icon('square', { size: 14, fill: 'currentColor' })}
            </button>
          </div>
        ` : ''}
      </div>

      <!-- Accensione / Spegnimento -->
      <div class="control-row tv-power-row">
        <div class="tv-power-copy">
          <div class="tv-power-title">Alimentazione TV</div>
          <div class="tv-power-sub">
            ${isPoweredOn ? 'Accesa • Connessa alla rete' : 'Spenta / Standby • Pronta per accensione'}
          </div>
        </div>
        <button type="button" class="${isPoweredOn ? 'btn-power-off' : 'btn-power-on'}" id="tv-modal-power-btn">
          ${icon('power', { size: 14 })} <span>${isPoweredOn ? 'Spegni TV' : 'Accendi'}</span>
        </button>
      </div>

      <!-- Controllo Volume & Mute -->
      <section class="modal-section">
        <div class="tv-volume-head">
          <div class="tv-volume-label-wrap">
            <label for="tv-modal-volume-slider" class="modal-section-title">Volume</label>
            <button type="button" class="btn-mute-toggle ${isMuted ? 'muted' : ''}" id="tv-modal-mute-btn" title="Muto">
              ${isMuted ? `${icon('volume-x', { size: 13 })} <span>Muto</span>` : `${icon('volume-2', { size: 13 })} <span>Attivo</span>`}
            </button>
          </div>
          <span id="tv-modal-vol-label" class="control-row-value">${volume}%</span>
        </div>
        <div class="tv-volume-slider-row">
          <button type="button" class="btn-vol-step" id="tv-modal-vol-down" aria-label="Abbassa volume">-</button>
          <input type="range" min="0" max="100" value="${volume}" id="tv-modal-volume-slider" name="tv-modal-volume-slider" class="timeline-slider tv-volume-slider" />
          <button type="button" class="btn-vol-step" id="tv-modal-vol-up" aria-label="Alza volume">+</button>
        </div>
      </section>

      <!-- Selezione Rapida Sorgenti con Loghi Ufficiali -->
      <section class="modal-section">
        <h4 class="modal-section-title">Seleziona Sorgente / App</h4>
        <div class="tv-sources-grid">
          <button class="source-chip ${source === 'Live TV' ? 'active' : ''}" data-source="Live TV">
            <img src="/logos/livetv.svg" class="chip-service-logo" alt="Live TV" />
            <span>Live TV</span>
          </button>
          <button class="source-chip ${source === 'Netflix' ? 'active' : ''}" data-source="Netflix">
            <img src="/logos/netflix-n.svg" class="chip-service-logo" alt="Netflix" />
            <span>Netflix</span>
          </button>
          <button class="source-chip ${source === 'Prime Video' ? 'active' : ''}" data-source="Prime Video">
            <img src="/logos/prime-video.svg" class="chip-service-logo" alt="Prime Video" />
            <span>Prime</span>
          </button>
          <button class="source-chip ${source === 'YouTube' ? 'active' : ''}" data-source="YouTube">
            <img src="/logos/youtube.svg" class="chip-service-logo" alt="YouTube" />
            <span>YouTube</span>
          </button>
          <button class="source-chip ${source === 'Disney+' ? 'active' : ''}" data-source="Disney+">
            <img src="/logos/disney-plus.svg" class="chip-service-logo" alt="Disney+" />
            <span>Disney+</span>
          </button>
          <button class="source-chip ${source === 'RaiPlay' ? 'active' : ''}" data-source="RaiPlay">
            <img src="/logos/raiplay.svg" class="chip-service-logo" alt="RaiPlay" />
            <span>RaiPlay</span>
          </button>
          <button class="source-chip ${source.includes('Spotify') ? 'active' : ''}" data-source="Spotify - Musica e podcast">
            <img src="/logos/spotify.svg" class="chip-service-logo" alt="Spotify" />
            <span>Spotify</span>
          </button>
          <button class="source-chip ${source === 'Browser Web' ? 'active' : ''}" data-source="Browser Web">
            <img src="/logos/google.svg" class="chip-service-logo" alt="Browser" />
            <span>Browser</span>
          </button>
          <button class="source-chip ${source === 'HDMI 1' ? 'active' : ''}" data-source="HDMI 1">
            <img src="/logos/hdmi.svg" class="chip-service-logo" alt="HDMI 1" />
            <span>HDMI 1</span>
          </button>
        </div>
      </section>

      <!-- Telecomando Virtuale sempre visibile -->
      <div class="remote-collapsible-wrapper open" id="remote-slot">
      </div>
    `;

    // Inietta sempre il telecomando virtuale
    const remoteSlot = container.querySelector('#remote-slot');
    if (remoteSlot) {
      remoteSlot.appendChild(this.remoteView.render());
    }

    this.bindEvents(container);
  }

  bindEvents(container) {
    // 1. Accensione / Spegnimento
    const powerBtn = container.querySelector('#tv-modal-power-btn');
    if (powerBtn) {
      powerBtn.addEventListener('click', () => {
        const wasOn = this.controller.isPoweredOn();
        if (wasOn) {
          powerBtn.innerHTML = `${icon('power', { size: 14 })} <span>Spegnimento...</span>`;
          powerBtn.disabled = true;
          this.controller.turnOff();
        } else {
          powerBtn.innerHTML = `${icon('zap', { size: 14 })} <span>Accensione TV in corso...</span>`;
          powerBtn.disabled = true;
          this.controller.turnOn();
        }
        setTimeout(() => this.render(container), 600);
      });
    }

    // 2. Play / Pause
    const playBtn = container.querySelector('#tv-modal-play-btn');
    if (playBtn) {
      playBtn.addEventListener('click', () => {
        this.controller.togglePlayPause();
        setTimeout(() => this.render(container), 200);
      });
    }

    // 3. Stop
    const stopBtn = container.querySelector('#tv-modal-stop-btn');
    if (stopBtn) {
      stopBtn.addEventListener('click', () => {
        this.controller.stopMedia();
        setTimeout(() => this.render(container), 200);
      });
    }

    // 4. Volume Slider e Bottoni Step
    const volSlider = container.querySelector('#tv-modal-volume-slider');
    const volLabel = container.querySelector('#tv-modal-vol-label');
    if (volSlider) {
      volSlider.addEventListener('input', (e) => {
        const v = parseInt(e.target.value, 10);
        volLabel.textContent = `${v}%`;
        this.controller.setVolume(v / 100);
      });
    }

    const volDown = container.querySelector('#tv-modal-vol-down');
    if (volDown) {
      volDown.addEventListener('click', () => {
        this.controller.volumeDown();
        setTimeout(() => this.render(container), 150);
      });
    }

    const volUp = container.querySelector('#tv-modal-vol-up');
    if (volUp) {
      volUp.addEventListener('click', () => {
        this.controller.volumeUp();
        setTimeout(() => this.render(container), 150);
      });
    }

    const muteBtn = container.querySelector('#tv-modal-mute-btn');
    if (muteBtn) {
      muteBtn.addEventListener('click', () => {
        this.controller.toggleMute();
        setTimeout(() => this.render(container), 150);
      });
    }

    // 5. Switch Rapido Sorgenti
    container.querySelectorAll('.source-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        const src = btn.dataset.source;
        this.controller.selectSource(src);
        setTimeout(() => this.render(container), 200);
      });
    });
  }

  updateLive() {
    if (this.controller.isModalOpen && this.container) {
      this.render(this.container);
    }
  }
}

