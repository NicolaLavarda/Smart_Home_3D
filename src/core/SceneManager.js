import * as THREE from 'three';
import { CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js';

export class SceneManager {
  constructor(canvasContainer, css2dContainer) {
    this.canvasContainer = canvasContainer;
    this.css2dContainer = css2dContainer;

    this.scene = new THREE.Scene();
    // Colore sfondo neutrale stile Blender Viewport (grigio studio per contrasto nitido)
    this.blenderBgColor = 0x393c40;
    this.scene.background = new THREE.Color(this.blenderBgColor);

    this.width = window.innerWidth;
    this.height = window.innerHeight;
    this.isMobileProfile = this.detectMobileTouchProfile();

    // Setup Camera
    this.camera = new THREE.PerspectiveCamera(56, this.width / this.height, 0.1, 1000);
    this.camera.position.set(23.0, 18.0, 25.0);

    // WebGL Renderer calibrato con profilo mobile/desktop adattivo (qualità HD nitida + shadow map on-demand su mobile)
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      powerPreference: 'high-performance',
      alpha: false,
    });
    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(this.getEffectivePixelRatio());
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.shadowMap.autoUpdate = !this.isMobileProfile;
    this.renderer.shadowMap.needsUpdate = true;
    this.renderer.localClippingEnabled = true;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.15;
    this.canvasContainer.appendChild(this.renderer.domElement);

    // CSS2D Renderer per badge HTML
    this.css2dRenderer = new CSS2DRenderer();
    this.css2dRenderer.setSize(this.width, this.height);
    this.css2dRenderer.domElement.style.position = 'absolute';
    this.css2dRenderer.domElement.style.top = '0px';
    this.css2dRenderer.domElement.style.left = '0px';
    this.css2dRenderer.domElement.style.pointerEvents = 'none';
    this.css2dContainer.appendChild(this.css2dRenderer.domElement);

    this.setupLighting();

    this._onWindowResize = this.onWindowResize.bind(this);
    window.addEventListener('resize', this._onWindowResize);

    this.updateCallbacks = [];
    this.resizeCallbacks = [];
    this.isNightMode = false;
    this.clock = new THREE.Clock();
    this._rafId = null;
    this._fpsFrames = 0;
    this._fpsLastMark = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    this.currentFps = 0;
    this.gpuRenderer = this._detectGpuRenderer();

    this.animate = this.animate.bind(this);
    this._onVisibilityChange = this.handleVisibilityChange.bind(this);
    if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
      document.addEventListener('visibilitychange', this._onVisibilityChange);
    }

    this._scheduleNextFrame();
  }

  detectMobileTouchProfile() {
    const hasTouch = typeof navigator !== 'undefined' && Number(navigator.maxTouchPoints) > 0;
    const isCoarse =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      Boolean(window.matchMedia('(pointer: coarse)')?.matches);
    const isFine =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      Boolean(window.matchMedia('(pointer: fine)')?.matches);
    const isNarrow =
      typeof window !== 'undefined' &&
      Number(window.innerWidth) > 0 &&
      Number(window.innerWidth) <= 900;
    // I portatili Windows con touchscreen hanno sia maxTouchPoints > 0 sia (pointer: fine) + schermo largo:
    // trattali come Desktop e riserva il profilo mobile a smartphone/tablet touch-first.
    return Boolean(isCoarse || isNarrow || (hasTouch && !isFine));
  }

  getEffectivePixelRatio() {
    const rawDpr = (typeof window !== 'undefined' && Number(window.devicePixelRatio)) || 1;
    const cap = this.detectMobileTouchProfile() ? 1.5 : 2.0;
    return Math.min(rawDpr, cap);
  }

  _detectGpuRenderer() {
    try {
      const gl = this.renderer?.getContext?.();
      if (!gl || typeof gl.getExtension !== 'function') return 'unknown';
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      if (dbg && typeof gl.getParameter === 'function') {
        const raw = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
        if (raw) return String(raw);
      }
      if (typeof gl.getParameter === 'function') {
        return String(gl.getParameter(gl.RENDERER) || 'webgl');
      }
    } catch {}
    return 'unknown';
  }

  getPerfStats() {
    const info = this.renderer?.info?.render || {};
    return {
      build: 'v3-hd',
      fps: this.currentFps,
      calls: info.calls ?? 0,
      triangles: info.triangles ?? 0,
      dpr: this.renderer?.getPixelRatio?.() ?? 1,
      mobile: this.isMobileProfile,
      gpu: this.gpuRenderer || 'unknown',
    };
  }

  requestShadowUpdate() {
    if (this.renderer?.shadowMap) {
      this.renderer.shadowMap.needsUpdate = true;
    }
  }

  setupLighting() {
    // 1. Luce Ambientale diffusa: illumina gli interni delle stanze e le pareti in ombra
    this.ambientLight = new THREE.AmbientLight(0xffffff, 0.75);
    this.scene.add(this.ambientLight);

    // 2. Luce Emisferica Studio: cielo chiaro sopra, rimbalzo neutro da terra
    this.hemiLight = new THREE.HemisphereLight(0xf1f5f9, 0x64748b, 0.65);
    this.hemiLight.position.set(0, 50, 0);
    this.scene.add(this.hemiLight);

    // 3. Sole Principale (Key Sun Light): luce solare chiara e calda con ombre morbide
    const shadowSize = this.isMobileProfile ? 1024 : 2048;
    this.sunLight = new THREE.DirectionalLight(0xfffdf5, 1.4);
    this.sunLight.position.set(25, 45, 20);
    this.sunLight.castShadow = true;
    this.sunLight.shadow.mapSize.width = shadowSize;
    this.sunLight.shadow.mapSize.height = shadowSize;
    this.sunLight.shadow.camera.near = 0.5;
    this.sunLight.shadow.camera.far = 150;
    this.sunLight.shadow.camera.left = -32;
    this.sunLight.shadow.camera.right = 32;
    this.sunLight.shadow.camera.top = 32;
    this.sunLight.shadow.camera.bottom = -32;
    this.sunLight.shadow.bias = -0.0003;
    this.scene.add(this.sunLight);

    // 4. Fill Light opposta: elimina le ombre troppo buie e rischiara i muri nord/est
    this.fillLight = new THREE.DirectionalLight(0xdbeafe, 0.55);
    this.fillLight.position.set(-20, 32, -25);
    this.scene.add(this.fillLight);
  }

  setNightMode(enabled) {
    this.isNightMode = enabled;
    if (enabled) {
      // Modalità Notturna: cielo blu notte scuro, illuminazione notturna
      this.scene.background.setHex(0x060a12);
      this.ambientLight.intensity = 0.12;
      this.ambientLight.color.setHex(0x38bdf8);
      this.hemiLight.intensity = 0.08;
      this.sunLight.intensity = 0.20;
      this.sunLight.color.setHex(0x60a5fa); // Luce lunare
      this.fillLight.intensity = 0.05;
      this.renderer.toneMappingExposure = 1.25;
    } else {
      // Modalità Giorno: sfondo Blender grigio studio e massima chiarezza architettonica
      this.scene.background.setHex(this.blenderBgColor);
      this.ambientLight.intensity = 0.75;
      this.ambientLight.color.setHex(0xffffff);
      this.hemiLight.intensity = 0.65;
      this.sunLight.intensity = 1.4;
      this.sunLight.color.setHex(0xfffdf5);
      this.fillLight.intensity = 0.55;
      this.renderer.toneMappingExposure = 1.15;
    }
    this.requestShadowUpdate();
  }

  onWindowResize() {
    this.width = window.innerWidth;
    this.height = window.innerHeight;
    this.isMobileProfile = this.detectMobileTouchProfile();
    this.camera.aspect = this.width / this.height;
    this.camera.updateProjectionMatrix();

    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(this.getEffectivePixelRatio());
    this.css2dRenderer.setSize(this.width, this.height);

    for (let i = 0; i < this.resizeCallbacks.length; i++) {
      try {
        this.resizeCallbacks[i](this.width, this.height);
      } catch (err) {
        console.warn('[SceneManager] Errore callback resize:', err);
      }
    }
  }

  addResizeCallback(fn) {
    if (typeof fn === 'function') {
      this.resizeCallbacks.push(fn);
    }
  }

  removeResizeCallback(fn) {
    this.resizeCallbacks = this.resizeCallbacks.filter((cb) => cb !== fn);
  }

  addUpdateCallback(fn) {
    this.updateCallbacks.push(fn);
  }

  removeUpdateCallback(fn) {
    this.updateCallbacks = this.updateCallbacks.filter((cb) => cb !== fn);
  }

  _scheduleNextFrame() {
    if (typeof document !== 'undefined' && document.hidden) {
      return;
    }
    if (this._rafId !== null) {
      return;
    }
    this._rafId = requestAnimationFrame(this.animate);
  }

  handleVisibilityChange() {
    if (typeof document !== 'undefined' && document.hidden) {
      if (this._rafId !== null) {
        if (typeof cancelAnimationFrame === 'function') {
          cancelAnimationFrame(this._rafId);
        }
        this._rafId = null;
      }
      return;
    }

    // Al ritorno in foreground, azzera il salto temporale accumulato dal Clock e riprendi il loop
    this.clock.start();
    this.clock.getDelta();
    this._scheduleNextFrame();
  }

  animate() {
    this._rafId = null;
    if (typeof document !== 'undefined' && document.hidden) {
      return;
    }

    this._scheduleNextFrame();
    const delta = this.clock.getDelta();
    const elapsed = this.clock.getElapsedTime();

    for (let i = 0; i < this.updateCallbacks.length; i++) {
      this.updateCallbacks[i](delta, elapsed);
    }

    this.renderer.render(this.scene, this.camera);
    this.css2dRenderer.render(this.scene, this.camera);

    this._fpsFrames++;
    const now = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
    const dtMs = now - this._fpsLastMark;
    if (dtMs >= 1000) {
      this.currentFps = Math.round((this._fpsFrames * 1000) / dtMs);
      this._fpsFrames = 0;
      this._fpsLastMark = now;
    }
  }
}
