# Guida Attivazione NVR Dual-Tier (`Sub H24` + `Main Event` con Pre-Buffer RAM)

Questa guida spiega come attivare l'archivio di videosorveglianza locale **Dual-Tier** di `Smart_Home_3D` sul tuo **PC Fisso Windows 10** appena installi l'Hard Disk SATA **CMR**.

---

## 1. Architettura Implementata

1. **Sub Stream continuo H24 (`*_sub`):**
   - Registrato 24/7 in segmenti MP4 da `60s` (`SPATIAL_NVR_SUB_SEGMENT_SEC=60.0`) tagliati esattamente sui keyframe (zero buchi tra un file e il successivo).
   - Occupa pochissimo spazio (~25–45 GB/giorno totali sulle 4 camere), garantendo storico lungo e compatibilità universale H.264 su qualsiasi browser.
2. **Main Stream in RAM + Scrittura su Evento (`*_main`):**
   - `MainStreamEventWorker` mantiene continuamente gli ultimi **`10s` di pacchetti compressi (GOP)** in RAM dentro `CompressedGopRingBuffer` (~50–90 MB totali su 4 camere, ~1–3% CPU sull'i5-6400 perché **non decodifica i pixel**).
   - Appena `spatial_server` rileva un soggetto (`person`, `car`, `truck`, `motorbike`), scarica istantaneamente i secondi già presenti in RAM (**pre-roll**) e prosegue la scrittura su disco fino a fine evento + **`15s` di inerzia** (`SPATIAL_NVR_MAIN_INERTIA_SEC=15.0`). Se il soggetto rientra entro 15 secondi, il timer si azzera e la clip rimane continua.
3. **Indice SQLite WAL + Playback Zero-Gap:**
   - Ogni segmento è indicizzato al millisecondo in `nvr_index.db` (SQLite WAL).
   - La timeline 3D preferisce automaticamente il tier **`main`** (badge **`REPLAY HD`** e barra ambra sulla timeline) quando disponibile, con fallback automatico su `sub` H.264 se il client non supporta HEVC (es. Duo 3 PoE 16MP).
   - Il controller frontend `DualVideoBufferController` precarica il segmento successivo sul secondo `<video>` nascosto negli ultimi 3 secondi e commuta al volo senza schermo nero.

---

## 2. Checklist di Attivazione quando arriva il Disco CMR

### Passo 1 — Verifica Reolink (I-Frame Interval)
Su ciascuna delle 4 telecamere Reolink (`Camera -> Stream`), assicurati che:
* **I-Frame Interval** sia impostato a **`1x` o `2s`** (fondamentale affinché il pre-buffer RAM e i tagli `60s` siano precisi al secondo).
* I flussi `carraio_sub/main`, `portico_sub/main`, `ingresso_sub/main`, `stradina_sub/main` siano raggiungibili da `go2rtc.exe`.

### Passo 2 — Montaggio & Controllo Disco su Windows 10
1. Collega il disco 3.5" SATA **CMR** a una porta SATA III libera sulla scheda madre (e alimentazione SATA dell'alimentatore).
2. *(Se hai scelto un Enterprise ricondizionato, es. HGST Ultrastar)*: avvia **CrystalDiskInfo** e controlla che lo stato SMART sia **`Buono`** con `0` settori riallocati (`05`) / pendenti (`C5`).
3. Da **Gestione disco (`diskmgmt.msc`)**, inizializza in **GPT**, formatta in **NTFS** e assegna una lettera fissa (es. **`D:`**).
4. Crea la cartella radice:
   ```bat
   mkdir D:\Surveillance
   ```

### Passo 3 — Installazione PyAV (`av`) nell'ambiente Python
Nella cartella del progetto `Smart_Home_3D`, esegui:
```bat
.venv\Scripts\pip.exe install -r spatial_server\requirements.txt
```
*(Il pacchetto `av` include le librerie FFmpeg precompilate per Windows x64: non serve installare `ffmpeg.exe` separatamente.)*

### Passo 4 — Configurazione `.env`
Apri il file `.env` (riferimento in [`.env.example`](../../.env.example)) e imposta almeno:
```env
SPATIAL_NVR_STORAGE_DIR=D:\Surveillance
SPATIAL_NVR_RECORDER_ENABLED=true

# Parametri consigliati (modificabili a piacere)
SPATIAL_NVR_SUB_SEGMENT_SEC=60.0
SPATIAL_NVR_MAIN_PRE_ROLL_SEC=10.0
SPATIAL_NVR_MAIN_INERTIA_SEC=15.0
SPATIAL_NVR_RAM_BUFFER_MAX_MB_PER_CAM=48.0

# Retention e spazio libero garantito (elimina sempre prima i vecchi Sub, poi i vecchi Main)
SPATIAL_NVR_MIN_FREE_GB=50.0
SPATIAL_NVR_SUB_RETENTION_DAYS=30
SPATIAL_NVR_MAIN_RETENTION_DAYS=60
```
Riavvia il servizio Windows **`SmartHome3D-SpatialServer`** (o `scripts\start_services.bat`).

---

## 3. Verifica, Test Rapido e Calibrazione Fine

* **Verifica stato live & buffer RAM:**
  Apri (da sessione autenticata) `GET /api/v1/recordings/status` oppure guarda la voce **Archivio NVR** nel pannello **Sicurezza → Impostazioni** della PWA: vedrai `state: "running"`, i MB occupati dal ring-buffer RAM e lo spazio libero su disco.
* **Test manuale registrazione Main Event (Admin):**
  ```bash
  POST /api/v1/recordings/Cam_Carraio/trigger
  # Body opzionale: {"duration_sec": 15}
  ```
  Verrà scaricato immediatamente il pre-buffer RAM degli ultimi 10s su `D:\Surveillance\Cam_Carraio\YYYY-MM-DD\main_*.mp4` e sulla timeline 3D comparirà la barra ambra **`REPLAY HD`**.
* **Calibrazione allineamento temporale `Sub ↔ Main`:**
  Se noti un leggero anticipo/ritardo fisso (es. 200–400 ms) nel passaggio tra `sub` e `main` di una specifica telecamera, compensalo in `.env` senza riavviare i flussi delle camere:
  ```env
  SPATIAL_NVR_CAMERA_CLOCK_OFFSETS=Cam_Ingresso:main=-250,Cam_Stradina:main=-250
  ```
* **Manutenzione manuale (Admin):**
  `POST /api/v1/recordings/maintenance/prune` forza la riconciliazione di eventuali file esterni e l'esecuzione immediata della pulizia disco.
