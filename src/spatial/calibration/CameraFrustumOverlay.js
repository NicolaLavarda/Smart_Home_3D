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
    this.opticalModel = String(options.opticalModel || 'pinhole_radtan');
    this.depth = options.depth || 2.0;
    this.opacity = options.opacity ?? 0.5;
    this.isPOVMode = false;
    this.requestedVisible = false;
    this.distortion = Array.isArray(options.distortion)
      ? options.distortion.map((v) => Number(v) || 0)
      : [0, 0, 0, 0, 0];
    this.groundClipPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

    this.geometry = new THREE.PlaneGeometry(1, 1, 32, 32);
    this.basePositions = new Float32Array(this.geometry.attributes.position.array);
    this.baseUVs = new Float32Array(this.geometry.attributes.uv.array);

    this.material = new THREE.MeshBasicMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: this.opacity,
      side: THREE.DoubleSide,
      depthTest: false,
      depthWrite: false,
      clippingPlanes: [this.groundClipPlane],
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
    this.syncMaterialVisibility();
  }

  syncMaterialVisibility() {
    this.material.visible = Boolean(
      this.requestedVisible &&
      this.videoTexture &&
      (this.isPOVMode || this.opacity > 0.001)
    );
  }

  setVisible(visible) {
    this.requestedVisible = Boolean(visible);
    this.syncMaterialVisibility();
  }

  setOpacity(alpha) {
    this.opacity = THREE.MathUtils.clamp(Number(alpha), 0, 1);
    this.material.opacity = this.opacity;
    this.syncMaterialVisibility();
  }

  setPOVMode(isPOV) {
    this.isPOVMode = Boolean(isPOV);
    this.depth = this.isPOVMode ? 2.0 : 15.95;
    this.material.depthTest = !this.isPOVMode;
    this.material.clippingPlanes = this.isPOVMode ? null : [this.groundClipPlane];
    this.material.needsUpdate = true;
    this.syncMaterialVisibility();
    this.updateGeometry();
  }

  isPanoramic() {
    const opt = this.opticalModel.toLowerCase();
    return opt.includes('equirectangular') || opt.includes('panoramic') || this.fovH >= 150;
  }

  updateOptics({ fovV, fovH, aspect, opticalModel, distortion }) {
    if (fovV !== undefined) this.fovV = Number(fovV);
    if (fovH !== undefined) this.fovH = Number(fovH);
    if (aspect !== undefined) this.aspect = Number(aspect);
    if (opticalModel !== undefined) this.opticalModel = String(opticalModel);
    if (Array.isArray(distortion)) {
      this.distortion = distortion.map((v) => Number(v) || 0);
    }
    this.updateGeometry();
  }

  updateGeometry() {
    const posAttr = this.geometry.attributes.position;
    const uvAttr = this.geometry.attributes.uv;

    if (this.isPanoramic()) {
      // Cupola sferica equirettangolare 180° (Reolink Duo 3 PoE): mappa ogni pixel (u, v) sul raggio reale (theta, phi)
      const clampedFovH = THREE.MathUtils.clamp(Number(this.fovH) || 180.0, 150.0, 355.0);
      const clampedFovV = THREE.MathUtils.clamp(Number(this.fovV) || 55.0, 10.0, 170.0);
      const halfH = THREE.MathUtils.degToRad(clampedFovH * 0.5);
      const halfV = THREE.MathUtils.degToRad(clampedFovV * 0.5);

      for (let i = 0; i < posAttr.count; i++) {
        const u0 = this.baseUVs[i * 2];
        const v0 = this.baseUVs[i * 2 + 1];
        const theta = (u0 - 0.5) * 2.0 * halfH;
        const phi = (v0 - 0.5) * 2.0 * halfV;
        const cosPhi = Math.cos(phi);
        const px = this.depth * cosPhi * Math.sin(theta);
        const py = this.depth * Math.sin(phi);
        const pz = -this.depth * cosPhi * Math.cos(theta);
        posAttr.setXYZ(i, px, py, pz);
        uvAttr.setXY(i, u0, v0);
      }

      posAttr.needsUpdate = true;
      uvAttr.needsUpdate = true;
      this.geometry.computeBoundingSphere();
      return;
    }

    const tanV = Math.tan(THREE.MathUtils.degToRad(this.fovV * 0.5));
    const tanH = this.fovH ? Math.tan(THREE.MathUtils.degToRad(this.fovH * 0.5)) : tanV * this.aspect;
    const h = 2.0 * tanV * this.depth;
    const w = 2.0 * tanH * this.depth;

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

