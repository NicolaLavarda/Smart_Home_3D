import * as THREE from 'three';
import { icon } from '../../ui/icons.js';
import {
  computePairCameraPixelError,
  decomposeWorldMatrixToCalibState,
  getOverlayWorldPointFromPixelUv,
  projectWorldToScreen,
  solvePnPLocal,
} from './PnPSolver.js';

const STORAGE_KEY = 'sh3d_camera_calibration_v2';
const SVG_NS = 'http://www.w3.org/2000/svg';
const PNP_STEP_OPACITY_3D_PCT = 10;
const PNP_STEP_OPACITY_2D_PCT = 75;

function isObjectVisibleInHierarchy(obj) {
  let cur = obj;
  while (cur) {
    if (cur.visible === false) return false;
    cur = cur.parent;
  }
  return true;
}

function getErrorTier(errorPx, inFront = true) {
  if (!inFront || !Number.isFinite(errorPx)) return 'bad';
  if (errorPx <= 10) return 'good';
  if (errorPx <= 35) return 'warn';
  return 'bad';
}

const TIER_COLORS = {
  good: '#10b981',
  warn: '#f59e0b',
  bad: '#f43f5e',
};

/**
 * CalibrationAssistantUI
 *
 * Pannello interattivo per la calibrazione geometrica Camera-to-World in vista POV:
 * - Sovrappone il video live della Reolink RLC-540A al modello 3D con opacità 0%-100%
 * - Regola in tempo reale Yaw, Pitch, Roll, Offset XYZ, FOV e distorsione k1/k2
 * - Offre il tasto 1-click "Inverti Direzione 180°" (Vialetto Interno <-> Strada Esterna)
 * - Guida la raccolta di coppie 3D <-> 2D (4x2+ punti) visualizzando in tempo reale
 *   i marker e i vettori di errore a schermo e applicando il risultato di SolvePnP.
 */
export class CalibrationAssistantUI {
  constructor({ sceneManager, cameraController, cameraProjector, videoStreamManager, spatialStreamClient, assetLoader, haClient = null }) {
    this.sceneManager = sceneManager;
    this.cameraController = cameraController;
    this.cameraProjector = cameraProjector;
    this.videoStreamManager = videoStreamManager;
    this.spatialStreamClient = spatialStreamClient;
    this.assetLoader = assetLoader;
    this.haClient = haClient;
    this._rbacToastTimer = null;

    this.isOpen = false;
    this.activeCameraName = 'Cam_Carraio';
    this.streamName = 'carraio_main';
    this.panelEl = null;
    this.hudBannerEl = null;
    this.vectorSvgEl = null;
    this.videoTextureEntry = null;
    this.overlayOpacity = 0.52;

    // Modalità raccolta corrispondenze PnP 3D <-> 2D
    this.pnpMode = false;
    this.pnpStep = '3d'; // '3d' -> '2d'
    this.pendingPoint3D = null;
    this.correspondences = [];
    this.showPnpVectors = true;
    this.hoveredPairIdx = null;
    this.isSolvingPnP = false;
    this.pointerScreenPos = null;
    this._opacityBeforePnp = null;
    this.raycaster = new THREE.Raycaster();

    this._pointerDownPos = null;
    this._pointerDownId = null;

    this.state = this.createDefaultState();
    this._onPointerDown = this.handleCanvasPointerDown.bind(this);
    this._onPointerMove = this.handleCanvasPointerMove.bind(this);
    this._onPointerUp = this.handleCanvasPointerUp.bind(this);
    this._onContextMenu = this.handleCanvasContextMenu.bind(this);
    this._onFrameUpdate = this.renderVectorOverlay.bind(this);
    this._onKeyDown = (e) => {
      if (!this.isOpen || e.key !== 'Escape') return;
      if (this.pnpMode && this.pendingPoint3D) {
        this.cancelPendingPoint();
        return;
      }
      if (this.pnpMode) {
        this.setPnpMode(false);
        return;
      }
      this.close();
    };
    this.onOpenCallback = null;
    this.onCloseCallback = null;
  }

  setLifecycleHooks({ onOpen, onClose } = {}) {
    this.onOpenCallback = typeof onOpen === 'function' ? onOpen : null;
    this.onCloseCallback = typeof onClose === 'function' ? onClose : null;
  }

  getManifestCamera(cameraName = this.activeCameraName) {
    return this.assetLoader?.manifest?.cameras?.[cameraName] || null;
  }

  getOpticalTanRatio(cameraName = this.activeCameraName) {
    const manifestCam = this.getManifestCamera(cameraName);
    if (manifestCam?.fov_h_deg && manifestCam?.fov_v_deg) {
      return (
        Math.tan(THREE.MathUtils.degToRad(manifestCam.fov_h_deg * 0.5)) /
        Math.max(1e-5, Math.tan(THREE.MathUtils.degToRad(manifestCam.fov_v_deg * 0.5)))
      );
    }
    return manifestCam?.aspect_ratio || 16 / 9;
  }

  createDefaultState(cameraName = this.activeCameraName) {
    const manifestCam = this.getManifestCamera(cameraName);
    const dist = manifestCam?.distortion_coeffs || [-0.18, 0.04, 0, 0, 0];
    return {
      offsetX: 0.0,
      offsetY: 0.0,
      offsetZ: 0.0,
      yawDeg: 0.0,
      pitchDeg: 0.0,
      rollDeg: 0.0,
      fovV: manifestCam?.fov_v_deg ?? 42.0,
      fovH: manifestCam?.fov_h_deg ?? 80.0,
      k1: dist[0] ?? -0.18,
      k2: dist[1] ?? 0.04,
      flip180: false,
    };
  }

  loadSavedState(cameraName) {
    const defaults = this.createDefaultState(cameraName);
    try {
      const raw = localStorage.getItem(`${STORAGE_KEY}_${cameraName}`);
      if (raw) {
        return { ...defaults, ...JSON.parse(raw) };
      }
    } catch { }
    return defaults;
  }

  saveStateToLocal(cameraName) {
    try {
      localStorage.setItem(`${STORAGE_KEY}_${cameraName}`, JSON.stringify(this.state));
    } catch { }
  }

  _showRbacToast(message = 'Calibrazione riservata agli utenti Admin.') {
    if (typeof document === 'undefined') return;
    const host = document.querySelector('.ui-layer') || document.body;
    if (!host) return;
    let toast = host.querySelector('#rbac-admin-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'rbac-admin-toast';
      toast.className = 'rbac-toast glass';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      host.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('visible');
    if (this._rbacToastTimer) {
      clearTimeout(this._rbacToastTimer);
    }
    this._rbacToastTimer = setTimeout(() => {
      toast.classList.remove('visible');
    }, 3500);
  }

  async open(cameraName = 'Cam_Carraio') {
    if (!this.haClient?.isAdmin) {
      this._showRbacToast('Calibrazione riservata agli utenti Admin.');
      return false;
    }

    this.activeCameraName = cameraName;
    this.state = this.loadSavedState(cameraName);

    const manifestCam = this.getManifestCamera(cameraName);
    this.streamName = manifestCam?.stream_id || 'carraio_main';

    if (!this.panelEl) {
      this.createDOM();
    }
    this.ensureOverlayDOM();

    this.isOpen = true;
    this.setCollapsed(false);
    this.panelEl.classList.add('open');

    const subtitleEl = this.panelEl.querySelector('#calib-cam-name');
    if (subtitleEl) {
      subtitleEl.textContent = `${cameraName} • ${manifestCam?.ha_label || 'Reolink RLC-540A'}`;
    }

    this.syncInputsFromState();
    this.syncOpacityUI(Math.round(this.overlayOpacity * 100));
    this.renderPnpPairsList();
    this.updatePnpControlsUI();
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

    const canvas = this.sceneManager.renderer.domElement;
    canvas.addEventListener('pointerdown', this._onPointerDown);
    canvas.addEventListener('pointermove', this._onPointerMove);
    canvas.addEventListener('pointerup', this._onPointerUp);
    canvas.addEventListener('contextmenu', this._onContextMenu);
    this.sceneManager.addUpdateCallback(this._onFrameUpdate);
  }

  close() {
    if (!this.isOpen) return;
    this.isOpen = false;
    this.setPnpMode(false);
    this.pendingPoint3D = null;
    this.pnpStep = '3d';

    if (this.panelEl) {
      this.panelEl.classList.remove('open');
      this.setCollapsed(false);
    }
    if (this.hudBannerEl) {
      this.hudBannerEl.classList.remove('visible');
    }
    if (this.vectorSvgEl) {
      this.vectorSvgEl.innerHTML = '';
    }

    this.cameraProjector.setOverlayPOVMode(this.activeCameraName, false, 0);
    if (this.videoTextureEntry) {
      this.videoStreamManager.releaseVideoTexture(this.streamName);
      this.videoTextureEntry = null;
    }

    const canvas = this.sceneManager.renderer.domElement;
    canvas.style.cursor = '';
    canvas.removeEventListener('pointerdown', this._onPointerDown);
    canvas.removeEventListener('pointermove', this._onPointerMove);
    canvas.removeEventListener('pointerup', this._onPointerUp);
    canvas.removeEventListener('contextmenu', this._onContextMenu);
    this.sceneManager.removeUpdateCallback(this._onFrameUpdate);
    window.removeEventListener('keydown', this._onKeyDown);
    this.onCloseCallback?.();
  }

  ensureOverlayDOM() {
    const appEl = document.getElementById('app') || document.body;
    const uiLayer = document.querySelector('.ui-layer');

    if (!this.vectorSvgEl) {
      const svg = document.createElementNS(SVG_NS, 'svg');
      svg.setAttribute('class', 'pnp-overlay-svg');
      svg.setAttribute('aria-hidden', 'true');
      appEl.appendChild(svg);
      this.vectorSvgEl = svg;
    }

    if (!this.hudBannerEl && uiLayer) {
      const banner = document.createElement('div');
      banner.className = 'pnp-hud-banner glass';
      banner.id = 'pnp-hud-banner';
      banner.innerHTML = `
        <span class="pnp-hud-step-badge" id="pnp-hud-step-badge">PASSO 1/2</span>
        <span class="pnp-hud-text" id="pnp-hud-text">Clicca un punto sul modello 3D</span>
        <button type="button" class="pnp-hud-action" id="pnp-hud-cancel-pending" style="display:none;">Annulla punto</button>
        <button type="button" class="pnp-hud-action secondary" id="pnp-hud-stop">Fine</button>
      `;
      uiLayer.appendChild(banner);
      this.hudBannerEl = banner;

      banner.querySelector('#pnp-hud-cancel-pending')?.addEventListener('click', () => {
        this.cancelPendingPoint();
      });
      banner.querySelector('#pnp-hud-stop')?.addEventListener('click', () => {
        this.setPnpMode(false);
      });
    }
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
          <button type="button" class="btn-close" id="calib-close-btn" title="Chiudi Calibrazione">${icon('x', { size: 15 })}</button>
        </div>
      </div>

      <div class="calib-body" id="calib-content">
        <div class="calib-section">
          <div class="calib-row-label">
            <span>Opacità Video Live</span>
            <span id="calib-val-opacity" class="calib-num">52%</span>
          </div>
          <input type="range" id="calib-opacity" min="0" max="100" value="52" class="timeline-slider" />
          <div class="calib-opacity-presets" role="group" aria-label="Preset opacità video">
            <button type="button" class="calib-preset-chip" data-opacity="0">0% Solo 3D</button>
            <button type="button" class="calib-preset-chip" data-opacity="50">50% Mix</button>
            <button type="button" class="calib-preset-chip" data-opacity="85">85% Video</button>
          </div>
        </div>

        <div class="calib-pnp-box" id="calib-pnp-box">
          <div class="calib-pnp-header">
            <span class="calib-pnp-title">${icon('crosshair', { size: 14 })} <span>Allineamento PnP (4+ coppie)</span></span>
            <span class="calib-pnp-pill neutral" id="calib-pnp-summary-pill">0/4</span>
          </div>

          <div class="calib-pnp-actions">
            <button type="button" class="btn-icon-text calib-pnp-btn" id="calib-pnp-toggle">
              ${icon('crosshair', { size: 14 })} <span id="calib-pnp-toggle-label">Avvia Raccolta</span>
            </button>
            <button type="button" class="btn-action-primary calib-pnp-solve-btn" id="calib-pnp-solve" disabled>
              ${icon('zap', { size: 14 })} <span>Risolvi PnP</span>
            </button>
          </div>

          <div id="calib-pnp-opacity-nudge" class="calib-pnp-nudge" style="display:none;">
            <span>Video trasparente: alzalo per vedere i dettagli nel feed.</span>
            <button type="button" class="calib-preset-chip" id="calib-pnp-raise-opacity">Porta a 75%</button>
          </div>

          <div id="calib-pnp-hint" class="calib-pnp-hint">
            1. Clicca uno spigolo sul modello 3D → 2. Clicca lo stesso punto sul video. Servono almeno 4 coppie distribuite.
          </div>

          <div class="calib-pnp-list" id="calib-pnp-list"></div>

          <div class="calib-pnp-footer" id="calib-pnp-footer" style="display:none;">
            <button type="button" class="calib-mini-btn" id="calib-pnp-vis-toggle" title="Mostra o nascondi marker e vettori a schermo">
              ${icon('eye', { size: 13 })} <span id="calib-pnp-vis-label">Nascondi vettori</span>
            </button>
            <button type="button" class="calib-mini-btn danger" id="calib-pnp-clear" title="Rimuovi tutte le coppie raccolte">
              ${icon('rotate-ccw', { size: 13 })} <span>Svuota</span>
            </button>
          </div>
        </div>

        <div class="calib-actions-row">
          <button type="button" class="btn-icon-text" id="calib-flip-180" style="flex:1;justify-content:center;font-size:11px;">
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

        <div class="calib-actions-row">
          <button type="button" class="btn-icon-text" id="calib-reset-btn" style="flex:1;justify-content:center;font-size:11px;">
            ${icon('rotate-ccw', { size: 14 })} <span>Reset SSoT</span>
          </button>
          <button type="button" class="btn-action-primary" id="calib-save-btn" style="flex:1.6;padding:8px 12px;font-size:12px;">
            ${icon('save', { size: 14 })} <span>Salva & Applica a Backend</span>
          </button>
        </div>
        <div id="calib-status-msg" class="calib-status-msg"></div>
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

  syncOpacityUI(pct) {
    if (!this.panelEl) return;
    const clamped = THREE.MathUtils.clamp(Math.round(pct), 0, 100);
    this.overlayOpacity = clamped / 100;
    const slider = this.panelEl.querySelector('#calib-opacity');
    const lbl = this.panelEl.querySelector('#calib-val-opacity');
    if (slider) slider.value = String(clamped);
    if (lbl) lbl.textContent = `${clamped}%`;
    this.cameraProjector.setOverlayOpacity(this.activeCameraName, this.overlayOpacity);

    this.panelEl.querySelectorAll('.calib-preset-chip[data-opacity]').forEach((chip) => {
      chip.classList.toggle('active', Number(chip.dataset.opacity) === clamped);
    });
    this.updatePnpControlsUI();
  }

  setPnpMode(active) {
    const nextActive = Boolean(active);
    const wasActive = this.pnpMode;
    this.pnpMode = nextActive;

    if (nextActive) {
      if (!wasActive) {
        this._opacityBeforePnp = Math.round(this.overlayOpacity * 100);
      }
      this.pendingPoint3D = null;
      this.pnpStep = '3d';
      this.showPnpVectors = true;
      this.syncOpacityUI(PNP_STEP_OPACITY_3D_PCT);
    } else {
      this.pendingPoint3D = null;
      this.pnpStep = '3d';
      this.pointerScreenPos = null;
      if (wasActive && this._opacityBeforePnp !== null) {
        const restorePct = this._opacityBeforePnp;
        this._opacityBeforePnp = null;
        this.syncOpacityUI(restorePct);
      }
    }

    const canvas = this.sceneManager?.renderer?.domElement;
    if (canvas) {
      canvas.style.cursor = this.pnpMode ? 'crosshair' : '';
    }
    this.renderPnpPairsList();
    this.updatePnpControlsUI();
  }

  cancelPendingPoint() {
    if (!this.pendingPoint3D) return;
    this.pendingPoint3D = null;
    this.pnpStep = '3d';
    if (this.pnpMode) {
      this.syncOpacityUI(PNP_STEP_OPACITY_3D_PCT);
    }
    this.renderPnpPairsList();
    this.updatePnpControlsUI();
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
      this.syncOpacityUI(parseInt(e.target.value, 10));
    });

    this.panelEl.querySelectorAll('.calib-preset-chip[data-opacity]').forEach((btn) => {
      btn.addEventListener('click', () => {
        this.syncOpacityUI(parseInt(btn.dataset.opacity, 10));
      });
    });

    this.panelEl.querySelector('#calib-pnp-raise-opacity')?.addEventListener('click', () => {
      this.syncOpacityUI(PNP_STEP_OPACITY_2D_PCT);
    });

    const bindSlider = (id, key, valId, suffix = '', decimals = 1) => {
      const el = this.panelEl.querySelector(id);
      el.addEventListener('input', (e) => {
        const v = parseFloat(e.target.value);
        this.state[key] = v;
        if (key === 'fovV') {
          const tanRatio = this.getOpticalTanRatio(this.activeCameraName);
          this.state.fovH = Number(
            (2 * THREE.MathUtils.radToDeg(Math.atan(Math.tan(THREE.MathUtils.degToRad(v * 0.5)) * tanRatio))).toFixed(2)
          );
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
      this.panelEl.querySelector('#calib-flip-180')?.classList.toggle('active', Boolean(this.state.flip180));
      this.applyLiveCalibration(true);
    });

    this.panelEl.querySelector('#calib-reset-btn').addEventListener('click', () => {
      localStorage.removeItem(`${STORAGE_KEY}_${this.activeCameraName}`);
      this.state = this.createDefaultState(this.activeCameraName);
      this.syncInputsFromState();
      this.applyLiveCalibration(true);
      this.setStatus('Ripristinati parametri originali da Blender SSoT.', 'info');
    });

    this.panelEl.querySelector('#calib-save-btn').addEventListener('click', async () => {
      await this.saveAndSubmitToBackend();
    });

    this.panelEl.querySelector('#calib-pnp-toggle').addEventListener('click', () => {
      this.setPnpMode(!this.pnpMode);
    });

    this.panelEl.querySelector('#calib-pnp-solve').addEventListener('click', async () => {
      await this.solvePnP();
    });

    this.panelEl.querySelector('#calib-pnp-vis-toggle').addEventListener('click', () => {
      this.showPnpVectors = !this.showPnpVectors;
      this.updatePnpControlsUI();
    });

    this.panelEl.querySelector('#calib-pnp-clear').addEventListener('click', () => {
      this.correspondences = [];
      this.pendingPoint3D = null;
      this.pnpStep = '3d';
      this.hoveredPairIdx = null;
      if (this.pnpMode) {
        this.syncOpacityUI(PNP_STEP_OPACITY_3D_PCT);
      }
      this.renderPnpPairsList();
      this.updatePnpControlsUI();
      this.setStatus('Punti PnP rimossi.', 'info');
    });
  }

  syncInputsFromState() {
    if (!this.panelEl) return;
    const setVal = (sel, val, lblSel, txt) => {
      const el = this.panelEl.querySelector(sel);
      if (el) {
        const min = parseFloat(el.min);
        const max = parseFloat(el.max);
        if (Number.isFinite(min) && val < min) el.min = String(Math.floor(val - 1));
        if (Number.isFinite(max) && val > max) el.max = String(Math.ceil(val + 1));
        el.value = String(val);
      }
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

    this.panelEl.querySelector('#calib-flip-180')?.classList.toggle('active', Boolean(this.state.flip180));
  }

  applyLiveCalibration(syncViewportCamera = true) {
    const pose = this.cameraProjector.applyCameraCalibration(this.activeCameraName, this.state);
    if (syncViewportCamera && pose && this.cameraController) {
      this.cameraController.setInstantCameraPose(pose.position, pose.quaternion, this.state.fovV);
    }
    this.refreshPairErrorsUI();
    return pose;
  }

  handleCanvasPointerDown(event) {
    if (!this.isOpen || !this.pnpMode) return;
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    this._pointerDownId = event.pointerId;
    this._pointerDownPos = { x: event.clientX, y: event.clientY };
  }

  handleCanvasPointerMove(event) {
    if (!this.isOpen || !this.pnpMode || event.pointerType === 'touch') {
      this.pointerScreenPos = null;
      return;
    }
    const rect = this.sceneManager.renderer.domElement.getBoundingClientRect();
    this.pointerScreenPos = {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
  }

  handleCanvasContextMenu(event) {
    if (!this.isOpen || !this.pnpMode) return;
    event.preventDefault();
    if (this.pendingPoint3D) {
      this.cancelPendingPoint();
    } else {
      this.setPnpMode(false);
    }
  }

  handleCanvasPointerUp(event) {
    if (!this.isOpen || !this.pnpMode) return;
    if (this._pointerDownId !== event.pointerId || !this._pointerDownPos) return;
    const dx = event.clientX - this._pointerDownPos.x;
    const dy = event.clientY - this._pointerDownPos.y;
    this._pointerDownId = null;
    this._pointerDownPos = null;

    const maxMove = event.pointerType === 'touch' ? 10 : 6;
    if (Math.hypot(dx, dy) > maxMove) return;

    const rect = this.sceneManager.renderer.domElement.getBoundingClientRect();
    const uView = (event.clientX - rect.left) / rect.width;
    const vView = (event.clientY - rect.top) / rect.height;
    const ndc = new THREE.Vector2(uView * 2 - 1, -(vView * 2 - 1));
    this.raycaster.setFromCamera(ndc, this.sceneManager.camera);

    if (this.pnpStep === '3d') {
      const hits = this.raycaster.intersectObjects(this.sceneManager.scene.children, true);
      const validHit = hits.find(
        (h) =>
          h.object.isMesh &&
          isObjectVisibleInHierarchy(h.object) &&
          !h.object.name.startsWith('Frustum') &&
          !h.object.name.startsWith('Decal_') &&
          !h.object.name.startsWith('Sensor_')
      );
      if (validHit) {
        this.pendingPoint3D = [validHit.point.x, validHit.point.y, validHit.point.z];
        this.pnpStep = '2d';
        this.showPnpVectors = true;
        this.renderPnpPairsList();
        this.syncOpacityUI(PNP_STEP_OPACITY_2D_PCT);
      } else {
        this.setStatus('Nessuna superficie 3D trovata sotto il cursore. Clicca un muro, pilastro o cancello.', 'warn');
      }
    } else if (this.pendingPoint3D) {
      const overlay = this.cameraProjector?.frustumOverlays?.get(this.activeCameraName);
      let pixelUv = null;

      if (overlay?.mesh) {
        overlay.mesh.updateMatrixWorld(true);
        const overlayHits = this.raycaster.intersectObject(overlay.mesh, false);
        if (overlayHits.length > 0 && overlayHits[0].uv) {
          pixelUv = [
            Number(THREE.MathUtils.clamp(overlayHits[0].uv.x, 0, 1).toFixed(4)),
            Number(THREE.MathUtils.clamp(1.0 - overlayHits[0].uv.y, 0, 1).toFixed(4)),
          ];
        } else {
          this.setStatus('Clicca dentro il riquadro del video sovrapposto per fissare il punto 2D.', 'warn');
          return;
        }
      } else {
        pixelUv = [Number(uView.toFixed(4)), Number(vView.toFixed(4))];
      }

      this.correspondences.push({
        world_point: this.pendingPoint3D,
        pixel_uv: pixelUv,
      });
      this.pendingPoint3D = null;
      this.pnpStep = '3d';
      this.showPnpVectors = true;
      this.renderPnpPairsList();
      this.syncOpacityUI(PNP_STEP_OPACITY_3D_PCT);
    }
  }

  getPairErrorsSnapshot() {
    const pose = this.cameraProjector?.getCalibratedCameraPose(this.activeCameraName);
    if (!pose) return [];
    return this.correspondences.map((corr) =>
      computePairCameraPixelError(
        corr.world_point,
        corr.pixel_uv,
        pose.position,
        pose.quaternion,
        this.state.fovV,
        this.state.fovH,
        this.state.k1,
        this.state.k2
      )
    );
  }

  renderPnpPairsList() {
    if (!this.panelEl) return;
    const listEl = this.panelEl.querySelector('#calib-pnp-list');
    if (!listEl) return;

    if (this.correspondences.length === 0 && !this.pendingPoint3D) {
      listEl.innerHTML = '';
      return;
    }

    const errors = this.getPairErrorsSnapshot();
    const rowsHtml = [];

    this.correspondences.forEach((corr, idx) => {
      const err = errors[idx] || { inFront: true, errorPx: NaN };
      const tier = getErrorTier(err.errorPx, err.inFront);
      const errLabel = !err.inFront
        ? 'Dietro cam'
        : Number.isFinite(err.errorPx)
          ? `${err.errorPx.toFixed(1)} px`
          : '--';

      rowsHtml.push(`
        <div class="calib-pnp-row" data-pair-idx="${idx}">
          <span class="calib-pnp-row-badge ${tier}" data-pair-badge-idx="${idx}">P${idx + 1}</span>
          <span class="calib-pnp-row-info">3D (${corr.world_point[0].toFixed(1)}, ${corr.world_point[1].toFixed(1)}, ${corr.world_point[2].toFixed(1)})</span>
          <span class="calib-pnp-row-err ${tier}" data-pair-err-idx="${idx}">${errLabel}</span>
          <button type="button" class="calib-pnp-del-btn" data-del-idx="${idx}" title="Rimuovi coppia P${idx + 1}" aria-label="Rimuovi coppia P${idx + 1}">
            ${icon('x', { size: 12 })}
          </button>
        </div>
      `);
    });

    if (this.pendingPoint3D) {
      const nextNum = this.correspondences.length + 1;
      rowsHtml.push(`
        <div class="calib-pnp-row pending">
          <span class="calib-pnp-row-badge pending">P${nextNum}</span>
          <span class="calib-pnp-row-info">3D fissato • clicca sul video</span>
          <button type="button" class="calib-pnp-del-btn" id="calib-pnp-cancel-pending-row" title="Annulla punto P${nextNum}" aria-label="Annulla punto P${nextNum}">
            ${icon('x', { size: 12 })}
          </button>
        </div>
      `);
    }

    listEl.innerHTML = rowsHtml.join('');

    listEl.querySelectorAll('.calib-pnp-row[data-pair-idx]').forEach((row) => {
      const idx = Number(row.dataset.pairIdx);
      row.addEventListener('mouseenter', () => {
        this.hoveredPairIdx = idx;
      });
      row.addEventListener('mouseleave', () => {
        if (this.hoveredPairIdx === idx) this.hoveredPairIdx = null;
      });
    });

    listEl.querySelectorAll('.calib-pnp-del-btn[data-del-idx]').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const idx = Number(btn.dataset.delIdx);
        this.correspondences.splice(idx, 1);
        if (this.hoveredPairIdx === idx) this.hoveredPairIdx = null;
        this.renderPnpPairsList();
        this.updatePnpControlsUI();
      });
    });

    listEl.querySelector('#calib-pnp-cancel-pending-row')?.addEventListener('click', (e) => {
      e.stopPropagation();
      this.cancelPendingPoint();
    });
  }

  refreshPairErrorsUI() {
    if (!this.panelEl) return;
    const errors = this.getPairErrorsSnapshot();

    errors.forEach((err, idx) => {
      const errEl = this.panelEl.querySelector(`[data-pair-err-idx="${idx}"]`);
      const badgeEl = this.panelEl.querySelector(`[data-pair-badge-idx="${idx}"]`);
      if (!errEl || !badgeEl) return;
      const tier = getErrorTier(err.errorPx, err.inFront);
      errEl.className = `calib-pnp-row-err ${tier}`;
      badgeEl.className = `calib-pnp-row-badge ${tier}`;
      errEl.textContent = !err.inFront
        ? 'Dietro cam'
        : Number.isFinite(err.errorPx)
          ? `${err.errorPx.toFixed(1)} px`
          : '--';
    });

    this.updateSummaryPill(errors);
  }

  updateSummaryPill(errors = this.getPairErrorsSnapshot()) {
    const pillEl = this.panelEl?.querySelector('#calib-pnp-summary-pill');
    if (!pillEl) return;

    const count = this.correspondences.length;
    if (count === 0) {
      pillEl.className = 'calib-pnp-pill neutral';
      pillEl.textContent = '0/4';
      return;
    }

    const validErrors = errors.filter((e) => e.inFront && Number.isFinite(e.errorPx));
    if (validErrors.length === 0) {
      pillEl.className = 'calib-pnp-pill bad';
      pillEl.textContent = `${count} • fuori vista`;
      return;
    }

    const meanErr = validErrors.reduce((acc, e) => acc + e.errorPx, 0) / validErrors.length;
    const tier = count < 4 && meanErr > 10 ? 'warn' : getErrorTier(meanErr, true);
    pillEl.className = `calib-pnp-pill ${tier}`;
    pillEl.textContent = `${count}/4+ • ~${meanErr.toFixed(1)} px`;
  }

  updatePnpControlsUI() {
    if (!this.panelEl) return;
    const toggleBtn = this.panelEl.querySelector('#calib-pnp-toggle');
    const toggleLabel = this.panelEl.querySelector('#calib-pnp-toggle-label');
    const solveBtn = this.panelEl.querySelector('#calib-pnp-solve');
    const hintEl = this.panelEl.querySelector('#calib-pnp-hint');
    const nudgeEl = this.panelEl.querySelector('#calib-pnp-opacity-nudge');
    const footerEl = this.panelEl.querySelector('#calib-pnp-footer');
    const visBtn = this.panelEl.querySelector('#calib-pnp-vis-toggle');
    const visLabel = this.panelEl.querySelector('#calib-pnp-vis-label');

    toggleBtn?.classList.toggle('active', this.pnpMode);
    if (toggleLabel) {
      toggleLabel.textContent = this.pnpMode ? 'Ferma Raccolta' : (this.correspondences.length > 0 ? 'Aggiungi Coppie' : 'Avvia Raccolta');
    }

    if (solveBtn) {
      solveBtn.disabled = this.correspondences.length < 4 || this.isSolvingPnP;
      solveBtn.innerHTML = this.isSolvingPnP
        ? `${icon('refresh-cw', { size: 14, className: 'spin' })} <span>Risolvo...</span>`
        : `${icon('zap', { size: 14 })} <span>Risolvi PnP</span>`;
    }

    if (nudgeEl) {
      nudgeEl.style.display = this.pnpMode && this.pnpStep === '2d' && this.overlayOpacity < 0.08 ? 'flex' : 'none';
    }

    const hasAnyPoints = this.correspondences.length > 0 || Boolean(this.pendingPoint3D);
    if (footerEl) {
      footerEl.style.display = hasAnyPoints ? 'flex' : 'none';
    }
    if (visBtn && visLabel) {
      visBtn.innerHTML = `${icon(this.showPnpVectors ? 'eye' : 'eye-off', { size: 13 })} <span id="calib-pnp-vis-label">${this.showPnpVectors ? 'Nascondi vettori' : 'Mostra vettori'}</span>`;
    }

    if (hintEl) {
      if (!this.pnpMode && this.correspondences.length === 0) {
        hintEl.textContent = '1. Clicca un punto sul modello 3D → 2. Clicca lo stesso punto sul video. Servono almeno 4 spigoli distanti.';
      } else if (!this.pnpMode && this.correspondences.length < 4) {
        hintEl.textContent = `Raccolte ${this.correspondences.length}/4 coppie minime. Riavvia la raccolta per aggiungerne altre.`;
      } else if (!this.pnpMode) {
        hintEl.textContent = 'I vettori a schermo mostrano lo scarto attuale tra modello 3D (ciano) e video (ambra). Premi Risolvi PnP per allineare.';
      } else if (this.pnpStep === '3d') {
        const pairNum = this.correspondences.length + 1;
        hintEl.textContent = `Coppia P${pairNum} — STEP 1 (opacità 10%): Clicca un punto geometrico noto sul modello 3D.`;
      } else {
        const pairNum = this.correspondences.length + 1;
        hintEl.textContent = `Coppia P${pairNum} — STEP 2 (opacità 75%): Clicca lo stesso punto sull’immagine video live (Esc per annullare P${pairNum}).`;
      }
    }

    if (this.hudBannerEl) {
      this.hudBannerEl.classList.toggle('visible', Boolean(this.isOpen && this.pnpMode));
      const stepBadge = this.hudBannerEl.querySelector('#pnp-hud-step-badge');
      const hudText = this.hudBannerEl.querySelector('#pnp-hud-text');
      const cancelBtn = this.hudBannerEl.querySelector('#pnp-hud-cancel-pending');
      const pairNum = this.correspondences.length + 1;

      if (this.pnpStep === '3d') {
        if (stepBadge) {
          stepBadge.textContent = `P${pairNum} · 1/2 3D`;
          stepBadge.className = 'pnp-hud-step-badge step-3d';
        }
        if (hudText) {
          hudText.textContent = 'Clicca uno spigolo sul modello 3D (trascina per orientare la vista)';
        }
        if (cancelBtn) cancelBtn.style.display = 'none';
      } else {
        if (stepBadge) {
          stepBadge.textContent = `P${pairNum} · 2/2 VIDEO`;
          stepBadge.className = 'pnp-hud-step-badge step-2d';
        }
        if (hudText) {
          hudText.textContent = 'Ora clicca lo stesso identico punto sul video sovrapposto';
        }
        if (cancelBtn) cancelBtn.style.display = 'inline-flex';
      }
    }

    this.updateSummaryPill();
  }

  renderVectorOverlay() {
    const svg = this.vectorSvgEl;
    if (!svg) return;

    const shouldDraw =
      this.isOpen &&
      this.showPnpVectors &&
      (this.correspondences.length > 0 || Boolean(this.pendingPoint3D));

    if (!shouldDraw) {
      if (svg.childElementCount > 0) svg.innerHTML = '';
      return;
    }

    const canvas = this.sceneManager.renderer.domElement;
    const width = canvas.clientWidth || window.innerWidth;
    const height = canvas.clientHeight || window.innerHeight;
    if (width <= 0 || height <= 0) return;

    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

    const pose = this.cameraProjector?.getCalibratedCameraPose(this.activeCameraName);
    const overlay = this.cameraProjector?.frustumOverlays?.get(this.activeCameraName);
    const overlayDepth = overlay?.depth || 2.0;
    const viewportCamera = this.sceneManager.camera;
    viewportCamera.updateMatrixWorld();

    const parts = [
      `<defs>
        <marker id="pnp-arrow-good" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="${TIER_COLORS.good}" />
        </marker>
        <marker id="pnp-arrow-warn" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="${TIER_COLORS.warn}" />
        </marker>
        <marker id="pnp-arrow-bad" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
          <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="${TIER_COLORS.bad}" />
        </marker>
        <marker id="pnp-arrow-preview" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#38bdf8" />
        </marker>
      </defs>`,
    ];

    const hasHoverFilter = this.hoveredPairIdx !== null;

    this.correspondences.forEach((corr, idx) => {
      const pairNum = idx + 1;
      const isHovered = this.hoveredPairIdx === idx;
      const groupOpacity = hasHoverFilter && !isHovered ? 0.35 : 1.0;

      const worldPt3D = new THREE.Vector3(corr.world_point[0], corr.world_point[1], corr.world_point[2]);
      const scr3D = projectWorldToScreen(worldPt3D, viewportCamera, width, height);

      let scr2D = null;
      let errInfo = { inFront: scr3D.inFront, errorPx: Infinity };

      if (pose) {
        const worldPt2D = getOverlayWorldPointFromPixelUv(
          corr.pixel_uv,
          pose.position,
          pose.quaternion,
          this.state.fovV,
          this.state.fovH,
          this.state.k1,
          this.state.k2,
          overlayDepth
        );
        scr2D = projectWorldToScreen(worldPt2D, viewportCamera, width, height);
        errInfo = computePairCameraPixelError(
          worldPt3D,
          corr.pixel_uv,
          pose.position,
          pose.quaternion,
          this.state.fovV,
          this.state.fovH,
          this.state.k1,
          this.state.k2
        );
      }

      const tier = getErrorTier(errInfo.errorPx, errInfo.inFront);
      const strokeColor = TIER_COLORS[tier];
      const strokeW = isHovered ? 3.0 : 2.2;

      parts.push(`<g opacity="${groupOpacity}">`);

      // Vettore 3D -> 2D quando entrambi i punti sono davanti alla camera
      if (scr3D.inFront && scr2D?.inFront) {
        const dx = scr2D.x - scr3D.x;
        const dy = scr2D.y - scr3D.y;
        const dist = Math.hypot(dx, dy);

        if (dist > 10) {
          const ux = dx / dist;
          const uy = dy / dist;
          const x1 = scr3D.x + ux * 7.5;
          const y1 = scr3D.y + uy * 7.5;
          const x2 = scr2D.x - ux * 8.5;
          const y2 = scr2D.y - uy * 8.5;

          parts.push(
            `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="rgba(10,13,20,0.85)" stroke-width="${strokeW + 2.4}" stroke-linecap="round" />`
          );
          parts.push(
            `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${strokeColor}" stroke-width="${strokeW}" stroke-linecap="round" marker-end="url(#pnp-arrow-${tier})" />`
          );
        }

        // Badge errore al punto medio del vettore
        const mx = (scr3D.x + scr2D.x) * 0.5;
        const my = (scr3D.y + scr2D.y) * 0.5;
        const nx = dist > 1 ? -(scr2D.y - scr3D.y) / dist : 0;
        const ny = dist > 1 ? (scr2D.x - scr3D.x) / dist : -1;
        const labelOffset = dist < 44 ? 20 : 12;
        const lx = mx + nx * labelOffset;
        const ly = my + ny * labelOffset;
        const pxLabel = Number.isFinite(errInfo.errorPx) ? `P${pairNum} · ${Math.round(errInfo.errorPx)}px` : `P${pairNum}`;
        const pillW = Math.max(46, pxLabel.length * 6.5 + 12);

        parts.push(
          `<g transform="translate(${lx.toFixed(1)}, ${ly.toFixed(1)})">
            <rect x="${(-pillW / 2).toFixed(1)}" y="-10" width="${pillW.toFixed(1)}" height="20" rx="6" fill="rgba(15, 23, 42, 0.9)" stroke="${strokeColor}" stroke-width="1.2" />
            <text x="0" y="3.5" text-anchor="middle" fill="#f8fafc" font-family="JetBrains Mono, monospace" font-size="10.5" font-weight="600">${pxLabel}</text>
          </g>`
        );
      }

      // Marker 3D (cerchio ciano)
      if (scr3D.inFront) {
        const r = isHovered ? 7.5 : 6;
        parts.push(
          `<g transform="translate(${scr3D.x.toFixed(1)}, ${scr3D.y.toFixed(1)})">
            <circle r="${r + 1.5}" fill="rgba(10, 13, 20, 0.85)" />
            <circle r="${r}" fill="rgba(56, 189, 248, 0.25)" stroke="#38bdf8" stroke-width="2" />
            <circle r="2" fill="#f8fafc" />
            <text x="-10" y="-9" text-anchor="end" fill="#7dd3fc" stroke="rgba(10,13,20,0.9)" stroke-width="3" paint-order="stroke" font-family="JetBrains Mono, monospace" font-size="10.5" font-weight="700">P${pairNum}·3D</text>
          </g>`
        );
      }

      // Marker 2D Video (rombo ambra/verde)
      if (scr2D?.inFront) {
        const d = isHovered ? 7.5 : 6;
        const targetColor = tier === 'good' ? '#34d399' : '#fbbf24';
        const behindNote = !scr3D.inFront ? ` (3D dietro camera)` : '';
        parts.push(
          `<g transform="translate(${scr2D.x.toFixed(1)}, ${scr2D.y.toFixed(1)})">
            <polygon points="0,${-d - 1.5} ${d + 1.5},0 0,${d + 1.5} ${-d - 1.5},0" fill="rgba(10, 13, 20, 0.85)" />
            <polygon points="0,${-d} ${d},0 0,${d} ${-d},0" fill="rgba(251, 191, 36, 0.22)" stroke="${targetColor}" stroke-width="2" />
            <circle r="1.8" fill="#f8fafc" />
            <text x="10" y="13" text-anchor="start" fill="${targetColor}" stroke="rgba(10,13,20,0.9)" stroke-width="3" paint-order="stroke" font-family="JetBrains Mono, monospace" font-size="10.5" font-weight="700">P${pairNum}·2D${behindNote}</text>
          </g>`
        );
      }

      parts.push('</g>');
    });

    // Punto 3D in sospeso + vettore anteprima verso cursore
    if (this.pendingPoint3D) {
      const nextNum = this.correspondences.length + 1;
      const pendingVec = new THREE.Vector3(
        this.pendingPoint3D[0],
        this.pendingPoint3D[1],
        this.pendingPoint3D[2]
      );
      const scrPending = projectWorldToScreen(pendingVec, viewportCamera, width, height);

      if (scrPending.inFront) {
        if (this.pointerScreenPos) {
          const dx = this.pointerScreenPos.x - scrPending.x;
          const dy = this.pointerScreenPos.y - scrPending.y;
          const dist = Math.hypot(dx, dy);
          if (dist > 12) {
            const ux = dx / dist;
            const uy = dy / dist;
            const x1 = scrPending.x + ux * 8;
            const y1 = scrPending.y + uy * 8;
            const x2 = this.pointerScreenPos.x - ux * 6;
            const y2 = this.pointerScreenPos.y - uy * 6;
            parts.push(
              `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="rgba(10,13,20,0.8)" stroke-width="4" stroke-dasharray="5 5" />`
            );
            parts.push(
              `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="#38bdf8" stroke-width="2" stroke-dasharray="5 5" marker-end="url(#pnp-arrow-preview)" />`
            );
          }
        }

        parts.push(
          `<g transform="translate(${scrPending.x.toFixed(1)}, ${scrPending.y.toFixed(1)})">
            <circle r="11" fill="none" stroke="rgba(56, 189, 248, 0.45)" stroke-width="1.5" stroke-dasharray="3 3" />
            <circle r="6.5" fill="rgba(56, 189, 248, 0.35)" stroke="#38bdf8" stroke-width="2.2" />
            <circle r="2" fill="#ffffff" />
            <text x="-11" y="-10" text-anchor="end" fill="#7dd3fc" stroke="rgba(10,13,20,0.9)" stroke-width="3" paint-order="stroke" font-family="JetBrains Mono, monospace" font-size="11" font-weight="700">P${nextNum}·3D (attesa video)</text>
          </g>`
        );
      }
    }

    svg.innerHTML = parts.join('');
  }

  buildBackendPayload(pose = null) {
    return {
      camera_id: this.activeCameraName,
      offset_xyz: [this.state.offsetX, this.state.offsetY, this.state.offsetZ],
      delta_euler_deg: [
        this.state.pitchDeg,
        this.state.yawDeg + (this.state.flip180 ? 180 : 0),
        this.state.rollDeg,
      ],
      fov_v_deg: this.state.fovV,
      fov_h_deg: this.state.fovH,
      distortion_coeffs: [this.state.k1, this.state.k2, 0.0, 0.0, 0.0],
      calibrated_matrix_world_gl: pose ? pose.matrixWorldElements : null,
    };
  }

  async solvePnP() {
    if (!this.haClient?.isAdmin) {
      this._showRbacToast('Calibrazione riservata agli utenti Admin.');
      return false;
    }
    if (this.correspondences.length < 4 || this.isSolvingPnP) return;
    const basePose = this.cameraProjector.getBaseCameraPose(this.activeCameraName);
    const currentPose = this.cameraProjector.getCalibratedCameraPose(this.activeCameraName);
    if (!basePose || !currentPose) return;

    this.isSolvingPnP = true;
    this.updatePnpControlsUI();
    this.setStatus('Risoluzione SolvePnP in corso...', 'info');

    let solvedResult = null;
    let usedSource = 'local';

    try {
      if (this.spatialStreamClient) {
        const prePayload = this.buildBackendPayload(currentPose);
        await this.spatialStreamClient.updateCameraCalibration(this.activeCameraName, prePayload);

        const res = await this.spatialStreamClient.solvePnP({
          camera_id: this.activeCameraName,
          correspondences: this.correspondences,
        });
        if (res && res.status === 'ok' && Array.isArray(res.matrix_world_gl) && res.matrix_world_gl.length === 16) {
          solvedResult = res;
          usedSource = 'backend';
        }
      }

      if (!solvedResult) {
        const localRes = solvePnPLocal(
          this.correspondences,
          currentPose.position,
          currentPose.quaternion,
          this.state.fovV,
          this.state.fovH,
          this.state.k1,
          this.state.k2
        );
        if (localRes) {
          solvedResult = localRes;
          usedSource = 'local';
        }
      }

      if (solvedResult && Array.isArray(solvedResult.matrix_world_gl)) {
        this.state = decomposeWorldMatrixToCalibState(
          solvedResult.matrix_world_gl,
          basePose,
          this.state
        );
        this.syncInputsFromState();
        this.applyLiveCalibration(true);
        this.saveStateToLocal(this.activeCameraName);

        this.showPnpVectors = true;
        this.setPnpMode(false);

        const errTxt = solvedResult.reprojection_error_px?.toFixed(1) ?? '--';
        const srcLabel = usedSource === 'backend' ? 'OpenCV SolvePnPRansac' : 'PnP Locale Browser';
        this.setStatus(
          `Allineato (${srcLabel})! Errore medio: ${errTxt} px.`,
          Number(solvedResult.reprojection_error_px) <= 15 ? 'success' : 'warn'
        );
      } else {
        this.setStatus(
          'SolvePnP non ha trovato una convergenza valida. Prova 4 punti più distanti e non allineati.',
          'error'
        );
      }
    } finally {
      this.isSolvingPnP = false;
      this.updatePnpControlsUI();
    }
  }

  async saveAndSubmitToBackend() {
    if (!this.haClient?.isAdmin) {
      this._showRbacToast('Calibrazione riservata agli utenti Admin.');
      return false;
    }
    this.saveStateToLocal(this.activeCameraName);
    const pose = this.cameraProjector.applyCameraCalibration(this.activeCameraName, this.state);

    if (!this.spatialStreamClient) {
      this.setStatus('Salvato in locale (Spatial Server non connesso).', 'info');
      return;
    }

    const payload = this.buildBackendPayload(pose);
    const res = await this.spatialStreamClient.updateCameraCalibration(this.activeCameraName, payload);
    if (res && res.status === 'ok') {
      this.setStatus('Calibrazione salvata e applicata al Raycaster 3D Python!', 'success');
    } else {
      this.setStatus('Salvato nel browser. Avvia spatial_server per sincronizzare il backend.', 'warn');
    }
  }

  setStatus(text, tone = 'info') {
    const el = this.panelEl?.querySelector('#calib-status-msg');
    if (!el) return;
    el.textContent = text;
    el.className = `calib-status-msg ${tone}`;
  }
}
