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
    this.controls.target.set(-0.5, 1.0, 16.0);

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

    // Stato follow continuo di un target dinamico (es. Robot Deebot)
    this.followTargetFn = null;
    this.followOffset = new THREE.Vector3(-2.1, 1.65, 2.1);

    // Sgancio automatico quando l'utente interagisce manualmente con la camera
    this._onUserInteract = () => {
      if (this.followTargetFn) {
        this.stopFollowing();
        if (this.isTransitioning) {
          this.isTransitioning = false;
          this.controls.enabled = true;
          this.onTransitionComplete = null;
        }
      }
    };
    this.domElement.addEventListener('pointerdown', this._onUserInteract, { passive: true });
    this.domElement.addEventListener('wheel', this._onUserInteract, { passive: true });
    this.domElement.addEventListener('touchstart', this._onUserInteract, { passive: true });

    // Preset Viste
    this.presets = {
      overview: {
        eye: new THREE.Vector3(24.0, 22.0, 32.0),
        target: new THREE.Vector3(-0.5, 1.0, 16.0),
        fov: 45,
      },
      gate: {
        eye: new THREE.Vector3(-12.2, 3.6, -1.5),
        target: new THREE.Vector3(-12.2, 1.0, 6.28),
        fov: 50,
      },
      carraio_cam: {
        eye: new THREE.Vector3(-11.29, 1.68, 6.03),
        target: new THREE.Vector3(-11.29, 0.5, -2.5),
        fov: 42,
      },
      living: {
        eye: new THREE.Vector3(6.0, 3.2, 6.4),
        target: new THREE.Vector3(2.8, 1.2, 3.2),
        fov: 48,
      },
      dining: {
        eye: new THREE.Vector3(8.0, 1.30, 7.0),
        target: new THREE.Vector3(12.8, 1.15, 3.6),
        fov: 50,
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
        eye: new THREE.Vector3(-24.0, 19.0, 36.0),
        target: new THREE.Vector3(-1.0, 1.0, 14.0),
        fov: 48,
      },
      irrigation_area1: {
        eye: new THREE.Vector3(-0.5, 14.0, 42.0),
        target: new THREE.Vector3(-0.5, 0.0, 27.5),
        fov: 48,
      },
      irrigation_area2: {
        eye: new THREE.Vector3(10.0, 11.0, 3.5),
        target: new THREE.Vector3(10.0, 0.0, 13.0),
        fov: 48,
      },
      irrigation_area3: {
        eye: new THREE.Vector3(-18.0, 13.0, 11.5),
        target: new THREE.Vector3(-4.0, 0.0, 11.5),
        fov: 48,
      },
      topdown: {
        eye: new THREE.Vector3(-0.5, 42.0, 16.01),
        target: new THREE.Vector3(-0.5, 0.0, 16.0),
        fov: 45,
      },
    };
  }

  startFollowing(getTargetFn, offset = new THREE.Vector3(-2.1, 1.65, 2.1), duration = 1.1, targetFov = 46) {
    if (typeof getTargetFn !== 'function') return;
    this.followTargetFn = getTargetFn;
    this.followOffset = offset.clone();

    const target = getTargetFn();
    if (!target || !Number.isFinite(target.x) || !Number.isFinite(target.y) || !Number.isFinite(target.z)) {
      this.stopFollowing();
      return;
    }

    const eye = target.clone().add(this.followOffset);
    this.flyTo(eye, target, duration, null, targetFov, true);
  }

  stopFollowing() {
    this.followTargetFn = null;
  }

  update(delta) {
    if (this.isTransitioning) {
      if (this.followTargetFn) {
        const liveTarget = this.followTargetFn();
        if (liveTarget && Number.isFinite(liveTarget.x) && Number.isFinite(liveTarget.y) && Number.isFinite(liveTarget.z)) {
          this.endTarget.copy(liveTarget);
          this.targetPos.copy(liveTarget).add(this.followOffset);
        }
      }

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
    } else if (this.followTargetFn) {
      const liveTarget = this.followTargetFn();
      if (liveTarget && Number.isFinite(liveTarget.x) && Number.isFinite(liveTarget.y) && Number.isFinite(liveTarget.z)) {
        const desiredEye = liveTarget.clone().add(this.followOffset);
        const followLerp = Math.min(1.0, Math.max(0.01, (delta || 0.016) * 8.0));
        this.controls.target.lerp(liveTarget, followLerp);
        this.camera.position.lerp(desiredEye, followLerp);
      }
    }

    this.controls.update();
  }

    flyTo(eyePosition, targetPosition, duration = 1.2, onComplete = null, targetFov = 45, keepFollowing = false) {
      if (eyePosition && !eyePosition.isVector3 && eyePosition.position && eyePosition.target) {
        const opts = eyePosition;
        return this.flyTo(
          opts.position,
          opts.target,
          opts.duration ?? 1.2,
          opts.onComplete ?? null,
          opts.fov ?? 45,
          Boolean(opts.keepFollowing)
        );
      }

      if (!keepFollowing) {
        this.stopFollowing();
      }

      const validEye = eyePosition && Number.isFinite(eyePosition.x) && Number.isFinite(eyePosition.y) && Number.isFinite(eyePosition.z);
      const validTarget = targetPosition && Number.isFinite(targetPosition.x) && Number.isFinite(targetPosition.y) && Number.isFinite(targetPosition.z);
      if (!validEye || !validTarget) {
        console.warn('[CameraController] flyTo ignorato per coordinate non valide:', { eyePosition, targetPosition });
        return;
      }

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

    /**
     * Applica istantaneamente una posa camera (usata dai cursori live della calibrazione POV).
     */
    setInstantCameraPose(position, quaternion, fov = null) {
      this.stopFollowing();
      this.isTransitioning = false;
      this.onCompleteCallback = null;
      this.camera.position.copy(position);

      const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(quaternion).normalize();
      const lookTarget = position.clone().add(forward.multiplyScalar(12));
      this.controls.target.copy(lookTarget);
      this.camera.lookAt(lookTarget);

      if (fov !== null && Number.isFinite(fov)) {
        this.camera.fov = fov;
        this.camera.updateProjectionMatrix();
      }
      this.controls.update();
    }

    /**
     * Sposta la camera nella posizione POV esatta della telecamera (con eventuale calibrazione salvata).
     */
    flyToCameraPOV(camNode, duration = 1.5, onComplete = null) {
      const worldPos = new THREE.Vector3();
      const worldDir = new THREE.Vector3();
      camNode.getWorldPosition(worldPos);
      camNode.getWorldDirection(worldDir);

      const fov = camNode.isPerspectiveCamera && camNode.fov ? camNode.fov : 42;
      // Sposta leggermente avanti (25cm) lungo la direzione visiva per non clippare la scocca della camera
      const eyePos = worldPos.clone().add(worldDir.clone().multiplyScalar(0.25));
      const lookTarget = eyePos.clone().add(worldDir.clone().multiplyScalar(12));

      this.flyTo(eyePos, lookTarget, duration, () => {
        if (onComplete) onComplete();
      }, fov);
    }
  }
