# `go2rtc/` — Media Server RTSP / WebRTC / MSE Nativo

Questa directory ospita [`go2rtc/go2rtc.yaml`](./go2rtc.yaml), la configurazione di **go2rtc** eseguito nativamente su Windows (`go2rtc\go2rtc.exe`, gestito come servizio `SmartHome3D-go2rtc`). Tutti i flussi delle 4 telecamere Reolink PoE operano in **passthrough** senza transcoding software FFmpeg per preservare la CPU Intel Core `i5-6400`.

---

## Configurazione Porte e Interfacce ([`go2rtc/go2rtc.yaml`](./go2rtc.yaml))

| Sezione YAML | Direttiva | Valore | Scopo & Sicurezza |
|---|---|---|---|
| `api` | `listen` | `"127.0.0.1:1984"` | API HTTP/WebSocket esposta solo su loopback. Esposta all'esterno esclusivamente via Caddy (`/go2rtc/api/webrtc*`, `/go2rtc/api/ws*`) con `forward_auth`. |
| `api` | `origin` | `""` | Nessun wildcard `*` CORS abilitato. |
| `rtsp` | `listen` | `"127.0.0.1:8554"` | Server RTSP locale consumato da `spatial_server` (`OpenVINORtspDetectionSource`, `DualTierNvrRecorderCoordinator`). |
| `webrtc` | `listen` | `":8555"` | Porta media ICE TCP/UDP protetta dalle regole Firewall `SmartHome3D-WebRTC-{TCP,UDP}-8555` (`LanCidr` + `100.64.0.0/10`). |
| `webrtc` | `candidates` | `${GO2RTC_CANDIDATE_LAN:127.0.0.1:8555}`, `${GO2RTC_CANDIDATE_TAILSCALE:127.0.0.1:8555}`, `stun:8555` | Candidati ICE parametrici letti da `.env` (via NSSM `AppEnvironmentExtra`). |

> [!IMPORTANT]
> Non inserire mai password o IP reali hardcoded in `go2rtc.yaml`: la suite [`tests/e2e/test_f4_go2rtc_yaml.py`](../tests/e2e/test_f4_go2rtc_yaml.py) verifica automaticamente che tutte le credenziali usino placeholder `${VAR:...}` e che `api.listen` / `rtsp.listen` restino vincolati a `127.0.0.1`.

---

## Catalogo Completo degli Stream Configurati

`go2rtc.yaml` definisce **16 stream** (4 per ciascuna delle 4 telecamere reali):

| Camera | Modello Reolink | IP Default | Stream Principali (`_main`, `_sub`, alias) | Snapshot CGI (`_snap`) |
|---|---|---|---|---|
| **Carraio** (`Cam_Carraio`) | RLC-540A | `192.168.86.47` | `carraio_main` (`h264Preview_01_main`), `carraio_sub` (`h264Preview_01_sub`), `carraio_scorrevole` -> `rtsp://127.0.0.1:8554/carraio_main` | `carraio_snap` -> `http://${REOLINK_CARRAIO_IP:192.168.86.47}:80/cgi-bin/api.cgi?cmd=Snap&channel=0&rs=sh3d...` |
| **Portico** (`Cam_Portico`) | RLC-810A | `192.168.86.51` | `portico_main` (`h264Preview_01_main`), `portico_sub` (`h264Preview_01_sub`), `portico` -> `rtsp://127.0.0.1:8554/portico_main` | `portico_snap` -> `http://${REOLINK_PORTICO_IP:192.168.86.51}:80/cgi-bin/api.cgi?cmd=Snap&channel=0&rs=sh3d...` |
| **Ingresso** (`Cam_Ingresso`) | Duo 3 PoE 180° | `192.168.86.53` | `ingresso_main` (`Preview_01_main`), `ingresso_sub` (`Preview_01_sub`), `ingresso` -> `rtsp://127.0.0.1:8554/ingresso_main` | `ingresso_snap` -> `http://${REOLINK_INGRESSO_IP:192.168.86.53}:80/cgi-bin/api.cgi?cmd=Snap&channel=0&rs=sh3d...` |
| **Stradina** (`Cam_Stradina`) | Duo 3 PoE 180° | `192.168.86.55` | `stradina_main` (`Preview_01_main`), `stradina_sub` (`Preview_01_sub`), `stradina` -> `rtsp://127.0.0.1:8554/stradina_main` | `stradina_snap` -> `http://${REOLINK_STRADINA_IP:192.168.86.55}:80/cgi-bin/api.cgi?cmd=Snap&channel=0&rs=sh3d...` |

### Variabili `.env` Utilizzate
Per ogni camera `<SLUG>` in `{CARRAIO, PORTICO, INGRESSO, STRADINA}`:
- `REOLINK_<SLUG>_IP`
- `REOLINK_<SLUG>_USER` *(default `admin`)*
- `REOLINK_<SLUG>_PASS` *(su Carraio `install_windows_services.ps1` supporta anche il fallback legacy `REOLINK_CARRAIO_PASSWORD`)*
- `GO2RTC_CANDIDATE_LAN` e `GO2RTC_CANDIDATE_TAILSCALE`

---

## Come Viene Consumato nel Sistema

1. **Frontend Live (`VideoStreamManager`)**:
   - **WebRTC (`Go2RtcWebRTCStream`, timeout `2200 ms`)**: `POST /go2rtc/api/webrtc?src=<stream>` (in prod via Caddy `forward_auth`) + media UDP/TCP su `:8555`.
   - **MSE (`Go2RtcMSEStream`, iOS 17+ `ManagedMediaSource` / H.265 `hevc` supportato)**: WebSocket `/go2rtc/api/ws?src=<stream>` (fMP4 su HTTPS `:443`).
   - **Fallback (`HaSnapshotFallbackStream`)**: se WebRTC e MSE falliscono, usa `/api/v1/ha-camera/snapshot/{entity_id}`.
2. **Computer Vision (`spatial_server`)**:
   - **Tracking YOLOv8n OpenVINO**: legge i substream leggeri da `rtsp://127.0.0.1:8554/<slug>_sub` (mappati automaticamente da `scene_manifest.json` tramite `sub_stream_id`).
   - **Biometria Face/ALPR (`Go2RtcSnapshotProvider`) & `SceneEventManager`**: richiedono frame JPEG on-demand via HTTP loopback `http://127.0.0.1:1984/api/frame.jpeg?src=<stream>` provando in ordine `*_snap`, `*_main`, `*_sub` (con fallback sull'ultimo frame substream decodificato in RAM).
   - **NVR Dual-Tier**: legge sia `<slug>_sub` (segmenti continui H24) sia `<slug>_main` (ring buffer RAM + clip eventi).

---

## Riferimenti Correlati
- Reverse proxy & `forward_auth` su `go2rtc`: [`caddy/README.md`](../caddy/README.md)
- Setup telecamere Reolink & porte RTSP/ONVIF: [`docs/runbooks/reolink-and-services.md`](../docs/runbooks/reolink-and-services.md)
- Aggiunta nuova telecamera: [`docs/runbooks/add-camera.md`](../docs/runbooks/add-camera.md)
- Test validazione `go2rtc.yaml` (`test_f4`): [`docs/reference/testing-suite.md`](../docs/reference/testing-suite.md)
