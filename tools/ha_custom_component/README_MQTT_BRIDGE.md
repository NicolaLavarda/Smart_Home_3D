# 🚀 Ecovacs Deebot MQTT Telemetry Bridge per Home Assistant

Questo bridge consente di catturare in tempo reale le coordinate SLAM dToF del **DEEBOT X1 TURBO** dall'integrazione ufficiale Ecovacs e di pubblicarle come JSON strutturato sul broker MQTT locale sul topic:

```
homeassistant/deebot/pose
```

---

## 📂 Come installarlo in Home Assistant (1 minuto)

Dalla tua interfaccia Home Assistant puoi usare **Studio Code Server**, **File Editor** o il **Terminal** (presenti nella tua barra laterale):

1. Vai nella cartella di configurazione di Home Assistant:
   ```
   /config/custom_components/
   ```
   *(Se la cartella `custom_components` non esiste, creala).*

2. Copia la cartella `ecovacs_mqtt_bridge` dentro `custom_components/`:
   ```
   /config/custom_components/ecovacs_mqtt_bridge/
   ├── manifest.json
   └── __init__.py
   ```

3. Nel tuo file `configuration.yaml` aggiungi semplicemente una riga:
   ```yaml
   ecovacs_mqtt_bridge:
   ```

4. Riavvia Home Assistant (*Strumenti per sviluppatori* $\to$ *Riavvia*).

---

## 🛰️ Formato del Payload MQTT emesso

Ogni volta che il Deebot naviga, viene pubblicato istantaneamente su `homeassistant/deebot/pose`:

```json
{
  "timestamp": 1731433150,
  "device": "Deebot",
  "state": "cleaning",
  "robot": {
    "x": 1420.5,
    "y": -850.2,
    "angle": 92.0
  },
  "dock": {
    "x": 0.0,
    "y": 0.0
  }
}
```

* `robot.x` e `robot.y`: distanza in millimetri rispetto alla docking station
* `robot.angle`: orientamento della prua del robottino in gradi ($0^\circ \to 360^\circ$)
* Il digital twin Three.js legge questo topic tramite il WebSocket nativo di Home Assistant e posiziona il modello 3D in tempo reale sul pavimento con interpolazione fluida a 60 FPS.

