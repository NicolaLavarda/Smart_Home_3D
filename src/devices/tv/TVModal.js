import { AVAILABLE_SOURCES } from './webos_commands.js';
import { TVRemote } from './TVRemote.js';

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
    this.isRemoteExpanded = false;
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
            <button class="btn-action-primary" id="tv-modal-play-btn" style="flex: 1;">
              ${isPlaying ? '⏸ Sospendi' : '▶ Riproduci'}
            </button>
            <button class="btn-icon-text" id="tv-modal-stop-btn" style="padding: 10px 14px;">
              ⏹
            </button>
          </div>
        ` : ''}
      </div>

      <!-- Accensione Wake-on-LAN / Spegnimento -->
      <div class="control-row tv-power-row">
        <div>
          <div style="font-weight: 600; font-size: 13px;">Alimentazione TV</div>
          <div style="font-size: 11px; color: var(--text-muted);">
            ${isPoweredOn ? 'Accesa • Connessa alla rete' : 'Spenta / Standby • Avvio tramite Wake-on-LAN'}
          </div>
        </div>
        <button class="${isPoweredOn ? 'btn-power-off' : 'btn-power-on'}" id="tv-modal-power-btn">
          ${isPoweredOn ? '⏻ Spegni TV' : '⏻ Accendi'}
        </button>
      </div>

      <!-- Controllo Volume & Mute -->
      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <label style="margin: 0;">Volume</label>
            <button class="btn-mute-toggle ${isMuted ? 'muted' : ''}" id="tv-modal-mute-btn" title="Muto">
              ${isMuted ? '🔇 Muto' : '🔊 Attivo'}
            </button>
          </div>
          <span id="tv-modal-vol-label" style="font-size: 12px; font-family: var(--font-mono);">${volume}%</span>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <button class="btn-vol-step" id="tv-modal-vol-down">-</button>
          <input type="range" min="0" max="100" value="${volume}" id="tv-modal-volume-slider" class="timeline-slider" style="flex: 1;" />
          <button class="btn-vol-step" id="tv-modal-vol-up">+</button>
        </div>
      </div>

      <!-- Selezione Rapida Sorgenti con Loghi Ufficiali -->
      <div class="control-row" style="flex-direction: column; align-items: stretch; gap: 8px;">
        <label>Seleziona Sorgente / App</label>
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
      </div>

      <!-- Pulsante per Mostrare/Nascondere il Telecomando Virtuale -->
      <button class="btn-remote-toggle ${this.isRemoteExpanded ? 'expanded' : ''}" id="btn-toggle-remote">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px;"><rect x="6" y="2" width="12" height="20" rx="3"></rect><circle cx="12" cy="7" r="1"></circle><circle cx="12" cy="11" r="1"></circle><circle cx="12" cy="15" r="1"></circle></svg>
        <span>${this.isRemoteExpanded ? 'Chiudi Telecomando LG' : 'Apri Telecomando LG Magic Remote'}</span>
      </button>

      <!-- Contenitore Telecomando a scomparsa -->
      <div class="remote-collapsible-wrapper ${this.isRemoteExpanded ? 'open' : ''}" id="remote-slot">
      </div>
    `;

    // Inietta il telecomando se espanso
    const remoteSlot = container.querySelector('#remote-slot');
    if (this.isRemoteExpanded) {
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
          powerBtn.textContent = '⏻ Spegnimento...';
          powerBtn.disabled = true;
          this.controller.turnOff();
        } else {
          powerBtn.textContent = '⚡ Invio pacchetto WoL...';
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

    // 6. Toggle Telecomando Virtuale
    const remoteToggle = container.querySelector('#btn-toggle-remote');
    if (remoteToggle) {
      remoteToggle.addEventListener('click', () => {
        this.isRemoteExpanded = !this.isRemoteExpanded;
        this.render(container);
      });
    }
  }

  updateLive() {
    if (this.container) {
      this.render(this.container);
    }
  }
}

