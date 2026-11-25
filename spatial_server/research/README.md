# Smart Home 3D — Spazio Ricerca & Benchmark Produzione

Quando `spatial_server` viene avviato in produzione (`SH3D_DEV_MODE=false`), la telemetria diagnostica viene salvata **automaticamente in background** in `spatial_server/data/research_telemetry/`.

## Cosa viene raccolto (tutto a basso impatto e auto-potante)
- `session_meta.json`: specifiche hardware reali del PC fisso (CPU, RAM totale/libera, versioni runtime).
- `<YYYY-MM-DD>/system_health.jsonl`: CPU%, RAM%, memoria RSS, latenze OpenVINO per camera, stato giorno/notte IR, distribuzione degli FPS adattivi, slot auto parcheggiate.
- `<YYYY-MM-DD>/track_lifecycle.jsonl`: creazione, scadenza, riaggancio Re-ID, fusioni tracce e registrazione/rimozione posti auto.
- `<YYYY-MM-DD>/scene_events.jsonl`: durata, severità (`alert` / `silent_alert` / `notable` / `routine`), punteggio foto e soggetti consolidati.
- `<YYYY-MM-DD>/biometrics_and_reid_samples.jsonl` + `<YYYY-MM-DD>/crops/`: campioni rate-limited dei ritagli (max 6 per traccia, ogni >= 4s) con dimensioni pixel reali e luce giorno/notte, più esiti biometrici.
- `<YYYY-MM-DD>/anomalies.jsonl`: segnalazione automatica di episodi anomali (> 180s, > 2 veicoli, copertina persona < 100 punti, RAM > 85%, inferenza > 250ms, reconnect RTSP).

Limite predefinito: **250 MB / 7 giorni** (modificabile con `RESEARCH_TELEMETRY_MAX_MB` / `RESEARCH_TELEMETRY_RETENTION_DAYS`, disattivabile con `RESEARCH_TELEMETRY_ENABLED=false`).

## Come esportare un singolo `.zip` da passare su chiavetta USB
Dalla root del progetto sul PC fisso esegui:

```powershell
.\.venv\Scripts\python.exe tools\export_research_bundle.py
```

Lo script genera in `spatial_server/data/research_telemetry/exports/sh3d_research_bundle_<timestamp>.zip` un archivio unico contenente i dati JSONL, i ritagli di esempio e il file riepilogativo **`REPORT_SUMMARY.md`** pronto da condividere per l'analisi.
Se vuoi un pacchetto leggerissimo senza immagini JPEG aggiungi `--no-crops`.
