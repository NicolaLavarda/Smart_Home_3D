import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

export class AssetLoader {
  constructor() {
    this.gltfLoader = new GLTFLoader();

    const dracoLoader = new DRACOLoader();
    dracoLoader.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.7/');
    this.gltfLoader.setDRACOLoader(dracoLoader);

    this.manifest = null;
    this.manifestVersion = 'v1-default';
    this.model = null;
    this.haEntitiesMap = new Map();
    this.groundColliders = [];
    this.cameras = new Map();
    this.sharedMaterials = new Map();

    this.pbrTextures = this.initProceduralPbrTextures();
  }

  createSurfaceMaterial(params) {
    return new THREE.MeshStandardMaterial(params);
  }

  getSharedMaterial(key, factory) {
    if (!this.sharedMaterials.has(key)) {
      const mat = factory();
      mat.needsUpdate = true;
      this.sharedMaterials.set(key, mat);
    }
    return this.sharedMaterials.get(key);
  }

  computeManifestVersion(manifestObj) {
    if (!manifestObj || typeof manifestObj !== 'object') {
      return 'v1-fallback';
    }
    const raw = JSON.stringify(manifestObj);
    let hash = 0x811c9dc5;
    for (let i = 0; i < raw.length; i++) {
      hash ^= raw.charCodeAt(i);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    const hashHex = hash.toString(16).padStart(8, '0');
    const explicit = manifestObj.version || manifestObj.exported_at || manifestObj.generated_at || '';
    if (explicit) {
      const clean = String(explicit).trim().replace(/[^a-zA-Z0-9._-]/g, '_');
      return `${clean}-${hashHex}`;
    }
    return `m-${hashHex}`;
  }

  initProceduralPbrTextures() {
    return {
      parquet: this.createParquetTexture(),
      grass: this.createGrassTexture(),
      stone: this.createStonePaverTexture(),
      gravel: this.createGravelTexture(),
    };
  }

  createParquetTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = '#ba8550';
    ctx.fillRect(0, 0, 512, 512);

    const plankH = 32;
    const plankW = 128;
    const colors = ['#ad7a46', '#c48f58', '#b5814c', '#a16d38', '#cc9760'];

    for (let y = 0; y < 512; y += plankH) {
      const offsetX = ((y / plankH) % 2) * (plankW / 2);
      for (let x = -plankW; x < 512 + plankW; x += plankW) {
        ctx.fillStyle = colors[Math.floor(Math.random() * colors.length)];
        ctx.fillRect(x + offsetX, y, plankW - 2, plankH - 2);

        // Venature sottili
        ctx.fillStyle = 'rgba(0, 0, 0, 0.08)';
        for (let l = 0; l < 4; l++) {
          const vy = y + Math.random() * plankH;
          ctx.fillRect(x + offsetX, vy, plankW - 2, 1);
        }
      }
    }

    ctx.strokeStyle = '#5c3917';
    ctx.lineWidth = 1.2;
    for (let y = 0; y < 512; y += plankH) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(512, y); ctx.stroke();
    }

    const tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(1.5, 1.5);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  createGrassTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');

    // Verde prato vivo e luminoso identico a Blender Viewport
    ctx.fillStyle = '#6cb74a';
    ctx.fillRect(0, 0, 512, 512);

    const tones = ['#5ea83c', '#6db74b', '#78be55', '#529933', '#85c960', '#64ae42'];
    for (let i = 0; i < 18000; i++) {
      const x = Math.random() * 512;
      const y = Math.random() * 512;
      ctx.fillStyle = tones[Math.floor(Math.random() * tones.length)];
      ctx.fillRect(x, y, 2 + Math.random() * 2, 3 + Math.random() * 3);
    }

    const tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(1.8, 1.8);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  createStonePaverTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = '#b0b5b9';
    ctx.fillRect(0, 0, 512, 512);

    const tileW = 64;
    const tileH = 48;
    const stones = ['#aab0b4', '#b6bbc0', '#a2a7ab', '#c0c5ca', '#9ba0a5'];

    for (let y = 0; y < 512; y += tileH) {
      const offsetX = ((y / tileH) % 2) * (tileW / 2);
      for (let x = -tileW; x < 512 + tileW; x += tileW) {
        ctx.fillStyle = stones[Math.floor(Math.random() * stones.length)];
        ctx.fillRect(x + offsetX, y, tileW - 3, tileH - 3);
      }
    }

    ctx.strokeStyle = '#5a5e62';
    ctx.lineWidth = 1.5;
    for (let y = 0; y < 512; y += tileH) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(512, y); ctx.stroke();
    }

    const tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(1.5, 1.5);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  createGravelTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = '#9aa0a6';
    ctx.fillRect(0, 0, 512, 512);

    const pebbles = ['#92989e', '#9fa5ab', '#8a9096', '#a7adb3', '#82888e'];
    for (let i = 0; i < 15000; i++) {
      const x = Math.random() * 512;
      const y = Math.random() * 512;
      const r = 1 + Math.random() * 2.5;
      ctx.fillStyle = pebbles[Math.floor(Math.random() * pebbles.length)];
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    }

    const tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(2.0, 2.0);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  async loadManifest(manifestUrl = '/models/scene_manifest.json') {
    try {
      const response = await fetch(manifestUrl, { cache: 'no-cache' });
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      this.manifest = await response.json();
      this.manifestVersion = this.computeManifestVersion(this.manifest);
      return this.manifest;
    } catch (err) {
      console.warn('[AssetLoader] Fallback manifest:', err);
      this.manifest = { ha_entities: {}, cameras: {}, ground_colliders: [] };
      this.manifestVersion = 'v1-fallback';
      return this.manifest;
    }
  }

  async loadHouseModel(modelUrl = '/models/house_optimized.glb') {
    await this.loadManifest();
    const versionTag = encodeURIComponent(this.manifestVersion || 'v1-fallback');

    const tryLoad = (url) => {
      const sep = url.includes('?') ? '&' : '?';
      const finalUrl = `${url}${sep}v=${versionTag}`;
      return new Promise((resolve, reject) => {
        this.gltfLoader.load(
          finalUrl,
          (gltf) => {
            try {
              this.model = gltf.scene;
              this.processScene(gltf);
              resolve({
                model: this.model,
                manifest: this.manifest,
                haEntitiesMap: this.haEntitiesMap,
                groundColliders: this.groundColliders,
                cameras: this.cameras,
              });
            } catch (procErr) {
              console.error('[AssetLoader] Errore in processScene:', procErr);
              reject(procErr);
            }
          },
          null,
          (error) => {
            console.error(`[AssetLoader] Errore caricamento modello da ${url}:`, error);
            reject(error);
          }
        );
      });
    };

    try {
      return await tryLoad(modelUrl);
    } catch (err) {
      if (modelUrl !== '/models/house_raw.glb') {
        console.warn('[AssetLoader] Tentativo fallback automatico su /models/house_raw.glb...');
        return await tryLoad('/models/house_raw.glb');
      }
      throw err;
    }
  }

  /**
   * Genera coordinate UV planari (X, Z) per geometrie prive di UV map (pavimenti, prati, strade).
   */
  ensurePlanarUVs(geometry, nodeName = '') {
    // Non applicare proiezione orizzontale su pareti verticali o schermi TV (lo schermo gestisce UV verticali proprie)
    if (nodeName.includes('TV_Salotto') || nodeName.includes('Screen')) return;

    if (geometry && !geometry.attributes.uv && geometry.attributes.position) {
      const pos = geometry.attributes.position;
      const count = pos.count;
      const uvs = new Float32Array(count * 2);
      for (let i = 0; i < count; i++) {
        // Proiezione planare orizzontale in metri
        uvs[i * 2] = pos.getX(i);
        uvs[i * 2 + 1] = pos.getZ(i);
      }
      geometry.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
    }
  }

  processScene(gltf) {
    const groundNamesFromManifest = new Set(
      (this.manifest.ground_colliders || []).map((gc) => gc.object_name)
    );

    if (gltf.cameras && gltf.cameras.length > 0) {
      for (const cam of gltf.cameras) {
        this.cameras.set(cam.name, cam);
      }
    }

    this.model.traverse((node) => {
      // Rimuovi eventuali luci esportate dal GLB per evitare sovraesposizione fisica (lux)
      if (node.isLight) {
        if (node.parent) node.parent.remove(node);
        return;
      }

      if (node.isCamera) {
        this.cameras.set(node.name, node);
      }

      if (node.isMesh) {
        node.castShadow = true;
        node.receiveShadow = true;

        // Genera UV se mancanti (esclusi schermi verticali)
        this.ensurePlanarUVs(node.geometry, node.name);

        // Assegna materiale PBR condiviso dalla cache (evita centinaia di istanze duplicate)
        if (node.material) {
          const matName = node.material.name || '';
          const objName = node.name || '';

          // 1. Prato e Giardino esterno -> VERDE VIVO IDENTICO A BLENDER
          if (matName.includes('Prato') || objName.includes('Prato') || objName.includes('Giardino')) {
            node.material = this.getSharedMaterial('Mat_Prato_Render', () => this.createSurfaceMaterial({
              name: 'Mat_Prato_Render',
              color: 0x6db64f,
              map: this.pbrTextures.grass,
              roughness: 0.80,
              metalness: 0.0,
            }));
          }
          // 2. Parquet Rovere interni -> LEGNO CALDO ROVERE BLENDER
          else if (matName.includes('Parquet') || objName.startsWith('Floor_Dining') || objName === 'Floor_Salotto') {
            node.material = this.getSharedMaterial('Mat_Parquet_Render', () => this.createSurfaceMaterial({
              name: 'Mat_Parquet_Render',
              color: 0xba8550,
              map: this.pbrTextures.parquet,
              roughness: 0.38,
              metalness: 0.04,
            }));
          }
          // 3. Lastricato Pietra (Portico, Terrazza, Camminamento) -> PIETRA CHIARA
          else if (matName.includes('Lastricato') || objName.includes('Portico_Pavement') || objName.includes('Walkway') || objName.includes('Terrazza')) {
            node.material = this.getSharedMaterial('Mat_Lastricato_Render', () => this.createSurfaceMaterial({
              name: 'Mat_Lastricato_Render',
              color: 0xb4b8bc,
              map: this.pbrTextures.stone,
              roughness: 0.65,
              metalness: 0.04,
            }));
          }
          // 4. Ghiaia Vialetto Carrabile -> GHIAIA CHIARA
          else if (matName.includes('Ghiaia') || objName.includes('Gravel')) {
            node.material = this.getSharedMaterial('Mat_Ghiaia_Render', () => this.createSurfaceMaterial({
              name: 'Mat_Ghiaia_Render',
              color: 0x9fa3a7,
              map: this.pbrTextures.gravel,
              roughness: 0.85,
              metalness: 0.04,
            }));
          }
          // 5. Pavimento Cemento Garage -> CEMENTO LISCIO CHIARO
          else if (matName.includes('Cemento') || objName.startsWith('Floor_Garage')) {
            node.material = this.getSharedMaterial('Mat_Cemento_Render', () => this.createSurfaceMaterial({
              name: 'Mat_Cemento_Render',
              color: 0x8a8f94,
              roughness: 0.75,
              metalness: 0.08,
            }));
          }
          // 6. Terreno di fondazione perimetrale
          else if (objName === 'Site_Foundation_Earth') {
            node.material = this.getSharedMaterial('Mat_Earth_Render', () => this.createSurfaceMaterial({
              name: 'Mat_Earth_Render',
              color: 0x484038,
              roughness: 0.95,
              metalness: 0.0,
            }));
            node.castShadow = false;
          }
          // 7. Muri Esterni -> INTONACO ARDESIA MODERNO (Identico a Blender!)
          else if (
            matName.includes('Esterno_Dark') ||
            objName.startsWith('Wall_North_') ||
            objName.startsWith('Wall_West_') ||
            objName.startsWith('Wall_East_') ||
            objName.startsWith('Wall_Garage_') ||
            objName.startsWith('Beam_Portico_') ||
            objName.startsWith('Muro_Cinta_')
          ) {
            node.material = this.getSharedMaterial('Mat_Muri_Esterni', () => this.createSurfaceMaterial({
              name: 'Mat_Muri_Esterni',
              color: 0x6e7b88, // Grigio ardesia elegante come su Blender
              roughness: 0.85,
              metalness: 0.02,
            }));
          }
          // 8. Muri Interni -> INTONACO CHIARO ACCOGLIENTE
          else if (
            matName.includes('Interno_Light') ||
            objName.startsWith('Wall_Div_') ||
            objName.startsWith('Wall_Bath_') ||
            objName.startsWith('Wall_Pocket_') ||
            objName.startsWith('Wall_Stair_')
          ) {
            node.material = this.getSharedMaterial('Mat_Muri_Interni', () => this.createSurfaceMaterial({
              name: 'Mat_Muri_Interni',
              color: 0xeeeae2,
              roughness: 0.90,
              metalness: 0.0,
            }));
          }
          // 9. Infissi e Finestre -> ANTRACITE SCURO
          else if (matName.includes('Infissi') || objName.includes('_Frame_') || objName.includes('_Mullion')) {
            node.material = this.getSharedMaterial('Mat_Infissi_Render', () => this.createSurfaceMaterial({
              name: 'Mat_Infissi_Render',
              color: 0x25272a,
              roughness: 0.45,
              metalness: 0.5,
            }));
          }
          // 9b. Cordoli perimetrali e recinzione -> CORDOLO CHIARO
          else if (matName.includes('Cordolo') || objName.includes('_Curb')) {
            node.material = this.getSharedMaterial('Mat_Cordolo_Render', () => this.createSurfaceMaterial({
              name: 'Mat_Cordolo_Render',
              color: 0xd8dade,
              roughness: 0.70,
              metalness: 0.02,
            }));
          }
          // 10. Vetri -> TRASPARENTI E RIFLETTENTI (escludi Vetro_Nero / display / schermi / macchine da caffe)
          else if (
            ((matName.includes('Vetro') || objName.includes('_Glass')) &&
             !matName.includes('Vetro_Nero') &&
             !objName.includes('Screen') &&
             !objName.includes('Display') &&
             !objName.includes('Caffe'))
          ) {
            node.material = this.getSharedMaterial('Mat_Vetro_Render', () => this.createSurfaceMaterial({
              name: 'Mat_Vetro_Render',
              color: 0x99ccff,
              transparent: true,
              opacity: 0.35,
              roughness: 0.05,
              metalness: 0.2,
            }));
            node.castShadow = false;
          }
          // 10b. Schermi TV, Display digitali e Macchina del Caffè -> OPACHI NERI/ANTRACITE
          else if (
            matName.includes('Vetro_Nero') ||
            matName.includes('Macchina_Caffe') ||
            objName.includes('Macchina_Caffe') ||
            matName.includes('Display')
          ) {
            const isCoffee = matName.includes('Macchina_Caffe') || objName.includes('Caffe');
            const matKey = isCoffee ? 'Mat_Macchina_Caffe_Opaque' : 'Mat_Vetro_Nero_Display_Opaque';
            node.material = this.getSharedMaterial(matKey, () => this.createSurfaceMaterial({
              name: 'Mat_Vetro_Nero_Display_Opaque',
              color: isCoffee ? 0x222428 : 0x050508,
              roughness: 0.25,
              metalness: 0.35,
              transparent: false,
              opacity: 1.0,
            }));
          }
          // 11. Recinzione e Cancelli metallici -> METALLO SCURO
          else if (matName.includes('Ringhiera') || objName.startsWith('Gate_')) {
            node.material = this.getSharedMaterial('Mat_Metallo_Cancello', () => this.createSurfaceMaterial({
              name: 'Mat_Metallo_Cancello',
              color: 0x151618,
              roughness: 0.40,
              metalness: 0.8,
            }));
          }
          // 11b. Vasca interna lavastoviglie -> INOX SATINATO
          else if (objName.includes('Lavastoviglie') && objName.includes('Scocca')) {
            node.material = this.getSharedMaterial('Mat_Lavastoviglie_Vasca_Inox', () => this.createSurfaceMaterial({
              name: 'Mat_Lavastoviglie_Vasca_Inox',
              color: 0x475569, // Inox satinato scuro per la vasca interna
              roughness: 0.25,
              metalness: 0.85,
            }));
          }
          // 12. Porte e Arredi in Legno -> NOCE / ROVERE CALDO
          else if (matName.includes('Legno') || matName.includes('Porta') || objName.startsWith('Door_') || objName.includes('Tavolo') || objName.includes('Sedia')) {
            node.material = this.getSharedMaterial('Mat_Legno_Arredi', () => this.createSurfaceMaterial({
              name: 'Mat_Legno_Arredi',
              color: 0x543219,
              roughness: 0.35,
              metalness: 0.05,
            }));
          }
          // 13. Mobili laccati bianchi, mensole Kallax e termosifoni / termoarredi (opachi e non-riflettenti, mai abbaglianti)
          else if (
            matName.includes('Laccato') ||
            objName.startsWith('Kallax_') ||
            objName.includes('Termoarredo_') ||
            objName.includes('Radiator')
          ) {
            node.material = this.getSharedMaterial('Mat_Laccato_Bianco_Soft', () => this.createSurfaceMaterial({
              name: 'Mat_Laccato_Bianco_Soft',
              color: 0xc4c2bc, // Bianco caldo satinato opaco soft (non abbagliante)
              roughness: 0.70,
              metalness: 0.0,
              emissive: new THREE.Color(0x000000),
              emissiveIntensity: 0.0,
            }));
          }
          // 13b. Diffusori lampada sospensione Isola Bancone (separati da Kallax e termosifone)
          else if (matName.includes('Lampada_Isola') || objName.includes('Isola_Lampada_Cono')) {
            node.material = this.getSharedMaterial('Mat_Diffusore_Isola', () => this.createSurfaceMaterial({
              name: 'Mat_Diffusore_Isola',
              color: 0xf2eee6,
              roughness: 0.35,
              metalness: 0.0,
              emissive: new THREE.Color(0x000000),
              emissiveIntensity: 0.0,
            }));
          }
          // 14. Testi e Etichette Blueprint 3D sul pavimento -> TONALITÀ GRIGIO ARDESIA SOTTILE (non bianchi abbaglianti!)
          else if (objName.startsWith('Label_')) {
            node.material = this.getSharedMaterial('Mat_Label_Blueprint', () => new THREE.MeshBasicMaterial({
              name: 'Mat_Label_Blueprint',
              color: 0x475569, // Slate 600 discreto
            }));
            node.castShadow = false;
            node.receiveShadow = false;
          }
          // 15. Altri materiali (preserva PBR completo sia su PC che su mobile)
          else {
            node.material.roughness = Math.max(node.material.roughness ?? 0.5, 0.3);
          }
        }

        // Registrazione Ground Colliders
        const isGroundCollider =
          node.userData.collider_role === 'ground' ||
          groundNamesFromManifest.has(node.name) ||
          node.name.startsWith('Floor_') ||
          node.name.startsWith('Giardino_') ||
          node.name === 'Driveway_Gravel' ||
          node.name === 'Portico_Pavement_Unified' ||
          node.name === 'Terrazza_All_Aperto' ||
          node.name === 'Walkway_Pedestrian_Pavement';

        if (isGroundCollider) {
          node.userData.collider_role = 'ground';
          node.castShadow = false;
          this.groundColliders.push(node);
        }
      }

      // Registrazione Entità Home Assistant
      let haEntity = node.userData.ha_entity;
      if (node.name === 'TV_Salotto_Screen' || node.name === 'TV_Salotto_Bezel') {
        haEntity = 'media_player.smart_tv_lg_oled_2';
        node.userData.ha_entity = 'media_player.smart_tv_lg_oled_2';
      }

      if (haEntity) {
        if (!this.haEntitiesMap.has(haEntity)) {
          this.haEntitiesMap.set(haEntity, []);
        }
        this.haEntitiesMap.get(haEntity).push(node);

        // Alias retrocompatibile per TV
        if (haEntity === 'media_player.smart_tv_lg_oled_2') {
          if (!this.haEntitiesMap.has('media_player.lg_webos_smart_tv')) {
            this.haEntitiesMap.set('media_player.lg_webos_smart_tv', []);
          }
          this.haEntitiesMap.get('media_player.lg_webos_smart_tv').push(node);
        }
      }

      const haAltEntity = node.userData.ha_alt_entity;
      if (haAltEntity) {
        if (!this.haEntitiesMap.has(haAltEntity)) {
          this.haEntitiesMap.set(haAltEntity, []);
        }
        this.haEntitiesMap.get(haAltEntity).push(node);
      }
    });

    this.batchStaticMeshes();

    console.log(
      `[AssetLoader] Modello elaborato con successo: ${this.haEntitiesMap.size} entità HA, ${this.groundColliders.length} collider calpestabili.`
    );
  }

  /**
   * Unisce (batching) le mesh architettoniche/decorative puramente statiche che condividono
   * lo stesso materiale, riducendo drasticamente i WebGL draw call (da ~1350 a ~100).
   * Preserva integralmente tutte le entità HA, i ground collider e le parti animate/interattive.
   */
  batchStaticMeshes() {
    if (!this.model) return;
    try {
      this.model.updateMatrixWorld(true);
      const invModelMatrix = this.model.matrixWorld.clone().invert();

      const dynamicNameRe =
        /^(Gate_|Switch_Gate|Garage_Door_Panel_|Lavastoviglie|TV_Salotto|Sprinkler_|Ecovacs_Deebot_|Security_Cam_|Bollard_Garden_|Wall_Garden_Light_|Puffer|Caldaia|Accumulo)|Screen/i;

      const protectedMeshes = new Set(this.groundColliders);
      this.haEntitiesMap.forEach((meshes) => {
        meshes.forEach((m) => protectedMeshes.add(m));
      });

      const hasProtectedAncestor = (node) => {
        let cur = node;
        while (cur && cur !== this.model) {
          if (cur.userData?.ha_entity || cur.userData?.ha_alt_entity) return true;
          if (cur.name && dynamicNameRe.test(cur.name)) return true;
          cur = cur.parent;
        }
        return false;
      };

      const buckets = new Map();
      const protectedGeometries = new Set();
      let totalMeshesBefore = 0;

      this.model.traverse((node) => {
        if (!node.isMesh) return;
        totalMeshesBefore++;

        const isProtected =
          protectedMeshes.has(node) ||
          hasProtectedAncestor(node) ||
          node.isSkinnedMesh ||
          Boolean(node.morphTargetInfluences) ||
          !node.geometry ||
          !node.geometry.attributes?.position ||
          !node.material ||
          Array.isArray(node.material) ||
          node.matrixWorld.determinant() < 0;

        if (isProtected) {
          if (node.geometry) protectedGeometries.add(node.geometry);
          return;
        }

        const key = `${node.material.uuid}|${node.castShadow ? 1 : 0}|${node.receiveShadow ? 1 : 0}`;
        let bucket = buckets.get(key);
        if (!bucket) {
          bucket = {
            material: node.material,
            castShadow: node.castShadow,
            receiveShadow: node.receiveShadow,
            meshes: [],
          };
          buckets.set(key, bucket);
        }
        bucket.meshes.push(node);
      });

      const relMatrix = new THREE.Matrix4();
      const meshesToRemove = [];
      const newBatchMeshes = [];
      let mergedSourceCount = 0;

      buckets.forEach((bucket) => {
        if (bucket.meshes.length < 2) return;

        const needsUv =
          Boolean(bucket.material.map) ||
          bucket.meshes.every((m) => Boolean(m.geometry?.attributes?.uv));

        const prepared = [];
        let ok = true;

        for (const mesh of bucket.meshes) {
          const raw = mesh.geometry.index ? mesh.geometry.toNonIndexed() : mesh.geometry.clone();
          if (!raw.attributes.normal) {
            raw.computeVertexNormals();
          }

          const posAttr = raw.attributes.position;
          const normAttr = raw.attributes.normal;
          if (!posAttr || !normAttr) {
            raw.dispose();
            ok = false;
            break;
          }

          const clean = new THREE.BufferGeometry();
          clean.setAttribute('position', posAttr.clone());
          clean.setAttribute('normal', normAttr.clone());
          if (needsUv) {
            if (raw.attributes.uv) {
              clean.setAttribute('uv', raw.attributes.uv.clone());
            } else {
              clean.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(posAttr.count * 2), 2));
            }
          }
          raw.dispose();

          relMatrix.multiplyMatrices(invModelMatrix, mesh.matrixWorld);
          clean.applyMatrix4(relMatrix);
          prepared.push(clean);
        }

        if (!ok || prepared.length < 2) {
          prepared.forEach((g) => g.dispose());
          return;
        }

        const merged = mergeGeometries(prepared, false);
        prepared.forEach((g) => g.dispose());

        if (!merged) return;

        merged.computeBoundingBox();
        merged.computeBoundingSphere();

        const batchMesh = new THREE.Mesh(merged, bucket.material);
        batchMesh.name = `StaticBatch_${bucket.material.name || bucket.material.uuid.slice(0, 8)}`;
        batchMesh.castShadow = bucket.castShadow;
        batchMesh.receiveShadow = bucket.receiveShadow;
        batchMesh.matrixAutoUpdate = false;
        batchMesh.updateMatrix();

        newBatchMeshes.push(batchMesh);
        for (const mesh of bucket.meshes) {
          meshesToRemove.push(mesh);
        }
        mergedSourceCount += bucket.meshes.length;
      });

      if (newBatchMeshes.length === 0) return;

      for (const mesh of meshesToRemove) {
        if (mesh.parent) mesh.parent.remove(mesh);
        if (mesh.geometry && !protectedGeometries.has(mesh.geometry)) {
          mesh.geometry.dispose();
        }
      }

      for (const batchMesh of newBatchMeshes) {
        this.model.add(batchMesh);
      }

      // Rimuovi eventuali nodi contenitori rimasti vuoti per velocizzare traverse() e CSS2DRenderer
      const pruneEmpty = (parent) => {
        for (let i = parent.children.length - 1; i >= 0; i--) {
          const child = parent.children[i];
          if (child.children.length > 0) {
            pruneEmpty(child);
          }
          if (
            !child.isMesh &&
            !child.isLight &&
            !child.isCamera &&
            child.children.length === 0 &&
            !child.userData?.ha_entity &&
            !child.userData?.ha_alt_entity &&
            !(child.name && dynamicNameRe.test(child.name))
          ) {
            parent.remove(child);
          }
        }
      };
      pruneEmpty(this.model);

      const totalMeshesAfter = totalMeshesBefore - mergedSourceCount + newBatchMeshes.length;
      console.log(
        `[AssetLoader] Static batching: ${mergedSourceCount} mesh statiche fuse in ${newBatchMeshes.length} batch (mesh totali: ${totalMeshesBefore} -> ${totalMeshesAfter}).`
      );
    } catch (err) {
      console.warn('[AssetLoader] Static batching saltato (fallback sicuro):', err);
    }
  }
}
