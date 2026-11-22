"""E2E tests for F18: Camera calibration server persistence, restart reload & cross-device sync."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.e2e.helpers.tier34_js_harness import run_vite_module_script

REPO_ROOT = Path(__file__).resolve().parents[2]


def _login(client: TestClient, token: str) -> None:
    resp = client.post(
        "/api/v1/auth/session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.tier1
def test_f18_t1_01_calibration_persists_across_server_restart_and_serves_all_users(
    tmp_path: Path,
    isolated_app_factory,
) -> None:
    """Admin saves calibration for Pinhole + 180° Panoramic cameras -> survives restart -> served to Resident & Admin."""
    shared_calib = tmp_path / "shared_camera_calibrations.json"

    app1 = isolated_app_factory(calibration_override_path=shared_calib)
    with TestClient(app1) as admin_client:
        _login(admin_client, "tok-admin")

        # Initial uncalibrated state reports is_calibrated=False with Cache-Control: no-store
        init_all = admin_client.get("/api/v1/calibrations")
        assert init_all.status_code == 200
        assert "no-store" in init_all.headers.get("cache-control", "").lower()
        init_map = init_all.json()["calibrations"]
        assert "Cam_Carraio" in init_map
        assert "Cam_Ingresso" in init_map
        assert init_map["Cam_Carraio"]["is_calibrated"] is False
        assert init_map["Cam_Ingresso"]["is_calibrated"] is False

        # Save calibration for Cam_Carraio (Pinhole)
        orig_carraio = np.array(init_map["Cam_Carraio"]["matrix_world_gl"], dtype=np.float64).reshape((4, 4))
        shifted_carraio = orig_carraio.copy()
        shifted_carraio[0, 3] += 0.35
        shifted_carraio[1, 3] -= 0.12
        shifted_carraio[2, 3] += 0.25

        carraio_ui = {
            "offsetX": 0.35,
            "offsetY": -0.12,
            "offsetZ": 0.25,
            "yawDeg": 0.0,
            "pitchDeg": 0.0,
            "rollDeg": 0.0,
            "fovV": 46.5,
            "fovH": 86.2,
            "k1": -0.14,
            "k2": 0.03,
            "flip180": False,
        }
        post_carraio = admin_client.post(
            "/api/v1/calibration/Cam_Carraio",
            json={
                "camera_id": "Cam_Carraio",
                "fov_v_deg": 46.5,
                "fov_h_deg": 86.2,
                "distortion_coeffs": [-0.14, 0.03, 0.0, 0.0, 0.0],
                "calibrated_matrix_world_gl": shifted_carraio.reshape(-1).tolist(),
                "ui_state": carraio_ui,
            },
        )
        assert post_carraio.status_code == 200
        assert post_carraio.json()["calibration"]["is_calibrated"] is True
        assert post_carraio.json()["calibration"]["ui_state"]["offsetX"] == pytest.approx(0.35)

        # Save calibration for Cam_Ingresso (180° Panoramic)
        orig_ing = np.array(init_map["Cam_Ingresso"]["matrix_world_gl"], dtype=np.float64).reshape((4, 4))
        shifted_ing = orig_ing.copy()
        shifted_ing[1, 3] -= 0.20
        ing_ui = {
            "offsetX": 0.0,
            "offsetY": -0.20,
            "offsetZ": 0.0,
            "yawDeg": 0.0,
            "pitchDeg": 0.0,
            "rollDeg": 0.0,
            "fovV": 58.0,
            "fovH": 180.0,
            "k1": 0.0,
            "k2": 0.0,
            "flip180": False,
        }
        post_ing = admin_client.post(
            "/api/v1/calibration/Cam_Ingresso",
            json={
                "camera_id": "Cam_Ingresso",
                "fov_v_deg": 58.0,
                "fov_h_deg": 180.0,
                "calibrated_matrix_world_gl": shifted_ing.reshape(-1).tolist(),
                "ui_state": ing_ui,
            },
        )
        assert post_ing.status_code == 200
        assert shared_calib.is_file()

    # Simulate full backend restart with a fresh FastAPI app reading the same file
    app2 = isolated_app_factory(calibration_override_path=shared_calib)
    with TestClient(app2) as resident_client:
        # Unauthenticated request rejected
        assert resident_client.get("/api/v1/calibrations").status_code == 401

        # Resident on another device can read all calibrations
        _login(resident_client, "tok-resident")
        reloaded_all = resident_client.get("/api/v1/calibrations")
        assert reloaded_all.status_code == 200
        assert "no-store" in reloaded_all.headers.get("cache-control", "").lower()
        reloaded = reloaded_all.json()["calibrations"]

        assert reloaded["Cam_Carraio"]["is_calibrated"] is True
        assert reloaded["Cam_Carraio"]["fov_v_deg"] == pytest.approx(46.5)
        assert reloaded["Cam_Carraio"]["fov_h_deg"] == pytest.approx(86.2)
        assert reloaded["Cam_Carraio"]["ui_state"]["offsetX"] == pytest.approx(0.35)
        assert reloaded["Cam_Carraio"]["matrix_world_gl"][3] == pytest.approx(shifted_carraio[0, 3], abs=1e-4)

        assert reloaded["Cam_Ingresso"]["is_calibrated"] is True
        assert reloaded["Cam_Ingresso"]["fov_v_deg"] == pytest.approx(58.0)
        assert reloaded["Cam_Ingresso"]["ui_state"]["offsetY"] == pytest.approx(-0.20)
        assert reloaded["Cam_Ingresso"]["matrix_world_gl"][7] == pytest.approx(shifted_ing[1, 3], abs=1e-4)

        # Single-camera GET also reports is_calibrated and no-store
        single = resident_client.get("/api/v1/calibration/Cam_Carraio")
        assert single.status_code == 200
        assert "no-store" in single.headers.get("cache-control", "").lower()
        assert single.json()["calibration"]["is_calibrated"] is True
        assert single.json()["calibration"]["ui_state"]["fovV"] == pytest.approx(46.5)


@pytest.mark.tier1
def test_f18_t1_02_legacy_calibration_file_without_ui_state_loads_as_calibrated(
    tmp_path: Path,
    isolated_app_factory,
) -> None:
    """Legacy camera_calibrations.json (without ui_state/is_calibrated) is recognized and served cleanly."""
    manifest = json.loads((REPO_ROOT / "public" / "models" / "scene_manifest.json").read_text(encoding="utf-8"))
    orig_cv = np.array(
        manifest["cameras"]["Cam_Portico"]["gltf_transform"]["extrinsic_cv_to_world"],
        dtype=np.float64,
    ).reshape((4, 4))
    shifted_cv = orig_cv.copy()
    shifted_cv[0, 3] += 0.42

    legacy_file = tmp_path / "legacy_calibs.json"
    legacy_file.write_text(
        json.dumps(
            {
                "Cam_Portico": {
                    "camera_id": "Cam_Portico",
                    "optical_model": "pinhole_radtan",
                    "fov_h_deg": 89.5,
                    "fov_v_deg": 45.5,
                    "distortion_coeffs": [-0.08, 0.02, 0.0, 0.0, 0.0],
                    "extrinsic_cv_to_world": shifted_cv.reshape(-1).tolist(),
                }
            }
        ),
        encoding="utf-8",
    )

    app = isolated_app_factory(calibration_override_path=legacy_file)
    with TestClient(app) as client:
        _login(client, "tok-resident")
        resp = client.get("/api/v1/calibrations")
        assert resp.status_code == 200
        portico = resp.json()["calibrations"]["Cam_Portico"]
        assert portico["is_calibrated"] is True
        assert portico["fov_v_deg"] == pytest.approx(45.5)
        assert portico["fov_h_deg"] == pytest.approx(89.5)
        assert portico["matrix_world_gl"][3] == pytest.approx(shifted_cv[0, 3], abs=1e-4)
        assert "ui_state" not in portico


@pytest.mark.tier1
def test_f18_t1_03_delete_calibration_rbac_reset_and_ws_broadcast(
    tmp_path: Path,
    isolated_app_factory,
) -> None:
    """DELETE /api/v1/calibration/{id} enforces Admin RBAC, resets SSoT across restarts & broadcasts WS update."""
    shared_calib = tmp_path / "reset_calibs.json"
    app = isolated_app_factory(calibration_override_path=shared_calib)

    with TestClient(app) as client:
        # Unauthenticated -> 401
        assert client.delete("/api/v1/calibration/Cam_Carraio").status_code == 401

        # Resident -> 403
        _login(client, "tok-resident")
        assert client.delete("/api/v1/calibration/Cam_Carraio").status_code == 403

        # Admin -> save then delete while WS listener receives both calibration_updated broadcasts
        _login(client, "tok-admin")
        base_meta = client.get("/api/v1/calibration/Cam_Carraio").json()["calibration"]
        base_fov_v = base_meta["fov_v_deg"]
        base_tx = base_meta["matrix_world_gl"][3]

        shifted = np.array(base_meta["matrix_world_gl"], dtype=np.float64).reshape((4, 4))
        shifted[0, 3] += 0.55

        with client.websocket_connect("/ws/spatial") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "server_status"

            def _recv_calibration_event() -> dict:
                for _ in range(30):
                    msg = ws.receive_json()
                    if msg.get("type") == "calibration_updated":
                        return msg
                raise AssertionError("Did not receive calibration_updated WS event within 30 messages")

            post_r = client.post(
                "/api/v1/calibration/Cam_Carraio",
                json={
                    "camera_id": "Cam_Carraio",
                    "fov_v_deg": 51.0,
                    "fov_h_deg": 92.0,
                    "calibrated_matrix_world_gl": shifted.reshape(-1).tolist(),
                    "ui_state": {"offsetX": 0.55, "fovV": 51.0, "fovH": 92.0},
                },
            )
            assert post_r.status_code == 200
            ws_save = _recv_calibration_event()
            assert ws_save["camera_id"] == "Cam_Carraio"
            assert ws_save["calibration"]["is_calibrated"] is True
            assert ws_save["calibration"]["fov_v_deg"] == pytest.approx(51.0)

            del_r = client.delete("/api/v1/calibration/Cam_Carraio")
            assert del_r.status_code == 200
            assert del_r.json()["calibration"]["is_calibrated"] is False
            assert del_r.json()["calibration"]["fov_v_deg"] == pytest.approx(base_fov_v)
            assert del_r.json()["calibration"]["matrix_world_gl"][3] == pytest.approx(base_tx, abs=1e-4)

            ws_reset = _recv_calibration_event()
            assert ws_reset["camera_id"] == "Cam_Carraio"
            assert ws_reset["calibration"]["is_calibrated"] is False

    # Verify reset persists after server restart
    app_after = isolated_app_factory(calibration_override_path=shared_calib)
    with TestClient(app_after) as client2:
        _login(client2, "tok-resident")
        cal = client2.get("/api/v1/calibration/Cam_Carraio").json()["calibration"]
        assert cal["is_calibrated"] is False
        assert cal["fov_v_deg"] == pytest.approx(base_fov_v)
        assert cal["matrix_world_gl"][3] == pytest.approx(base_tx, abs=1e-4)


@pytest.mark.tier1
def test_f18_t1_04_frontend_cross_device_sync_reopen_legacy_decompose_and_reset() -> None:
    """Frontend Device A saves -> Device B (empty localStorage) loads exact pose & sliders -> Reset SSoT syncs."""
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        const fs = await import('fs');
        const { makeElement } = installBrowserShims({ href: 'https://pc-fisso.tail123.ts.net/' });
        const THREE = await server.ssrLoadModule('three');
        const { CameraProjector, CALIBRATION_STORAGE_PREFIX } = await server.ssrLoadModule('/src/spatial/CameraProjector.js');
        const { CalibrationAssistantUI } = await server.ssrLoadModule('/src/spatial/calibration/CalibrationAssistantUI.js');
        const { SpatialStreamClient } = await server.ssrLoadModule('/src/spatial/network/SpatialStreamClient.js');

        const manifest = JSON.parse(fs.readFileSync('public/models/scene_manifest.json', 'utf-8'));

        function makeRig(localStorageBacking) {
          globalThis.localStorage = {
            getItem: (k) => (Object.prototype.hasOwnProperty.call(localStorageBacking, k) ? localStorageBacking[k] : null),
            setItem: (k, v) => { localStorageBacking[k] = String(v); },
            removeItem: (k) => { delete localStorageBacking[k]; },
          };
          const scene = new THREE.Scene();
          const cameras = new Map();
          for (const camId of ['Cam_Carraio', 'Cam_Portico', 'Cam_Ingresso', 'Cam_Stradina']) {
            const meta = manifest.cameras[camId];
            const cam = new THREE.PerspectiveCamera(meta.fov_v_deg, meta.aspect_ratio, 0.1, 250);
            cam.name = camId;
            const m = new THREE.Matrix4().set(...meta.gltf_transform.matrix_world_gl);
            m.decompose(cam.position, cam.quaternion, cam.scale);
            scene.add(cam);
            cam.updateMatrixWorld(true);
            cameras.set(camId, cam);
          }
          const assetLoader = { manifest, cameras, groundColliders: [] };
          const projector = new CameraProjector(scene, assetLoader);
          projector.setupCameraFrustums();
          return { scene, cameras, assetLoader, projector };
        }

        // Simulated backend store shared across devices
        const serverOverrides = {};
        const fakeSpatialClient = {
          async fetchAllCameraCalibrations() {
            const out = {};
            for (const camId of ['Cam_Carraio', 'Cam_Portico', 'Cam_Ingresso', 'Cam_Stradina']) {
              out[camId] = serverOverrides[camId]
                ? { ...serverOverrides[camId], is_calibrated: true }
                : { camera_id: camId, is_calibrated: false };
            }
            return { status: 'ok', calibrations: out };
          },
          async fetchCameraCalibration(camId) {
            return {
              status: 'ok',
              calibration: serverOverrides[camId]
                ? { ...serverOverrides[camId], is_calibrated: true }
                : { camera_id: camId, is_calibrated: false },
            };
          },
          async updateCameraCalibration(camId, payload) {
            serverOverrides[camId] = {
              camera_id: camId,
              fov_v_deg: payload.fov_v_deg,
              fov_h_deg: payload.fov_h_deg,
              distortion_coeffs: payload.distortion_coeffs,
              matrix_world_gl: payload.calibrated_matrix_world_gl,
              ui_state: payload.ui_state,
              updated_at: 1763850000.5,
              is_calibrated: true,
            };
            return { status: 'ok', calibration: serverOverrides[camId] };
          },
          async resetCameraCalibration(camId) {
            delete serverOverrides[camId];
            return { status: 'ok', camera_id: camId, calibration: { camera_id: camId, is_calibrated: false } };
          },
        };

        // 1. Device A calibrates Cam_Carraio (with flip180 + offsets + rotation + FOV + distortion) and saves
        const storageA = {};
        const rigA = makeRig(storageA);
        const uiLayerA = makeElement('div', 'ui-layer');
        uiLayerA.classList.add('ui-layer');
        document.body.appendChild(uiLayerA);
        const canvasA = makeElement('canvas', 'c-a');

        const calibA = new CalibrationAssistantUI({
          sceneManager: { renderer: { domElement: canvasA }, camera: { updateMatrixWorld() {} }, scene: rigA.scene, addUpdateCallback() {}, removeUpdateCallback() {} },
          cameraController: { activePovCameraName: null, setPovExitLocked() {}, exitCameraPOV() {}, setInstantCameraPose() {} },
          cameraProjector: rigA.projector,
          videoStreamManager: { acquireVideoTexture: async () => ({ texture: {}, provider: { mode: 'webrtc' } }), releaseVideoTexture() {} },
          spatialStreamClient: fakeSpatialClient,
          assetLoader: rigA.assetLoader,
          haClient: { isAdmin: true },
        });
        await calibA.open('Cam_Carraio');
        calibA.state = {
          offsetX: 0.42,
          offsetY: -0.18,
          offsetZ: 0.31,
          yawDeg: 14.5,
          pitchDeg: -6.5,
          rollDeg: 2.5,
          fovV: 49.0,
          fovH: 88.5,
          k1: -0.11,
          k2: 0.02,
          flip180: true,
        };
        const savedOk = await calibA.saveAndSubmitToBackend();
        const savedPoseA = rigA.projector.getCalibratedCameraPose('Cam_Carraio');
        calibA.close();

        // Also seed a legacy server override for Cam_Portico WITHOUT ui_state (only matrix_world_gl)
        const porticoPose = rigA.projector.applyCameraCalibration('Cam_Portico', {
          offsetX: -0.25,
          offsetY: 0.10,
          offsetZ: 0.40,
          yawDeg: -12.0,
          pitchDeg: 5.5,
          rollDeg: -1.5,
          fovV: 47.0,
          fovH: 91.0,
          k1: -0.05,
          k2: 0.01,
          flip180: false,
        });
        serverOverrides.Cam_Portico = {
          camera_id: 'Cam_Portico',
          fov_v_deg: 47.0,
          fov_h_deg: 91.0,
          distortion_coeffs: [-0.05, 0.01, 0, 0, 0],
          matrix_world_gl: porticoPose.matrixWorldElements,
          is_calibrated: true,
        };

        // 2. Device B starts with COMPLETELY EMPTY localStorage (brand new phone / cleared browser)
        const storageB = {};
        const rigB = makeRig(storageB);
        const beforeSyncPos = rigB.cameras.get('Cam_Carraio').position.toArray();
        const backendRes = await fakeSpatialClient.fetchAllCameraCalibrations();
        const syncRes = rigB.projector.applyBackendCalibrations(backendRes.calibrations, { persistLocal: true });

        const afterSyncCam = rigB.cameras.get('Cam_Carraio');
        const afterSyncPos = afterSyncCam.position.toArray();
        const afterSyncFov = afterSyncCam.fov;
        const afterSyncState = rigB.projector.getCalibrationState('Cam_Carraio');
        const afterSyncPorticoState = rigB.projector.getCalibrationState('Cam_Portico');
        const afterSyncPorticoCam = rigB.cameras.get('Cam_Portico');
        const afterSyncPorticoPos = afterSyncPorticoCam.position.toArray();

        // Opening CalibrationAssistantUI on Device B must load the synced sliders (not Blender defaults!)
        const calibB = new CalibrationAssistantUI({
          sceneManager: { renderer: { domElement: canvasA }, camera: { updateMatrixWorld() {} }, scene: rigB.scene, addUpdateCallback() {}, removeUpdateCallback() {} },
          cameraController: { activePovCameraName: null, setPovExitLocked() {}, exitCameraPOV() {}, setInstantCameraPose() {} },
          cameraProjector: rigB.projector,
          videoStreamManager: { acquireVideoTexture: async () => ({ texture: {}, provider: { mode: 'webrtc' } }), releaseVideoTexture() {} },
          spatialStreamClient: fakeSpatialClient,
          assetLoader: rigB.assetLoader,
          haClient: { isAdmin: true },
        });
        await calibB.open('Cam_Carraio');
        const deviceBOpenedState = { ...calibB.state };
        calibB.close();

        // 3. Offline draft protection: Device B has an unsynced draft on Cam_Stradina; backend says is_calibrated=false -> draft preserved!
        rigB.projector.saveLocalCalibration('Cam_Stradina', { offsetX: 0.77, yawDeg: 9.0, fovV: 55.0, fovH: 180.0 }, { syncedToBackend: false });
        rigB.projector.applyCameraCalibration('Cam_Stradina', { offsetX: 0.77, yawDeg: 9.0, fovV: 55.0, fovH: 180.0 });
        const stradinaSync = rigB.projector.applyBackendCalibration('Cam_Stradina', { camera_id: 'Cam_Stradina', is_calibrated: false }, { persistLocal: true });
        const stradinaStillHasDraft = rigB.projector.getCalibrationState('Cam_Stradina')?.offsetX === 0.77;

        // 4. Device A resets Cam_Carraio (Reset SSoT) -> Device B receives is_calibrated=false and resets back to Blender SSoT
        await calibA.open('Cam_Carraio');
        const resetOk = await calibA.resetToManifestDefault();
        calibA.close();
        const afterResetAll = await fakeSpatialClient.fetchAllCameraCalibrations();
        const resetSyncB = rigB.projector.applyBackendCalibrations(afterResetAll.calibrations, { persistLocal: true });
        const afterResetPosB = rigB.cameras.get('Cam_Carraio').position.toArray();
        const localCacheAfterResetB = storageB[`${CALIBRATION_STORAGE_PREFIX}Cam_Carraio`] || null;

        // 5. SpatialStreamClient dispatches calibration_updated WS events
        let wsNotified = null;
        const ssc = new SpatialStreamClient('http://localhost:8765');
        ssc.onCalibrationUpdate((m) => { wsNotified = m; });
        const origWs = globalThis.WebSocket;
        let fakeWsInstance = null;
        globalThis.WebSocket = class {
          constructor() { fakeWsInstance = this; this.readyState = 1; }
          close() {}
        };
        ssc.connectWebSocket();
        fakeWsInstance.onmessage({ data: JSON.stringify({ type: 'calibration_updated', camera_id: 'Cam_Portico', calibration: { is_calibrated: true } }) });
        globalThis.WebSocket = origWs;

        return {
          savedOk,
          savedPosA: savedPoseA.position.toArray(),
          beforeSyncPos,
          afterSyncPos,
          afterSyncFov,
          appliedCameras: syncRes.appliedCameras,
          afterSyncState,
          deviceBOpenedState,
          afterSyncPorticoState,
          afterSyncPorticoPos,
          expectedPorticoPos: porticoPose.position.toArray(),
          stradinaReset: stradinaSync.reset,
          stradinaStillHasDraft,
          resetOk,
          resetCamerasB: resetSyncB.resetCameras,
          afterResetPosB,
          localCacheAfterResetB,
          wsNotified,
        };
        """,
    )

    assert js_res["savedOk"] is True
    assert "Cam_Carraio" in js_res["appliedCameras"]
    assert "Cam_Portico" in js_res["appliedCameras"]

    # Device B matches Device A's saved position, FOV and exact slider state
    for i in range(3):
        assert js_res["afterSyncPos"][i] == pytest.approx(js_res["savedPosA"][i], abs=1e-3)
        assert js_res["afterSyncPos"][i] != pytest.approx(js_res["beforeSyncPos"][i], abs=1e-2)
    assert js_res["afterSyncFov"] == pytest.approx(49.0)
    assert js_res["deviceBOpenedState"]["flip180"] is True
    assert js_res["deviceBOpenedState"]["yawDeg"] == pytest.approx(14.5)
    assert js_res["deviceBOpenedState"]["offsetX"] == pytest.approx(0.42)
    assert js_res["deviceBOpenedState"]["k1"] == pytest.approx(-0.11)

    # Legacy matrix-only override (Cam_Portico) decomposes cleanly to matching position/angles
    for i in range(3):
        assert js_res["afterSyncPorticoPos"][i] == pytest.approx(js_res["expectedPorticoPos"][i], abs=1e-2)
    assert js_res["afterSyncPorticoState"]["offsetX"] == pytest.approx(-0.25, abs=0.01)
    assert js_res["afterSyncPorticoState"]["yawDeg"] == pytest.approx(-12.0, abs=0.1)
    assert js_res["afterSyncPorticoState"]["fovV"] == pytest.approx(47.0)

    # Offline draft is not clobbered by uncalibrated backend
    assert js_res["stradinaReset"] is False
    assert js_res["stradinaStillHasDraft"] is True

    # Reset SSoT propagates to Device B and clears its local cache
    assert js_res["resetOk"] is True
    assert "Cam_Carraio" in js_res["resetCamerasB"]
    for i in range(3):
        assert js_res["afterResetPosB"][i] == pytest.approx(js_res["beforeSyncPos"][i], abs=1e-3)
    assert js_res["localCacheAfterResetB"] is None

    # WS calibration_updated event delivered
    assert js_res["wsNotified"] is not None
    assert js_res["wsNotified"]["camera_id"] == "Cam_Portico"
