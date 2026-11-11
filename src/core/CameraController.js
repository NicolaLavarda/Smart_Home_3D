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
    this.controls.target.set(3, 1, -13);

    this.isTransitioning = false;
    this.transitionStart = 0;
    this.transitionDuration = 1.2;
    this.startPos = new THREE.Vector3();
    this.targetPos = new THREE.Vector3();
    this.startTarget = new THREE.Vector3();
    this.endTarget = new THREE.Vector3();
    this.onTransitionComplete = null;

    // Preset Viste
    this.presets = {
      overview: {
        eye: new THREE.Vector3(22, 18, 22),
        target: new THREE.Vector3(3, 1, -13),
      },
      gate: {
        eye: new THREE.Vector3(-12, 7, 7),
        target: new THREE.Vector3(-5.3, 1.2, 0),
      },
      carraio_cam: {
        eye: new THREE.Vector3(-5.3, 2.3, -0.1),
        target: new THREE.Vector3(-5.3, 0.4, 10.0),
      },
      living: {
        eye: new THREE.Vector3(2, 3.8, -2),
        target: new THREE.Vector3(5.5, 1.2, -5.5),
      },
      kitchen: {
        eye: new THREE.Vector3(7.5, 4.2, -9.5),
        target: new THREE.Vector3(9.2, 1.4, -5.5),
      },
      topdown: {
        eye: new THREE.Vector3(3, 36, -13.01),
        target: new THREE.Vector3(3, 0, -13),
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

  flyTo(eyePosition, targetPosition, duration = 1.2, onComplete = null) {
    this.controls.enabled = false;
    this.isTransitioning = true;
    this.transitionStart = performance.now() / 1000;
    this.transitionDuration = duration;

    this.startPos.copy(this.camera.position);
    this.targetPos.copy(eyePosition);

    this.startTarget.copy(this.controls.target);
    this.endTarget.copy(targetPosition);

    this.onTransitionComplete = onComplete;
  }

  flyToPreset(presetKey, duration = 1.2) {
    const preset = this.presets[presetKey];
    if (preset) {
      this.flyTo(preset.eye, preset.target, duration);
    }
  }

  flyToCameraPOV(camNode, duration = 1.5, onComplete = null) {
    const worldPos = new THREE.Vector3();
    const worldDir = new THREE.Vector3();
    camNode.getWorldPosition(worldPos);
    camNode.getWorldDirection(worldDir);

    const lookTarget = worldPos.clone().add(worldDir.clone().multiplyScalar(12));

    this.flyTo(worldPos, lookTarget, duration, () => {
      if (camNode.isPerspectiveCamera && camNode.fov) {
        this.camera.fov = camNode.fov;
        this.camera.updateProjectionMatrix();
      }
      if (onComplete) onComplete();
    });
  }
}
