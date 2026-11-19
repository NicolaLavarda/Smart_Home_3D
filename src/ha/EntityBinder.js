import * as THREE from 'three';
import { deviceRegistry } from '../devices/DeviceRegistry.js';

export class EntityBinder {
  constructor(scene, haClient, options = {}) {
    this.scene = scene;
    this.haClient = haClient;
    this.isMobileProfile = Boolean(options.isMobileProfile);
    this.onSceneMoved = typeof options.onSceneMoved === 'function' ? options.onSceneMoved : null;
    this.haEntitiesMap = new Map();
    this.lights3D = new Map();      // entity_id -> Array<PointLight>
    this.animatedObjects = new Map(); // mesh -> { origPos, origRot, targetPos, targetRot, type }
    this.interactionManager = null;
    this.cameraController = null;
  }

  setInteractionManager(im) {
    this.interactionManager = im;
  }

  setCameraController(cc) {
    this.cameraController = cc;
  }

  bindEntities(haEntitiesMap) {
    this.haEntitiesMap = haEntitiesMap;

    // Crea luci Three.js dinamiche in corrispondenza dei corpi illuminanti
    this.setupDynamicLights();

    // Registra posizioni iniziali dei cancelli per l'animazione di scorrimento
    this.setupGateTransforms();

    // Collega i controller decentralizzati dei dispositivi smart (TV, Lavastoviglie, Irrigazione, Deebot)
    deviceRegistry.bind3D(haEntitiesMap, this.scene, {
      haClient: this.haClient,
      entityBinder: this,
      interactionManager: this.interactionManager,
      cameraController: this.cameraController,
      haEntitiesMap: this.haEntitiesMap,
    });

    // Sottoscrivi aggiornamenti in tempo reale da Home Assistant / Mock
    this.haClient.subscribeEntities((entities) => {
      this.handleEntitiesUpdate(entities);
    });
  }

  setupDynamicLights() {
    this.haEntitiesMap.forEach((meshes, entityId) => {
      if (!entityId.startsWith('light.')) return;

      // Clona individualmente i materiali delle mesh delle luci per isolarli completamente
      // da mobili, pareti o termoarredi che potrebbero condividere lo stesso shader originario
      meshes.forEach((mesh) => {
        if (mesh.material) {
          mesh.material = mesh.material.clone();
        }
      });

      const lightList = [];

      // 1. Luci esterne: 4 Lampioncini giardino (raggio ~7 metri) + 4 Luci a muro su muro Est (a 60cm da terra)
      if (entityId === 'light.luci_esterne') {
        const bollards = meshes.filter(
          (m) =>
            m.name.startsWith('Bollard_Garden_') &&
            !m.name.includes('_Base') &&
            !m.name.includes('_Pillar') &&
            !m.name.includes('_Cap')
        );
        const wallLights = meshes.filter(
          (m) => m.name.startsWith('Wall_Garden_Light_') && !m.name.includes('_Body')
        );

        if (this.isMobileProfile) {
          // Su mobile consolida in 2 PointLight (zona lampioncini + muro Est) per ridurre il costo fragment shader PBR
          if (bollards.length > 0) {
            const center = new THREE.Vector3();
            bollards.forEach((b) => {
              const p = new THREE.Vector3();
              b.getWorldPosition(p);
              center.add(p);
            });
            center.divideScalar(bollards.length);
            const pl = new THREE.PointLight(0xfff5dd, 0.0, 22.0, 1.05);
            pl.position.set(center.x, center.y + 1.1, center.z);
            pl.userData.baseIntensity = 18.0;
            this.scene.add(pl);
            lightList.push(pl);
          }
          if (wallLights.length > 0) {
            const center = new THREE.Vector3();
            wallLights.forEach((wl) => {
              const p = new THREE.Vector3();
              wl.getWorldPosition(p);
              center.add(p);
            });
            center.divideScalar(wallLights.length);
            const pl = new THREE.PointLight(0xfff3db, 0.0, 18.0, 1.05);
            pl.position.set(center.x - 0.5, center.y + 0.4, center.z);
            pl.userData.baseIntensity = 14.0;
            this.scene.add(pl);
            lightList.push(pl);
          }
        } else {
          bollards.forEach((b) => {
            const p = new THREE.Vector3();
            b.getWorldPosition(p);
            // Raggio 7 metri: distanza 16m con decadimento morbido 1.15 e intensità ben visibile sul prato
            const pl = new THREE.PointLight(0xfff5dd, 0.0, 16.0, 1.15);
            pl.position.set(p.x, p.y + 0.45, p.z);
            pl.userData.baseIntensity = 12.0;
            this.scene.add(pl);
            lightList.push(pl);
          });

          wallLights.forEach((wl) => {
            const p = new THREE.Vector3();
            wl.getWorldPosition(p);
            // Luci a muro a 60cm da terra lungo il muro Est: orientate verso ovest (-X)
            const pl = new THREE.PointLight(0xfff3db, 0.0, 13.0, 1.15);
            pl.position.set(p.x - 0.35, p.y + 0.1, p.z);
            pl.userData.baseIntensity = 9.0;
            this.scene.add(pl);
            lightList.push(pl);
          });
        }
      }
      // 2. Lampadario zona pranzo cucina (light.forno): potente e diffonde su tutta l'area cucina/pranzo
      else if (entityId === 'light.forno') {
        const center = new THREE.Vector3();
        let count = 0;
        meshes.forEach((m) => {
          if (!m.name.includes('Asta')) {
            const p = new THREE.Vector3();
            m.getWorldPosition(p);
            center.add(p);
            count++;
          }
        });
        if (count > 0) center.divideScalar(count);
        else center.set(11.3, 1.9, 5.4);

        const pl = new THREE.PointLight(0xfff2d4, 0.0, 16.0, 1.15);
        pl.position.set(center.x, center.y - 0.2, center.z);
        pl.userData.baseIntensity = 9.0;
        this.scene.add(pl);
        lightList.push(pl);
      }
      // 3. Salotto - Faretti a soffitto (light.smart_plug_in_unit_switch_3)
      else if (entityId === 'light.smart_plug_in_unit_switch_3') {
        const spots = this.isMobileProfile
          ? [new THREE.Vector3(3.2, 2.65, 3.5)]
          : [
              new THREE.Vector3(1.8, 2.65, 3.5),
              new THREE.Vector3(3.2, 2.65, 3.5),
              new THREE.Vector3(4.6, 2.65, 3.5),
            ];
        spots.forEach((pos) => {
          const pl = new THREE.PointLight(0xfffaea, 0.0, this.isMobileProfile ? 14.0 : 11.0, 1.15);
          pl.position.copy(pos);
          pl.userData.baseIntensity = this.isMobileProfile ? 10.5 : 7.0;
          this.scene.add(pl);
          lightList.push(pl);
        });
      }
      // 4. Salotto - Applique Est (light.1)
      else if (entityId === 'light.1') {
        meshes.forEach((m) => {
          const p = new THREE.Vector3();
          m.getWorldPosition(p);
          const pl = new THREE.PointLight(0xffedd0, 0.0, 10.0, 1.2);
          pl.position.set(p.x - 0.35, p.y, p.z); // Scostata dal muro est verso l'interno della stanza (-X)
          pl.userData.baseIntensity = 6.0;
          this.scene.add(pl);
          lightList.push(pl);
        });
      }
      // 5. Salotto - Applique Nord (light.2)
      else if (entityId === 'light.2') {
        meshes.forEach((m) => {
          const p = new THREE.Vector3();
          m.getWorldPosition(p);
          const pl = new THREE.PointLight(0xffedd0, 0.0, 10.0, 1.2);
          pl.position.set(p.x, p.y, p.z + 0.35); // Scostata dal muro nord verso l'interno della stanza (+Z)
          pl.userData.baseIntensity = 6.0;
          this.scene.add(pl);
          lightList.push(pl);
        });
      }
      // 6. Bancone cucina (light.bancone)
      else if (entityId === 'light.bancone') {
        if (this.isMobileProfile && meshes.length > 0) {
          const center = new THREE.Vector3();
          meshes.forEach((m) => {
            const p = new THREE.Vector3();
            m.getWorldPosition(p);
            center.add(p);
          });
          center.divideScalar(meshes.length);
          const pl = new THREE.PointLight(0xfff3db, 0.0, 11.0, 1.2);
          pl.position.set(center.x, center.y - 0.15, center.z);
          pl.userData.baseIntensity = 8.5;
          this.scene.add(pl);
          lightList.push(pl);
        } else {
          meshes.forEach((m) => {
            const p = new THREE.Vector3();
            m.getWorldPosition(p);
            const pl = new THREE.PointLight(0xfff3db, 0.0, 9.5, 1.25);
            pl.position.set(p.x, p.y - 0.15, p.z);
            pl.userData.baseIntensity = 6.5;
            this.scene.add(pl);
            lightList.push(pl);
          });
        }
      }
      // 7. Portico (light.portico)
      else if (entityId === 'light.portico') {
        const sources = meshes.filter((m) => !m.name.includes('_Lens') && !m.name.includes('_Plate'));
        if (this.isMobileProfile && sources.length > 0) {
          const center = new THREE.Vector3();
          sources.forEach((m) => {
            const p = new THREE.Vector3();
            m.getWorldPosition(p);
            center.add(p);
          });
          center.divideScalar(sources.length);
          const pl = new THREE.PointLight(0xfff0db, 0.0, 12.0, 1.2);
          pl.position.copy(center);
          pl.userData.baseIntensity = 8.5;
          this.scene.add(pl);
          lightList.push(pl);
        } else {
          sources.forEach((m) => {
            const p = new THREE.Vector3();
            m.getWorldPosition(p);
            const pl = new THREE.PointLight(0xfff0db, 0.0, 10.0, 1.25);
            pl.position.copy(p);
            pl.userData.baseIntensity = 6.0;
            this.scene.add(pl);
            lightList.push(pl);
          });
        }
      }
      // 8. Altre luci generiche
      else {
        const center = new THREE.Vector3();
        let count = 0;
        meshes.forEach((m) => {
          if (!m.name.includes('Asta') && !m.name.includes('Base') && !m.name.includes('Body')) {
            const p = new THREE.Vector3();
            m.getWorldPosition(p);
            center.add(p);
            count++;
          }
        });
        if (count > 0) center.divideScalar(count);
        else meshes[0]?.getWorldPosition(center);

        const pl = new THREE.PointLight(0xfff1e0, 0.0, 9.5, 1.3);
        pl.position.copy(center);
        pl.userData.baseIntensity = 5.0;
        this.scene.add(pl);
        lightList.push(pl);
      }

      this.lights3D.set(entityId, lightList);
    });
  }

  setupGateTransforms() {
    // 1. Cancello carraio a doppia anta a battente (switch.switch_casa_interruttore_1)
    const carraioMeshes = this.haEntitiesMap.get('switch.switch_casa_interruttore_1') || [];
    const leafR = carraioMeshes.find((m) => m.name === 'Gate_Leaf_R');
    const switchMesh = carraioMeshes.find((m) => m.name === 'Switch_Gate_Carraio');

    carraioMeshes.forEach((mesh) => {
      if (!mesh.name.startsWith('Gate_Leaf_')) return;

      // Normalizza il pivot esattamente sulla cerniera laterale se i vertici sono stati cotti nel mondo
      if (mesh.geometry && Math.abs(mesh.position.x) < 1.0 && Math.abs(mesh.position.z) < 1.0) {
        mesh.geometry.computeBoundingBox();
        const bbox = mesh.geometry.boundingBox;
        if (bbox) {
          const isLeft = mesh.name.includes('_L');
          const hingeX = isLeft ? bbox.min.x : bbox.max.x;
          const hingeZ = (bbox.min.z + bbox.max.z) * 0.5;
          mesh.geometry.translate(-hingeX, 0, -hingeZ);
          mesh.position.set(hingeX, mesh.position.y, hingeZ);
        }
      }

      this.animatedObjects.set(mesh, {
        origPos: mesh.position.clone(),
        targetPos: mesh.position.clone(),
        origRotY: mesh.rotation.y,
        targetRotY: mesh.rotation.y,
        type: 'carraio_swing_gate',
      });
    });

    // Rende l'eventuale selettore sul cancello solidale all'anta destra durante la rotazione
    if (leafR && switchMesh && switchMesh.parent !== leafR) {
      leafR.updateMatrixWorld(true);
      switchMesh.updateMatrixWorld(true);
      leafR.attach(switchMesh);
    }

    // 2. Serranda garage (switch.switch_casa_interruttore_3)
    const garagePanels = [];
    this.scene.traverse((node) => {
      if (node.isMesh && node.name.startsWith('Garage_Door_Panel_')) {
        garagePanels.push(node);
      }
    });
    garagePanels.forEach((mesh) => {
      this.animatedObjects.set(mesh, {
        origPos: mesh.position.clone(),
        targetPos: mesh.position.clone(),
        type: 'garage_shutter',
      });
    });
  }

  handleEntitiesUpdate(entities) {
    // 1. Aggiorna moduli dispositivi decentralizzati (Smart TV, ecc.)
    deviceRegistry.update3D(entities);

    // 2. Aggiorna illuminazione, cancelli e badge
    Object.entries(entities).forEach(([entityId, stateObj]) => {
      const meshes = this.haEntitiesMap.get(entityId) || [];
      const domain = entityId.split('.')[0];
      const isOn = stateObj.state === 'on' || stateObj.state === 'open' || stateObj.state === 'playing';

      // Aggiorna badge CSS2D
      if (this.interactionManager) {
        if (domain === 'sensor') {
          this.interactionManager.updateSensorState(entityId, stateObj.state, stateObj.attributes);
        } else {
          this.interactionManager.updateBadgeState(entityId, isOn, stateObj.state);
        }
      }

      if (domain === 'light') {
        this.updateLightState(entityId, meshes, stateObj);
      } else if (domain === 'cover' || domain === 'switch') {
        this.updateSwitchCoverState(entityId, meshes, stateObj);
      }
    });
  }

  updateLightState(entityId, meshes, stateObj) {
    const isOn = stateObj.state === 'on';
    const attrs = stateObj.attributes || {};
    const brightness = (attrs.brightness ?? 255) / 255;
    const rgb = attrs.rgb_color || [255, 240, 200];

    const color = new THREE.Color(`rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`);

    // Aggiorna PointLights associati
    const pointLights = this.lights3D.get(entityId) || [];
    pointLights.forEach((pl) => {
      pl.color.copy(color);
      const baseIntensity = pl.userData.baseIntensity ?? 1.8;
      pl.intensity = isOn ? baseIntensity * brightness : 0.0;
    });

    // Aggiorna materiale emissivo delle sole mesh diffusori/lampade
    meshes.forEach((mesh) => {
      const name = mesh.name || '';
      // Salta elementi non illuminanti (aste, corpi scuri, basamenti, o mobili)
      if (
        name.includes('_Base') ||
        name.includes('_Pillar') ||
        name.includes('_Cap') ||
        name.includes('_Body') ||
        name.includes('_Pole') ||
        name.includes('Asta') ||
        name.includes('Kallax') ||
        name.includes('Termoarredo') ||
        name.includes('Plate')
      ) {
        return;
      }

      if (mesh.material && 'emissive' in mesh.material) {
        if (isOn) {
          mesh.material.emissive.copy(color);
          mesh.material.emissiveIntensity = 2.6 * brightness;
        } else {
          mesh.material.emissive.setHex(0x000000);
          mesh.material.emissiveIntensity = 0.0;
        }
      }
    });
  }

  updateSwitchCoverState(entityId, meshes, stateObj) {
    const isOpen = stateObj.state === 'open' || stateObj.state === 'on';

    // Cancello Carraio (apertura a battente 90° verso l'interno del giardino +Z)
    if (entityId === 'switch.switch_casa_interruttore_1') {
      meshes.forEach((mesh) => {
        const anim = this.animatedObjects.get(mesh);
        if (!anim || anim.type !== 'carraio_swing_gate') return;
        if (isOpen) {
          const deltaAngle = mesh.name.includes('_L') ? -Math.PI / 2 : Math.PI / 2;
          anim.targetRotY = anim.origRotY + deltaAngle;
        } else {
          anim.targetRotY = anim.origRotY;
        }
      });
    }

    // Serranda Garage
    if (entityId === 'switch.switch_casa_interruttore_3') {
      this.animatedObjects.forEach((anim, mesh) => {
        if (anim.type === 'garage_shutter') {
          if (isOpen) {
            anim.targetPos.set(anim.origPos.x, anim.origPos.y + 2.3, anim.origPos.z);
          } else {
            anim.targetPos.copy(anim.origPos);
          }
        }
      });
    }
  }

  update(delta) {
    // 1. Tick per i moduli dispositivi decentralizzati (animazioni schermo TV, ecc.)
    deviceRegistry.update(delta);

    // 2. Animazione fluida cancelli (rotazione a battente) e serrande (lerp traslazione)
    let moved = false;
    this.animatedObjects.forEach((anim, mesh) => {
      if (anim && anim.targetPos) {
        if (mesh.position.distanceToSquared(anim.targetPos) > 1e-6) {
          mesh.position.lerp(anim.targetPos, 0.08);
          moved = true;
        } else if (!mesh.position.equals(anim.targetPos)) {
          mesh.position.copy(anim.targetPos);
          moved = true;
        }
      }
      if (anim && anim.targetRotY !== undefined) {
        const diff = anim.targetRotY - mesh.rotation.y;
        if (Math.abs(diff) > 0.0005) {
          mesh.rotation.y = THREE.MathUtils.lerp(mesh.rotation.y, anim.targetRotY, 0.08);
          moved = true;
        } else if (mesh.rotation.y !== anim.targetRotY) {
          mesh.rotation.y = anim.targetRotY;
          moved = true;
        }
      }
    });

    if (moved && this.onSceneMoved) {
      this.onSceneMoved();
    }
  }

  toggleEntity(entityId) {
    const customController = deviceRegistry.findControllerForEntity(entityId);
    if (customController && customController.togglePower) {
      customController.togglePower();
      return;
    }

    const domain = entityId.split('.')[0];
    this.haClient.callService(domain, 'toggle', { entity_id: entityId });
  }
}

