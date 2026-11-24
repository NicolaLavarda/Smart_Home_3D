# `scripts/` — Provisioning Windows, Servizi NSSM, Firewall e Manutenzione

Questa directory contiene tutti gli script PowerShell (`.ps1`) e Batch (`.bat`) per il provisioning, l'avvio, l'arresto, l'aggiornamento e l'ottimizzazione del nodo Windows 10 **nativo (Zero Docker / Zero WSL2)**.

---

## Panoramica Script

| Script | Tipo | Privilegi Richiesti | Scopo |
|---|---|---|---|
| [`setup_windows_node.ps1`](./setup_windows_node.ps1) | PowerShell | Standard (Admin per `VC_redist` UAC o `-InstallServices`) | Provisioning one-click: `.env`, `VC_redist.x64`, `go2rtc.exe`, `caddy.exe`, `nssm.exe`, `.venv`, modelli OpenVINO/biometria. |
| [`install_windows_services.ps1`](./install_windows_services.ps1) | PowerShell | **Amministratore** | Registra/aggiorna in modo idempotente i 3 servizi NSSM, propaga `.env` in `AppEnvironmentExtra`, configura Windows Firewall (`:8555`) e avvia i servizi. |
| [`start_services.bat`](./start_services.bat) | Batch | Standard (dev) / Admin (NSSM se non già avviato) | Avvia `go2rtc`, `spatial_server` e `Caddy`: usa i servizi NSSM se registrati, altrimenti avvia in modalità console caricando `.env`. |
| [`stop_services.bat`](./stop_services.bat) | Batch | Admin (per servizi NSSM) | Arresta i servizi NSSM in ordine inverso (`Caddy` -> `SpatialServer` -> `go2rtc`) e termina eventuali processi console residui. |
| [`update_services.bat`](./update_services.bat) | Batch | Admin (consigliato per NSSM) | Aggiorna da `origin/main`, arresta i servizi, aggiorna `.venv`/`node_modules`, compila `dist/`, aggiorna NSSM, valida `Caddyfile` e riavvia tutto. |
| [`decommission_codeproject_ai.ps1`](./decommission_codeproject_ai.ps1) | PowerShell | Read-only standard / **Admin** con `-Apply` | Audit e dismissione reversibile del server legacy CodeProject.AI (porta `32168`) per liberare ~1–2 GB RAM dopo il passaggio alla biometria nativa. |

---

## 1. [`setup_windows_node.ps1`](./setup_windows_node.ps1)

Prepara da zero sia il portatile di sviluppo sia il PC Fisso di produzione (`i5-6400 / 8 GB RAM / Intel HD 530`).

### Parametri
- `-WithOpenVINO` *(switch)*: installa `openvino>=2024.4.0` in `.venv` ed esegue [`tools/download_yolo_openvino_model.py`](../tools/download_yolo_openvino_model.py).
- `-WithBiometrics` *(switch)*: esegue [`tools/download_biometric_models.py`](../tools/download_biometric_models.py) per scaricare i modelli ONNX Face Recognition (SCRFD/MobileFaceNet) e ALPR.
- `-InstallServices` *(switch)*: al termine delega automaticamente a `install_windows_services.ps1 -LanCidr $LanCidr`.
- `-LanCidr <string>` *(default `"192.168.86.0/24"`)*: subnet LAN passata alle regole firewall WebRTC quando si usa `-InstallServices`.

### Operazioni Eseguite
1. Crea `.env` da `.env.example` se non presente.
2. Verifica nel registro `HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64` la presenza di **Microsoft Visual C++ Redistributable x64** (`vc_redist.x64.exe`); se assente, lo scarica e lo installa silenziosamente.
3. Scarica e verifica (`Test-PeBinary`, header PE `MZ`) i binari Windows amd64 gitignored:
   - `go2rtc\go2rtc.exe` (archivio `go2rtc_win64.zip` da GitHub Releases).
   - `caddy\caddy.exe` (API `caddyserver.com` con fallback GitHub Releases).
   - `tools\nssm.exe` (archivio `win64\nssm.exe` da `nssm.cc`).
4. Crea il virtualenv Python `.venv` e installa `spatial_server\requirements.txt`.

### Esempio d'Uso
```powershell
# Setup completo nodo produzione (PowerShell come Amministratore)
powershell -ExecutionPolicy Bypass -File scripts\setup_windows_node.ps1 -WithOpenVINO -WithBiometrics -InstallServices -LanCidr 192.168.86.0/24
```

---

## 2. [`install_windows_services.ps1`](./install_windows_services.ps1)

Installa o aggiorna in modo idempotente i servizi Windows tramite **NSSM** e le regole **Windows Defender Firewall**. Richiede una sessione PowerShell **Amministratore**.

### Parametri
- `-LanCidr <string>` *(default `"192.168.86.0/24"`)*: validato con regex e controlli range IPv4 (`0..255` e prefisso `0..32`).
- `-SkipFirewall` *(switch)*: salta l'aggiornamento delle regole Windows Defender Firewall.
- `-NoStart` *(switch)*: registra/aggiorna i servizi e `AppEnvironmentExtra` senza avviarli al termine.

### Servizi NSSM Configurati
Tutti e 3 i servizi sono configurati con `Start=SERVICE_AUTO_START`, `AppExit Default Restart`, `AppRestartDelay=5000` ms, `AppStopMethod*=5000` ms e rotazione log automatica in `logs\` (`AppRotateFiles=1`, `AppRotateOnline=1`, `AppRotateBytes=5242880` = 5 MB per file):

| Nome Servizio | Eseguibile & Parametri | Dipendenze (`DependOnService`) | Ambiente & Log |
|---|---|---|---|
| `SmartHome3D-go2rtc` | `go2rtc\go2rtc.exe -c "<repo>\go2rtc\go2rtc.yaml"` | *(nessuna)* | `AppEnvironmentExtra` da `.env` (omette `GO2RTC_CANDIDATE_*` se vuoti); `logs\go2rtc.{stdout,stderr}.log` |
| `SmartHome3D-SpatialServer` | `.venv\Scripts\uvicorn.exe spatial_server.main:app --host 127.0.0.1 --port <SPATIAL_SERVER_PORT>` | `SmartHome3D-go2rtc` | `AppEnvironmentExtra` da `.env`, forza `SPATIAL_SERVER_HOST=127.0.0.1` e imposta `OMP_NUM_THREADS=2` se assente; `logs\spatial_server.{stdout,stderr}.log` |
| `SmartHome3D-Caddy` | `caddy\caddy.exe run --config "<repo>\caddy\Caddyfile" --adapter caddyfile` | `SmartHome3D-SpatialServer`, `SmartHome3D-go2rtc` | `logs\caddy.{stdout,stderr}.log` |

> [!NOTE]
> Lo script gestisce automaticamente il parsing `.env` UTF-8 (inclusi prefissi `export`, commenti, virgolette e caratteri speciali), supporta gli alias legacy `REOLINK_CARRAIO_PASSWORD` -> `REOLINK_CARRAIO_PASS` e `MQTT_PASSWORD` -> `MQTT_PASS`, e sincronizza `AppEnvironmentExtra` anche nel registro `HKLM:\SYSTEM\CurrentControlSet\Services\<Name>\Parameters`.

### Regole Windows Defender Firewall
Se `-SkipFirewall` non è passato, rimuove le vecchie regole `SmartHome3D-WebRTC-*` e crea due regole **Inbound Allow** limitate esclusivamente alla porta **`8555`** e agli indirizzi remoti **`@($LanCidr, "100.64.0.0/10")`** (LAN locale + Tailscale CGNAT):
- `SmartHome3D-WebRTC-TCP-8555` (TCP `:8555`)
- `SmartHome3D-WebRTC-UDP-8555` (UDP `:8555`)

---

## 3. [`start_services.bat`](./start_services.bat) e [`stop_services.bat`](./stop_services.bat)

- **`start_services.bat`**:
  - Carica `.env` nella sessione batch, imposta `SPATIAL_SERVER_HOST=127.0.0.1` e `SPATIAL_SERVER_PORT=8765` se vuoti.
  - Se rileva almeno uno dei servizi `SmartHome3D-*` via `sc query`, li avvia in ordine di dipendenza (`SmartHome3D-go2rtc` -> `SmartHome3D-SpatialServer` -> `SmartHome3D-Caddy`) con `nssm.exe start` / `net start`.
  - Altrimenti entra in **modalità console / sviluppo**: termina eventuali istanze residue (`caddy.exe`, `go2rtc.exe`, `uvicorn.exe` su `spatial_server.main:app`) e avvia i processi in finestre minimizzate (`/MIN`).
- **`stop_services.bat`**:
  - Arresta gli eventuali servizi NSSM in ordine inverso (`SmartHome3D-Caddy` -> `SmartHome3D-SpatialServer` -> `SmartHome3D-go2rtc`), attendendo fino a 15 iterazioni che passino in `STOPPED`.
  - Termina eventuali processi console residui legati al repository.

---

## 4. [`update_services.bat`](./update_services.bat)

Procedura di aggiornamento automatico per il nodo di produzione:
```bat
scripts\update_services.bat
REM Oppure forzando reinstallazione dipendenze Python/Node e rebuild dist\:
scripts\update_services.bat --deps
```
Sequenza operativa:
1. Verifica `git` e salva `OLD_HEAD`; esegue `git fetch origin main` (se fallisce esce lasciando i servizi in esecuzione).
2. Arresta i servizi tramite `scripts\stop_services.bat`.
3. Riallinea i file tracciati con `git checkout -f -B main origin/main` e `git reset --hard origin/main` *(preserva file untracked/gitignored come `.env`, `camera_calibrations.json`, DB SQLite e log)*.
4. Se mancano binari o `.venv`, invoca `setup_windows_node.ps1 -WithOpenVINO`.
5. Aggiorna `.venv` se `spatial_server/requirements.txt` è cambiato (o con `--deps`), scarica `yolov8n_openvino_model` se mancante, aggiorna `node_modules` se `package.json`/`package-lock.json` sono cambiati, e ricompila `dist\` con `npm.cmd run build` se `dist/`/`index.html`/`sw.js` mancano o se file frontend (`index.html`, `package*.json`, `vite.config.js`, `src/`, `public/`) sono cambiati.
6. Se i servizi NSSM sono installati e il prompt è Amministratore, aggiorna `AppEnvironmentExtra` tramite `install_windows_services.ps1 -NoStart -SkipFirewall`.
7. Valida `caddy\Caddyfile` (`caddy.exe validate`) e riavvia tutti i servizi con `scripts\start_services.bat`.

---

## 5. [`decommission_codeproject_ai.ps1`](./decommission_codeproject_ai.ps1)

Script sicuro per dismettere il vecchio server **CodeProject.AI** (porta `32168`) dopo l'attivazione della biometria ONNX nativa in `SmartHome3D-SpatialServer`:

```powershell
# 1. Audit in sola lettura (dry-run, default)
powershell -ExecutionPolicy Bypass -File scripts\decommission_codeproject_ai.ps1

# 2. Arresto e disabilitazione servizi CodeProject.AI (richiede Admin)
powershell -ExecutionPolicy Bypass -File scripts\decommission_codeproject_ai.ps1 -Apply
```

- **Senza `-Apply`**: mostra RAM libera/totale, servizi `*CodeProject*`, albero processi figli (`CodeProject*`, `AnalysisLayer*`, worker Python/ONNX/Paddle), stato porta TCP `32168` e impronta RAM stimata.
- **Con `-Apply`**: verifica che `SmartHome3D-SpatialServer` sia `Running` (a meno di passare `-SkipSpatialCheck`), arresta e imposta `StartupType=Disabled` sui servizi CodeProject.AI, termina eventuali processi residui e mostra la RAM recuperata più il comando di rollback esatto.

---

## Riferimenti Correlati
- Runbook completo di produzione: [`docs/runbooks/production-tailscale.md`](../docs/runbooks/production-tailscale.md)
- Reference variabili `.env`: [`docs/reference/env-variables.md`](../docs/reference/env-variables.md)
- Test dry-run degli script (`test_f15`): [`docs/reference/testing-suite.md`](../docs/reference/testing-suite.md)
