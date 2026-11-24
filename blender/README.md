# `blender/` — Script SSoT e Pipeline di Export 3D

Questa directory contiene gli script Python Blender (`bpy`) ufficiali che trasformano il file sorgente [`Smart_Home_3D.blend`](../Smart_Home_3D.blend) negli artefatti runtime consumati sia dal frontend Three.js sia dal backend Python `spatial_server`.

> Per la guida architetturale completa su Custom Properties, trasformazioni di coordinate, schema JSON del manifest e script builder nella root del repository, consulta [`docs/architecture/blender-ssot-pipeline.md`](../docs/architecture/blender-ssot-pipeline.md).

---

## Struttura di `blender/scripts/`

| Script | Responsabilità | Output / Effetto |
|---|---|---|
| [`blender/scripts/setup_ha_properties.py`](./scripts/setup_ha_properties.py) | Applica in modo idempotente le Custom Properties SSoT su `Smart_Home_3D.blend`: assegna `collider_role="ground"` alle 20 mesh `GROUND_COLLIDERS`, popola `ENTITY_MAPPINGS`, allinea le aperture parete sud sala da pranzo/porta sud salotto e configura le 4 telecamere reali (`Cam_Carraio`, `Cam_Portico`, `Cam_Ingresso`, `Cam_Stradina`). | Modifica e salva `Smart_Home_3D.blend`. |
| [`blender/scripts/add_user_devices.py`](./scripts/add_user_devices.py) | Crea o rigenera in `HA_SSoT_Devices` le mesh fisiche e le Custom Properties di applique, bollard giardino, luci muro, centrale termica in lavanderia (puffer/caldaia/sensori), interruttori cancelli/garage e gli 11 gettini irrigatori (`Sprinkler_Area1..3`). | Modifica e salva `Smart_Home_3D.blend`. |
| [`blender/scripts/export_glb.py`](./scripts/export_glb.py) | Calibra i materiali Principled BSDF per compatibilità glTF (`MATERIAL_COLOR_OVERRIDES`, rimozione nodi procedurali preservando `TEX_IMAGE`), estrae `ha_entities`, `cameras` e `ground_colliders` nel manifest ed esporta il `.glb` (`export_extras=True`, `export_cameras=True`, `export_lights=False`). | Scrive `public/models/house_raw.glb` e `public/models/scene_manifest.json`. |

---

## Comandi `npm` della Pipeline Modello

Definiti in [`package.json`](../package.json) (richiedono Blender 5.2 installato in `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`):

```powershell
# 1. (Opzionale) Applica/aggiorna Custom Properties SSoT, ground colliders e le 4 camere reali su Smart_Home_3D.blend
npm run setup:props

# 2. Esporta house_raw.glb e rigenera public/models/scene_manifest.json
npm run export:blend

# 3. Ottimizza house_raw.glb -> house_optimized.glb tramite @gltf-transform (dedup, prune, weld)
npm run optimize:glb

# Pipeline completa di esportazione + ottimizzazione (da eseguire dopo ogni modifica al .blend)
npm run build:model
```

### Esecuzione Diretta da CLI Blender
```powershell
# Esecuzione manuale di add_user_devices.py in background
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b Smart_Home_3D.blend -P blender/scripts/add_user_devices.py

# Export con path personalizzati
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b Smart_Home_3D.blend -P blender/scripts/export_glb.py -- public/models/house_raw.glb public/models/scene_manifest.json
```

---

## Note Critiche di Manutenzione
1. **Esporta sempre con `build:model`**: se modifichi una telecamera o un'entità in Blender, è indispensabile rigenerare sia `scene_manifest.json` sia `house_optimized.glb` affinché Three.js (`AssetLoader`, `CameraCatalog`, `CameraProjector`) e `spatial_server` (`TrimeshGroundRaycaster`, modelli ottici) restino allineati.
2. **Non esportare luci fisiche Blender**: `export_glb.py` mantiene `export_lights=False` perché la luce solare Blender (`2868 lux`) sovrasaturerebbe il lighting dinamico giorno/notte di Three.js.
3. **Preservazione `userData`**: `tools/optimize_glb.mjs` usa `prune({ keepAttributes: true, keepLeaves: true })` per non scartare attributi o nodi camera/device vuoti.

---

## Riferimenti Correlati
- Architettura pipeline SSoT e schema `scene_manifest.json`: [`docs/architecture/blender-ssot-pipeline.md`](../docs/architecture/blender-ssot-pipeline.md)
- Ottimizzatore GLB & script ausiliari Blender: [`tools/README.md`](../tools/README.md)
- Runbook aggiunta nuova telecamera: [`docs/runbooks/add-camera.md`](../docs/runbooks/add-camera.md)
