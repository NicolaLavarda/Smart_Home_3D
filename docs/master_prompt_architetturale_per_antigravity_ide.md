# RUOLO E OBIETTIVO PRIMARIO

Agisci come **Principal Software Architect, 3D Computer Vision Engineer e Senior Full-Stack Developer (Three.js / Python)**, oltre che come **DevOps Tutor chiaro e didattico**.
Il tuo compito è analizzare in profondità l'intero repository corrente del progetto **Smart Home 3D Digital Twin** e progettare, pianificare e implementare un'architettura **rigorosamente Modulare e Orientata agli Oggetti (OOP / SOLID)** che integri:

1. **Streaming Video Live a bassa latenza (WebRTC / MSE)** tramite `go2rtc` dentro la scena Three.js (sia in UI modale sia proiettato sul frustum 3D in modalità POV).
2. **Calibrazione Geometrica Camera-to-World (SSoT Blender $\rightarrow$ Three.js / Python)** per allineare al millimetro l'ottica reale della telecamera con la telecamera virtuale nel modello 3D.
3. **Pipeline di Computer Vision e Raycasting 3D Real-Time** che trasforma i bounding box 2D di persone e veicoli in coordinate 3D $(X, Y, Z)$ proiettate sulle mesh calpestabili (`collider_role: "ground"`) del file `house_optimized.glb`.
4. **Tracking Multi-Camera (Filtro di Kalman 3D), Persistenza Serie-Temporali (`SQLite3 WAL`) e Predisposizione Face Recognition**, collegati allo scrubber temporale (`TimelineController.js` e `TrajectoryRenderer.js`) per il replay storico e la visualizzazione live a $60\text{ fps}$.

---

# 1. TOPOLOGIA DI RETE (PORTATILE DI SVILUPPO vs PC FISSO SERVER) E VINCOLI HARDWARE

Tieni conto fin dal primo istante della seguente topologia fisica della rete domestica (LAN `192.168.86.0/24`):

* **MACCHINA A — PC Portatile di Sviluppo (Dove stai girando TU ora, Antigravity IDE):**
  * Contiene questo repository Git, l'ambiente di sviluppo Vite/Three.js e Blender.
  * **Strategia di Sviluppo e Test Immediato:** Poiché il portatile è connesso alla stessa LAN domestica della telecamera (`192.168.86.47`) e di Home Assistant (`192.168.86.24`), durante lo sviluppo **puoi e devi scaricare, configurare e avviare `go2rtc` e il microservizio Python direttamente su questo portatile** usando i tuoi strumenti da terminale, così da permettere all'utente di testare tutto immediatamente nel browser locale senza dover configurare subito il PC fisso.
* **MACCHINA B — PC Fisso Server Sempre Acceso (Destinazione di Produzione):**
  * **Sistema Operativo e Hardware:** PC Desktop con **Windows 10**, CPU **Intel Core i5-6400 @ 2.70GHz** ($4\text{ Core} / 4\text{ Thread}$, architettura Skylake Gen 6), **8 GB di RAM DDR4** ($7.89\text{ GB}$ utilizzabili), GPU integrata **Intel HD Graphics 530** (supporto hardware **Intel QuickSync** H.264/HEVC 8-bit e **OpenVINO / DirectML**).
  * **Macchina Virtuale (VirtualBox su PC Fisso):** Esegue **Home Assistant OS** e il broker **Mosquitto MQTT** all'indirizzo `192.168.86.24` (porta `8123` per HA, porta `1883` per MQTT).
  * **Vincolo Critico di Virtualizzazione e RAM sul PC Fisso:** VirtualBox su host Windows 10 **non permette il passthrough della GPU integrata Intel HD 530** verso la VM Linux. Inoltre, con soli $8\text{ GB}$ di RAM totali sul PC fisso, **è severamente vietato utilizzare Docker Desktop / WSL2 su Windows 10** o database pesanti in RAM (come InfluxDB/TimescaleDB in container).
* **Architettura di Deploy Definitiva (Zero-Docker su Windows 10):**
  * **Dentro la VM Home Assistant (`192.168.86.24`):** Rimangono solo Home Assistant Core e il broker Mosquitto MQTT.
  * **Nativamente su Windows 10 (prima sul Portatile per i test assistiti da te, poi copiato sul PC Fisso tramite script one-click):**
    1. **`go2rtc.exe` (Eseguibile nativo standalone):** Gestisce i flussi RTSP dalle telecamere in passthrough (zero-copy) ed espone WebRTC/MSE sulla porta `1984` (consumo $\approx 25\text{ MB}$ RAM, $< 2\%$ CPU).
    2. **Microservizio Spaziale Python (`FastAPI` + `uvicorn` + `asyncio`):** Esegue l'ingestione dei rilevamenti CV, il calcolo matematico di proiezione/raycasting 3D, il tracking di Kalman e l'esposizione delle API REST + WebSocket sulla porta `8000`.
    3. **Motore di Inferenza CV Locale/Ibrido:** Il microservizio deve supportare tramite **Strategy Pattern** sia la ricezione di bounding box esterni via MQTT, sia un **detector locale leggero basato su OpenVINO Runtime** (`YOLOv8n` / `YOLOv11n` eseguibile su CPU/iGPU Intel HD Graphics 530 tramite `device="AUTO"` o `"GPU"` in OpenVINO, leggendo il sub-stream RTSP a $640 \times 360$ a $6\text{-}8\text{ fps}$ da `go2rtc`).
    4. **Database Time-Series:** **SQLite3 in modalità WAL** (`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`) con indicizzazione spazio-temporale (consumo $\approx 15\text{ MB}$ RAM, query range $< 5\text{ ms}$).

---

# 2. PARCO TELECAMERE: REOLINK RLC-540A (`192.168.86.47`) E SCALABILITÀ DUO 3 PoE

Il sistema deve essere testato immediatamente sulla telecamera esistente sul pilastrino tra cancello carraio e cancelletto pedonale, ma deve essere già progettato a livello matematico e OOP per le prossime 3 telecamere Reolink:

1. **Telecamera Attuale (`Cam_Carraio` / `camera.carraio_scorrevole`):**
   * **Modello:** **Reolink RLC-540A** (PoE, $5\text{ MP}$ Super HD, AI Person/Vehicle Detection integrata).
   * **Indirizzo di Rete Web UI:** `http://192.168.86.47:80` (IP statico/LAN: `192.168.86.47`).
   * **Ottica:** Lente fissa $4.0\text{ mm}$ @ $F=2.0$, FOV Orizzontale $\approx 80^\circ$, FOV Verticale $\approx 42^\circ$ (Modello geometrico: **Pinhole Standard con distorsione Radiale-Tangenziale Brown-Conrady** $[k_1, k_2, p_1, p_2, k_3]$).
   * **Endpoint Streaming Reolink (`192.168.86.47`):**
     * *Main Stream* (Live View Three.js): `rtsp://{CAM_USER}:{CAM_PASS}@192.168.86.47:554/h264Preview_01_main` (valuta anche l'uso del protocollo nativo `reolink` o `http-flv` supportato da `go2rtc` su `http://192.168.86.47:80/flv?port=1935&app=bcs&stream=channel0_main.bcs&user=...&password=...` per evitare qualsiasi glitch RTSP tipico dei firmware Reolink).
     * *Sub Stream* (Computer Vision $640 \times 360$ H.264 @ $6\text{-}8\text{ fps}$): `rtsp://{CAM_USER}:{CAM_PASS}@192.168.86.47:554/h264Preview_01_sub`.
   * **Nota di Configurazione Reolink:** Nei firmware Reolink recenti, le porte RTSP (`554`), RTMP (`1935`) e ONVIF (`8000`) sono spesso disabilitate di default. Dovrai fornire all'utente le istruzioni esatte (clic per clic sull'interfaccia `http://192.168.86.47:80`) per abilitarle.
2. **Telecamere Future (es. Reolink Duo 3 PoE + altre 2 Reolink):**
   * La **Reolink Duo 3 PoE** ($16\text{ MP}$) combina **due lenti fisiche in un unico flusso video panoramico a $180^\circ$** tramite stitching interno.
   * **Implicazione Architetturale Critica:** Un'immagine panoramica stitched a $180^\circ$ **non segue la proiezione prospettica rettilinea (Pinhole)**! Pertanto, la conversione da pixel $(u, v)$ a raggio 3D $(\vec{o}, \vec{d})$ **NON deve mai essere cablata (hardcoded)** nel tracker o nel raycaster, ma incapsulata dietro un'interfaccia polimorfica `ICameraOpticalModel` con implementazioni intercambiabili (`PinholeRadTanModel`, `CylindricalPanoramicModel`, `DualFisheyeStitchedModel`).

---

# 3. REQUISITI ARCHITETTURALI OBBLIGATORI: OOP, SOLID E DESIGN PATTERNS

Ogni singolo sottosistema (Backend Python e Frontend JavaScript/Three.js) deve rispettare i principi **SOLID**, l'**Inversione delle Dipendenze (DIP)** e la **Separazione delle Responsabilità (SoC)**. Nessuna classe di dominio deve dipendere da implementazioni concrete di rete, database o motori AI.

## 3.1 Architettura Backend Python (`spatial_server/`)

Struttura il backend come un package Python modulare tipizzato (`typing`, `abc.ABC`, `pydantic>=2.0`):

1. **Domain Models (`domain/models.py` - Pydantic v2):**
   * `BoundingBox2D`: coordinate normalizzate $[x_{\min}, y_{\min}, x_{\max}, y_{\max}] \in [0, 1]^4$, metodo `.get_ground_contact_uv() -> tuple[float, float]` che restituisce $(u = \frac{x_{\min} + x_{\max}}{2}, v = y_{\max})$.
   * `DetectionEvent`: `camera_id`, `timestamp`, `class_label` (`person`, `car`, `truck`, `bicycle`, `dog`), `confidence`, `bbox: BoundingBox2D`, `sub_label: Optional[str]`, `face_confidence: Optional[float]`.
   * `Ray3D`: origine $\vec{o} \in \mathbb{R}^3$ e direzione normalizzata $\vec{d} \in \mathbb{R}^3$ nello spazio mondo Three.js/Blender.
   * `SpatialPoint3D`: posizione $(x, y, z)$, velocità $(v_x, v_y, v_z)$, incertezza/covarianza, `camera_sources: list[str]`.
   * `TrackedEntity3D`: `track_id` (UUID/int), `class_label`, `identity: Optional[str]` (es. `"Mario"`, `"Sconosciuto"`, `None`), `identity_confidence: float`, `state: SpatialPoint3D`, `last_seen: float`.

2. **Strategy Pattern per l'Ottica e la Proiezione (`optics/interfaces.py`):**
   * Interfaccia astratta `ICameraOpticalModel(ABC)`:
     * `pixel_to_world_ray(u_norm: float, v_norm: float) -> Ray3D`
     * `world_point_to_pixel(point_3d: tuple[float, float, float]) -> Optional[tuple[float, float]]`
   * Implementazione 1: `PinholeRadTanOpticalModel` (per **Reolink RLC-540A**): applica `cv2.undistortPoints` con matrice intrinseca $K$ e coefficienti $[k_1, k_2, p_1, p_2, k_3]$, trasforma il raggio dallo spazio camera OpenCV ($+Z$ in avanti, $+X$ a destra, $+Y$ in basso) allo spazio mondo tramite la matrice estrinseca $4 \times 4$ esportata da Blender (`scene_manifest.json`).
   * Implementazione 2: `EquirectangularPanoramicOpticalModel` (predisposizione pronta per **Reolink Duo 3 PoE** a $180^\circ$): mappa $(u_{\text{norm}}, v_{\text{norm}})$ in angoli sferici/cilindrici $(\theta, \phi)$ prima di applicare la rotazione estrinseca.
   * `CameraCalibrationSolver`: servizio basato su `cv2.solvePnPRansac` per ricalcolare o rifinire la posa estrinseca partendo da $N \ge 4$ corrispondenze tra punti 3D noti nel modello Blender (es. spigoli del pilastrino e del cancello) e pixel 2D cliccati sul frame della telecamera.

3. **Adapter Pattern per il Raycasting 3D su Mesh (`geometry/raycaster.py`):**
   * Interfaccia `ISpatialRaycaster(ABC)` con metodo `intersect_ground(ray: Ray3D) -> Optional[tuple[float, float, float]]`.
   * Implementazione `TrimeshGroundRaycaster`: carica all'avvio `public/models/house_optimized.glb` (usando `trimesh`), filtra esclusivamente i nodi/mesh che nel `scene_manifest.json` o negli `extras` glTF possiedono `collider_role == "ground"` (vialetto, strada, giardino, pavimento), costruisce un albero BVH accelerato e calcola l'intersezione raggio-triangolo in $< 0.2\text{ ms}$. Include un fallback su piano matematico $Y = y_{\text{ground}}$ se il raggio cade appena fuori dai bordi della mesh.

4. **Adapter Pattern per l'Ingestione Computer Vision (`ingestion/interfaces.py`):**
   * Interfaccia `IDetectionSource(ABC)` (asincrona, emette `DetectionEvent` verso una coda/bus interno).
   * Implementazione 1: `OpenVINORtspDetectionSource` (Ideale per Windows 10 nativo senza Docker): si connette al sub-stream RTSP di `go2rtc` (`192.168.86.47`), decodifica a basso framerate ($6\text{-}8\text{ fps}$) ed esegue l'inferenza con un modello `YOLOv8n` compilato per **OpenVINO** (`device="AUTO"` o `"GPU"` su Intel HD Graphics 530), filtrando le classi `person`, `car`, `bicycle`, `motorcycle`, `truck`, `dog`.
   * Implementazione 2: `MqttFrigateDetectionSource`: sottoscrive i topic MQTT su `192.168.86.24:1883` e converte i payload JSON in `DetectionEvent`.
   * Implementazione 3: `SyntheticWalkSimulatorSource`: generatore matematico di camminate/veicoli di test lungo il vialetto davanti a `Cam_Carraio` per validare l'intera pipeline 3D istantaneamente anche senza muoversi dalla scrivania.

5. **Strategy Pattern per Face Recognition & Re-ID (`biometrics/interfaces.py`):**
   * Interfaccia `IIdentityResolver(ABC)` con metodo asincrono `resolve_identity(camera_id: str, frame_crop: bytes, track_id: str) -> Optional[IdentityMatch]`.
   * Implementazioni: `NoOpIdentityResolver` (default a costo zero), `OpenVINOInsightFaceResolver` (locale su iGPU) e `ExternalWebhookIdentityResolver` (per CompreFace / CodeProject.AI / Double Take).

6. **Multi-Camera 3D Tracker & Sensor Fusion (`tracking/kalman_tracker.py`):**
   * Interfaccia `IMultiCameraTracker(ABC)`.
   * Implementazione `Kalman3DMultiTracker`:
     * Stato del filtro per ogni entità: $\mathbf{x} = [x, y, z, v_x, v_y, v_z]^T$ (modello a velocità costante nello spazio 3D).
     * Associazione dati tramite **Algoritmo Ungherese (`scipy.optimize.linear_sum_assignment`)** basato sulla distanza di Mahalanobis / Euclidea nel mondo 3D e compatibilità di classe/identità.
     * **Fusione Multi-Camera:** se `Cam_Carraio` e una seconda telecamera vedono la stessa persona nello stesso punto $(X, Y, Z)$ entro un raggio di tolleranza (es. $0.8\text{ m}$), fonde le due osservazioni nello stesso `track_id` globale.

7. **Repository Pattern per il Database Serie-Temporali (`persistence/repository.py`):**
   * Interfaccia `ISpatialTrackRepository(ABC)`:
     * `save_batch(points: list[TrackedEntity3D]) -> Awaitable[None]`
     * `query_time_range(t_start: float, t_end: float, classes: Optional[list[str]], identities: Optional[list[str]], max_points: int) -> Awaitable[list[HistoricalTrackSegment]]`
     * `get_activity_density_histogram(t_start: float, t_end: float, buckets: int) -> Awaitable[list[ActivityBucket]]` (per disegnare i picchi di attività sulla timeline di Three.js).
     * `prune_old_records(retention_days: int) -> Awaitable[int]`
   * Implementazione `SQLiteWALTrackRepository`: utilizza `aiosqlite`, modalità `WAL`, buffer di scrittura in memoria con flush ogni $500\text{ ms}$, tabella indicizzata su `(timestamp, track_id, class_label, identity)` e tabella virtuale **SQLite R-Tree** per query spaziali 3D istantanee.

## 3.2 Architettura Frontend Three.js (`src/spatial/` & `src/video/`)

Mantieni il codice frontend in moduli ES6 rigorosamente orientati agli oggetti, integrati con l'architettura esistente del progetto:

1. **`IVideoStreamProvider` & `VideoStreamManager` (`src/video/`):**
   * Astrazione OOP per il player video con implementazioni `Go2RtcWebRTCStream`, `Go2RtcMSEStream` e `HaSnapshotFallbackStream`.
   * Espone un elemento `<video>` standard utilizzabile sia nel DOM (modale/drawer della telecamera) sia come sorgente per `new THREE.VideoTexture(videoElement)`.
2. **`CameraFrustumOverlay` & `CalibrationAssistantUI` (`src/spatial/calibration/`):**
   * Quando l'utente entra in modalità **POV** su `Cam_Carraio` (transizione camera Three.js verso la posa esatta della telecamera Blender), permette di sovrapporre il flusso live di `go2rtc` (`192.168.86.47`) con opacità regolabile ($0\% \rightarrow 100\%$) sul canvas 3D WebGL.
   * Fornisce controlli di fine-tuning in tempo reale (FOV, Pitch, Yaw, Roll, offset XYZ e coefficienti $k_1, k_2$) con pulsante per esportare i parametri calibrati o inviare coppie di punti 2D-3D al solver PnP del backend.
3. **`SpatialStreamClient` (`src/spatial/network/`):**
   * Gestisce la connessione WebSocket (`/ws/spatial`) con riconnessione esponenziale per i dati real-time e le chiamate REST (`/api/v1/tracks`, `/api/v1/timeline-density`) per lo scrubber storico.
4. **`SpatialAvatarFactory` & Refactoring di `TrajectoryRenderer.js` / `TimelineController.js`:**
   * Disaccoppia il rendering 3D dei soggetti rilevati tramite un `SpatialAvatarFactory`:
     * Per `person`: marker 3D stilizzato (cilindro/capsula parametrica o silhouette low-poly orientata secondo il vettore velocità $\vec{v} = (v_x, 0, v_z)$) + anello luminoso a terra + **Sprite/CSS2D Badge** sopra la testa che mostra l'`identity` (se riconosciuta) o la classe + confidenza, e la scia storica (trail 3D sfumato).
     * Per `car` / `vehicle`: bounding box 3D orientato lungo il vettore di moto sul vialetto carraio.
   * **Interpolazione LERP/Hermite a $60\text{ fps}$:** poiché la CV produce dati a $6\text{-}10\text{ Hz}$, il renderer frontend deve interpolare fluidamente nel `requestAnimationFrame` posizione e rotazione usando la posizione $(x,y,z)$ e il vettore velocità $(v_x,v_y,v_z)$ forniti dal filtro di Kalman.

---

# 4. PIPELINE BLENDER SSoT (`export_glb.py` & `scene_manifest.json`)

Ispeziona lo script Blender `export_glb.py` e il file `scene_manifest.json`. Progetta l'aggiornamento retrocompatibile affinché per ogni oggetto camera (es. `Cam_Carraio`) vengano esportati nel manifest:

* La matrice di trasformazione mondo `matrix_world` ($4 \times 4$) già convertita (o accompagnata dalla matrice di cambio base esplicita) tra il sistema di coordinate Blender ($+Z$ Up, $-Y$ Forward camera) e il sistema Three.js ($+Y$ Up).
* I parametri ottici intrinseci provenienti dai dati Camera di Blender (`lens` in mm, `sensor_width`, `sensor_height`, `angle_x`, `angle_y`) e i custom properties per il modello ottico:
  * `optical_model`: `"pinhole_radtan"` (default per RLC-540A) o `"panoramic_180"` (per Duo 3 PoE).
  * `distortion_coeffs`: `[k1, k2, p1, p2, k3]`.
  * `stream_id`: `"carraio_scorrevole"`.
* Assicurati che le mesh del terreno/vialetto davanti al cancello carraio e al cancelletto pedonale siano correttamente esportate e identificabili dal `TrimeshGroundRaycaster` come superfici di collisione `ground`.

---

# 5. SUPPORTO INSTALLAZIONE ZERO-FRICTION (IMPORTANTE: L'UTENTE NON HA MAI INSTALLATO QUESTI TOOL)

L'utente **non sa come si scarichino, installino o configurino manualmente `go2rtc`, ambienti Python, OpenVINO o i flussi RTSP della Reolink**. Pertanto:

1. **Fai tu il lavoro sporco sul Portatile:** Quando arriveremo alle fasi di implementazione, usa direttamente i tuoi comandi da terminale in Antigravity IDE per scaricare automaticamente il binario Windows di `go2rtc.exe` da GitHub Releases, creare il virtual environment Python (`.venv`), installare i pacchetti da `requirements.txt` e avviare i servizi in locale sul portatile per i test immediati.
2. **Script Automatizzati per il PC Fisso (`scripts/`):** Prepara nella cartella `scripts/` degli script PowerShell/Batch (`setup_windows_node.ps1`, `start_services.bat`) che scarichino da soli `go2rtc.exe`, creino l'ambiente Python e avviino tutto con un semplice doppio clic quando l'utente vorrà spostare la cartella `spatial_server/` sul PC fisso Windows 10.
3. **Guida Passo-Passo Illustrata per la Reolink (`192.168.86.47`):** Spiega all'utente con indicazioni elementari (menu per menu sulla pagina `http://192.168.86.47:80`) dove cliccare per attivare RTSP/RTMP/ONVIF sulla sua Reolink RLC-540A e dove inserire username e password nel file `.env`.

---

# 6. ISTRUZIONI OPERATIVE PER ANTIGRAVITY IDE (COME PROCEDERE ORA)

**NON scrivere codice alla cieca prima di aver analizzato il repository.** Esegui il lavoro seguendo rigorosamente questi 3 step sequenziali:

### STEP 1: Audit Approfondito del Codice Esistente (Fase 0)
Ispeziona tutti i file del progetto attuale, con particolare attenzione a:
* Configurazione `.env` / `.env.example` e `package.json`.
* Script Blender (`export_glb.py` e file correlati) e struttura attuale di `public/models/scene_manifest.json` e `house_optimized.glb`.
* Gestione delle telecamere nel frontend Three.js, gestione del click/POV su `Cam_Carraio`, `TimelineController.js`, `TrajectoryRenderer.js` e integrazione WebSocket con Home Assistant.

### STEP 2: Presentazione del Piano d'Implementazione Tecnico
Prima di modificare i file, produci un documento architetturale dettagliato che mostri:
1. **Esito dell'Audit:** Come si agganciano esattamente i nuovi moduli ai file esistenti del repository senza rompere alcuna funzionalità attuale.
2. **Albero dei File Completi:** L'elenco esatto dei nuovi file da creare (sia nella cartella del microservizio Python `spatial_server/`, sia in `src/` per il frontend, sia per la configurazione `go2rtc.yaml` e gli script automatici `.bat`/`.ps1` per Windows 10).
3. **Diagramma delle Classi e dei Contratti (Interfacce):** Firma esatta dei metodi delle classi astratte Python e delle classi ES6 JavaScript, incluso lo schema JSON esatto dei messaggi WebSocket e MQTT.
4. **Matrice di Trasformazione Matematica:** La formula esatta che userai nel codice per convertire la posa della camera esportata da Blender/Three.js nella matrice estrinseca OpenCV $[R \mid t]$ e nel raggio 3D $(\vec{o}, \vec{d})$.

### STEP 3: Roadmap Esecutiva in 4 Fasi Atomiche e Collaudabili
Suddividi l'implementazione nelle seguenti 4 fasi (attendi la mia conferma dopo il piano, oppure procedi fase per fase verificando il funzionamento di ciascuna):

* **FASE 1 — Attivazione RTSP Reolink (`192.168.86.47`), Setup Automatico `go2rtc` + Live Stream WebRTC in Three.js:**
  * Istruzioni passo-passo per abilitare RTSP/FLV sulla web UI Reolink `http://192.168.86.47:80`.
  * Script automatico per scaricare `go2rtc.exe` e file `go2rtc.yaml` preconfigurato per `192.168.86.47` (main stream e sub stream).
  * Implementazione di `VideoStreamManager` nel frontend per vedere il flusso live a bassa latenza cliccando su `Cam_Carraio` e proiettato nel frustum 3D.
* **FASE 2 — SSoT Blender Ottico + Tool di Calibrazione Visiva POV:**
  * Aggiornamento di `export_glb.py` e `scene_manifest.json` con i parametri ottici della Reolink RLC-540A.
  * Implementazione del `CalibrationAssistantUI` nel frontend: entrando in POV su `Cam_Carraio`, sovrapposizione in trasparenza del video reale della Reolink sopra il modello 3D del cancello/pilastrino per verificare e rifinire l'allineamento geometrico perfetto tra mondo reale e mondo virtuale.
* **FASE 3 — Microservizio Python OOP, Raycasting `Trimesh`, Inferenza OpenVINO/MQTT e Kalman 3D:**
  * Creazione del backend `spatial_server/` con `PinholeRadTanOpticalModel`, `TrimeshGroundRaycaster` su `house_optimized.glb`, `Kalman3DMultiTracker`, `SQLiteWALTrackRepository`, `SyntheticWalkSimulatorSource` e `OpenVINORtspDetectionSource`.
* **FASE 4 — Integrazione Frontend Real-Time + Scrubber Storico + Collaudo Fisico e Deploy su PC Fisso:**
  * Collegamento di `TimelineController.js`, `TrajectoryRenderer.js` e `SpatialAvatarFactory` al WebSocket e alle API REST del microservizio Python.
  * **Protocollo di Test Finale sul Campo e Migrazione:**
    1. Test immediato sul portatile con il simulatore sintetico (`SyntheticWalkSimulatorSource`).
    2. Allineamento del frustum con l'overlay live sul pilastrino del cancello.
    3. Uscita fisica davanti alla **Reolink RLC-540A (`192.168.86.47`)** (a piedi e in auto), verifica in tempo reale sulla pagina web Three.js dell'avatar 3D che cammina lungo il vialetto calpestabile e test del replay storico tramite lo scrubber temporale.
    4. Esecuzione dello script one-click per portare `go2rtc` e `spatial_server` in esecuzione permanente sul PC fisso Windows 10.

Inizia ora eseguendo lo **STEP 1 (Audit del Repository)** e lo **STEP 2 (Piano d'Implementazione Tecnico Dettagliato)**.