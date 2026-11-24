# `spatial_server` — Microservizio Spatial CV, Biometria, NVR e Automazioni 3D

> **Riferimento architetturale approfondito:** per gli algoritmi interni, le formule matematiche di proiezione/tracking, gli schemi dei dati e i dettagli implementativi di tutti i 12 sottosistemi, consulta [docs/architecture/spatial-cv-and-biometrics.md](../docs/architecture/spatial-cv-and-biometrics.md).

`spatial_server` è il backend Python (FastAPI + ASGI Uvicorn) del Digital Twin **Smart Home 3D**. Esegue in tempo reale l'ingestione dei flussi video/eventi, la proiezione 2D→3D tramite modelli ottici e raycasting sul terreno Blender, il tracking multi-camera 3D con filtro di Kalman, il riconoscimento biometrico asincrono (volti e targhe ALPR), la registrazione NVR dual-tier senza transcodifica, l'aggregazione di episodi scena (`SceneEvent`) con snapshot annotati, la valutazione reattiva di automazioni spaziali 2.5D e l'autenticazione RBAC integrata con Home Assistant e Caddy.

---

## 1. Stack Tecnologico e Rete

| Componente | Tecnologia / Versione (`requirements.txt`) | Ruolo |
| :--- | :--- | :--- |
| **API & ASGI** | `fastapi>=0.115.0`, `uvicorn[standard]>=0.30.0`, `pydantic>=2.9.0` | Server HTTP REST & WebSocket `/ws/spatial`, validazione schemi |
| **Computer Vision 2D** | `openvino>=2024.4.0` (opzionale via setup), `onnxruntime>=1.20.0,<2.0.0`, `opencv-python-headless>=4.10.0` | Inferenza YOLOv8n su RTSP sub-stream, fallback ONNX Runtime / HOG |
| **Geometria & Ottica 3D** | `trimesh>=4.4.0`, `rtree>=1.3.0`, `numpy>=1.26.0`, `scipy>=1.13.0` | Raycasting su mesh `house_optimized.glb`, SolvePnPRansac, associazione ungherese |
| **Biometria (Face & ALPR)** | `onnxruntime>=1.20.0,<2.0.0`, `open-image-models[onnx]>=0.4.0`, `fast-plate-ocr[onnx]>=1.0.0` | SCRFD + MobileFaceNet/ResNet50 ArcFace, YOLOv9-tiny + CCT-XS/MobileViT OCR |
| **NVR Dual-Tier** | `av>=13.0.0` (PyAV / FFmpeg muxer), `psutil>=6.0.0` | Demux/remux H.264/HEVC/AAC zero-transcode (`movflags=+faststart`) |
| **Persistenza & Stato** | `sqlite3` (stdlib, `WAL` + estensione `rtree`) | Storico traiettorie 3D, eventi biometrici, episodi, automazioni, indice NVR |
| **Integrazioni & Auth** | `aiomqtt>=2.2.0`, `httpx>=0.27.0`, `websockets>=12.0`, `python-dotenv>=1.0.1` | Bridge H24 verso Home Assistant, MQTT Discovery, proxy snapshot, HMAC auth |
| **Testing** | `pytest>=8.3.0` | Suite di test unitari, persistenza, sicurezza, NVR, biometria e automazioni |

### Porte e Topologia di Rete

- **Bind predefinito (`SPATIAL_SERVER_HOST:SPATIAL_SERVER_PORT`):** `127.0.0.1:8765` (solo loopback).
- **Esposizione in produzione:** `spatial_server` non viene mai esposto direttamente su LAN o Internet; tutto il traffico browser/PWA passa tramite **Caddy** (`127.0.0.1:8080`, configurato in [caddy/Caddyfile](../caddy/Caddyfile)) e **Tailscale Serve** (`https://<nodo>.<tailnet>.ts.net:443`).
- **Dipendenze locali su loopback:**
  - **go2rtc API HTTP:** `http://127.0.0.1:1984` (`GO2RTC_HTTP_BASE_URL`) per snapshot ad alta risoluzione (`/api/frame.jpeg?src=...`).
  - **go2rtc RTSP:** `rtsp://127.0.0.1:8554` (`GO2RTC_RTSP_BASE_URL`) per i sub-stream OpenVINO e gli stream Sub/Main NVR.
  - **Caddy `forward_auth`:** Caddy interroga `http://127.0.0.1:8765/api/v1/auth/verify` prima di inoltrare le richieste a `/go2rtc/api/webrtc*` e `/go2rtc/api/ws*`.

---

## 2. Setup Ambiente `.venv`, Modelli AI, Avvio e Test

### 2.1 Setup Automatico (Consigliato su Windows 10/11)

Lo script [scripts/setup_windows_node.ps1](../scripts/setup_windows_node.ps1) crea automaticamente il virtualenv `.venv`, installa le dipendenze di [requirements.txt](./requirements.txt) e, tramite switch dedicati, scarica i binari nativi (`go2rtc`, `caddy`, `nssm`) e i modelli AI:

```powershell
# Setup base + runtime OpenVINO + download/conversione YOLOv8n FP16 + modelli biometrici ONNX
powershell -ExecutionPolicy Bypass -File scripts/setup_windows_node.ps1 -WithOpenVINO -WithBiometrics

# In produzione, per registrare anche i servizi Windows NSSM e le regole firewall WebRTC (:8555):
powershell -ExecutionPolicy Bypass -File scripts/setup_windows_node.ps1 -WithOpenVINO -WithBiometrics -InstallServices -LanCidr 192.168.86.0/24
```

### 2.2 Setup Manuale e Download Modelli

```powershell
# 1. Creazione e attivazione virtualenv dalla root del repository
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r spatial_server/requirements.txt

# 2. (Opzionale ma consigliato) Runtime OpenVINO per YOLOv8n su CPU/iGPU Intel HD 530
.\.venv\Scripts\python.exe -m pip install "openvino>=2024.4.0"

# 3. Download YOLOv8n ONNX e conversione in OpenVINO IR FP16 (spatial_server/models/yolov8n_openvino_model/)
.\.venv\Scripts\python.exe tools/download_yolo_openvino_model.py

# 4. Download modelli biometrici ONNX + manifest.json (spatial_server/models/biometrics/)
.\.venv\Scripts\python.exe tools/download_biometric_models.py

# 5. Enrollment galleria volti familiari (.npz) con validazione Leave-One-Out
.\.venv\Scripts\python.exe tools/enroll_faces.py
```

### 2.3 Comandi di Avvio (Sviluppo e Produzione)

Configurare prima il file `.env` nella root del repository partendo da [.env.example](../.env.example).

#### Sviluppo locale (terminale console)

Impostare `SH3D_DEV_MODE=true` in `.env` (per CORS automatico verso `localhost:3000/5173/8080` e override `*_DEV` opzionali), quindi avviare dalla root del repository:

```powershell
# Avvio diretto Uvicorn con hot-reload (solo sviluppo)
.\.venv\Scripts\uvicorn.exe spatial_server.main:app --host 127.0.0.1 --port 8765 --reload
```

Oppure avviare l'intero stack locale (`go2rtc` + `spatial_server` + `Caddy`) in console con:

```bat
scripts\start_services.bat
```

#### Produzione Windows (Servizi NSSM)

In produzione (`SH3D_DEV_MODE=false`, `SPATIAL_AUTH_REQUIRED=true`), il servizio viene registrato come servizio Windows **NSSM** denominato `SmartHome3D-SpatialServer` tramite [scripts/install_windows_services.ps1](../scripts/install_windows_services.ps1) (eseguito come Amministratore):

- **Comando registrato:** `.venv\Scripts\uvicorn.exe spatial_server.main:app --host 127.0.0.1 --port 8765`
- **Dipendenza:** `SmartHome3D-go2rtc`
- **Thread tuning:** imposta `OMP_NUM_THREADS=2` se non valorizzato, per non saturare i 4 core della CPU (es. `i5-6400`) condivisi con la VM Home Assistant.
- **Gestione ciclo di vita:** [scripts/start_services.bat](../scripts/start_services.bat), [scripts/stop_services.bat](../scripts/stop_services.bat) e [scripts/update_services.bat](../scripts/update_services.bat) (con log rotativi a 5 MB in `logs/spatial_server.stdout.log` e `logs/spatial_server.stderr.log`).

### 2.4 Esecuzione Test (`pytest` e runner pipeline)

```powershell
# Esecuzione completa della suite pytest (50 test)
.\.venv\Scripts\pytest.exe spatial_server/tests -v

# Esecuzione mirata per singolo sottosistema
.\.venv\Scripts\pytest.exe spatial_server/tests/test_security_auth.py -v
.\.venv\Scripts\pytest.exe spatial_server/tests/test_biometrics_unit.py -v
.\.venv\Scripts\pytest.exe spatial_server/tests/test_nvr_dual_tier.py -v

# Runner standalone end-to-end (ottica, OpenVINO letterbox, Trimesh raycaster, Kalman multi-cam, SQLite, REST/WS)
.\.venv\Scripts\python.exe spatial_server/tests/verify_pipeline.py
```

---

## 3. Mappa Completa dei Package e Moduli

| Percorso | Ruolo principale |
| :--- | :--- |
| [main.py](./main.py) | Entrypoint FastAPI (`create_app`, `app`), orchestratore `SpatialPipelineService`, lifespan, 55 route REST e `/ws/spatial` |
| [config.py](./config.py) | `SpatialServerConfig.from_env()`: parsing tipizzato e validato di tutte le variabili `.env` |
| [requirements.txt](./requirements.txt) | Dipendenze Python del microservizio |
| [__init__.py](./__init__.py) | Marker package `spatial_server` |
| **Domain** | |
| [domain/__init__.py](./domain/__init__.py) | Export pubblici del dominio |
| [domain/models.py](./domain/models.py) | Modelli Pydantic `BoundingBox2D`, `DetectionEvent`, `Ray3D`, `SpatialPoint3D`, `TrackedEntity3D`, `CalibrationOverridePayload`, `PnPCorrespondence`, `SolvePnPRequest` |
| **Ingestion** | |
| [ingestion/__init__.py](./ingestion/__init__.py) | Export interfacce e sorgenti |
| [ingestion/interfaces.py](./ingestion/interfaces.py) | `IDetectionSource`, `DetectionBatchCallback` |
| [ingestion/openvino_rtsp_source.py](./ingestion/openvino_rtsp_source.py) | `OpenVINORtspDetectionSource` (OpenVINO IR / ORT / Ultralytics / HOG), letterbox 640×640, `deduplicate_2d_detections` |
| [ingestion/mqtt_source.py](./ingestion/mqtt_source.py) | `MqttFrigateDetectionSource` per eventi Frigate (`frigate/events`) o JSON flat con mappa alias telecamere |
| [ingestion/synthetic_source.py](./ingestion/synthetic_source.py) | `SyntheticWalkSimulatorSource` (simulatore 10 Hz persona + auto per test senza movimento reale) |
| **Optics** | |
| [optics/__init__.py](./optics/__init__.py) | Export modelli ottici e solver |
| [optics/interfaces.py](./optics/interfaces.py) | Interfaccia `ICameraOpticalModel` |
| [optics/pinhole_model.py](./optics/pinhole_model.py) | `PinholeRadTanOpticalModel` (Brown-Conrady 5 coeff.), `matrix_gl_to_cv`, `matrix_cv_to_gl` |
| [optics/panoramic_model.py](./optics/panoramic_model.py) | `EquirectangularPanoramicOpticalModel` per camere 180° (Reolink Duo 3 PoE) |
| [optics/calibration_solver.py](./optics/calibration_solver.py) | `create_optical_model_from_manifest`, `CameraCalibrationSolver` (`solve_pnp_ransac`, override atomici su `camera_calibrations.json`) |
| **Geometry** | |
| [geometry/__init__.py](./geometry/__init__.py) | Export raycaster |
| [geometry/interfaces.py](./geometry/interfaces.py) | Interfaccia `ISpatialRaycaster` |
| [geometry/raycaster.py](./geometry/raycaster.py) | `TrimeshGroundRaycaster`, `GroundHitResult` (mesh `ground_colliders` da `house_optimized.glb` + fallback piano `Y=0`) |
| **Tracking** | |
| [tracking/__init__.py](./tracking/__init__.py) | Export tracker 3D |
| [tracking/interfaces.py](./tracking/interfaces.py) | `IMultiTargetTracker3D`, `TrackObservation3D` |
| [tracking/kalman_tracker.py](./tracking/kalman_tracker.py) | `Kalman3DMultiTracker`, `_KalmanTrack`, fusione multi-camera anti-ping-pong, matching ungherese a 2 stadi, cap di cardinalità logica |
| **Biometrics** | |
| [biometrics/__init__.py](./biometrics/__init__.py) | Export completi del sottosistema biometrico |
| [biometrics/models.py](./biometrics/models.py) | `BiometricJob`, `CropPayload`, `FaceQualityMetrics`, `FaceEvaluation`, `PlateQualityMetrics`, `PlateNormalizedResult`, `PlateEvaluation`, `PlateWhitelistEntry`, `TrackBiometricUpdate` |
| [biometrics/interfaces.py](./biometrics/interfaces.py) | `IIdentityResolver`, `IFrameSnapshotProvider`, `IFaceRecognizer`, `IPlateRecognizer`, `IBiometricCoordinator` |
| [biometrics/worker.py](./biometrics/worker.py) | `TrackCoalescingQueue`, `BiometricEligibilityGate`, `BiometricWorkerService` |
| [biometrics/snapshot_provider.py](./biometrics/snapshot_provider.py) | `Go2RtcSnapshotProvider`, `parse_jpeg_dimensions`, `decode_and_crop_jpeg` (circuit-breaker + fallback substream + decode half-res 16MP) |
| [biometrics/face_pipeline.py](./biometrics/face_pipeline.py) | `OnnxInsightFaceRecognizer` (SCRFD + Quality Gate + allineamento ArcFace 112×112 + embedding 512-D) |
| [biometrics/alpr_pipeline.py](./biometrics/alpr_pipeline.py) | `OnnxAlprRecognizer` (YOLOv9-tiny + Quality Gate anti-glare + CLAHE + `fast-plate-ocr`) |
| [biometrics/plate_postprocessor.py](./biometrics/plate_postprocessor.py) | `normalize_and_validate_plate`, `levenshtein_distance`, `PlateWhitelistMatcher` |
| [biometrics/face_gallery.py](./biometrics/face_gallery.py) | `FaceGalleryIndex`, `FaceGalleryMatch` (centroidi + K rappresentativi diversi su `.npz`) |
| [biometrics/crop_store.py](./biometrics/crop_store.py) | `BiometricCropStore` (salvataggio atomico miglior thumbnail JPEG + pruning retention/quota) |
| [biometrics/consensus.py](./biometrics/consensus.py) | `TrackBiometricConsensusManager` (voto pesato multi-frame, locking a K conferme, backoff `unknown`) |
| [biometrics/resolvers.py](./biometrics/resolvers.py) | `NoOpIdentityResolver`, `OpenVINOInsightFaceResolver`, `ExternalWebhookIdentityResolver` |
| [biometrics/onnx_runtime_utils.py](./biometrics/onnx_runtime_utils.py) | `build_ort_session_options`, `resolve_ort_providers`, `create_ort_session` |
| **Events** | |
| [events/__init__.py](./events/__init__.py) | Export sottosistema episodi |
| [events/models.py](./events/models.py) | `SceneEventRecord`, `SceneSubjectRecord`, `FrameBoxAnnotation`, `generate_event_id`, `is_valid_event_id` |
| [events/manager.py](./events/manager.py) | `SceneEventManager` (episodi con inerzia, ranking fotogramma migliore, re-annotazione HITL, arricchimento NVR) |
| [events/annotator.py](./events/annotator.py) | `annotate_scene_frame_bgr`, `EventSnapshotStore` (`_raw.jpg` e `_ann.jpg`) |
| [events/narrator.py](./events/narrator.py) | `build_scene_sentence_it`, `build_scene_title_it`, `format_location_it` |
| [events/signing.py](./events/signing.py) | `SignedMediaTokenService` (URL HMAC-SHA256 a scadenza per notifiche mobile/display) |
| **Automations** | |
| [automations/__init__.py](./automations/__init__.py) | Export motore automazioni |
| [automations/models.py](./automations/models.py) | `Point2D`, `SpatialZoneDefinition`, `VirtualEntityDefinition`, `SubjectFilterSpec`, `TriggerSpec`, `ConditionSpec`, `ActionSpec`, `AutomationRuleDefinition`, `AutomationExecutionLog` |
| [automations/geometry.py](./automations/geometry.py) | `SpatialGeometryEngine`, `PerimeterCrossingEvent` (ray-casting 2D/2.5D con isteresi + intersezione segmenti orientati) |
| [automations/kinematics.py](./automations/kinematics.py) | `TrackKinematicHistoryBuffer`, `KinematicSample`, `ZonePresenceState`, `ZoneTransitionEvent`, `WindowKinematicMetrics`, `TrackStepEvents` |
| [automations/astronomy.py](./automations/astronomy.py) | `AstronomicalClock` (equazioni solari NOAA alba/tramonto) |
| [automations/evaluators.py](./automations/evaluators.py) | `SubjectFilterEvaluator`, `TriggerRegistry` (8 evaluator), `ConditionEvaluator` (AST booleano) |
| [automations/engine.py](./automations/engine.py) | `AutomationEngineService` (late biometric binding, esecutore azioni, notifiche bundle, template `{{...}}`) |
| **Recordings (NVR)** | |
| [recordings/__init__.py](./recordings/__init__.py) | Export sottosistema NVR |
| [recordings/interfaces.py](./recordings/interfaces.py) | `RecordingSegmentRecord`, `PlaybackResolutionRecord`, `EncodedPacket`, `StreamMetadata`, `GopChunk`, `SegmentWriteResult`, `IMediaPacketSource`, `IMediaSegmentWriter`, `INvrSegmentIndex`, `IVideoArchiveRepository`, `IDualTierRecorderCoordinator` |
| [recordings/media_backend.py](./recordings/media_backend.py) | `PyAvRtspPacketSource`, `PyAvMp4SegmentWriter`, `is_pyav_available` |
| [recordings/ring_buffer.py](./recordings/ring_buffer.py) | `CompressedGopRingBuffer` (pre-roll RAM allineato a GOP IDR) |
| [recordings/sqlite_index.py](./recordings/sqlite_index.py) | `SQLiteNvrIndexStore` (indice WAL `nvr_index.db`, switch zero-gap Sub↔Main, fallback HEVC→H.264) |
| [recordings/filesystem_nvr.py](./recordings/filesystem_nvr.py) | `FilesystemNvrArchiveRepository` (riconciliazione dischi e parser nomi file) |
| [recordings/retention.py](./recordings/retention.py) | `DiskRetentionManager`, `RetentionSweepReport` (scadenze differenziate + guardia spazio libero) |
| [recordings/recorder_service.py](./recordings/recorder_service.py) | `CameraRecordingProfile`, `MainEventStateMachine`, `SubStreamContinuousWorker`, `MainStreamEventWorker`, `CameraDualTierRecorder`, `DualTierNvrRecorderCoordinator` |
| **Integrations** | |
| [integrations/__init__.py](./integrations/__init__.py) | Export bridge esterni |
| [integrations/ha_bridge.py](./integrations/ha_bridge.py) | `HomeAssistantBridgeService` (WebSocket H24 `HA_TOKEN`, state mirroring, auto-discovery, REST `call_service`, eventi bottoni push) |
| [integrations/mqtt_bridge.py](./integrations/mqtt_bridge.py) | `HomeAssistantMqttBridge` (MQTT Discovery `camera.sh3d_ultimo_evento` e `select.sh3d_allarme`) |
| **Persistence & Security** | |
| [persistence/__init__.py](./persistence/__init__.py) | Export repository |
| [persistence/interfaces.py](./persistence/interfaces.py) | Interfaccia `ITrackRepository` |
| [persistence/repository.py](./persistence/repository.py) | `SQLiteWALTrackRepository` (schema completo 10 tabelle + R-Tree `track_spatial_idx`) |
| [security/__init__.py](./security/__init__.py) | Export modulo autenticazione |
| [security/ha_auth.py](./security/ha_auth.py) | `HomeAssistantAuthVerifier`, `HAUserPrincipal`, cookie HMAC `sh3d_session`, dipendenze `require_authenticated_user`, `require_admin_user`, `authenticate_websocket` |
| **Modelli, Dati e Test** | |
| [models/biometrics/manifest.json](./models/biometrics/manifest.json) | Manifest SHA-256 e metadati I/O tensori ONNX dei modelli Face e ALPR |
| [tests/](./tests/) | 8 suite `test_*.py` + script E2E [verify_pipeline.py](./tests/verify_pipeline.py) |

---

## 4. Catalogo Completo degli Endpoint HTTP REST e WebSocket

Tutti gli endpoint sono definiti dentro `create_app()` in [main.py](./main.py).
Legenda RBAC:
- **Public / Token**: non richiede sessione pregressa (valida credenziali nella richiesta stessa, es. Bearer HA o firma HMAC URL).
- **Utente (`require_authenticated_user`)**: richiede cookie `sh3d_session` valido oppure header `Authorization: Bearer <ha_token>` (sia Residenti che Admin/Owner; se `SPATIAL_AUTH_REQUIRED=false` restituisce `synthetic_local_admin_principal`).
- **Admin (`require_admin_user`)**: richiede `principal.is_privileged == True` (`is_admin=True` oppure `is_owner=True` su Home Assistant); i Residenti ricevono `403 Forbidden`.

### 4.1 Autenticazione & Forward-Auth

| Metodo | Path | Auth / RBAC | Scopo e dettagli |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/session` | Bearer HA / body `{"token": "..."}` | Verifica il token OAuth2 su Home Assistant ed emette il cookie HMAC `sh3d_session` (`HttpOnly`, `SameSite=Strict`). |
| `GET` | `/api/v1/auth/verify` | Utente | Verifica sessione corrente; usato anche da Caddy `forward_auth` per proteggere `/go2rtc/*`. Restituisce header `X-SH3D-User` e `X-SH3D-Admin`. |
| `POST` | `/api/v1/auth/logout` | Public | Elimina il cookie `sh3d_session` (`clear_session_cookie`). |

### 4.2 Stato Sistema, Storico Tracce 3D e Timeline

| Metodo | Path | Auth / RBAC | Scopo e dettagli |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/status` | Utente | Diagnostica completa: `dev_mode`, `ingestion_mode`, `source_details`, `active_cameras`, `ground_colliders_count`, `ground_triangles_count`, `sqlite_journal_mode`, `sqlite_has_rtree`, `active_tracks_count`, `connected_clients`, contatori persistenza/raycast, `biometrics`, `nvr`, `ha_bridge`, `events`. |
| `GET` | `/api/v1/tracks` | Utente | Query storico tracce su `[t_start, t_end]` (obbligatori). Filtri: `classes` (CSV), `min_x`, `max_x`, `min_z`, `max_z` (usa `track_spatial_idx` R-Tree), `limit` (`1..20000`, default `5000`), `identity`, `plate`, `unknown_only`. |
| `GET` | `/api/v1/timeline-density` | Utente | Istogramma attività su `[t_start, t_end]` diviso in `buckets` (`5..360`, default `60`). |

### 4.3 Biometria (Face Recognition, ALPR e Revisione HITL)

| Metodo | Path | Auth / RBAC | Scopo e dettagli |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/biometrics/status` | Utente | Diagnostica `BiometricWorkerService`, stato circuit-breaker snapshot per camera, conteggi galleria/whitelist e uso disco crop. |
| `GET` | `/api/v1/biometrics/events` | Utente | Query su `biometric_events` con filtri `t_start`, `t_end`, `modality`, `status`, `identity`, `plate`, `track_id`, `limit` (`1..1000`, default `100`). Espone `crop_url` sanitizzato senza path disco interni. |
| `GET` | `/api/v1/biometrics/crops/{crop_id}` | Utente | Restituisce il JPEG del miglior crop (`FileResponse`, `Cache-Control: private, max-age=300`, `X-Content-Type-Options: nosniff`). Valida `crop_id` (`^[a-zA-Z0-9_-]{8,64}$`). |
| `GET` | `/api/v1/biometrics/identities` | Utente | Elenco persone iscritte unendo `FaceGalleryIndex` (`.npz`) e metadati SQLite (`face_embeddings` + `biometric_events`). |
| `GET` | `/api/v1/biometrics/plates` | Utente | Elenco targhe autorizzate da SQLite `plate_whitelist`. |
| `POST` | `/api/v1/biometrics/events/{event_id}/assign` | **Admin** | Revisione HITL (`BiometricEventAssignRequest`): assegna identità volto (ed estrae/arruola embedding dal crop se `enroll_crop=true`) oppure targa ALPR (opzionalmente aggiungendo a `plate_whitelist`), esegue backfill su `track_history` (`event_ts - 600s`), aggiorna tracker, `SceneEventManager` e `AutomationEngineService`. |
| `POST` | `/api/v1/biometrics/identities/reload` | **Admin** | Ricarica da disco il file `face_gallery*.npz` in memoria senza riavviare il server. |
| `DELETE` | `/api/v1/biometrics/identities/{person_name}` | **Admin** | Elimina una persona sia da `FaceGalleryIndex` (`.npz`) sia da `face_embeddings` SQLite. |
| `PUT` | `/api/v1/biometrics/plates` | **Admin** | Crea o aggiorna una targa in `plate_whitelist` (`PlateWhitelistUpsertRequest`) e sincronizza `PlateWhitelistMatcher` + `plates_whitelist.json`. |
| `DELETE` | `/api/v1/biometrics/plates/{plate}` | **Admin** | Rimuove la targa normalizzata dalla whitelist SQLite e risincronizza matcher e JSON. |
| `POST` | `/api/v1/biometrics/crops/prune` | **Admin** | Forza pruning manuale di `biometric_events` scaduti e crop JPEG oltre retention/quota (`BIOMETRICS_CROP_RETENTION_DAYS`, `BIOMETRICS_CROP_MAX_MB`). |

### 4.4 Episodi Scena (`SceneEvent`), Snapshot Cover e Media Firmati

| Metodo | Path | Auth / RBAC | Scopo e dettagli |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/events` | Utente | Lista episodi scena (`t_start`, `t_end`, `importance`, `camera_id`, `zone_id`, `identity`, `plate`, `unknown_only`, `subject_class`, `limit` `1..500`), arricchiti con `has_video_clip` e `has_hd_clip` dall'archivio NVR. |
| `GET` | `/api/v1/events/{event_id}` | Utente | Dettaglio singolo `SceneEventRecord` (validato `is_valid_event_id`) arricchito con stato clip NVR. |
| `DELETE` | `/api/v1/events/{event_id}` | **Admin** | Cancella episodio da `scene_events` e rimuove i relativi JPEG `_raw.jpg` e `_ann.jpg`. |
| `POST` | `/api/v1/events/maintenance/prune` | **Admin** | Forza la pulizia di episodi e snapshot oltre `SPATIAL_EVENTS_RETENTION_DAYS` e `SPATIAL_EVENTS_SNAPSHOT_MAX_MB`. |
| `GET` | `/api/v1/events/{event_id}/cover.jpg` | Utente | Snapshot JPEG originale (`raw`) della cover migliore dell'episodio. |
| `GET` | `/api/v1/events/{event_id}/annotated.jpg` | Utente | Snapshot JPEG annotato (`annotated`) con bounding box e pill etichette (fallback a `raw` se assente). |
| `GET` | `/api/v1/events/{event_id}/media/{variant}.jpg` | **Signed HMAC** (`exp`, `sig`) | Accesso senza cookie destinato alle notifiche mobile/TV/Nest Hub (`variant` in `raw` \| `annotated`); verifica firma HMAC-SHA256 e TTL via `SignedMediaTokenService`. |

### 4.5 Registrazione Video NVR Dual-Tier

| Metodo | Path | Auth / RBAC | Scopo e dettagli |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/recordings/status` | Utente | Stato configurazione storage NVR, elenco camere, statistiche `nvr_index.db` e diagnostica `DualTierNvrRecorderCoordinator`. |
| `GET` | `/api/v1/recordings/{camera_id}/segments` | Utente | Segmenti MP4 indicizzati in `[t_start, t_end]`, filtro opzionale `tier` (`sub` \| `main`). |
| `GET` | `/api/v1/recordings/{camera_id}/resolve` | Utente | Risolve istante `t` (`prefer_tier="main"`, `allow_hevc=true`) con priorità `main > sub`, lookahead zero-gap (`switch_at_unix`, `next_segment`, `next_seek_offset_sec`) e fallback H.264 automatico se HEVC non supportato. |
| `POST` | `/api/v1/recordings/{camera_id}/trigger` | **Admin** | Attiva registrazione manuale sul Main Stream (`NvrTriggerRequest.duration_sec` clampata in `2.0..300.0`s). |
| `POST` | `/api/v1/recordings/maintenance/prune` | **Admin** | Forza `reconcile_with_filesystem(force=True)` + `DiskRetentionManager.sweep()`. |
| `GET` | `/api/v1/recordings/{camera_id}/file/{filename}` | Utente | Streaming/download sicuro del segmento video (`video/mp4`, `video/webm`, `video/x-matroska`). |

### 4.6 Calibrazione Ottica Telecamere e SolvePnPRansac

| Metodo | Path | Auth / RBAC | Scopo e dettagli |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/calibrations` | Utente | Metadati di calibrazione correnti di tutte le telecamere registrate (`is_calibrated`, `fov_*`, `distortion_coeffs`, `extrinsic_cv_to_world`, `matrix_world_gl`, `ui_state`). |
| `GET` | `/api/v1/calibration/{camera_id}` | Utente | Metadati di calibrazione per la singola telecamera (`404` se non registrata). |
| `POST` | `/api/v1/calibration/solve-pnp` | **Admin** | Esegue `cv2.solvePnPRansac` con >= 4 corrispondenze 3D↔2D (`SolvePnPRequest`) su camere `PinholeRadTanOpticalModel`, aggiorna modello live, salva override e trasmette `calibration_updated`. |
| `POST` | `/api/v1/calibration/{camera_id}` | **Admin** | Applica override live (`CalibrationOverridePayload`: `calibrated_matrix_world_gl` 16 float row-major, `fov_h_deg`, `fov_v_deg`, `distortion_coeffs`, `ui_state`), persiste su `camera_calibrations.json` e trasmette `calibration_updated`. |
| `DELETE` | `/api/v1/calibration/{camera_id}` | **Admin** | Rimuove l'override persistito e ripristina il modello ottico dal manifesto SSoT `scene_manifest.json`. |

### 4.7 Automazioni Spaziali 2.5D, Zone, Entità Virtuali e Log

| Metodo | Path | Auth / RBAC | Scopo e dettagli |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/automations/bootstrap` | Utente | Stato completo per Automation Studio: `zones`, `virtual_entities`, `rules`, ultimi 60 `logs`, `sun` (alba/tramonto NOAA), `identities`, `plates`, `cameras`, `ha_discovery`. |
| `GET` | `/api/v1/automations/ha-discovery` | Utente | Riepilogo entità `notify.*`, `media_player.*`, `tts.*`, `switch/light/lock/cover/script/button.*` scoperte dal bridge HA. |
| `GET` | `/api/v1/automations/zones` | Utente | Elenco zone poligonali 2.5D e perimetri orientati. |
| `PUT` | `/api/v1/automations/zones` | **Admin** | Crea o aggiorna `SpatialZoneDefinition` e trasmette `automation_zones_updated`. |
| `DELETE` | `/api/v1/automations/zones/{zone_id}` | **Admin** | Elimina una zona/perimetro (`404` se inesistente). |
| `GET` | `/api/v1/automations/virtual-entities` | Utente | Elenco entità virtuali interne `sh3d.*` (es. `sh3d.allarme`). |
| `PUT` | `/api/v1/automations/virtual-entities` | **Admin** | Crea o aggiorna la definizione completa di `VirtualEntityDefinition`. |
| `POST` | `/api/v1/automations/virtual-entities/{entity_id}/state` | **Utente** | Cambia stato (`VirtualEntityStateChangeRequest`: `state`, `operation` tra `set`/`turn_on`/`turn_off`/`toggle`/`increment`, `attributes`); accessibile anche ai Residenti per armare/disarmare `sh3d.allarme`. |
| `DELETE` | `/api/v1/automations/virtual-entities/{entity_id}` | **Admin** | Elimina entità virtuale `sh3d.*`. |
| `GET` | `/api/v1/automations/rules` | Utente | Elenco regole ECA (`AutomationRuleDefinition`). |
| `PUT` | `/api/v1/automations/rules` | **Admin** | Crea o aggiorna una regola ECA e azzera il suo runtime state in memoria. |
| `POST` | `/api/v1/automations/rules/{rule_id}/toggle` | **Admin** | Abilita/disabilita rapidamente una regola (`{"enabled": true|false}`). |
| `POST` | `/api/v1/automations/rules/{rule_id}/trigger` | **Admin** | Esegue manualmente tutte le azioni di una regola (`manual_test`). |
| `DELETE` | `/api/v1/automations/rules/{rule_id}` | **Admin** | Elimina una regola dal DB e dalla memoria. |
| `GET` | `/api/v1/automations/logs` | Utente | Cronologia esecuzioni (`rule_id` opzionale, `limit` `1..500`, default `80`). |
| `DELETE` | `/api/v1/automations/logs` | **Admin** | Svuota la tabella `automation_logs`. |
| `POST` | `/api/v1/automations/ha-states` | Utente | Sincronizza dal frontend un batch di stati Home Assistant (`HaStatesSyncRequest`: `entities`, `trigger_on_diff`). |

### 4.8 Ingestione, Test Manuale e Proxy Snapshot HA

| Metodo | Path | Auth / RBAC | Scopo e dettagli |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/ingestion/mode` | **Admin** | Commuta a caldo `IngestionModeRequest.mode` tra `"synthetic"`, `"openvino"`, `"mqtt"`, `"hybrid"`. |
| `POST` | `/api/v1/detections` | **Admin** | Inietta uno o più `DetectionEvent` HTTP nella pipeline completa (raycast → Kalman → persistenza → eventi → automazioni). |
| `GET` | `/api/v1/ha-camera/snapshot/{entity_id}` | Utente | Proxy autenticato verso `<ha_base>/api/camera_proxy/{entity_id}` (regex `^camera\.[a-zA-Z0-9_]+$` + allowlist origini anti-SSRF su `ha_local_url`, `ha_tailscale_url`, `ha_public_url`, query opzionale `ha_url`). |

### 4.9 Protocollo WebSocket `WS /ws/spatial`

L'handshake WebSocket in [main.py](./main.py) verifica l'autenticazione tramite `authenticate_websocket` (cookie `sh3d_session` o header `Authorization: Bearer`) quando `SPATIAL_AUTH_REQUIRED=true`; in caso di credenziali mancanti o invalide chiude immediatamente con codice `4401` (`"Unauthorized"`).

- **Messaggi Client → Server:**
  - Stringa `"ping"` → risposta testuale `"pong"`.
  - JSON `{"type": "ha_states_sync", "entities": {...}, "trigger_on_diff": true}` → aggiorna `AutomationEngineService.sync_ha_states_batch(...)`.
- **Messaggi Server → Client (JSON broadcast a tutti i client connessi):**
  - `server_status`: inviato subito dopo `accept()` e a ogni cambio di modalità (`ingestion_mode`, `active_cameras`).
  - `spatial_frame`: stream real-time a frequenza di batch (`timestamp`, `ingestion_mode`, `active_tracks: list[TrackedEntity3D]`).
  - `biometric_event`: risultato consenso/lock/unknown o review HITL (`event_id`, `track_id`, `modality`, `identity`, `plate`, `plate_whitelisted`, `plate_owner`, `biometric_locked`, `biometric_status`, `best_crop_id`, `crop_url`, `quality_score`).
  - `scene_event_updated`: creazione/aggiornamento/chiusura episodio (`event`: `SceneEventRecord.to_api_dict()`).
  - `calibration_updated`: aggiornamento calibrazione o reset (`camera_id`, `calibration`).
  - `automation_zones_updated`, `virtual_entity_updated`, `virtual_entities_list`, `automation_rules_updated`: sincronizzazione live CRUD Automation Studio.
  - `automation_triggered`: notifica esecuzione regola (`log`, `rule_id`, `trigger_count`, `last_triggered_at`).
  - `automation_ui_alert`: banner/avviso sonoro in UI 3D (`title`, `message`, `severity`, `sound`, `zone_id`, `camera_id`, `track_id`).
  - `automation_ha_service_call`: fallback verso browser solo quando né `HomeAssistantBridgeService` né `HA_TOKEN` backend sono disponibili.

---

## 5. Database SQLite e Persistenza su Disco

### 5.1 Database Principale: `spatial_server/data/spatial_tracks.db`

Gestito da [SQLiteWALTrackRepository](./persistence/repository.py) con:
- `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, `PRAGMA temp_store=MEMORY;`, `PRAGMA cache_size=-4000;`
- Scritture batch transazionali ogni `0.5s` da `_db_flush_loop` (con deduplicazione dei target stazionari tramite `_PersistAnchor`: salva solo se spostamento `>= 0.15m`, heartbeat `>= 10.0s`, o variazione di `identity`/`plate`/`biometric_locked`/`class_label`).
- Pulizia automatica ogni `3600s` + `PRAGMA wal_checkpoint(TRUNCATE);`.

| Tabella / Virtual Table | Scopo |
| :--- | :--- |
| `track_history` | Serie temporale delle posizioni 3D `(x, y, z)`, velocità `(vx, vy, vz)`, `camera_sources`, confidenze, `identity`, `plate`, `plate_whitelisted`, `plate_owner`, `biometric_locked`, `best_crop_id`. |
| `track_spatial_idx` (`VIRTUAL TABLE ... USING rtree`) | Indice R-Tree 2D `(id, min_x, max_x, min_z, max_z)` con padding ±`0.25m` per query spaziali rapide su aree (fallback automatico a indice B-Tree `idx_track_xz` se SQLite locale è compilato senza R-Tree). |
| `identities` | Tabella legacy identità (`name`, `embedding_blob`, `updated_at`, `notes`). |
| `biometric_events` | Log deduplicato per `(track_id, modality)` entro finestra 3600s di tutti gli esiti biometrici (`locked` / `unknown`), con `best_crop_id`, `best_crop_relpath` e campi HITL (`reviewed_by`, `reviewed_at`). |
| `face_embeddings` | Campioni vettoriali float32 (`embedding_blob`) arruolati via HITL o enrollment, associati a `person_name` e `model_name`. |
| `plate_whitelist` | Targhe autorizzate (`plate` PK normalizzata, `owner_name`, `vehicle_label`, `notes`, `updated_at`), sincronizzate con `plates_whitelist.json`. |
| `spatial_zones` | Definizioni JSON delle zone poligonali 2.5D e dei perimetri orientati. |
| `virtual_entities` | Entità virtuali interne `sh3d.*` (inclusa `sh3d.allarme`) con stato corrente. |
| `automation_rules` | Regole ECA complete (`triggers`, `condition`, `actions`, `cooldown_s`, `execution_mode`). |
| `automation_logs` | Audit trail delle esecuzioni delle regole (`trigger_type`, `actions_executed`, `status`). |
| `scene_events` | Episodi multi-camera indicizzati per `started_at`, `importance`, `status`, testo ricercabile (`identities_text`, `plates_text`, `classes_text`) e path snapshot cover. |

### 5.2 Database Indice NVR: `<SPATIAL_NVR_STORAGE_DIR>/nvr_index.db`

Gestito da [SQLiteNvrIndexStore](./recordings/sqlite_index.py) sull'HDD CMR configurato in `SPATIAL_NVR_STORAGE_DIR` (es. `D:\Surveillance`):
- Modalità WAL (`PRAGMA journal_mode=WAL;`, `PRAGMA cache_size=-4000;`).
- Tabella `nvr_segments` con indici compositi `(camera_id, start_unix, end_unix)`, `(camera_id, stream_tier, start_unix, end_unix)`, `(stream_tier, start_unix)` e `(camera_id, filename)`.
- Struttura file video su disco: `<storage_dir>/<camera_id>/<YYYY-MM-DD>/<tier>_<start_unix:.3f>_<duration_sec:.3f>.mp4` (scrittura atomica via file `.tmp.mp4` con `movflags=+faststart`).

### 5.3 Altri Artefatti Persistenti in `spatial_server/data/`

- **`camera_calibrations.json`**: override persistenti dei parametri ottici ed estrinseci per telecamera, scritti atomicamente via `tempfile.mkstemp` + `os.replace` da [calibration_solver.py](./optics/calibration_solver.py).
- **`biometrics/face_gallery.npz` (oppure `face_gallery_mbf.npz` / `face_gallery_r50.npz`)**: galleria vettoriale compatta (`person_names`, `centroids`, `rep_embeddings`, `rep_person_idx`, `rep_qualities`).
- **`biometrics/plates_whitelist.json`**: mirror JSON della whitelist targhe, sincronizzato bidirezionalmente con la tabella `plate_whitelist` in SQLite all'avvio e a ogni operazione CRUD.
- **`biometrics/crops/YYYY-MM-DD/<crop_id>.jpg`**: un solo thumbnail JPEG (max 320px lato lungo, qualità 82) per traccia/evento biometrico (`crop_id = "<unix>_<track_id>_<modality>_<attempts>"`).
- **`events/snapshots/YYYY-MM-DD/<event_id>_{raw|ann}.jpg`**: coppie di immagini cover (originale ridimensionata max `1280px` e annotata con bounding box/etichette).

---

## 6. Autenticazione, Cookie HMAC e Ruoli RBAC

Implementata in [security/ha_auth.py](./security/ha_auth.py):

1. **Verifica Token Home Assistant (`HomeAssistantAuthVerifier.verify_token`):**
   - Accetta il Bearer token OAuth2 di Home Assistant (passato su `POST /api/v1/auth/session` o via header `Authorization: Bearer`).
   - Calcola `SHA-256(token)` e controlla prima la cache thread-safe in RAM (TTL default `SPATIAL_AUTH_CACHE_TTL_S=120.0`, max `1024` voci).
   - **Canale primario (WebSocket):** si connette a `<ha_url>/api/websocket` (provando in ordine `VITE_HA_LOCAL_URL`, `VITE_HA_TAILSCALE_URL`, `ha_public_url`), invia `{"type": "auth", "access_token": ...}` e poi `{"id": 1, "type": "auth/current_user"}` per ottenere `id`, `name`, `is_admin`, `is_owner`.
   - **Fallback fail-closed (REST):** se il WebSocket non è raggiungibile, tenta `GET <ha_url>/api/`, ma poiché tale endpoint non espone i ruoli utente forza `is_admin=False` e `is_owner=False` (impedendo l'accesso a qualsiasi route Admin).
2. **Cookie di Sessione `sh3d_session`:**
   - Formato: `<base64url(payload_json)>.<base64url(HMAC-SHA256)>` firmato con `SPATIAL_SESSION_SECRET` (se omesso viene generato in RAM a ogni avvio con `secrets.token_bytes(32)`, invalidando le sessioni al riavvio).
   - Payload `v=1`: `sub` (`user_id`), `name`, `adm` (`is_admin`), `own` (`is_owner`), `iat`, `exp` (TTL default `43200.0`s = 12 ore).
   - Attributi cookie: `HttpOnly`, `SameSite=Strict`, `Path=/`, e `Secure=True` automatico quando la richiesta è HTTPS o contiene `X-Forwarded-Proto: https` (dietro Tailscale Serve + Caddy).
3. **RBAC (Admin vs Residente):**
   - **Residente (`is_admin=False`, `is_owner=False`)**: può leggere stato, tracce, biometria, episodi, registrazioni NVR, calibrazioni, automazioni, modificare lo stato di entità virtuali (`POST /api/v1/automations/virtual-entities/{entity_id}/state`, es. allarme casa), usare il proxy snapshot HA e connettersi a `WS /ws/spatial`.
   - **Admin / Owner (`is_privileged=True`)**: abilitato in aggiunta a revisione biometrica HITL (`assign`), gestione galleria volti/whitelist targhe, pruning manuale, trigger manuale NVR, calibrazione telecamere / `solve-pnp`, CRUD zone/regole/entità virtuali, switch modalità ingestione e iniezione `/api/v1/detections`.
4. **Media Firmati HMAC (`SignedMediaTokenService`):**
   - Le notifiche push/display usano URL `/api/v1/events/{event_id}/media/{variant}.jpg?exp=<unix>&sig=<b64>` firmati con lo stesso segreto HMAC di sessione (`SPATIAL_SIGNED_MEDIA_TTL_S=86400`), consentendo a HA Companion (su 4G/5G) e Nest Hub di scaricare la snapshot senza cookie.

---

## 7. Variabili d'Ambiente Rilevanti

> **Catalogo esaustivo:** per l'elenco completo di tutte le variabili `.env`, formati, comportamenti Dev vs Prod e regole di sicurezza, consulta [docs/reference/env-variables.md](../docs/reference/env-variables.md).

Di seguito i gruppi principali letti da [config.py](./config.py) (con valori di default quando assenti):

| Gruppo | Variabili chiave e default in `config.py` |
| :--- | :--- |
| **Server & Modalità** | `SH3D_DEV_MODE` (`false`), `SPATIAL_SERVER_HOST` (`127.0.0.1`), `SPATIAL_SERVER_PORT` (`8765`), `SPATIAL_PUBLIC_URL` (`""`), `SPATIAL_ALLOWED_ORIGINS` (default localhost + origini derivate da HA public URL) |
| **Sicurezza & HA** | `SPATIAL_AUTH_REQUIRED` (`true`), `SPATIAL_DEV_AUTH_REQUIRED` (override solo se `SH3D_DEV_MODE=true`), `SPATIAL_AUTH_CACHE_TTL_S` (`120.0`), `SPATIAL_SESSION_SECRET` (`""`), `VITE_HA_LOCAL_URL`, `VITE_HA_TAILSCALE_URL`, `VITE_HA_PUBLIC_URL` / `HA_PUBLIC_URL`, `HA_TOKEN`, `HA_BRIDGE_ENABLED` (`true`), `HA_MQTT_BRIDGE_ENABLED` (`false`) |
| **CV & Ingestione** | `CV_INGESTION_MODE` / `SPATIAL_INGESTION_MODE` (`"synthetic"`, override `CV_DEV_INGESTION_MODE` in dev), `OPENVINO_DEVICE` (`AUTO`), `OPENVINO_CPU_THREADS` (`2`), `OPENVINO_YOLO_MODEL` (`models/yolov8n_openvino_model`), `OPENVINO_FPS_LIMIT` (`7.0`), `OPENVINO_CONF_THRESHOLD` (`0.35`), `OPENVINO_CAMERA_STREAMS`, `GO2RTC_RTSP_BASE_URL` (`rtsp://127.0.0.1:8554`) |
| **MQTT & Persistenza** | `MQTT_BROKER_HOST` (`192.168.86.24`), `MQTT_BROKER_PORT` (`1883`), `MQTT_USER`, `MQTT_PASS`, `MQTT_TOPIC_PREFIX` / `MQTT_FRIGATE_TOPIC` (`frigate/events`), `SPATIAL_RETENTION_DAYS` (`30`), `SPATIAL_PERSIST_MIN_DISPLACEMENT_M` (`0.15`), `SPATIAL_PERSIST_HEARTBEAT_S` (`10.0`) |
| **Biometria** | `BIOMETRICS_ENABLED` (`false`, override `BIOMETRICS_DEV_ENABLED` in dev), `BIOMETRICS_FACE_ENABLED` (`true`), `BIOMETRICS_ALPR_ENABLED` (`true`), `BIOMETRICS_ONNX_PROVIDER` (`cpu`), `BIOMETRICS_ONNX_INTRA_THREADS` (`2`), `BIOMETRICS_QUEUE_MAXSIZE` (`8`), `BIOMETRICS_FACE_MATCH_THRESHOLD` (`0.45`), `BIOMETRICS_FACE_MARGIN_THRESHOLD` (`0.08`), `BIOMETRICS_FACE_CONSENSUS_K` (`2`), `BIOMETRICS_FACE_MAX_RANGE_M` (`8.0`), `BIOMETRICS_ALPR_MAX_RANGE_M` (`13.0`), `BIOMETRICS_CAMERA_RULES` |
| **NVR Dual-Tier** | `SPATIAL_NVR_STORAGE_DIR` (`None`), `SPATIAL_NVR_RECORDER_ENABLED` (`false`), `SPATIAL_NVR_SUB_SEGMENT_SEC` (`60.0`), `SPATIAL_NVR_MAIN_PRE_ROLL_SEC` (`10.0`), `SPATIAL_NVR_MAIN_INERTIA_SEC` (`15.0`), `SPATIAL_NVR_RAM_BUFFER_MAX_MB_PER_CAM` (`48.0`), `SPATIAL_NVR_MIN_FREE_GB` (`50.0`), `SPATIAL_NVR_SUB_RETENTION_DAYS` (`30`), `SPATIAL_NVR_MAIN_RETENTION_DAYS` (`60`), `SPATIAL_NVR_CAMERA_CLOCK_OFFSETS`, `SPATIAL_NVR_CAMERA_STREAMS` |
| **Episodi & Notifiche** | `SPATIAL_EVENTS_INERTIA_S` (`18.0`), `SPATIAL_EVENTS_PRE_ROLL_S` (`3.0`), `SPATIAL_EVENTS_RETENTION_DAYS` (`30`), `SPATIAL_EVENTS_SNAPSHOT_MAX_MB` (`400.0`), `SPATIAL_EVENTS_SNAPSHOT_MAX_WIDTH` (`1280`), `SPATIAL_SIGNED_MEDIA_TTL_S` (`86400`), `HOME_LATITUDE` (`45.55`), `HOME_LONGITUDE` (`11.55`) |
