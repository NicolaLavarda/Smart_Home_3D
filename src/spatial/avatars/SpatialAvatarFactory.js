import * as THREE from 'three';
import { CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js';
import { icon } from '../../ui/icons.js';

const CLASS_STYLE = {
  person: { color: 0x06b6d4, badgeColor: '#38bdf8', iconName: 'user', defaultName: 'Persona' },
  car: { color: 0xf59e0b, badgeColor: '#fbbf24', iconName: 'car', defaultName: 'Veicolo' },
  truck: { color: 0xf97316, badgeColor: '#fb923c', iconName: 'truck', defaultName: 'Furgone' },
  bicycle: { color: 0x10b981, badgeColor: '#34d399', iconName: 'bike', defaultName: 'Bici' },
  dog: { color: 0xec4899, badgeColor: '#f472b6', iconName: 'dog', defaultName: 'Animale' },
};

/**
 * SpatialAvatarFactory
 *
 * Factory Pattern per generare e aggiornare gli avatar 3D delle entità tracciate
 * (Persone, Veicoli, Bici, Animali) con badge CSS2D di identità (Face/Re-ID) e velocità.
 */
export class SpatialAvatarFactory {
  constructor() {
    this.geometries = {
      ring: new THREE.RingGeometry(0.32, 0.44, 24),
      personBody: new THREE.CapsuleGeometry(0.18, 0.85, 6, 12),
      personHead: new THREE.SphereGeometry(0.15, 14, 10),
      carChassis: new THREE.BoxGeometry(1.75, 0.72, 3.8),
      carCabin: new THREE.BoxGeometry(1.42, 0.56, 2.0),
      smallBody: new THREE.CapsuleGeometry(0.16, 0.45, 4, 10),
      arrowCone: new THREE.ConeGeometry(0.11, 0.28, 8),
    };
  }

  createAvatar(trackData) {
    const classLabel = trackData.class_label || trackData.class || 'person';
    const style = CLASS_STYLE[classLabel] || CLASS_STYLE.person;

    const group = new THREE.Group();
    group.name = `Avatar_${trackData.track_id ?? trackData.id}`;

    // Anello radar a terra
    const ringMat = new THREE.MeshBasicMaterial({
      color: style.color,
      transparent: true,
      opacity: 0.78,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const ring = new THREE.Mesh(this.geometries.ring, ringMat);
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.03;
    group.add(ring);

    const bodyMat = new THREE.MeshStandardMaterial({
      color: style.color,
      emissive: style.color,
      emissiveIntensity: 0.32,
      roughness: 0.35,
      metalness: 0.15,
      transparent: true,
      opacity: 0.88,
    });

    if (classLabel === 'car' || classLabel === 'truck') {
      const chassis = new THREE.Mesh(this.geometries.carChassis, bodyMat);
      chassis.position.y = 0.45;
      chassis.castShadow = true;
      group.add(chassis);

      const cabin = new THREE.Mesh(this.geometries.carCabin, bodyMat);
      cabin.position.set(0, 1.02, -0.1);
      cabin.castShadow = true;
      group.add(cabin);
      ring.scale.set(2.4, 2.4, 1);
    } else if (classLabel === 'person') {
      const torso = new THREE.Mesh(this.geometries.personBody, bodyMat);
      torso.position.y = 0.72;
      torso.castShadow = true;
      group.add(torso);

      const head = new THREE.Mesh(this.geometries.personHead, bodyMat);
      head.position.y = 1.48;
      head.castShadow = true;
      group.add(head);
    } else {
      const body = new THREE.Mesh(this.geometries.smallBody, bodyMat);
      body.position.y = 0.45;
      body.rotation.x = Math.PI / 2;
      body.castShadow = true;
      group.add(body);
    }

    // Freccia direzionale anteriore (+Z locale)
    const dirArrow = new THREE.Mesh(
      this.geometries.arrowCone,
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9 })
    );
    dirArrow.rotation.x = Math.PI / 2;
    dirArrow.position.set(0, 0.14, classLabel === 'car' || classLabel === 'truck' ? 2.15 : 0.58);
    group.add(dirArrow);

    // Badge CSS2D flottante con nome identità (se riconosciuta) e confidenza
    const div = document.createElement('div');
    div.className = 'spatial-avatar-badge';
    div.style.cssText = [
      'display: inline-flex;',
      'align-items: center;',
      'gap: 5px;',
      'padding: 3px 8px;',
      'border-radius: 6px;',
      'background: rgba(15, 23, 42, 0.88);',
      `border: 1px solid ${style.badgeColor};`,
      'color: #f8fafc;',
      'font-family: Inter, system-ui, sans-serif;',
      'font-size: 11px;',
      'font-weight: 600;',
      'white-space: nowrap;',
      'pointer-events: none;',
      'box-shadow: 0 4px 12px rgba(0, 0, 0, 0.45);',
    ].join('');

    const css2dLabel = new CSS2DObject(div);
    css2dLabel.position.set(0, classLabel === 'car' || classLabel === 'truck' ? 1.8 : 1.95, 0);
    group.add(css2dLabel);

    group.userData = {
      classLabel,
      ring,
      ringMat,
      bodyMat,
      dirArrow,
      badgeEl: div,
      css2dLabel,
    };

    this.updateAvatarMetadata(group, trackData);
    return group;
  }

  updateAvatarMetadata(avatarGroup, trackData) {
    const classLabel = trackData.class_label || trackData.class || 'person';
    const style = CLASS_STYLE[classLabel] || CLASS_STYLE.person;
    const { badgeEl, ringMat, bodyMat } = avatarGroup.userData;
    if (!badgeEl) return;

    const idNum = trackData.track_id ?? trackData.id ?? '?';
    const identity = trackData.identity;
    const state = trackData.state || {};
    const vx = state.vx ?? 0;
    const vz = state.vz ?? 0;
    const speedMs = Math.hypot(vx, vz);
    const camSources = Array.isArray(trackData.camera_sources)
      ? trackData.camera_sources.join('+')
      : trackData.camera || 'Cam_Carraio';

    const iconHtml = icon(style.iconName, { size: 12 });
    const title = identity
      ? `${iconHtml} <span>${identity}</span>`
      : `${iconHtml} <span>${style.defaultName} #${idNum}</span>`;

    const confPct = trackData.confidence ? `${Math.round(trackData.confidence * 100)}%` : '';
    const speedStr = speedMs > 0.15 ? ` • ${speedMs.toFixed(1)} m/s` : '';

    badgeEl.innerHTML = `${title} <span style="opacity:0.72;font-weight:400;font-size:10px;">${confPct}${speedStr} · ${camSources}</span>`;

    if (identity && identity !== 'Sconosciuto') {
      ringMat.color.setHex(0x10b981);
      bodyMat.color.setHex(0x10b981);
      bodyMat.emissive.setHex(0x10b981);
      badgeEl.style.borderColor = '#10b981';
    } else {
      ringMat.color.setHex(style.color);
      bodyMat.color.setHex(style.color);
      bodyMat.emissive.setHex(style.color);
      badgeEl.style.borderColor = style.badgeColor;
    }
  }

  dispose() {
    Object.values(this.geometries).forEach((g) => g.dispose());
  }
}

