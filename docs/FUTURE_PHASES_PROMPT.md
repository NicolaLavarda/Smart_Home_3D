# 🚀 Prompt Master per la Prossima Sessione: Pipeline Video, Computer Vision Spaziale e Replay (x, y, z, t)

Copia e incolla il testo seguente in una nuova sessione per avviare l'implementazione delle 4 fasi avanzate.

---

```markdown
Agisci come Senior Full-Stack IoT Architect, Computer Vision Spaziale Engineer e Principal Graphics/Systems Engineer (Three.js / WebGL / Python / MQTT / Time-Series DB).

## 1. Contesto e Stato Attuale del Repository
In questa repository è già operativo e collaudato il nucleo del **Digital Twin 3D** della mia casa (giardino + piano terra), con le seguenti caratteristiche:
1. **Blender come Single Source of Truth (SSoT):** Tutte le Custom Properties (`ha_entity`, `collider_role: "ground"`, `ha_camera_entity`) sono definite nel file `.blend`, esportate headless tramite `npm run build:model` in `public/models/house_optimized.glb` e cataloga nel manifesto `public/models/scene_manifest.json`.
2. **Home Assistant Bidirezionale Live:** Connessione WebSocket attiva su `http://192.168.86.24:8123` via `home-assistant-js-websocket`, con controllo interattivo di luci (`light.bancone`, `light.forno`), cancello motorizzato animato (`switch.switch_casa_interruttore_1`), smart TV e telecamera carraio.
3. **Motore Spazio-Temporale 3D (Frontend Ready):** `src/spatial/CameraProjector.js`, `TrajectoryRenderer.js` e `TimelineController.js` sono già implementati con raycasting 2D $(u,v) \to 3D\,(x,y,z)$ sulle mesh calpestabili, frustum ottico della telecamera `Cam_Carraio` e scrubber temporale (attualmente alimentato da dati sintetici di test).

---

## 2. Obiettivo della Sessione
Dobbiamo trasformare il prototipo frontend in una **piattaforma di produzione end-to-end** per la videosorveglianza spaziale e il tracking spazio-temporale continuo. Il sistema deve gestire l'attuale telecamera `Cam_Carraio` montata sul pilastrino del cancello e scalare in modo modulare fino a **5-6 telecamere totali** nei prossimi mesi, con predisposizione nativa per **Face Recognition** (riconoscimento dei componenti della mia famiglia) e Re-ID multi-camera.

Dobbiamo progettare e implementare le 4 fasi mancanti:
1. **Live Video Stream a Bassa Latenza dentro Three.js:** Visualizzazione del feed video reale dentro il drawer modale di `Cam_Carraio` e modalità POV 3D.
2. **Microservizio Ingestion Eventi CV (MQTT $\to$ Coordinate 3D):** Servizio asincrono che riceve i bounding box 2D $[ymin, xmin, ymax, xmax]$, applica la matrice di proiezione e pubblica eventi 3D uniformi.
3. **Database Serie-Temporali Spazio-Temporale:** Persistenza ad alte prestazioni di tracce $(x, y, z, t)$ per replay storico istantaneo tramite lo scrubber di Three.js.
4. **Calibrazione Geometrica ad Alta Precisione delle Telecamere:** Procedura guidata e validazione millimetrica tra il mondo reale e le coordinate virtuali di Blender.

---

## 3. Requisito Fondamentale: Scalabilità e Architettura ad Oggetti (OOP)
L'architettura deve essere rigorosamente modulare e orientata agli oggetti:
- **Data Models fortemente tipizzati:** Utilizza strutture dati estendibili (Pydantic in Python / interfacce TS/JS nel frontend) per disaccoppiare la sorgente di Computer Vision (Frigate, YOLO, FaceNet, ecc.) dal motore 3D:
  - `Detection2D`: `{ id, camera_id, timestamp, bbox: [ymin, xmin, ymax, xmax], class: "person"|"car"|"dog", confidence, face_embedding?, identity? }`
  - `SpatialPoint3D`: `{ entity_id, class, x, y, z, t, camera_id, is_grounded: bool, identity: string|null, metadata: dict }`
  - `Tracklet3D`: cronologia interpolata, velocità vettoriale, direzione e stato di permanenza.
- **Predisposizione per Face Recognition:** Il sistema deve prevedere fin da subito il campo `identity` e `face_attributes`, in modo da poter inserire in seguito un modulo di riconoscimento volti addestrato sui membri della famiglia senza alterare il database o l'interfaccia 3D.

---

## 4. Fase 0: Audit Preliminare e Domande di Allineamento (NON SCRIVERE CODICE PRIMA)
Prima di iniziare lo sviluppo, analizza lo stato della repository e forniscimi:
1. **La lista esatta delle variabili d'ambiente da aggiungere al file `.env`** (es. credenziali broker Mosquitto MQTT su Home Assistant, porte, URL stream RTSP, token aggiuntivi).
2. **Consulenza Architettonica per la Gestione Video e CV (1 -> 6 Telecamere):**
   - Attualmente NON gestisco ancora i flussi video con Frigate o software dedicati, ma ho l'integrazione telecamera nativa su Home Assistant (`camera.carraio_scorrevole`).
   - Spiegami e confronta in modo oggettivo l'architettura consigliata (es. **Frigate NVR con go2rtc integrato** vs **go2rtc standalone** vs **Add-on Home Assistant**). Qual è la configurazione più affidabile, fluida a bassissima latenza (WebRTC sub-second) e con il minor consumo di CPU/GPU per gestire l'espansione a 5-6 telecamere 4K/2K?
3. **Scelta del Database Serie-Temporali:**
   - Confronta le opzioni per la persistenza di coordinate $(x, y, z, t)$ (es. SQLite con estensione spaziale vs QuestDB vs InfluxDB vs TimescaleDB/PostgreSQL), valutando semplicità di manutenzione in ambito home automation locale e velocità di query per lo scrubber di Three.js.
4. **Piano Operativo Dettagliato a Fasi (Roadmap di Implementazione):**
   - Suddiviso in step atomici, verificabili e retrocompatibili con quanto già funzionante nel repository.
```

