import * as THREE from 'three';

/**
 * SpatialZoneRenderer3D
 *
 * Renders and interactively edits 2.5D spatial zones (closed polygons),
 * oriented perimeter tripwires (polylines with normal arrows A -> B),
 * and directional kinematic cones (azimuth ± tolerance) directly inside the Three.js scene.
 */
export class SpatialZoneRenderer3D {
  constructor({ sceneManager, cameraProjector }) {
    this.sceneManager = sceneManager;
    this.cameraProjector = cameraProjector;
    this.scene = sceneManager?.scene;

    this.rootGroup = new THREE.Group();
    this.rootGroup.name = 'AutomationZonesGroup';
    this.zonesGroup = new THREE.Group();
    this.zonesGroup.name = 'SavedZonesGroup';
    this.draftGroup = new THREE.Group();
    this.draftGroup.name = 'DraftZoneGroup';
    this.directionConeGroup = new THREE.Group();
    this.directionConeGroup.name = 'DirectionConePreviewGroup';

    this.rootGroup.add(this.zonesGroup);
    this.rootGroup.add(this.draftGroup);
    this.rootGroup.add(this.directionConeGroup);
    if (this.scene) {
      this.scene.add(this.rootGroup);
    }

    this.zones = [];
    this.zoneMeshesById = new Map();
    this.zonesVisible = false;
    this.highlightedZoneId = null;
    this._alertTimers = new Map();

    this.rootGroup.visible = false;
    this.zonesGroup.visible = false;

    // Interactive 3D drawing state
    this.isDrawing = false;
    this.drawMode = 'polygon'; // 'polygon' | 'perimeter' | 'direction_origin'
    this.draftVertices = [];
    this.draftColor = '#38bdf8';
    this.draftNormalFlipped = false;
    this.cursorWorldPt = null;
    this.onDraftChanged = null;
    this.onDirectionPicked = null;

    this.raycaster = new THREE.Raycaster();
    this.groundPlaneFallback = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    this._pointerDownScreen = null;

    this._onPointerDown = this.handlePointerDown.bind(this);
    this._onPointerMove = this.handlePointerMove.bind(this);
    this._onPointerUp = this.handlePointerUp.bind(this);
  }

  setZonesVisible(visible) {
    this.zonesVisible = Boolean(visible);
    this.rootGroup.visible = this.zonesVisible;
    this.zonesGroup.visible = this.zonesVisible;
    this.sceneManager?.requestShadowUpdate?.();
  }

  toggleZonesVisible() {
    this.setZonesVisible(!this.zonesVisible);
    return this.zonesVisible;
  }

  setZones(zonesList = []) {
    this.zones = Array.isArray(zonesList) ? zonesList : [];
    this.rebuildAllZones();
  }

  setHighlightedZone(zoneId = null) {
    this.highlightedZoneId = zoneId || null;
    this.rebuildAllZones();
  }

  flashZoneAlert(zoneId, severity = 'critical', durationMs = 6000) {
    if (!zoneId) return;
    if (!this.zonesVisible) return;
    if (this._alertTimers.has(zoneId)) {
      clearTimeout(this._alertTimers.get(zoneId));
    }
    this.highlightedZoneId = zoneId;
    this.rebuildAllZones(severity === 'critical' ? '#f43f5e' : '#f59e0b');

    const timer = setTimeout(() => {
      this._alertTimers.delete(zoneId);
      if (this.highlightedZoneId === zoneId) {
        this.highlightedZoneId = null;
      }
      this.rebuildAllZones();
    }, durationMs);
    this._alertTimers.set(zoneId, timer);
  }

  rebuildAllZones(overrideAlertColor = null) {
    this._clearGroup(this.zonesGroup);
    this.zoneMeshesById.clear();

    for (const zone of this.zones) {
      if (!zone || !Array.isArray(zone.vertices) || zone.vertices.length < 2) continue;
      const isHighlighted = this.highlightedZoneId === zone.zone_id;
      const colorHex = isHighlighted && overrideAlertColor ? overrideAlertColor : (zone.color || '#38bdf8');
      const meshGroup = this._buildZoneVisualGroup(zone, {
        colorHex,
        isHighlighted,
        isDraft: false,
      });
      this.zonesGroup.add(meshGroup);
      this.zoneMeshesById.set(zone.zone_id, meshGroup);
    }
  }

  // =========================================================================
  // INTERACTIVE 3D DRAWING (Polygons, Perimeters & Direction Arrows)
  // =========================================================================

  startDrawing({
    geometryType = 'polygon',
    color = '#38bdf8',
    normalFlipped = false,
    initialVertices = [],
    onVerticesChanged = null,
  } = {}) {
    this.stopDrawing();
    this.isDrawing = true;
    this.drawMode = geometryType === 'perimeter' ? 'perimeter' : 'polygon';
    this.draftColor = color || '#38bdf8';
    this.draftNormalFlipped = Boolean(normalFlipped);
    this.draftVertices = Array.isArray(initialVertices)
      ? initialVertices.map((v) => ({ x: Number(v.x), z: Number(v.z) }))
      : [];
    this.onDraftChanged = typeof onVerticesChanged === 'function' ? onVerticesChanged : null;
    this.zonesGroup.visible = true;

    const domEl = this.sceneManager?.renderer?.domElement;
    if (domEl) {
      domEl.addEventListener('pointerdown', this._onPointerDown);
      domEl.addEventListener('pointermove', this._onPointerMove);
      domEl.addEventListener('pointerup', this._onPointerUp);
      domEl.style.cursor = 'crosshair';
    }
    this.rebuildDraftVisual();
  }

  startDirectionPicking({ originXZ = null, onDirectionPicked = null } = {}) {
    this.stopDrawing();
    this.isDrawing = true;
    this.drawMode = 'direction_origin';
    this.draftVertices = originXZ ? [{ x: Number(originXZ.x), z: Number(originXZ.z) }] : [];
    this.onDirectionPicked = typeof onDirectionPicked === 'function' ? onDirectionPicked : null;

    const domEl = this.sceneManager?.renderer?.domElement;
    if (domEl) {
      domEl.addEventListener('pointerdown', this._onPointerDown);
      domEl.addEventListener('pointermove', this._onPointerMove);
      domEl.addEventListener('pointerup', this._onPointerUp);
      domEl.style.cursor = 'crosshair';
    }
  }

  stopDrawing() {
    this.isDrawing = false;
    this.cursorWorldPt = null;
    const domEl = this.sceneManager?.renderer?.domElement;
    if (domEl) {
      domEl.removeEventListener('pointerdown', this._onPointerDown);
      domEl.removeEventListener('pointermove', this._onPointerMove);
      domEl.removeEventListener('pointerup', this._onPointerUp);
      domEl.style.cursor = '';
    }
    this._clearGroup(this.draftGroup);
  }

  undoLastDraftVertex() {
    if (this.draftVertices.length > 0) {
      this.draftVertices.pop();
      this.rebuildDraftVisual();
      this.onDraftChanged?.([...this.draftVertices]);
    }
  }

  clearDraftVertices() {
    this.draftVertices = [];
    this.rebuildDraftVisual();
    this.onDraftChanged?.([]);
  }

  handlePointerDown(e) {
    if (!this.isDrawing || e.button !== 0) return;
    this._pointerDownScreen = { x: e.clientX, y: e.clientY };
  }

  handlePointerMove(e) {
    if (!this.isDrawing) return;
    const pt = this.raycastGroundPoint(e.clientX, e.clientY);
    if (!pt) return;
    this.cursorWorldPt = pt;

    if (this.drawMode === 'direction_origin' && this.draftVertices.length === 1) {
      const origin = this.draftVertices[0];
      const dx = pt.x - origin.x;
      const dz = pt.z - origin.z;
      if (Math.hypot(dx, dz) > 0.25) {
        const az = ((Math.atan2(dz, dx) * 180) / Math.PI + 360) % 360;
        this.showDirectionCone({
          azimuthDeg: az,
          toleranceDeg: 30,
          originXZ: origin,
        });
      }
      return;
    }

    this.rebuildDraftVisual();
  }

  handlePointerUp(e) {
    if (!this.isDrawing || e.button !== 0 || !this._pointerDownScreen) return;
    const moveDist = Math.hypot(
      e.clientX - this._pointerDownScreen.x,
      e.clientY - this._pointerDownScreen.y
    );
    this._pointerDownScreen = null;
    // Ignore camera orbit drags (> 6 px)
    if (moveDist > 6) return;

    const pt = this.raycastGroundPoint(e.clientX, e.clientY);
    if (!pt) return;

    if (this.drawMode === 'direction_origin') {
      if (this.draftVertices.length === 0) {
        this.draftVertices.push({ x: Number(pt.x.toFixed(2)), z: Number(pt.z.toFixed(2)) });
      } else {
        const origin = this.draftVertices[0];
        const dx = pt.x - origin.x;
        const dz = pt.z - origin.z;
        const az = Math.round(((Math.atan2(dz, dx) * 180) / Math.PI + 360) % 360);
        this.showDirectionCone({ azimuthDeg: az, toleranceDeg: 30, originXZ: origin });
        const cb = this.onDirectionPicked;
        this.stopDrawing();
        cb?.({ azimuthDeg: az, originXZ: origin });
      }
      return;
    }

    this.draftVertices.push({
      x: Number(pt.x.toFixed(2)),
      z: Number(pt.z.toFixed(2)),
    });
    this.rebuildDraftVisual();
    this.onDraftChanged?.([...this.draftVertices]);
  }

  raycastGroundPoint(clientX, clientY) {
    const domEl = this.sceneManager?.renderer?.domElement;
    const camera = this.sceneManager?.camera;
    if (!domEl || !camera) return null;

    const rect = domEl.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;

    const ndc = new THREE.Vector2(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -((clientY - rect.top) / rect.height) * 2 + 1
    );
    this.raycaster.setFromCamera(ndc, camera);

    const colliders = this.cameraProjector?.groundColliders || [];
    if (colliders.length > 0) {
      const hits = this.raycaster.intersectObjects(colliders, true);
      if (hits.length > 0) {
        return hits[0].point;
      }
    }

    const target = new THREE.Vector3();
    const hitPlane = this.raycaster.ray.intersectPlane(this.groundPlaneFallback, target);
    return hitPlane ? target : null;
  }

  rebuildDraftVisual() {
    this._clearGroup(this.draftGroup);
    if (this.draftVertices.length === 0) return;

    const previewVertices = [...this.draftVertices];
    if (this.cursorWorldPt) {
      previewVertices.push({ x: this.cursorWorldPt.x, z: this.cursorWorldPt.z });
    }

    // Draw vertex handles
    const handleGeom = new THREE.SphereGeometry(0.14, 14, 14);
    const handleMat = new THREE.MeshBasicMaterial({ color: this.draftColor });
    for (const v of this.draftVertices) {
      const m = new THREE.Mesh(handleGeom, handleMat);
      m.position.set(v.x, 0.08, v.z);
      this.draftGroup.add(m);
    }

    if (previewVertices.length >= 2) {
      const draftZone = {
        zone_id: '__draft__',
        name: 'Bozza',
        geometry_type:
          this.drawMode === 'polygon' && previewVertices.length >= 3 ? 'polygon' : 'perimeter',
        vertices: previewVertices,
        normal_flipped: this.draftNormalFlipped,
        color: this.draftColor,
      };
      const grp = this._buildZoneVisualGroup(draftZone, {
        colorHex: this.draftColor,
        isHighlighted: true,
        isDraft: true,
      });
      this.draftGroup.add(grp);
    }
  }

  // =========================================================================
  // 3D DIRECTIONAL CONE VISUALIZER (For Mean Direction & Speed Triggers)
  // =========================================================================

  showDirectionCone({ azimuthDeg = 0, toleranceDeg = 35, originXZ = null, zoneId = null } = {}) {
    this._clearGroup(this.directionConeGroup);
    if (!Number.isFinite(Number(azimuthDeg))) return;

    let cx = 0;
    let cz = 0;
    if (originXZ && Number.isFinite(originXZ.x) && Number.isFinite(originXZ.z)) {
      cx = Number(originXZ.x);
      cz = Number(originXZ.z);
    } else if (zoneId) {
      const z = this.zones.find((item) => item.zone_id === zoneId);
      if (z && Array.isArray(z.vertices) && z.vertices.length > 0) {
        cx = z.vertices.reduce((s, v) => s + Number(v.x), 0) / z.vertices.length;
        cz = z.vertices.reduce((s, v) => s + Number(v.z), 0) / z.vertices.length;
      }
    }

    const azRad = (Number(azimuthDeg) * Math.PI) / 180;
    const tolRad = (Math.max(5, Math.min(175, Number(toleranceDeg) || 35)) * Math.PI) / 180;
    const radius = 3.2;
    const yBase = 0.09;

    // Build angular fan mesh on XZ plane
    const segments = 24;
    const positions = [cx, yBase, cz];
    for (let i = 0; i <= segments; i++) {
      const a = azRad - tolRad + (2 * tolRad * i) / segments;
      positions.push(cx + Math.cos(a) * radius, yBase, cz + Math.sin(a) * radius);
    }
    const indices = [];
    for (let i = 1; i <= segments; i++) {
      indices.push(0, i, i + 1);
    }

    const fanGeom = new THREE.BufferGeometry();
    fanGeom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    fanGeom.setIndex(indices);

    const fanMat = new THREE.MeshBasicMaterial({
      color: '#f59e0b',
      transparent: true,
      opacity: 0.28,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    this.directionConeGroup.add(new THREE.Mesh(fanGeom, fanMat));

    // Central direction arrow
    const dirVec = new THREE.Vector3(Math.cos(azRad), 0, Math.sin(azRad)).normalize();
    const arrow = new THREE.ArrowHelper(
      dirVec,
      new THREE.Vector3(cx, yBase + 0.04, cz),
      radius * 0.95,
      0xf59e0b,
      0.55,
      0.32
    );
    this.directionConeGroup.add(arrow);
  }

  hideDirectionCone() {
    this._clearGroup(this.directionConeGroup);
  }

  // =========================================================================
  // INTERNAL 3D MESH BUILDERS
  // =========================================================================

  _buildZoneVisualGroup(zone, { colorHex = '#38bdf8', isHighlighted = false, isDraft = false } = {}) {
    const group = new THREE.Group();
    const color = new THREE.Color(colorHex);
    const verts = zone.vertices;
    const baseY = 0.05;
    const wallHeight = isHighlighted ? 0.85 : 0.55;

    if (zone.geometry_type === 'polygon' && verts.length >= 3) {
      // 1. Ground translucent fill via ShapeGeometry
      // Shape is in XY, we rotate X by +90 deg so (x, y_shape) maps to (x, +z_world)
      const shape = new THREE.Shape();
      shape.moveTo(Number(verts[0].x), Number(verts[0].z));
      for (let i = 1; i < verts.length; i++) {
        shape.lineTo(Number(verts[i].x), Number(verts[i].z));
      }
      shape.closePath();

      const fillGeom = new THREE.ShapeGeometry(shape);
      fillGeom.rotateX(Math.PI / 2);
      const fillMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: isHighlighted ? 0.34 : 0.18,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const fillMesh = new THREE.Mesh(fillGeom, fillMat);
      fillMesh.position.y = baseY;
      group.add(fillMesh);

      // 2. Vertical translucent perimeter walls
      const wallVerts = [];
      for (let i = 0; i < verts.length; i++) {
        const a = verts[i];
        const b = verts[(i + 1) % verts.length];
        wallVerts.push(
          a.x, baseY, a.z,
          b.x, baseY, b.z,
          b.x, baseY + wallHeight, b.z,
          a.x, baseY, a.z,
          b.x, baseY + wallHeight, b.z,
          a.x, baseY + wallHeight, a.z
        );
      }
      const wallGeom = new THREE.BufferGeometry();
      wallGeom.setAttribute('position', new THREE.Float32BufferAttribute(wallVerts, 3));
      const wallMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: isHighlighted ? 0.24 : 0.11,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      group.add(new THREE.Mesh(wallGeom, wallMat));

      // 3. Closed outline loop (bottom & top)
      const loopPtsBottom = verts.map((v) => new THREE.Vector3(v.x, baseY + 0.01, v.z));
      const loopPtsTop = verts.map((v) => new THREE.Vector3(v.x, baseY + wallHeight, v.z));
      const lineMat = new THREE.LineBasicMaterial({
        color,
        transparent: true,
        opacity: isHighlighted ? 1.0 : 0.8,
      });
      group.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(loopPtsBottom), lineMat));
      group.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(loopPtsTop), lineMat));
    } else if (verts.length >= 2) {
      // PERIMETER / TRIPWIRE BARRIER + ORIENTED NORMAL ARROWS (A -> B)
      const barrierHeight = isHighlighted ? 1.15 : 0.9;
      const wallVerts = [];
      for (let i = 0; i < verts.length - 1; i++) {
        const a = verts[i];
        const b = verts[i + 1];
        wallVerts.push(
          a.x, baseY, a.z,
          b.x, baseY, b.z,
          b.x, baseY + barrierHeight, b.z,
          a.x, baseY, a.z,
          b.x, baseY + barrierHeight, b.z,
          a.x, baseY + barrierHeight, a.z
        );

        // Compute segment normal (matching backend SpatialGeometryEngine.compute_segment_normal_xz)
        const dx = b.x - a.x;
        const dz = b.z - a.z;
        const segLen = Math.hypot(dx, dz);
        if (segLen > 0.15) {
          let nx = -dz / segLen;
          let nz = dx / segLen;
          if (zone.normal_flipped) {
            nx = -nx;
            nz = -nz;
          }
          const midX = 0.5 * (a.x + b.x);
          const midZ = 0.5 * (a.z + b.z);
          const arrowDir = new THREE.Vector3(nx, 0, nz).normalize();
          const arrow = new THREE.ArrowHelper(
            arrowDir,
            new THREE.Vector3(midX, baseY + 0.12, midZ),
            Math.min(1.1, Math.max(0.45, segLen * 0.35)),
            color.getHex(),
            0.28,
            0.18
          );
          group.add(arrow);
        }
      }

      const wallGeom = new THREE.BufferGeometry();
      wallGeom.setAttribute('position', new THREE.Float32BufferAttribute(wallVerts, 3));
      const wallMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: isHighlighted ? 0.38 : 0.22,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      group.add(new THREE.Mesh(wallGeom, wallMat));

      const linePtsBottom = verts.map((v) => new THREE.Vector3(v.x, baseY + 0.01, v.z));
      const linePtsTop = verts.map((v) => new THREE.Vector3(v.x, baseY + barrierHeight, v.z));
      const lineMat = new THREE.LineBasicMaterial({ color });
      group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(linePtsBottom), lineMat));
      group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(linePtsTop), lineMat));
    }

    if (!isDraft) {
      const postGeom = new THREE.CylinderGeometry(0.04, 0.04, wallHeight, 8);
      const postMat = new THREE.MeshBasicMaterial({ color });
      for (const v of verts) {
        const post = new THREE.Mesh(postGeom, postMat);
        post.position.set(v.x, baseY + wallHeight * 0.5, v.z);
        group.add(post);
      }
    }

    return group;
  }

  _clearGroup(group) {
    if (!group) return;
    while (group.children.length > 0) {
      const child = group.children.pop();
      this._disposeObject3D(child);
    }
  }

  _disposeObject3D(obj) {
    if (!obj) return;
    if (obj.children && obj.children.length > 0) {
      for (const c of [...obj.children]) {
        this._disposeObject3D(c);
      }
    }
    obj.geometry?.dispose?.();
    if (Array.isArray(obj.material)) {
      obj.material.forEach((m) => m?.dispose?.());
    } else {
      obj.material?.dispose?.();
    }
  }
}
