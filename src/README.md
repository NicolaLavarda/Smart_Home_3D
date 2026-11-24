# Frontend Digital Twin (`src/`) — Guida Sviluppatore e Mappa Moduli

Questa cartella contiene l'applicazione client **Smart Home 3D** basata su **Vite**, **Three.js**, **Home Assistant WebSocket API**, **WebRTC/MSE (go2rtc)** e **PWA (Workbox)** per il controllo in tempo reale della casa in 3D, la videosorveglianza, il replay NVR e il tracciamento spaziale CV/biometrico.

Per la trattazione architetturale completa modulo per modulo, vedi [`docs/architecture/frontend-and-devices.md`](../docs/architecture/frontend-and-devices.md).

---

## 1. Entrypoint, DOM Shell e Ciclo di Bootstrap

### [`index.html`](../index.html)
Carica [`src/style.css`](style.css) e avvia [`src/main.js`](main.js) (`type="module"`) montando i quattro layer principali dentro `#app`:

- `#canvas-container` (`z-index: 1`): ospita il `WebGLRenderer` di Three.js (`touch-action: none`).
- `#css2d-container` (`z-index: 2`): ospita il `CSS2DRenderer` per i badge 3D e gli avatar biometrici.
- `.ui-layer` (`z-index: 10`, `pointer-events: none` di base): sovrastruttura HUD con:
  - `#top-bar`: barre a isola superiore gestite da [`TopBar`](ui/TopBar.js).
  - `aside#device-modal-drawer.modal-drawer.glass`: drawer laterale/bottom sheet dei dispositivi gestito da [`DeviceModals`](ha/DeviceModals.js) (contiene `#modal-header-toggle`, `#modal-title`, `#modal-subtitle`, `#modal-close`, `#modal-body`).
  - `#security-hub-root`: pannello/strip sicurezza e NVR gestito da [`SecurityFabHub`](ui/SecurityFabHub.js).
  - `#nav-hub-root`: FAB e foglio di navigazione rapida viste/dispositivi gestito da [`NavigationFabHub`](ui/NavigationFabHub.js).

### [`src/main.js`](main.js)
La funzione `bootstrap()` orchestra l'inizializzazione e i collegamenti tra i sottosistemi nel seguente ordine:

1. **Engine 3D**: istanzia [`SceneManager`](core/SceneManager.js), [`CameraController`](core/CameraController.js) e [`AssetLoader`](core/AssetLoader.js).
2. **Home Assistant & Binding**: istanzia [`HAClient`](ha/HAClient.js), [`EntityBinder`](ha/EntityBinder.js), [`DeviceModals`](ha/DeviceModals.js) e [`InteractionManager`](core/InteractionManager.js). Inietta `cameraController` e `sceneManager` nei controller che li richiedono (es. `vacuumController`).
3. **Catalogo Camere, Spatial CV e Video/NVR**: istanzia [`CameraCatalog`](video/CameraCatalog.js), [`CameraProjector`](spatial/CameraProjector.js), [`TrajectoryRenderer`](spatial/TrajectoryRenderer.js), [`SpatialStreamClient`](spatial/network/SpatialStreamClient.js), [`VideoStreamManager`](video/VideoStreamManager.js), [`CameraRecordingManager`](video/recordings/CameraRecordingManager.js) (con [`SpatialServerNvrProvider`](video/recordings/SpatialServerNvrProvider.js) + [`EdgeCameraSdProvider`](video/recordings/EdgeCameraSdProvider.js)), [`CalibrationAssistantUI`](spatial/calibration/CalibrationAssistantUI.js), [`SpatialZoneRenderer3D`](spatial/automations/SpatialZoneRenderer3D.js) e [`AutomationStudioUI`](spatial/automations/AutomationStudioUI.js).
4. **UI Shell & Coordinamento `.ui-layer`**: monta [`TopBar`](ui/TopBar.js), [`NavigationFabHub`](ui/NavigationFabHub.js), [`SecurityFabHub`](ui/SecurityFabHub.js), [`CameraPovOverlayController`](spatial/CameraPovOverlayController.js) e [`PwaUpdatePrompt`](ui/PwaUpdatePrompt.js). Sincronizza le classi di stato su `.ui-layer` (`sheet-open`, `sec-strip-active`, `sec-expanded-active`, `nav-expanded-active`) tramite `syncUiLayerState()` per evitare sovrapposizioni tra drawer dispositivi, pannello sicurezza, calibrazione 3D e navigazione.
5. **Autenticazione & Sessione**: collega `spatialStreamClient.setTokenProvider(() => haClient.getAccessToken())`, la schermata di login/OAuth `#auth-overlay` (`createAuthOverlay`), e `haClient.onAuthChange` per scambiare il token HA con il cookie HttpOnly `sh3d_session` sul backend (`authenticateWithHaToken`), connettere `/ws/spatial`, sincronizzare le calibrazioni e gestire i deep-link `?event=` o `?panel=security&mode=...`.
6. **Asset 3D & Loop di Render**: carica `/models/house_optimized.glb` tramite `assetLoader.loadScene()`, popola `cameraCatalog.syncFromManifest()`, `cameraProjector`, `entityBinder.bindScene()`, `interactionManager.createDeviceBadges()`, `spatialZoneRenderer.loadFromBackend()`, avvia `haClient.connect()` e aggancia il loop frame-by-frame di `sceneManager.onUpdate(delta, elapsed)` su `cameraController`, `entityBinder`, `trajectoryRenderer`, `spatialZoneRenderer` e `interactionManager`.

---

## 2. Pipeline Vite, Proxy e PWA ([`vite.config.js`](../vite.config.js))

Dipendenze principali definite in [`package.json`](../package.json): `three` (`^0.174.0`), `home-assistant-js-websocket` (`^9.4.0`), `lucide` (`^1.73.0`), `vite` (`^6.2.0`), `vite-plugin-pwa` (`^0.21.2`) e `@gltf-transform/*` (`^4.1.1`) per la pipeline Blender/GLB.

| Comando (`package.json`) | Funzione | Note operative (`vite.config.js`) |
| --- | --- | --- |
| `npm run dev` | Avvio dev server (`vite --host`) | Porta `3000`, `host: true`, `sourcemap: true`, carica env con prefisso `VITE_` e `SH3D_`. |
| `npm run build` | Build bundle di produzione (`vite build`) | Forza `stripDevViteVars = true` indipendentemente da `SH3D_DEV_MODE`. |
| `npm run preview` | Anteprima locale della `dist/` (`vite preview`) | Espone anch'essa il middleware `haCameraBridgePlugin` se configurato. |

### `SH3D_DEV_MODE` e Azzeramento Variabili Dev in Build
In [`vite.config.js`](../vite.config.js), `SH3D_DEV_MODE` (impostabile a `'1'`, `'true'`, `'yes'` o `'on'` — vedi [`.env.example`](../.env.example)) abilita in sviluppo (`command === 'serve'`) l'esposizione di token LLAT e URL diretti al client. Quando `stripDevViteVars = isProd || !devModeEnabled` è `true` (sempre in `vite build`, oppure quando `SH3D_DEV_MODE` è disattivato in dev), Vite sovrascrive a `""` via `define`:
- `import.meta.env.VITE_HA_TOKEN`
- `import.meta.env.VITE_HA_DEV_URL`
- `import.meta.env.VITE_SPATIAL_SERVER_URL`
- `import.meta.env.VITE_SPATIAL_WS_URL`
- `import.meta.env.VITE_GO2RTC_URL`
- `import.meta.env.VITE_GO2RTC_TAILSCALE_URL`

Inoltre azzera `bridgeEnv.VITE_HA_TOKEN` nel plugin bridge così nessun segreto dev resta incorporato nella build statica servita all'esterno.

### Middleware `haCameraBridgePlugin` (`/api/ha-camera/snapshot`)
Registrato sia su `configureServer` sia su `configurePreviewServer`, espone `GET /api/ha-camera/snapshot?entity_id=...`:
- Valida `entity_id` con regex `^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$` (default: `camera.carraio_scorrevole`).
- Usa l'header `Authorization` della richiesta (oppure `bridgeEnv.VITE_HA_TOKEN` in dev mode) e tenta in cascata gli URL normalizzati (`ha_url` query, `VITE_HA_PUBLIC_URL`, `VITE_HA_TAILSCALE_URL`, `VITE_HA_REMOTE_URL`, `VITE_HA_LOCAL_URL`, `VITE_HA_URL`) verso `${baseUrl}/api/camera_proxy/${entityId}` con timeout `3500 ms`.
- In produzione dietro reverse proxy HTTPS, [`HaSnapshotFallbackStream`](video/HaSnapshotFallbackStream.js) interroga primariamente `/api/v1/ha-camera/snapshot/{entityId}` sul backend Spatial Server protetto da cookie `sh3d_session`.

### Strategie PWA & Workbox (`createPwaOptions`)
Configurato con `registerType: 'prompt'` e `injectRegister: 'auto'` (gestito in UI da [`PwaUpdatePrompt`](ui/PwaUpdatePrompt.js)):
- **Esclusioni navigazione (`navigateFallbackDenylist`) e `NetworkOnly`**: `/^\/api\//`, `/^\/ws\//`, `/^\/go2rtc\//`, `/[?&]auth_callback=/` (per non intercettare il rientro OAuth2 PKCE di Home Assistant né i feed live/REST).
- **`NetworkFirst` (`networkTimeoutSeconds: 3`, cache `sh3d-scene-manifest`)**: `/\/models\/scene_manifest\.json/`.
- **`CacheFirst`**: `sh3d-3d-models` (30 giorni, max 4 entry) per `/\/models\/.*\.glb(\?.*)?$/i` e `sh3d-draco-decoder` (max 10 entry, 365 giorni) per `https://www.gstatic.com/draco/...`.

---

## 3. Struttura Completa di `src/`

### Root di `src/`

| File | Responsabilità |
| --- | --- |
| [`src/main.js`](main.js) | Bootstrap applicazione, wiring servizi, coordinamento `.ui-layer`, auth e render loop. |
| [`src/style.css`](style.css) | Design system Material 3 Dark Spatial, layout HUD responsive, drawer, calibrazione e studio automazioni. |

### `src/core/` — Motore 3D, Asset e Interazione

| File | Responsabilità |
| --- | --- |
| [`SceneManager.js`](core/SceneManager.js) | WebGL2 + CSS2DRenderer, rilevamento profilo mobile/touch, ombre, illuminazione giorno/notte e pause su `visibilitychange`. |
| [`AssetLoader.js`](core/AssetLoader.js) | Caricamento `scene_manifest.json` + GLB con DRACO (`1.5.7`), texture procedurali, mappa `haEntitiesMap`, collider AABB muri e batching statico. |
| [`CameraController.js`](core/CameraController.js) | `OrbitControls`, 17 preset camera desktop (12 viste + 5 `device_*`) + `mobilePresets` portrait, interpolazione `flyTo()`, inseguimento target e modalità POV telecamere (`flyToCameraPOV`). |
| [`InteractionManager.js`](core/InteractionManager.js) | Raycasting click/tap, hover emissivo desktop, badge CSS2D distanziati e decal WebGL 3D termici su puffer/caldaia. |

### `src/ha/` — Connessione Home Assistant, Binding e Modali

| File | Responsabilità |
| --- | --- |
| [`HAClient.js`](ha/HAClient.js) | Connessione WS (`home-assistant-js-websocket`) in Dev LLAT, Prod OAuth2 PKCE o Offline Mock; `subscribeMqtt()`, `callService()`, RBAC utente. |
| [`EntityBinder.js`](ha/EntityBinder.js) | Binding entità su mesh e `PointLight` (con consolidamento mobile), animazione cancelli/serranda, diffing snapshot e ponte verso `deviceRegistry`. |
| [`DeviceModals.js`](ha/DeviceModals.js) | Gestione drawer `aside#device-modal-drawer`, instradamento a controller dispositivi o fallback `light`/generico e hook apertura/chiusura. |

### `src/devices/` — Ecosistema Smart Devices 3D

| File / Modulo | Responsabilità |
| --- | --- |
| [`BaseDeviceController.js`](devices/BaseDeviceController.js) | Classe base astratta (`bind3D`, `update3D`, `renderModal`, `onModalClose`, `onTick`, `dispose`). |
| [`DeviceRegistry.js`](devices/DeviceRegistry.js) | Singleton registro dispositivi (`deviceRegistry`), lookup per entità, binding GLTF e diffing selettivo. |
| [`tv/`](devices/tv/index.js) (`TVController.js`, `TVModal.js`, `TVRemote.js`, `TVScreenRenderer.js`, `webos_commands.js`) | Stato LG webOS (`media_player.lg_webos_smart_tv` / alias + WoL), CanvasTexture 1024x576 a 10 FPS con 13 loghi SVG e telecomando virtuale Magic Remote. |
| [`dishwasher/`](devices/dishwasher/index.js) (`DishwasherController.js`, `DishwasherModal.js`) | 15 entità programma/porta/sale/brillantante, pivot sportello `Lavastoviglie_Door_Pivot` (`-40°`), LED emissivo pulsante e controlli avvio/stop. |
| [`irrigation/`](devices/irrigation/index.js) (`IrrigationController.js`, `IrrigationModal.js`, `WaterSpraySystem.js`) | 10 entità (`irrigazione_attiva`, 3 aree, 3 timer, 3 `smart_switch`), 11 irrigatori `Sprinkler_Area*` e particelle fisiche `THREE.Points` con riser pop-up (`25 cm`). |
| [`vacuum/`](devices/vacuum/index.js) (`VacuumController.js`, `VacuumModal.js`) | Ecovacs Deebot (`vacuum.deebot` + 18 entità), tracking live MQTT `deebot/pose` / `homeassistant/deebot/pose`, LERP/SLERP, pattuglia mock e modale 3 tab. |
| [`thermal/`](devices/thermal/index.js) (`ThermalController.js`, `ThermalModal.js`) | 21 entità caldaia/puffer/doccia/valvola, algoritmo consigli (`getSmartAdvice()`), gradiente stratificato puffer e modale 3 tab. |
| [`camera/`](devices/camera/index.js) (`SecurityCameraController.js`, `SecurityCameraModal.js`) | Controller multi-camera sincronizzato da `CameraCatalog`, modale live Main/Sub, AI/biometria, switch ottimistici (`1.4 s`) e reboot Admin two-step. |

### `src/spatial/` — Computer Vision 3D, Calibrazione e Automazioni

| File / Modulo | Responsabilità |
| --- | --- |
| [`CameraProjector.js`](spatial/CameraProjector.js) | Proiezione frustum 3D e impronta 2D a terra con raycasting occlusione muri (`pinhole_radtan` + `equirectangular_180`). |
| [`CameraPovOverlayController.js`](spatial/CameraPovOverlayController.js) | Sovrapposizione live/replay HUD (`#pov-overlay-hud`) quando la camera entra in POV di una telecamera, con controllo opacità e HD/SD. |
| [`TrajectoryRenderer.js`](spatial/TrajectoryRenderer.js) | Rendering avatar 3D da tracce live WS e replay NVR, scia `18 s`, dead-reckoning `max 1.2 s`. |
| [`TimelineController.js`](spatial/TimelineController.js) | Controller timeline storico standalone (include scenario demo 3 entità; nella UI attiva la timeline è integrata in `SecurityFabHub`). |
| [`avatars/SpatialAvatarFactory.js`](spatial/avatars/SpatialAvatarFactory.js) | Mesh 3D per classe (`person`, `car`, `truck`, `motorbike`, `bicycle`, `dog`) e badge CSS2D `.spatial-avatar-badge` con stato biometrico/targa. |
| [`network/SpatialStreamClient.js`](spatial/network/SpatialStreamClient.js) | Client REST + WebSocket `/ws/spatial` con auth cookie `sh3d_session`, backoff, calibrazioni, biometria, automazioni ed episodi `SceneEvent`. |
| [`calibration/CalibrationAssistantUI.js`](spatial/calibration/CalibrationAssistantUI.js) | Pannello Admin-only `#calibration-assistant-panel` in POV con slider pose/lente e picking interattivo 3D ↔ 2D PnP. |
| [`calibration/CameraFrustumOverlay.js`](spatial/calibration/CameraFrustumOverlay.js) | Griglia 32x32 corretta per distorsione `k1/k2` o cupola 180° in sovrapposizione al live view di calibrazione. |
| [`calibration/PnPSolver.js`](spatial/calibration/PnPSolver.js) | Inversione distorsione Brown-Conrady e solver 6-DoF Levenberg-Marquardt locale (`solvePnPLocal`) di fallback a OpenCV. |
| [`automations/AutomationStudioUI.js`](spatial/automations/AutomationStudioUI.js) | Modale `#sh3d-automation-studio` a 4 tab (Regole, Zone, Entità `sh3d.*`, Log), allarme banner live e audio WebAudio. |
| [`automations/SpatialZoneRenderer3D.js`](spatial/automations/SpatialZoneRenderer3D.js) | Rendering 2.5D di poligoni e tripwire orientati con frecce normali, disegno a terra interattivo e cono azimut. |

### `src/video/` — Streaming Live e Replay Dual-Tier

| File / Modulo | Responsabilità |
| --- | --- |
| [`IVideoStreamProvider.js`](video/IVideoStreamProvider.js) | Contratto base astratto dei provider di stream video live. |
| [`CameraCatalog.js`](video/CameraCatalog.js) | Registro metadati camere reali da `scene_manifest.json` (`is_real_security_camera`) + override `VITE_SECURITY_CAMERAS_JSON`. |
| [`Go2RtcWebRTCStream.js`](video/Go2RtcWebRTCStream.js) | Negoziazione WebRTC SDP verso go2rtc (`POST /api/webrtc`, STUN Google, timeout `2200 ms`). |
| [`Go2RtcMSEStream.js`](video/Go2RtcMSEStream.js) | Stream WS fMP4 con `ManagedMediaSource` (iOS 17+) o `MediaSource`, probe codec H.264/H.265/Opus/AAC e controllo latenza `<2.2s`. |
| [`HaSnapshotFallbackStream.js`](video/HaSnapshotFallbackStream.js) | Polling JPEG a `650 ms` da `/api/ha-camera/snapshot` (dev) o `/api/v1/ha-camera/snapshot/...` convertito in `canvas.captureStream(15)`. |
| [`VideoStreamManager.js`](video/VideoStreamManager.js) | Cascata provider (`WebRTC -> MSE -> Sub-stream -> Snapshot`), condivisione `primarySessions` a 0 ms e `THREE.VideoTexture` con Grace TTL `30 s`. |
| [`recordings/`](video/recordings/index.js) (`RecordingModels.js`, `IRecordingProvider.js`, `SpatialServerNvrProvider.js`, `EdgeCameraSdProvider.js`, `DualVideoBufferController.js`, `CameraRecordingManager.js`) | Motore NVR a doppio buffer `<video>` zero-glitch con provider NVR backend (`/api/v1/recordings/...`) + Edge SD Home Assistant, preload `3.0 s` e sync drift `>0.55 s`. |

### `src/ui/` — Shell HUD Material 3, Controlli e PWA

| File | Responsabilità |
| --- | --- |
| [`TopBar.js`](ui/TopBar.js) | Barre superiori `#top-bar`, stato HA `#ha-badge`, toggle notte/frustum/badge, menu impostazioni con RBAC e telemetria FPS/GPU. |
| [`NavigationFabHub.js`](ui/NavigationFabHub.js) | FAB `#btn-nav-fab` e sheet `#m3-nav-sheet` per 6 viste ambiente e 5 dispositivi smart con badge stato live. |
| [`SecurityFabHub.js`](ui/SecurityFabHub.js) | FAB `#btn-security-fab` e `#m3-security-panel` (live multi-cam, galleria `SceneEvent`, replay timeline, impostazioni biometriche/whitelist, modale allarme `#sec-alarm-modal`). |
| [`PwaUpdatePrompt.js`](ui/PwaUpdatePrompt.js) | Toast aggiornamento Service Worker `#pwa-update-toast` basato su `virtual:pwa-register`. |
| [`icons.js`](ui/icons.js) | Registry `ICON_MAP` (90+ icone `lucide`) ed helper SVG `icon(name, opts)`. |

---

## 4. Design System, RBAC Lato UI e Modalità Offline Mock

### Design System & Token CSS ([`src/style.css`](style.css))
Il tema **Material 3 Dark Spatial** usa vetro traslucido (`backdrop-filter: blur(16px)` in `.glass`) e contrasti elevati sul canvas 3D:

- **Token base `:root`**: `--bg-primary` (`#0a0d14`), `--bg-glass` (`rgba(16, 22, 34, 0.78)`), `--bg-glass-card` (`rgba(23, 31, 48, 0.88)`), `--border-glass`, `--border-active`, accenti `--accent-cyan` (`#06b6d4`), `--accent-indigo` (`#6366f1`), `--accent-emerald` (`#10b981`), `--accent-amber` (`#f59e0b`), `--accent-rose` (`#f43f5e`), `--font-sans` (`Inter`), `--font-mono` (`JetBrains Mono`).
- **Token Material 3**: `--md-surface`, `--md-surface-container-low`, `--md-surface-container`, `--md-surface-container-high`, `--md-surface-container-highest`, `--md-outline`, `--md-outline-variant`, `--md-primary` (`#38bdf8`), `--md-on-primary`, `--md-primary-container`, `--md-secondary-container`, `--md-tertiary` (`#34d399`), `--md-error` (`#fb7185`), `--md-elevation-2`, `--md-elevation-3`, `--md-ease-standard` (`cubic-bezier(0.2, 0, 0, 1)`), `--sec-strip-video-h` (`112px`), `--sec-strip-total-h` (`170px`).
- **Breakpoint & Touch**: `SceneManager.detectMobileTouchProfile()` distingue i laptop con touchscreen (`pointer: fine`) da smartphone/tablet (`pointer: coarse` o `innerWidth <= 900`) limitando DPR a `1.5` e ombre statiche on-demand; lato CSS rispondono breakpoint a `1024px`, `767px`, `580px`, `400px`, `max-height: 540px` (landscape compatto), `(pointer: coarse)` e `(hover: none)`.

### RBAC Lato UI (`Admin` vs `Residente` vs `Ospite` / `Demo Locale`)
[`HAClient`](ha/HAClient.js) legge l'utente autenticato tramite `getUser(connection)` e calcola `isAdmin = Boolean(user.is_admin || user.is_owner)`. [`TopBar`](ui/TopBar.js) mostra il ruolo in `#top-settings-dropdown` con `.role-pill`:

| Capacità UI | `Admin` (`admin`) | `Residente` (`resident`) | `Demo Locale` (`isMock` / `guest`) |
| --- | --- | --- | --- |
| Navigazione 3D, luci, cancelli, tutti i 6 dispositivi | Sì | Sì | Sì (stato simulato in memoria) |
| Live multi-cam, switch Main/Sub, POV 3D, replay NVR, eventi | Sì | Sì | Sì (feed fallback/locale) |
| Controlli telecamera (faretto, sirena, switch rapidi) | Sì | Sì | Sì (simulato) |
| `CalibrationAssistantUI` (`#btn-open-cam-calib`, SolvePnP, salvataggio) | Sì | Nascosto | Nascosto |
| `AutomationStudioUI` (`#btn-open-automations`, regole/zone/`sh3d.*`) | Sì | Nascosto | Sì (anteprima locale `isAdmin \|\| isMock`) |
| Riavvio telecamera two-step (`#btn-cam-reboot` in `SecurityCameraModal`) | Sì | Nascosto | Nascosto |
| Biometria HITL, CRUD whitelist targhe, Face Gallery, prune, elimina eventi | Sì | Nascosto / sola lettura | Bloccato / locale |

### Modalità Offline Mock / Demo
Si attiva automaticamente (in ambiente non-produzione) se non sono configurati né `VITE_HA_TOKEN` né URL/token/callback OAuth, oppure come fallback se tutti i tentativi di connessione WebSocket in dev falliscono (`initMockMode()`):
- Popola [`HAClient.mockEntities`](ha/HAClient.js) con oltre 50 entità realistiche (luci interne/esterne, cancelli/garage, caldaia/puffer, 3 zone irrigazione, lavastoviglie, 4 Reolink + controlli, LG webOS TV + WoL, Ecovacs Deebot + consumabili).
- Simula i comandi in `handleMockService()` (incluse automazioni locali come apertura valvola/pompa irrigazione, cambio programma lavastoviglie, WoL TV e pattugliamento 3D del Deebot tramite `simulateMockPatrol()` in [`VacuumController`](devices/vacuum/VacuumController.js)).
- In assenza di go2rtc/HA raggiunti, [`HaSnapshotFallbackStream`](video/HaSnapshotFallbackStream.js) genera un canvas diagnostico `15 fps` (`"STAND-BY"` / diagnostica crosshair) per permettere il collaudo completo dei layout HUD.

---

## 5. Come Aggiungere un Nuovo Dispositivo 3D

Per introdurre un nuovo elettrodomestico o sottosistema interattivo seguendo il pattern del progetto:

1. **Prepara la geometria Blender e `scene_manifest.json`**:
   - Assegna le proprietà custom `ha_entity` (e opzionalmente `ha_alt_entity`, `ha_action: "modal"`) agli oggetti nel `.blend` e riesporta GLB + manifest.
   - Se la mesh si anima o cambia materiale dinamicamente, verifica che il suo prefisso nome sia escluso dal batching statico in `batchStaticMeshes()` dentro [`AssetLoader.js`](core/AssetLoader.js) (oppure aggiungi il prefisso all'array `protectedPrefixes`).
2. **Crea la cartella `src/devices/<nuovo_dispositivo>/`**:
   - Estendi [`BaseDeviceController`](devices/BaseDeviceController.js) implementando `get id()`, `get name()`, `get primaryEntityId()`, `get associatedEntityIds()`, `bind3D(scene, haEntitiesMap)`, `update3D(haClient)`, `renderModal(containerEl, haClient)`, e opzionalmente `onModalClose()`, `onTick(delta, elapsed)` e `dispose()`.
   - Separa il markup/eventi complessi della UI in un modulo `<Nome>Modal.js` dedicato mantenendo eventuali `<button>`/`<select>` con ID univoci.
   - Usa sempre `BaseDeviceController.getEntity(haClient, entityId)` e `haClient.callService(...)`; non chiamare mai `window.haClient` globali non iniettati.
3. **Registra il controller in [`DeviceRegistry.js`](devices/DeviceRegistry.js)**:
   - Importa il nuovo controller in `initDefaultControllers()` e chiama `this.register(new <Nome>Controller())`.
   - Se la mesh non possiede `userData.ha_entity` diretta nel GLB, aggiungi il nome oggetto Blender al mapping di fallback di `DeviceRegistry.bind3D()`.
4. **Integra Mock, Camera Preset e Navigazione**:
   - Aggiungi le entità iniziali in `HAClient.mockEntities` e la relativa gestione in `HAClient.handleMockService()`.
   - Aggiungi opzionalmente un preset camera (`device_<nome>`) in [`CameraController.js`](core/CameraController.js) e la voce di accesso rapido nel tab *Dispositivi* di [`NavigationFabHub.js`](ui/NavigationFabHub.js).
