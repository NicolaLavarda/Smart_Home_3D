# 🏡 Smart Home 3D - Digital Twin & Spatial CV Engine

> Piattaforma 3D interattiva basata su **Three.js**, **Blender Python API**, **Home Assistant (WebSocket)** e motore di ricostruzione spazio-temporale $(x, y, z, t)$ multi-camera.

---

## 📐 I Tre Pilastri Architetturali

1. **Blender come Single Source of Truth (SSoT):**  
   Nessuna coordinata 3D o nome mesh cablato nel codice web. Nomi, entità IoT, telecamere e superfici calpestabili derivano dalle **Custom Properties** del file `.blend` ed esportati in un unico manifesto strutturato (`public/models/scene_manifest.json`) e nel modello compresso (`public/models/house_optimized.glb`).
2. **Integrazione Bidirezionale Home Assistant:**  
   Sincronizzazione in tempo reale tramite `home-assistant-js-websocket`. Cliccando sui dispositivi 3D si pilotano luci (colore, luminosità ed emissione materiale), cancelli scorrevoli motorizzati, TV e telecamere. Include una modalità **Mock/Demo Offline reattiva** a zero configurazione.
3. **Motore Spazio-Temporale Multi-Camera $(x, y, z, t)$:**  
   Proiezione raycasting dai bounding box 2D $(u, v)$ delle telecamere di sicurezza sulle superfici calpestabili (`collider_role = "ground"`), visualizzazione 3D dei coni ottici (frustum) e timeline con scrubber per il replay storico dei movimenti di persone e veicoli.

---

## 🚀 Avvio Rapido

### Prerequisiti
- **Node.js** v18+ (testato con v24.11 LTS)
- **Blender** 4.x / 5.x LTS installato nel sistema

### Installazione e Avvio Frontend
```bash
# Installa le dipendenze
npm install

# Avvia il server di sviluppo Vite
npm run dev
```
Apri il browser su `http://localhost:3000`.

---

## 🛠️ Pipeline di Compilazione Blender -> Web

| Comando | Descrizione |
|---|---|
| `npm run setup:props` | Applica o aggiorna automaticamente le Custom Properties su `Smart_Home_3D.blend` |
| `npm run export:blend` | Esegue l'export headless in `.glb` con `export_extras=True` e genera `scene_manifest.json` |
| `npm run optimize:glb` | Ottimizza e comprime il file `.glb` tramite `@gltf-transform` preservando i metadati |
| `npm run build:model` | Esegue in sequenza export completo e compressione |
| `npm run build` | Compila la web app di produzione con Vite |

---

## 🏷️ Guida Blender: Come Taggare Nuovi Oggetti (SSoT)

Per aggiungere o modificare dispositivi nel modello 3D senza toccare una riga di codice JavaScript:

### Entità Configurate su Home Assistant Reale
- **`light.forno`**: Lampadario sopra al tavolo da pranzo/cucina (`Lampadario_Coppa_1..4`, `Lampadario_Pranzo_Asta`).
- **`light.bancone`**: Lampade a sospensione sopra al bancone dell'isola (`Isola_Lampada_Cono_1`, `Isola_Lampada_Cono_2`).
- **`light.portico`**: Illuminazione esterna portico.
- **`switch.switch_casa_interruttore_1`**: Cancello carraio automatico (`Gate_Leaf_L`, `Gate_Leaf_R`).
- **`media_player.smart_tv_lg_oled_2`**: Smart TV LG OLED in salotto.
- **`camera.carraio_scorrevole`**: Telecamera di sicurezza reale su palo montata sul pilastrino centrale tra cancello e cancelletto a quota $+2.10\,\text{m}$, orientata verso l'esterno.
- **`ha_action`** (`String`, opzionale, default `"toggle"`):  
  - `"toggle"`: Click rapido per accendere/spegnere o aprire/chiudere.
  - `"modal"`: Apre il pannello contestuale laterale (slider luminosità/colore, controlli TV, streaming telecamera).
- **`ha_ui_type`** (`String`, opzionale):  
  - `"light_emissive"`: Materiale emissivo sincronizzato + PointLight dinamica Three.js.
  - `"tv_display"`: Texture dinamica interattiva sullo schermo.
  - `"sliding_gate"`: Animazione di traslazione/apertura dell'anta.

### 2. Superfici Calpestabili (Ground Colliders)
Per consentire alle telecamere di proiettare i rilevamenti sul pavimento interno o sul giardino:
- Seleziona la mesh del pavimento o del prato.
- Aggiungi la Custom Property:
  - **`collider_role`** (`String`): `"ground"`

### 3. Telecamere di Sicurezza
Per ogni oggetto `Camera` in Blender destinato alla videosorveglianza:
- Aggiungi la Custom Property:
  - **`ha_camera_entity`** (`String`): `camera.cancello_ingresso`, `camera.salotto`, ecc.
  - **`ha_label`** (`String`): Nome descrittivo per l'interfaccia.
  - **`coverage_zone`** (`String`): Zona di copertura (es. `outdoor_front`, `indoor_living`).

### 4. Tre Regole Fondamentali in Blender
1. **Applica sempre Scala e Rotazione (`Ctrl + A → Apply Scale`):** Prima di salvare, verifica che la scala sia `(1.0, 1.0, 1.0)`, per garantire distanze metriche e raycasting accurati.
2. **Basso Poligonaggio per le Mesh di Collisione:** Mantieni le mesh del suolo pulite e semplici per raycasting istantaneo a 60 fps.
3. **Calibrazione con Background Image:** Imposta uno screenshot della telecamera reale come immagine di sfondo dell'oggetto Camera in Blender per allineare altezza, orientamento e FOV con la telecamera reale.

---

## 📹 Motore Spazio-Temporale Multi-Camera $(x, y, z, t)$

### Proiezione Matematica da 2D a 3D
Il modulo `CameraProjector.js` implementa:
$$\text{NDC}_x = 2u - 1, \quad \text{NDC}_y = 1 - 2v$$
dove $u, v \in [0, 1]$ rappresentano la base inferiore centrale del bounding box 2D rilevato nel flusso video. Un raggio viene generato dall'origine e orientamento della telecamera Blender nel mondo virtuale e interseca le mesh aventi `collider_role = "ground"`, restituendo le coordinate assolute $(x, y, z)$ in metri.

### Funzionalità della Timeline
- **Replay Storico:** Scrubber temporale, controllo velocità ($1\times, 2\times, 5\times$) e riproduzione fluida con interpolazione tra i fotogrammi.
- **Scie con Dissolvenza:** Tracce 3D dinamiche con gradiente temporale (massima opacità sulla posizione corrente, sfumata verso zero nel passato).
- **POV Telecamera:** Cliccando su una telecamera e premendo *"Entra nella vista POV"*, Three.js effettua una transizione fluida allineandosi esattamente al punto di vista e al campo visivo della telecamera reale.

---

## 🔌 Configurazione Home Assistant

Per collegare la tua istanza reale di Home Assistant, crea un file `.env` a partire da `.env.example`:

```env
VITE_HA_URL=ws://192.168.1.100:8123/api/websocket
VITE_HA_TOKEN=tuo_long_lived_access_token_qui
```

Se `.env` non è presente o la connessione WebSocket fallisce, l'applicazione si avvia automaticamente in **Modalità Demo Mock**, permettendo di testare tutte le interazioni, gli stati e le animazioni direttamente nel browser.

---

## 📂 Struttura del Progetto

```text
├── blender/
│   ├── Smart_Home_3D.blend        # File sorgente 3D di Blender (SSoT)
│   └── scripts/
│       ├── export_glb.py          # Script export headless GLB + scene_manifest.json
│       └── setup_ha_properties.py # Utility CLI per taggare Custom Properties
├── public/
│   └── models/
│       ├── house_optimized.glb    # Modello compresso per il web
│       ├── house_raw.glb          # Modello grezzo esportato da Blender
│       └── scene_manifest.json    # Catalogo entità HA, matrici camere, bounds
├── src/
│   ├── core/
│   │   ├── SceneManager.js        # WebGLRenderer, CSS2DRenderer, illuminazione giorno/notte
│   │   ├── AssetLoader.js         # Caricamento GLTF + DRACO + parsing userData
│   │   ├── CameraController.js    # OrbitControls + preset stanze + flyTo POV camera
│   │   └── InteractionManager.js  # Raycasting click/hover + badge 3D fluttuanti
│   ├── ha/
│   │   ├── HAClient.js            # WebSocket client HA + Mock/Demo engine reattivo
│   │   ├── EntityBinder.js        # Binding 3D luci, cancelli, TV e materiali emissivi
│   │   └── DeviceModals.js        # Drawer laterale glassmorphism per TV, telecamere, clima
│   ├── spatial/
│   │   ├── CameraProjector.js     # Proiezione UV -> (x,y,z) su ground collider + coni frustum
│   │   ├── TrajectoryRenderer.js  # Scie 3D con sfumatura temporale e marker stilizzati
│   │   └── TimelineController.js  # Scrubber temporale, controlli play/pause e dataset sintetico
│   ├── ui/
│   │   └── TopBar.js              # Barra superiore con status HA, toggle notte e telecamere
│   ├── style.css                  # Design system moderno glassmorphism
│   └── main.js                    # Bootstrap e orchestrazione dell'applicazione
├── tools/
│   └── optimize_glb.mjs           # Script di ottimizzazione @gltf-transform
├── package.json
├── vite.config.js
└── README.md
```

