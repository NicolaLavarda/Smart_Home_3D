import { icon } from '../../ui/icons.js';

/**
 * SecurityCameraModal
 *
 * Pannello modale OOP per la telecamera di sicurezza Reolink RLC-540A (Cam_Carraio):
 * - Player live WebRTC / MSE a bassissima latenza via VideoStreamManager (go2rtc)
 * - Selettore flusso Main (5MP) / Sub (640x360) e riconnessione rapida
 * - Ingresso nella vista POV 3D esatta della telecamera
 * - Avvio dell'assistente di calibrazione ottica POV con overlay trasparente
 * - Toggle diretto della modalità CV sul microservizio spaziale (Simulatore / OpenVINO Live)
 */
export class SecurityCameraModal {
  constructor(controller) {
    this.controller = controller;
    this.container = null;
    this.videoEl = null;
    this.badgeEl = null;
    this.latencyEl = null;
    this.hintEl = null;
    this.endpointEl = null;
    this.activeStreamName = 'carraio_main';
    this.isSyntheticActive = true;
    this._unsubscribeStatus = null;
    this._unsubscribeAuth = null;
    this._camIp = '192.168.86.47';
    this._camName = 'Cam_Carraio';
  }

  async render(container, context = {}) {
    if (this._unsubscribeAuth) {
      this._unsubscribeAuth();
      this._unsubscribeAuth = null;
    }
    this.container = container;
    const camName = this.controller.findMatchingBlenderCameraName();
    const manifestCam = context.assetLoader?.manifest?.cameras?.[camName];
    const fovH = manifestCam?.fov_h_deg ?? 80;
    const fovV = manifestCam?.fov_v_deg ?? 42;
    const lensMm = manifestCam?.lens_mm ?? 4.0;
    const camIp = manifestCam?.camera_ip || '192.168.86.47';
    this._camIp = camIp;
    this._camName = camName;
    const haClient = this.controller.haClient || context.haClient;
    const isTailscale = Boolean(haClient?.isTailscale);
    const endpointLabel = isTailscale
      ? `Tailscale Bridge → ${camIp} • ${camName}`
      : `${camIp} • ${camName}`;

    // Controlla stato corrente del backend spaziale se disponibile
    let serverMode = 'synthetic';
    const spatialClient = this.controller.spatialStreamClient || context.spatialStreamClient;
    if (spatialClient) {
      const st = await spatialClient.fetchStatus().catch(() => null);
      if (st?.ingestion_mode) {
        serverMode = st.ingestion_mode;
      }
    }
    this.isSyntheticActive = serverMode === 'synthetic';

    container.innerHTML = `
      <div class="camera-preview-stream" id="cam-preview-wrapper">
        <video id="cam-modal-video" autoplay muted playsinline style="width:100%;height:100%;object-fit:cover;display:block;"></video>
        <span class="live-badge" id="cam-stream-badge">CONNESSIONE...</span>
        <span class="cam-latency-badge" id="cam-latency-badge">-- ms</span>
      </div>

      <div class="control-row" style="gap: 8px;">
        <div style="display:flex;gap:6px;flex:1;">
          <button class="btn-icon-text stream-quality-btn active" data-stream="carraio_main" style="flex:1;justify-content:center;padding:6px 8px;font-size:11px;">
            Main 5MP
          </button>
          <button class="btn-icon-text stream-quality-btn" data-stream="carraio_sub" style="flex:1;justify-content:center;padding:6px 8px;font-size:11px;">
            Sub 640×360
          </button>
        </div>
        <button class="btn-icon-text" id="btn-cam-reconnect" title="Riconnetti stream" style="padding:6px 10px;font-size:11px;">
          ${icon('refresh-cw', { size: 13 })} <span>Riconnetti</span>
        </button>
      </div>

      <div class="control-row">
        <label>Modello & Ottica SSoT</label>
        <span style="font-family:var(--font-mono);font-size:11px;color:var(--accent-cyan);">
          RLC-540A • ${lensMm}mm (${fovH}°×${fovV}°)
        </span>
      </div>

      <div class="control-row">
        <label>Endpoint Rete / Node 3D</label>
        <span id="cam-endpoint-label" style="font-family:var(--font-mono);font-size:11px;color:var(--text-main);">
          ${endpointLabel}
        </span>
      </div>

      <button class="btn-action-primary" id="btn-camera-pov" style="width:100%;">
        ${icon('crosshair', { size: 15 })} <span>Entra in Vista POV 3D</span>
      </button>

      <button class="btn-icon-text" id="btn-camera-calibrate" hidden disabled style="width:100%;justify-content:center;border-color:rgba(6,182,212,0.45);color:#38bdf8;display:none;">
        ${icon('sliders-horizontal', { size: 15 })} <span>Apri Calibrazione Ottica POV</span>
      </button>

      <button class="btn-icon-text" id="btn-toggle-simulator" hidden disabled style="width:100%;justify-content:center;display:none;">
        ${this.isSyntheticActive
          ? `${icon('brain', { size: 15 })} <span>Passa a Rilevamento OpenVINO Live</span>`
          : `${icon('footprints', { size: 15 })} <span>Avvia Simulatore Camminata 3D</span>`}
      </button>

      <div id="cam-status-hint" style="font-size:11px;color:var(--text-muted);line-height:1.45;text-align:center;">
        Streaming gestito da go2rtc (WebRTC → MSE → Snapshot Fallback).
      </div>
    `;

    this.videoEl = container.querySelector('#cam-modal-video');
    this.badgeEl = container.querySelector('#cam-stream-badge');
    this.latencyEl = container.querySelector('#cam-latency-badge');
    this.hintEl = container.querySelector('#cam-status-hint');
    this.endpointEl = container.querySelector('#cam-endpoint-label');

    await this.connectStream(this.activeStreamName);

    // Qualità Main / Sub
    container.querySelectorAll('.stream-quality-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        container.querySelectorAll('.stream-quality-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        this.activeStreamName = btn.dataset.stream;
        await this.connectStream(this.activeStreamName);
      });
    });

    // Riconnetti
    container.querySelector('#btn-cam-reconnect')?.addEventListener('click', () => {
      this.connectStream(this.activeStreamName);
    });

    // Vista POV 3D
    const povBtn = container.querySelector('#btn-camera-pov');
    const camNode = context.assetLoader?.cameras?.get(camName);
    const camCtrl = this.controller.cameraController || context.cameraController;
    if (camNode && camCtrl) {
      povBtn.addEventListener('click', () => {
        camCtrl.flyToCameraPOV(camNode, 1.4, () => {
          context.modal?.close();
        });
      });
    } else {
      povBtn.disabled = true;
      povBtn.textContent = 'Camera POV non trovata nella scena';
    }

    // Apri Calibrazione Ottica POV (solo Admin)
    const calibBtn = container.querySelector('#btn-camera-calibrate');
    const simBtn = container.querySelector('#btn-toggle-simulator');

    const applyRbacVisibility = (adminFlag) => {
      const allowed = Boolean(adminFlag);
      if (calibBtn) {
        calibBtn.hidden = !allowed;
        calibBtn.disabled = !allowed;
        calibBtn.style.display = allowed ? '' : 'none';
      }
      if (simBtn) {
        simBtn.hidden = !allowed;
        simBtn.disabled = !allowed;
        simBtn.style.display = allowed ? '' : 'none';
      }
    };
    applyRbacVisibility(haClient?.isAdmin);
    if (typeof haClient?.onAuthChange === 'function') {
      this._unsubscribeAuth = haClient.onAuthChange((authState) => {
        applyRbacVisibility(authState?.isAdmin ?? haClient?.isAdmin);
      });
    }

    calibBtn?.addEventListener('click', async () => {
      if (!haClient?.isAdmin) return;
      const calibUI = this.controller.calibrationAssistant;
      if (camNode && camCtrl) {
        camCtrl.flyToCameraPOV(camNode, 1.3, () => {
          if (calibUI) {
            calibUI.open(camName);
          }
          context.modal?.close();
        });
      } else if (calibUI) {
        calibUI.open(camName);
        context.modal?.close();
      }
    });

    // Toggle Simulatore / OpenVINO (solo Admin)
    simBtn?.addEventListener('click', async () => {
      if (!haClient?.isAdmin) return;
      const client = this.controller.spatialStreamClient || context.spatialStreamClient;
      if (!client) {
        this.hintEl.textContent = 'Microservizio spaziale non collegato (porta 8765).';
        return;
      }
      const nextMode = this.isSyntheticActive ? 'openvino' : 'synthetic';
      const res = await client.setIngestionMode(nextMode);
      if (res && res.status === 'ok') {
        this.isSyntheticActive = res.ingestion_mode === 'synthetic';
        simBtn.innerHTML = this.isSyntheticActive
          ? `${icon('brain', { size: 15 })} <span>Passa a Rilevamento OpenVINO Live</span>`
          : `${icon('footprints', { size: 15 })} <span>Avvia Simulatore Camminata 3D</span>`;
        this.hintEl.textContent = `Modalità CV attiva: ${res.ingestion_mode.toUpperCase()}`;
      } else {
        this.hintEl.textContent = 'Backend spaziale offline: impossibile cambiare modalità CV.';
      }
    });
  }

  updateStreamStatusUI(status) {
    if (!this.badgeEl || !this.hintEl) return;
    const isTailscale = Boolean(status.isTailscale || this.controller.haClient?.isTailscale);

    if (status.mode === 'webrtc') {
      this.badgeEl.textContent = 'WEBRTC LIVE';
      this.badgeEl.style.background = 'rgba(16, 185, 129, 0.92)';
      this.hintEl.textContent = `Stream reale a bassa latenza (${this.activeStreamName}) connesso via WebRTC.`;
      if (this.endpointEl) {
        this.endpointEl.textContent = isTailscale
          ? `Tailscale Direct → ${this._camIp} • ${this._camName}`
          : `${this._camIp} • ${this._camName}`;
      }
    } else if (status.mode === 'mse') {
      this.badgeEl.textContent = 'MSE LIVE';
      this.badgeEl.style.background = 'rgba(6, 182, 212, 0.92)';
      this.hintEl.textContent = `Stream reale connesso via go2rtc MSE (${this.activeStreamName}).`;
      if (this.endpointEl) {
        this.endpointEl.textContent = isTailscale
          ? `Tailscale Direct → ${this._camIp} • ${this._camName}`
          : `${this._camIp} • ${this._camName}`;
      }
    } else if (status.hasLiveHaFrames) {
      if (isTailscale) {
        this.badgeEl.textContent = 'HA TAILSCALE LIVE';
        this.badgeEl.style.background = 'rgba(16, 185, 129, 0.92)';
        this.hintEl.textContent = `Streaming remoto attivo via Home Assistant Tailscale Bridge (${status.resolvedEntityId || 'camera'}).`;
      } else {
        this.badgeEl.textContent = 'HA PROXY LIVE';
        this.badgeEl.style.background = 'rgba(6, 182, 212, 0.92)';
        this.hintEl.textContent = `Stream attivo tramite proxy Home Assistant (${status.resolvedEntityId || 'camera'}).`;
      }
      if (this.endpointEl) {
        this.endpointEl.textContent = isTailscale
          ? `Tailscale Bridge → ${this._camIp} • ${this._camName}`
          : `HA Proxy → ${this._camIp} • ${this._camName}`;
      }
    } else if (isTailscale) {
      this.badgeEl.textContent = 'TAILSCALE • ATTESA BRIDGE';
      this.badgeEl.style.background = 'rgba(99, 102, 241, 0.9)';
      this.hintEl.textContent = 'Connesso via Tailscale: in attesa frame da HA Bridge (oppure attiva Subnet Router 192.168.86.0/24).';
      if (this.endpointEl) {
        this.endpointEl.textContent = `Tailscale Bridge → ${this._camIp} • ${this._camName}`;
      }
    } else {
      this.badgeEl.textContent = 'SIMULAZIONE / ATTESA CREDENZIALI REOLINK';
      this.badgeEl.style.background = 'rgba(99, 102, 241, 0.9)';
      this.hintEl.textContent = 'Reolink non raggiungibile o credenziali mancanti in .env: attivo feed diagnostico.';
    }

    if (this.latencyEl) {
      this.latencyEl.textContent = `${status.latencyMs ?? 0} ms`;
    }
  }

  async connectStream(streamName) {
    const vsm = this.controller.videoStreamManager;
    if (!vsm || !this.videoEl) return;

    if (this._unsubscribeStatus) {
      this._unsubscribeStatus();
      this._unsubscribeStatus = null;
    }

    this.badgeEl.textContent = 'CONNESSIONE...';
    this.badgeEl.style.background = 'rgba(245, 158, 11, 0.9)';

    try {
      const provider = await vsm.attachToVideoElement(streamName, this.videoEl, 'auto');
      this.updateStreamStatusUI(provider.getStatus());

      if (typeof provider.onStatusChange === 'function') {
        this._unsubscribeStatus = provider.onStatusChange((st) => {
          if (this.container && st.connected) {
            this.updateStreamStatusUI(st);
          }
        });
      }
    } catch (err) {
      this.badgeEl.textContent = 'OFFLINE';
      this.badgeEl.style.background = 'rgba(239, 68, 68, 0.9)';
    }
  }

  destroy() {
    if (this._unsubscribeStatus) {
      this._unsubscribeStatus();
      this._unsubscribeStatus = null;
    }
    if (this._unsubscribeAuth) {
      this._unsubscribeAuth();
      this._unsubscribeAuth = null;
    }
    if (this.videoEl && this.controller.videoStreamManager) {
      this.controller.videoStreamManager.detachFromVideoElement(this.videoEl);
    }
    this.videoEl = null;
    this.badgeEl = null;
    this.latencyEl = null;
    this.hintEl = null;
    this.endpointEl = null;
    this.container = null;
  }
}

