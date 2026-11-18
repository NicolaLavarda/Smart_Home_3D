# 🚀 Prompt Master — Trasformazione in PWA Self-Hosted di Produzione, Sicurezza Multi-Utente, Reverse Proxy HTTPS & Pipeline Famiglia

> **Come usare questo prompt:** Quando avrai completato la calibrazione delle telecamere, aggiunto tutte le nuove telecamere e consolidato il setup sul PC Fisso, incolla il contenuto del blocco sottostante in una nuova sessione (idealmente attivando `/plan`) per far analizzare lo stato aggiornato del repository e generare un piano d'implementazione completo, prima di scrivere codice.

---

```markdown
Agisci come **Principal Full-Stack Architect, Security/DevOps Engineer (Windows Native / Reverse Proxy / Tailscale) e Senior Web/PWA Engineer (Three.js / Vite / FastAPI)**.

## 1. Contesto del Progetto e Stato Attuale (Smart Home 3D)
Il progetto **Smart Home 3D** (`Digital Twin & Spatial CV Engine`) è ora pronto sul piano 3D, telecamere e calibrazione sul PC Fisso Windows 10 (**Intel i5-6400 / 8 GB RAM / Zero Docker / Zero WSL2**), con Home Assistant OS + Mosquitto MQTT in VM VirtualBox (`192.168.86.24`), `go2rtc.exe` e il microservizio Python `spatial_server` (FastAPI + OpenVINO + SQLite3 WAL + `camera_calibrations.json`) nativi su Windows.

Ora l'obiettivo è portare l'applicazione in **produzione familiare multi-dispositivo** (smartphone iOS/Android, tablet domestici/a muro e PC) come **PWA installabile, sicura e aggiornabile centralmente**, utilizzabile senza attriti sia **in locale sul Wi-Fi di casa** sia **da remoto via Tailscale**.

---

## 2. Decisione Architetturale Già Approvata (Vincolante)
È stata già valutata e scelta l'architettura **PWA Self-Hosted sul PC Fisso + Reverse Proxy HTTPS Same-Origin + Home Assistant OAuth2 + Tailscale**:
- **NO** pubblicazione del sistema reale su Firebase Hosting (esporrebbe `VITE_HA_TOKEN` nel bundle statico, causerebbe blocchi Mixed Content `HTTPS -> HTTP/WS`, eliminerebbe i backend/proxy locali).
- **NO** distribuzione di pacchetti statici/APK/ZIP per singolo dispositivo.
- **SÌ** a un **Reverse Proxy HTTPS Same-Origin sul PC Fisso Windows 10** (es. **Caddy** nativo Windows, zero Docker) che espone sotto un'unica origine HTTPS:
  - `/` → build statica Vite di produzione (`dist/`)
  - `/api/v1/*` e `/ws/spatial` → `spatial_server` FastAPI (`127.0.0.1:8765`)
  - `/go2rtc/*` → `go2rtc` (`127.0.0.1:1984`)
  - *(da valutare nel piano)* `/ha/*` o connessione diretta HTTPS/WSS verso Home Assistant (`192.168.86.24:8123`), evitando qualsiasi problema di CORS e Mixed Content (`https://` + `wss://`).

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
4. **Sicurezza di Rete (Runbook operativo fuori codice):**
   - Documentazione chiara per: rete **Wi-Fi Ospiti con Isolamento Client** (così gli ospiti non vedono `192.168.86.0/24`), onboarding su **Tailscale** per i familiari (piano Free fino a 3 utenti / 100 dispositivi o *Tailscale Sharing*) e **ACL Tailscale** per limitare i dispositivi familiari alla sola porta HTTPS della PWA/HA (bloccando RDP, SMB, SSH sul PC Fisso).

### B. Strategia HTTPS & URL Unico (100% Gratuito con Solo Tailscale — Zero Domini a Pagamento)
Per una PWA installabile su iOS ("Aggiungi a schermata Home") e Android (Service Worker + schermo intero), l'applicazione deve essere servita **in HTTPS valido sullo stesso identico URL** sia sul Wi-Fi di casa sia da remoto, **senza acquistare alcun dominio esterno e senza aprire porte sul router**:
- **Soluzione scelta — Dominio gratuito Tailscale (`https://<nome-pc>.<tailnet>.ts.net`) con certificato Let's Encrypt automatico:**
  - Usa **`Tailscale Serve`** (terminazione TLS automatica gestita da Tailscale verso Caddy in ascolto locale su `127.0.0.1`) oppure **Caddy con certificato generato via `tailscale cert`** (con rinnovo automatico schedulato).
  - **Vantaggi:** zero costi, zero configurazione DNS esterna, zero port-forwarding, certificato HTTPS reale accettato nativamente da iOS/Android/Desktop, e **stesso URL sia a casa sia fuori** (con l'app Tailscale attiva / *VPN On-Demand* sui telefoni e tablet di famiglia).
  - **Nota per la rete locale / tablet fissi in casa:** valuta e documenta come assicurare l'accesso fluido anche quando si è sul Wi-Fi domestico (es. attivando *Tailscale On-Demand* o lasciando Tailscale connesso sui dispositivi con routing limitato alla sola tailnet `100.64.0.0/10` + eventuale subnet locale, così il resto del traffico Internet esce diretto senza rallentamenti né consumo batteria significativo).

### C. Trasformazione Frontend in Vera PWA & Refactoring di Rete/Streaming
Analizza lo stato aggiornato dei file frontend e prevedi nel piano:
1. **PWA Installabile (`vite-plugin-pwa` / Workbox + `index.html`):**
   - Web App Manifest completo (`manifest.webmanifest`, `display: "standalone"`, icone `192x192`, `512x512`, `apple-touch-icon`, meta tag iOS `apple-mobile-web-app-capable`, `viewport-fit=cover`, orientamento/theme color coerenti col design dell'app).
   - Strategia Service Worker mirata:
     - Precache degli asset statici dell'app (`HTML/JS/CSS`, loghi in `public/logos/`).
     - Gestione intelligente di `public/models/house_optimized.glb` (~2,6 MB+) e `public/models/scene_manifest.json` (`NetworkFirst` o hash di versione, affinché ogni export aggiornato da Blender venga scaricato automaticamente dai dispositivi senza rimanere bloccati sulla vecchia casa in cache).
     - **Esclusione tassativa dalla cache** (NetworkOnly) per `/api/*`, `/ws/*`, `/go2rtc/*`, `/ha/*` e callback OAuth di Home Assistant.
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
1. **Igiene Repository (`.gitignore`):** assicurati che `.env`, `.env.local`, `.venv/`, `node_modules/`, `dist/`, file DB `spatial_server/data/*.db*`, `spatial_server/data/camera_calibrations.json` (se specifico dell'ambiente server) ed eseguibili scaricati (`go2rtc.exe`, `caddy.exe`) non creino conflitti tra portatile e PC Fisso.
2. **Build & Deploy Script One-Click (`scripts/deploy_prod.ps1` o `.bat`):** sul PC Fisso esegue `git pull`, `npm ci && npm run build`, eventuale aggiornamento `.venv`, verifica configurazione Caddy/go2rtc e riavvio pulito dei servizi.
3. **Esecuzione Unattended al Boot di Windows 10:** gestione di `go2rtc`, `spatial_server` (`uvicorn`) e `Caddy` come **Servizi di Windows** (es. tramite **NSSM** o Task Scheduler senza sessione utente richiesta, con restart automatico su crash e log rotati), rispettando il vincolo di memoria (8 GB RAM totali condivisi con la VM Home Assistant).
4. **Runbook Finale in Italiano (`docs/`):** guida passo-passo per configurare utenti HA, Caddy + Tailscale HTTPS (`Tailscale Serve` / `tailscale cert`), Windows Firewall, servizi Windows, e onboarding una-tantum sui telefoni/tablet di famiglia (Safari iOS / Chrome Android + Tailscale On-Demand).

---

## 4. Procedura Richiesta (Usa `/plan`)
1. **Ispeziona prima lo stato aggiornato del repository** (tutti i file in `src/`, `spatial_server/`, `go2rtc/`, `scripts/`, `public/models/`, `vite.config.js`, `package.json`, `.env.example`, `.gitignore`) perché rispetto alla stesura di questo prompt potrei aver aggiunto nuove telecamere, dispositivi o modificato file.
2. **Segnala subito eventuali gap, conflitti o domande di allineamento** (es. architettura `Tailscale Serve` davanti a Caddy vs Caddy diretto con `tailscale cert`, eventuale reverse proxy anche per Home Assistant `/ha/*`, gestione WebRTC porta `8555` vs solo MSE su `443`, configurazione *Tailscale On-Demand* sui dispositivi di famiglia).
3. **Produci un Piano di Implementazione dettagliato ed esaustivo (stile `/plan`)** suddiviso in fasi atomiche, ordinate per dipendenze, con elenco esatto dei file da creare/modificare, architettura OOP/SOLID coerente col resto del progetto, criteri di verifica end-to-end (desktop, mobile iOS/Android, LAN vs Tailscale, admin vs utente famiglia, installazione PWA e offline/update test) **prima di applicare modifiche**.
```
