# Pipeline AI-Agent: Aggiunta Nuova Telecamera in `Smart_Home_3D`

> **Destinatario:** Agente AI operativo nel repository `Smart_Home_3D`.
> **Obiettivo:** Integrare end-to-end una nuova telecamera IP/ONVIF già configurata in Home Assistant (HA), partendo dal **modello commerciale** e dalle **misure fisiche relative alla casa**, preservando al 100% la telecamera esistente (`Cam_Carraio`), la sicurezza, l'architettura **Blender Single Source of Truth (SSoT)**, le prestazioni sull'host di produzione e tutti i test automatici.

---

## 0. Regole d'Oro & Vincoli Non Negociabili

Prima di modificare qualsiasi file, rispetta sempre questi invarianti verificati dal repository e dalla suite e2e:

1. **Blender è l'unica SSoT geometrica e ottica (`PRODUCT.md`):** coordinate, orientamento, `lens_mm`, `sensor_width_mm`, `sensor_height_mm`, `optical_model`, `distortion_coeffs` e associazione entità HA provengono da `Smart_Home_3D.blend` → `public/models/scene_manifest.json` e `house.glb`. Non inventare offset geometrici hardcoded nel frontend o nel backend per "correggere" una posa sbagliata: correggi la posa in Blender.
2. **Retrocompatibilità assoluta su `Cam_Carraio`:** ogni modifica a `setup_ha_properties.py`, `export_glb.py`, `go2rtc.yaml`, frontend (`src/`) o backend (`spatial_server/`) deve lasciare perfettamente funzionante `Cam_Carraio` (`camera.carraio_scorrevole`, `camera.carraio_trasparente`, stream `carraio_main` / `carraio_sub`).
3. **Zero segreti nel repository (`tests/e2e/test_f4_go2rtc_yaml.py`, `tests/e2e/test_f7_repo_hygiene.py`):**
   - Le credenziali RTSP/ONVIF, gli IP privati (se sensibili) e i token vanno **solo** in `.env` (gitignored).
   - In `go2rtc/go2rtc.yaml` usa **solo** placeholder `${NOME_VARIABILE}`, mai password o URL completi in chiaro.
   - In `.env.example` documenta i nuovi nomi variabili lasciando i segreti vuoti e mantenendo i default sicuri (`VITE_HA_TOKEN=` vuoto, `SPATIAL_SERVER_HOST=127.0.0.1`, `SPATIAL_AUTH_REQUIRED=true`).
   - In `npm run build` di produzione non devono essere attive `VITE_HA_TOKEN`, `VITE_GO2RTC_URL`, `VITE_SPATIAL_SERVER_URL` (`test_tier4_scenarios.py`).
4. **Invarianti di rete & `go2rtc.yaml`:** non alterare `api.listen: "127.0.0.1:1984"`, `api.origin: ""`, `rtsp.listen: "127.0.0.1:8554"`, `webrtc.listen: ":8555"`.
5. **Budget hardware reale (`docs/FUTURE_PHASES_PROMPT.md`, `docs/master_prompt_architetturale_per_antigravity_ide.md`):** l'host di produzione è un PC Windows 10 con CPU **Intel i5-6400 (4C/4T)**, **8 GB RAM** totali (condivisi con la VM VirtualBox di Home Assistant su `192.168.86.24`), GPU **Intel HD 530**, senza Docker/WSL2. Evita transcoding software FFmpeg in `go2rtc` e dimensiona l'eventuale ingestion OpenVINO di `spatial_server/` con estrema parsimonia.
6. **UI in italiano & RBAC (`PRODUCT.md`, `tests/e2e/test_f11_rbac_ui.py`, `test_f17_m3_ui_and_recordings.py`):** etichette UI sempre in italiano, niente `entity_id` grezzi (stringhe con `.`) nei sottotitoli dei modali, e non rompere la visibilità RBAC di `#btn-open-cam-calib`, `#btn-camera-calibrate`, `#btn-toggle-simulator`, `#btn-camera-pov`.

---

## Fase 0 — Raccolta Input & Pre-Flight Check

### 0.1 Checklist input minimi che l'utente deve fornire (o che l'agente deve richiedere/scoprire)

Quando l'utente chiede di aggiungere una nuova telecamera, verifica di avere tutti i seguenti dati prima di iniziare l'integrazione di rete/configurazione:

| Dato | Obbligatorio? | Come ottenerlo / Fallback se mancante |
| :--- | :---: | :--- |
| **Modello esatto della telecamera** (marca + sigla, es. `Reolink Duo 3 PoE`, `Reolink RLC-810A`) | Sì | Fornito dall'utente |
| **Posizione fisica e misure rispetto alla casa** (muro/palo di montaggio, distanza da due spigoli noti o coordinate, altezza dal suolo/pavimento, dove guarda / punto target inquadrato) | Sì | Fornito dall'utente |
| **Nome logico / zona di copertura** (es. `Giardino Nord`, `Portico Sud`, `Cam_Portico`) | Consigliato | Se mancante, dedurlo dalla posizione e concordare lo slug (`<slug>`) prima di fissare nomi in Blender/env |
| **`entity_id` Home Assistant** (es. `camera.portico_fluente`) | Sì (per live/HA) | Chiederlo all'utente oppure ispezionare HA REST API usando `.env.local` (`tools/fetch_ha_entities.mjs`) se l'utente autorizza la lettura |
| **IP LAN (preferibilmente DHCP reservation)**, porta RTSP (default `554`) / ONVIF / RTMP, e credenziali dedicate (o sapere che vanno messe in `.env`) | Sì (per `go2rtc`/snapshot) | Chiedere all'utente di inserire le credenziali direttamente in `.env` (o di confermare le variabili). Non loggare mai password |
| **Se deve essere inclusa nella CV / tracking 3D (`spatial_server`)** o solo in streaming + frustum 3D | Consigliato | Default prudente su i5-6400: abilitare sempre frustum 3D + streaming + NVR snapshot/replay; valutare CV OpenVINO multi-stream solo se la CPU lo consente |

### 0.2 Pre-flight check automatico nel workspace

Appena ricevuta la richiesta:
1. Leggi `public/models/scene_manifest.json` per vedere quali `cameras`, `ha_entities` e `ground_colliders` esistono già ed evitare collisioni sui nomi (`Cam_<Nome>`, `stream_id`, `sub_stream_id`, `ha_camera_entity`).
2. Verifica i file chiave dell'architettura attuale:
   - `blender/scripts/setup_ha_properties.py`
   - `blender/scripts/export_glb.py`
   - `go2rtc/go2rtc.yaml`
   - `.env.example`
   - `src/devices/camera/SecurityCameraController.js` e `SecurityCameraModal.js`
   - `spatial_server/main.py` e `spatial_server/config.py`
3. Definisci uno **slug univoco** in stile snake_case ASCII senza spazi né caratteri speciali:
   - Nome oggetto camera in Blender: `Cam_<PascalNome>` (es. `Cam_Portico`, `Cam_Giardino_Nord`)
   - Mesh 3D corpo/supporto in Blender: `Security_Cam_<PascalNome>_Body`, `Security_Cam_<PascalNome>_Pole` (il prefisso `Security_Cam_` è riconosciuto automaticamente da `dynamicNameRe` in `src/core/AssetLoader.js` per escludere la mesh dallo static batching)
   - Stream `go2rtc`: `<slug>_main` e `<slug>_sub`
   - Prefisso env vars: `<MODEL_OR_BRAND>_<SLUG_UPPER>_*` (es. `REOLINK_PORTICO_URL`, `REOLINK_PORTICO_SUB_URL` oppure `REOLINK_PORTICO_USER`, `REOLINK_PORTICO_PASS`, `REOLINK_PORTICO_HOST`)

---

## Fase 1 — Ricerca Online delle Specifiche Tecniche

Usa la ricerca web (`search_web`) per consultare **datasheet ufficiale del produttore** (e documentazione RTSP/ONVIF ufficiale, es. `support.reolink.com`) e raccogli i parametri esatti del modello indicato dall'utente:

### 1.1 Parametri ottici e fisici da estrarre

| Parametro | Perché serve | Dove va usato |
| :--- | :--- | :--- |
| **Tipo di ottica / camera** (singolo sensore fisso/varifocal vs dual-lens stitched panoramic 180°) | Determina se usare `pinhole_radtan` o `equirectangular_180` | `optical_model` in Blender, `CameraCatalog.js`, `spatial_server/optics/` |
| **FOV Orizzontale (`HFOV`)** e **FOV Verticale (`VFOV`)** (e eventuale diagonale `DFOV`) in gradi | Impostano frustum 3D, proiezione suolo e calibratore | `lens_mm` + `sensor_width_mm` + `sensor_height_mm` in Blender |
| **Lunghezza focale nominale (`f` in mm)** e **dimensione sensore** (es. `1/2.7"`, `1/2.8"`, `1/1.2"`) | Verifica coerenza ottica e calcolo `sensor_width_mm` reale o equivalente | Camera Blender (`cam.lens`, `cam.sensor_width`, `cam.sensor_height`) |
| **Risoluzione nativa e aspect ratio** (es. `2560x1920` = `4:3`, `2560x1440` = `16:9`, `3840x2160` = `16:9`, `7680x2160` = `32:9` ≈ `3.556:1`) | Critico per proiezione a terra corretta, aspect ratio player WebRTC/MSE e raycasting OpenVINO | `sensor_width`/`sensor_height`, `aspect_ratio` in `scene_manifest.json`, `.m3-cam-tile` in `SecurityFabHub.js` |
| **Codec video di fabbrica (Main vs Sub)** (`H.264` vs `H.265/HEVC`) | **WebRTC nei browser richiede H.264**. Molte camere 4K/8MP/16MP (es. Reolink Duo 3 PoE, RLC-810A) usano **H.265** sul Main Stream di default! | Configurazione stream in `go2rtc.yaml` e guida all'utente se serve impostare H.264 o usare MSE |
| **Sintassi URL RTSP / FLV / ONVIF (Main e Sub)** | Es. Reolink `h264Preview_01_main` / `h264Preview_01_sub` o ONVIF | `.env` e `go2rtc/go2rtc.yaml` |
| **Dimensioni fisiche (mm) e fattore di forma** (Bullet, Turret, Dome, Dual-lens) + staffa/angolo tipico | Per costruire un modello 3D in scala corretta in Blender | Mesh `Security_Cam_<Nome>_Body` |

### 1.2 Formule ottiche per impostare la Camera Blender senza errori

In Blender, l'angolo di campo orizzontale $\text{HFOV}$ e verticale $\text{VFOV}$ sono legati a `lens` ($f$) e alle dimensioni del sensore (`sensor_width` $W_s$, `sensor_height` $H_s$):

$$W_s = 2 \cdot f \cdot \tan\left(\frac{\text{HFOV}}{2}\right), \qquad H_s = 2 \cdot f \cdot \tan\left(\frac{\text{VFOV}}{2}\right)$$

> **Attenzione al bug/comportamento di `blender/scripts/export_glb.py`:**
> `export_glb.py` calcola di default `aspect = render.resolution_x / render.resolution_y` (attualmente `16:9`), MA se `cam_obj.get("optical_model")` è impostato **e** `cam.sensor_height > 0`, usa `cam.sensor_height` reale per calcolare `fov_v_deg`!
> Tuttavia `aspect_ratio` nel manifest continua a derivare da `scene.render.resolution_x / scene.render.resolution_y` a meno che tu non estenda `export_glb.py` per leggere una custom property dedicata (es. `aspect_ratio` o calcolare `W_s / H_s`).
> **Regola pratica:**
> - Per camera **Pinhole standard** (`pinhole_radtan`): imposta `cam.sensor_fit = 'HORIZONTAL'`, scegli `f = cam.lens` (es. la focale reale del datasheet come `4.0` mm, `2.8` mm, oppure verifica con la formula sopra), e calcola `cam.sensor_width` e `cam.sensor_height` in modo che riproducano esattamente `HFOV` e `VFOV` del datasheet (oppure per 16:9 esattamente `sensor_height = sensor_width / (16/9)`).
> - Per camera **Dual-Lens 180°** (es. `Reolink Duo 3 PoE`): imposta `optical_model = "equirectangular_180"`, `sensor_fit = 'HORIZONTAL'`, `fov_h_deg = 180.0` (in Blender la camera pinhole di preview non arriva fisicamente a 180° esatti con FOV infinito: usa comunque un proxy grandangolare es. `lens = 2.0`, `sensor_width = 36.0`, e **esporta esplicitamente** `fov_h_deg = 180.0`, `fov_v_deg` reale da datasheet es. `55.0`, e `aspect_ratio` reale es. `3.5556` tramite custom property in `export_glb.py` se il sensore non è 16:9).

---

## Fase 2 — Traduzione Misure Reali → Coordinate, Modello 3D e Custom Properties in Blender (SSoT)

### 2.1 Sistema di coordinate e Landmark verificati in `Smart_Home_3D.blend`

In Blender il sistema di riferimento è **1 unità = 1 metro**:
- **`+X`** = Est (destra guardando la casa da Sud verso Nord)
- **`+Y`** = Nord (dietro la casa; il giardino frontale/driveway è verso `-Y`)
- **`+Z`** = Alto (quota verticale sopra il piano zero)

> In `export_glb.py`, `blender_to_gltf_coords([x, y, z])` converte automaticamente in glTF/Three.js: `[x, z, -y]` (`+X` Est, `+Y` Alto, `+Z` Sud). Lavora **sempre** in coordinate Blender dentro `.blend` e lascia che sia `export_glb.py` a esportare verso glTF.

Usa queste coordinate reali estratte da `Smart_Home_3D.blend` e `public/models/scene_manifest.json` per posizionare la telecamera con precisione centimetrica rispetto alle misure fornite dall'utente:

| Oggetto / Collezione di Riferimento | Range `X` (m) | Range `Y` (m) | Range `Z` (m) | Note |
| :--- | :---: | :---: | :---: | :--- |
| **`02_Edificio_Residenziale`** | `0.00 → 14.20` | `-8.21 → 0.00` | `-0.05 → 3.00` | Casa principale (parete sud a `Y = -8.21`, parete nord a `Y = 0.00`, parete ovest a `X = 0.00`, parete est a `X = 14.20`) |
| **`03_Lavanderia`** | `0.00 → 4.65` | `-15.43 → -11.33` | `-0.05 → 2.70` | Corpo ovest a sud della casa |
| **`04_Garage`** | `6.39 → 14.20` | `-24.53 → -18.23` | `-2.10 → 2.80` | Corpo est-sud |
| **`Gate_Central_Low_Wall`** | `-11.47 → -11.09` | `-6.47 → -6.09` | `0.00 → 1.30` | Pilastrino centrale cancello (supporta `Cam_Carraio`) |
| **`Gate_Leaf_L` / `Gate_Leaf_R`** | `-15.01 → -11.87` | `-6.30 → -6.27` | `0.12 → 1.45` | Ante del cancello carraio |
| **`Cam_Carraio`** (esistente) | `-11.29` | `-6.28` | `1.68` | Camera di riferimento già configurata (`Security_Cam_Pole_Pillar` e `Security_Cam_Body`) |
| **`Driveway_Gravel`** (collider) | `-15.03 → 5.59` | `-23.03 → -8.28` | centro `-0.025` | Vialetto ghiaia |
| **`Portico_Pavement_Unified`** (collider) | `0.00 → 13.90` | `-25.03 → -7.11` | — | Portico e cortile pavimentato |
| **`Terrazza_All_Aperto`** (collider) | `-15.41 → -9.11` | `-8.28 → -1.50` | — | Terrazza ovest |
| **`Walkway_Pedestrian_Pavement`** (collider) | centro `-5.355` | centro `-8.215` | centro `-0.025` | Camminamento pedonale |
| **`Giardino_Area_1_Prato`** (collider) | centro `-0.66` (`dim 29.12`) | centro `-25.62` (`dim 15.98`) | centro `-0.025` | Prato sud |
| **`Giardino_Area_2_Prato`** (collider) | centro `9.895` (`dim 8.01`) | centro `-13.64` (`dim 9.18`) | centro `-0.025` | Prato est tra casa e garage |
| **`Giardino_Area_3A/3B/3C_Prato`** (collider) | es. `3A` centro `-5.27` | `3A` centro `-4.59` | — | Giardini ovest/nord-ovest |

> Prima di finalizzare le coordinate `(X, Y, Z)` della nuova telecamera, se l'utente fa riferimento a un muro o elemento specifico non tabellato sopra, interroga `Smart_Home_3D.blend` in headless con `"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b Smart_Home_3D.blend --python-expr "..."` per ottenere il bounding box esatto di quell'oggetto.

### 2.2 Calcolo dell'orientamento (Aim / `look_at`)

Una `bpy.types.Object` di tipo `CAMERA` in Blender guarda lungo il proprio asse locale **`-Z`**, con **`+Y` locale verso l'alto** (orizzonte diritto) e **`+X` locale verso destra**.
Dato il punto di installazione $\mathbf{P} = (x_c, y_c, z_c)$ e il punto target sul terreno/scena $\mathbf{T} = (x_t, y_t, z_t)$ indicato dall'utente, usa in uno script Python di Blender `mathutils`:

```python
from mathutils import Vector

cam_pos = Vector((x_c, y_c, z_c))
target_pos = Vector((x_t, y_t, z_t))
direction = target_pos - cam_pos
rot_quat = direction.to_track_quat('-Z', 'Y')
cam_obj.location = cam_pos
cam_obj.rotation_mode = 'XYZ'
cam_obj.rotation_euler = rot_quat.to_euler('XYZ')
```

Allinea nello stesso modo (oppure imposta come figlio o con offset coerente lungo `direction`) il corpo fisico della telecamera `Security_Cam_<Nome>_Body`, evitando collisioni geometriche (compenetrazioni nel muro/grondaia). Verifica che il corpo sporga esternamente rispetto al muro di almeno mezzo spessore della staffa.

### 2.3 Struttura oggetti & Custom Properties in Blender

Crea in `Smart_Home_3D.blend` (preferibilmente mediante uno script Python idempotente eseguito via Blender CLI e poi salvando il `.blend`, oppure estendendo `blender/scripts/add_user_devices.py` / creando uno script dedicato):

1. **Mesh 3D visibile e cliccabile:**
   - Nome: `Security_Cam_<PascalNome>_Body` (e opzionale `Security_Cam_<PascalNome>_Mount` o `..._Pole`).
   - Il prefisso **`Security_Cam_`** garantisce che `src/core/AssetLoader.js` (`dynamicNameRe`) **non** la fondi negli static batch e ne mantenga l'interattività separata.
   - Custom property obbligatoria sulla mesh cliccabile principale:
     - `ha_entity` = `"<entity_id_ha>"` (es. `"camera.portico_fluente"`)
     - `ha_label` = `"<Nome leggibile in italiano>"` (es. `"Telecamera Portico"`)
   - *(Motivo critico verificato in `src/core/InteractionManager.js` e `export_glb.py`: `InteractionManager.registerEntities` registra solo oggetti con `mesh.isMesh === true`, quindi mettere `ha_entity` solo sull'oggetto `CAMERA` non rende cliccabile la mesh 3D né mostra il badge!)*

2. **Oggetto Camera ottica (`bpy.data.objects.new("Cam_<PascalNome>", cam_data)`):**
   - Custom properties da impostare sulla camera:
     - `ha_camera_entity`: `"<entity_id_ha>"` (es. `"camera.portico_fluente"`)
     - `ha_label`: `"<Nome leggibile in italiano>"`
     - `coverage_zone`: `"<Descrizione breve zona>"` (es. `"Portico e Cortile Sud"`)
     - `optical_model`: `"pinhole_radtan"` oppure `"equirectangular_180"` (per dual-lens 180° stitched)
     - `distortion_coeffs`: `[0.0, 0.0, 0.0, 0.0, 0.0]` (o coefficienti Brown-Conrady noti/calibrati)
     - `stream_id`: `"<slug>_main"`
     - `sub_stream_id`: `"<slug>_sub"`
     - `camera_ip`: `"<IP_LAN_CAMERA>"` (solo IP locale o vuoto se non voluto in manifest; **mai** credenziali!)
     - Se panoramica non-16:9, valutare l'esportazione esplicita in `export_glb.py` di `aspect_ratio` e `is_panoramic_180` (vedi Fase 4).

### 2.4 ATTENZIONE CRITICA: Aggiornare `blender/scripts/setup_ha_properties.py`!

In `blender/scripts/setup_ha_properties.py` esiste attualmente una logica di cleanup pensata quando c'era una sola camera:

```python
for obj in bpy.data.objects:
    if obj.type == "CAMERA" and obj.name != "Cam_Carraio":
        if "ha_camera_entity" in obj:
            del obj["ha_camera_entity"]
        if "ha_label" in obj:
            del obj["ha_label"]
```

**Se lanci `npm run setup:props` o `npm run build:model` senza prima aggiornare `setup_ha_properties.py`, lo script cancellerà `ha_camera_entity` e `ha_label` dalla tua nuova telecamera!**

Prima di eseguire la pipeline Blender:
1. Aggiorna `blender/scripts/setup_ha_properties.py` (es. trasformando `"Cam_Carraio"` in una whitelist/dizionario `SECURITY_CAMERAS_CONFIG` o richiamando `setup_real_security_camera(...)` per ogni telecamera censita, inclusa la nuova).
2. Aggiorna anche `ENTITY_MAPPINGS` / la funzione di configurazione delle mesh `Security_Cam_<Nome>_Body` nello stesso script in modo che `npm run setup:props` sia **100% idempotente** su tutte le telecamere presenti e future.

### 2.5 Export, ottimizzazione GLB e verifica geometrica

Esegui dalla root del progetto:

```powershell
npm.cmd run build:model
```

*(Esegue in sequenza `setup:props` → `export:blend` → `optimize:glb`, generando `public/models/house_raw.glb`, `public/models/house.glb` e `public/models/scene_manifest.json`.)*

Subito dopo controlla `public/models/scene_manifest.json`:
- Esiste la nuova chiave sotto `manifest.cameras["Cam_<PascalNome>"]` con `is_real_security_camera: true`, `ha_camera_entity`, `stream_id`, `sub_stream_id`, `optical_model`, `fov_h_deg`, `fov_v_deg`, `gltf_transform`.
- La mesh `Security_Cam_<PascalNome>_Body` è presente sotto `manifest.ha_entities["<entity_id_ha>"].objects`.
- Tutti gli elementi preesistenti (`Cam_Carraio`, `ground_colliders`, altre entità HA) sono ancora integri e non duplicati/spariti.
- **Verifica visiva rapida (consigliata):** fai un breve script Blender che imposta `scene.camera = bpy.data.objects["Cam_<PascalNome>"]` e renderizza un'anteprima leggera in `tmp`/`scratch` (e poi rimuovi eventuali file temporanei fuori repo o tieni pulito il repo) oppure verifica proiezione/frustum con i test geometrici per accertarti che la camera non guardi dentro un muro o al contrario.

---

## Fase 3 — Configurazione Streaming `go2rtc` e `.env`

### 3.1 Aggiornamento `.env` e `.env.example`

1. In **`.env`** (locale/produzione, gitignored) aggiungi le variabili della nuova telecamera, senza toccare quelle di `Cam_Carraio`:
   ```dotenv
   # Esempio per telecamera bullet/turret/duo
   <PREFISSO>_USER=admin
   <PREFISSO>_PASS=<password_reale>
   <PREFISSO>_HOST=<IP_LAN_STATICO>
   # oppure URL completi per stream se preferisci lo stesso schema di REOLINK_CARRAIO_*
   <PREFISSO>_MAIN_URL=rtsp://...
   <PREFISSO>_SUB_URL=rtsp://...
   ```
   *(Se non conosci la password, lascia la richiesta esplicita all'utente: l'agente non deve mai inventare o chiedere di committare segreti).*

2. In **`.env.example`** documenta i soli nomi delle variabili con valori placeholder/vuoti:
   ```dotenv
   <PREFISSO>_MAIN_URL=rtsp://<USER>:<PASSWORD>@<CAMERA_IP>:554/h264Preview_01_main
   <PREFISSO>_SUB_URL=rtsp://<USER>:<PASSWORD>@<CAMERA_IP>:554/h264Preview_01_sub
   ```
   *(Non inserire mai password reali né IP reali se considerati sensibili dai controlli di igiene; segui esattamente lo stile di `REOLINK_CARRAIO_*` in `.env.example`.)*

### 3.2 Aggiornamento `go2rtc/go2rtc.yaml`

Aggiungi gli stream nella sezione `streams:` usando **solo** `${VAR}`:

```yaml
streams:
  # Esistenti (NON TOCCARE)
  carraio_main: ${REOLINK_CARRAIO_MAIN_URL}
  carraio_sub: ${REOLINK_CARRAIO_SUB_URL}
  carraio_scorrevole: ${REOLINK_CARRAIO_MAIN_URL}

  # Nuova telecamera
  <slug>_main: ${<PREFISSO>_MAIN_URL}
  <slug>_sub: ${<PREFISSO>_SUB_URL}
  <ha_entity_slug>: ${<PREFISSO>_MAIN_URL}   # utile se risolto dal nome entity HA (es. camera.<ha_entity_slug>)
```

**Attenzione al codec H.264 vs H.265:**
- `Go2RtcWebRTCStream.js` negozia WebRTC, che nei browser accetta quasi universalmente **H.264** (non H.265/HEVC su molti setup WebRTC standard). `Go2RtcMSEStream.js` fa da fallback automatico.
- Sulle camere 4K/8MP/16MP moderne (es. Reolink Duo 3 PoE, RLC-810A) il **Sub Stream (`Clear`/`Fluent`)** è spesso in H.264 mentre il **Main Stream** è in H.265 di default.
- Se la camera consente di impostare **H.264** (anche riducendo la risoluzione main se necessario), consiglialo all'utente o segnalalo nella checklist finale. **Non** attivare `#ffmpeg:` con transcoding continuo sulla CPU i5-6400 a meno di esplicita richiesta dell'utente.

Verifica subito la sintassi YAML e le regole di sicurezza con:
```powershell
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_f4_go2rtc_yaml.py tests/e2e/test_f7_repo_hygiene.py
```

---

## Fase 4 — Audit & Supporto Multi-Camera nel Codice (Frontend + Backend)

Nel repository convivono moduli **già completamente multi-camera** e moduli nati nella prima fase con riferimenti hardcoded a `Cam_Carraio` / `RLC-540A`. **L'agente deve controllare questa tabella a ogni aggiunta e generalizzare tutto ciò che bloccherebbe la nuova telecamera.**

### 4.1 Stato attuale dei componenti Frontend (`src/`)

| Componente | Stato attuale | Azione richiesta per nuova telecamera |
| :--- | :--- | :--- |
| `src/video/CameraCatalog.js` | Quasi pronto: carica tutte le camere in `manifest.cameras` con `is_real_security_camera === true` o `ha_camera_entity` | **Se la camera è equirettangolare 180°**: `isPanoramic180` oggi controlla `opticalModel.toLowerCase().includes('panoramic') \|\| this.fovH >= 150`, ma **non** `'equirectangular'`. Aggiungi `opticalModel.toLowerCase().includes('equirectangular')` e verifica che `fovH` / `aspectRatio` vengano letti dal manifest. |
| `src/ui/SecurityFabHub.js` | **Già multi-camera**: crea una tile `.m3-cam-tile` per ogni camera in `CameraCatalog`, usa `tile.cam.getStreamName('sub')`, adatta aspect ratio da `loadedmetadata`, gestisce replay slot e POV `flyToCameraPOV` | Verificare soltanto che lo stream name (`stream_id`, `sub_stream_id`) ed `entityId` corrispondano al manifest e a `go2rtc.yaml`. |
| `src/spatial/CameraProjector.js` | **Già multi-camera**: `setupCameraFrustums()` costruisce frustum, proiezione suolo e `CameraFrustumOverlay` per tutte le camere nel manifest | Verificare che la proiezione sul pavimento/prato (`groundColliders`) non resti bloccata da ostacoli e che il `CameraFrustumOverlay` usi `fov_v_deg` / `fov_h_deg` coerenti. |
| `src/devices/camera/SecurityCameraController.js` | **Single-camera hardcoded**: `primaryEntityId: 'camera.carraio_scorrevole'`, `name: 'Telecamera Carraio (Reolink RLC-540A)'`, `associatedEntityIds` fisso, `renderModal` non passa `entity` a `modalView.render()`, `findMatchingBlenderCameraName` fa match speciale solo su `'carraio'` | **Rendere multi-camera**: registrare le entità dinamicamente (es. istanziando un controller per camera da `manifest.cameras` o rendendo `SecurityCameraController` parametrico / multi-entity), passare `entity` a `modalView.render(container, context, entity)`, e far sì che `findMatchingBlenderCameraName(entityId)` risolva il match su `camData.ha_camera_entity === entityId` per tutte le camere (preservando il match `'carraio'` per `camera.carraio_trasparente`). |
| `src/devices/camera/SecurityCameraModal.js` | **Single-camera hardcoded**: `activeStreamName = 'carraio_main'`, `_camIp = '192.168.86.47'`, `_camName = 'Cam_Carraio'`, bottoni `data-stream="carraio_main"` / `"carraio_sub"`, etichetta `RLC-540A` | **Rendere dinamico**: leggere `entityId` -> cercare in `assetLoader.sceneManifest.cameras` la camera corrispondente (`_camName`, `stream_id`, `sub_stream_id`, `camera_ip`, `ha_label`, `fov_h_deg`, `fov_v_deg`, `lens_mm`) con fallback su `Cam_Carraio` SOLO se non risolto. Preservare gli ID DOM `#btn-camera-calibrate`, `#btn-toggle-simulator`, `#btn-camera-pov` richiesti dai test RBAC/e2e! |
| `src/ha/DeviceModals.js` | Prende `modalTitle` da `customController.name` | Assicurarsi che il titolo modale rifletta il nome specifico della telecamera cliccata (es. `Telecamera Portico`), e **senza** inserire `entity_id` con `.` in `#modal-subtitle` (`test_f17`). |
| `src/devices/DeviceRegistry.js` | Fallback `allMeshes.length === 0` cerca solo `Security_Cam_Body` / `Security_Cam_Pole_Pillar` | Aggiornare il fallback o assicurare che `Security_Cam_<Nome>_Body` abbia `ha_entity` in Blender così il lookup diretto via `haEntitiesMap` funziona sempre. |
| `src/video/HaSnapshotFallbackStream.js` | Testo diagnostico offline hardcoded su `REOLINK RLC-540A`, `IP 192.168.86.47`, `CAM_CARRAIO` | Passare metadati camera opzionali (etichetta/IP/camera name) così lo stato offline mostra i dati reali della telecamera selezionata mantenendo i default carraio come fallback. |
| `src/ha/HAClient.js` | `mockEntities` contiene solo `camera.carraio_scorrevole` e `camera.carraio_trasparente` | Aggiungere la nuova entità `camera.<...>` in `mockEntities` per mantenere operativo l'**Offline Mock Fallback** quando HA non è raggiungibile! |
| `src/ui/TopBar.js` | `#btn-open-cam-calib` ("Calibra Cam") apre direttamente `'Cam_Carraio'` | Decidere in modo pulito: mantenere `#btn-open-cam-calib` compatibile con i test RBAC (`test_f11`), eventualmente aprendo l'ultima camera usata o aprendo un selettore/mantenendo per le altre camere il bottone `#btn-camera-calibrate` dal rispettivo modale e dall'hub `SecurityFabHub`. |
| `src/core/CameraController.js` | Preset vista fissa (contiene `carraio_cam`, più `flyToCameraPOV`) | Opzionale: aggiungere preset camera rapido se l'utente desidera un bottone dedicato nella TopBar. |
| `blender/scripts/export_glb.py` | Calcola `aspect_ratio` solo da `scene.render.resolution_x / resolution_y` | Se la nuova telecamera ha un aspect ratio diverso da `16:9` (es. `4:3` o `32:9` panoramic), leggere un eventuale custom attribute `aspect_ratio` (o `sensor_width / sensor_height`) sull'oggetto camera e scriverlo nel manifest. |

### 4.2 Stato attuale del Backend (`spatial_server/`)

| Componente | Stato attuale | Azione richiesta per nuova telecamera |
| :--- | :--- | :--- |
| `spatial_server/main.py` (`build_pipeline_service`), `spatial_server/optics/calibration_solver.py`, `spatial_server/geometry/raycaster.py`, `spatial_server/tracking/kalman_tracker.py`, `spatial_server/recordings/filesystem_nvr.py`, `spatial_server/persistence/repository.py` (`SQLiteWALTrackRepository`) | **Già multi-camera**: carica tutte le camere dal `scene_manifest.json`, supporta sia `PinholeRadTanOpticalModel` sia `EquirectangularPanoramicOpticalModel`, fonde rilevazioni multi-camera nello stesso `track_id` 3D e salva clip NVR per `<camera_id>` | Nessun cambio strutturale richiesto per la pipeline core; verificare i test unitari. |
| `spatial_server/config.py` e `spatial_server/main.py` (`_build_openvino_source`) | **Single-camera hardcoded**: in modalità `openvino`/`hybrid` legge solo `GO2RTC_RTSP_CARRAIO_SUB` e avvia un solo thread `OpenVINORtspDetectionSource` su `"Cam_Carraio"` | Se l'utente vuole rilevamento OpenVINO anche sulla nuova telecamera: estendere `config.py` / `_build_openvino_source()` per supportare una lista di stream RTSP (uno per camera abilitata) letti da `.env` o costruiti dai `sub_stream_id` del manifest, tenendo conto del budget CPU su i5-6400 (limitare `target_fps`, es. `2`–`3` FPS totali divisi tra le camere, oppure lasciare disattivata la CV su camere secondarie se non richiesta). |
| `spatial_server/ingestion/mqtt_source.py` | **Single-camera hardcoded**: `camera_alias_map` mappa solo `carraio` / `carraio_scorrevole` / `Cam_Carraio` e manda ogni camera sconosciuta a `default_camera_id = "Cam_Carraio"` | Se si usa `mqtt` o `hybrid` (es. Frigate): aggiungere gli alias della nuova telecamera (`<slug> -> "Cam_<PascalNome>"`) o generarli automaticamente dal `scene_manifest.json`. |
| `spatial_server/main.py` (`POST /api/v1/calibration/solve-pnp`) | Rifiuta con HTTP 400 le camere non pinhole (`EquirectangularPanoramicOpticalModel`) | Per camere 180° equirettangolari, la calibrazione va fatta tramite `POST /api/v1/calibration/{camera_id}` (yaw/pitch/roll/posizione/FOV) o in Blender, non con `solve-pnp`. |

---

## Fase 5 — Verifiche, Test, Build, Deploy Windows e Calibrazione Finale

Esegui questi controlli **in ordine** dopo ogni modifica (non saltare i test esistenti):

1. **Test Backend & E2E Python:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest spatial_server/tests/verify_pipeline.py
   .\.venv\Scripts\python.exe -m pytest tests/e2e/test_f2_config_hardening.py tests/e2e/test_f3_main_auth_rbac_ws.py tests/e2e/test_f4_go2rtc_yaml.py tests/e2e/test_f7_repo_hygiene.py tests/e2e/test_f10_video_streams.py tests/e2e/test_f11_rbac_ui.py tests/e2e/test_f15_windows_deploy_e2e.py tests/e2e/test_f17_m3_ui_and_recordings.py tests/e2e/test_tier3_cross_feature.py tests/e2e/test_tier4_scenarios.py
   ```
   *(Se Playwright/browser è configurato e l'ambiente lo consente, esegui anche i test UI completi senza escludere casi; riporta sempre l'esatto esito osservato).*

2. **Build Produzione Frontend & Verifica Leak Token:**
   - Assicurati che durante il build di produzione `VITE_HA_TOKEN`, `VITE_GO2RTC_URL` e `VITE_SPATIAL_SERVER_URL` non siano esportate con segreti reali.
   ```powershell
   npm.cmd run build
   ```
   - Verifica che in `dist/` non sia presente alcun token HA o password RTSP.

3. **Aggiornamento Servizi Windows NSSM (Produzione):**
   - Le variabili aggiunte in `.env` **non** vengono lette automaticamente dai servizi Windows già installati (`SmartHome3D-go2rtc`, `SmartHome3D-SpatialServer`, `SmartHome3D-Caddy`) finché non viene rigenerato `AppEnvironmentExtra`.
   - È necessario eseguire come Amministratore `scripts/update_services.bat` oppure `powershell -ExecutionPolicy Bypass -File scripts\install_windows_services.ps1` per sincronizzare `.env` e riavviare i servizi.

4. **Calibrazione & Smoke Test Live in UI:**
   - Apri la vista 3D → controlla il nuovo badge/mesh della telecamera (click → apre il modale corretto con nome italiano, IP e stream `<slug>_main` / `<slug>_sub`).
   - Apri il drawer/pannello `SecurityFabHub` → verifica che compaiano sia `Cam_Carraio` sia la nuova camera, che lo streaming WebRTC/MSE parta senza freeze e che `flyToCameraPOV` porti al punto di vista reale.
   - Confronta l'immagine reale della telecamera con la scena 3D (modalità calibrazione / SOVRAPPOSIZIONE): affina eventuale `rotation_euler` in `Smart_Home_3D.blend` (e riesporta con `npm.cmd run build:model`) per far combaciare perfettamente pilastri, muretti e terreno, evitando derive tra SSoT Blender e override solo in `localStorage`.

5. **Documentazione di chiusura:**
   - Aggiorna `HA_DEVICES_MAPPING.md` marcando la nuova entità camera come mappata (`Cam_<PascalNome>`).

---

## Checklist Rapida per l'Utente ("C'è bisogno di altro?")

### A. Cosa devi preparare/fornire tu per ogni nuova telecamera
1. **Modello esatto** (marca + sigla completa).
2. **Misure e punto d'installazione** rispetto a un riferimento riconoscibile della casa (es. *"su muro sud del garage, a 1.5 m dallo spigolo ovest, altezza 2.9 m dal portico, inclinata verso il cancello / centro vialetto"*), più eventuale **quota/distanza di ciò che vuoi inquadrare**.
3. **Configurazione di rete della camera sulla LAN:**
   - Indirizzo IP statico / prenotazione DHCP sul router;
   - Porte **RTSP (`554`) / ONVIF** abilitate nell'app del produttore (su Reolink vanno spesso abilitate manualmente in *Network → Advanced → Port Settings*);
   - Codec idealmente impostato su **H.264** sul sub-stream (e se disponibile anche sul main stream per WebRTC nativo diretto senza ricodifica);
   - Username e password (preferibilmente account dedicato alle telecamere in `.env`).
4. **Identificativo in Home Assistant:** nome dell'entità `camera.*` generata in HA (oppure assicurarsi che `.env.local` abbia un token di test locale se vuoi farla scoprire all'agente via `tools/fetch_ha_entities.mjs`).
5. **Scelta funzionale (facoltativa):** se desideri solo **streaming 3D + frustum + snapshot NVR** oppure anche **rilevamento persone/oggetti OpenVINO 24/7** su quella telecamera (su i5-6400 aggiungere flussi OpenVINO continui va valutato rispetto al carico CPU).

### B. Interventi one-time / prerequisiti tecnici nel codice attuale (da eseguire al primo inserimento della 2ª telecamera)
Al momento il sistema ha già l'ossatura multi-camera in `CameraCatalog`, `SecurityFabHub`, `CameraProjector`, `Kalman3DMultiTracker` e `FilesystemNvrArchiveRepository`, **ma presenta alcuni blocchi single-camera legati a `Cam_Carraio`** che l'agente dovrà rimuovere seguendo la Fase 4 la prima volta che aggiungerai la seconda telecamera:
1. **`blender/scripts/setup_ha_properties.py`:** oggi cancella `ha_camera_entity` e `ha_label` su ogni camera diversa da `Cam_Carraio`; va esteso a una lista/dizionario multi-camera prima di eseguire `build:model`.
2. **UI Modali e Controller Camera (`SecurityCameraController.js`, `SecurityCameraModal.js`, `DeviceModals.js`, `TopBar.js`, `HaSnapshotFallbackStream.js`):** oggi sono ancora cablati su `Cam_Carraio`, `carraio_main`/`carraio_sub`, `192.168.86.47` e `RLC-540A`; vanno resi data-driven sul `scene_manifest.json`.
3. **Supporto aspect ratio / equirettangolare (`CameraCatalog.js`, `export_glb.py`):** utile se la seconda camera è una **180° dual-lens** (es. `equirectangular_180`) o ha sensore non `16:9`.
4. **`spatial_server` (`config.py`, `main.py`, `mqtt_source.py`):** se vuoi anche rilevamento AI multi-camera in `openvino`/`hybrid` o `mqtt`, va esteso l'avvio di più sorgenti RTSP e la tabella alias di `mqtt_source.py`.
5. **Reinstall/Sync servizi NSSM su Windows:** dopo aver aggiornato `.env` in produzione, va sempre eseguito come Amministratore `scripts/update_services.bat` o `scripts/install_windows_services.ps1`.
