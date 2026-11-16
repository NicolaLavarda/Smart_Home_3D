# Guida Completa Configurazione Reolink RLC-540A, Streaming e Deployment Windows 10

Questa guida spiega passo passo come abilitare i flussi di rete sulla telecamera **Reolink RLC-540A** (`192.168.86.47`), testare immediatamente il sistema sul portatile di sviluppo e migrare in produzione sul PC Fisso Windows 10 (**Intel i5-6400 / 8 GB RAM / Intel HD 530**, senza Docker).

---

## 1. Configurazione Obbligatoria su Reolink RLC-540A (`http://192.168.86.47:80`)

Nei firmware Reolink recenti, i server di rete **RTSP**, **RTMP** e **ONVIF** sono **disattivati di fabbrica**. Segui esattamente questi clic nell'interfaccia Web della telecamera:

1. Apri il browser dal PC e vai su **`http://192.168.86.47:80`**.
2. Effettua il login con l'account amministratore (di default utente `admin` e la password configurata in fase di installazione).
3. In alto a destra, clicca sull'icona dell'**Ingranaggio (Impostazioni / Settings)**.
4. Nel menu laterale sinistro espandi **`Network` (Rete)** → **`Advanced` (Avanzate)**.
5. Alla voce **`Port Settings` (Impostazioni Porta)** clicca su **`Set Up` (Configura)**:
   * Attiva l'interruttore **`RTSP`** e verifica che la porta sia **`554`**.
   * Attiva l'interruttore **`RTMP`** e verifica che la porta sia **`1935`** (usata internamente anche per il feed `http-flv` a latenza ultra-bassa).
   * Attiva l'interruttore **`ONVIF`** sulla porta **`8000`** (utile per Home Assistant e auto-discovery).
   * Clicca **`Save` (Salva)** in basso.
6. Sempre nelle Impostazioni, vai su **`Camera` → `Stream` (Flusso Video)** e imposta **H.264** per compatibilità WebRTC diretta nel browser:
   * **Clear (Main Stream):** Risoluzione massima (es. `2560×1920` o `2560×1440`), **FPS: `15–25`**, **I-Frame Interval: `1x` o `2s`** (per WebRTC istantaneo).
   * **Fluent (Sub Stream — per Computer Vision AI):** Risoluzione **`640×360`** (o `640×480`), **FPS: `8`**, **Max Bitrate: `512 Kbps`**.
   * Clicca **`Save` (Salva)**.

> [!TIP]
> Se la tua RLC-540A avesse il Main Stream a 5MP codificato in **H.265 (HEVC)**, WebRTC su alcuni browser potrebbe non decodificarlo senza transcodifica; usare **`go2rtc` MSE** (già gestito automaticamente come fallback in `VideoStreamManager`) oppure mantenere **H.264** risolve il problema a monte con zero consumo CPU.

---

## 2. Configurazione File `.env` (Credenziali e LAN)

Apri il file `.env` nella cartella radice del progetto e compila i parametri mancanti (NON condividere o committare `.env` su Git):

```env
# Credenziali Reolink RLC-540A
REOLINK_CARRAIO_IP=192.168.86.47
REOLINK_CARRAIO_USER=admin
REOLINK_CARRAIO_PASS=LA_TUA_PASSWORD_REOLINK

# Home Assistant VM & Mosquitto MQTT (192.168.86.24)
MQTT_BROKER_HOST=192.168.86.24
MQTT_BROKER_PORT=1883
MQTT_USER=
MQTT_PASS=
MQTT_FRIGATE_TOPIC=frigate/events

# Microservizio Spaziale Python (porta 8765 per evitare conflitti con IIS/Apache su 8000)
VITE_SPATIAL_SERVER_URL=http://localhost:8765
VITE_SPATIAL_WS_URL=ws://localhost:8765/ws/spatial
SPATIAL_SERVER_HOST=0.0.0.0
SPATIAL_SERVER_PORT=8765
CV_INGESTION_MODE=synthetic
OPENVINO_DEVICE=AUTO
```

---

## 3. Test Immediato sul Portatile di Sviluppo

1. Avvia i due servizi nativi (`go2rtc.exe` su porta `1984` e `spatial_server` FastAPI su porta `8765`):
   ```bat
   scripts\start_services.bat
   ```
2. Avvia il frontend Three.js in modalità sviluppo:
   ```bat
   npm.cmd run dev
   ```
3. Apri **`http://localhost:3000`** nel browser:
   * Clicca fisicamente sulla telecamera sul pilastrino (o sull'icona `📹`) per aprire il modale **WebRTC / MSE Live** della RLC-540A e passare da `Main 5MP` a `Sub 640×360`.
   * Nella barra in basso vedrai il badge verde **`SPATIAL SYNTHETIC`** con gli avatar 3D (persona `"Nicola"` + veicolo) che camminano a **60 fps** lungo il vialetto grazie all'interpolazione Kalman e allo storico **SQLite3 WAL + R-Tree**.

---

## 4. Calibrazione Ottica POV (Allineamento Reolink ↔ Modello 3D)

Una volta che il video live della Reolink appare nel modale:

1. Premi il tasto **`📐 Apri Calibrazione Ottica POV`** dentro il modale telecamera (o **`📐 Calibra Cam`** nella barra superiore).
2. La scena volerà all'interno del modello `Cam_Carraio` sovrapponendo il video reale traslucido al modello 3D:
   * Se vedi il vialetto invertito rispetto alla strada esterna, clicca **`🔄 Inverti Direzione 180° (Vialetto ↔ Strada)`**.
   * Usa **Yaw Δ / Pitch Δ / Roll Δ** ed eventualmente **FOV Vert.** e **k1/k2** finché i pilastri, il cancello e i bordi del vialetto nel video combaciano con le mesh 3D.
   * *(Opzionale avanzato)* Usa **`🎯 Raccogli Punti PnP`** cliccando 4 spigoli corrispondenti (prima sul 3D, poi sul video) e premi **`⚡ Risolvi PnP`** per la calibrazione automatica OpenCV `SolvePnPRansac`.
3. Premi **`💾 Salva & Applica a Backend`**: la matrice calibrata `extrinsic_cv_to_world` viene salvata in `spatial_server/data/camera_calibrations.json` ed applicata istantaneamente al `TrimeshGroundRaycaster`.

---

## 5. Passaggio dalla Modalità Sintetica a OpenVINO Live / MQTT / Hybrid

Puoi cambiare sorgente CV in qualsiasi momento **a caldo (zero downtime)** direttamente dal modale della telecamera (`🧠 Passa a Rilevamento OpenVINO Live`) oppure tramite API:

* **`synthetic`**: simulatore 10 Hz per test e demo.
* **`openvino`**: legge `rtsp://127.0.0.1:8554/carraio_sub` ($640\times 360$ @ $7\text{ fps}$) ed esegue inferenza locale.
* **`mqtt`**: riceve eventi `frigate/events` o JSON custom dal broker Mosquitto sulla VM (`192.168.86.24:1883`).
* **`hybrid`**: attiva contemporaneamente OpenVINO locale e MQTT.

### Abilitare YOLOv8n su OpenVINO (Intel HD Graphics 530 / CPU Skylake)
Sul PC con Python e connettività Internet:
```bat
.venv\Scripts\pip.exe install openvino>=2024.4.0
```
Se possiedi un modello `yolov8n_openvino_model/` esportato (cartella con `.xml` + `.bin`), posizionalo in `spatial_server/models/yolov8n_openvino_model/` e imposta `OPENVINO_DEVICE=GPU` (o `AUTO`) in `.env` per scaricare la CPU su Intel HD 530 QuickSync/OpenCL. In assenza del file `.xml`, il microservizio attiva automaticamente il detector persone leggero OpenCV HOG come fallback operativo.

### Predisposizione Riconoscimento Facciale (`IIdentityResolver`)
* Se usi Frigate con `sub_label` (es. via DoubleTake / CompreFace), il nome della persona appare automaticamente nel badge CSS2D sopra l'avatar (`🧑 Nicola`) senza alcuna configurazione extra.
* Oppure imposta `FACE_RECOGNITION_WEBHOOK_URL=http://192.168.86.x:port/recognize` in `.env`, oppure salva gli embedding ArcFace `.npy` (es. `Nicola.npy`) in `spatial_server/models/face_gallery/`.

---

## 6. Migrazione Finale sul PC Fisso Server (Windows 10 — i5-6400 / 8 GB RAM)

Poiché tutto lo stack è **100% nativo Windows (Zero Docker / Zero WSL2)**:

1. Copia la cartella del progetto `Smart_Home_3D` sul PC Fisso (es. `C:\SmartHome3D`).
2. Compila `.env` con le password corrette (e costruisci una build statica del frontend con `npm.cmd run build` se vuoi servirla da file/webserver locale).
3. Apri PowerShell nella cartella ed esegui **una sola volta**:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup_windows_node.ps1 -WithOpenVINO
   ```
4. Avvia i servizi con doppio clic su **`scripts\start_services.bat`**.
5. *(Consigliato)* Per l'avvio automatico ad ogni accensione di Windows 10, apri **Utilità di pianificazione (`taskschd.msc`)** → *Crea attività* → Trigger: *All'avvio del sistema* → Azione: avvia `C:\SmartHome3D\scripts\start_services.bat`.
6. **Impronta RAM stimata sul PC Fisso:**
   * `go2rtc.exe`: ~25 MB RAM
   * `spatial_server` Python + Trimesh + SQLite3 WAL + OpenVINO sub-stream: ~140–220 MB RAM (lascia quasi tutta la RAM libera alla VM Home Assistant OS su VirtualBox).

---

## 7. Aggiunta di Nuove Telecamere (Inclusa Reolink Duo 3 PoE 180°)

Il sistema è già predisposto tramite **Strategy Pattern (`ICameraOpticalModel`)**:
1. Aggiungi la nuova camera in Blender (`Cam_Giardino`, `Cam_Duo3`, ecc.) con custom property `ha_camera_entity`, `stream_id`, `sub_stream_id`, e per la **Reolink Duo 3 PoE** imposta `optical_model = "equirectangular_180"` e `fov_h_deg = 180.0`.
2. Riesegui `npm.cmd run build:model` per aggiornare `scene_manifest.json` e `house_optimized.glb`.
3. Aggiungi gli stream della nuova Reolink in `go2rtc/go2rtc.yaml`.
4. Il tracker `Kalman3DMultiTracker` fonderà automaticamente nello stesso `track_id` le rilevazioni provenienti da più telecamere con aree sovrapposte!

---

## 8. Accesso Remoto con Tailscale (Fuori dal Wi-Fi di Casa)

Quando sei fuori dalla rete Wi-Fi domestica (`192.168.86.0/24`), il client `HAClient` si collega automaticamente a Home Assistant tramite l'indirizzo Tailscale (`VITE_HA_TAILSCALE_URL` in `.env`). Per combinare Tailscale e telecamere hai **due livelli di funzionamento** integrati:

### Livello 1 — Automatico (Zero Configurazione Extra): Bridge Home Assistant via Tailscale
* Se `go2rtc.exe` locale sul portatile non riesce a raggiungere `192.168.86.47` (perché sei su un'altra rete), `VideoStreamManager` esegue in ~1.5 secondi il fallback su **`HaSnapshotFallbackStream`**.
* Il frontend passa tramite il proxy same-origin di Vite (`/api/ha-camera/snapshot`) o del microservizio Python (`/api/v1/ha-camera/snapshot/{entity_id}`), evitando qualsiasi blocco **CORS** del browser e risolvendo automaticamente l'entità Reolink reale su Home Assistant.
* Nel modale della telecamera vedrai il badge verde **`HA TAILSCALE LIVE`** e l'endpoint **`Tailscale Bridge → 192.168.86.47`**.

> [!NOTE]
> Affinché il Bridge funzioni, è necessario che la Reolink sia già aggiunta come integrazione **Reolink** (o **Generic Camera**) dentro Home Assistant e che il file `.env` contenga `VITE_HA_TOKEN` valido.

### Livello 2 — WebRTC / MSE a Bassa Latenza da Remoto (Consigliato)
Per ottenere il flusso **WebRTC / MSE a 25 fps** anche fuori casa hai due opzioni:

1. **Opzione A — Tailscale Subnet Router (Raggiunge `192.168.86.47` direttamente via VPN):**
   * **Su Home Assistant (Add-on Tailscale):**
     1. Vai in **Impostazioni → Componenti aggiuntivi → Tailscale → Configurazione**.
     2. Aggiungi la subnet della LAN domestica nelle rotte annunciate (`advertise_routes`):
        ```yaml
        advertise_routes:
          - 192.168.86.0/24
        ```
     3. Salva e riavvia l'add-on.
     4. Apri la **Tailscale Admin Console** (`https://login.tailscale.com/admin/machines`), clicca sui tre puntini (`...`) della macchina Home Assistant → **Edit route settings** → attiva la spunta su **`192.168.86.0/24`**.
   * **In alternativa sul PC Fisso Windows 10 (sempre acceso):**
     Esegui una sola volta da terminale amministratore:
     ```bat
     tailscale up --advertise-routes=192.168.86.0/24
     ```
     e approva la rotta nella Tailscale Admin Console.
   * Con il Subnet Router attivo, `go2rtc.exe` sul portatile può raggiungere direttamente `rtsp://192.168.86.47:554` e la pagina Web `http://192.168.86.47` ovunque ti trovi.

2. **Opzione B — `go2rtc.exe` sul PC Fisso esposto via IP Tailscale:**
   * Quando `go2rtc.exe` gira sul PC Fisso sempre acceso (`scripts\start_services.bat`), aggiungi in `.env` sul portatile:
     ```env
     VITE_GO2RTC_TAILSCALE_URL=http://IP_TAILSCALE_PC_FISSO:1984
     ```
   * Quando `HAClient` rileva che sei connesso via Tailscale, `VideoStreamManager` si collegherà automaticamente all'istanza `go2rtc` del PC Fisso senza bisogno del Subnet Router.


