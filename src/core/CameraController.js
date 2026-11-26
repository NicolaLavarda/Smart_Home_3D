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
    this.controls.minDistance = 0.8;
    this.controls.maxDistance = 160.0;
    this.controls.target.set(-0.5, 1.0, 16.0);
    this.activePresetKey = 'overview';

    this.isTransitioning = false;
    this.transitionStart = 0;
    this.transitionDuration = 1.2;
    this.startPos = new THREE.Vector3();
    this.targetPos = new THREE.Vector3();
    this.startTarget = new THREE.Vector3();
    this.endTarget = new THREE.Vector3();
    this.startFov = 56;
    this.targetFov = 56;
    this.onTransitionComplete = null;

    // Stato follow continuo di un target dinamico (es. Robot Deebot)
    this.followTargetFn = null;
    this.followOffset = new THREE.Vector3(-2.1, 1.65, 2.1);

    // Stato vista POV telecamera (per overlay video live/replay automatico)
    this.activePovCameraName = null;
    this._povPhase = 'idle'; // 'idle' | 'entering' | 'active'
    this._povLockedPos = null;
    this._povLockedDir = null;
    this._povLockedFov = null;
    this._povDockedPerfMs = 0;
    this._povExitLocked = false;
    this._povViewportFovResolver = null;
    this._povListeners = new Set();
    this._povPointerDownPos = null;
    this._tmpPovDir = new THREE.Vector3();

    // Sgancio automatico quando l'utente interagisce manualmente con la camera
    this._onUserInteract = (event) => {
      if (this.followTargetFn) {
        this.stopFollowing();
        if (this.isTransitioning) {
          this.isTransitioning = false;
          this.controls.enabled = true;
          this.onTransitionComplete = null;
        }
      }

      if (this.activePovCameraName && !this._povExitLocked) {
        if (event?.type === 'wheel' || (event?.type === 'touchstart' && (event.touches?.length || 0) >= 2)) {
          if (this.isTransitioning) {
            this.isTransitioning = false;
            this.controls.enabled = true;
            this.onTransitionComplete = null;
          }
          this.exitCameraPOV({ reason: event.type });
          return;
        }
        if (event?.type === 'pointerdown') {
          this._povPointerDownPos = { x: event.clientX, y: event.clientY };
        }
      }
    };
    this._onPovPointerMove = (event) => {
      if (!this._povPointerDownPos || !this.activePovCameraName || this._povExitLocked) return;
      const dx = event.clientX - this._povPointerDownPos.x;
      const dy = event.clientY - this._povPointerDownPos.y;
      if (Math.hypot(dx, dy) > 5) {
        this._povPointerDownPos = null;
        if (this.isTransitioning) {
          this.isTransitioning = false;
          this.controls.enabled = true;
          this.onTransitionComplete = null;
        }
        this.exitCameraPOV({ reason: 'drag' });
      }
    };
    this._onPovPointerUp = () => {
      this._povPointerDownPos = null;
    };
    this.domElement.addEventListener('pointerdown', this._onUserInteract, { passive: true });
    this.domElement.addEventListener('pointermove', this._onPovPointerMove, { passive: true });
    this.domElement.addEventListener('pointerup', this._onPovPointerUp, { passive: true });
    this.domElement.addEventListener('pointercancel', this._onPovPointerUp, { passive: true });
    this.domElement.addEventListener('wheel', this._onUserInteract, { passive: true });
    this.domElement.addEventListener('touchstart', this._onUserInteract, { passive: true });

    // Preset Viste (FOV più ampio 54°-62° V per far respirare gli spazi interni ed esterni)
    this.presets = {
      overview: {
        eye: new THREE.Vector3(24.0, 22.0, 32.0),
        target: new THREE.Vector3(-0.5, 1.0, 16.0),
        fov: 56,
      },
      gate: {
        eye: new THREE.Vector3(-12.2, 3.6, -1.5),
        target: new THREE.Vector3(-12.2, 1.0, 6.28),
        fov: 58,
      },
      carraio_cam: {
        eye: new THREE.Vector3(-11.29, 1.68, 6.03),
        target: new THREE.Vector3(-11.29, 0.5, -2.5),
        fov: 58,
      },
      living: {
        eye: new THREE.Vector3(6.0, 3.2, 6.4),
        target: new THREE.Vector3(2.8, 1.2, 3.2),
        fov: 60,
      },
      dining: {
        eye: new THREE.Vector3(8.65, 1.28, 6.54),
        target: new THREE.Vector3(12.8, 1.15, 3.6),
        fov: 60,
      },
      kitchen: {
        eye: new THREE.Vector3(11.2, 2.6, 3.4),
        target: new THREE.Vector3(7.8, 1.1, 6.2),
        fov: 60,
      },
      laundry: {
        eye: new THREE.Vector3(1.12, 1.46, 12.90),
        target: new THREE.Vector3(0.98, 0.95, 14.78),
        fov: 62,
      },
      garden: {
        eye: new THREE.Vector3(-24.0, 19.0, 36.0),
        target: new THREE.Vector3(-1.0, 1.0, 14.0),
        fov: 58,
      },
      irrigation_area1: {
        eye: new THREE.Vector3(-0.5, 14.0, 42.0),
        target: new THREE.Vector3(-0.5, 0.0, 27.5),
        fov: 56,
      },
      irrigation_area2: {
        eye: new THREE.Vector3(10.0, 11.0, 3.5),
        target: new THREE.Vector3(10.0, 0.0, 13.0),
        fov: 56,
      },
      irrigation_area3: {
        eye: new THREE.Vector3(-18.0, 13.0, 11.5),
        target: new THREE.Vector3(-4.0, 0.0, 11.5),
        fov: 56,
      },
      topdown: {
        eye: new THREE.Vector3(-0.5, 45.0, 15.01),
        target: new THREE.Vector3(-0.5, 0.0, 15.0),
        fov: 54,
      },
      // Viste contestuali dedicate per i 5 centri di controllo / dispositivi (primo piano + contesto stanza/giardino)
      device_thermal: {
        // Interno lavanderia (oltre il muro nord a Z=12.63 verso il portico) con caldaia e puffer in primo piano
        eye: new THREE.Vector3(1.12, 1.46, 12.90),
        target: new THREE.Vector3(0.98, 0.95, 14.78),
        fov: 62,
      },
      device_irrigation: {
        eye: new THREE.Vector3(-16.0, 17.5, 34.0),
        target: new THREE.Vector3(0.5, 0.5, 16.5),
        fov: 58,
      },
      device_tv: {
        eye: new THREE.Vector3(5.3, 2.05, 4.7),
        target: new THREE.Vector3(1.0, 1.15, 2.85),
        fov: 58,
      },
      device_dishwasher: {
        // Stessa angolazione diagonale della vista cucina, centrata e leggermente avvicinata sulla lavastoviglie
        eye: new THREE.Vector3(10.55, 1.88, 4.75),
        target: new THREE.Vector3(8.38, 0.72, 7.00),
        fov: 58,
      },
      device_deebot: {
        // Vista di fallback usata solo se le coordinate live/3D del robot non sono disponibili
        eye: new THREE.Vector3(9.4, 2.25, 4.3),
        target: new THREE.Vector3(13.2, 0.45, 2.1),
        fov: 58,
      },
    };

    // Varianti responsive dedicate a schermi verticali/mobile (aspect < 0.85)
    // Garantiscono inquadratura completa della casa principale e proporzioni corrette senza tagli
    this.mobilePresets = {
      overview: {
        eye: new THREE.Vector3(20.0, 32.0, 37.5),
        target: new THREE.Vector3(7.2, 1.0, 7.5),
        fov: 62,
      },
      topdown: {
        eye: new THREE.Vector3(6.9, 46.0, 10.21),
        target: new THREE.Vector3(6.9, 0.0, 10.2),
        fov: 56,
      },
      garden: {
        eye: new THREE.Vector3(-27.0, 24.5, 40.0),
        target: new THREE.Vector3(-1.5, 1.0, 14.0),
        fov: 64,
      },
      living: {
        eye: new THREE.Vector3(6.1, 3.1, 6.5),
        target: new THREE.Vector3(2.6, 1.15, 3.1),
        fov: 66,
      },
      dining: {
        eye: new THREE.Vector3(8.45, 1.41, 6.54),
        target: new THREE.Vector3(12.6, 1.15, 3.6),
        fov: 66,
      },
      kitchen: {
        eye: new THREE.Vector3(11.3, 2.55, 3.4),
        target: new THREE.Vector3(7.8, 1.05, 6.2),
        fov: 66,
      },
      laundry: {
        eye: new THREE.Vector3(1.12, 1.46, 12.90),
        target: new THREE.Vector3(0.98, 0.90, 14.78),
        fov: 70,
      },
      device_thermal: {
        eye: new THREE.Vector3(1.12, 1.46, 12.90),
        target: new THREE.Vector3(0.98, 0.90, 14.78),
        fov: 70,
      },
      device_irrigation: {
        eye: new THREE.Vector3(-22.0, 24.5, 40.0),
        target: new THREE.Vector3(-0.5, 0.5, 15.0),
        fov: 64,
      },
      device_tv: {
        eye: new THREE.Vector3(5.3, 2.05, 4.7),
        target: new THREE.Vector3(1.0, 1.15, 2.85),
        fov: 66,
      },
      device_dishwasher: {
        eye: new THREE.Vector3(10.55, 1.88, 4.75),
        target: new THREE.Vector3(8.38, 0.72, 7.00),
        fov: 66,
      },
      device_deebot: {
        eye: new THREE.Vector3(9.4, 2.25, 4.3),
        target: new THREE.Vector3(13.2, 0.45, 2.1),
        fov: 64,
      },
    };

    // Avvio immediato in vista Panoramica adattata al viewport corrente (PC o Mobile)
    this.applyPresetImmediate('overview');
  }

  isPortraitViewport() {
    let aspect = this.camera?.aspect;
    if (!Number.isFinite(aspect) || aspect <= 0) {
      if (typeof window !== 'undefined' && window.innerHeight > 0) {
        aspect = window.innerWidth / window.innerHeight;
      } else {
        aspect = 16 / 9;
      }
    }
    return aspect < 0.85;
  }

  getResponsiveFov(baseFov = 58) {
    return this.isPortraitViewport() ? Math.min(72, baseFov + 8) : baseFov;
  }

  getPresetForViewport(presetKey) {
    const base = this.presets[presetKey];
    if (!base) return null;
    if (this.isPortraitViewport()) {
      if (this.mobilePresets[presetKey]) {
        return this.mobilePresets[presetKey];
      }
      return {
        eye: base.eye,
        target: base.target,
        fov: Math.min(64, (base.fov || 45) + 8),
      };
    }
    return base;
  }

  applyPresetImmediate(presetKey) {
    const preset = this.getPresetForViewport(presetKey);
    if (!preset) return false;
    this.exitCameraPOV({ reason: 'preset' });
    this.stopFollowing();
    this.isTransitioning = false;
    this.controls.enabled = true;
    this.onTransitionComplete = null;
    this.activePresetKey = presetKey;

    this.camera.position.copy(preset.eye);
    this.controls.target.copy(preset.target);
    this.camera.fov = preset.fov || 45;
    this.camera.updateProjectionMatrix();
    this.camera.lookAt(preset.target);
    this.controls.update();
    return true;
  }

  startFollowing(getTargetFn, offset = new THREE.Vector3(-2.1, 1.65, 2.1), duration = 1.1, targetFov = 58) {
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

  onPovChange(listener) {
    if (typeof listener !== 'function') return () => {};
    this._povListeners.add(listener);
    return () => this._povListeners.delete(listener);
  }

  _emitPovChange(payload) {
    this._povListeners.forEach((fn) => {
      try {
        fn(payload);
      } catch (err) {
        console.warn('[CameraController] Errore listener POV:', err);
      }
    });
  }

  setPovExitLocked(locked) {
    this._povExitLocked = Boolean(locked);
  }

  setPovViewportFovResolver(resolverFn) {
    this._povViewportFovResolver = typeof resolverFn === 'function' ? resolverFn : null;
  }

  _resolvePovFov(camName, fallbackFov = 42) {
    if (camName && typeof this._povViewportFovResolver === 'function') {
      const resolved = Number(this._povViewportFovResolver(camName, this.camera?.aspect));
      if (Number.isFinite(resolved) && resolved > 0) {
        return resolved;
      }
    }
    return fallbackFov;
  }

  syncPovViewportFov() {
    if (!this.activePovCameraName || this._povPhase !== 'active' || this.isTransitioning) return;
    const nextFov = this._resolvePovFov(this.activePovCameraName, this.camera.fov);
    if (Number.isFinite(nextFov) && nextFov > 0 && Math.abs(this.camera.fov - nextFov) > 0.05) {
      this.camera.fov = nextFov;
      this.camera.updateProjectionMatrix();
      this._povLockedFov = nextFov;
    }
  }

  exitCameraPOV({ reason = 'manual' } = {}) {
    if (!this.activePovCameraName && this._povPhase === 'idle') return false;
    const previousCameraName = this.activePovCameraName;
    this.activePovCameraName = null;
    this._povPhase = 'idle';
    this._povLockedPos = null;
    this._povLockedDir = null;
    this._povLockedFov = null;
    this._povPointerDownPos = null;
    this._emitPovChange({
      cameraName: null,
      phase: 'exited',
      previousCameraName,
      reason,
    });
    return true;
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

    if (
      !this.isTransitioning &&
      this._povPhase === 'active' &&
      this.activePovCameraName &&
      !this._povExitLocked &&
      this._povLockedPos &&
      this._povLockedDir &&
      performance.now() - this._povDockedPerfMs > 180
    ) {
      this.camera.getWorldDirection(this._tmpPovDir);
      const posMoved = this.camera.position.distanceTo(this._povLockedPos) > 0.04;
      const dirMoved = this._tmpPovDir.angleTo(this._povLockedDir) > 0.02;
      const fovMoved = this._povLockedFov !== null && Math.abs(this.camera.fov - this._povLockedFov) > 0.5;
      if (posMoved || dirMoved || fovMoved) {
        this.exitCameraPOV({ reason: 'moved' });
      }
    }
  }

    flyTo(eyePosition, targetPosition, duration = 1.2, onComplete = null, targetFov = 56, keepFollowing = false, keepPov = false) {
      if (eyePosition && !eyePosition.isVector3 && eyePosition.position && eyePosition.target) {
        const opts = eyePosition;
        return this.flyTo(
          opts.position,
          opts.target,
          opts.duration ?? 1.2,
          opts.onComplete ?? null,
          opts.fov ?? 45,
          Boolean(opts.keepFollowing),
          Boolean(opts.keepPov)
        );
      }

      if (!keepPov) {
        this.exitCameraPOV({ reason: 'navigate' });
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
      this.targetFov = targetFov || 56;

      this.onTransitionComplete = onComplete;
    }

    flyToPreset(presetKey, duration = 1.2) {
      const preset = this.getPresetForViewport(presetKey);
      if (preset) {
        this.activePresetKey = presetKey;
        if (duration <= 0) {
          this.applyPresetImmediate(presetKey);
        } else {
          this.flyTo(preset.eye, preset.target, duration, null, preset.fov || 56);
        }
      }
    }

    /**
     * Applica istantaneamente una posa camera (usata dai cursori live della calibrazione POV).
     */
    setInstantCameraPose(position, quaternion, fov = null, cameraName = null) {
      this.stopFollowing();
      this.isTransitioning = false;
      this.onTransitionComplete = null;
      this.camera.position.copy(position);

      const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(quaternion).normalize();
      const lookTarget = position.clone().add(forward.clone().multiplyScalar(12));
      this.controls.target.copy(lookTarget);
      this.camera.lookAt(lookTarget);

      const resolvedCamName = cameraName || this.activePovCameraName;
      if (fov !== null && Number.isFinite(fov)) {
        this.camera.fov = this._resolvePovFov(resolvedCamName, fov);
        this.camera.updateProjectionMatrix();
      }
      this.controls.update();

      if (cameraName) {
        this.activePovCameraName = cameraName;
        this._povPhase = 'active';
      }
      if (this.activePovCameraName) {
        this._povLockedPos = position.clone();
        this._povLockedDir = forward.clone().normalize();
        this._povLockedFov = this.camera.fov;
      }
    }

    /**
     * Sposta la camera nella posizione POV esatta della telecamera (con eventuale calibrazione salvata).
     */
    flyToCameraPOV(camNode, duration = 1.5, onComplete = null, options = {}) {
      if (!camNode) return;
      camNode.updateMatrixWorld?.(true);
      const worldPos = new THREE.Vector3();
      const worldDir = new THREE.Vector3();
      camNode.getWorldPosition(worldPos);
      camNode.getWorldDirection(worldDir);
      worldDir.normalize();

      const camName = camNode.name || options.cameraName || null;
      const forCalibration = Boolean(options?.forCalibration);
      const rawFov = camNode.isPerspectiveCamera && camNode.fov ? camNode.fov : 42;
      const fov = this._resolvePovFov(camName, rawFov);
      // Posizione ottica esatta della lente (0m offset) così l'overlay video 3D coincide pixel-per-pixel col modello
      const eyePos = worldPos.clone();
      const lookTarget = eyePos.clone().add(worldDir.clone().multiplyScalar(12));

      const previousCameraName = this.activePovCameraName;
      if (previousCameraName && previousCameraName !== camName) {
        this.exitCameraPOV({ reason: 'switch_pov' });
      }

      this.activePovCameraName = camName;
      this._povPhase = 'entering';
      this._povLockedPos = null;
      this._povLockedDir = null;
      this._povLockedFov = null;

      this._emitPovChange({
        cameraName: camName,
        phase: 'entering',
        previousCameraName: previousCameraName !== camName ? previousCameraName : null,
        forCalibration,
      });

      const finishDock = () => {
        if (this.activePovCameraName === camName) {
          this.controls.update();
          this._povPhase = 'active';
          this._povDockedPerfMs = performance.now();
          this._povLockedPos = this.camera.position.clone();
          this._povLockedDir = this.camera.getWorldDirection(new THREE.Vector3()).normalize();
          this._povLockedFov = this.camera.fov;
          this._emitPovChange({
            cameraName: camName,
            phase: 'active',
            previousCameraName: null,
            forCalibration,
          });
        }
        if (onComplete) onComplete();
      };

      if (duration <= 0) {
        this.stopFollowing();
        this.isTransitioning = false;
        this.controls.enabled = true;
        this.onTransitionComplete = null;
        this.camera.position.copy(eyePos);
        this.controls.target.copy(lookTarget);
        this.camera.fov = fov;
        this.camera.updateProjectionMatrix();
        this.camera.lookAt(lookTarget);
        this.controls.update();
        finishDock();
        return;
      }

      this.flyTo(eyePos, lookTarget, duration, finishDock, fov, false, true);
    }
  }
