import * as THREE from 'three';
import { icon } from '../../ui/icons.js';

const STORAGE_KEY = 'sh3d_camera_calibration_v2';

/**
 * CalibrationAssistantUI
 *
 * Pannello interattivo per la calibrazione geometrica Camera-to-World in vista POV:
 * - Sovrappone il video live della Reolink RLC-540A al modello 3D con opacità 0%-100%
 * - Regola in tempo reale Yaw, Pitch, Roll, Offset XYZ, FOV e distorsione k1/k2
 * - Offre il tasto 1-click "Inverti Direzione 180°" (Vialetto Interno <-> Strada Esterna)
 * - Supporta la raccolta di coppie di punti 3D-2D per SolvePnPRansac sul backend Python
 */
export class CalibrationAssistantUI {
  constructor({ sceneManager, cameraController, cameraProjector, videoStreamManager, spatialStreamClient, assetLoader }) {
    this.sceneManager = sceneManager;
    this.cameraController = cameraController;
    this.cameraProjector = cameraProjector;
    this.videoStreamManager = videoStreamManager;
    this.spatialStreamClient = spatialStreamClient;
    this.assetLoader = assetLoader;

    this.isOpen = false;
    this.activeCameraName = 'Cam_Carraio';
    this.streamName = 'carraio_main';
    this.panelEl = null;
    this.videoTextureEntry = null;
    this.overlayOpacity = 0.52;

    // Modalità raccolta corrispondenze PnP 3D <-> 2D
    this.pnpMode = false;
    this.pnpStep = '3d'; // '3d' -> '2d'
    this.pendingPoint3D = null;
    this.correspondences = [];
    this.raycaster = new THREE.Raycaster();

    this.state = this.createDefaultState();
    this._onCanvasClick = this.handleCanvasClick.bind(this);
    this._onKeyDown = (e) => {
      if (e.key === 'Escape' && this.isOpen) this.close();
    };
    this.onOpenCallback = null;
    this.onCloseCallback = null;
  }

  setLifecycleHooks({ onOpen, onClose } = {}) {
    this.onOpenCallback = typeof onOpen === 'function' ? onOpen : null;
    this.onCloseCallback = typeof onClose === 'function' ? onClose : null;
  }

  createDefaultState() {
    return {
      offsetX: 0.0,
      offsetY: 0.0,
      offsetZ: 0.0,
      yawDeg: 0.0,
      pitchDeg: 0.0,
      rollDeg: 0.0,
      fovV: 42.0,
      fovH: 80.0,
      k1: -0.18,
      k2: 0.04,
      flip180: false,
    };
  }

  loadSavedState(cameraName) {
    try {
      const raw = localStorage.getItem(`${STORAGE_KEY}_${cameraName}`);
      if (raw) {
        return { ...this.createDefaultState(), ...JSON.parse(raw) };
      }
    } catch {}

    const manifestCam = this.assetLoader?.manifest?.cameras?.[cameraName];
    const dist = manifestCam?.distortion_coeffs || [-0.18, 0.04, 0, 0, 0];
    return {
      ...this.createDefaultState(),
      fovV: manifestCam?.fov_v_deg ?? 42.0,
      fovH: manifestCam?.fov_h_deg ?? 80.0,
      k1: dist[0] ?? -0.18,
      k2: dist[1] ?? 0.04,
    };
  }

  saveStateToLocal(cameraName) {
    try {
      localStorage.setItem(`${STORAGE_KEY}_${cameraName}`, JSON.stringify(this.state));
    } catch {}
  }

  async open(cameraName = 'Cam_Carraio') {
    this.activeCameraName = cameraName;
    this.state = this.loadSavedState(cameraName);

    const manifestCam = this.assetLoader?.manifest?.cameras?.[cameraName];
    this.streamName = manifestCam?.stream_id || 'carraio_main';

    if (!this.panelEl) {
      this.createDOM();
    }
    this.isOpen = true;
    this.setCollapsed(false);
    this.panelEl.classList.add('open');
    this.syncInputsFromState();
    this.onOpenCallback?.(cameraName);
    window.addEventListener('keydown', this._onKeyDown);

    // Collega VideoTexture live sul frustum 3D
    try {
      this.videoTextureEntry = await this.videoStreamManager.acquireVideoTexture(this.streamName);
      this.cameraProjector.attachOverlayTexture(cameraName, this.videoTextureEntry.texture);
      this.cameraProjector.setOverlayPOVMode(cameraName, true, this.overlayOpacity);
    } catch (err) {
      console.warn('[CalibrationAssistantUI] Impossibile collegare VideoTexture:', err);
    }

    // Applica immediatamente la calibrazione corrente alla scena + vista POV
    this.applyLiveCalibration(true);

    // Abilita listener click sul canvas per eventuali corrispondenze PnP
    this.sceneManager.renderer.domElement.addEventListener('click', this._onCanvasClick);
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this.pnpMode = false;
    if (this.panelEl) {
      this.panelEl.classList.remove('open');
      this.setCollapsed(false);
    }

    this.cameraProjector.setOverlayPOVMode(this.activeCameraName, false, 0);
    if (this.videoTextureEntry) {
      this.videoStreamManager.releaseVideoTexture(this.streamName);
      this.videoTextureEntry = null;
    }

    this.sceneManager.renderer.domElement.removeEventListener('click', this._onCanvasClick);
    window.removeEventListener('keydown', this._onKeyDown);
    this.onCloseCallback?.();
  }

  createDOM() {
    const uiLayer = document.querySelector('.ui-layer');
    const panel = document.createElement('div');
    panel.className = 'calibration-panel glass';
    panel.id = 'calibration-assistant-panel';
    panel.innerHTML = `
      <div class="calib-header" id="calib-header-toggle" title="Clicca per comprimere / espandere">
        <div class="calib-title-wrap">
          <div class="calib-title">${icon('sliders-horizontal', { size: 14 })} <span>Calibrazione Ottica POV</span></div>
          <div class="calib-subtitle" id="calib-cam-name">Cam_Carraio • Reolink RLC-540A</div>
        </div>
        <div class="modal-header-actions">
          <span class="modal-collapse-chevron" id="calib-collapse-icon">${icon('chevron-up', { size: 15 })}</span>
          <button class="btn-close" id="calib-close-btn" title="Chiudi Calibrazione">${icon('x', { size: 15 })}</button>
        </div>
      </div>

      <div class="calib-body" id="calib-content">
        <div class="calib-section">
          <div class="calib-row-label">
            <span>Opacità Overlay Video Live</span>
            <span id="calib-val-opacity" class="calib-num">52%</span>
          </div>
          <input type="range" id="calib-opacity" min="0" max="100" value="52" class="timeline-slider" />
        </div>

        <div class="calib-actions-row">
          <button class="btn-icon-text" id="calib-flip-180" style="flex:1;justify-content:center;font-size:11px;">
            ${icon('refresh-cw', { size: 14 })} <span>Inverti Direzione 180° (Vialetto ↔ Strada)</span>
          </button>
        </div>

        <div class="calib-grid">
          <div class="calib-slider-box">
            <div class="calib-row-label"><span>Yaw Δ (°)</span><span id="calib-val-yaw" class="calib-num">0.0°</span></div>
            <input type="range" id="calib-yaw" min="-180" max="180" step="0.5" value="0" class="timeline-slider" />
          </div>
          <div class="calib-slider-box">
            <div class="calib-row-label"><span>Pitch Δ (°)</span><span id="calib-val-pitch" class="calib-num">0.0°</span></div>
            <input type="range" id="calib-pitch" min="-45" max="45" step="0.5" value="0" class="timeline-slider" />
          </div>
          <div class="calib-slider-box">
            <div class="calib-row-label"><span>Roll Δ (°)</span><span id="calib-val-roll" class="calib-num">0.0°</span></div>
            <input type="range" id="calib-roll" min="-30" max="30" step="0.5" value="0" class="timeline-slider" />
          </div>
          <div class="calib-slider-box">
            <div class="calib-row-label"><span>FOV Vert. (°)</span><span id="calib-val-fov" class="calib-num">42.0°</span></div>
            <input type="range" id="calib-fov" min="20" max="110" step="0.5" value="42" class="timeline-slider" />
          </div>
        </div>

        <div class="calib-grid-3">
          <div class="calib-slider-box">
            <div class="calib-row-label"><span>Off X (m)</span><span id="calib-val-ox" class="calib-num">0.00</span></div>
            <input type="range" id="calib-ox" min="-2.0" max="2.0" step="0.02" value="0" class="timeline-slider" />
          </div>
          <div class="calib-slider-box">
            <div class="calib-row-label"><span>Off Y (m)</span><span id="calib-val-oy" class="calib-num">0.00</span></div>
            <input type="range" id="calib-oy" min="-2.0" max="2.0" step="0.02" value="0" class="timeline-slider" />
          </div>
          <div class="calib-slider-box">
            <div class="calib-row-label"><span>Off Z (m)</span><span id="calib-val-oz" class="calib-num">0.00</span></div>
            <input type="range" id="calib-oz" min="-2.0" max="2.0" step="0.02" value="0" class="timeline-slider" />
          </div>
        </div>

        <div class="calib-grid">
          <div class="calib-slider-box">
            <div class="calib-row-label"><span>Distorsione k1</span><span id="calib-val-k1" class="calib-num">-0.18</span></div>
            <input type="range" id="calib-k1" min="-0.6" max="0.4" step="0.01" value="-0.18" class="timeline-slider" />
          </div>
          <div class="calib-slider-box">
            <div class="calib-row-label"><span>Distorsione k2</span><span id="calib-val-k2" class="calib-num">0.04</span></div>
            <input type="range" id="calib-k2" min="-0.4" max="0.4" step="0.01" value="0.04" class="timeline-slider" />
          </div>
        </div>

        <div class="calib-pnp-box">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
            <button class="btn-icon-text" id="calib-pnp-toggle" style="font-size:11px;padding:6px 10px;">
              ${icon('crosshair', { size: 14 })} <span>Raccogli Punti PnP (0/4)</span>
            </button>
            <button class="btn-icon-text" id="calib-pnp-solve" disabled style="font-size:11px;padding:6px 10px;">
              ${icon('zap', { size: 14 })} <span>Risolvi PnP</span>
            </button>
          </div>
          <div id="calib-pnp-hint" style="font-size:10px;color:var(--text-muted);margin-top:4px;">
            Opzionale: clicca 4 punti noti (es. spigoli pilastrino/cancello) in 3D e nel video.
          </div>
        </div>

        <div class="calib-actions-row">
          <button class="btn-icon-text" id="calib-reset-btn" style="flex:1;justify-content:center;font-size:11px;">
            ${icon('rotate-ccw', { size: 14 })} <span>Reset SSoT</span>
          </button>
          <button class="btn-action-primary" id="calib-save-btn" style="flex:1.6;padding:8px 12px;font-size:12px;">
            ${icon('save', { size: 14 })} <span>Salva & Applica a Backend</span>
          </button>
        </div>
        <div id="calib-status-msg" style="font-size:11px;color:var(--accent-cyan);text-align:center;"></div>
      </div>
    `;

    uiLayer.appendChild(panel);
    this.panelEl = panel;
    this.bindEvents();
  }

  setCollapsed(collapsed) {
    if (!this.panelEl) return;
    const isCollapsed = Boolean(collapsed);
    this.panelEl.classList.toggle('collapsed', isCollapsed);
    const collapseIcon = this.panelEl.querySelector('#calib-collapse-icon');
    if (collapseIcon) {
      collapseIcon.innerHTML = icon(isCollapsed ? 'chevron-down' : 'chevron-up', { size: 15 });
    }
  }

  bindEvents() {
    this.panelEl.querySelector('#calib-header-toggle').addEventListener('click', () => {
      this.setCollapsed(!this.panelEl.classList.contains('collapsed'));
    });

    this.panelEl.querySelector('#calib-close-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      this.close();
    });

    const opSlider = this.panelEl.querySelector('#calib-opacity');
    opSlider.addEventListener('input', (e) => {
      const pct = parseInt(e.target.value, 10);
      this.overlayOpacity = pct / 100;
      this.panelEl.querySelector('#calib-val-opacity').textContent = `${pct}%`;
      this.cameraProjector.setOverlayOpacity(this.activeCameraName, this.overlayOpacity);
    });

    const bindSlider = (id, key, valId, suffix = '', decimals = 1) => {
      const el = this.panelEl.querySelector(id);
      el.addEventListener('input', (e) => {
        const v = parseFloat(e.target.value);
        this.state[key] = v;
        if (key === 'fovV') {
          const aspect = this.sceneManager.camera.aspect || 16 / 9;
          this.state.fovH = Number((2 * THREE.MathUtils.radToDeg(Math.atan(Math.tan(THREE.MathUtils.degToRad(v / 2)) * aspect))).toFixed(2));
        }
        this.panelEl.querySelector(valId).textContent = `${v.toFixed(decimals)}${suffix}`;
        this.applyLiveCalibration(true);
      });
    };

    bindSlider('#calib-yaw', 'yawDeg', '#calib-val-yaw', '°', 1);
    bindSlider('#calib-pitch', 'pitchDeg', '#calib-val-pitch', '°', 1);
    bindSlider('#calib-roll', 'rollDeg', '#calib-val-roll', '°', 1);
    bindSlider('#calib-fov', 'fovV', '#calib-val-fov', '°', 1);
    bindSlider('#calib-ox', 'offsetX', '#calib-val-ox', '', 2);
    bindSlider('#calib-oy', 'offsetY', '#calib-val-oy', '', 2);
    bindSlider('#calib-oz', 'offsetZ', '#calib-val-oz', '', 2);
    bindSlider('#calib-k1', 'k1', '#calib-val-k1', '', 2);
    bindSlider('#calib-k2', 'k2', '#calib-val-k2', '', 2);

    this.panelEl.querySelector('#calib-flip-180').addEventListener('click', () => {
      this.state.flip180 = !this.state.flip180;
      this.applyLiveCalibration(true);
    });

    this.panelEl.querySelector('#calib-reset-btn').addEventListener('click', () => {
      localStorage.removeItem(`${STORAGE_KEY}_${this.activeCameraName}`);
      this.state = this.createDefaultState();
      this.syncInputsFromState();
      this.applyLiveCalibration(true);
      this.setStatus('Ripristinati parametri originali da Blender SSoT.');
    });

    this.panelEl.querySelector('#calib-save-btn').addEventListener('click', async () => {
      await this.saveAndSubmitToBackend();
    });

    const pnpToggle = this.panelEl.querySelector('#calib-pnp-toggle');
    pnpToggle.addEventListener('click', () => {
      this.pnpMode = !this.pnpMode;
      this.pnpStep = '3d';
      pnpToggle.classList.toggle('active', this.pnpMode);
      this.updatePnpHint();
    });

    this.panelEl.querySelector('#calib-pnp-solve').addEventListener('click', async () => {
      await this.solvePnPOnBackend();
    });
  }

  syncInputsFromState() {
    if (!this.panelEl) return;
    const setVal = (sel, val, lblSel, txt) => {
      const el = this.panelEl.querySelector(sel);
      if (el) el.value = val;
      const lbl = this.panelEl.querySelector(lblSel);
      if (lbl) lbl.textContent = txt;
    };
    setVal('#calib-yaw', this.state.yawDeg, '#calib-val-yaw', `${this.state.yawDeg.toFixed(1)}°`);
    setVal('#calib-pitch', this.state.pitchDeg, '#calib-val-pitch', `${this.state.pitchDeg.toFixed(1)}°`);
    setVal('#calib-roll', this.state.rollDeg, '#calib-val-roll', `${this.state.rollDeg.toFixed(1)}°`);
    setVal('#calib-fov', this.state.fovV, '#calib-val-fov', `${this.state.fovV.toFixed(1)}°`);
    setVal('#calib-ox', this.state.offsetX, '#calib-val-ox', this.state.offsetX.toFixed(2));
    setVal('#calib-oy', this.state.offsetY, '#calib-val-oy', this.state.offsetY.toFixed(2));
    setVal('#calib-oz', this.state.offsetZ, '#calib-val-oz', this.state.offsetZ.toFixed(2));
    setVal('#calib-k1', this.state.k1, '#calib-val-k1', this.state.k1.toFixed(2));
    setVal('#calib-k2', this.state.k2, '#calib-val-k2', this.state.k2.toFixed(2));
  }

  applyLiveCalibration(syncViewportCamera = true) {
    const pose = this.cameraProjector.applyCameraCalibration(this.activeCameraName, this.state);
    if (syncViewportCamera && pose && this.cameraController) {
      this.cameraController.setInstantCameraPose(pose.position, pose.quaternion, this.state.fovV);
    }
  }

  handleCanvasClick(event) {
    if (!this.isOpen || !this.pnpMode) return;
    const rect = this.sceneManager.renderer.domElement.getBoundingClientRect();
    const u = (event.clientX - rect.left) / rect.width;
    const v = (event.clientY - rect.top) / rect.height;

    if (this.pnpStep === '3d') {
      const ndc = new THREE.Vector2(u * 2 - 1, -(v * 2 - 1));
      this.raycaster.setFromCamera(ndc, this.sceneManager.camera);
      const hits = this.raycaster.intersectObjects(this.sceneManager.scene.children, true);
      const validHit = hits.find((h) => h.object.isMesh && !h.object.name.startsWith('Frustum'));
      if (validHit) {
        this.pendingPoint3D = [validHit.point.x, validHit.point.y, validHit.point.z];
        this.pnpStep = '2d';
        this.updatePnpHint();
      }
    } else {
      if (this.pendingPoint3D) {
        this.correspondences.push({
          world_point: this.pendingPoint3D,
          pixel_uv: [Number(u.toFixed(4)), Number(v.toFixed(4))],
        });
        this.pendingPoint3D = null;
        this.pnpStep = '3d';
        this.updatePnpHint();
      }
    }
  }

  updatePnpHint() {
    if (!this.panelEl) return;
    const toggleBtn = this.panelEl.querySelector('#calib-pnp-toggle');
    const solveBtn = this.panelEl.querySelector('#calib-pnp-solve');
    const hint = this.panelEl.querySelector('#calib-pnp-hint');
    toggleBtn.innerHTML = `${icon('crosshair', { size: 14 })} <span>Raccogli Punti PnP (${this.correspondences.length}/4)</span>`;
    solveBtn.disabled = this.correspondences.length < 4;

    if (!this.pnpMode) {
      hint.textContent = 'Opzionale: clicca 4 punti noti (es. spigoli pilastrino/cancello) in 3D e nel video.';
    } else if (this.pnpStep === '3d') {
      hint.textContent = 'STEP A: Clicca un punto geometrico noto sul modello 3D (abbassa opacità video se serve).';
    } else {
      hint.textContent = 'STEP B: Ora clicca lo stesso identico punto sull’immagine video reale.';
    }
  }

  async solvePnPOnBackend() {
    if (!this.spatialStreamClient || this.correspondences.length < 4) return;
    this.setStatus('Risoluzione SolvePnPRansac in corso...');
    const res = await this.spatialStreamClient.solvePnP({
      camera_id: this.activeCameraName,
      correspondences: this.correspondences,
    });
    if (res && res.status === 'ok') {
      this.setStatus(`PnP risolto! Errore medio riproiezione: ${res.reprojection_error_px?.toFixed(2) ?? '--'} px`);
      this.correspondences = [];
      this.pnpMode = false;
      this.updatePnpHint();
    } else {
      this.setStatus('Errore SolvePnP: verifica che spatial_server (porta 8765) sia avviato.');
    }
  }

  async saveAndSubmitToBackend() {
    this.saveStateToLocal(this.activeCameraName);
    const pose = this.cameraProjector.applyCameraCalibration(this.activeCameraName, this.state);

    if (!this.spatialStreamClient) {
      this.setStatus('Salvato in locale (Spatial Server non connesso).');
      return;
    }

    const payload = {
      camera_id: this.activeCameraName,
      offset_xyz: [this.state.offsetX, this.state.offsetY, this.state.offsetZ],
      delta_euler_deg: [this.state.pitchDeg, this.state.yawDeg + (this.state.flip180 ? 180 : 0), this.state.rollDeg],
      fov_v_deg: this.state.fovV,
      fov_h_deg: this.state.fovH,
      distortion_coeffs: [this.state.k1, this.state.k2, 0.0, 0.0, 0.0],
      calibrated_matrix_world_gl: pose ? pose.matrixWorldElements : null,
    };

    const res = await this.spatialStreamClient.updateCameraCalibration(this.activeCameraName, payload);
    if (res && res.status === 'ok') {
      this.setStatus('Calibrazione salvata e applicata al Raycaster 3D Python!');
    } else {
      this.setStatus('Salvato nel browser. Avvia spatial_server per sincronizzare il backend.');
    }
  }

  setStatus(text) {
    const el = this.panelEl?.querySelector('#calib-status-msg');
    if (el) el.textContent = text;
  }
}

