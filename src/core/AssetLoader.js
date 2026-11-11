import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

export class AssetLoader {
  constructor() {
    this.gltfLoader = new GLTFLoader();

    const dracoLoader = new DRACOLoader();
    dracoLoader.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.7/');
    this.gltfLoader.setDRACOLoader(dracoLoader);

    this.manifest = null;
    this.model = null;
    this.haEntitiesMap = new Map();
    this.groundColliders = [];
    this.cameras = new Map();

    this.pbrTextures = this.initProceduralPbrTextures();
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
    for (let i = 0; i < 45000; i++) {
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
    for (let i = 0; i < 40000; i++) {
      const x = Math.random() * 512;
      const y = Math.random() * 512;
      const r = 1 + Math.random() * 3;
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
      const url = `${manifestUrl}?t=${Date.now()}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      this.manifest = await response.json();
      return this.manifest;
    } catch (err) {
      console.warn('[AssetLoader] Fallback manifest:', err);
      this.manifest = { ha_entities: {}, cameras: {}, ground_colliders: [] };
      return this.manifest;
    }
  }

  async loadHouseModel(modelUrl = '/models/house_optimized.glb') {
    if (!this.manifest) {
      await this.loadManifest();
    }

    const tryLoad = (url) => {
      // Cache busting per evitare che il browser ricarichi il vecchio file
      const finalUrl = `${url}?t=${Date.now()}`;
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

        // Clona e assegna materiale PBR distintivo
        if (node.material) {
          const matName = node.material.name || '';
          const objName = node.name || '';

          // 1. Prato e Giardino esterno -> VERDE VIVO IDENTICO A BLENDER
          if (matName.includes('Prato') || objName.includes('Prato') || objName.includes('Giardino')) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Prato_Render',
              color: 0x6db64f,
              map: this.pbrTextures.grass,
              roughness: 0.80,
              metalness: 0.0,
            });
            node.material.needsUpdate = true;
          }
          // 2. Parquet Rovere interni -> LEGNO CALDO ROVERE BLENDER
          else if (matName.includes('Parquet') || objName.startsWith('Floor_Dining') || objName === 'Floor_Salotto') {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Parquet_Render',
              color: 0xba8550,
              map: this.pbrTextures.parquet,
              roughness: 0.38,
              metalness: 0.04,
            });
            node.material.needsUpdate = true;
          }
          // 3. Lastricato Pietra (Portico, Terrazza, Camminamento) -> PIETRA CHIARA
          else if (matName.includes('Lastricato') || objName.includes('Portico_Pavement') || objName.includes('Walkway') || objName.includes('Terrazza')) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Lastricato_Render',
              color: 0xb4b8bc,
              map: this.pbrTextures.stone,
              roughness: 0.65,
              metalness: 0.04,
            });
            node.material.needsUpdate = true;
          }
          // 4. Ghiaia Vialetto Carrabile -> GHIAIA CHIARA
          else if (matName.includes('Ghiaia') || objName.includes('Gravel')) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Ghiaia_Render',
              color: 0x9fa3a7,
              map: this.pbrTextures.gravel,
              roughness: 0.85,
              metalness: 0.04,
            });
            node.material.needsUpdate = true;
          }
          // 5. Pavimento Cemento Garage -> CEMENTO LISCIO CHIARO
          else if (matName.includes('Cemento') || objName.startsWith('Floor_Garage')) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Cemento_Render',
              color: 0x8a8f94,
              roughness: 0.75,
              metalness: 0.08,
            });
            node.material.needsUpdate = true;
          }
          // 6. Terreno di fondazione perimetrale
          else if (objName === 'Site_Foundation_Earth') {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Earth_Render',
              color: 0x484038,
              roughness: 0.95,
              metalness: 0.0,
            });
            node.material.needsUpdate = true;
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
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Muri_Esterni',
              color: 0x6e7b88, // Grigio ardesia elegante come su Blender
              roughness: 0.85,
              metalness: 0.02,
            });
            node.material.needsUpdate = true;
          }
          // 8. Muri Interni -> INTONACO CHIARO ACCOGLIENTE
          else if (
            matName.includes('Interno_Light') ||
            objName.startsWith('Wall_Div_') ||
            objName.startsWith('Wall_Bath_') ||
            objName.startsWith('Wall_Pocket_') ||
            objName.startsWith('Wall_Stair_')
          ) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Muri_Interni',
              color: 0xeeeae2,
              roughness: 0.90,
              metalness: 0.0,
            });
            node.material.needsUpdate = true;
          }
          // 9. Infissi e Finestre -> ANTRACITE SCURO
          else if (matName.includes('Infissi') || objName.includes('_Frame_') || objName.includes('_Mullion')) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Infissi_Render',
              color: 0x25272a,
              roughness: 0.45,
              metalness: 0.5,
            });
            node.material.needsUpdate = true;
          }
          // 9b. Cordoli perimetrali e recinzione -> CORDOLO CHIARO
          else if (matName.includes('Cordolo') || objName.includes('_Curb')) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Cordolo_Render',
              color: 0xd8dade,
              roughness: 0.70,
              metalness: 0.02,
            });
            node.material.needsUpdate = true;
          }
          // 10. Vetri -> TRASPARENTI E RIFLETTENTI (escludi Vetro_Nero / display / schermi / macchine da caffe)
          else if (
            ((matName.includes('Vetro') || objName.includes('_Glass')) &&
             !matName.includes('Vetro_Nero') &&
             !objName.includes('Screen') &&
             !objName.includes('Display') &&
             !objName.includes('Caffe'))
          ) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Vetro_Render',
              color: 0x99ccff,
              transparent: true,
              opacity: 0.35,
              roughness: 0.05,
              metalness: 0.2,
            });
          }
          // 10b. Schermi TV, Display digitali e Macchina del Caffè -> OPACHI NERI/ANTRACITE
          else if (
            matName.includes('Vetro_Nero') ||
            matName.includes('Macchina_Caffe') ||
            objName.includes('Macchina_Caffe') ||
            matName.includes('Display')
          ) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Vetro_Nero_Display_Opaque',
              color: (matName.includes('Macchina_Caffe') || objName.includes('Caffe')) ? 0x222428 : 0x050508,
              roughness: 0.25,
              metalness: 0.35,
              transparent: false,
              opacity: 1.0,
            });
          }
          // 11. Recinzione e Cancelli metallici -> METALLO SCURO
          else if (matName.includes('Ringhiera') || objName.startsWith('Gate_')) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Metallo_Cancello',
              color: 0x151618,
              roughness: 0.40,
              metalness: 0.8,
            });
          }
          // 11b. Vasca interna lavastoviglie -> INOX SATINATO
          else if (objName.includes('Lavastoviglie') && objName.includes('Scocca')) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Lavastoviglie_Vasca_Inox',
              color: 0x475569, // Inox satinato scuro per la vasca interna
              roughness: 0.25,
              metalness: 0.85,
            });
            node.material.needsUpdate = true;
          }
          // 12. Porte e Arredi in Legno -> NOCE / ROVERE CALDO
          else if (matName.includes('Legno') || matName.includes('Porta') || objName.startsWith('Door_') || objName.includes('Tavolo') || objName.includes('Sedia')) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Legno_Arredi',
              color: 0x543219,
              roughness: 0.35,
              metalness: 0.05,
            });
          }
          // 13. Mobili laccati bianchi, mensole Kallax e termosifoni / termoarredi (opachi e non-riflettenti, mai abbaglianti)
          else if (
            matName.includes('Laccato') ||
            objName.startsWith('Kallax_') ||
            objName.includes('Termoarredo_') ||
            objName.includes('Radiator')
          ) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Laccato_Bianco_Soft',
              color: 0xc4c2bc, // Bianco caldo satinato opaco soft (non abbagliante)
              roughness: 0.70,
              metalness: 0.0,
              emissive: new THREE.Color(0x000000),
              emissiveIntensity: 0.0,
            });
            node.material.needsUpdate = true;
          }
          // 13b. Diffusori lampada sospensione Isola Bancone (separati da Kallax e termosifone)
          else if (matName.includes('Lampada_Isola') || objName.includes('Isola_Lampada_Cono')) {
            node.material = new THREE.MeshStandardMaterial({
              name: 'Mat_Diffusore_Isola',
              color: 0xf2eee6,
              roughness: 0.35,
              metalness: 0.0,
              emissive: new THREE.Color(0x000000),
              emissiveIntensity: 0.0,
            });
            node.material.needsUpdate = true;
          }
          // 14. Testi e Etichette Blueprint 3D sul pavimento -> TONALITÀ GRIGIO ARDESIA SOTTILE (non bianchi abbaglianti!)
          else if (objName.startsWith('Label_')) {
            node.material = new THREE.MeshBasicMaterial({
              color: 0x475569, // Slate 600 discreto
            });
          }
          // 15. Altri materiali
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

    console.log(
      `[AssetLoader] Modello elaborato con successo: ${this.haEntitiesMap.size} entità HA, ${this.groundColliders.length} collider calpestabili.`
    );
  }
}
