# `caddy/` — Reverse Proxy Same-Origin e Web Server PWA

Questa directory ospita [`caddy/Caddyfile`](./Caddyfile), la configurazione di **Caddy** eseguita nativamente su Windows dal servizio `SmartHome3D-Caddy` (`caddy\caddy.exe`, binario gitignored scaricato da [`scripts/setup_windows_node.ps1`](../scripts/setup_windows_node.ps1)).

---

## Architettura & Integrazione con Tailscale Serve

Caddy ascolta **esclusivamente su loopback** (`127.0.0.1:8080`) in HTTP con terminazione TLS delegata a **Tailscale Serve (`:443`)**:

```text
Browser / PWA (https://<pc-fisso>.<tailnet>.ts.net)
   └──► Tailscale Serve (:443, TLS Let's Encrypt)
           └──► Caddy (http://127.0.0.1:8080)
                   ├── /api/v1/*, /ws/spatial ──► 127.0.0.1:8765 (spatial_server)
                   ├── /go2rtc/api/webrtc*    ──► forward_auth :8765/api/v1/auth/verify ──► 127.0.0.1:1984
                   ├── /go2rtc/api/ws*        ──► forward_auth :8765/api/v1/auth/verify ──► 127.0.0.1:1984
                   ├── /go2rtc/* , /go2rtc    ──► 403 Forbidden
                   └── /*                     ──► dist/ (file_server + try_files /index.html)
```

---

## Dettaglio Direttive in [`caddy/Caddyfile`](./Caddyfile)

### 1. Blocco Globale & Listener
- `auto_https off`: disattiva la gestione certificati automatica di Caddy perché il TLS pubblico `*.ts.net` è gestito da Tailscale Serve.
- `trusted_proxies static 127.0.0.1/32 ::1/128`: accetta gli header `X-Forwarded-*` provenienti dal processo locale di Tailscale Serve su loopback.
- `http://:8080` + `bind 127.0.0.1`: impedisce l'esposizione di Caddy sulla scheda di rete LAN (`0.0.0.0`).

### 2. Header di Sicurezza Globali
Applicati su tutte le risposte del virtual host:
- `X-Content-Type-Options "nosniff"`
- `X-Frame-Options "SAMEORIGIN"`
- `Referrer-Policy "strict-origin-when-cross-origin"`

### 3. Routing Backend & `forward_auth` su `go2rtc`
| Route | Comportamento | Note di Sicurezza |
|---|---|---|
| `handle /api/v1/*` | `reverse_proxy 127.0.0.1:8765` | Tutte le REST API (auth, tracks, biometria, eventi, NVR, automazioni, calibrazioni, snapshot HA). |
| `handle /ws/spatial` | `reverse_proxy 127.0.0.1:8765` | WebSocket real-time verso `spatial_server` (autenticato da cookie `sh3d_session` o Bearer). |
| `handle /go2rtc/api/webrtc*` | `forward_auth 127.0.0.1:8765` (`uri /api/v1/auth/verify`) -> `uri strip_prefix /go2rtc` -> `reverse_proxy 127.0.0.1:1984` | Verifica la sessione utente su `spatial_server` prima di inoltrare offerte SDP WebRTC a `go2rtc`. |
| `handle /go2rtc/api/ws*` | `forward_auth 127.0.0.1:8765` (`uri /api/v1/auth/verify`) -> `uri strip_prefix /go2rtc` -> `reverse_proxy 127.0.0.1:1984` | Come sopra per streaming MSE su WebSocket. |
| `handle /go2rtc/*` e `handle /go2rtc` | `respond "Forbidden" 403` | Blocca pubblicamente la Web UI amministrativa di `go2rtc`, `/api/config`, `/api/streams`, ecc. |

**Dettagli tecnici critici nei blocchi `forward_auth`:**
- `header_up -Connection` e `header_up -Upgrade` dentro `forward_auth`: rimuove gli header di upgrade WebSocket dalla subrequest HTTP `GET /api/v1/auth/verify`, evitando errori durante il handshake `/go2rtc/api/ws*`.
- `header_up -Origin` dentro `reverse_proxy 127.0.0.1:1984` per `/go2rtc/api/ws*`: poiché [`go2rtc/go2rtc.yaml`](../go2rtc/go2rtc.yaml) imposta `api.origin: ""`, rimuovere l'header `Origin` dal proxy interno garantisce il corretto upgrade WebSocket di `go2rtc` senza aprire CORS wildcard su `:1984`.

### 4. Static PWA Serving & Cache-Control
- `root * dist` + `encode zstd gzip` + `try_files {path} /index.html` + `file_server` (nota: `AppDirectory` del servizio NSSM è la root del repository).
- **`@no_cache`** (`/`, `/index.html`, `/sw.js`, `/workbox-*.js`, `/registerSW.js`, `/manifest.webmanifest`, `/models/scene_manifest.json`): `Cache-Control "no-cache, must-revalidate"` per garantire l'aggiornamento immediato del Service Worker e del manifest SSoT 3D.
- **`@immutable_assets`** (`/assets/*`): `Cache-Control "public, max-age=31536000, immutable"` per i chunk JavaScript/CSS con hash generati da Vite.

---

## Comandi Operativi e Validazione

```powershell
# Validazione sintattica della configurazione
.\caddy\caddy.exe validate --config .\caddy\Caddyfile --adapter caddyfile

# Reload graceful (se avviato manualmente in console)
.\caddy\caddy.exe reload --config .\caddy\Caddyfile --adapter caddyfile

# Esposizione HTTPS pubblica tramite Tailscale Serve (da Admin)
tailscale serve --bg 8080
tailscale serve status
```

---

## Riferimenti Correlati
- Architettura & sicurezza same-origin: [`docs/architecture/system-overview.md`](../docs/architecture/system-overview.md)
- Media server protetto dietro Caddy: [`go2rtc/README.md`](../go2rtc/README.md)
- Test automatizzati `Caddyfile` (`test_f6` e `test_tier3`): [`docs/reference/testing-suite.md`](../docs/reference/testing-suite.md)
