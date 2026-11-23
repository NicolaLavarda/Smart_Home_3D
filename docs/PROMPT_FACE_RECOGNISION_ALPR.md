# TASK: Audit Architetturale e Piano di Implementazione Dettagliato — Sottosistema Biometrico (Face Recognition + ALPR Targhe IT/EU) per `Smart_Home_3D`

## 0. Regola Operativa Fondamentale (SOLO ANALISI E PIANIFICAZIONE)
**NON modificare, creare o eliminare alcun file del repository in questa fase.**
Il tuo obiettivo è:
1. Analizzare a fondo lo stato attuale del codice e della documentazione del repository.
2. Verificare cosa è già implementato, parzialmente abbozzato o da adattare.
3. Produrre un **piano di implementazione minuzioso, modulare e pronto per l'esecuzione a fasi**, verificabile su hardware reale prima della messa in produzione.

---

## 1. Fase Obbligatoria di Audit del Repository (Leggi prima di progettare)
Prima di formulare qualsiasi proposta, ispeziona e incrocia i seguenti file reali del progetto per rispettare al 100% convenzioni, interfacce, sicurezza e architettura esistenti:

- **Documentazione architetturale e operativa:**
  - `docs/master_prompt_architetturale_per_antigravity_ide.md`
  - `docs/PIPELINE_AGGIUNTA_TELECAMERA.md` e `docs/PROMPT_AGGIUNTA_TELECAMERA.md`
  - `docs/RUNBOOK_PRODUZIONE_FAMIGLIA_TAILSCALE.md`
  - `docs/PWA_PRODUCTION_SECURITY_PROMPT.md`
  - `docs/FUTURE_PHASES_PROMPT.md`
- **Backend Spaziale (`spatial_server/`):**
  - `spatial_server/main.py`, `spatial_server/config.py`, `spatial_server/requirements.txt`
  - `spatial_server/domain/models.py`
  - `spatial_server/biometrics/interfaces.py` e `spatial_server/biometrics/resolvers.py`
  - `spatial_server/ingestion/openvino_rtsp_source.py`, `spatial_server/ingestion/mqtt_source.py` e `spatial_server/ingestion/interfaces.py`
  - `spatial_server/optics/pinhole_model.py`, `spatial_server/optics/panoramic_model.py` e `spatial_server/optics/interfaces.py`
  - `spatial_server/tracking/kalman_tracker.py` e `spatial_server/tracking/interfaces.py`
  - `spatial_server/persistence/repository.py` e `spatial_server/persistence/interfaces.py`
  - `spatial_server/security/ha_auth.py`
  - `spatial_server/tests/verify_pipeline.py` e `spatial_server/tests/test_security_auth.py`
- **Video, Proxy e Servizi Windows:**
  - `go2rtc/go2rtc.yaml`
  - `caddy/Caddyfile`
  - `scripts/install_windows_services.ps1`, `scripts/setup_windows_node.ps1`, `scripts/update_services.bat`
- **Frontend 3D / PWA (`src/`):**
  - `src/main.js`
  - `src/spatial/network/SpatialStreamClient.js`
  - `src/spatial/avatars/SpatialAvatarFactory.js`
  - `src/spatial/TrajectoryRenderer.js` (e `src/spatial/TimelineController.js`, tenendo presente che oggi `SecurityFabHub.js` è l'hub primario montato in `src/main.js` per Live + Cronologia/Replay 3D)
  - `src/ui/SecurityFabHub.js` e `src/devices/camera/SecurityCameraModal.js`

---

## 2. Vincoli Hardware e di Produzione (INVIOLABILI)
Tutta la progettazione deve rispettare rigorosamente i vincoli dell'host di produzione sempre acceso:

- **OS:** Windows 10, esecuzione nativa dei servizi tramite **NSSM** (`SmartHome3D-go2rtc`, `SmartHome3D-SpatialServer`, `SmartHome3D-Caddy`).
- **CPU:** Intel Core i5-6400 @ 2.70 GHz (4 Core / 4 Thread, Skylake Gen 6, AVX2).
- **RAM:** **8 GB DDR4 totali** (7.89 GB utilizzabili) condivisi tra Windows 10, la VM VirtualBox di Home Assistant OS, `go2rtc`, `Caddy` e `SpatialServer`.
- **iGPU:** Intel HD Graphics 530 (nessun GPU passthrough verso VirtualBox).
- **Divieti assoluti:**
  - **NO Docker Desktop / NO WSL2**.
  - **NO PyTorch, NO TensorFlow, NO dlib, NO servizi AI esterni pesanti** (l'obiettivo è dismettere completamente il vecchio server CodeProject.AI recuperando ~1–2 GB di RAM).
  - **NO transcoding software FFmpeg** in `go2rtc` (flussi video sempre in passthrough H.264).
  - **NO scrittura su disco di snapshot temporanei** ad ogni frame.
- **Budget risorse del nuovo sottosistema biometrico dentro `SpatialServer`:**
  - RAM aggiuntiva stimata: target **<= 250–300 MB** con un unico runtime ONNX/OpenVINO condiviso (`onnxruntime` / `openvino` già presente e già condiviso tra le 4 sorgenti RTSP in `_build_openvino_sources` tramite `shared_compiled_ov` e `infer_lock`).
  - CPU: esecuzione vincolata (`intra_op_num_threads=2` o configurabile), coda asincrona limitata con politica *drop-oldest* per garantire che 2 core restino sempre disponibili alla VM VirtualBox, a `go2rtc` e al loop di tracking multi-camera (4 flussi RTSP substream attivi in parallelo a ~7 FPS complessivi).
  - Latenza target per valutazione su singolo crop: **~80–150 ms** (contro gli 1.500–2.000 ms del vecchio approccio a polling).

---

## 3. Obiettivo Funzionale e Requisiti Architetturali
Integrare in modo nativo, scalabile, disaccoppiato e *track-aware* il **riconoscimento volti** e il **riconoscimento targhe (ALPR italiano/europeo)** direttamente dentro `spatial_server/biometrics/`, rendendo l'identità biometrica parte integrante del tracking 3D, della persistenza locale e dell'interfaccia PWA.

Il piano deve coprire nel dettaglio tutti i seguenti pilastri:

### A. Strategia Dual-Stream "Substream Tracking + Main Stream On-Demand" (Multi-Camera 16:9 / 4:3 + Panoramiche 180° 32:9)
- Il tracking 24/7 (`openvino_rtsp_source.py` + `kalman_tracker.py`) continua a girare leggero sui **4 substream** condividendo il modello OpenVINO (`carraio_sub`, `portico_sub`, `ingresso_sub`, `stradina_sub`). Nota che `_infer_openvino_yolo` applica già il letterboxing `640x640` e rimappa le coordinate normalizzate `BoundingBox2D` (`[0, 1]^4`) sull'aspect ratio nativo del substream di ciascuna telecamera.
- Solo quando un track 3D di classe `person` o `car`/`vehicle` entra in una zona/distanza utile (ROI 3D o distanza massima `obs_range_m` dalla camera configurabile per telecamera) e non ha ancora un'identità bloccata, il worker biometrico richiede in modo **asincrono** un frame ad alta risoluzione dall'endpoint locale di `go2rtc` (`http://127.0.0.1:1984/api/frame.jpeg?src=<main_stream>`) mantenuto in memoria (RAM, zero file temporanei).
- **Gestione differenziata risoluzioni e ottiche (Pinhole vs Panoramiche 180° 32:9):**
  - `Cam_Carraio` (RLC-540A, 5MP `2560x1920`) e `Cam_Portico` (RLC-810A, 8MP `3840x2160`) usano il modello `pinhole_radtan`.
  - `Cam_Ingresso` e `Cam_Stradina` sono **Reolink Duo 3 PoE panoramiche 180° dual-lens** (`equirectangular_180` in `spatial_server/optics/panoramic_model.py`, aspect ratio **32:9**, main stream fino a `7680x2160` 16MP). Decodificare un intero frame JPEG `7680x2160` in BGR non compresso in Python occuperebbe ~48 MB per singolo frame e >150–200 ms di solo JPEG decode sull'i5-6400: prevedere quindi una strategia memory-safe (es. parametri di resize `go2rtc` o decode OpenCV ridotto `IMREAD_REDUCED_COLOR_2` quando il bbox è sufficientemente grande, oltre a penalizzare/scartare crop ai bordi estremi del FOV 180° dove la distorsione equirettangolare degrada landmark facciali e OCR targhe).
- Rimappatura delle coordinate normalizzate del bounding box dal substream al frame ad alta risoluzione (con padding configurabile e clamp ai bordi) per ritagliare **esclusivamente** il soggetto/veicolo prima dell'inferenza e liberare immediatamente il buffer del frame intero.
- Verifica di `go2rtc/go2rtc.yaml` e della mappatura `camera_id -> main_stream_id / sub_stream_id` (derivabile da `scene_manifest.json` / `config.py`).

### B. Pipeline Face Recognition (InsightFace ONNX puro)
- **Modelli ONNX leggeri:**
  - Face Detection + 5 Landmark: `SCRFD_500M` (con opzione configurabile per `SCRFD_2.5G`).
  - Allineamento affine standard `112x112` tramite i 5 landmark (essenziale per compensare l'angolo dall'alto delle telecamere di sorveglianza).
  - Face Embedding: `w600k_mbf.onnx` (MobileFaceNet, 512-D L2-normalizzato), con supporto configurabile per `w600k_r50.onnx` se il benchmark su i5-6400 lo consente.
- **Quality Gating pre-embedding (per evitare falsi positivi e CPU sprecata):**
  - Scarto automatico se la larghezza del volto è sotto soglia (es. `< 45–50 px`).
  - Controllo nitidezza/blur (varianza del Laplaciano sotto soglia).
  - Stima grossolana della posa/yaw dai 5 landmark (scarto profili estremi).
- **Enrollment da cartelle esistenti:**
  - Ho già delle cartelle ordinate con foto/crop di volti di familiari e parenti (`<base_dir>/<NomePersona>/*.jpg`).
  - Progettare un tool CLI idempotente in `tools/` (es. `enroll_faces.py`) che scansiona le cartelle, applica detection + allineamento + quality filtering, segnala/scarta foto non valide, estrae gli embedding e genera un indice compatto (`.npz` o tabella SQLite dedicata) contenente sia il **centroide medio** sia i **K embedding rappresentativi** per persona (diverse luci/angolazioni/occhiali).
  - Matching a runtime tramite Cosine Similarity vettorizzata in NumPy con soglia configurabile + margine tra 1° e 2° candidato (ratio/margin check per evitare ambiguità tra familiari simili).

### C. Pipeline ALPR Targhe Italiane / Europee (`fast-alpr` ONNX puro)
- **Modelli ONNX leggeri:**
  - Plate Detector: `yolo-v9-t-384-license-plate-end2end` eseguito **solo sul crop del veicolo** (mai sull'intero frame).
  - Plate OCR: `fast-plate-ocr` modello europeo (`european-plates-mobile-vit-v2-model` o `cct-xs-v2-global-model`).
- **Post-processing specifico per targhe italiane:**
  - Validazione formato standard italiano `^[A-Z]{2}[0-9]{3}[A-Z]{2}$` (escludendo le lettere non ammesse `I, O, Q, U`) con correzione deterministica posizionale delle ambiguità OCR (es. `0/O/D`, `1/I/L`, `8/B`, `5/S`, `2/Z` in base alla posizione lettera vs cifra).
  - Gestione pulita anche di targhe non standard (es. moto, vecchie targhe, estere) senza crash o scarti silenziosi.
  - Matching su **whitelist configurabile** (auto di famiglia/parenti) con tolleranza controllata (es. distanza di Levenshtein `<= 1`) applicata solo dopo aggregazione multi-frame.

### D. Architettura Concorrente, Backpressure e "Track Locking"
- **Rifattorizzazione dell'hook in `process_detection_batch` (`spatial_server/main.py`):** attualmente `await self.identity_resolver.resolve_identity(evt)` viene invocato in modo sincrono *prima* di `self.tracker.update(observations, now_ts)`, quando l'evento 2D non ha ancora un `track_id` 3D associato. Il piano deve spostare/disaccoppiare la risoluzione biometrica **dopo** `self.tracker.update(...)` (mantenendo comunque il passthrough immediato a costo zero di eventuali `sub_label` pre-etichettate da MQTT/Frigate), così da accodare richieste biometriche già arricchite di `track_id`, distanza 3D (`obs_range_m`), `camera_id` migliore e `bbox` 2D associato.
- Disaccoppiamento totale tra loop di ingestion/tracking e worker biometrico tramite coda asincrona bounded (es. `asyncio.Queue` / `ThreadPoolExecutor` dedicato con `maxsize` piccolo e scarto/sovrascrittura dei job obsoleti per lo stesso `track_id`) senza contendere il lock del loop RTSP substream se non strettamente necessario.
- **Fusione temporale per `track_id`:**
  - Accumulare al massimo `N` (es. 3–5) inferenze valide per track.
  - Applicare voto pesato (confidenza × qualità crop).
  - Appena `K` (es. 2–3) frame concordano sopra soglia sulla stessa identità o targa, **bloccare (`lock`) l'identità sul track** e interrompere l'inferenza biometrica su quel `track_id` fino al termine del track (o fino a eventuale scadenza/cambio stato).
- Valutare come propagare e mantenere l'identità biometrica (e la targa) durante il tracking multi-camera / handover 3D nel `kalman_tracker.py` (es. passaggio di un veicolo o persona tra `Cam_Carraio`, `Cam_Ingresso`, `Cam_Portico` e `Cam_Stradina`) e forzare il salvataggio immediato in SQLite (`_select_tracks_to_persist`) appena un track ottiene o aggiorna l'identità/targa bloccata.

### E. Persistenza SQLite WAL e Gestione Crop/Thumbnail
- **Database (`spatial_tracks.db`):** estensione retrocompatibile dello schema con migrazioni automatiche idempotenti (`ALTER TABLE` / nuove tabelle) per salvare `identity`, `identity_confidence`, `plate`, `plate_confidence`, `biometric_locked`, riferimento al *best crop* thumbnail e tabella/log degli eventi biometrici.
- **Gestione *best crop* su disco:** salvare esclusivamente il singolo crop migliore per track (o per evento sconosciuto/confermato) con una politica automatica di retention/pulizia (es. limite giorni o quota MB allineata a `_db_flush_loop`) per evitare crescita incontrollata del disco.

### F. Integrazione Frontend 3D / PWA e Human-in-the-Loop
- Esporre identità, targa, confidenza e stato di lock nel payload WebSocket verso `SpatialStreamClient.js` e nello storico REST (`/api/v1/tracks`).
- Mostrare badge identità/targa sugli avatar in `SpatialAvatarFactory.js` (e `TrajectoryRenderer.js`) e filtri semantici (per persona, targa, sconosciuto) in `SecurityFabHub.js` (che oggi in `src/main.js` è l'hub centrale attivo per Live multi-camera e Cronologia/Replay 3D) e, per coerenza/retrocompatibilità, in `TimelineController.js` / `SecurityCameraModal.js`.
- Prevedere (in una fase dedicata) un flusso **Human-in-the-Loop** sicuro nella PWA (`SecurityFabHub.js` / modale dedicata): visualizzare il crop migliore di un volto/targa sconosciuto o a bassa confidenza e poterlo assegnare a una persona/whitelist con aggiornamento incrementale dell'indice degli embedding o della whitelist.

### G. Sicurezza, Privacy e Manutenibilità
- **Zero segreti nel codice:** eventuali credenziali telecamere, configurazioni sensibili e whitelist targhe devono risiedere esclusivamente in variabili d'ambiente / `.env` locale o file di configurazione gitignored.
- Tutti i nuovi endpoint HTTP/WS (es. recupero thumbnail crop, stato diagnostico biometrico, gestione enrollment/whitelist) devono essere protetti tramite `spatial_server/security/ha_auth.py` in coerenza con `docs/PWA_PRODUCTION_SECURITY_PROMPT.md` e coperti da test in `spatial_server/tests/test_security_auth.py`.

### H. Fase 0 di Benchmark sull'i5-6400 e Validazione Pre-Produzione
- Includere nel piano una **Fase 0 di Benchmark** con uno script standalone eseguibile sul PC fisso su snapshot reali + le mie cartelle volti per misurare prima dell'integrazione:
  - Latenza (ms) per ogni stadio (`go2rtc` fetch, decode/crop, SCRFD, MobileFaceNet/ResNet50, Plate Detector, Plate OCR).
  - Impronta RAM (RSS) e carico CPU%.
  - Confronto reale fra `onnxruntime` (`CPUExecutionProvider` con `intra_op_num_threads=2`), `OpenVINOExecutionProvider` (CPU Skylake) e `DmlExecutionProvider` (Intel HD 530).
- Includere una strategia pulita per validare la nuova pipeline su flussi reali prima di spegnere definitivamente CodeProject.AI.

---

## 4. Formato Obbligatorio del Piano di Implementazione che devi restituire

Organizza la tua risposta esattamente nelle seguenti sezioni, con massimo livello di dettaglio tecnico:

1. **Audit dello Stato Attuale della Repository (Gap Analysis):**
   - Cosa esiste già e funziona in `biometrics/`, `ingestion/`, `tracking/`, `persistence/`, `go2rtc.yaml` e frontend.
   - Disallineamenti, limiti o debiti tecnici individuati nel codice reale che vanno risolti prima o durante l'implementazione.
2. **Architettura Target e Flusso Dati/Concorrenza:**
   - Diagramma testuale/ASCII del flusso completo (`Substream -> Tracker 3D -> ROI/Distance Gate -> Async Biometric Queue -> go2rtc Main Snapshot -> Crop -> Face/ALPR ONNX -> Multi-frame Consensus & Lock -> SQLite WAL + WS Frontend`).
   - Strategia esatta di gestione thread, memoria e backpressure sull'i5-6400.
3. **Design Modulare File-by-File:**
   - Elenco esatto di ogni file da creare o modificare, con: responsabilità, firme delle classi/interfacce, nuovi campi in `domain/models.py`, schema SQLite (DDL + strategia di migrazione), nuove chiavi di `config.py` / `.env.example`, dipendenze esatte in `requirements.txt` (con versioni compatibili Windows/Python 3.12) e gestione download/caching locale dei modelli ONNX.
4. **Specifica Contratto API REST e WebSocket (PWA):**
   - Schema dei payload WebSocket real-time e degli endpoint REST (storico con filtri, thumbnail crop, diagnostica biometrica, eventuale enrollment/whitelist) con i relativi requisiti di autenticazione `ha_auth.py`.
5. **Roadmap di Implementazione a Fasi Atomiche (Fase 0 -> Fase N):**
   - Suddividi il lavoro in fasi piccole, indipendenti e testabili (es. Fase 0 Benchmark & Enrollment CLI, Fase 1 Core Biometrics ONNX & Unit Test, Fase 2 Integrazione Dual-Stream `go2rtc` + Tracker Lock, Fase 3 Persistenza SQLite WAL & API REST/Thumbnail, Fase 4 Frontend 3D/PWA & Security Tests, Fase 5 Human-in-the-Loop & Dismissione CodeProject.AI).
   - Per **ogni fase** specifica: deliverable esatti, comando di verifica / test automatico (`pytest`) e criteri oggettivi di accettazione ("Definition of Done").
6. **Rischi Tecnici, Edge Case e Mitigazioni:**
   - Riflesso IR notturno sulle targhe, cali FPS sotto carico multi-camera, falsi positivi tra familiari simili, timeout/disconnessioni `go2rtc`, crescita disco dei thumbnail.
7. **Domande Aperte / Decisioni da Confermare:**
   - Elenca solo i parametri o le scelte architetturali ambigue che devo confermarti prima di darti il via libera alla Fase 0.

---

## 5. Dettagli Locali Opzionali da Tenere Presenti
- Percorso cartelle volti già pronte: `[INSERISCI QUI IL PERCORSO, es. D:\faces_db\<NomePersona> o "da definire"]`
- Telecamere attive in `go2rtc.yaml` e `scene_manifest.json`:
  - `Cam_Carraio` (`carraio_main` / `carraio_sub`, Reolink RLC-540A pinhole — prioritaria per **ALPR targhe** e **volti** al cancello/cancelletto)
  - `Cam_Ingresso` (`ingresso_main` / `ingresso_sub`, Reolink Duo 3 PoE 180° `equirectangular_180` 32:9 — copertura panoramica viale ovest/ingresso in sovrapposizione con `Cam_Carraio`)
  - `Cam_Portico` (`portico_main` / `portico_sub`, Reolink RLC-810A pinhole — prioritaria per **volti** sotto il portico e **ALPR/veicoli** verso il garage)
  - `Cam_Stradina` (`stradina_main` / `stradina_sub`, Reolink Duo 3 PoE 180° `equirectangular_180` 32:9 — copertura panoramica facciata nord / stradina)