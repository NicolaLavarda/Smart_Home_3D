import * as THREE from 'three';

/**
 * CameraFrustumOverlay
 *
 * Gestisce il piano di proiezione VideoTexture all'interno del frustum 3D di una telecamera:
 * - In modalità POV calibrazione: proietta il video live davanti alla camera con opacità 0%..100%
 *   e distorsione Brown-Conrady (k1, k2) applicata alle coordinate UV di una griglia 24x24.
 * - In vista esterna (Overview): mostra il feed video proiettato alla base del cono frustum.
 */
export class CameraFrustumOverlay {
  constructor(cameraName, options = {}) {
    this.cameraName = cameraName;
    this.fovV = options.fovV || 42.0;
    this.fovH = options.fovH || 80.0;
    this.aspect = options.aspect || 16 / 9;
    this.depth = options.depth || 2.0;
    this.opacity = options.opacity ?? 0.5;
    this.isPOVMode = false;
    this.distortion = [0, 0, 0, 0, 0];

    this.geometry = new THREE.PlaneGeometry(1, 1, 24, 24);
    this.basePositions = new Float32Array(this.geometry.attributes.position.array);
    this.baseUVs = new Float32Array(this.geometry.attributes.uv.array);

    this.material = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: this.opacity,
      side: THREE.DoubleSide,
      depthTest: false,
      depthWrite: false,
      visible: false,
    });

    this.mesh = new THREE.Mesh(this.geometry, this.material);
    this.mesh.name = `FrustumOverlay_${cameraName}`;
    this.mesh.renderOrder = 999;
    this.mesh.frustumCulled = false;

    this.videoTexture = null;
    this.updateGeometry();
  }

  attachVideoTexture(videoTexture) {
    this.videoTexture = videoTexture;
    this.material.map = videoTexture;
    this.material.needsUpdate = true;
  }

  setVisible(visible) {
    this.material.visible = Boolean(visible && this.videoTexture);
  }

  setOpacity(alpha) {
    this.opacity = THREE.MathUtils.clamp(Number(alpha), 0, 1);
    this.material.opacity = this.opacity;
  }

  setPOVMode(isPOV) {
    this.isPOVMode = Boolean(isPOV);
    this.depth = this.isPOVMode ? 2.0 : 15.95;
    this.material.depthTest = !this.isPOVMode;
    this.updateGeometry();
  }

  updateOptics({ fovV, fovH, aspect, distortion }) {
    if (fovV !== undefined) this.fovV = Number(fovV);
    if (fovH !== undefined) this.fovH = Number(fovH);
    if (aspect !== undefined) this.aspect = Number(aspect);
    if (Array.isArray(distortion)) {
      this.distortion = distortion.map((v) => Number(v) || 0);
    }
    this.updateGeometry();
  }

  updateGeometry() {
    const tanV = Math.tan(THREE.MathUtils.degToRad(this.fovV * 0.5));
    const tanH = this.fovH ? Math.tan(THREE.MathUtils.degToRad(this.fovH * 0.5)) : tanV * this.aspect;
    const h = 2.0 * tanV * this.depth;
    const w = 2.0 * tanH * this.depth;

    const posAttr = this.geometry.attributes.position;
    const uvAttr = this.geometry.attributes.uv;
    const k1 = this.distortion[0] || 0;
    const k2 = this.distortion[1] || 0;

    for (let i = 0; i < posAttr.count; i++) {
      const bx = this.basePositions[i * 3];
      const by = this.basePositions[i * 3 + 1];
      posAttr.setXYZ(i, bx * w, by * h, -this.depth);

      // Mappa UV con preview distorsione radiale Brown-Conrady
      const u0 = this.baseUVs[i * 2];
      const v0 = this.baseUVs[i * 2 + 1];
      if (Math.abs(k1) > 1e-5 || Math.abs(k2) > 1e-5) {
        const xn = (u0 - 0.5) * 2.0 * tanH;
        const yn = (v0 - 0.5) * 2.0 * tanV;
        const r2 = xn * xn + yn * yn;
        const radial = 1.0 + k1 * r2 + k2 * r2 * r2;
        const uDist = 0.5 + (xn * radial) / (2.0 * tanH);
        const vDist = 0.5 + (yn * radial) / (2.0 * tanV);
        uvAttr.setXY(i, THREE.MathUtils.clamp(uDist, 0.0, 1.0), THREE.MathUtils.clamp(vDist, 0.0, 1.0));
      } else {
        uvAttr.setXY(i, u0, v0);
      }
    }

    posAttr.needsUpdate = true;
    uvAttr.needsUpdate = true;
    this.geometry.computeBoundingSphere();
  }

  dispose() {
    this.geometry.dispose();
    this.material.dispose();
  }
}

