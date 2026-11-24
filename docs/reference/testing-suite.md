# Guida Completa alla Suite di Test (`tests/e2e/` e `spatial_server/tests/`)

Questo documento descrive l'intera architettura di testing automatico di **Smart_Home_3D**, composta complessivamente da **298 test item** raccolti dalla discovery standard di `pytest` (`tests/e2e/`: **248 test item** in 23 file; `spatial_server/tests/test_*.py`: **50 test item** in 8 file), ai quali si aggiungono gli **11 check** in [`spatial_server/tests/verify_pipeline.py`](../../spatial_server/tests/verify_pipeline.py) (eseguibili passando esplicitamente il file a `pytest` o via `python`). Completa la dotazione il layer di helper Python/Node e gli script di verifica CLI.

> [!NOTE]
> Il progetto **non** utilizza `vitest`: tutti i test sui moduli JavaScript/ESM frontend vengono eseguiti tramite **Node.js + Vite SSR** orchestrato direttamente da `pytest` attraverso gli harness in `tests/e2e/helpers/`.

---

## 1. Come Eseguire i Test

Tutti i test Python usano il virtualenv locale `.venv` nella root del repository:

```powershell
# 1. Discovery standard completa (E2E + spatial_server/tests/test_*.py: 298 test item)
.\.venv\Scripts\python.exe -m pytest tests/e2e spatial_server/tests -v

# 2. Suite backend completa includendo verify_pipeline.py (50 + 11 = 61 test item)
.\.venv\Scripts\python.exe -m pytest spatial_server/tests spatial_server/tests/verify_pipeline.py -v
.\.venv\Scripts\python.exe spatial_server/tests/verify_pipeline.py

# 3. Solo suite E2E (248 test item)
.\.venv\Scripts\python.exe -m pytest tests/e2e -v

# 4. Solo discovery standard backend (50 test item)
.\.venv\Scripts\python.exe -m pytest spatial_server/tests -v

# 4. Filtraggio per marker Tier (su file decorati con @pytest.mark.tier1 / tier2)
.\.venv\Scripts\python.exe -m pytest tests/e2e -m tier1 -v
.\.venv\Scripts\python.exe -m pytest tests/e2e -m tier2 -v

# 5. Singola feature o scenario cross-feature (esempi)
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_f16_runbook_e2e.py tests/e2e/test_f7_repo_hygiene.py -v
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_tier3_cross_feature.py tests/e2e/test_tier4_scenarios.py -v
```

### Verifiche Complementari Node.js & Config
```powershell
# Verifica lettura mapping dispositivi Home Assistant (deve risolvere docs/reference/ha-devices-mapping.md)
node tools/read_mapped.mjs

# Ispezione config VitePWA in modalità production senza leggere .env reale
node tests/e2e/helpers/vite_config_inspect.mjs production

# Validazione sintattica Caddyfile (se caddy\caddy.exe è presente)
.\caddy\caddy.exe validate --config .\caddy\Caddyfile --adapter caddyfile
```

> [!IMPORTANT]
> Su Windows in runner sandboxed, `FastAPI/Starlette TestClient` e il server loopback locale `FakeHAServer` in [`tests/e2e/conftest.py`](../../tests/e2e/conftest.py) richiedono permessi di socket loopback locali (vedi docstring in `pytest_configure`). Inoltre `tests/e2e/conftest.py` imposta deterministicamente `_PRE_SEEDED_ENV` prima di importare `spatial_server.*`, garantendo l'isolamento da eventuali impostazioni locali in `.env`.

---

## 2. Architettura Tiered di `tests/e2e/` (`conftest.py` e `helpers/`)

### 2.1 Fixture e Isolation Layer ([`tests/e2e/conftest.py`](../../tests/e2e/conftest.py))
- **`pytest_configure`**: pre-inizializza `os.environ` con valori sicuri (`SH3D_DEV_MODE=false`, `SPATIAL_AUTH_REQUIRED=true`, `CV_INGESTION_MODE=synthetic`, chiavi `VITE_HA_*` azzerate) e registra 4 marker pytest (`tier1`, `tier2`, `tier3`, `tier4`).
- **`FakeHAServer` (`fake_ha_server`)**: server FastAPI/Uvicorn in-process su porta effimera `127.0.0.1` che emula Home Assistant:
  - `GET /api/` (controllo Bearer token ed override status per test failure).
  - `GET /api/camera_proxy/{entity_id}` (restituisce `_MINIMAL_JPEG` valido per camera autorizzata).
  - `WS /api/websocket` (`auth_required` -> `auth` -> `auth_ok` -> `auth/current_user` con token predefiniti `tok-admin`, `tok-owner`, `tok-resident`, più modalità di errore `auth_current_user_error` e `drop`).
- **`isolated_app_factory` / `client`**: istanzia `create_app(cfg)` con DB SQLite, `data_dir`, `models_dir` e `camera_calibrations.json` isolati in `tmp_path`.

### 2.2 Helper in [`tests/e2e/helpers/`](../../tests/e2e/helpers/)
| File | Ruolo |
|---|---|
| [`artifacts.py`](../../tests/e2e/helpers/artifacts.py) | Validazione binary PNG via header `IHDR` + `cv2.imdecode` (`parse_png_info`), scansione anti-segreti su `dist/assets/*.js` e `.js.map` (`scan_dist_js_secrets`: pattern token JWT codificati, `Bearer ...`, `VITE_HA_TOKEN`), parsing `<meta>`/`<link>`/`<script>` HTML (`parse_html_meta`), runner `run_js_scenario` e `inspect_vite_config`. |
| [`js_harness.mjs`](../../tests/e2e/helpers/js_harness.mjs) | Runner Vite SSR ESM con shim completo di DOM (`DomDocument`, `DomElement`, `ClassList`), Canvas 2D, WebGL2 proxy, `localStorage`, `fetch`, `WebSocket`, `RTCPeerConnection`, `MediaSource`/`ManagedMediaSource` per eseguire scenari sui veri moduli `src/**/*.js`. |
| [`tier34_js_harness.py`](../../tests/e2e/helpers/tier34_js_harness.py) | Wrapper Python + `_BROWSER_SHIM_JS` usato dai test Tier 3/4 (`run_vite_module_script`, `resolve_vite_config_json`) per importare ed eseguire moduli frontend in modalità `production` o `development` senza mai leggere `.env`. |
| [`ps_bat_harness.py`](../../tests/e2e/helpers/ps_bat_harness.py) | Compila al volo un eseguibile PE stub C# (`Sh3dTestStub`) e shadow PowerShell per testare `scripts/*.ps1` e `scripts/*.bat` in workspace temporanei isolati (AST parsing via `System.Management.Automation.Language.Parser`, simulazione `sc.exe`, `nssm.exe`, `git.exe`, `net.exe`, firewall, registro `HKLM:`), con zero effetti sull'OS reale. |
| [`vite_config_inspect.mjs`](../../tests/e2e/helpers/vite_config_inspect.mjs) | Carica `vite.config.js` facendo temporaneamente `chdir` in una directory vuota (evita la lettura di `.env`) ed estrae configurazione Vite e opzioni `VitePWA`. |

---

## 3. Catalogo Test E2E per Feature (`F1` – `F19`, Tier 3, Tier 4)

### 3.1 Suite Feature (`F1`–`F19`, Tier 1 Happy Path & Tier 2 Negative/Security/Boundary)

| File | Test | Focus Principale |
|---|---|---|
| [`test_f1_security_package.py`](../../tests/e2e/test_f1_security_package.py) | 12 | `spatial_server/security`: verifica token via HA WS `auth/current_user`, ruoli `Admin`/`Owner`/`Residente`, cache SHA-256 TTL, cookie HMAC `sh3d_session`, dipendenze FastAPI e WS auth. |
| [`test_f2_config_hardening.py`](../../tests/e2e/test_f2_config_hardening.py) | 16 | `spatial_server/config.py`: default loopback `127.0.0.1`, `auth_required=True`, parsing `SPATIAL_ALLOWED_ORIGINS` (rifiuto wildcard `*`), normalizzazione URL HA, bool parsing (`test_f2_t2_01` parametrizzato su 6 varianti). |
| [`test_f3_main_auth_rbac_ws.py`](../../tests/e2e/test_f3_main_auth_rbac_ws.py) | 15 | Endpoints `/api/v1/auth/session`, `/verify`, `/logout`, `401` non autenticati, `403` `Residente` su rotte mutative, proxy `/api/v1/ha-camera/snapshot/{entity_id}`, WS `/ws/spatial` (`4401` su mancata auth). |
| [`test_f4_go2rtc_yaml.py`](../../tests/e2e/test_f4_go2rtc_yaml.py) | 10 | Validazione YAML di `go2rtc/go2rtc.yaml`: bind loopback `127.0.0.1:1984` e `:8554`, `origin: ""`, WebRTC `:8555` con placeholder `${GO2RTC_CANDIDATE_*}`, nessuna password o IP cablato in chiaro. |
| [`test_f5_backend_test_compat.py`](../../tests/e2e/test_f5_backend_test_compat.py) | 10 | Compatibilità di `spatial_server/tests/test_security_auth.py` e `verify_pipeline.py`, e garanzia che `auth_required=true` non possa essere bypassato con header fittizi. |
| [`test_f6_caddyfile.py`](../../tests/e2e/test_f6_caddyfile.py) | 12 | `caddy/Caddyfile`: bind loopback `:8080`, security header, proxy `/api/v1/*` e `/ws/spatial`, `forward_auth` su `/go2rtc/api/webrtc*` e `/ws*`, `403` su `/go2rtc/*`, cache PWA e `caddy validate`. |
| [`test_f7_repo_hygiene.py`](../../tests/e2e/test_f7_repo_hygiene.py) | 10 | `.gitignore` (`git check-ignore`), `.env.example` (chiavi obbligatorie, default sicuri, zero segreti o token JWT, zero duplicati), `git ls-files` senza `.env` o `.exe` tracciati. |
| [`test_f8_ha_client_oauth.py`](../../tests/e2e/test_f8_ha_client_oauth.py) | 10 | `HAClient.js`: OAuth2 `getAuth`, risoluzione `hassUrl` (`:8443` su `*.ts.net`), `onAuthChange`, `getAccessToken`, divieto di silent fallback Mock in produzione. |
| [`test_f9_spatial_stream_client.py`](../../tests/e2e/test_f9_spatial_stream_client.py) | 10 | `SpatialStreamClient.js`: URL same-origin in prod vs fallback dev, `authenticateWithHaToken`, `credentials: 'include'`, gestione HTTP `401`/WS `4401` e dispatch frame. |
| [`test_f10_video_streams.py`](../../tests/e2e/test_f10_video_streams.py) | 14 | `VideoStreamManager`, `Go2RtcWebRTCStream` (`2200ms` timeout, `credentials: 'include'`), `Go2RtcMSEStream` (`ManagedMediaSource` iOS 17+), `HaSnapshotFallbackStream` e sharing stream persistente (Tier 3 locale). |
| [`test_f11_rbac_ui.py`](../../tests/e2e/test_f11_rbac_ui.py) | 10 | UI RBAC (`TopBar`, `SecurityCameraModal`, `CalibrationAssistantUI`, overlay login OAuth2 in `src/main.js`): nasconde e blocca controlli admin per utenti `Residente`. |
| [`test_f12_pwa_workbox.py`](../../tests/e2e/test_f12_pwa_workbox.py) | 10 | `vite-plugin-pwa`, regole `Workbox` in `vite.config.js` (`NetworkOnly` API/WS/go2rtc/OAuth, `NetworkFirst` manifest, `CacheFirst` `.glb`), verifica `dist/sw.js` e zero segreti in `dist/`. |
| [`test_f13_pwa_assets_prompt.py`](../../tests/e2e/test_f13_pwa_assets_prompt.py) | 10 | Icone PWA (`public/pwa/*` e `dist/pwa/*` validate via `IHDR` + `cv2`), meta tag iOS in `index.html`, `PwaUpdatePrompt.js` (`Aggiorna` -> `updateSW`) e CSS `safe-area`. |
| [`test_f14_glb_cache_mobile_perf.py`](../../tests/e2e/test_f14_glb_cache_mobile_perf.py) | 10 | Versioning deterministico `.glb` in `AssetLoader.js` (mai `Date.now()`) e pausa/ripresa `requestAnimationFrame` su `visibilitychange` in `SceneManager.js`. |
| [`test_f15_windows_deploy_e2e.py`](../../tests/e2e/test_f15_windows_deploy_e2e.py) | 17 | Dry-run completo degli script `scripts/*.ps1` e `scripts/*.bat`: AST PowerShell, provisioning binari, NSSM `AppEnvironmentExtra`, Firewall `:8555`, fallback console vs NSSM, rollback `update_services.bat`. |
| [`test_f16_runbook_e2e.py`](../../tests/e2e/test_f16_runbook_e2e.py) | 13 | Audit automatizzato di [`docs/runbooks/production-tailscale.md`](../runbooks/production-tailscale.md): sezioni richieste, porte, comandi `tailscale serve`/`netsh`, policy ACL, note iOS/Android, link relativi risolti e zero segreti. |
| [`test_f17_m3_ui_and_recordings.py`](../../tests/e2e/test_f17_m3_ui_and_recordings.py) | 15 | Redesign Material 3 (`NavigationFabHub`, `SecurityFabHub`), `ThermalController`/`ThermalModal`, multi-camera 180°/replay, responsività e provider OOP NVR/Edge. |
| [`test_f18_biometrics_ui.py`](../../tests/e2e/test_f18_biometrics_ui.py) | 5 | Avatar biometrici 3D + protezione XSS (`SpatialAvatarFactory`), filtri biometrici in `SecurityFabHub`, strip live in `SecurityCameraModal`, icone e flusso Admin HITL/Whitelist RBAC. |
| [`test_f18_calibration_persistence_sync.py`](../../tests/e2e/test_f18_calibration_persistence_sync.py) | 4 | Persistenza calibrazioni su restart server, caricamento legacy senza `ui_state`, `DELETE /api/v1/calibration/{camera_id}` RBAC + broadcast WS, sincronizzazione cross-device frontend. |
| [`test_f19_camera_coverage_occlusion.py`](../../tests/e2e/test_f19_camera_coverage_occlusion.py) | 3 | Modalità copertura camere 3-stati (`off` / `2D` / `3D`), occlusione raycast contro i muri, anchor guard `Cam_Portico` e rifiuto salti PnP eccessivi lato backend. |
| [`test_f19_events_and_notifications_ui.py`](../../tests/e2e/test_f19_events_and_notifications_ui.py) | 3 | Tab `Eventi` giornalieri in `SecurityFabHub`, jump al replay, allarme a 3 stati e builder azioni notifica in `AutomationStudioUI`. |

### 3.2 Suite Cross-Feature e End-to-End Realistici (`Tier 3` & `Tier 4`)

- **[`test_tier3_cross_feature.py`](../../tests/e2e/test_tier3_cross_feature.py)** (**20 test** `test_t3_01`..`test_t3_20`): verifica l'integrazione a coppie tra tutti i layer: Caddy `forward_auth` <-> FastAPI `/verify` e `go2rtc` (`403`), `HAClient` <-> `SpatialStreamClient` <-> cookie + WS, CORS + `8765`, `VideoStreamManager` + `HaSnapshotFallbackStream` + Caddy, `Workbox` + `Cache-Control` + `AssetLoader`, `.env.example` <-> `config.py` / `go2rtc.yaml` / `install_windows_services.ps1` / `start_services.bat`, `.gitignore` e consistenza cross-reference `scripts/` <-> runbook.
- **[`test_tier4_scenarios.py`](../../tests/e2e/test_tier4_scenarios.py)** (**9 scenari** `test_t4_01`..`test_t4_09`): simula cicli di vita utente completi:
  1. Ciclo completo Admin (`t4_01`) e workflow ristretto Residente (`t4_02`).
  2. Cold start PWA, versioning `.glb` e aggiornamento Service Worker (`t4_03`).
  3. Consistenza topologica Tailscale Serve `:443` + `:8443` same-origin (`t4_04`).
  4. Primo deploy Windows 10, aggiornamento unattended e crash recovery (`t4_05`).
  5. Catena fallback video iOS 17 Safari PWA (`t4_06`) e fallback snapshot multi-camera con `HA_TOKEN` vuoto (`t4_08`).
  6. Audit build di produzione zero-secret (`t4_07`) e risparmio energetico mobile `visibilitychange` (`t4_09`).

---

## 4. Suite Backend `spatial_server/tests/` (50 Test Discovery + 11 in `verify_pipeline.py`)

| File | Test | Copertura |
|---|---|---|
| [`verify_pipeline.py`](../../spatial_server/tests/verify_pipeline.py) | 11 | Test core pipeline spaziale: ottica pinhole/panoramica, letterbox OpenVINO e parsing output, ancora di persistenza stazionaria/slow-drift, `TrimeshGroundRaycaster`, `Kalman3DMultiTracker` + fusione multi-camera, `SQLiteWALTrackRepository`, REST e WebSocket. |
| [`test_security_auth.py`](../../spatial_server/tests/test_security_auth.py) | 11 | `SpatialServerConfig.from_env`, verifica WS + cache SHA-256, fallback REST fail-closed, tampering/scadenza `sh3d_session`, codici `401`/`403`, CORS e protezione path-traversal su endpoint crop biometrici. |
| [`test_biometrics_unit.py`](../../spatial_server/tests/test_biometrics_unit.py) | 9 | Post-processing targhe italiane, fuzzy match Levenshtein + tie-rejection, matching galleria volti e margin threshold, consensus locking, sicurezza `BiometricCropStore` + quota pruning, decodifica panoramica e circuit breaker `Go2RtcSnapshotProvider`. |
| [`test_nvr_dual_tier.py`](../../spatial_server/tests/test_nvr_dual_tier.py) | 7 | Ring buffer RAM GOP + budget per camera, macchina a stati eventi `main` (pre-roll, inerzia, rollover, trigger manuale), indice SQLite `nvr_index.db` + lookahead + fallback HEVC, retention disco (sacrificio `sub` prima di `main`) e API/RBAC NVR. |
| [`test_biometrics_integration.py`](../../spatial_server/tests/test_biometrics_integration.py) | 5 | Flusso end-to-end face lock + persistenza + WS + handover multi-camera, ALPR whitelist lock, isolamento circuit-breaker con `go2rtc` lento, normalizzazione classi MQTT motorbike, `build_pipeline` e `/api/v1/status`. |
| [`test_biometrics_persistence.py`](../../spatial_server/tests/test_biometrics_persistence.py) | 5 | Migrazione idempotente schema DB legacy preservando WAL, seed `max_track_id` al riavvio, backfill biometrico e filtri query, dedup eventi biometrici e race-safety sync whitelist. |
| [`test_scene_events_and_notifications.py`](../../spatial_server/tests/test_scene_events_and_notifications.py) | 5 | Narratore naturale italiano multi-soggetto, `EventSnapshotStore`, ranking camere e cattura `SceneEventManager`, integrazione `HomeAssistantBridgeService` + notifiche con late biometric update, endpoint eventi e token media HMAC. |
| [`test_biometrics_hitl.py`](../../spatial_server/tests/test_biometrics_hitl.py) | 4 | Flusso Admin Human-in-the-Loop (`assign` volto con enrollment crop e backfill DB, `assign` targa + sync whitelist, reload/delete identità e prune crop). |
| [`test_automations_engine.py`](../../spatial_server/tests/test_automations_engine.py) | 4 | Geometria poligoni/attraversamenti perimetro orientati, cinematica sliding-window (velocità/direzione/transizioni zona), motore regole IF/THEN/ELSE end-to-end e API REST `/api/v1/automations/*`. |

---

## Riferimenti Correlati
- Configurazione variabili di test/ambiente: [env-variables.md](./env-variables.md)
- Panoramica architetturale e sicurezza: [system-overview.md](../architecture/system-overview.md)
- Runbook di produzione e checklist post-deploy: [production-tailscale.md](../runbooks/production-tailscale.md)
- Script Windows testati in `test_f15`: [scripts/README.md](../../scripts/README.md)
