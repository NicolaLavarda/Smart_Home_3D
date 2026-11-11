import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export class CameraController {
  constructor(camera, domElement) {
    this.camera = camera;
    this.domElement = domElement;

    this.controls = new OrbitControls(this.camera, this.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.05;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.02;
    this.controls.minDistance = 1.5;
    this.controls.maxDistance = 160.0;
    this.controls.target.set(4.0, 1.0, 12.0);

    this.isTransitioning = false;
    this.transitionStart = 0;
    this.transitionDuration = 1.2;
    this.startPos = new THREE.Vector3();
    this.targetPos = new THREE.Vector3();
    this.startTarget = new THREE.Vector3();
    this.endTarget = new THREE.Vector3();
    this.startFov = 45;
    this.targetFov = 45;
    this.onTransitionComplete = null;

    // Preset Viste
    this.presets = {
      overview: {
        eye: new THREE.Vector3(23.0, 18.0, 25.0),
        target: new THREE.Vector3(4.0, 1.0, 12.0),
        fov: 45,
      },
      gate: {
        eye: new THREE.Vector3(-5.8, 3.2, -7.0),
        target: new THREE.Vector3(-5.8, 1.0, 0.2),
        fov: 48,
      },
      carraio_cam: {
        eye: new THREE.Vector3(-5.3, 2.2, 0.35),
        target: new THREE.Vector3(-1.5, 0.8, 8.5),
        fov: 55,
      },
      living: {
        eye: new THREE.Vector3(6.0, 3.2, 6.4),
        target: new THREE.Vector3(2.8, 1.2, 3.2),
        fov: 48,
      },
      kitchen: {
        eye: new THREE.Vector3(11.2, 2.6, 3.4),
        target: new THREE.Vector3(7.8, 1.1, 6.2),
        fov: 50,
      },
      laundry: {
        eye: new THREE.Vector3(0.95, 1.65, 12.7),
        target: new THREE.Vector3(0.95, 0.95, 14.85),
        fov: 52,
      },
      garden: {
        eye: new THREE.Vector3(-19.1, 17.5, 30.5),
        target: new THREE.Vector3(3.5, 1.0, 8.9),
        fov: 48,
      },
      topdown: {
        eye: new THREE.Vector3(4.0, 36.0, 11.01),
        target: new THREE.Vector3(4.0, 0.0, 11.0),
        fov: 45,
      },
    };
  }

  update(delta) {
    if (this.isTransitioning) {
      const now = performance.now() / 1000;
      const elapsed = now - this.transitionStart;
      const progress = Math.min(elapsed / this.transitionDuration, 1.0);

      const t = progress * progress * (3 - 2 * progress);

      this.camera.position.lerpVectors(this.startPos, this.targetPos, t);
      this.controls.target.lerpVectors(this.startTarget, this.endTarget, t);

      if (this.startFov !== this.targetFov) {
        this.camera.fov = THREE.MathUtils.lerp(this.startFov, this.targetFov, t);
        this.camera.updateProjectionMatrix();
      }

      if (progress >= 1.0) {
        this.isTransitioning = false;
        this.controls.enabled = true;
        if (this.onTransitionComplete) {
          this.onTransitionComplete();
          this.onTransitionComplete = null;
        }
      }
    }

    this.controls.update();
  }

  flyTo(eyePosition, targetPosition, duration = 1.2, onComplete = null, targetFov = 45) {
    this.controls.enabled = false;
    this.isTransitioning = true;
    this.transitionStart = performance.now() / 1000;
    this.transitionDuration = duration;

    this.startPos.copy(this.camera.position);
    this.targetPos.copy(eyePosition);

    this.startTarget.copy(this.controls.target);
    this.endTarget.copy(targetPosition);

    this.startFov = this.camera.fov;
    this.targetFov = targetFov || 45;

    this.onTransitionComplete = onComplete;
  }

  flyToPreset(presetKey, duration = 1.2) {
    const preset = this.presets[presetKey];
    if (preset) {
      this.flyTo(preset.eye, preset.target, duration, null, preset.fov || 45);
    }
  }

  flyToCameraPOV(camNode, duration = 1.5, onComplete = null) {
    const worldPos = new THREE.Vector3();
    const worldDir = new THREE.Vector3();
    camNode.getWorldPosition(worldPos);
    camNode.getWorldDirection(worldDir);

    const fov = camNode.isPerspectiveCamera && camNode.fov ? camNode.fov : 65;
    // Sposta leggermente avanti (25cm) lungo la direzione visiva per non clippare la scocca della camera
    const eyePos = worldPos.clone().add(worldDir.clone().multiplyScalar(0.25));
    const lookTarget = eyePos.clone().add(worldDir.clone().multiplyScalar(12));

    this.flyTo(eyePos, lookTarget, duration, () => {
      if (onComplete) onComplete();
    }, fov);
  }
}
