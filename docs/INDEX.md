# 📚 Indice della Documentazione — Smart Home 3D

Indice completo della documentazione di **Smart_Home_3D** organizzato secondo la tassonomia **Diátaxis** (*Architettura & Comprensione*, *Runbook Operativi*, *Reference Tecnico*, *Prompt Storici*) insieme alle guide locali di ciascun servizio e cartella del repository.

> Punto d'ingresso principale: [`README.md`](../README.md) · Definizione e vincoli di prodotto: [`PRODUCT.md`](../PRODUCT.md)

---

## 1. Architettura & Comprensione (`docs/architecture/`)

Documenti di spiegazione e riferimento architetturale sui sottosistemi di **Smart Home 3D**.

| Documento | Argomento |
|---|---|
| [`architecture/system-overview.md`](architecture/system-overview.md) | Panoramica end-to-end tra Browser/PWA, Tailscale Serve (`:443` / `:8443`), Caddy (`:8080`), `spatial_server` (`:8765`), `go2rtc` (`:1984` / `:8554` / `:8555`), VM Home Assistant (`.24:8123` / `:1883`), flusso OAuth2 PKCE + `sh3d_session` + `forward_auth` e budget hardware (`i5-6400`, `8 GB RAM`). |
| [`architecture/frontend-and-devices.md`](architecture/frontend-and-devices.md) | Architettura dettagliata dell'app Vite/Three.js/PWA (`src/`): motore 3D (`core/`), sync HA & OAuth2 (`ha/`), i 6 controller modulari (`devices/`: TV, lavastoviglie, irrigazione, vacuum, termica, telecamere), proiezione/calibrazione PnP/automazioni (`spatial/`), cascade WebRTC/MSE/Snapshot e NVR Dual-Buffer (`video/`), UI Shell Material 3 & Workbox (`ui/`, `vite.config.js`). |
| [`architecture/spatial-cv-and-biometrics.md`](architecture/spatial-cv-and-biometrics.md) | Architettura interna di `spatial_server/`: pipeline end-to-end e analisi approfondita di tutti i 12 sottosistemi (`domain`, `ingestion`, `optics`, `geometry`, `tracking`, `biometrics` Face/ALPR, `events`, `automations`, `recordings` NVR Dual-Tier, `integrations` HA/MQTT, `persistence` SQLite WAL + R-Tree, `security` HMAC/RBAC). |
| [`architecture/blender-ssot-pipeline.md`](architecture/blender-ssot-pipeline.md) | Pipeline **Blender Single Source of Truth (SSoT)**: `Smart_Home_3D.blend`, script `blender/scripts/` e builder root, contratto delle Custom Properties (`ha_*`, `collider_role`, proprietà ottiche/stream), schema completo di `public/models/scene_manifest.json` e ottimizzazione `@gltf-transform` (`tools/optimize_glb.mjs`). |
| [`architecture/smart-devices.md`](architecture/smart-devices.md) | Pattern modulare e decentralizzato `BaseDeviceController` + `DeviceRegistry` in `src/devices/` (esempio completo modulo TV webOS e guida all'aggiunta di nuovi dispositivi). |
| [`architecture/hardware-server-specs.md`](architecture/hardware-server-specs.md) | Specifiche dell'host fisico di produzione (Windows 10 nativo, Intel Core i5-6400, 8 GB DDR4, Intel HD 530), VirtualBox HA VM (`192.168.86.24`), servizi NSSM e vincoli Zero Docker / Zero transcoding. |

---

## 2. Guide Operative & Runbook (`docs/runbooks/`)

Procedure passo-passo per deploy, messa in produzione, manutenzione hardware e integrazione di nuove telecamere.

| Runbook | Scopo Operativo |
|---|---|
| [`runbooks/production-tailscale.md`](runbooks/production-tailscale.md) | **Runbook di produzione famiglia:** configurazione `trusted_proxies` e RBAC (`Admin` vs `Residente`) su Home Assistant, Tailscale Windows 10 unattended, `netsh portproxy` + `tailscale serve` (`:443` / `:8443`), Caddy + NSSM + Firewall `:8555`, ACL / Node Sharing, onboarding PWA iOS/Android, attivazione biometria Face/ALPR e dismissione CodeProject.AI. |
| [`runbooks/add-camera.md`](runbooks/add-camera.md) | **Pipeline end-to-end per aggiungere una telecamera:** raccolta requisiti, parametri ottici/equirettangolari, posizionamento e Custom Properties in `Smart_Home_3D.blend`, aggiornamento `setup_ha_properties.py` / `go2rtc.yaml` / `.env`, audit multi-camera frontend/backend, test e calibrazione POV. |
| [`runbooks/reolink-and-services.md`](runbooks/reolink-and-services.md) | Configurazione iniziale web UI Reolink (RTSP `554`, RTMP `1935`, ONVIF `8000`, codec H.264 Main/Sub), `.env` di sviluppo, calibrazione ottica POV e passaggio tra modalità `synthetic`, `openvino`, `mqtt` e `hybrid`. |
| [`runbooks/nvr-dual-tier-hdd.md`](runbooks/nvr-dual-tier-hdd.md) | Architettura e checklist di attivazione su disco SATA **CMR** dell'archivio locale **NVR Dual-Tier** (`Sub H24` in segmenti da `60s` + `Main Event` con pre-buffer RAM GOP da `10s`, PyAV senza transcodifica e calibrazione offset temporali). |

---

## 3. Reference Tecnico (`docs/reference/`)

Specifiche tabellari e cataloghi di riferimento generati o verificati rispetto al codice.

| Documento | Contenuto |
|---|---|
| [`reference/env-variables.md`](reference/env-variables.md) | Reference completo delle sezioni `0`–`9` di [`.env.example`](../.env.example), fallback in `spatial_server/config.py`, variabili aggiuntive runtime, comportamento di `SH3D_DEV_MODE`, build-time stripping `VITE_*` e regole di propagazione verso NSSM. |
| [`reference/ha-devices-mapping.md`](reference/ha-devices-mapping.md) | Inventario delle entità estratte da Home Assistant e stato di mappatura nel 3D Digital Twin (file auto-generato da `node tools/generate_devices_mapping_md.mjs` e letto da `node tools/read_mapped.mjs`). |
| [`reference/testing-suite.md`](reference/testing-suite.md) | Mappa completa delle suite automatiche: `tests/e2e/` (`F1`–`F19`, Tier 3, Tier 4 — 248 item `pytest`), harness Python/Node (`tests/e2e/helpers/`), `spatial_server/tests/` (50 item + `verify_pipeline.py`) e verifiche CLI Node/Caddy. |

---

## 4. Guide Locali per Servizio & Cartella (Repository)

Ogni componente operativo principale dispone di un `README` dedicato nella propria directory:

| Cartella / Servizio | Guida | Copertura Principale |
|---|---|---|
| **Frontend Three.js / PWA** | [`src/README.md`](../src/README.md) | Entrypoint `index.html` -> `src/main.js`, pipeline Vite/Workbox, mappa di tutti i 62 file in `src/`, CSS Material 3, RBAC UI e guida estensione `BaseDeviceController`. |
| **Backend Spatial CV & NVR** | [`spatial_server/README.md`](../spatial_server/README.md) | Stack Python, setup `.venv`, mappa moduli, catalogo completo dei 55 endpoint REST e protocollo `/ws/spatial`, SQLite WAL e RBAC `ha_auth.py`. |
| **Pipeline Blender SSoT** | [`blender/README.md`](../blender/README.md) | Script `setup_ha_properties.py`, `add_user_devices.py`, `export_glb.py`, comandi `npm` (`setup:props`, `export:blend`, `optimize:glb`, `build:model`). |
| **Script Windows & NSSM** | [`scripts/README.md`](../scripts/README.md) | Provisioning `setup_windows_node.ps1`, servizi NSSM (`install_windows_services.ps1`), `start`/`stop`/`update_services.bat` e `decommission_codeproject_ai.ps1`. |
| **Reverse Proxy Caddy** | [`caddy/README.md`](../caddy/README.md) | Listener loopback `127.0.0.1:8080`, route `/api/v1/*`, `/ws/spatial`, `forward_auth` su `go2rtc`, blocco `403` sulla UI `go2rtc` e policy `Cache-Control` PWA. |
| **Media Server go2rtc** | [`go2rtc/README.md`](../go2rtc/README.md) | Configurazione `127.0.0.1:1984` / `:8554`, WebRTC ICE `:8555` e catalogo dei 16 stream (`_main`, `_sub`, alias, `_snap`) per le 4 Reolink PoE. |
| **Home Assistant VM** | [`homeassistant/README.md`](../homeassistant/README.md) | Automazioni (`homeassistant/automations.yaml`), `trusted_proxies`, bridge `:8443`, OAuth2/RBAC e bridge H24/MQTT. |
| **Catalogo Tool & Script** | [`tools/README.md`](../tools/README.md) | Ottimizzazione GLB, download/benchmark AI OpenVINO & biometria (`enroll_faces.py`), discovery HA e tool di audit/geometria Blender. |
| **Bridge MQTT Deebot (HA)** | [`tools/ha_custom_component/README_MQTT_BRIDGE.md`](../tools/ha_custom_component/README_MQTT_BRIDGE.md) | Installazione in Home Assistant del custom component `ecovacs_mqtt_bridge` e payload JSON su `homeassistant/deebot/pose`. |

---

## 5. Prompt di Progettazione & Archivio Storico (`docs/prompts/`)

Prompt architetturali di contesto e pianificazione usati nelle fasi evolutive del progetto:

| Prompt | Oggetto |
|---|---|
| [`prompts/master-architecture-prompt.md`](prompts/master-architecture-prompt.md) | Prompt architetturale fondativo: topologia portatile/PC fisso, SOLID/OOP, modelli ottici, raycaster Trimesh, Kalman 3D e pipeline Blender SSoT. |
| [`prompts/future-phases.md`](prompts/future-phases.md) | Prompt di transizione dal prototipo frontend alla piattaforma end-to-end multi-camera (`Cam_Carraio` -> 5–6 camere) con Face Recognition e Re-ID. |
| [`prompts/add-camera-prompt.md`](prompts/add-camera-prompt.md) | Template operativo pronto da compilare per richiedere l'integrazione di una nuova telecamera secondo [`runbooks/add-camera.md`](runbooks/add-camera.md). |
| [`prompts/face-alpr-prompt.md`](prompts/face-alpr-prompt.md) | Prompt di audit e piano implementativo per il sottosistema biometrico nativo (Face Recognition ONNX + ALPR targhe IT/EU) entro il budget `i5-6400 / 8 GB RAM`. |
| [`prompts/pwa-security-prompt.md`](prompts/pwa-security-prompt.md) | Prompt di progettazione per PWA self-hosted, `Tailscale Serve` + `Caddy`, OAuth2 + RBAC `Admin`/`Residente` e servizi NSSM unattended. |
