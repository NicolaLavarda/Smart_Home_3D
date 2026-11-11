# 🏗️ Smart Devices Decentralized Architecture

Questo documento descrive l'architettura modulare, decentralizzata e scalabile implementata in Smart Home 3D Digital Twin per la gestione dei dispositivi interattivi.

---

## 🎯 Obiettivi di Design

1. **Decentralizzazione & Separazione delle Responsabilità (SoC)**:
   - Ogni dispositivo smart possiede una cartella dedicata in `src/devices/<device_name>/`.
   - Tutta la logica di business, le chiamate API/servizi di Home Assistant, la grafica 3D procedurale e i componenti UI del pannello/telecomando sono confinati nel rispettivo modulo.
   - `EntityBinder` e `DeviceModals` non contengono più logica monolitica cablata, ma fungono da orchestratori agnostici.

2. **Scalabilità Futura**:
   - Aggiungere un nuovo dispositivo (es. **Lavastoviglie**, **Robot Aspirapolvere**, **Telecamere Frigate**, **Climatizzazione**) richiede solo l'estensione di `BaseDeviceController` e la registrazione in `DeviceRegistry`.

---

## 📁 Struttura Directory

```
src/
└── devices/
    ├── BaseDeviceController.js       # Contratto e classe base astratta
    ├── DeviceRegistry.js             # Registro singleton & orchestratore
    └── tv/                           # Mini-progetto dedicato alla Smart TV
        ├── index.js                  # Export pubblico del modulo
        ├── TVController.js           # Controller di business & integrazione HA
        ├── TVScreenRenderer.js       # Render grafico 3D procedurale (1024x576 CanvasTexture)
        ├── TVModal.js                # Pannello modale di controllo live
        ├── TVRemote.js               # Telecomando virtuale LG Magic Remote
        └── webos_commands.js         # Costanti comandi webOS e sorgenti
```

---

## 🔌 Il Modulo TV (`src/devices/tv/`)

### 1. Accensione Corretta via Wake-on-LAN
- **Entità WoL:** `button.wake_on_lan_58_fd_b1_ae_99_79`
- **Servizio HA:** `button.press`
- **Comportamento:** Quando la TV è spenta o in standby (con scheda di rete a basso consumo), l'accensione invia il magic packet Wake-on-LAN su `button.wake_on_lan_58_fd_b1_ae_99_79`.
- **Spegnimento:** `media_player.turn_off` su `media_player.lg_webos_smart_tv` (o comando webOS `system/turnOff`).

### 2. Rendering 3D Dinamico dello Schermo (`TVScreenRenderer.js`)
Lo schermo Three.js (`TV_Salotto_Screen`) monta una `THREE.CanvasTexture` dinamica a 1024x576 che riflette in tempo reale cosa si sta guardando:
- **Live TV / Digitale Terrestre:** Grafica trasmissione broadcast con badge rete (Rai 1, Rai 2, Rai 3, Canale 5, Italia 1, LA7), orario, punto rosso "DIRETTA", titolo del programma e barra progresso.
- **Netflix:** Layout cinematografico scuro, logo rosso "NETFLIX", titolo serie/film, badge 4K HDR Dolby Atmos e timeline rossa.
- **Prime Video:** Gradiente blu scuro Amazon, logo "prime video", badge Prime Original.
- **YouTube:** Layout dark, logo YouTube con play button, titolo video e canale.
- **Disney+:** Gradiente galattico Disney, titolo e badge IMAX Enhanced.
- **Spotify:** Equalizer audio animato a 28 bande dinamiche, titolo brano e artista in ascolto.
- **Browser Web:** Barra degli indirizzi con lucchetto SSL (`https://www.google.com`) e pagina Google.
- **Standby / Spenta:** Pannello nero OLED con riflesso vetro antiriflesso e LED rosso di standby in basso a destra.

### 3. Telecomando Virtuale Integrato (`TVRemote.js`)
Accessibile con un click dal pannello della TV ("Mostra Telecomando Virtuale LG"):
- **Tasto Power & Eco:** Accensione WoL, spegnimento e toggle schermo OLED (`TURN_OFF_SCREEN` / `TURN_ON_SCREEN`).
- **Tastierino Numerico (0-9):** Selezione diretta canale / input caratteri.
- **Colonne Rocker:** Volume + / Volume - / Mute Audio, Canale ▲ / Canale ▼ / Guida programmi.
- **Navigazione D-Pad & Wheel:** Frecce direzionali Su/Giù/Sinistra/Destra e rotella centrale **OK** (`SEND_ENTER`), Tasto Home e Back.
- **Controlli Media:** Play, Pausa, Stop, Rewind ⏪, Fast Forward ⏩.
- **Tasti Rapidi App:** Netflix, Prime Video, Disney+, YouTube.
- **Strumenti Avanzati webOS:**
  - *Invia Notifica Toast:* invia un messaggio popup direttamente sullo schermo della TV reale tramite `system.notifications/createToast`.
  - *Apri URL:* apre qualsiasi pagina web (es. `https://www.google.com`) nel browser della TV tramite `system.launcher/open`.

---

## 🚀 Come Aggiungere un Nuovo Dispositivo in Futuro

### Esempio: Modulo Lavastoviglie (`src/devices/dishwasher/`)

1. **Crea la cartella** `src/devices/dishwasher/` con la classe che estende `BaseDeviceController`:
```javascript
import { BaseDeviceController } from '../BaseDeviceController.js';

export class DishwasherController extends BaseDeviceController {
  constructor() {
    super('dishwasher', {
      name: 'Lavastoviglie Cucina',
      primaryEntityId: 'sensor.lavastoviglie_stato_di_funzionamento',
      associatedEntityIds: ['sensor.lavastoviglie_programma', 'sensor.lavastoviglie_tempo_rimanente'],
    });
  }

  bind3D(meshes, scene, context) {
    // Esempio: gestisci l'animazione di apertura dello sportello o led frontale
  }

  update3D(stateObj, allEntities) {
    // Esempio: aggiorna colore emissivo o texture display lavastoviglie
  }

  renderModal(container, entity, context) {
    // Esempio: mostra fase del ciclo (Lavaggio, Risciacquo, Asciugatura), tempo residuo e comandi
    container.innerHTML = `
      <div class="control-row">
        <label>Stato</label>
        <span>${entity.state}</span>
      </div>
      ...
    `;
  }
}
```

2. **Registra il dispositivo in `DeviceRegistry.js`**:
```javascript
import { DishwasherController } from './dishwasher/DishwasherController.js';

initDefaultDevices() {
  this.register(new TVController());
  this.register(new DishwasherController()); // <-- Aggiunto!
}
```

3. **Pronto!**
   - Cliccando sulla mesh della lavastoviglie nella scena 3D o sul suo badge, `DeviceRegistry` intercetta automaticamente il click e apre il pannello dedicato della lavastoviglie!

