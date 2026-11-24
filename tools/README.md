# `tools/` — Catalogo Completo Script, Utility e Componenti Ausiliari

Questa directory raccoglie tutti gli strumenti CLI offline, gli script di provisioning modelli AI, i tool di discovery/mapping Home Assistant, l'ottimizzatore GLB, i tool di ispezione/audit Blender e gli script legacy usati durante la ricostruzione della planimetria 3D.

---

## 1. Pipeline Modelli GLB & Ottimizzazione

| File | Runtime | Scopo & Utilizzo |
|---|---|---|
| [`optimize_glb.mjs`](./optimize_glb.mjs) | Node.js (`npm run optimize:glb`) | Legge `public/models/house_raw.glb`, applica `@gltf-transform` (`dedup()`, `prune({ keepAttributes: true, keepLeaves: true })`, `weld()`) preservando nomi nodi e `userData` Blender, e scrive `public/models/house_optimized.glb` (con fallback copy se `@gltf-transform` fallisce). |

---

## 2. Provisioning AI, OpenVINO & Biometria (ONNX)

| File | Runtime & CLI | Scopo |
|---|---|---|
| [`download_yolo_openvino_model.py`](./download_yolo_openvino_model.py) | `.venv\Scripts\python.exe tools\download_yolo_openvino_model.py [--target-dir ...] [--force]` | Scarica `yolov8n.onnx` (640×640 COCO), verifica inferenza `(1, 3, 640, 640) -> (1, 84, 8400)` con ONNX Runtime e converte in OpenVINO FP16 IR (`yolov8n.xml` + `yolov8n.bin`) in `spatial_server/models/yolov8n_openvino_model/`. |
| [`download_biometric_models.py`](./download_biometric_models.py) | `.venv\Scripts\python.exe tools\download_biometric_models.py [--models-dir ...] [--force]` | Scarica e verifica i modelli ONNX per Face Recognition (`det_500m.onnx`, `w600k_mbf.onnx`, `w600k_r50.onnx` da InsightFace `buffalo_s`/`buffalo_l`) e ALPR (`yolo-v9-t-384-license-plate-end2end`, `cct-xs-v2-global-model`, `european-plates-mobile-vit-v2-model`) in `spatial_server/models/biometrics/` generando `manifest.json` con SHA-256 e I/O tensori. |
| [`enroll_faces.py`](./enroll_faces.py) | `.venv\Scripts\python.exe tools\enroll_faces.py --input <dir> [--output ...] [--det-model ...] [--rec-model ...] [--max-reps 8] [--min-width 48] [--min-blur 25] [--max-yaw-ratio 0.55] [--outlier-min-cos 0.30] [--threads 2] [--report]` | Tool idempotente ONNX Runtime + OpenCV per generare la galleria compatta `spatial_server/data/biometrics/face_gallery.npz` a partire da sottocartelle `<NomePersona>\*.jpg`, con filtro qualità/outlier, rappresentanti diversificati e valutazione Leave-One-Out (`--report`). |
| [`benchmark_biometrics.py`](./benchmark_biometrics.py) | `.venv\Scripts\python.exe tools\benchmark_biometrics.py [--skip-cameras] [--only-cameras] [--warmup 5] [--iters 25] [--gallery-mbf ...] [--gallery-r50 ...]` | Benchmark hardware Fase 0 (latenza p50/mean/p95 ms, memoria RSS MB, downscaling 16MP 32:9 Reolink Duo 3 PoE): misura CGI Snap delle 4 Reolink, Face ONNX (`CPUExecutionProvider` threads 1/2/4 vs OpenVINO) e ALPR ONNX. |

---

## 3. Home Assistant Discovery, Mapping & Telemetria MQTT

> [!NOTE]
> `fetch_ha_entities.mjs`, `generate_devices_mapping_md.mjs` e `listen_deebot_pose.mjs` leggono localmente `.env` per connettersi al WebSocket di Home Assistant in sviluppo/manutenzione.

| File / Cartella | Runtime & CLI | Scopo |
|---|---|---|
| [`fetch_ha_entities.mjs`](./fetch_ha_entities.mjs) | `node tools/fetch_ha_entities.mjs` | Si connette via WebSocket a HA (`VITE_HA_URL` + `VITE_HA_TOKEN` in `.env`) e stampa in console le entità raggruppate per dominio (`light`, `camera`, `cover`, `media_player` e parole chiave). |
| [`generate_devices_mapping_md.mjs`](./generate_devices_mapping_md.mjs) | `node tools/generate_devices_mapping_md.mjs` | Scarica tutte le entità rilevanti da HA e genera [`docs/reference/ha-devices-mapping.md`](../docs/reference/ha-devices-mapping.md) evidenziando quelle già mappate (`ALREADY_MAPPED`) e predisponendo i blocchi `###` compilabili dall'utente. |
| [`read_mapped.mjs`](./read_mapped.mjs) | `node tools/read_mapped.mjs` | Analizza [`docs/reference/ha-devices-mapping.md`](../docs/reference/ha-devices-mapping.md) splittando su ``### ` `` ed estrae tutte le entità marcate dall'utente con `Azione: mappa` o `Posizione 3D` compilata. |
| [`listen_deebot_pose.mjs`](./listen_deebot_pose.mjs) | `node tools/listen_deebot_pose.mjs` | Listener WebSocket diagnostico compatibile Node 18–24+: si sottoscrive al topic MQTT `homeassistant/deebot/pose` via HA e stampa `X`, `Y` (mm), `Angolo` (°) e stato del Deebot in tempo reale. |
| [`ha_custom_component/README_MQTT_BRIDGE.md`](./ha_custom_component/README_MQTT_BRIDGE.md) | Home Assistant Custom Component | Guida all'installazione e payload JSON del componente [`ha_custom_component/ecovacs_mqtt_bridge/`](./ha_custom_component/ecovacs_mqtt_bridge/__init__.py) su Home Assistant. |

---

## 4. Strumenti Blender (`bpy`): Audit, Dispositivi, Geometria e Camere di Test

Questi script vanno eseguiti nel runtime Python di Blender (`blender.exe -b Smart_Home_3D.blend -P tools/<script>.py`).

### 4.1 Audit e Verifica Scena
- [`audit_scene_objects.py`](./audit_scene_objects.py): conteggio globale oggetti/mesh/materiali e report per categoria (cucina, salotto, camino, lavanderia, bagno, scale, dispositivi HA, infissi).
- [`audit_detailed.py`](./audit_detailed.py): elenco completo oggetti nelle collezioni principali (`02_Edificio_Residenziale`, `03_Lavanderia`, `04_Garage`, `05_Scale_e_Sottoscala`, `08_Luci_e_Camere`) e riepilogo prefissi in `09_Arredi_Principali`.
- [`find_dishwasher_mesh.py`](./find_dishwasher_mesh.py), [`verify_dishwasher_layout.py`](./verify_dishwasher_layout.py): verifica bounding-box e layout della lavastoviglie in cucina.
- `inspect_*.py` (Blender): [`inspect_driveway_curve.py`](./inspect_driveway_curve.py), [`inspect_front_fence.py`](./inspect_front_fence.py), [`inspect_gate_and_shower.py`](./inspect_gate_and_shower.py), [`inspect_kitchen_blender.py`](./inspect_kitchen_blender.py), [`inspect_kitchen_lower.py`](./inspect_kitchen_lower.py), [`inspect_lavanderia.py`](./inspect_lavanderia.py), [`inspect_lavanderia_all.py`](./inspect_lavanderia_all.py), [`inspect_layout.py`](./inspect_layout.py), [`inspect_openings.py`](./inspect_openings.py), [`inspect_paraste.py`](./inspect_paraste.py), [`inspect_parts.py`](./inspect_parts.py), [`inspect_paths.py`](./inspect_paths.py), [`inspect_salotto_east.py`](./inspect_salotto_east.py), [`inspect_salotto_walls.py`](./inspect_salotto_walls.py) — stampano coordinate vertici, dimensioni e posizioni mondiali delle varie aree del `.blend`.

### 4.2 Dispositivi, Geometria e Ripristini Mirati
- [`add_ecovacs_deebot.py`](./add_ecovacs_deebot.py): crea le mesh e i materiali `Mat_Deebot_*` del robot aspirapolvere e della stazione di ricarica in sala da pranzo (`x = 13.90` vicino al camino).
- [`add_irrigation_sprinklers.py`](./add_irrigation_sprinklers.py): genera gli 11 gettini pop-up in `01_Sito_e_Giardini` suddivisi nelle 3 aree `switch.smart_switch_area1..3`.
- [`update_fence_walkways_garage.py`](./update_fence_walkways_garage.py): aggiorna recinzione perimetrale, muretto centrale cancelli, `Terrazza_All_Aperto`, vialetto pedonale, curva viale carraio, colonne portico, posizione garage, prati watertight e lampioncini.
- [`update_kitchen_dishwasher.py`](./update_kitchen_dishwasher.py): ristruttura lavastoviglie (60 cm), cassetti e scocca della base sud cucina.
- [`restore_and_fix_all.py`](./restore_and_fix_all.py): script di ripristino e correzione su sito/giardini, lavanderia, garage, scale, recinzione e arredi.
- [`restore_dining_chairs.py`](./restore_dining_chairs.py): ricostruisce/riallinea le sedie del tavolo da pranzo.
- [`fix_doors_view.py`](./fix_doors_view.py), [`open_door_cam.py`](./open_door_cam.py): correzione apertura ante (`Door_Bagno_Panel`, `Door_Antibagno_Panel`).
- [`test_shader.py`](./test_shader.py), [`test_shower_update.py`](./test_shower_update.py): test isolati di nodi shader PBR e ridimensionamento muretti doccia lavanderia.
- [`generate_model.py`](./generate_model.py): **[OBSOLETO — NON ESEGUIRE]** contiene protezione esplicita `RuntimeError("SAFETY ABORT: tools/generate_model.py is an obsolete scene wiper. DO NOT RUN.")`.

### 4.3 Camere di Ispezione e Rendering Preview Blender
- [`add_antibagno_cam.py`](./add_antibagno_cam.py), [`add_axon_cam.py`](./add_axon_cam.py), [`add_stair_cam.py`](./add_stair_cam.py), [`adjust_stair_cam.py`](./adjust_stair_cam.py), [`render_kitchen_preview.py`](./render_kitchen_preview.py), [`update_cam_world.py`](./update_cam_world.py): posizionano camere di controllo interne/assonometriche o regolano il World background di Blender per render di verifica visiva.

---

## 5. Legacy Planimetria, OCR & Cropping Immagini (OpenCV / Pillow)

Utility storiche usate nella fase iniziale di rilievo delle tavole architettoniche (non usate a runtime):
- **Rilevamento linee e misure su tavole**: [`find_garage_y.py`](./find_garage_y.py), [`find_h_lines.py`](./find_h_lines.py), [`find_opening_y.py`](./find_opening_y.py), [`find_v_lines.py`](./find_v_lines.py), [`measure_gap.py`](./measure_gap.py), [`test_ocr.py`](./test_ocr.py) (usa `pytesseract`).
- **Crop di regioni planimetriche**: [`inspect_arrow.py`](./inspect_arrow.py), [`inspect_arrow2.py`](./inspect_arrow2.py), [`inspect_bottom.py`](./inspect_bottom.py), [`inspect_color_plan.py`](./inspect_color_plan.py), [`inspect_connection.py`](./inspect_connection.py), [`inspect_dividing.py`](./inspect_dividing.py), [`inspect_new_images.py`](./inspect_new_images.py), [`inspect_plan.py`](./inspect_plan.py), [`inspect_revit.py`](./inspect_revit.py), [`inspect_sheet4.py`](./inspect_sheet4.py), [`inspect_stair_details.py`](./inspect_stair_details.py), [`inspect_stairs_zoom.py`](./inspect_stairs_zoom.py), [`inspect_strip.py`](./inspect_strip.py), [`inspect_upper.py`](./inspect_upper.py).
- **Asset di riferimento**: [`ecovacs_map_extracted.png`](./ecovacs_map_extracted.png), [`map_rotated_ccw90.png`](./map_rotated_ccw90.png).

---

## 6. Binari Runtime Provisionati Localmente (`.gitignore`)

- `tools/nssm.exe`: scaricato automaticamente da [`scripts/setup_windows_node.ps1`](../scripts/setup_windows_node.ps1) (non tracciato su Git) e usato da `install_windows_services.ps1`, `start_services.bat` e `stop_services.bat`.

---

## Riferimenti Correlati
- Architettura Blender SSoT e `optimize_glb.mjs`: [`docs/architecture/blender-ssot-pipeline.md`](../docs/architecture/blender-ssot-pipeline.md)
- Guida locale `blender/`: [`blender/README.md`](../blender/README.md)
- Script di deployment Windows & NSSM: [`scripts/README.md`](../scripts/README.md)
- Mapping dispositivi Home Assistant: [`docs/reference/ha-devices-mapping.md`](../docs/reference/ha-devices-mapping.md)
