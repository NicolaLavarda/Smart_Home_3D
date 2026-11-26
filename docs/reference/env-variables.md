# Reference Completo Variabili d'Ambiente (`.env`)

Questo documento elenca **tutte** le variabili d'ambiente definite in [`.env.example`](../../.env.example) (sezioni 0–9) e le ulteriori chiavi supportate a runtime da [`spatial_server/config.py`](../../spatial_server/config.py), [`spatial_server/automations/engine.py`](../../spatial_server/automations/engine.py), [`spatial_server/main.py`](../../spatial_server/main.py), [`vite.config.js`](../../vite.config.js) e [`src/video/CameraCatalog.js`](../../src/video/CameraCatalog.js).

> [!CAUTION]
> Non leggere, condividere o committare mai il file `.env` reale. Usa esclusivamente `.env.example` come template di riferimento.

---

## Regole Generali & Sicurezza (`SH3D_DEV_MODE` e `VITE_*`)

1. **Interruttore unico `SH3D_DEV_MODE`**:
   - `false` *(default sicuro produzione)*: abilita auth obbligatoria, CORS ristretto a `SPATIAL_ALLOWED_ORIGINS`, routing same-origin Caddy/Tailscale e ignora/azzera gli override di sviluppo (`VITE_GO2RTC_URL`, `VITE_SPATIAL_*`, `VITE_HA_TOKEN`, `VITE_HA_DEV_URL`, `SPATIAL_DEV_AUTH_REQUIRED`).
   - `true` *(sviluppo locale)*: in `spatial_server/config.py` aggiunge automaticamente le origini `DEFAULT_ALLOWED_ORIGINS` (`localhost`/`127.0.0.1` sulle porte `3000`, `5173`, `4173`, `8080`, `8765`), applica `VITE_HA_DEV_URL` e gli eventuali override `SPATIAL_DEV_AUTH_REQUIRED`, `CV_DEV_INGESTION_MODE`, `BIOMETRICS_DEV_ENABLED`.
2. **Build-time stripping in `vite.config.js`**:
   - Durante **`npm run build`** (`mode === 'production'`), Vite **azzera sempre** in compile-time (`define`) `VITE_HA_TOKEN`, `VITE_HA_DEV_URL`, `VITE_SPATIAL_SERVER_URL`, `VITE_SPATIAL_WS_URL`, `VITE_GO2RTC_URL` e `VITE_GO2RTC_TAILSCALE_URL`, indipendentemente dal valore di `SH3D_DEV_MODE`.
   - Qualsiasi altra variabile con prefisso `VITE_*` viene incorporata in chiaro nel bundle JavaScript `dist/assets/*.js`: non mettere **mai** segreti in variabili `VITE_*`.
3. **Propagazione verso NSSM su Windows**:
   - I servizi Windows (`SmartHome3D-go2rtc`, `SmartHome3D-SpatialServer`, `SmartHome3D-Caddy`) non rileggono `.env` dinamicamente da soli: dopo ogni modifica a `.env`, riesegui `scripts\install_windows_services.ps1` (o `scripts\update_services.bat` da Amministratore) per aggiornare `AppEnvironmentExtra`.

---

## Sezione 0 — Modalità Sviluppo vs Produzione

| Variabile | Default `.env.example` | Default Fallback Codice | Descrizione & Comportamento |
|---|---|---|---|
| `SH3D_DEV_MODE` | `false` | `False` (backend) / `!isProd` (Vite se omessa) | Interruttore master dev vs prod per `vite.config.js` e `SpatialServerConfig`. |

---

## Sezione 1 — Home Assistant, OAuth2 & Bridge Backend

| Variabile | Default `.env.example` | Default Fallback Codice | Descrizione & Comportamento |
|---|---|---|---|
| `VITE_HA_PUBLIC_URL` | `""` | `""` | URL HTTPS pubblico HA usato dal browser per OAuth2 PKCE (es. `https://<pc-fisso>.<tailnet>.ts.net:8443`). Se vuoto su `*.ts.net`, `HAClient` risolve automaticamente `https://<hostname>:8443`. |
| `VITE_HA_DEV_URL` | `""` | `""` | **[Solo dev]** Override di `VITE_HA_PUBLIC_URL` attivo solo con `SH3D_DEV_MODE=true`; azzerato in `npm run build`. |
| `VITE_HA_LOCAL_URL` | `""` | `""` | Indirizzo LAN HA (es. `http://192.168.86.24:8123`), usato da `spatial_server` (`HomeAssistantAuthVerifier`, snapshot, `HomeAssistantBridgeService`) e in dev dal frontend. |
| `VITE_HA_TAILSCALE_URL` | `""` | `""` | URL VPN/Tailscale diretto verso HA (es. `http://100.x.y.z:8123`), usato come fallback server-side o in dev. |
| `VITE_HA_TOKEN` | `""` | `""` | **[Solo dev]** Long-Lived Access Token frontend; deve restare vuoto in produzione. Azzerato in `npm run build`. |
| `HA_TOKEN` | `""` | `""` | Token **backend-only** (mai `VITE_`) per `HomeAssistantBridgeService`: permette automazioni H24, notifiche push, TTS/TV e discovery entità anche a browser chiusi. |
| `HA_BRIDGE_ENABLED` | `true` | `True` | Abilita il bridge WebSocket H24 verso Home Assistant in `spatial_server`. |
| `HA_MQTT_BRIDGE_ENABLED` | `false` | `False` | Abilita il bridge opzionale MQTT Discovery (`camera.sh3d_ultimo_evento`, `select.sh3d_allarme`). |
| `SPATIAL_PUBLIC_URL` | `""` | Derivato da `SPATIAL_ALLOWED_ORIGINS` / `VITE_HA_PUBLIC_URL` | URL HTTPS pubblico della PWA usato per costruire deep-link e URL firmati nelle notifiche mobile. |

---

## Sezione 5 — Streaming Video Live (`go2rtc` & Reolink)

*(Nota: la numerazione delle sezioni in `.env.example` passa direttamente da `1` a `5`.)*

| Variabile | Default `.env.example` | Default Fallback Codice | Descrizione & Comportamento |
|---|---|---|---|
| `GO2RTC_CANDIDATE_LAN` | `""` | `127.0.0.1:8555` in `go2rtc.yaml` | Candidato ICE WebRTC LAN pubblicizzato da `go2rtc` (`<IP_LAN>:8555`). Omesso da NSSM se vuoto così si applica il default YAML. |
| `GO2RTC_CANDIDATE_TAILSCALE` | `""` | `127.0.0.1:8555` in `go2rtc.yaml` | Candidato ICE WebRTC Tailscale (`<IP_TAILSCALE>:8555`). |
| `GO2RTC_API_PORT` | `1984` | `1984` | Porta API loopback di `go2rtc` usata da `spatial_server` per derivare `go2rtc_http_base_url` se quest'ultima è assente. |
| `GO2RTC_WEBRTC_PORT` | `8555` | — | Variabile informativa allineata a `webrtc.listen` in `go2rtc/go2rtc.yaml`. |
| `VITE_GO2RTC_URL` | `http://localhost:1984` | `""` in prod | **[Solo dev]** URL diretto `go2rtc` usato in `npm run dev` con `SH3D_DEV_MODE=true`; azzerato in `npm run build` (dove si usa same-origin `/go2rtc`). |
| `VITE_GO2RTC_TAILSCALE_URL` | `""` | `""` | **[Solo dev]** Endpoint `go2rtc` remoto alternativo in dev; azzerato in `npm run build`. |
| `REOLINK_CARRAIO_IP` | `""` | `192.168.86.47` in `go2rtc.yaml` | IP LAN camera Reolink RLC-540A Carraio. |
| `REOLINK_CARRAIO_USER` | `""` | `admin` in `go2rtc.yaml` | Username RTSP/CGI Carraio. |
| `REOLINK_CARRAIO_PASS` | `""` | `""` | Password RTSP/CGI Carraio (`install_windows_services.ps1` e `start_services.bat` accettano anche il fallback legacy `REOLINK_CARRAIO_PASSWORD`). |
| `REOLINK_PORTICO_IP` | `""` | `192.168.86.51` in `go2rtc.yaml` | IP LAN camera Reolink RLC-810A Portico. |
| `REOLINK_PORTICO_USER` | `""` | `admin` in `go2rtc.yaml` | Username RTSP/CGI Portico. |
| `REOLINK_PORTICO_PASS` | `""` | `""` | Password RTSP/CGI Portico. |
| `REOLINK_INGRESSO_IP` | `""` | `192.168.86.53` in `go2rtc.yaml` | IP LAN camera Reolink Duo 3 PoE Ingresso. |
| `REOLINK_INGRESSO_USER` | `""` | `admin` in `go2rtc.yaml` | Username RTSP/CGI Ingresso. |
| `REOLINK_INGRESSO_PASS` | `""` | `""` | Password RTSP/CGI Ingresso. |
| `REOLINK_STRADINA_IP` | `""` | `192.168.86.55` in `go2rtc.yaml` | IP LAN camera Reolink Duo 3 PoE Stradina. |
| `REOLINK_STRADINA_USER` | `""` | `admin` in `go2rtc.yaml` | Username RTSP/CGI Stradina. |
| `REOLINK_STRADINA_PASS` | `""` | `""` | Password RTSP/CGI Stradina. |

---

## Sezione 6 — Microservizio Spaziale (`spatial_server`, OpenVINO & MQTT)

| Variabile | Default `.env.example` | Default Fallback `config.py` | Descrizione & Comportamento |
|---|---|---|---|
| `SPATIAL_SERVER_HOST` | `127.0.0.1` | `127.0.0.1` | Host di bind FastAPI/Uvicorn (`install_windows_services.ps1` forza `127.0.0.1` in produzione). |
| `SPATIAL_SERVER_PORT` | `8765` | `8765` | Porta HTTP/WS di `spatial_server`. |
| `SPATIAL_AUTH_REQUIRED` | `true` | `True` | Abilita autenticazione obbligatoria (`sh3d_session` o Bearer HA) su API e `/ws/spatial`. |
| `SPATIAL_DEV_AUTH_REQUIRED` | `""` | — | **[Solo dev]** Sovrascrive `SPATIAL_AUTH_REQUIRED` solo quando `SH3D_DEV_MODE=true`; ignorata in produzione. |
| `SPATIAL_SESSION_SECRET` | `""` | Random 32 byte in RAM | Chiave segreta HMAC-SHA256 (>= 32 byte hex/base64) per firmare `sh3d_session` e URL media firmati. Se vuota, le sessioni decadono al riavvio. |
| `SPATIAL_ALLOWED_ORIGINS` | `""` | `DEFAULT_ALLOWED_ORIGINS` + `ha_public_url` | Lista separata da virgole delle origini CORS consentite in produzione (es. `https://<pc-fisso>.<tailnet>.ts.net`). Il wildcard `*` viene scartato. |
| `VITE_SPATIAL_SERVER_URL` | `http://localhost:8765` | `""` in prod | **[Solo dev]** URL diretto HTTP di `spatial_server` in dev; azzerato in `npm run build` (same-origin `/api/v1/*`). |
| `VITE_SPATIAL_WS_URL` | `ws://localhost:8765/ws/spatial` | `""` in prod | **[Solo dev]** URL WebSocket diretto in dev; azzerato in `npm run build` (same-origin `/ws/spatial`). |
| `CV_INGESTION_MODE` | `openvino` | `synthetic` | Modalità ingestione CV: `synthetic` \| `openvino` \| `mqtt` \| `hybrid`. |
| `OPENVINO_DEVICE` | `AUTO` | `AUTO` | Target inferenza OpenVINO (`AUTO`, `CPU`, `GPU`). |
| `OPENVINO_CPU_THREADS` | `2` | `2` | Numero di thread CPU OpenVINO/ONNX per detection YOLOv8n (`max(1, val)`). |
| `OPENVINO_MODEL_NAME` | `yolov8n` | — | Nome logico modello in `.env.example` (il path fisico effettivo è controllato da `OPENVINO_YOLO_MODEL`, default `spatial_server/models/yolov8n_openvino_model`). |
| `OPENVINO_FPS_LIMIT` | `7.0` | `7.0` | Budget FPS complessivo ripartito tra gli stream OpenVINO attivi (`max(1.5, fps / n_cams)`). |
| `OPENVINO_CONF_THRESHOLD` | `0.62` | `0.35` | Soglia minima confidenza globale di fallback YOLOv8n/HOG (usata per classi senza override specifico o quando le soglie per-classe sono omesse). |
| `SPATIAL_RECONSTRUCT_PERSON` | `true` | `True` | Abilita/disabilita rilevamento e ricostruzione 3D per persone (`person`). |
| `SPATIAL_PERSON_STATIONARY_CONF_THRESHOLD` | `0.78` | `OPENVINO_CONF_THRESHOLD` | Confidenza minima per ricostruire una persona ferma (`speed <= SPATIAL_PERSON_MIN_SPEED_MPS`). |
| `SPATIAL_PERSON_MOVING_CONF_THRESHOLD` | `0.62` | `OPENVINO_CONF_THRESHOLD` | Confidenza minima per ricostruire una persona in movimento (`speed > SPATIAL_PERSON_MIN_SPEED_MPS`). |
| `SPATIAL_PERSON_MIN_SPEED_MPS` | `0.25` | `0.25` | Velocità orizzontale minima (m/s) per discriminare persona ferma vs in movimento (`0.0` = nessuna tolleranza). |
| `SPATIAL_RECONSTRUCT_VEHICLE` | `true` | `True` | Abilita/disabilita rilevamento e ricostruzione 3D per veicoli (`car`, `truck`, `motorbike`). |
| `SPATIAL_VEHICLE_STATIONARY_CONF_THRESHOLD` | `0.72` | `OPENVINO_CONF_THRESHOLD` | Confidenza minima per ricostruire un veicolo fermo (`speed <= SPATIAL_VEHICLE_MIN_SPEED_MPS`). |
| `SPATIAL_VEHICLE_MOVING_CONF_THRESHOLD` | `0.62` | `OPENVINO_CONF_THRESHOLD` | Confidenza minima per ricostruire un veicolo in movimento (`speed > SPATIAL_VEHICLE_MIN_SPEED_MPS`). |
| `SPATIAL_VEHICLE_MIN_SPEED_MPS` | `0.35` | `0.35` | Velocità orizzontale minima (m/s) per discriminare veicolo fermo vs in movimento (`0.0` = nessuna tolleranza). |
| `SPATIAL_RECONSTRUCT_ANIMAL` | `true` | `True` | Abilita/disabilita rilevamento e ricostruzione 3D per animali (`dog`, ecc.). |
| `SPATIAL_ANIMAL_STATIONARY_CONF_THRESHOLD` | `0.75` | `OPENVINO_CONF_THRESHOLD` | Confidenza minima per ricostruire un animale fermo (`speed <= SPATIAL_ANIMAL_MIN_SPEED_MPS`). |
| `SPATIAL_ANIMAL_MOVING_CONF_THRESHOLD` | `0.62` | `OPENVINO_CONF_THRESHOLD` | Confidenza minima per ricostruire un animale in movimento (`speed > SPATIAL_ANIMAL_MIN_SPEED_MPS`). |
| `SPATIAL_ANIMAL_MIN_SPEED_MPS` | `0.20` | `0.20` | Velocità orizzontale minima (m/s) per discriminare animale fermo vs in movimento (`0.0` = nessuna tolleranza). |
| `OPENVINO_CAMERA_STREAMS` | *(commentata)* | `""` (auto da `scene_manifest.json`) | Override manuale CSV `CamId=rtsp://...` per selezionare stream RTSP specifici per OpenVINO. |
| `SPATIAL_RETENTION_DAYS` | `30` | `30` | Giorni di retention nello storico traiettorie `spatial_tracks.db`. |
| `SPATIAL_PERSIST_MIN_DISPLACEMENT_M` | `0.15` | `0.15` | Spostamento minimo in metri richiesto prima di scrivere un nuovo campione di tracking su DB. |
| `SPATIAL_PERSIST_HEARTBEAT_S` | `10.0` | `10.0` | Intervallo massimo (secondi) di persistenza heartbeat per target stazionari. |
| `MQTT_BROKER_HOST` | `""` | `192.168.86.24` | Hostname/IP del broker Mosquitto MQTT (VM HA). |
| `MQTT_BROKER_PORT` | `1883` | `1883` | Porta TCP del broker MQTT. |
| `MQTT_USER` | `""` | `""` | Username MQTT opzionale. |
| `MQTT_PASS` | `""` | `""` | Password MQTT opzionale (supportato anche `MQTT_PASSWORD`). |
| `MQTT_TOPIC_PREFIX` | `frigate` | `frigate` (`frigate/events`) | Prefisso topic Frigate; `config.py` compone `<MQTT_TOPIC_PREFIX>/events` se `MQTT_FRIGATE_TOPIC` non è impostato. |

---

## Sezione 7 — Sottosistema Biometrico Nativo (Face Recognition + ALPR)

| Variabile | Default `.env.example` | Default Fallback `config.py` | Descrizione & Comportamento |
|---|---|---|---|
| `GO2RTC_HTTP_BASE_URL` | `http://127.0.0.1:1984` | `http://127.0.0.1:{GO2RTC_API_PORT}` | Base URL HTTP di `go2rtc` usato per snapshot alta risoluzione (`api/frame.jpeg`) e `SceneEventManager`. |
| `BIOMETRICS_ENABLED` | `true` | `False` | Master switch del worker biometrico asincrono (`BiometricWorkerService`). |
| `BIOMETRICS_FACE_ENABLED` | `true` | `True` | Abilita Face Recognition (`SCRFD_500M` + `MobileFaceNet`). |
| `BIOMETRICS_ALPR_ENABLED` | `true` | `True` | Abilita riconoscimento targhe (`YOLOv9-t` + `fast-plate-ocr`). |
| `BIOMETRICS_ONNX_PROVIDER` | `cpu` | `cpu` | Execution provider ONNX Runtime (`cpu`, ecc.). |
| `BIOMETRICS_ONNX_INTRA_THREADS` | `2` | `2` | Thread intra-op ONNX Runtime (`max(1, val)`). |
| `BIOMETRICS_ONNX_INTER_THREADS` | `1` | `1` | Thread inter-op ONNX Runtime (`max(1, val)`). |
| `BIOMETRICS_QUEUE_MAXSIZE` | `8` | `8` | Capacità massima coda bounded di job biometrici. |
| `BIOMETRICS_MIN_EVAL_INTERVAL_S` | `0.6` | `0.6` | Intervallo minimo tra valutazioni consecutive sullo stesso `track_id`. |
| `BIOMETRICS_MAX_ATTEMPTS_PER_TRACK` | `6` | `6` | Numero massimo di tentativi biometrici per singolo `track_id`. |
| `BIOMETRICS_UNKNOWN_BACKOFF_S` | `4.0` | `4.0` | Backoff (secondi) dopo mancato riconoscimento prima di riprovare sullo stesso track. |
| `BIOMETRICS_SNAPSHOT_TIMEOUT_S` | `2.5` | `2.5` | Timeout fetch snapshot HTTP da `go2rtc`. |
| `BIOMETRICS_PANORAMIC_MAX_WIDTH` | `3840` | `3840` | Larghezza massima downscaling per snapshot da camere 180° (16MP). |
| `BIOMETRICS_PANORAMIC_EDGE_MARGIN_U` | `0.15` | `0.15` | Margine laterale normalizzato `[0, 0.45]` per tagli/edge su camere panoramiche 180°. |
| `BIOMETRICS_FACE_DET_MODEL` | `det_500m.onnx` | `det_500m.onnx` | Nome file modello detection volti SCRFD sotto `spatial_server/models/biometrics/face/`. |
| `BIOMETRICS_FACE_REC_MODEL` | `w600k_mbf.onnx` | `w600k_mbf.onnx` | Nome file modello embedding facciale ArcFace/MobileFaceNet. |
| `BIOMETRICS_FACE_MIN_WIDTH_PX` | `48.0` | `48.0` | Larghezza minima bounding-box volto in pixel. |
| `BIOMETRICS_FACE_MIN_LAPLACIAN` | `35.0` | `35.0` | Soglia minima nitidezza (varianza Laplaciano). |
| `BIOMETRICS_FACE_MAX_YAW_RATIO` | `0.55` | `0.55` | Rapporto massimo di rotazione laterale (yaw) accettato. |
| `BIOMETRICS_FACE_MATCH_THRESHOLD` | `0.45` | `0.45` | Soglia minima similarità coseno per match volto. |
| `BIOMETRICS_FACE_MARGIN_THRESHOLD` | `0.08` | `0.08` | Margine minimo tra 1° e 2° candidato nella galleria volti. |
| `BIOMETRICS_FACE_CONSENSUS_K` | `2` | `2` | Numero di frame concordanti richiesti per bloccare (`biometric_locked`) l'identità volto. |
| `BIOMETRICS_FACE_MAX_RANGE_M` | `8.0` | `8.0` | Distanza massima camera-target in metri per triggerare Face Recognition. |
| `BIOMETRICS_ALPR_DET_MODEL` | `yolo-v9-t-384-license-plate-end2end` | `yolo-v9-t-384-license-plate-end2end` | Modello detector targhe sotto `spatial_server/models/biometrics/alpr/`. |
| `BIOMETRICS_ALPR_OCR_MODEL` | `cct-xs-v2-global-model` | `cct-xs-v2-global-model` | Modello OCR targhe (`fast-plate-ocr`). |
| `BIOMETRICS_ALPR_MIN_PLATE_WIDTH_PX` | `55.0` | `55.0` | Larghezza minima crop targa in pixel. |
| `BIOMETRICS_ALPR_CONSENSUS_K` | `2` | `2` | Consensus multi-frame richiesto prima di bloccare una targa su un track. |
| `BIOMETRICS_ALPR_MAX_RANGE_M` | `13.0` | `13.0` | Distanza massima camera-veicolo in metri per ALPR. |
| `BIOMETRICS_ALPR_WHITELIST_MAX_DIST` | `1` | `1` | Distanza di Levenshtein massima ammessa per fuzzy match su `plates_whitelist.json`. |
| `BIOMETRICS_CROP_RETENTION_DAYS` | `14` | `14` | Giorni di retention dei crop JPEG biometrici in `data/biometrics/crops/`. |
| `BIOMETRICS_CROP_MAX_MB` | `250.0` | `250.0` | Quota disco massima (MB) per i crop biometrici salvati. |
| `BIOMETRICS_DATA_DIR` | *(commentata)* | `spatial_server/data/biometrics` | Override cartella dati biometrici (galleria `.npz`, whitelist, crop). |
| `BIOMETRICS_PLATES_WHITELIST_FILE` | *(commentata)* | `<BIOMETRICS_DATA_DIR>/plates_whitelist.json` | Override percorso file JSON whitelist targhe. |
| `BIOMETRICS_CAMERA_RULES` | *(commentata)* | `""` | Override range per singola camera nel formato `CamId:face=8.0,CamId:alpr=13.0`. |

---

## Sezione 8 — Registrazione NVR Dual-Tier (`Sub` H24 + `Main` Event)

| Variabile | Default `.env.example` | Default Fallback `config.py` | Descrizione & Comportamento |
|---|---|---|---|
| `SPATIAL_NVR_STORAGE_DIR` | *(vuota)* | `None` | Cartella radice su HDD CMR interno SATA (es. `D:\Surveillance`). Se vuota, il recorder NVR resta disattivato in modo graceful. |
| `SPATIAL_NVR_RECORDER_ENABLED` | `false` | `False` | Abilita il registratore nativo Dual-Tier (`DualTierNvrRecorderCoordinator`). |
| `SPATIAL_NVR_SUB_SEGMENT_SEC` | `60.0` | `60.0` | Durata in secondi dei segmenti continui `sub` (min `10.0`). |
| `SPATIAL_NVR_MAIN_PRE_ROLL_SEC` | `10.0` | `10.0` | Secondi di pre-roll conservati nel ring buffer RAM per le clip `main` (`0.0`..`60.0`). |
| `SPATIAL_NVR_MAIN_INERTIA_SEC` | `15.0` | `15.0` | Secondi di post-roll/inerzia dopo l'ultimo trigger prima di chiudere una clip `main` (`2.0`..`120.0`). |
| `SPATIAL_NVR_MAIN_MAX_CLIP_SEC` | `300.0` | `300.0` | Durata massima singola clip `main` prima del rollover automatico (min `30.0`). |
| `SPATIAL_NVR_RAM_BUFFER_MAX_MB_PER_CAM` | `48.0` | `48.0` | Tetto RAM (MB) per camera del ring buffer GOP (`8.0`..`256.0`). |
| `SPATIAL_NVR_TRIGGER_CLASSES` | `person,car,truck,motorbike` | `("person","car","truck","motorbike")` | Classi YOLO/CV che scatenano la registrazione `main` ad alta risoluzione. |
| `SPATIAL_NVR_MIN_CONFIDENCE` | `0.55` | `0.55` | Confidenza minima di detection per attivare il trigger `main` (`0.05`..`0.99`). |
| `SPATIAL_NVR_MAX_STORAGE_GB` | `0.0` | `0.0` | Tetto storage globale NVR in GB (`0.0` = illimitato, delega al solo `MIN_FREE_GB`). |
| `SPATIAL_NVR_MIN_FREE_GB` | `50.0` | `50.0` | Spazio libero minimo da preservare sul disco NVR (innesca pruning dei segmenti `sub` più vecchi). |
| `SPATIAL_NVR_SUB_RETENTION_DAYS` | `30` | `30` | Retention in giorni per registrazioni continue `sub`. |
| `SPATIAL_NVR_MAIN_RETENTION_DAYS` | `60` | `60` | Retention in giorni per clip eventi `main`. |
| `SPATIAL_NVR_PRUNE_INTERVAL_SEC` | `300.0` | `300.0` | Frequenza in secondi del ciclo di manutenzione retention (min `10.0`). |
| `SPATIAL_NVR_INDEX_DB_NAME` | `nvr_index.db` | `nvr_index.db` | Nome file SQLite dell'indice NVR dentro `SPATIAL_NVR_STORAGE_DIR` (sanitizzato contro path traversal). |
| `SPATIAL_NVR_CAMERA_CLOCK_OFFSETS` | *(commentata)* | `""` | Offset temporali di calibrazione fine (ms) nel formato `CamId:sub=0,CamId:main=-200`. |
| `SPATIAL_NVR_CAMERA_STREAMS` | *(commentata)* | `""` | Override stream RTSP per NVR nel formato `CamId=sub_url\|main_url,...`. |

---

## Sezione 9 — Episodi Scena (`SceneEvent`), Snapshot Annotati & Media Firmati

| Variabile | Default `.env.example` | Default Fallback `config.py` | Descrizione & Comportamento |
|---|---|---|---|
| `SPATIAL_EVENTS_INERTIA_S` | `18.0` | `18.0` | Inerzia (secondi) prima di chiudere un episodio `SceneEvent` (`2.0`..`120.0`). |
| `SPATIAL_EVENTS_PRE_ROLL_S` | `3.0` | `3.0` | Finestra pre-roll associata agli episodi (`0.0`..`30.0`). |
| `SPATIAL_EVENTS_RETENTION_DAYS` | `30` | `30` | Retention in giorni per record e snapshot degli eventi scena. |
| `SPATIAL_EVENTS_SNAPSHOT_MAX_MB` | `400.0` | `400.0` | Quota disco massima (MB) per `spatial_server/data/events/`. |
| `SPATIAL_EVENTS_SNAPSHOT_MAX_WIDTH` | `1280` | `1280` | Larghezza massima JPEG degli snapshot salvati/annotati (`480`..`3840`). |
| `SPATIAL_SIGNED_MEDIA_TTL_S` | `86400` | `86400` | Durata (secondi, default 24h) dei token HMAC per l'endpoint `/api/v1/events/{event_id}/media/{variant}.jpg` (notifiche mobile). |

---

## Variabili Aggiuntive & Alias Legacy nel Codice

Oltre alle variabili elencate in `.env.example`, il codice supporta le seguenti chiavi aggiuntive o alias retrocompatibili:

| Variabile | File Sorgente | Default | Scopo / Note |
|---|---|---|---|
| `HOME_LATITUDE`, `HOME_LONGITUDE` | [spatial_server/automations/engine.py](../../spatial_server/automations/engine.py) | `45.55`, `11.55` | Coordinate geografiche per `AstronomicalClock` (alba/tramonto nel motore automazioni). |
| `VITE_SECURITY_CAMERAS_JSON` | [src/video/CameraCatalog.js](../../src/video/CameraCatalog.js) | `""` | Array JSON opzionale di telecamere extra caricate da `CameraCatalog` in aggiunta al manifest Blender. |
| `SPATIAL_AUTH_CACHE_TTL_S` | [spatial_server/config.py](../../spatial_server/config.py) | `120.0` | TTL (secondi) cache verifica token HA in `HomeAssistantAuthVerifier`. |
| `OPENVINO_YOLO_MODEL` | [spatial_server/config.py](../../spatial_server/config.py) | `spatial_server/models/yolov8n_openvino_model` | Path completo modello OpenVINO IR/ONNX. |
| `FACE_RECOGNITION_WEBHOOK_URL` | [spatial_server/config.py](../../spatial_server/config.py) | `""` | Legacy webhook esterno (CodeProject.AI); **deve restare vuoto** usando la biometria nativa. |
| `GO2RTC_RTSP_CARRAIO_SUB`, `GO2RTC_RTSP_BASE_URL`, `GO2RTC_RTSP_<SLUG>_SUB` | [spatial_server/config.py](../../spatial_server/config.py), [spatial_server/main.py](../../spatial_server/main.py) | `rtsp://127.0.0.1:8554/carraio_sub`, `rtsp://127.0.0.1:8554` | Override URL RTSP per singolo stream OpenVINO (`<SLUG>` es. `PORTICO`, `INGRESSO`, `STRADINA`). |
| `CV_DEV_INGESTION_MODE`, `BIOMETRICS_DEV_ENABLED` | [spatial_server/config.py](../../spatial_server/config.py) | `""` | Override opzionali applicati solo se `SH3D_DEV_MODE=true`. |
| `OMP_NUM_THREADS` | [scripts/install_windows_services.ps1](../../scripts/install_windows_services.ps1) | `2` (impostato da script se assente) | Limita i thread OpenMP del processo `SmartHome3D-SpatialServer` su CPU `i5-6400`. |
| Alias legacy | `config.py`, `HAClient.js`, `scripts/` | — | `HA_PUBLIC_URL`, `VITE_HA_REMOTE_URL`, `VITE_HA_URL`, `SPATIAL_INGESTION_MODE`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_PASSWORD`, `MQTT_FRIGATE_TOPIC`, `REOLINK_CARRAIO_PASSWORD`. |

---

## Riferimenti Correlati
- Template canonico: [`.env.example`](../../.env.example)
- Caricamento backend: [spatial_server/config.py](../../spatial_server/config.py)
- Build & stripping frontend: [vite.config.js](../../vite.config.js)
- Propagazione servizi Windows: [scripts/README.md](../../scripts/README.md)
