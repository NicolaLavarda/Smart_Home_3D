# 🚀 Prompt Master — Trasformazione in PWA Self-Hosted di Produzione, Sicurezza Multi-Utente, Reverse Proxy HTTPS & Pipeline Famiglia

> **Come usare questo prompt:** Quando avrai completato la calibrazione delle telecamere, aggiunto tutte le nuove telecamere e consolidato il setup sul PC Fisso, incolla il contenuto del blocco sottostante in una nuova sessione (idealmente attivando `/plan`) per far analizzare lo stato aggiornato del repository e generare un piano d'implementazione completo, prima di scrivere codice.

---

```markdown
Agisci come **Principal Full-Stack Architect, Security/DevOps Engineer (Windows Native / Reverse Proxy / Tailscale) e Senior Web/PWA Engineer (Three.js / Vite / FastAPI)**.

## 1. Contesto del Progetto e Stato Attuale (Smart Home 3D)
Il progetto **Smart Home 3D** (`Digital Twin & Spatial CV Engine`) è ora operativo sul piano 3D, telecamera (`Cam_Carraio`), calibrazione e pipeline OpenVINO live sul PC Fisso Windows 10 (**Intel i5-6400 / 8 GB RAM / Zero Docker / Zero WSL2**), con Home Assistant OS + Mosquitto MQTT in VM VirtualBox (`192.168.86.24`), `go2rtc.exe` e il microservizio Python `spatial_server` (FastAPI + OpenVINO `yolov8n_openvino_model` + deduplica DB + SQLite3 WAL + `camera_calibrations.json`) gestiti dagli script in `scripts/` (`setup_windows_node.ps1`, `start_services.bat`, `stop_services.bat`, `update_services.bat`).

Ora l'obiettivo è portare l'applicazione in **produzione familiare multi-dispositivo** (smartphone iOS/Android, tablet domestici/a muro e PC) come **PWA installabile, sicura e aggiornabile centralmente**, utilizzabile senza attriti sia **in locale sul Wi-Fi di casa** sia **da remoto via Tailscale**.

---

## 2. Decisione Architetturale Già Approvata (Vincolante)
È stata già valutata e scelta l'architettura **PWA Self-Hosted sul PC Fisso + Reverse Proxy HTTPS Same-Origin + Home Assistant OAuth2 + Tailscale**:
- **NO** pubblicazione del sistema reale su Firebase Hosting (esporrebbe `VITE_HA_TOKEN` nel bundle statico, causerebbe blocchi Mixed Content `HTTPS -> HTTP/WS`, eliminerebbe i backend/proxy locali).
- **NO** distribuzione di pacchetti statici/APK/ZIP per singolo dispositivo.
- **SÌ** alla configurazione adottata: **`Tailscale Serve` (terminazione TLS HTTPS automatica) + `Caddy` su `127.0.0.1`** sul PC Fisso Windows 10 (zero Docker, zero gestione manuale di certificati):
  - **Sulla porta `443` (`https://<pc-fisso>.<tailnet>.ts.net`):** `Tailscale Serve` gestisce TLS/Let's Encrypt e inoltra a Caddy su `127.0.0.1:8080`, che espone sotto un'unica origine HTTPS:
    - `/` → build statica Vite di produzione (`dist/`)
    - `/api/v1/*` e `/ws/spatial` → `spatial_server` FastAPI (`127.0.0.1:8765`)
    - `/go2rtc/*` → `go2rtc` (`127.0.0.1:1984`)
  - **Per Home Assistant (`192.168.86.24:8123` — niente subpath `/ha/*`):** Home Assistant **non supporta** il reverse proxy su subpath `/ha/*` (OAuth, asset statici e WebSocket richiedono root `/`). Esponi quindi HA in HTTPS/WSS sulla root tramite **`Tailscale Serve` su porta alternativa `:8443`** dal PC Fisso (`tailscale serve --bg --https=8443 http://192.168.86.24:8123` → `https://<pc-fisso>.<tailnet>.ts.net:8443`, impostando `trusted_proxies` in HA) oppure via **`Tailscale Serve` dell'Add-on HA**, evitando qualsiasi problema di Mixed Content (`https://` + `wss://`) e funzionando anche con singolo nodo condiviso.

---

## 3. Requisiti Completi da Coprire nel Piano di Implementazione

### A. Sicurezza, Autenticazione e Gestione Permessi (4 Livelli — Defense in Depth)
Un requisito fondamentale è che **in locale a casa mia NON basti conoscere la password del Wi-Fi per aprire l'app e controllare cancelli, luci o telecamere**, e che ogni membro della famiglia abbia il proprio accesso e i propri permessi:

1. **Eliminazione di `VITE_HA_TOKEN` in produzione & Switch a Home Assistant OAuth2 (`getAuth()`):**
   - Oggi `src/ha/HAClient.js` usa `createLongLivedTokenAuth` con `import.meta.env.VITE_HA_TOKEN`, che Vite incorpora in chiaro dentro il JS compilato in `dist/`.
   - Progetta una **doppia modalità pulita**:
     - **Sviluppo (`dev`):** continua a supportare opzionalmente `VITE_HA_TOKEN` (da `.env.local` non committato) per test rapidi sul portatile, più fallback Mock/Demo se non configurato.
     - **Produzione (`prod`):** usa `getAuth()` (flusso OAuth2 nativo di `home-assistant-js-websocket`) in modo che ogni dispositivo/familiare effettui il login **una sola volta** con il proprio utente personale Home Assistant (con eventuale 2FA), salvando i token solo localmente in quel browser (revocabili singolarmente da HA in caso di smarrimento dispositivo, con audit log reale in HA su chi ha eseguito cosa).
2. **Protezione di `spatial_server` (`spatial_server/main.py`) e `go2rtc` (`go2rtc/go2rtc.yaml`):**
   - Oggi entrambi ascoltano su `0.0.0.0` senza autenticazione e con CORS aperto (`allow_origins=["*"]` / `origin: "*"`), esponendo tracce storiche (`/api/v1/tracks`), snapshot proxy (`/api/v1/ha-camera/snapshot/{entity_id}` che usa il token server-side), calibrazioni (`POST /api/v1/calibration/*`), cambio modalità CV (`POST /api/v1/ingestion/mode`), stream live `/go2rtc/*` e WebSocket `/ws/spatial`.
   - In produzione devono ascoltare **solo su `127.0.0.1`** (non esposti direttamente sulla LAN) ed essere raggiungibili **unicamente tramite il Reverse Proxy HTTPS**.
   - Progetta un meccanismo di **Single Sign-On basato su Home Assistant** (senza creare un secondo DB di username/password): validazione lato FastAPI e/o Reverse Proxy (`forward_auth` / cookie di sessione HttpOnly o Bearer token validato con cache TTL breve contro l'API di Home Assistant), applicata anche a WebSocket (`/ws/spatial`) e agli stream `go2rtc` (`/go2rtc/*`).
   - Restringi CORS agli origin effettivi di produzione/dev invece di `*`.
3. **Separazione Ruoli: Modalità "Admin" vs "Residente/Famiglia":**
   - I familiari in casa o su mobile/tablet non devono poter alterare per sbaglio la calibrazione ottica delle telecamere o cambiare pipeline OpenVINO/MQTT/Synthetic.
   - Verifica i permessi dell'utente HA autenticato (`is_owner` / `is_admin` tramite API HA):
     - **Lato Frontend:** nascondi/disabilita controlli amministrativi (es. `Calibra Cam` in `src/ui/TopBar.js`, `CalibrationAssistantUI`, toggle `CV_INGESTION_MODE` in `src/devices/camera/SecurityCameraModal.js`) agli utenti non-admin.
     - **Lato Backend (`spatial_server/main.py`):** proteggi con controllo ruolo Admin gli endpoint mutativi/sensibili (`POST /api/v1/calibration/*`, `POST /api/v1/calibration/solve-pnp`, `POST /api/v1/ingestion/mode`).
4. **Sicurezza di Rete & Topologia Tailscale (Runbook operativo fuori codice):**
   - **Stato attuale della tailnet:** oggi Tailscale gira come Add-on nella VM Home Assistant (`192.168.86.24`) ed è collegato al portatile, al mio telefono e a un altro dispositivo non pertinente; inoltre i familiari hanno già un proprio account Tailscale/HA.
   - **Installazione su PC Fisso + Condivisione Famiglia (Piano Free Personal):** installa il client Tailscale nativo anche su **Windows 10 del PC Fisso**. Sul piano gratuito **Personal** (fino a **6 utenti** nella tailnet, dispositivi utente **illimitati**, fino a 50 risorse taggate e 3 gruppi ACL) puoi scegliere:
     - **Node Sharing (`Share...`) del solo nodo PC Fisso:** isola completamente il dispositivo estraneo e il portatile (i familiari vedono *solo* `pc-fisso.<tailnet>.ts.net`, inclusa `:443` per la PWA e `:8443` per HA, ricordando che i nodi condivisi *non* ereditano i Subnet Router);
     - **Oppure utenti nella tailnet (fino a 6 utenti) + ACL Tailscale** per limitare i dispositivi familiari alle sole porte `443` e `8443` del PC Fisso (bloccando RDP, SMB, SSH).
   - Documenta anche la rete **Wi-Fi Ospiti con Isolamento Client** (così gli ospiti non vedono `192.168.86.0/24`).

### B. Strategia HTTPS & URL Unico (100% Gratuito con `Tailscale Serve` — Zero Domini a Pagamento)
Per una PWA installabile su iOS ("Aggiungi a schermata Home") e Android (Service Worker + schermo intero), l'applicazione deve essere servita **in HTTPS valido sullo stesso identico URL** sia sul Wi-Fi di casa sia da remoto, **senza acquistare alcun dominio esterno e senza aprire porte sul router**:
- **Soluzione scelta e confermata — `Tailscale Serve` + Caddy locale su `127.0.0.1`:**
  - `Tailscale Serve` (`tailscale serve --bg 8080` + opzionale `--https=8443 http://192.168.86.24:8123`) gestisce automaticamente rilascio e rinnovo del certificato HTTPS Let's Encrypt su `https://<pc-fisso>.<tailnet>.ts.net` (senza configurazione TLS manuale in Caddy né `tailscale cert`).
  - **Vantaggi:** zero costi, zero DNS esterno, zero port-forwarding, certificato accettato nativamente da iOS/Android/Desktop, **stesso URL identico sia a casa sia fuori** (funziona anche verso utenti esterni tramite FQDN completo con *Node Sharing*).
  - **Instradamento mobile (nessun Exit Node richiesto) & App Browser:**
    - Non serve configurare né attivare un *Exit Node*: il traffico Internet normale (ricerche Google, YouTube, app terze) esce sempre diretto dalla rete del telefono. Tailscale instrada nel tunnel **solo** il traffico diretto agli indirizzi della tailnet (`100.64.0.0/10` / `*.ts.net`).
    - Se sui telefoni Android/iOS viene usato il filtro *App Split Tunneling* di Tailscale, nella guida chiarisci che va incluso il browser che gestisce la PWA (es. Chrome/Safari), spiegando che ciò non fa comunque passare da casa la normale navigazione web.
    - Documenta *Tailscale On-Demand* / risparmio batteria per uso fluido su iOS e Android sia sul Wi-Fi domestico sia fuori casa.

### C. Trasformazione Frontend in Vera PWA & Refactoring di Rete/Streaming
Analizza lo stato aggiornato dei file frontend e prevedi nel piano:
1. **PWA Installabile (`vite-plugin-pwa` / Workbox + `index.html`):**
   - Web App Manifest completo (`manifest.webmanifest`, `display: "standalone"`, icone `192x192`, `512x512`, `apple-touch-icon`, meta tag iOS `apple-mobile-web-app-capable`, `viewport-fit=cover`, orientamento/theme color coerenti col design dell'app).
   - Strategia Service Worker mirata:
     - Precache degli asset statici dell'app (`HTML/JS/CSS`, loghi in `public/logos/`).
     - Gestione intelligente di `public/models/house_optimized.glb` (~2,6 MB+) e `public/models/scene_manifest.json` (`NetworkFirst` o hash di versione, affinché ogni export aggiornato da Blender venga scaricato automaticamente dai dispositivi senza rimanere bloccati sulla vecchia casa in cache).
     - **Esclusione tassativa dalla cache** (NetworkOnly) per `/api/*`, `/ws/*`, `/go2rtc/*` e per i callback OAuth di Home Assistant.
     - Banner/toast discreto in italiano per notificare quando è disponibile una nuova versione ("Nuova versione disponibile — Aggiorna") con `skipWaiting` controllato.
2. **Eliminazione dipendenze da `localhost` e supporto Same-Origin:**
   - Rimuovi il presupposto di `http://localhost:8765` e `http://localhost:1984` in produzione in `src/spatial/network/SpatialStreamClient.js`, `src/video/VideoStreamManager.js`, `src/video/Go2RtcWebRTCStream.js`, `src/video/Go2RtcMSEStream.js`, `src/video/HaSnapshotFallbackStream.js` e `src/ha/HAClient.js`.
   - In produzione, usa path relativi same-origin (`/api/v1/...`, `wss://<host>/ws/spatial`, `/go2rtc/...`) con fallback configurabile per `dev` (mantenendo intatto il workflow attuale con `npm run dev`).
   - Verifica che in produzione il fallback snapshot delle telecamere punti direttamente a `/api/v1/ha-camera/snapshot/{entity_id}` di `spatial_server` (dato che il middleware `haCameraBridgePlugin` in `vite.config.js` non esiste nella build statica `dist/`).
3. **Streaming Video Mobile/Tailscale (`go2rtc` WebRTC vs MSE):**
   - In `go2rtc/go2rtc.yaml`, `webrtc.candidates` attualmente contiene solo `127.0.0.1:8555` e `stun:8555`, che non funzionano da mobile o via Tailscale.
   - Prevedi una configurazione pulita per supportare sia **WebRTC** da LAN/Tailscale (es. candidates parametrici per IP LAN + IP Tailscale + apertura mirata porta `8555` TCP/UDP su Windows Firewall verso LAN/Tailscale) sia il fallback automatico affidabile su **MSE via `wss://.../go2rtc/api/ws`** sulla sola porta `443` del Reverse Proxy.
4. **Ottimizzazione Mobile, Tablet & Risparmio Batteria:**
   - Modifica `src/core/SceneManager.js` per mettere in pausa/throttling il render loop `requestAnimationFrame` quando `document.hidden === true` (fondamentale su smartphone/tablet quando l'app è in background).
   - Valuta profili grafici adattivi / lightweight su mobile (pixel ratio, shadow map o toggle qualità) e verifica l'ergonomia touch di UI, modali, `TopBar.js` e controlli Orbit/Raycast su iOS Safari e Android Chrome.

### D. Pipeline di Sviluppo, Versioning, Deploy & Servizi Windows
Progetta una pipeline chiara e riproducibile tra **Portatile (Dev)**, **Git** e **PC Fisso Windows 10 (Prod)**:
1. **Igiene Repository (`.gitignore`):** `.gitignore` esclude già `.env`, `.env.local`, `.venv/`, `node_modules/`, `dist/`, `go2rtc/go2rtc.exe`, `spatial_server/data/*.db*` e `spatial_server/models/`, ma **aggiungi anche `spatial_server/data/camera_calibrations.json`** (e l'eventuale eseguibile `caddy.exe` / certificati locali) affinché le calibrazioni locali del PC Fisso non creino conflitti né vengano sovrascritte da commit dal portatile.
2. **Estensione Script di Deploy / Update (`scripts/update_services.bat`, `start_services.bat`, `stop_services.bat`, `setup_windows_node.ps1`):**
   - NON creare script duplicati da zero: integra e potenzia `scripts/update_services.bat` (che oggi fa già `git fetch` + `reset --hard origin/main`, aggiornamento `.venv`/`npm` su diff, rebuild condizionale di `dist/` se presente e riavvio servizi).
   - Fai in modo che in produzione `dist/` venga sempre ricostruito quando cambia il frontend (anche alla prima configurazione), integrando gestione/reload di **Caddy** (e download opzionale in `setup_windows_node.ps1`), check prerequisiti (`VC_redist.x64` per OpenVINO) e uniformazione di `REOLINK_CARRAIO_PASS` / `REOLINK_CARRAIO_PASSWORD`.
3. **Esecuzione Unattended al Boot di Windows 10 (Post-Blackout / Auto-Login):** gestione di `go2rtc`, `spatial_server` (`uvicorn`) e `Caddy` come **Servizi di Windows nativi** (es. tramite **NSSM** sotto account di sistema/servizio senza dipendere da password utente interattive o errori dell'Utilità di pianificazione su PC con auto-login al boot), con restart automatico su crash e log rotati, rispettando il vincolo di memoria (`8 GB` RAM condivisi con la VM VirtualBox di Home Assistant).
4. **Runbook Finale in Italiano (`docs/`):** guida passo-passo per configurare:
   - utenti Home Assistant (ruoli Admin vs Residente) e modifica a `configuration.yaml` di HA (`use_x_forwarded_for: true` + aggiunta dell'IP LAN del PC Fisso in `trusted_proxies` senza rimuovere eventuali proxy già presenti, **lasciando acceso e invariato l'Add-on Tailscale di HA** così l'App ufficiale HA e Tasker continuano a usare lo stesso indirizzo attuale);
   - installazione di Tailscale nativo su Windows 10 del PC Fisso, Caddy + `Tailscale Serve` HTTPS (`:443` + `:8443`), *Node Sharing* / ACL Tailscale e Wi-Fi Ospiti;
   - Windows Firewall e servizi Windows NSSM;
   - onboarding una-tantum sui telefoni/tablet di famiglia (Safari iOS / Chrome Android + inclusione del browser nello Split Tunneling senza Exit Node + Tailscale On-Demand).

---

## 4. Procedura Richiesta (Usa `/plan`)
1. **Ispeziona prima lo stato aggiornato del repository** (tutti i file in `src/`, `spatial_server/`, `go2rtc/`, `scripts/`, `public/models/`, `vite.config.js`, `package.json`, `.env.example`, `.gitignore`) perché rispetto alla stesura di questo prompt potrei aver aggiunto nuove telecamere, dispositivi o modificato file.
2. **Segnala subito eventuali gap, conflitti o domande di allineamento** (es. esposizione HA su porta `:8443` via `Tailscale Serve` dal PC Fisso vs uso dell'Add-on Tailscale HA, *Node Sharing* vs utenti nella stessa tailnet con ACL, gestione WebRTC porta `8555` vs solo MSE su `443`, configurazione *Tailscale On-Demand* sui dispositivi di famiglia).
3. **Produci un Piano di Implementazione dettagliato ed esaustivo (stile `/plan`)** suddiviso in fasi atomiche, ordinate per dipendenze, con elenco esatto dei file da creare/modificare, architettura OOP/SOLID coerente col resto del progetto, criteri di verifica end-to-end (desktop, mobile iOS/Android, LAN vs Tailscale, admin vs utente famiglia, installazione PWA e offline/update test) **prima di applicare modifiche**.
```
