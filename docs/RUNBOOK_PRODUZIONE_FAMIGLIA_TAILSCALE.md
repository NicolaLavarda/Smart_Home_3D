# 🏡 Runbook di Produzione — Smart Home 3D (Windows 10 + Caddy + Tailscale Serve + PWA Famiglia)

Guida operativa completa per mettere in produzione **Smart Home 3D Digital Twin** sul PC Fisso Windows 10 (`Intel i5-6400 / 8 GB RAM / Intel HD 530`, **Zero Docker / Zero WSL2**), esponendolo in modo sicuro alla famiglia tramite **Tailscale Serve**, **Caddy same-origin**, **OAuth2 + RBAC Home Assistant** e **PWA installabile** su iOS e Android.

> **Prerequisito telecamera:** per la configurazione iniziale RTSP/H.264 della Reolink RLC-540A (`192.168.86.47`), fare riferimento alla Sezione 1 di [`docs/GUIDA_CONFIGURAZIONE_REOLINK_E_SERVIZI.md`](./GUIDA_CONFIGURAZIONE_REOLINK_E_SERVIZI.md).

---

## Panoramica Architetturale (Defense-in-Depth)

```text
Smartphone / Tablet / PC Famiglia (su Wi-Fi di casa OPPURE 4G/5G)
  │
  ├── HTTPS :443  (https://<pc-fisso>.<tailnet>.ts.net)
  │     └──► Tailscale Serve (:443) ──► Caddy (127.0.0.1:8080)
  │           ├── /                       ──► PWA statica Vite (dist/) + Service Worker
  │           ├── /api/v1/*, /ws/spatial  ──► spatial_server (127.0.0.1:8765) [Auth + RBAC]
  │           ├── /go2rtc/api/webrtc*     ──► forward_auth (:8765/api/v1/auth/verify) ──► go2rtc (127.0.0.1:1984)
  │           ├── /go2rtc/api/ws*         ──► forward_auth (:8765/api/v1/auth/verify) ──► go2rtc (127.0.0.1:1984)
  │           └── /go2rtc/* (altro)       ──► 403 Forbidden (Web UI e config go2rtc bloccati)
  │
  ├── HTTPS :8443 (https://<pc-fisso>.<tailnet>.ts.net:8443)
  │     └──► Tailscale Serve (:8443) ──► Loopback bridge 127.0.0.1:8123 ──► VM Home Assistant (192.168.86.24:8123)
  │
  └── WebRTC Media :8555 (TCP/UDP, Firewall ristretto a LAN + 100.64.0.0/10)
        └──► go2rtc (:8555) [fallback automatico a MSE wss://.../go2rtc/api/ws su :443 e Snapshot HA]
```

**Principi chiave di sicurezza:**
1. **Un'unica origine HTTPS (`:443`)** per PWA, API, WebSocket spaziale e streaming video: nessun token segreto (`VITE_HA_TOKEN`) viene mai compilato dentro `dist/assets/*.js`.
2. **Nessuna porta backend esposta su LAN/Wi-Fi**: `:8080` (Caddy), `:8765` (`spatial_server`), `:1984` e `:8554` (`go2rtc`) ascoltano esclusivamente su `127.0.0.1`.
3. **Autenticazione SSO Home Assistant + Cookie `sh3d_session`** (`HttpOnly`, `SameSite=Strict`, `Secure`) e controllo ruoli **RBAC** (`Admin` vs `Residente`).
4. **Add-on Tailscale nella VM Home Assistant invariato**, così App Companion, Tasker e automazioni esistenti continuano a funzionare senza interruzioni.

---

## 1. Configurazione Home Assistant (`192.168.86.24:8123`)

### 1.1 Regola d'oro: Add-on Tailscale di Home Assistant invariato
* **Non disinstallare e non riconfigurare** l'Add-on Tailscale presente nella VM Home Assistant (`192.168.86.24`).
* L'App ufficiale Home Assistant Companion, Tasker e gli eventuali webhook/automazioni già configurati su quell'add-on rimangono completamente intatti e indipendenti.
* Il traffico OAuth2 e WebSocket della PWA passerà attraverso il nodo Tailscale del PC Fisso sulla porta `:8443` verso la VM HA in LAN (`192.168.86.24:8123`).

### 1.2 Abilitazione `trusted_proxies` in `configuration.yaml`
Poiché `Tailscale Serve` sul PC Fisso inoltra le richieste verso `192.168.86.24:8123` aggiungendo gli header `X-Forwarded-For`, Home Assistant restituirà `400: Bad Request` se l'IP LAN del PC Fisso non è autorizzato tra i proxy fidati.

1. Individua l'IP LAN statico (o con prenotazione DHCP sul router) del PC Fisso Windows 10 eseguendo `ipconfig` (es. `192.168.86.XX`).
2. Modifica `/config/configuration.yaml` su Home Assistant **mantenendo** gli indirizzi di loopback e la subnet del Supervisor/Add-on HA (`172.30.33.0/24`):
   ```yaml
   http:
     use_x_forwarded_for: true
     trusted_proxies:
       - 127.0.0.1
       - ::1
       - 172.30.33.0/24
       - 192.168.86.XX  # <-- Sostituire con l'IP LAN reale del PC Fisso Windows 10
   ```
   > **Nota per Home Assistant `2026.8+`:** a partire da HA `2026.8`, la configurazione `http:` in YAML è deprecata a favore dell'interfaccia web. Se la tua versione segnala l'avviso di deprecazione, imposta gli stessi valori in **Impostazioni → Sistema → Rete → Server HTTP** (*Trust X-Forwarded-For* attivo + elenco *Trusted proxies*).
3. Vai in **Strumenti per sviluppatori → Controlla configurazione** e **Riavvia Home Assistant**.

### 1.3 Creazione Utenti e Ruoli RBAC (`Admin` vs `Residente`)
Vai in Home Assistant → **Impostazioni → Persone → Utenti** (oppure *Gestisci utenti*):

* **Account `Admin` (Proprietario / Amministratore):**
  * Flag **Amministratore** **ATTIVO** (`is_admin: true` / `is_owner: true`).
  * Accesso completo alla scena 3D, alla calibrazione ottica POV (`#btn-open-cam-calib` *"Calibra Cam"*, `#btn-camera-calibrate` *"Apri Calibrazione Ottica POV"*, `CalibrationAssistantUI`), al selettore modalità CV/Simulatore (`#btn-toggle-simulator`) e agli endpoint mutativi (`/api/v1/calibration/solve-pnp`, `/api/v1/calibration/{camera_id}`, `/api/v1/ingestion/mode`, `/api/v1/detections`).
* **Account `Residente` (Familiari — es. Moglie / Figli / Tablet da muro):**
  * Crea un utente personale per ogni familiare nel gruppo **Utenti** con il flag **Amministratore** **DISATTIVATO** (`is_admin: false`).
  * Verifica che l'opzione **"Può accedere solo dalla rete locale"** sia **DISATTIVATA**, altrimenti il login OAuth2 attraverso Tailscale `:8443` può essere rifiutato.
  * Comportamento garantito: il familiare comanda normalmente dispositivi e telecamere live/timeline, ma **non vede** i controlli di calibrazione o simulazione nella UI e qualsiasi chiamata diretta verso API amministrative restituisce `403 Forbidden` dal backend `spatial_server`.
* **Consiglio sicurezza:** attiva l'autenticazione a due fattori **2FA (TOTP)** su ogni account HA; in caso di smarrimento di uno smartphone, potrai revocare il solo *refresh token* di quel dispositivo dal profilo dell'utente in Home Assistant.

---

## 2. Setup PC Fisso Windows 10 (`i5-6400 / 8 GB RAM`) & Tailscale Serve

### 2.1 Client Tailscale Windows 10 in Modalità Unattended
1. Installa **Tailscale per Windows** sul PC Fisso e accedi con l'account proprietario della tailnet.
2. Abilita la modalità **Unattended** in modo che il tunnel Tailscale e `Tailscale Serve` restino attivi anche dopo un riavvio automatico senza login interattivo Windows:
   * Da interfaccia grafica: icona Tailscale nella tray → **Preferences → Run Unattended**, oppure da **PowerShell come Amministratore**:
     ```powershell
     tailscale up --unattended
     # oppure, se il nodo è già connesso:
     tailscale set --unattended=true
     ```
3. Nella **Tailscale Admin Console → DNS**, verifica che **MagicDNS** e **HTTPS Certificates** siano abilitati (necessari affinché `tailscale serve` generi automaticamente i certificati TLS Let's Encrypt).
4. Annota il nome FQDN MagicDNS e l'IP Tailscale del PC Fisso con:
   ```powershell
   tailscale status
   ```
   Esempio: `pc-fisso.<tailnet>.ts.net` e `100.x.y.z`.

### 2.2 Bridge Loopback per Home Assistant (`:8443`) & Configurazione `Tailscale Serve`
In Tailscale (`1.104.1`), `tailscale serve` accetta esclusivamente destinazioni locali (`localhost` o `127.0.0.1`): puntare direttamente all'IP LAN della VM (`http://192.168.86.24:8123`) restituisce l'errore `only localhost or 127.0.0.1 proxies are currently supported`.

Per risolvere in modo pulito, nativo e persistente senza aprire porte sulla LAN, si crea un bridge loopback `127.0.0.1:8123 -> 192.168.86.24:8123` tramite Windows `netsh interface portproxy` (gestito dal servizio di sistema `iphlpsvc` / *Helper IP*, attivo di default su Windows 10).

Esegui da **PowerShell come Amministratore**:
```powershell
# 1. Espone Caddy (127.0.0.1:8080) su HTTPS porta :443
tailscale serve --bg 8080

# 2. Crea il bridge locale permanente 127.0.0.1:8123 -> VM Home Assistant (192.168.86.24:8123)
netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=8123 connectaddress=192.168.86.24 connectport=8123

# 3. Espone Home Assistant (per OAuth2 e WebSocket) su HTTPS porta :8443
tailscale serve --bg --https=8443 8123
```

Verifica subito lo stato attivo:
```powershell
tailscale serve status
netsh interface portproxy show v4tov4
```
Output atteso di `tailscale serve status`:
* `https://<pc-fisso>.<tailnet>.ts.net` (`:443`) → `proxy http://127.0.0.1:8080`
* `https://<pc-fisso>.<tailnet>.ts.net:8443` (`:8443`) → `proxy http://127.0.0.1:8123`

### 2.3 Configurazione File `.env` di Produzione
Se `.env` non esiste ancora nella root del repository, copia `.env.example` in `.env`, quindi imposta i parametri di produzione (sostituendo `<pc-fisso>.<tailnet>.ts.net`, `192.168.86.XX`, `100.x.y.z` e le password reali):

```env
# Home Assistant OAuth2 (browser su :8443) + URL LAN backend-to-backend
VITE_HA_PUBLIC_URL=https://<pc-fisso>.<tailnet>.ts.net:8443
VITE_HA_LOCAL_URL=http://192.168.86.24:8123
VITE_HA_TOKEN=

# Sicurezza Backend, Cookie HttpOnly & Same-Origin
SPATIAL_SERVER_HOST=127.0.0.1
SPATIAL_SERVER_PORT=8765
SPATIAL_AUTH_REQUIRED=true
SPATIAL_SESSION_SECRET=<chiave_casuale_almeno_32_byte>
SPATIAL_ALLOWED_ORIGINS=https://<pc-fisso>.<tailnet>.ts.net

# go2rtc WebRTC Candidates & Credenziali Reolink RLC-540A
GO2RTC_CANDIDATE_LAN=192.168.86.XX:8555
GO2RTC_CANDIDATE_TAILSCALE=100.x.y.z:8555
REOLINK_CARRAIO_IP=192.168.86.47
REOLINK_CARRAIO_USER=admin
REOLINK_CARRAIO_PASS=<password_reolink>

# OpenVINO & MQTT (VM Home Assistant)
CV_INGESTION_MODE=openvino
OPENVINO_DEVICE=AUTO
MQTT_BROKER_HOST=192.168.86.24
MQTT_BROKER_PORT=1883
MQTT_USER=
MQTT_PASS=
```

Per generare velocemente un `SPATIAL_SESSION_SECRET` robusto in PowerShell:
```powershell
[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Maximum 256 }))
```

> **Attenzioni critiche su `.env`:**
> * **`VITE_HA_TOKEN` deve restare vuoto** in produzione: Vite incorpora tutte le variabili `VITE_*` in chiaro dentro `dist/assets/*.js` durante `npm.cmd run build`.
> * Assicurati che `VITE_SPATIAL_SERVER_URL`, `VITE_SPATIAL_WS_URL`, `VITE_GO2RTC_URL` e `VITE_GO2RTC_TAILSCALE_URL` restino **commentati o assenti** in produzione, così il frontend usa automaticamente gli endpoint same-origin (`/api/v1/*`, `/ws/spatial`, `/go2rtc/*`).
> * Ogni modifica a `VITE_HA_PUBLIC_URL` richiede una nuova compilazione (`npm.cmd run build`); ogni modifica alle variabili backend (`REOLINK_CARRAIO_PASS`, `SPATIAL_*`, `GO2RTC_CANDIDATE_*`) richiede l'aggiornamento dell'ambiente NSSM (rieseguendo `scripts\install_windows_services.ps1` o `scripts\update_services.bat` da Amministratore).

### 2.4 Build Frontend PWA, Servizi NSSM & Windows Defender Firewall
1. Dalla root del repository, compila il frontend PWA di produzione:
   ```powershell
   npm.cmd install
   npm.cmd run build
   ```
2. Verifica che non siano finiti token nei bundle e che il Service Worker PWA sia stato generato:
   ```powershell
   Test-Path dist\manifest.webmanifest
   Test-Path dist\sw.js
   Select-String -Path dist\assets\*.js -Pattern "eyJ"
   ```
   *(L'ultimo comando non deve restituire alcuna corrispondenza.)*
3. Apri **PowerShell come Amministratore** nella root del repository ed esegui il setup completo e la registrazione dei servizi:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup_windows_node.ps1 -WithOpenVINO -InstallServices -LanCidr 192.168.86.0/24
   ```
   Cosa esegue automaticamente la coppia `setup_windows_node.ps1` + `install_windows_services.ps1`:
   * Verifica e installa **Microsoft Visual C++ Redistributable x64** (`VC_redist.x64`, richiesto da OpenVINO).
   * Scarica i binari Windows amd64 gitignored: `go2rtc\go2rtc.exe`, `caddy\caddy.exe`, `tools\nssm.exe`.
   * Crea `.venv`, installa `spatial_server\requirements.txt` e `openvino>=2024.4.0`.
   * Registra 3 servizi Windows NSSM con **avvio automatico al boot** (`SERVICE_AUTO_START`), **riavvio automatico su crash** (`5s`), **dipendenze ordinate** e **rotazione log in `logs\`** (`5 MB` per file):
     1. **`SmartHome3D-go2rtc`**: esegue `go2rtc\go2rtc.exe -c go2rtc\go2rtc.yaml` (`127.0.0.1:1984`, `127.0.0.1:8554`, `:8555` TCP/UDP) ricevendo le variabili `.env` tramite `AppEnvironmentExtra`.
     2. **`SmartHome3D-SpatialServer`**: esegue `.venv\Scripts\uvicorn.exe spatial_server.main:app --host 127.0.0.1 --port 8765` (`DependOnService: SmartHome3D-go2rtc`, forzando `SPATIAL_SERVER_HOST=127.0.0.1`).
     3. **`SmartHome3D-Caddy`**: esegue `caddy\caddy.exe run --config caddy\Caddyfile --adapter caddyfile` con `AppDirectory` sulla root del repository (`DependOnService: SmartHome3D-SpatialServer`, `SmartHome3D-go2rtc`).
   * Configura in modo idempotente le regole **Windows Defender Firewall** (`SmartHome3D-WebRTC-TCP-8555` e `SmartHome3D-WebRTC-UDP-8555`) aprendo **solo la porta `8555` TCP/UDP** verso la LAN (`192.168.86.0/24`) e Tailscale CGNAT (`100.64.0.0/10`), mantenendo `:8080`, `:8765`, `:1984` e `:8554` isolati su `127.0.0.1`.

### 2.5 Aggiornamenti Futuri Unattended (`scripts\update_services.bat`)
Per aggiornare il nodo di produzione dopo un push su `main`, esegui da **Prompt dei comandi / PowerShell come Amministratore**:
```bat
scripts\update_services.bat
```
Lo script arresta in ordine inverso i servizi NSSM (`Caddy` → `SpatialServer` → `go2rtc`), riallinea i file tracciati a `origin/main` (preservando `.env` e `spatial_server/data/camera_calibrations.json`), aggiorna `.venv`/`node_modules` se modificati, ricompila `dist\` (anche al primo deploy o con `--deps`), aggiorna `AppEnvironmentExtra` dei servizi NSSM da `.env`, valida `caddy\Caddyfile` e riavvia tutti i servizi.

Per avvio/arresto manuale sono disponibili `scripts\start_services.bat` e `scripts\stop_services.bat` (entrambi rilevano automaticamente i servizi NSSM se installati).

---

## 3. Accesso Famiglia, Sicurezza Rete (`Node Sharing` vs `ACL`) & Wi-Fi Ospiti

### 3.1 Scelta Topologia Tailscale (Piano Free Personal: fino a 6 utenti, 3 gruppi ACL)
Scegli una delle due modalità supportate dal piano gratuito Tailscale Personal:

* **Opzione A — Node Sharing (`Share...`) del solo PC Fisso (Consigliata per massimo isolamento):**
  * Nella **Tailscale Admin Console → Machines**, clicca `...` sul PC Fisso → **Share...** → invia il link o invita l'email Tailscale personale del familiare.
  * **Vantaggi:** il familiare vede **esclusivamente** il PC Fisso e non vede nessun altro nodo della tua tailnet (né il portatile di sviluppo, né altri computer, né l'Add-on HA); inoltre i nodi condivisi non ereditano eventuali Subnet Router.
  * **Requisiti:** il familiare deve avere MagicDNS attivo nella propria tailnet (attivo di default) e usare sempre l'URL FQDN completo (`https://<pc-fisso>.<tua-tailnet>.ts.net` e `:8443`).
  * **Attenzione:** di default la condivisione espone tutte le porte del nodo condiviso, quindi **va sempre abbinata** alla regola ACL/Grants su `autogroup:shared` indicata al punto 3.2!
* **Opzione B — Utenti nella stessa Tailnet (fino a 6 utenti su Personal Free):**
  * Invita i familiari nella tua tailnet (**Users → Invite users**) e inseriscili nel gruppo `group:famiglia` dentro le Access Controls.

### 3.2 Policy Tailscale (`grants` consigliato) — Principio del Minimo Privilegio
Nella **Tailscale Admin Console → Access Controls**, sostituisci la regola permissiva iniziale (`"src": ["*"], "dst": ["*:*"]`) con una policy esplicita (adattando `pc-fisso`, IP `100.x.y.z` ed email reali):

```jsonc
{
  "groups": {
    "group:admin": ["tuo-account@example.com"],
    "group:famiglia": ["familiare1@example.com", "familiare2@example.com"]
  },
  "hosts": {
    "pc-fisso": "100.x.y.z"
  },
  "grants": [
    // Admin: accesso completo alla tailnet
    {
      "src": ["group:admin"],
      "dst": ["*"],
      "ip": ["*"]
    },
    // Familiari nella stessa tailnet O tramite Node Sharing (autogroup:shared):
    // consentite SOLO :443 (PWA+API+MSE), :8443 (HA OAuth2/WS) e :8555 (WebRTC media).
    // Bloccati RDP (3389), SMB (445), SSH (22) e qualsiasi altra macchina della tailnet.
    {
      "src": ["group:famiglia", "autogroup:shared"],
      "dst": ["pc-fisso"],
      "ip": ["tcp:443", "tcp:8443", "tcp:8555", "udp:8555"]
    }
  ]
}
```

### 3.3 Sicurezza Locale & Isolamento Wi-Fi Ospiti
* **Sul Wi-Fi principale di casa:** chi conosce soltanto la password del Wi-Fi **non può** comandare luci/cancelli né vedere le telecamere, perché `:8080`, `:8765`, `:1984` e `:8554` rispondono solo su `127.0.0.1` e ogni richiesta su `:443` / `:8443` richiede un account Home Assistant valido e il cookie firmato `sh3d_session`.
* **Wi-Fi Ospiti (Guest Wi-Fi):** attiva sul router/Access Point una rete Wi-Fi dedicata agli ospiti con **Client Isolation (AP Isolation)** attiva e **Accesso alla rete locale / Intranet DISABILITATO** (VLAN isolata). In questo modo gli ospiti non possono raggiungere `192.168.86.0/24` (né la VM HA `.24`, né la Reolink `.47`, né la porta `:8555` del PC Fisso).

---

## 4. Onboarding Smartphone & Tablet Famiglia (iOS & Android)

Procedura una-tantum per ogni dispositivo familiare (circa 3 minuti):

### 4.1 Installazione Tailscale & Regola "Nessun Exit Node"
1. Installa l'app **Tailscale** da App Store (iOS/iPadOS) o Google Play Store (Android) ed effettua l'accesso con l'account del familiare (accettando l'invito *Node Sharing* o tailnet).
2. Verifica che **Exit Node** sia impostato su **None / Nessuno**.
   > **Nota rassicurante per la famiglia:** senza Exit Node, tutto il traffico Internet normale (YouTube, Google, WhatsApp, app bancarie) continua a uscire **direttamente** dalla rete cellulare o dal Wi-Fi locale, senza passare dal PC di casa. Nel tunnel cifrato Tailscale viaggia **solo** il traffico diretto a `*.ts.net` (`100.64.0.0/10`).

### 4.2 Configurazione Specifica Android vs iOS (Affidabilità a Casa e Fuori Casa)
* **Android — App Split Tunneling & Batteria:**
  1. Apri **Tailscale → Settings → App Split Tunneling** (modalità esclusione): verifica che il browser usato per la PWA (**Google Chrome**, ed eventuali app PWA separate se presenti in elenco) **NON sia escluso**. Mantenere Chrome incluso nel routing Tailscale non dirotta la navigazione normale su casa (non c'è Exit Node), ma consente a Chrome/PWA di risolvere `https://<pc-fisso>.<tailnet>.ts.net` e `:8443`.
  2. Vai in **Impostazioni Android → App → Tailscale → Batteria** e seleziona **Senza restrizioni** (*Unrestricted*) per impedire che il risparmio energetico interrompa il tunnel in background.
* **iOS / iPadOS — Tailscale VPN On-Demand:**
  1. Apri **Tailscale → icona Profilo (in alto a destra) → Settings → VPN On-Demand**.
  2. Attiva **VPN On-Demand** configurandola per rimanere **attiva sia su Rete Cellulare sia su Wi-Fi (incluso il Wi-Fi di casa)**.
  > **Perché restare connessi anche sul Wi-Fi di casa?** Perché la PWA utilizza **un unico URL identico** (`https://<pc-fisso>.<tailnet>.ts.net`) sia a casa che fuori casa, mentre Caddy e i backend locali rispondono su `127.0.0.1` dietro `Tailscale Serve`. Con WireGuard senza Exit Node il consumo batteria su Wi-Fi è trascurabile.

### 4.3 Primo Login OAuth2 (`Accedi con Home Assistant`)
1. Apri **Safari** (iOS/iPadOS) o **Google Chrome** (Android) e visita:
   `https://<pc-fisso>.<tailnet>.ts.net`
2. Apparirà la schermata **"Accedi con Home Assistant"** (in produzione la modalità Mock silenziosa è disattivata).
3. Tocca **"Accedi con Home Assistant"**: verrai reindirizzato su `https://<pc-fisso>.<tailnet>.ts.net:8443`. Inserisci username e password personali (`Residente` o `Admin`) + eventuale codice 2FA, conferma e attendi il rientro automatico (`?auth_callback=1`).
4. Il browser salva localmente i token OAuth2 e riceve il cookie di sessione sicuro `sh3d_session`. Gli utenti `Residente` vedranno il proprio nome e ruolo nel menu Impostazioni senza pulsanti di calibrazione o simulazione.

### 4.4 Installazione come PWA (Schermata Home)
* **iOS / iPadOS (Safari):** tocca **Condividi** (icona quadrato con freccia verso l'alto) → **Aggiungi alla schermata Home** → conferma **"Smart Home 3D"** → apri dall'icona sulla Home (modalità `standalone` a schermo intero con `safe-area` e `ManagedMediaSource` per MSE su iOS 17+).
* **Android (Chrome):** accetta il banner **"Installa app"** oppure apri il menu `⋮` → **Installa app** / **Aggiungi a schermata Home**.

### 4.5 Cache Intelligente `.glb` & Aggiornamenti Automatici
* Il modello 3D (`house_optimized.glb`) e il decoder Draco vengono memorizzati in cache locale (`CacheFirst` con versione deterministica `?v=...` letta da `scene_manifest.json` in `NetworkFirst`), rendendo le aperture successive quasi istantanee e a consumo zero di dati mobili.
* Dopo ogni aggiornamento sul PC Fisso (`scripts\update_services.bat`), alla riapertura della PWA compare il banner **"Nuova versione disponibile — Aggiorna"**: toccando **Aggiorna** l'app si ricarica immediatamente con l'ultima build.

---

## 5. Checklist Verifica Finale & Troubleshooting Rapido

### 5.1 Checklist Post-Deploy
Esegui queste verifiche sul PC Fisso (PowerShell) e da uno smartphone su rete 4G/5G e su Wi-Fi di casa:

| Verifica | Comando / Azione | Esito Atteso |
|---|---|---|
| Servizi NSSM attivi | `Get-Service SmartHome3D-*` | Tutti e 3 (`go2rtc`, `SpatialServer`, `Caddy`) in stato `Running` |
| Regole Firewall `:8555` | `Get-NetFirewallRule -DisplayName "SmartHome3D*"` | Presenti solo `TCP-8555` e `UDP-8555` limitate a LAN + `100.64.0.0/10` |
| Bridge & Tailscale Serve | `tailscale serve status` e `netsh interface portproxy show v4tov4` | `:443 -> 127.0.0.1:8080`, `:8443 -> 127.0.0.1:8123 -> 192.168.86.24:8123` |
| Blocco UI `go2rtc` | Apri `https://<pc-fisso>.<tailnet>.ts.net/go2rtc/` da browser | Risposta `403 Forbidden` |
| RBAC `Residente` | Login con utente non-admin su smartphone (4G/5G e Wi-Fi) | Nessun tasto *Calibra Cam*; `POST /api/v1/calibration/...` → `403` |
| Video Live + PWA | Apri telecamera Carraio su smartphone e installa su Home | Stream `WEBRTC` o `MSE LIVE` fluido; riapertura istantanea da icona PWA |

### 5.2 Troubleshooting Errori Comuni

| Sintomo / Errore | Causa Probabile | Soluzione |
|---|---|---|
| `tailscale serve --https=8443 http://192.168.86.24:8123` fallisce con `only localhost or 127.0.0.1 proxies are currently supported` | Limite CLI Tailscale `1.104.1` verso target non-localhost | Configurare `netsh interface portproxy add v4tov4 listenaddress=127.0.0.1 listenport=8123 connectaddress=192.168.86.24 connectport=8123` e poi `tailscale serve --bg --https=8443 8123` |
| Home Assistant risponde `400: Bad Request` durante il login OAuth2 | IP LAN del PC Fisso assente in `trusted_proxies` su HA | Aggiungere l'IP LAN del PC Fisso in `configuration.yaml` (`http.trusted_proxies` + `use_x_forwarded_for: true`) o nella UI Rete su HA `2026.8+` e riavviare HA |
| Loop di redirect, errore CORS o `401` su `/api/v1/auth/session` / `/go2rtc/*` | `SPATIAL_ALLOWED_ORIGINS` o `VITE_HA_PUBLIC_URL` errati (es. slash finale o vecchio dominio) | Verificare `SPATIAL_ALLOWED_ORIGINS=https://<pc-fisso>.<tailnet>.ts.net` e `VITE_HA_PUBLIC_URL=https://<pc-fisso>.<tailnet>.ts.net:8443` in `.env`, rilanciare `npm.cmd run build` e aggiornare i servizi NSSM |
| Video telecamera in `MSE LIVE` o `OFFLINE` | Credenziali Reolink errate, `GO2RTC_CANDIDATE_*` mancanti in NSSM o porta `8555` filtrata | Verificare `REOLINK_CARRAIO_PASS`, `GO2RTC_CANDIDATE_LAN` e `GO2RTC_CANDIDATE_TAILSCALE` in `.env`, rieseguire `scripts\install_windows_services.ps1` (Admin) per aggiornare `AppEnvironmentExtra` di `SmartHome3D-go2rtc`, controllare Firewall `:8555` e Grant Tailscale *(nota: su reti mobili restrittive `MSE LIVE` su `:443` funge comunque da fallback)* |
| `*.ts.net` irraggiungibile dallo smartphone sul Wi-Fi di casa | Tailscale disattivato su Wi-Fi (On-Demand) o Chrome escluso in Android App Split Tunneling | Mantenere Tailscale attivo anche sul Wi-Fi domestico (senza Exit Node) e non escludere Chrome/PWA nello Split Tunneling |
| Utente `Residente` vede ancora *Calibra Cam* | Sessione salvata con vecchio account Admin o flag Amministratore ancora attivo in HA | Disattivare *Amministratore* sull'utente in Home Assistant, eseguire **Logout** dal menu Impostazioni della PWA e rieffettuare il login |

---

## 6. Sottosistema Biometrico (Face Recognition + ALPR) e Dismissione CodeProject.AI

### 6.1 Provisioning Modelli ONNX ed Enrollment Volti
Per abilitare il riconoscimento volti (`SCRFD_500M` + `MobileFaceNet w600k_mbf`) e la lettura targhe IT/EU (`YOLOv9-tiny` + `fast-plate-ocr` European/Global) nativamente dentro `SmartHome3D-SpatialServer` senza Docker/PyTorch:

1. Scarica i modelli ONNX leggeri sul nodo Windows eseguito come Amministratore:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\setup_windows_node.ps1 -WithOpenVINO -WithBiometrics
   # oppure direttamente nel virtualenv attivo:
   .\.venv\Scripts\python.exe tools\download_biometric_models.py
   ```
2. Genera l'indice compatto degli embedding facciali (`.npz`) dalle cartelle ordinate della famiglia (`<NomePersona>\*.jpg`):
   ```powershell
   .\.venv\Scripts\python.exe tools\enroll_faces.py --source "C:\Percorso\Volti totali"
   ```
3. Configura le targhe autorizzate di famiglia in `spatial_server\data\biometrics\plates_whitelist.json` oppure direttamente dalla UI Admin della PWA (sezione **Sicurezza → Cronologia → Gestisci**).

### 6.2 Validazione Hardware su Intel Core i5-6400 (8 GB RAM)
Prima di abilitare la biometria H24 in produzione, verifica sul PC Fisso che latenza per singolo crop (`~80–150 ms`) e RAM aggiuntiva (`<= 250–300 MB`) rispettino i vincoli della VM Home Assistant:

```powershell
.\.venv\Scripts\python.exe tools\benchmark_biometrics.py --compare-providers
```

Impostazioni consigliate in `.env` per preservare almeno 2 core alla VM VirtualBox di Home Assistant e a `go2rtc`:
```env
OMP_NUM_THREADS=2
OPENVINO_CPU_THREADS=2
BIOMETRICS_ONNX_PROVIDER=cpu
BIOMETRICS_ONNX_INTRA_THREADS=2
BIOMETRICS_ENABLED=true
BIOMETRICS_FACE_ENABLED=true
BIOMETRICS_ALPR_ENABLED=true
FACE_RECOGNITION_WEBHOOK_URL=
```

### 6.3 Attivazione Graduale, Controllo RBAC e Flusso Admin HITL
1. Aggiorna le variabili d'ambiente NSSM di `SmartHome3D-SpatialServer` ed esegui il riavvio ordinato:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\install_windows_services.ps1 -NoStart -SkipFirewall
   scripts\stop_services.bat
   scripts\start_services.bat
   ```
2. Verifica lo stato della pipeline biometrica (`running=true`, modelli `face_ready` / `alpr_ready`, quota crop e coda bounded):
   - Via API autenticata: `GET https://<pc-fisso>.<tailnet>.ts.net/api/v1/biometrics/status`
   - Dalla PWA su smartphone/PC:
     - **Utenti `Residente`:** vedono in sola lettura badge 3D, pillole targa, strip live e cronologia filtrabile per persona/targa/sconosciuti; **non vedono** né il pulsante *Gestisci* né i pulsanti *Assegna* (`POST/PUT/DELETE` biometrici rispondono `403 Forbidden`).
     - **Utenti `Admin` / `Owner`:** possono etichettare volti e targhe sconosciuti con il flusso **Human-in-the-Loop** (aggiungendo subito il crop alla galleria volti o la targa alla whitelist), ricaricare o rimuovere identità dalla galleria ed eliminare voci della whitelist.

### 6.4 Dismissione Sicura di CodeProject.AI (~1–2 GB RAM recuperata)
Solo dopo aver confermato su flussi reali (4 telecamere attive) che `SmartHome3D-SpatialServer` riconosce correttamente volti e targhe e che `FACE_RECOGNITION_WEBHOOK_URL=` è vuoto in `.env`:

1. Esegui prima un **audit read-only** per misurare processi, porta `32168` e RAM occupata da CodeProject.AI:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\decommission_codeproject_ai.ps1
   ```
2. Se `SmartHome3D-SpatialServer` è attivo e stabile, arresta e disabilita il servizio legacy recuperando ~1–2 GB di RAM sul nodo 8 GB:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\decommission_codeproject_ai.ps1 -Apply
   ```
   *(L'operazione è reversibile tramite `Set-Service -Name "<nome_servizio>" -StartupType Automatic; Start-Service -Name "<nome_servizio>"`, indicato dallo script al termine.)*

