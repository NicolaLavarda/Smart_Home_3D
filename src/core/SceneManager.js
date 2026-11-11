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

    // Setup Camera
    this.camera = new THREE.PerspectiveCamera(45, this.width / this.height, 0.1, 1000);
    this.camera.position.set(22, 18, 22);

    // WebGL Renderer calibrato
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      powerPreference: 'high-performance',
      alpha: false,
    });
    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
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

    window.addEventListener('resize', this.onWindowResize.bind(this));

    this.updateCallbacks = [];
    this.isNightMode = false;
    this.clock = new THREE.Clock();

    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
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
    this.sunLight = new THREE.DirectionalLight(0xfffdf5, 1.4);
    this.sunLight.position.set(25, 45, 20);
    this.sunLight.castShadow = true;
    this.sunLight.shadow.mapSize.width = 2048;
    this.sunLight.shadow.mapSize.height = 2048;
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
  }

  onWindowResize() {
    this.width = window.innerWidth;
    this.height = window.innerHeight;
    this.camera.aspect = this.width / this.height;
    this.camera.updateProjectionMatrix();

    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.css2dRenderer.setSize(this.width, this.height);
  }

  addUpdateCallback(fn) {
    this.updateCallbacks.push(fn);
  }

  removeUpdateCallback(fn) {
    this.updateCallbacks = this.updateCallbacks.filter((cb) => cb !== fn);
  }

  animate() {
    requestAnimationFrame(this.animate);
    const delta = this.clock.getDelta();
    const elapsed = this.clock.getElapsedTime();

    for (let i = 0; i < this.updateCallbacks.length; i++) {
      this.updateCallbacks[i](delta, elapsed);
    }

    this.renderer.render(this.scene, this.camera);
    this.css2dRenderer.render(this.scene, this.camera);
  }
}
