# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Household residents (personal home use) interacting with their residence across desktop browsers, phones, and home tablets for both daily home automation and security monitoring.

## Product Purpose

**Smart Home 3D** is an interactive web Digital Twin and Spatial CV Engine that turns the home's real 3D layout—indoors and outdoors—into a unified control and situational-awareness interface. It lets residents operate smart home devices directly in spatial context (lights, motorized gates, LG webOS Smart TV, dishwasher, garden irrigation, robot vacuum) while simultaneously monitoring live security cameras and reconstructing multi-camera 3D person/vehicle trajectories `(x, y, z, t)` with historical replay.

## Positioning

Unlike generic 2D smart home dashboards or hardcoded 3D floorplans, Smart Home 3D uses **Blender as Single Source of Truth (SSoT)**: 3D meshes, IoT entity bindings, security camera calibration matrices, and walkable ground colliders are authored via `.blend` Custom Properties and exported to `scene_manifest.json` + `house_optimized.glb`, paired with a live raycasted 3D spatial tracking and timeline replay engine and zero-config Offline Mock/Demo fallback.

## Operating Context

- **Primary Runtime:** Browser-based Vite web app (`index.html`, `src/main.js`) serving an interactive WebGL/CSS2D 3D scene (`Three.js`).
- **Smart Home Integration:** Bidirectional WebSocket sync via `home-assistant-js-websocket` (`VITE_HA_URL`, `VITE_HA_TOKEN`) plus a Vite dev/preview proxy (`/api/ha-camera/snapshot`) for Home Assistant camera snapshots across local/remote/Tailscale endpoints.
- **Video & Spatial CV Services:** Multi-provider camera streaming (`VideoStreamManager`) supporting `go2rtc` (MSE / WebRTC) with Home Assistant snapshot fallback, paired with `SpatialStreamClient` for live and historical detections and `CalibrationAssistantUI` for camera POV optical alignment.
- **3D Asset Pipeline:** Blender headless scripts (`npm run setup:props`, `npm run export:blend`, `npm run optimize:glb`, `npm run build:model`) update `public/models/house_optimized.glb` and `public/models/scene_manifest.json` without manual coordinate hardcoding in JavaScript.

## Capabilities and Constraints

- **Italian UI Language:** Keep all user-facing copy, navigation, device labels, and status messages in Italian (`<html lang="it">`).
- **Blender SSoT Pipeline:** Preserve `Smart_Home_3D.blend` -> `public/models/scene_manifest.json` + `public/models/house_optimized.glb` as the canonical source of 3D geometry, entity tags (`ha_entity`, `ha_action`, `ha_ui_type`, `ha_camera_entity`), and ground colliders (`collider_role = "ground"`).
- **Decentralized Device Modules:** Device controllers extend `BaseDeviceController` and register in `src/devices/DeviceRegistry.js` (`tv`, `dishwasher`, `irrigation`, `vacuum`, `security_camera`), complementing core light/gate bindings in `EntityBinder.js`.
- **Offline Mock/Demo Continuity:** When Home Assistant or `spatial_server` is unreachable or unconfigured, the app must continue operating cleanly via its reactive Mock/Demo mode and synthetic spatial scenario.
- **Cross-Device Household Access:** Used across desktop, mobile phone, and tablet screens; touch usability alongside mouse orbit/raycast controls should be preserved.
- **Open / Unspecified Details:** Exact relative priority between phone, tablet, and desktop viewports and any formal accessibility standard target are not separately specified.

## Brand Commitments

- **Product Name:** `Smart Home 3D` (subtitle: `Digital Twin & Spatial CV Engine`).
- **Procedural Media & Device Logos:** Keep the existing SVG brand assets in `public/logos/` (`lg-webos.svg`, `netflix.svg`, `prime-video.svg`, `disney-plus.svg`, `youtube.svg`, `spotify.svg`, `rai1.svg`, `raiplay.svg`, `mediaset.svg`, `google.svg`, `hdmi.svg`, `livetv.svg`) used by `TVScreenRenderer` and device controls.

## Evidence on Hand

- **3D Source & Exported Assets:** `Smart_Home_3D.blend`, `public/models/house_optimized.glb`, `public/models/scene_manifest.json`.
- **Documented HA Entity & Device Mapping:** `HA_DEVICES_MAPPING.md`, `README.md`, and `docs/SMART_DEVICES_ARCHITECTURE.md` (including `light.forno`, `light.bancone`, `light.portico`, `switch.switch_casa_interruttore_1`, `media_player.smart_tv_lg_oled_2`, `camera.carraio_scorrevole`, `vacuum.deebot`, plus dishwasher and 3-zone irrigation modules).
- **Camera & Service Configuration Guides:** `docs/GUIDA_CONFIGURAZIONE_REOLINK_E_SERVIZI.md`.
- **Absences:** No external customer testimonials, commercial pricing, licensing claims, or public benchmarks exist; future work must not fabricate them.

## Product Principles

1. **Spatial Context First:** Devices, status indicators, and camera detections belong directly on the 3D home model so residents orient by room and yard rather than abstract lists.
2. **Blender as Single Source of Truth:** Structural changes, camera poses, and entity tags flow from the `.blend` export and `scene_manifest.json` rather than hardcoded JS coordinates.
3. **Resilient Live-to-Mock Continuity:** Live Home Assistant, `go2rtc`, and Spatial CV streams elevate the app when connected, while Offline Mock/Demo and snapshot fallbacks ensure it never dead-ends.
4. **Encapsulated Device Ownership:** Each smart device category owns its Home Assistant commands, 3D animations/renderers, and contextual controls inside `src/devices/`.
5. **Natural Italian Household Clarity:** Every label, badge, and control uses clear Italian matching the real home's rooms, appliances, and outdoor areas.
