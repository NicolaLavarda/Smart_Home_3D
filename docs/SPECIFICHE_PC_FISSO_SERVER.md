# Specifiche PC Fisso Server (`Smart_Home_3D`)

Questo documento raccoglie le specifiche hardware, di sistema e architetturali del **PC fisso sempre acceso**, utilizzato come host di produzione per Home Assistant e per tutti i servizi di `Smart_Home_3D`.

---

## 1. Hardware e Sistema Operativo

- **Ruolo:** Server domestico sempre acceso (host di produzione)
- **Sistema Operativo:** Windows 10 (esecuzione nativa dei servizi, **senza** Docker Desktop / WSL2)
- **CPU:** Intel Core i5-6400 @ 2.70 GHz (4 Core / 4 Thread, architettura Skylake Gen 6)
- **RAM:** 8 GB DDR4 (7.89 GB utilizzabili)
- **GPU integrata:** Intel HD Graphics 530 (supporto hardware Intel QuickSync H.264/HEVC 8-bit e OpenVINO / DirectML)

---

## 2. Virtualizzazione (Home Assistant & MQTT)

Sul PC fisso gira **VirtualBox** con una macchina virtuale Linux dedicata a:
- **Home Assistant OS** (`192.168.86.24:8123`)
- **Mosquitto MQTT** (`192.168.86.24:1883`)

---

## 3. Servizi e Programmi di `Smart_Home_3D` (Nativi su Windows 10)

I componenti applicativi di `Smart_Home_3D` girano nativamente su Windows 10 come servizi automatici gestiti tramite **NSSM** (e possono essere serviti anche all'esterno tramite **Tailscale**):

1. **`SmartHome3D-go2rtc` (`go2rtc\go2rtc.exe`)**
   - Gestisce i flussi video delle telecamere IP in passthrough (WebRTC / MSE / RTSP) senza transcoding software.
   - Porte locali: API/UI `127.0.0.1:1984`, RTSP `127.0.0.1:8554`, WebRTC `:8555` (TCP/UDP aperto su LAN e Tailscale).
2. **`SmartHome3D-SpatialServer` (`spatial_server` Python — FastAPI + Uvicorn)**
   - Microservizio spaziale su `127.0.0.1:8765` per raycasting 3D, tracking di Kalman, persistenza serie-temporali su **SQLite3 (modalità WAL)** ed eventuale inferenza CV locale leggera tramite **OpenVINO** su CPU / iGPU Intel HD 530.
3. **`SmartHome3D-Caddy` (`caddy\caddy.exe`)**
   - Reverse proxy e web server per servire il frontend PWA (`dist\`) e instradare le chiamate verso i servizi locali.

---

## 4. Vincoli Hardware e Architetturali

- **Niente GPU passthrough in VirtualBox:** VirtualBox su host Windows 10 non supporta il passthrough della Intel HD Graphics 530 verso la VM di Home Assistant; per questo motivo i servizi video e di Computer Vision girano nativamente sull'host Windows 10.
- **Niente Docker Desktop / WSL2:** con 8 GB di RAM totali condivisi tra Windows 10 e la VM VirtualBox di Home Assistant, è vietato usare Docker Desktop, WSL2 o database pesanti in RAM.
- **Niente transcoding software FFmpeg in `go2rtc`:** i flussi video devono restare in passthrough (H.264) per non saturare i 4 core dell'i5-6400.

---

*Riferimenti nel repository:* [master_prompt_architetturale_per_antigravity_ide.md](master_prompt_architetturale_per_antigravity_ide.md), [PIPELINE_AGGIUNTA_TELECAMERA.md](PIPELINE_AGGIUNTA_TELECAMERA.md), [RUNBOOK_PRODUZIONE_FAMIGLIA_TAILSCALE.md](RUNBOOK_PRODUZIONE_FAMIGLIA_TAILSCALE.md).
