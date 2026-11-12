# 📋 Mappatura Dispositivi ed Entità Home Assistant $\to$ 3D Digital Twin

> **Istruzioni per l'utente:**
> Questo file contiene tutte le entità fisiche e i sensori presenti nel tuo Home Assistant.
> 1. Per ogni entità che vuoi posizionare nel 3D, cambia **`Azione:`** da **`ignora`** a **`mappa`**.
> 2. Compila **`Posizione 3D:`** descrivendo dove si trova l'oggetto (es. *"Parete nord del salotto a 1.2m"*, *"Soffitto centro cucina"*, *"Tavolino vicino al divano"*).
> 3. Compila **`Funzionamento / Note:`** indicando cosa deve fare quando interagisci (es. *"Click per accendere/spegnere"*, *"Mostra badge temperatura in tempo reale"*, *"Apri modal per scegliere sorgente/volume"*).
> 4. Quando hai finito, salva il file e dimmi di procedere: leggerò questo file e applicherò i collegamenti e i modelli 3D corrispondenti!

---

## 🟢 Entità Già Mappate nel 3D (Riferimento Attivo)

* **`light.bancone`** — *Bancone* (Stato live: `on`)
  - **Oggetto 3D / Ruolo:** Isola_Lampada_Cono_1, Isola_Lampada_Cono_2 (Luci sopra il bancone cucina)
  - **Azione:** `GIA_MAPPATO`

* **`light.forno`** — *Forno* (Stato live: `on`)
  - **Oggetto 3D / Ruolo:** Lampadario_Coppa_1..4, Lampadario_Pranzo_Asta (Lampadario sopra tavolo pranzo)
  - **Azione:** `GIA_MAPPATO`

* **`light.portico`** — *Portico* (Stato live: `on`)
  - **Oggetto 3D / Ruolo:** Pillar_Portico_1 (Illuminazione portico)
  - **Azione:** `GIA_MAPPATO`

* **`switch.switch_casa_interruttore_1`** — *Cancello* (Stato live: `off`)
  - **Oggetto 3D / Ruolo:** Gate_Leaf_L, Gate_Leaf_R (Ante cancello carraio animato)
  - **Azione:** `GIA_MAPPATO`

* **`media_player.smart_tv_lg_oled_2`** — *Smart TV LG oled* (Stato live: `idle`)
  - **Oggetto 3D / Ruolo:** TV_Salotto_Screen, TV_Salotto_Bezel (Smart TV salotto)
  - **Azione:** `GIA_MAPPATO`

* **`camera.carraio_scorrevole`** — *Carraio Scorrevole* (Stato live: `idle`)
  - **Oggetto 3D / Ruolo:** Cam_Carraio (Telecamera reale montata su palo pilastrino a Z=2.10m)
  - **Azione:** `GIA_MAPPATO`

* **`vacuum.deebot`** — *Ecovacs Deebot* (Stato live: `docked`)
  - **Oggetto 3D / Ruolo:** Ecovacs_Deebot_Body, Ecovacs_Deebot_Dock_Base, Ecovacs_Deebot_Dock_Tower, Ecovacs_Deebot_Lidar (Robot aspirapolvere e stazione su parete Est sala da pranzo vicino al caminetto)
  - **Azione:** `GIA_MAPPATO`

---

## 💡 1. Luci (light.*) (15 entità)

### `light.smart_plug_in_unit_switch_3`
- **Nome HA:** Tavolo
- **Stato Live:** `on`
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** è un'unica entità ma accende 6 piccole luci a soffitto nel salotto messe a formare un rettangolo 2x3 che copre tutto il salotto
- **Funzionamento / Note:** 

### `light.forno` `[COLLEGATO]`
- **Nome HA:** Forno
- **Stato Live:** `on`
- **Azione:** `GIA_MAPPATO` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Lampadario_Coppa_1..4, Lampadario_Pranzo_Asta (Lampadario sopra tavolo pranzo)
- **Funzionamento / Note:** Già funzionante

### `light.bancone` `[COLLEGATO]`
- **Nome HA:** Bancone
- **Stato Live:** `on`
- **Azione:** `GIA_MAPPATO` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Isola_Lampada_Cono_1, Isola_Lampada_Cono_2 (Luci sopra il bancone cucina)
- **Funzionamento / Note:** Già funzionante

### `light.luci_esterne`
- **Nome HA:** Luci esterne
- **Stato Live:** `off`
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** ci sono 4 lampioncini messi così: uno nella curva interna del vialetto che porta dal canelletto al portico, uno 3 metri più a est di quello, 1 nella cura interna della stradina che va dal canello al garage e 1 a 6 metri a est da quest ultimo. Inoltre controlla oltre ai 4 lampioncini anche 4 luci equidistanziate lungo il muro est del giardino area 2. Ti allego in chat l'immagine di come sono fatti i 4 lampioncini che ho in giro per il giardino come ti dicevo.
- **Funzionamento / Note:** 

### `light.portico` `[COLLEGATO]`
- **Nome HA:** Portico
- **Stato Live:** `on`
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** è un'unica entità ma accende due lampade messe in alto a muro uno sull'angolo in basso a sinistra e uno in alto a destra guardando la piantina del portico (il portico è chiaramente la zona tra la casa e la lavanderia)
- **Funzionamento / Note:** 

### `light.led`
- **Nome HA:** Led
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `light.telecamera_floodlight`
- **Nome HA:** Telecamera Floodlight
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `light.smart_switch_21033073248029258h1848e1e968958d_dnd`
- **Nome HA:** Area 3 Dnd
- **Stato Live:** `on` (classe: DNDMode)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `light.albero_dnd`
- **Nome HA:** Albero Dnd
- **Stato Live:** `unavailable` (classe: DNDMode)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `light.smart_switch_2307180542542458070248e1e9d1bc0b_dnd`
- **Nome HA:** Caldaia Dnd
- **Stato Live:** `on` (classe: DNDMode)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `light.smart_switch_2307186117120258070248e1e9d1bc14_dnd`
- **Nome HA:** Area 1 Dnd
- **Stato Live:** `on` (classe: DNDMode)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `light.smart_switch_2307180028397658070248e1e9d1bc12_dnd`
- **Nome HA:** Area 2 Dnd
- **Stato Live:** `on` (classe: DNDMode)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `light.carraio_faretto`
- **Nome HA:** Carraio Faretto
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `light.1`
- **Nome HA:** Divani
- **Stato Live:** `unavailable`
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** devo ancora sistemare mobili e divani in salotto ma intanto mettila sul muro a est del salotto a metà tra la porta in vetro grande e l'angolo a nord-est del salotto
- **Funzionamento / Note:** 

### `light.2`
- **Nome HA:** Divani
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** devo ancora sistemare mobili e divani in salotto ma intanto mettila sul muro a nord del salotto a metà
- **Funzionamento / Note:** 

---

## 🔌 2. Interruttori, Prese e Relè (switch.*) (59 entità)

### `switch.smart_plug_in_unit_switch`
- **Nome HA:** Bancone
- **Stato Live:** `on` (classe: outlet)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.smart_plug_in_unit_switch_2`
- **Nome HA:** Luci esterne
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.smart_plug_in_unit_switch_3`
- **Nome HA:** Tavolo
- **Stato Live:** `on` (classe: outlet)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.smart_plug_in_unit`
- **Nome HA:** Forno
- **Stato Live:** `on` (classe: outlet)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.portico`
- **Nome HA:** Portico
- **Stato Live:** `on` (classe: outlet)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.valvola_acqua_calda`
- **Nome HA:** Valvola Acqua Calda
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.switch_casa_interruttore_1` `[COLLEGATO]`
- **Nome HA:** Cancello
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Al centro del cancello quello grande a sinistra
- **Funzionamento / Note:**

### `switch.switch_casa_interruttore_2`
- **Nome HA:** Cancelletto
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Al cancelletto quello piccolo a destra
- **Funzionamento / Note:**

### `switch.switch_casa_interruttore_3`
- **Nome HA:** Portone
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Al centro del portone del garage
- **Funzionamento / Note:** 

### `switch.albero_esterno`
- **Nome HA:** Albero esterno
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.led`
- **Nome HA:** Led
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.presepe`
- **Nome HA:** Presepe
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_registrazione_video`
- **Nome HA:** Telecamera Registrazione video
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_registrazione_del_movimento`
- **Nome HA:** Telecamera Registrazione del movimento
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_capovolgi`
- **Nome HA:** Telecamera Capovolgi
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_filigrana_temporale`
- **Nome HA:** Telecamera Filigrana temporale
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_tracciamento_del_movimento`
- **Nome HA:** Telecamera Tracciamento del movimento
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_allarme_di_movimento`
- **Nome HA:** Telecamera Allarme di movimento
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.giardino_telecamera_use_motion_detection_zone`
- **Nome HA:** Telecamera Use motion detection zone
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.deebot_advanced_mode`
- **Nome HA:** Deebot Modalità avanzata
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.deebot_carpet_auto_boost_suction`
- **Nome HA:** Deebot Aspirazione automatica potenziata del tappeto
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.smart_switch_area3`
- **Nome HA:** Area 3
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Giardino Area 3 (Prato Nord e Viale Ovest), 5 gettini pop-up da 25cm disposti lungo il prato alle coordinate:
  1. `Sprinkler_Area3_1`: (-3.52, -0.58, 0.00) - Angolo Nord-Ovest vicino cancello pedonale
  2. `Sprinkler_Area3_2`: (-0.67, -5.40, 0.00) - Angolo Nord-Est vicino facciata ovest casa
  3. `Sprinkler_Area3_3`: (-5.09, -7.96, 0.00) - Bordo ovest lungo cordolo viale carrabile
  4. `Sprinkler_Area3_4`: (-0.85, -14.95, 0.00) - Parete ovest lavanderia
  5. `Sprinkler_Area3_5`: (4.15, -16.02, 0.00) - A sud della lavanderia vicino al portico
- **Funzionamento / Note:** Controlla l'irrigazione dell'Area 3 del giardino. Quando acceso (`on`), alza in pop-up i 5 gettini di 25cm e attiva l'animazione particellare dei getti d'acqua ad arco balistico che bagnano il prato verde. Cliccando su qualsiasi gettino si apre il pannello modale con controlli live e inquadrature 3D dedicate. 

### `switch.albero`
- **Nome HA:** Albero
- **Stato Live:** `unavailable` (classe: outlet)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.smart_switch_2307180542542458070248e1e9d1bc0b_config_overtemp_enable`
- **Nome HA:** Caldaia Config overtemp enable
- **Stato Live:** `on` (classe: switch)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.smart_switch_caldaia`
- **Nome HA:** Caldaia
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** in lavanderia alla sinistra del box doccia bisogna ricostruire accumulo e caldaia e posizionare sulla parete di fronte questo interruttore per accendere/spegnere la caldaia
- **Funzionamento / Note:** 

### `switch.smart_switch_2307186117120258070248e1e9d1bc14_config_overtemp_enable`
- **Nome HA:** Area 1 Config overtemp enable
- **Stato Live:** `on` (classe: switch)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.smart_switch_area1`
- **Nome HA:** Area 1
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Giardino Area 1 (Prato Sud), 4 gettini pop-up da 25cm disposti lungo il prato alle coordinate:
  1. `Sprinkler_Area1_1`: (-7.39, -26.45, 0.00) - Angolo Sud-Ovest della proprietà
  2. `Sprinkler_Area1_2`: (-0.16, -21.50, 0.00) - Bordo nord sotto la curva del viale carrabile
  3. `Sprinkler_Area1_3`: (5.00, -24.69, 0.00) - Centro sud del prato
  4. `Sprinkler_Area1_4`: (12.30, -24.82, 0.00) - Angolo est sotto la parete sud del garage
- **Funzionamento / Note:** Controlla l'irrigazione dell'Area 1 del giardino (Prato Sud). Quando acceso (`on`), alza in pop-up i 4 gettini di 25cm e attiva l'animazione dei getti d'acqua con traiettoria parabolica e oscillazione angolare sul prato verde.

### `switch.smart_switch_2307180028397658070248e1e9d1bc12_config_overtemp_enable`
- **Nome HA:** Area 2 Config overtemp enable
- **Stato Live:** `on` (classe: switch)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.smart_switch_area2`
- **Nome HA:** Area 2
- **Stato Live:** `off` (classe: outlet)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Giardino Area 2 (Corte Est tra casa e garage), 2 gettini pop-up da 25cm disposti agli angoli opposti:
  1. `Sprinkler_Area2_1`: (6.89, -8.57, 0.00) - Angolo Nord-Ovest vicino al portico e facciata sud casa
  2. `Sprinkler_Area2_2`: (13.28, -16.58, 0.00) - Angolo Sud-Est vicino al muro est e parete nord garage
- **Funzionamento / Note:** Controlla l'irrigazione dell'Area 2 del giardino (Corte Est). Quando acceso (`on`), alza in pop-up i 2 gettini di 25cm e attiva l'animazione di irrigazione con getti d'acqua incrociati a 90° sul prato verde. 

### `switch.lavastoviglie_vario_speed`
- **Nome HA:** Lavastoviglie Vario speed +
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.lavastoviglie_silence_on_demand`
- **Nome HA:** Lavastoviglie Silence on demand
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.lavastoviglie_half_load`
- **Nome HA:** Lavastoviglie Half load
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.lavastoviglie_extra_dry`
- **Nome HA:** Lavastoviglie Extra dry
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.lavastoviglie_hygiene`
- **Nome HA:** Lavastoviglie Hygiene +
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.volti_ha_carraio_carraio_analisi`
- **Nome HA:** Volti HA - Carraio Carraio Analisi
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.lavastoviglie_potenza`
- **Nome HA:** Lavastoviglie Potenza
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_privacy`
- **Nome HA:** Telecamera Privacy
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_media_sync`
- **Nome HA:** Telecamera Media Sync
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_lens_distortion_correction`
- **Nome HA:** Telecamera Lens Distortion Correction
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_indicator_led`
- **Nome HA:** Telecamera Indicator LED
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_record_audio`
- **Nome HA:** Telecamera Record Audio
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_diagnose_mode`
- **Nome HA:** Telecamera Diagnose Mode
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_privacy_zones`
- **Nome HA:** Telecamera Privacy Zones
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_flip`
- **Nome HA:** Telecamera Flip
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_auto_track`
- **Nome HA:** Telecamera Auto Track
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_notifications`
- **Nome HA:** Telecamera Notifications
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_rich_notifications`
- **Nome HA:** Telecamera Rich Notifications
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_automatically_upgrade_firmware`
- **Nome HA:** Telecamera Automatically Upgrade Firmware
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_automatic_reboot`
- **Nome HA:** Telecamera Automatic Reboot
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.telecamera_record_to_sd_card`
- **Nome HA:** Telecamera Record to SD Card
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.carraio_infrared_lights_in_night_mode`
- **Nome HA:** Carraio Luci a infrarossi in modalità notturna
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.carraio_registra_audio`
- **Nome HA:** Carraio Registra audio
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.carraio_sirena_su_evento`
- **Nome HA:** Carraio Sirena su evento
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.carraio_e_mail_sull_evento`
- **Nome HA:** Carraio E-mail sull'evento
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.carraio_caricamento_ftp`
- **Nome HA:** Carraio Caricamento FTP
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.carraio_notifiche_push`
- **Nome HA:** Carraio Notifiche push
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.carraio_registra`
- **Nome HA:** Carraio Registra
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.1_smooth_transitions`
- **Nome HA:** 1 Smooth transitions
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `switch.2_smooth_transitions`
- **Nome HA:** 2 Smooth transitions
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

---

## 📺 3. Smart TV, Casse e Media Player (media_player.*) (15 entità)

### `media_player.lg_webos_smart_tv` `[COLLEGATO]`
- **Nome HA:** LG webOS Smart TV
- **Stato Live:** `disponibile` (classe: tv)
- **Azione:** `GIA_MAPPATO`
- **Oggetto 3D / Ruolo:** TV_Salotto_Screen, TV_Salotto_Bezel (Texture 3D dinamica Live TV / Streaming)
- **Funzionamento / Note:** Controllato tramite il controller modulare `src/devices/tv/TVController.js`. Supporta visualizzazione dinamica della trasmissione in corso (Canali DVB-T2, Netflix, Prime Video, YouTube, Disney+, Spotify, Browser), switch sorgenti, regolazione volume e pannello Telecomando Virtuale LG Magic Remote. Accensione gestita via Wake-on-LAN (`button.wake_on_lan_58_fd_b1_ae_99_79`). 

### `media_player.gruppo_nest`
- **Nome HA:** Gruppo Nest
- **Stato Live:** `off` (classe: speaker)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.display3`
- **Nome HA:** Display3
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.display2`
- **Nome HA:** Display2
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.display`
- **Nome HA:** Display
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.display3_2`
- **Nome HA:** Display3
- **Stato Live:** `idle` (classe: speaker)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.display2_2`
- **Nome HA:** Display2
- **Stato Live:** `idle` (classe: speaker)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.display_2`
- **Nome HA:** Display
- **Stato Live:** `idle` (classe: speaker)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.pc_3nest`
- **Nome HA:** PC+3Nest
- **Stato Live:** `idle` (classe: speaker)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.pc_1nest`
- **Nome HA:** PC+1Nest
- **Stato Live:** `idle` (classe: speaker)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.web_edge_on_windows`
- **Nome HA:** Web (Edge on Windows)
- **Stato Live:** `unavailable` (classe: speaker)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.display_sendspin`
- **Nome HA:** Display (Sendspin)
- **Stato Live:** `unavailable` (classe: speaker)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.gruppo_nest_2`
- **Nome HA:** Gruppo Nest
- **Stato Live:** `off` (classe: speaker)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `media_player.smart_tv_lg_oled_2` `[COLLEGATO]`
- **Nome HA:** Smart TV LG oled
- **Stato Live:** `idle` (classe: speaker)
- **Azione:** `GIA_MAPPATO` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** TV_Salotto_Screen, TV_Salotto_Bezel (Smart TV salotto)
- **Funzionamento / Note:** Già funzionante

### `media_player.macbook_air_di_giorgia`
- **Nome HA:** 32ES400_Series
- **Stato Live:** `unavailable` (classe: speaker)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

---

## 📹 4. Telecamere di Sicurezza (camera.*) (9 entità)

### `camera.carraio_analisi`
- **Nome HA:** Carraio Analisi
- **Stato Live:** `idle`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `camera.telecamera`
- **Nome HA:** Telecamera
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `camera.volti_ha_carraio_carraio_annotata`
- **Nome HA:** Volti HA - Carraio Carraio Annotata
- **Stato Live:** `idle`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `camera.telecamera_hd_stream`
- **Nome HA:** Babalù
- **Stato Live:** `idle`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `camera.telecamera_sd_stream`
- **Nome HA:** Telecamera SD Stream
- **Stato Live:** `idle`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `camera.carraio_scorrevole` `[COLLEGATO]`
- **Nome HA:** Carraio Scorrevole
- **Stato Live:** `idle`
- **Azione:** `GIA_MAPPATO` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Cam_Carraio (Telecamera reale montata su palo pilastrino a Z=2.10m)
- **Funzionamento / Note:** Già funzionante

### `camera.carraio_trasparente`
- **Nome HA:** Carraio Trasparente
- **Stato Live:** `idle`
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** è la telecamera che ho predisposto sul pilastrino tra cancello e cancelletto
- **Funzionamento / Note:** 

### `camera.carraio_istantanee_scorrevoli`
- **Nome HA:** Carraio Istantanee scorrevoli
- **Stato Live:** `idle`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `camera.carraio_istantanee_trasparente`
- **Nome HA:** Carraio Istantanee trasparente
- **Stato Live:** `idle`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

---

## 🚨 7. Sensori di Presenza, Movimento e Apertura (binary_sensor.*) (31 entità)

### `binary_sensor.irrigazione_attiva`
- **Nome HA:** Irrigazione attiva
- **Stato Live:** `off` (classe: running)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.nicola_android_auto`
- **Nome HA:** Nicola Android Auto
- **Stato Live:** `off` (classe: connectivity)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.nicola_headphones`
- **Nome HA:** Nicola Headphones
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.nicola_is_charging`
- **Nome HA:** Nicola Is charging
- **Stato Live:** `off` (classe: plug)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.nicola_bluetooth_state`
- **Nome HA:** Nicola Bluetooth state
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.nicola_nfc_state`
- **Nome HA:** Nicola NFC state
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.deebot_mop_attached`
- **Nome HA:** Deebot Mocio montato
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.volti_ha_carraio_carraio_volto_rilevato`
- **Nome HA:** Volti HA - Carraio Carraio Volto Rilevato
- **Stato Live:** `off` (classe: occupancy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.salotto_ruview_salotto_stanza_stanza_attiva_salotto`
- **Nome HA:** RuView Salotto (Stanza) Stanza Attiva (Salotto)
- **Stato Live:** `unknown` (classe: occupancy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.salotto_ruview_salotto_nodo_1_presenza_nodo_1`
- **Nome HA:** RuView Salotto - Nodo 1 Presenza (Nodo 1)
- **Stato Live:** `unknown` (classe: occupancy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.salotto_ruview_salotto_nodo_2_presenza_nodo_2`
- **Nome HA:** RuView Salotto - Nodo 2 Presenza (Nodo 2)
- **Stato Live:** `unknown` (classe: occupancy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.salotto_ruview_salotto_nodo_3_presenza_nodo_3`
- **Nome HA:** RuView Salotto - Nodo 3 Presenza (Nodo 3)
- **Stato Live:** `unknown` (classe: occupancy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.salotto_ruview_salotto_nodo_4_presenza_nodo_4`
- **Nome HA:** RuView Salotto - Nodo 4 Presenza (Nodo 4)
- **Stato Live:** `unknown` (classe: occupancy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.lavastoviglie_connettivita`
- **Nome HA:** Lavastoviglie Connettività
- **Stato Live:** `on` (classe: connectivity)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.lavastoviglie_controllo_remoto`
- **Nome HA:** Lavastoviglie Controllo remoto
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.lavastoviglie_avvio_remoto`
- **Nome HA:** Lavastoviglie Avvio remoto
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.telecamera_noise`
- **Nome HA:** Telecamera Noise
- **Stato Live:** `unavailable` (classe: sound)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.carraio_movimento`
- **Nome HA:** Carraio Movimento
- **Stato Live:** `off` (classe: motion)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.carraio_persona`
- **Nome HA:** Carraio Persona
- **Stato Live:** `off` (classe: motion)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.carraio_veicolo`
- **Nome HA:** Carraio Veicolo
- **Stato Live:** `off` (classe: motion)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.carraio_animale`
- **Nome HA:** Carraio Animale
- **Stato Live:** `off` (classe: motion)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.onhub_stato_della_wan`
- **Nome HA:** OnHub Stato della WAN
- **Stato Live:** `on` (classe: connectivity)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.1_overheated`
- **Nome HA:** 1 Overheated
- **Stato Live:** `unavailable` (classe: problem)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.1_cloud_connection`
- **Nome HA:** 1 Cloud connection
- **Stato Live:** `unavailable` (classe: connectivity)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.2_overheated`
- **Nome HA:** 2 Overheated
- **Stato Live:** `unavailable` (classe: problem)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.2_cloud_connection`
- **Nome HA:** 2 Cloud connection
- **Stato Live:** `unavailable` (classe: connectivity)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.telecamera_cell_motion_detection`
- **Nome HA:** Telecamera Cell Motion Detection
- **Stato Live:** `unavailable` (classe: motion)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.telecamera_motion_alarm`
- **Nome HA:** Telecamera Motion Alarm
- **Stato Live:** `unavailable` (classe: motion)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.telecamera_cell_motion_detection_2`
- **Nome HA:** Telecamera Cell Motion Detection
- **Stato Live:** `on` (classe: motion)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.telecamera_motion_alarm_2`
- **Nome HA:** Telecamera Motion Alarm
- **Stato Live:** `on` (classe: motion)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `binary_sensor.backups_stale`
- **Nome HA:** Backups Stale
- **Stato Live:** `off` (classe: problem)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

---

## 📊 8. Sensori Ambientali, Consumi ed Energetici (sensor.*) (160 entità)

### `sensor.home_assistant_core_cpu_percent`
- **Nome HA:** Home Assistant Core Percentuale CPU
- **Stato Live:** `4.17` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.home_assistant_core_memory_percent`
- **Nome HA:** Home Assistant Core Percentuale di memoria
- **Stato Live:** `20.85` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.minuti_caldaia_accesa`
- **Nome HA:** minuti caldaia accesa
- **Stato Live:** `0.0` h (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.backup_backup_manager_state`
- **Nome HA:** Backup Backup Manager state
- **Stato Live:** `idle` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.backup_next_scheduled_automatic_backup`
- **Nome HA:** Backup Next scheduled automatic backup
- **Stato Live:** `2026-11-13T04:08:45+00:00` (classe: timestamp)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.backup_last_successful_automatic_backup`
- **Nome HA:** Backup Last successful automatic backup
- **Stato Live:** `2026-11-11T04:09:52+00:00` (classe: timestamp)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.backup_last_attempted_automatic_backup`
- **Nome HA:** Backup Last attempted automatic backup
- **Stato Live:** `2026-11-11T04:03:54+00:00` (classe: timestamp)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.statistiche_temperatura_caldaia_giornaliera`
- **Nome HA:** Statistiche Temperatura Caldaia Giornaliera
- **Stato Live:** `43.73` °C (classe: temperature)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.statistiche_temperatura_accumulo_alto_giornaliera`
- **Nome HA:** Statistiche Temperatura Accumulo Alto Giornaliera
- **Stato Live:** `39.92` °C (classe: temperature)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.temperatura_calda_caldaia`
- **Nome HA:** Temperatura Calda Caldaia
- **Stato Live:** `44.3` °C
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.temperatura_esterna_attuale`
- **Nome HA:** Temperatura esterna attuale
- **Stato Live:** `12.5` °C (classe: temperature)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.temperatura_acqua_fredda_stimata`
- **Nome HA:** Temperatura acqua fredda stimata
- **Stato Live:** `12` °C (classe: temperature)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.litri_acqua_calda`
- **Nome HA:** Litri acqua calda
- **Stato Live:** `68` L
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.minuti_doccia_disponibili_accumulo`
- **Nome HA:** Minuti doccia disponibili Accumulo
- **Stato Live:** `8` min (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.minuti_doccia_disponibili_caldaia`
- **Nome HA:** Minuti doccia disponibili Caldaia
- **Stato Live:** `0` min (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.minuti_doccia_disponibili_caldaia2`
- **Nome HA:** Minuti doccia disponibili Caldaia2
- **Stato Live:** `0` min (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.minuti_doccia_disponibili`
- **Nome HA:** Minuti doccia disponibili
- **Stato Live:** `8.0` min (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.minuti_di_attesa`
- **Nome HA:** Minuti di attesa
- **Stato Live:** `0` min (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.minuti_doccia_disponibili_caldaia_con_inerzia`
- **Nome HA:** Minuti doccia disponibili caldaia con inerzia
- **Stato Live:** `0` min (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.statistiche_temperatura_accumulo_basso_giornaliera`
- **Nome HA:** Statistiche Temperatura Accumulo Basso Giornaliera
- **Stato Live:** `14.58` °C (classe: temperature)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.statistiche_temperatura_accumulo_basso_settimanale`
- **Nome HA:** Statistiche Temperatura Accumulo Basso Settimanale
- **Stato Live:** `15.94` °C (classe: temperature)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.statistiche_temperatura_accumulo_alto_settimanale`
- **Nome HA:** Statistiche Temperatura Accumulo Alto Settimanale
- **Stato Live:** `34.91` °C (classe: temperature)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.statistiche_temperatura_caldaia_settimanale`
- **Nome HA:** Statistiche Temperatura Caldaia Settimanale
- **Stato Live:** `37.35` °C (classe: temperature)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.pixel_8a_battery_level`
- **Nome HA:** Pixel 8a Battery level
- **Stato Live:** `79` % (classe: battery)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.pixel_8a_battery_state`
- **Nome HA:** Pixel 8a Battery state
- **Stato Live:** `discharging` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.pixel_8a_charger_type`
- **Nome HA:** Pixel 8a Charger type
- **Stato Live:** `none` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.nicola_volume_level_accessibility`
- **Nome HA:** Nicola Volume level accessibility
- **Stato Live:** `7`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.nicola_battery_level`
- **Nome HA:** Nicola Battery level
- **Stato Live:** `72` % (classe: battery)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.nicola_battery_state`
- **Nome HA:** Nicola Battery state
- **Stato Live:** `discharging` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.nicola_charger_type`
- **Nome HA:** Nicola Charger type
- **Stato Live:** `none` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.nicola_battery_temperature`
- **Nome HA:** Nicola Battery temperature
- **Stato Live:** `24.3` °C (classe: temperature)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.nicola_battery_power`
- **Nome HA:** Nicola Battery power
- **Stato Live:** `0.98` W (classe: power)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.nicola_remaining_charge_time`
- **Nome HA:** Nicola Remaining charge time
- **Stato Live:** `unavailable` min (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.nicola_bluetooth_connection`
- **Nome HA:** Nicola Bluetooth connection
- **Stato Live:** `1` connection(s)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.mi_note_10_battery_level`
- **Nome HA:** Mi Note 10 Battery level
- **Stato Live:** `65` % (classe: battery)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.mi_note_10_battery_state`
- **Nome HA:** Mi Note 10 Battery state
- **Stato Live:** `discharging` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.mi_note_10_charger_type`
- **Nome HA:** Mi Note 10 Charger type
- **Stato Live:** `none` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.tablet_dania_battery_level`
- **Nome HA:** Tablet Dania Battery level
- **Stato Live:** `88` % (classe: battery)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.tablet_dania_battery_state`
- **Nome HA:** Tablet Dania Battery state
- **Stato Live:** `discharging` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.tablet_dania_charger_type`
- **Nome HA:** Tablet Dania Charger type
- **Stato Live:** `none` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.google_pixel_watch_2_battery_level`
- **Nome HA:** Google Pixel Watch 2 Battery level
- **Stato Live:** `98` % (classe: battery)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.google_pixel_watch_2_battery_state`
- **Nome HA:** Google Pixel Watch 2 Battery state
- **Stato Live:** `discharging` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.google_pixel_watch_2_charger_type`
- **Nome HA:** Google Pixel Watch 2 Charger type
- **Stato Live:** `none` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.pixel_10a_battery_level`
- **Nome HA:** Pixel 10a Battery level
- **Stato Live:** `95` % (classe: battery)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.pixel_10a_battery_state`
- **Nome HA:** Pixel 10a Battery state
- **Stato Live:** `discharging` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.pixel_10a_charger_type`
- **Nome HA:** Pixel 10a Charger type
- **Stato Live:** `none` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.shower_time_daily`
- **Nome HA:** shower_time_daily
- **Stato Live:** `0.163413522777778` h
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.electricity_maps_intensita_della_co2`
- **Nome HA:** Electricity Maps Intensità della CO2
- **Stato Live:** `376.0` gCO2eq/kWh
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.electricity_maps_percentuale_della_rete_di_combustibili_fossili`
- **Nome HA:** Electricity Maps Percentuale della rete di combustibili fossili
- **Stato Live:** `71.8` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.energy_production_today`
- **Nome HA:** Solar production forecast Produzione di energia stimata - oggi
- **Stato Live:** `0.0` kWh (classe: energy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.energy_production_today_remaining`
- **Nome HA:** Solar production forecast Produzione di energia stimata - rimanente oggi
- **Stato Live:** `0.0` kWh (classe: energy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.energy_production_tomorrow`
- **Nome HA:** Solar production forecast Produzione di energia stimata - domani
- **Stato Live:** `0.0` kWh (classe: energy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.power_highest_peak_time_today`
- **Nome HA:** Solar production forecast Ora di picco di massima potenza - oggi
- **Stato Live:** `2026-11-11T06:07:23+00:00` (classe: timestamp)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.power_highest_peak_time_tomorrow`
- **Nome HA:** Solar production forecast Ora di picco di massima potenza - domani
- **Stato Live:** `2026-11-12T06:08:47+00:00` (classe: timestamp)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.power_production_now`
- **Nome HA:** Solar production forecast Produzione di potenza stimata - ora
- **Stato Live:** `0` W (classe: power)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.energy_current_hour`
- **Nome HA:** Solar production forecast Produzione di energia stimata - quest'ora
- **Stato Live:** `0.0` kWh (classe: energy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.energy_next_hour`
- **Nome HA:** Solar production forecast Produzione di energia stimata - ora successiva
- **Stato Live:** `0.0` kWh (classe: energy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.hp_deskjet_3700_series_tempo_di_attivita`
- **Nome HA:** HP DeskJet 3700 series Tempo di attività
- **Stato Live:** `2026-11-07T09:51:21+00:00` (classe: timestamp)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.hp_deskjet_3700_series_black_ink`
- **Nome HA:** HP DeskJet 3700 series black ink
- **Stato Live:** `10` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.hp_deskjet_3700_series_tri_color_ink`
- **Nome HA:** HP DeskJet 3700 series tri-color ink
- **Stato Live:** `90` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.shower_time_weekly`
- **Nome HA:** shower_time_weekly
- **Stato Live:** `0.546535393611111` h
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.shower_time_monthly`
- **Nome HA:** shower_time_monthly
- **Stato Live:** `3.35934867333333300` h
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.temperatura_caldaia`
- **Nome HA:** Temperatura Caldaia
- **Stato Live:** `44.2` °C (classe: temperature)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Sulla parte alta della caldaia in posizione centrale
- **Funzionamento / Note:** 

### `sensor.temperatura_accumulo_alto`
- **Nome HA:** Temperatura Accumulo Alto
- **Stato Live:** `53.1` °C (classe: temperature)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** nella parte superiore dell'accumulo
- **Funzionamento / Note:** 

### `sensor.temperatura_accumulo_basso`
- **Nome HA:** Temperatura Accumulo Basso
- **Stato Live:** `14.2` °C (classe: temperature)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** nella parte inferiore dell'accumulo
- **Funzionamento / Note:** 

### `sensor.variazione_temperatura_caldaia`
- **Nome HA:** Variazione Temperatura Caldaia
- **Stato Live:** `0.03` °C/min
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:**
- **Funzionamento / Note:** 

### `sensor.variazione_temperatura_accumulo_alto`
- **Nome HA:** Variazione Temperatura Accumulo Alto
- **Stato Live:** `0.22` °C/min
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.variazione_temperatura_accumulo_basso`
- **Nome HA:** Variazione Temperatura Accumulo Basso
- **Stato Live:** `0.06` °C/min
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.variazione2_temperatura_caldaia`
- **Nome HA:** Variazione2 Temperatura Caldaia
- **Stato Live:** `0.07` °C/min^2
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.variazione2_temperatura_accumulo_alto`
- **Nome HA:** Variazione2 Temperatura Accumulo Alto
- **Stato Live:** `-0.0` °C/min^2
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.variazione2_temperatura_accumulo_basso`
- **Nome HA:** Variazione2 Temperatura Accumulo Basso
- **Stato Live:** `0.04` °C/min^2
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.temperatura_pannelli_solari`
- **Nome HA:** Temperatura Pannelli Solari
- **Stato Live:** `unknown` °C (classe: temperature)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.segnale_wifi_esp32`
- **Nome HA:** Segnale WiFi ESP32
- **Stato Live:** `36` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.hp_deskjet_3700_series`
- **Nome HA:** HP DeskJet 3700 series
- **Stato Live:** `idle` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.albero_energia_totale`
- **Nome HA:** Albero esterno Energia totale
- **Stato Live:** `0` kWh (classe: energy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.led_corrente`
- **Nome HA:** Led Corrente
- **Stato Live:** `0.0` A (classe: current)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.led_potenza`
- **Nome HA:** Led Potenza
- **Stato Live:** `0.0` W (classe: power)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.led_tensione`
- **Nome HA:** Led Tensione
- **Stato Live:** `228.6` V (classe: voltage)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.led_energia_totale`
- **Nome HA:** Led Energia totale
- **Stato Live:** `0` kWh (classe: energy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.presepe_corrente`
- **Nome HA:** Presepe Corrente
- **Stato Live:** `0.0` A (classe: current)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.presepe_potenza`
- **Nome HA:** Presepe Potenza
- **Stato Live:** `0.0` W (classe: power)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.presepe_tensione`
- **Nome HA:** Presepe Tensione
- **Stato Live:** `223.5` V (classe: voltage)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.presepe_energia_totale`
- **Nome HA:** Presepe Energia totale
- **Stato Live:** `0` kWh (classe: energy)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_area_cleaned`
- **Nome HA:** Deebot Area pulita
- **Stato Live:** `69` m² (classe: area)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_cleaning_duration`
- **Nome HA:** Deebot Durata pulizia
- **Stato Live:** `54.0` min (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_total_area_cleaned`
- **Nome HA:** Deebot Area totale pulita
- **Stato Live:** `20088` m² (classe: area)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_total_cleaning_duration`
- **Nome HA:** Deebot Total cleaning duration
- **Stato Live:** `363.691944444444` h (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_total_cleanings`
- **Nome HA:** Deebot Pulizie totali
- **Stato Live:** `516`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_batteria`
- **Nome HA:** Deebot Batteria
- **Stato Live:** `100` % (classe: battery)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_main_brush_lifespan`
- **Nome HA:** Deebot Durata spazzola principale
- **Stato Live:** `56.7` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_filter_lifespan`
- **Nome HA:** Deebot Durata filtro
- **Stato Live:** `96.49` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_round_mop_lifespan`
- **Nome HA:** Deebot Durata del mocio rotondo
- **Stato Live:** `99.94` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_side_brush_lifespan`
- **Nome HA:** Deebot Durata spazzola laterale
- **Stato Live:** `97.09` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.deebot_unit_care_lifespan`
- **Nome HA:** Deebot Unit care lifespan
- **Stato Live:** `85.94` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.smart_switch_21033073248029258h1848e1e968958d_signal_strength`
- **Nome HA:** Area 3 Signal strength
- **Stato Live:** `73` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.smart_switch_21033083227840258h1848e1e96893d3_sensor_protocol`
- **Nome HA:** Albero Sensor protocol
- **Stato Live:** `disconnected` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.albero_signal_strength`
- **Nome HA:** Albero Signal strength
- **Stato Live:** `unavailable` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.smart_switch_2307180542542458070248e1e9d1bc0b_config_overtemp_type`
- **Nome HA:** Caldaia Config overtemp type
- **Stato Live:** `-1` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.smart_switch_2307180542542458070248e1e9d1bc0b_signal_strength`
- **Nome HA:** Caldaia Signal strength
- **Stato Live:** `86` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.smart_switch_2307186117120258070248e1e9d1bc14_config_overtemp_type`
- **Nome HA:** Area 1 Config overtemp type
- **Stato Live:** `-1` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.smart_switch_2307186117120258070248e1e9d1bc14_signal_strength`
- **Nome HA:** Area 1 Signal strength
- **Stato Live:** `86` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.smart_switch_2307180028397658070248e1e9d1bc12_config_overtemp_type`
- **Nome HA:** Area 2 Config overtemp type
- **Stato Live:** `-1` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.smart_switch_2307180028397658070248e1e9d1bc12_signal_strength`
- **Nome HA:** Area 2 Signal strength
- **Stato Live:** `94` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.volti_ha_carraio_carraio_persone`
- **Nome HA:** Volti HA - Carraio Carraio Persone
- **Stato Live:** `Nessuno`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_stanza_zona_puntamento_salotto`
- **Nome HA:** RuView Salotto (Stanza) Zona Puntamento (Salotto)
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_1_movimento_nodo_1`
- **Nome HA:** RuView Salotto - Nodo 1 Movimento (Nodo 1)
- **Stato Live:** `unknown` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_1_energia_movimento_nodo_1`
- **Nome HA:** RuView Salotto - Nodo 1 Energia Movimento (Nodo 1)
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_1_battito_cardiaco_nodo_1`
- **Nome HA:** RuView Salotto - Nodo 1 Battito Cardiaco (Nodo 1)
- **Stato Live:** `unknown` bpm
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_1_respiro_nodo_1`
- **Nome HA:** RuView Salotto - Nodo 1 Respiro (Nodo 1)
- **Stato Live:** `unknown` bpm
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_1_segnale_wifi_rssi_nodo_1`
- **Nome HA:** RuView Salotto - Nodo 1 Segnale WiFi RSSI (Nodo 1)
- **Stato Live:** `unknown` dBm (classe: signal_strength)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_1_conteggio_persone_nodo_1`
- **Nome HA:** RuView Salotto - Nodo 1 Conteggio Persone (Nodo 1)
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_2_movimento_nodo_2`
- **Nome HA:** RuView Salotto - Nodo 2 Movimento (Nodo 2)
- **Stato Live:** `unknown` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_2_energia_movimento_nodo_2`
- **Nome HA:** RuView Salotto - Nodo 2 Energia Movimento (Nodo 2)
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_2_battito_cardiaco_nodo_2`
- **Nome HA:** RuView Salotto - Nodo 2 Battito Cardiaco (Nodo 2)
- **Stato Live:** `unknown` bpm
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_2_respiro_nodo_2`
- **Nome HA:** RuView Salotto - Nodo 2 Respiro (Nodo 2)
- **Stato Live:** `unknown` bpm
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_2_segnale_wifi_rssi_nodo_2`
- **Nome HA:** RuView Salotto - Nodo 2 Segnale WiFi RSSI (Nodo 2)
- **Stato Live:** `unknown` dBm (classe: signal_strength)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_2_conteggio_persone_nodo_2`
- **Nome HA:** RuView Salotto - Nodo 2 Conteggio Persone (Nodo 2)
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_3_movimento_nodo_3`
- **Nome HA:** RuView Salotto - Nodo 3 Movimento (Nodo 3)
- **Stato Live:** `unknown` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.lavastoviglie_program_aborted`
- **Nome HA:** Lavastoviglie Program aborted
- **Stato Live:** `off` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.lavastoviglie_program_finished`
- **Nome HA:** Lavastoviglie Program finished
- **Stato Live:** `off` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.lavastoviglie_sale_quasi_vuoto`
- **Nome HA:** Lavastoviglie Sale quasi vuoto
- **Stato Live:** `off` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.lavastoviglie_brillantante_quasi_vuoto`
- **Nome HA:** Lavastoviglie Brillantante quasi vuoto
- **Stato Live:** `off` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.lavastoviglie_orario_di_fine_del_programma`
- **Nome HA:** Lavastoviglie Orario di fine del programma
- **Stato Live:** `unavailable` (classe: timestamp)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.lavastoviglie_avanzamento_del_programma`
- **Nome HA:** Lavastoviglie Avanzamento del programma
- **Stato Live:** `unavailable` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_3_energia_movimento_nodo_3`
- **Nome HA:** RuView Salotto - Nodo 3 Energia Movimento (Nodo 3)
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_3_battito_cardiaco_nodo_3`
- **Nome HA:** RuView Salotto - Nodo 3 Battito Cardiaco (Nodo 3)
- **Stato Live:** `unknown` bpm
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_3_respiro_nodo_3`
- **Nome HA:** RuView Salotto - Nodo 3 Respiro (Nodo 3)
- **Stato Live:** `unknown` bpm
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_3_segnale_wifi_rssi_nodo_3`
- **Nome HA:** RuView Salotto - Nodo 3 Segnale WiFi RSSI (Nodo 3)
- **Stato Live:** `unknown` dBm (classe: signal_strength)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_3_conteggio_persone_nodo_3`
- **Nome HA:** RuView Salotto - Nodo 3 Conteggio Persone (Nodo 3)
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_4_movimento_nodo_4`
- **Nome HA:** RuView Salotto - Nodo 4 Movimento (Nodo 4)
- **Stato Live:** `unknown` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_4_energia_movimento_nodo_4`
- **Nome HA:** RuView Salotto - Nodo 4 Energia Movimento (Nodo 4)
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_4_battito_cardiaco_nodo_4`
- **Nome HA:** RuView Salotto - Nodo 4 Battito Cardiaco (Nodo 4)
- **Stato Live:** `unknown` bpm
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_4_respiro_nodo_4`
- **Nome HA:** RuView Salotto - Nodo 4 Respiro (Nodo 4)
- **Stato Live:** `unknown` bpm
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_4_segnale_wifi_rssi_nodo_4`
- **Nome HA:** RuView Salotto - Nodo 4 Segnale WiFi RSSI (Nodo 4)
- **Stato Live:** `unknown` dBm (classe: signal_strength)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.salotto_ruview_salotto_nodo_4_conteggio_persone_nodo_4`
- **Nome HA:** RuView Salotto - Nodo 4 Conteggio Persone (Nodo 4)
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.lavastoviglie_stato_di_funzionamento`
- **Nome HA:** Lavastoviglie Stato di funzionamento
- **Stato Live:** `ready` (classe: enum)
- **Azione:** `mappa` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** Al centro della lavastoviglie posizionata lungo il muro dove c'è anche il lavandino in cucina esattamente proprio poco più a ovest del lavandino
- **Funzionamento / Note:** 

### `sensor.lavastoviglie_porta`
- **Nome HA:** Lavastoviglie Porta
- **Stato Live:** `open` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.telecamera_network_ssid`
- **Nome HA:** Telecamera Network SSID
- **Stato Live:** `Google WiFi`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.telecamera_link_type`
- **Nome HA:** Telecamera Link Type
- **Stato Live:** `wifi`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.telecamera_rssi`
- **Nome HA:** Telecamera RSSI
- **Stato Live:** `-46` dBm
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.telecamera_last_automatic_reboot_time`
- **Nome HA:** Telecamera Last Automatic Reboot Time
- **Stato Live:** `2025-01-14T02:18:17+00:00` (classe: timestamp)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.telecamera_recordings_synchronization`
- **Nome HA:** Telecamera Recordings Synchronization
- **Stato Live:** `Idle`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.carraio_day_night_state`
- **Nome HA:** Carraio Day night state
- **Stato Live:** `day` (classe: enum)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.carraio_utilizzo_della_cpu`
- **Nome HA:** Carraio Utilizzo della CPU
- **Stato Live:** `57` %
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_dati_ricevuti`
- **Nome HA:** OnHub Dati ricevuti
- **Stato Live:** `4294967295` B (classe: data_size)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_dati_inviati`
- **Nome HA:** OnHub Dati inviati
- **Stato Live:** `4294967295` B (classe: data_size)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_pacchetti_ricevuti`
- **Nome HA:** OnHub Pacchetti ricevuti
- **Stato Live:** `46111759` packets
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_pacchetti_inviati`
- **Nome HA:** OnHub Pacchetti inviati
- **Stato Live:** `26827982` packets
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_ip_esterno`
- **Nome HA:** OnHub IP esterno
- **Stato Live:** `192.168.8.100`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_tempo_di_attivita`
- **Nome HA:** OnHub Tempo di attività
- **Stato Live:** `353396` s (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_stato_della_wan`
- **Nome HA:** OnHub Stato della WAN
- **Stato Live:** `Connected`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_velocita_di_scaricamento`
- **Nome HA:** OnHub Velocità di scaricamento
- **Stato Live:** `0.0` KiB/s (classe: data_rate)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_velocita_di_caricamento`
- **Nome HA:** OnHub Velocità di caricamento
- **Stato Live:** `0.0` KiB/s (classe: data_rate)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_velocita_di_scaricamento_dei_pacchetti`
- **Nome HA:** OnHub Velocità di scaricamento dei pacchetti
- **Stato Live:** `89.0330959117442` packets/s
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.onhub_velocita_di_caricamento_dei_pacchetti`
- **Nome HA:** OnHub Velocità di caricamento dei pacchetti
- **Stato Live:** `113.833029778587` packets/s
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.1_signal_level`
- **Nome HA:** 1 Signal level
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.2_signal_level`
- **Nome HA:** 2 Signal level
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.durata_doccia_filtrata`
- **Nome HA:** Durata doccia filtrata
- **Stato Live:** `unavailable` h
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.durata_doccia_oggi`
- **Nome HA:** Durata doccia oggi
- **Stato Live:** `unavailable` h (classe: duration)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `sensor.backup_state`
- **Nome HA:** Backup State
- **Stato Live:** `backed_up`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

---

## 🔔 9. Sirene e Notificatori (siren.*) (2 entità)

### `siren.telecamera_siren`
- **Nome HA:** Telecamera Siren
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `siren.carraio_sirena`
- **Nome HA:** Carraio Sirena
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

---

## 🔘 10. Pulsanti e Comandi Rapidi (button.*) (37 entità)

### `button.wake_on_lan_58_fd_b1_ae_99_79` `[COLLEGATO]`
- **Nome HA:** Wake on LAN TV
- **Stato Live:** `disponibile`
- **Azione:** `GIA_MAPPATO`
- **Funzionamento / Note:** Utilizzato da `TVController` e dal pannello modale / telecomando virtuale per inviare il pacchetto magic packet Wake-on-LAN per accendere l'LG Smart TV quando è spenta. 

### `button.deebot_relocate`
- **Nome HA:** Deebot Trasferire
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.area_3_refresh`
- **Nome HA:** Area 3 Refresh
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.area_3_reload`
- **Nome HA:** Area 3 Reload
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.albero_refresh`
- **Nome HA:** Albero Refresh
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.albero_reload`
- **Nome HA:** Albero Reload
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.caldaia_refresh`
- **Nome HA:** Caldaia Refresh
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.caldaia_reload`
- **Nome HA:** Caldaia Reload
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.smart_switch_2307186117120258070248e1e9d1bc14_refresh`
- **Nome HA:** Area 1 Refresh
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.smart_switch_2307186117120258070248e1e9d1bc14_reload`
- **Nome HA:** Area 1 Reload
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.smart_switch_2307180028397658070248e1e9d1bc12_refresh`
- **Nome HA:** Area 2 Refresh
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.smart_switch_2307180028397658070248e1e9d1bc12_reload`
- **Nome HA:** Area 2 Reload
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.lavastoviglie_stop_program`
- **Nome HA:** Lavastoviglie Stop program
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.telecamera_reboot`
- **Nome HA:** Telecamera Reboot
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.telecamera_format_sd_card`
- **Nome HA:** Telecamera Format SD Card
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.telecamera_manual_alarm_start`
- **Nome HA:** Telecamera Manual Alarm Start
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.telecamera_manual_alarm_stop`
- **Nome HA:** Telecamera Manual Alarm Stop
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.telecamera_sync_time`
- **Nome HA:** Telecamera Sync Time
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.telecamera_calibrate`
- **Nome HA:** Telecamera Calibrate
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.telecamera_move_up`
- **Nome HA:** Telecamera Move Up
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.telecamera_move_down`
- **Nome HA:** Telecamera Move Down
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.telecamera_move_right`
- **Nome HA:** Telecamera Move Right
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.telecamera_move_left`
- **Nome HA:** Telecamera Move Left
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.carraio_riavvia`
- **Nome HA:** Carraio Riavvia
- **Stato Live:** `unknown` (classe: restart)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.bancone_identifica`
- **Nome HA:** Bancone Identifica
- **Stato Live:** `unavailable` (classe: identify)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.luci_esterne_identifica`
- **Nome HA:** Luci Esterne Identifica
- **Stato Live:** `unavailable` (classe: identify)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.tavolo_identifica`
- **Nome HA:** Tavolo Identifica
- **Stato Live:** `unavailable` (classe: identify)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.display3_brano_preferito_attuale`
- **Nome HA:** Display3 Brano preferito attuale
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.display2_brano_preferito_attuale`
- **Nome HA:** Display2 Brano preferito attuale
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.display_brano_preferito_attuale`
- **Nome HA:** Display Brano preferito attuale
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.pc_3nest_brano_preferito_attuale`
- **Nome HA:** PC+3Nest Brano preferito attuale
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.pc_1nest_brano_preferito_attuale`
- **Nome HA:** PC+1Nest Brano preferito attuale
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.web_edge_on_windows_brano_preferito_attuale`
- **Nome HA:** Web (Edge on Windows) Brano preferito attuale
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.display_sendspin_brano_preferito_attuale`
- **Nome HA:** Display (Sendspin) Brano preferito attuale
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.gruppo_nest_brano_preferito_attuale`
- **Nome HA:** Gruppo Nest Brano preferito attuale
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.smart_tv_lg_oled_brano_preferito_attuale_2`
- **Nome HA:** Smart TV LG oled Brano preferito attuale
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `button.macbook_air_di_giorgia_brano_preferito_attuale`
- **Nome HA:** 32ES400_Series Brano preferito attuale
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

---

## ⚙️ 11. Altri Dispositivi e Scene (select, number, scene, automation) (115 entità)

### `script.parladisplay`
- **Nome HA:** ParlaDisplay
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `script.parladisplay_modificabile`
- **Nome HA:** ParlaDisplay (modificabile)
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `script.get_tv`
- **Nome HA:** Get TV
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `script.input_socket`
- **Nome HA:** Input Socket
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `script.mqtt_publish_k`
- **Nome HA:** mqtt_publish_k
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `script.avvio_programma`
- **Nome HA:** Avvio Programma
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.irrigazione_attiva`
- **Nome HA:** Irrigazione
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.area_1`
- **Nome HA:** Enable Area 1
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.area_2`
- **Nome HA:** Enable Area 2
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.area_3`
- **Nome HA:** Enable Area 3
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.doccia_in_corso`
- **Nome HA:** Doccia in corso
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.gestione_automatica_acqua_calda`
- **Nome HA:** Gestione automatica acqua calda
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.volto_rilevato_codeprojectai`
- **Nome HA:** input_boolean.volto_rilevato_codeprojectai
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.script_in_corso`
- **Nome HA:** input_boolean.script_in_corso
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.ferma_script_codeprojectai`
- **Nome HA:** input_boolean.ferma_script_codeprojectai
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.veicolo_in_posizione_ingresso`
- **Nome HA:** input_boolean.veicolo_in_posizione_ingresso
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.abbaglianti_rilevati`
- **Nome HA:** input_boolean.abbaglianti_rilevati
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.programma_lavastoviglie`
- **Nome HA:** Programma Lavastoviglie
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.smart_plug_in_unit_power_on_behavior_on_startup`
- **Nome HA:** Bancone Power-on behavior
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.smart_plug_in_unit_power_on_behavior_on_startup_2`
- **Nome HA:** Luci Esterne Power-on behavior
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.smart_plug_in_unit_power_on_behavior_on_startup_3`
- **Nome HA:** Tavolo Power-on behavior
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.smart_plug_in_unit_comportamento_dell_accensione_all_avvio`
- **Nome HA:** Forno Power-on behavior
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.smart_plug_in_unit_comportamento_dell_accensione_all_avvio_2`
- **Nome HA:** Portico Power-on behavior
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.albero_comportamento_di_accensione`
- **Nome HA:** Albero esterno Power-on behavior
- **Stato Live:** `last`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.led_comportamento_di_accensione`
- **Nome HA:** Led Power-on behavior
- **Stato Live:** `last`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.presepe_comportamento_di_accensione`
- **Nome HA:** Presepe Power-on behavior
- **Stato Live:** `last`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_modalita_di_registrazione`
- **Nome HA:** Telecamera Modalità di registrazione
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_visione_notturna`
- **Nome HA:** Telecamera Visione notturna
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_sensibilita_di_rilevamento_del_movimento`
- **Nome HA:** Telecamera Sensibilità di rilevamento del movimento
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `scene.blocca_cancello`
- **Nome HA:** Blocca cancello
- **Stato Live:** `2025-02-11T20:25:06.771527+00:00`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.deebot_water_flow_level`
- **Nome HA:** Deebot Water flow level
- **Stato Live:** `medium`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.deebot_active_map`
- **Nome HA:** Deebot Active map
- **Stato Live:** `Piano terra`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.disattiva_telecamera_in_casa`
- **Nome HA:** Disattiva telecamera in casa
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.accendi_telecamera_quando_fuori_di_casa`
- **Nome HA:** Accendi telecamera quando fuori di casa
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.invia_valore_k_a_mqtt`
- **Nome HA:** Invia valore k a MQTT
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.invia_valore_tempo_ciclo_a_mqtt`
- **Nome HA:** Invia valore tempo_ciclo a MQTT
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.invia_valore_options_a_mqtt`
- **Nome HA:** Invia valore options a MQTT
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.notifica_volume_display_al_57`
- **Nome HA:** Messaggio Google Nest Hub per sapere acqua calda
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.debug_minuti_doccia_disponibili`
- **Nome HA:** Debug Minuti Doccia Disponibili
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.gestione_richiesta_doccia`
- **Nome HA:** Gestione richiesta doccia
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.spegni_caldaia_al_termine_timer`
- **Nome HA:** Spegni caldaia
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.time_analysis`
- **Nome HA:** Invia valore time_analysis a MQTT
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.doccia_iniziata`
- **Nome HA:** Doccia iniziata
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.doccia_finita`
- **Nome HA:** Doccia finita
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.salva_media_temp_giornaliera`
- **Nome HA:** Salva media temp giornaliera
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.salva_media_temp_settimanale`
- **Nome HA:** Salva media temp settimanale
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.salva_media_temp_mensile`
- **Nome HA:** Salva media temp mensile
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.controllo_valvola_acqua_calda`
- **Nome HA:** Controllo valvola acqua calda
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.auto_manuale_acqua_calda`
- **Nome HA:** Auto/manuale acqua calda
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.accensione_programmata_caldaia`
- **Nome HA:** Accensione programmata caldaia
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.gestione_irrigazione`
- **Nome HA:** Garden Irrigation Management
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.esclusione_irrigazione_simultanea`
- **Nome HA:** Esclusione Irrigazione Simultanea
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.spegnimento_irrigazione`
- **Nome HA:** Spegnimento Irrigazione
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.avvia_codeprojectai_loop`
- **Nome HA:** Avvia CodeProjectAI Loop
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.termina_script`
- **Nome HA:** Termina script
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.apri_cancelletto_se_persona_riconosciuta`
- **Nome HA:** Apri Cancelletto se Persona Riconosciuta
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.mostra_volto_rilevato_su_display`
- **Nome HA:** Mostra volto su display + notifiche ai telefoni
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.apri_cancello_se_targa_riconosciuta`
- **Nome HA:** Apri Cancello se Targa Riconosciuta
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.spegnimento_script_in_corso_dopo_130s`
- **Nome HA:** Termina script_in_corso dopo 40s
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.apri_cancelletto_da_notifica`
- **Nome HA:** Apri cancelletto da notifica
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.spegnimento_automatico_area_irrigazione_dopo_90_min`
- **Nome HA:** Spegnimento automatico area irrigazione dopo 90 min
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.ferma_script_codeproject_ai_se_non_c_e_piu_nessuno`
- **Nome HA:** Termina script se non c'è più nessuno
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.notifica_spostamento_persone`
- **Nome HA:** Notifica spostamento mamma
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.incrementa_volto_cache`
- **Nome HA:** Incrementa volto cache
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.pulizia_log_script_python`
- **Nome HA:** Pulizia log script python
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.flash_telecamera_per_segnare_script_in_corso`
- **Nome HA:** Flash telecamera per segnare script in corso
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.doccia_aggiungi_durata_valida_al_totale_giornaliero`
- **Nome HA:** Doccia - Aggiungi durata valida al totale giornaliero
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.doccia_azzera_contatore_giornaliero_durata_valida`
- **Nome HA:** Doccia - Azzera contatore giornaliero durata valida
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.notifica_spostamento_papa`
- **Nome HA:** Notifica spostamento papà
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.analisi_ai_ogni_20_minuti_telecamera_tapo`
- **Nome HA:** Analisi AI ogni 20 minuti - Telecamera Tapo
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.controllo_luci_albero`
- **Nome HA:** Controllo Luci Albero
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.avviso_aggiunta_legna_stufa`
- **Nome HA:** Stufa avviso aggiunta legna
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.stufa_sta_scaldando_a_sufficenza`
- **Nome HA:** Stufa sta scaldando a sufficenza
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.spegnimento_programmato_caldaia`
- **Nome HA:** Spegnimento programmato caldaia
- **Stato Live:** `off`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.web_app_impianto_termico`
- **Nome HA:** Web app - impianto termico
- **Stato Live:** `on`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.lavastoviglie_start_in_relative`
- **Nome HA:** Lavastoviglie Start in relative
- **Stato Live:** `0` s
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.lavastoviglie_active_program`
- **Nome HA:** Lavastoviglie Active program
- **Stato Live:** `unknown`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.lavastoviglie_programma_selezionato`
- **Nome HA:** Lavastoviglie Programma selezionato
- **Stato Live:** `dishcare_dishwasher_program_eco_50`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.telecamera_movement_angle`
- **Nome HA:** Telecamera Movement Angle
- **Stato Live:** `15`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.telecamera_motion_detection_digital_sensitivity`
- **Nome HA:** Telecamera Motion Detection - Digital Sensitivity
- **Stato Live:** `80`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.telecamera_microphone_volume`
- **Nome HA:** Telecamera Microphone - Volume
- **Stato Live:** `60`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.telecamera_speaker_volume`
- **Nome HA:** Telecamera Speaker - Volume
- **Stato Live:** `90`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_timezone`
- **Nome HA:** Telecamera Timezone
- **Stato Live:** `UTC+01:00 (Europe/Amsterdam)`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_automatic_reboot_time`
- **Nome HA:** Telecamera Automatic Reboot - Time
- **Stato Live:** `03:00 - 03:30`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_night_vision_switching`
- **Nome HA:** Telecamera Night Vision Switching
- **Stato Live:** `auto` (classe: night_vision)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_light_frequency`
- **Nome HA:** Telecamera Light Frequency
- **Stato Live:** `auto`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_automatic_alarm`
- **Nome HA:** Telecamera Automatic Alarm
- **Stato Live:** `off` (classe: alarm)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_siren_type`
- **Nome HA:** Telecamera Siren Type
- **Stato Live:** `Siren`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_motion_detection`
- **Nome HA:** Telecamera Motion Detection
- **Stato Live:** `high` (classe: motion_detection)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_baby_cry_detection`
- **Nome HA:** Telecamera Baby Cry Detection
- **Stato Live:** `off` (classe: baby_cry_detection)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_move_to_preset`
- **Nome HA:** Telecamera Move to Preset
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.telecamera_patrol_mode`
- **Nome HA:** Telecamera Patrol Mode
- **Stato Live:** `unavailable` (classe: patrol_mode)
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_accendi_la_luminosita_del_faretto`
- **Nome HA:** Carraio Accendi la luminosità del faretto
- **Stato Live:** `70`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_volume`
- **Nome HA:** Carraio Volume
- **Stato Live:** `100`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_sensibilita_al_movimento`
- **Nome HA:** Carraio Sensibilità al movimento
- **Stato Live:** `38`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_ai_person_sensitivity`
- **Nome HA:** Carraio AI person sensitivity
- **Stato Live:** `80`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_ai_vehicle_sensitivity`
- **Nome HA:** Carraio AI vehicle sensitivity
- **Stato Live:** `100`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_ai_animal_sensitivity`
- **Nome HA:** Carraio AI animal sensitivity
- **Stato Live:** `60`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_soglia_di_commutazione_giorno_notte`
- **Nome HA:** Carraio Soglia di commutazione giorno-notte
- **Stato Live:** `50`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_luminosita_dell_immagine`
- **Nome HA:** Carraio Luminosità dell'immagine
- **Stato Live:** `128`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_contrasto_dell_immagine`
- **Nome HA:** Carraio Contrasto dell'immagine
- **Stato Live:** `128`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_saturazione_dell_immagine`
- **Nome HA:** Carraio Saturazione dell'immagine
- **Stato Live:** `128`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `number.carraio_nitidezza_dell_immagine`
- **Nome HA:** Carraio Nitidezza dell'immagine
- **Stato Live:** `128`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.carraio_modalita_faretto`
- **Nome HA:** Carraio Modalità faretto
- **Stato Live:** `auto`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.carraio_modalita_giorno_notte`
- **Nome HA:** Carraio Modalità giorno-notte
- **Stato Live:** `auto`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.carraio_clear_frame_rate`
- **Nome HA:** Carraio Clear frame rate
- **Stato Live:** `10` Hz
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.carraio_fluent_frame_rate`
- **Nome HA:** Carraio Fluent frame rate
- **Stato Live:** `10` Hz
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.carraio_clear_bit_rate`
- **Nome HA:** Carraio Clear bit rate
- **Stato Live:** `6144` kbit/s
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.carraio_fluent_bit_rate`
- **Nome HA:** Carraio Fluent bit rate
- **Stato Live:** `256` kbit/s
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.carraio_post_recording_time`
- **Nome HA:** Carraio Post-recording time
- **Stato Live:** `15 Seconds`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.1_light_preset`
- **Nome HA:** 1 Light preset
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `select.2_light_preset`
- **Nome HA:** 2 Light preset
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `input_boolean.elaborazione_codeprojectai_completata`
- **Nome HA:** Elaborazione Completata
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `automation.notifica_spostamento_persona`
- **Nome HA:** Notifica spostamento persone
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

### `script.avvio_lavastoviglie`
- **Nome HA:** Avvio Lavastoviglie
- **Stato Live:** `unavailable`
- **Azione:** `ignora` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->
- **Posizione 3D:** 
- **Funzionamento / Note:** 

---

