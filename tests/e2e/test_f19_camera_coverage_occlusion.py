"""Tests for 3-state camera coverage mode, wall raycast occlusion, and Cam_Portico anchor guard."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from spatial_server.domain.models import PnPCorrespondence
from spatial_server.optics.calibration_solver import CameraCalibrationSolver, create_optical_model_from_manifest
from tests.e2e.helpers.artifacts import run_js_scenario
from tests.e2e.helpers.tier34_js_harness import run_vite_module_script

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.tier1
def test_f19_camera_coverage_3state_occlusion_and_portico_anchor() -> None:
    """Verifies 3-state coverage (off/3d/2d), wall occlusion raycast, TopBar UI cycle, and Cam_Portico anchor guard."""
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        const fs = await import('fs');
        const { makeElement } = installBrowserShims({ href: 'https://localhost:5173/' });
        const THREE = await server.ssrLoadModule('three');
        const { CameraProjector, computeClippedFrustumData } = await server.ssrLoadModule('/src/spatial/CameraProjector.js');
        const { TopBar } = await server.ssrLoadModule('/src/ui/TopBar.js');

        const manifest = JSON.parse(fs.readFileSync('public/models/scene_manifest.json', 'utf-8'));

        // 1. Wall occlusion test: camera at (5, 2.2, 0) looking +Z toward ground (5, 0, 8), wall at z=[4.0, 4.3]
        const camPos = new THREE.Vector3(5, 2.2, 0);
        const lookMat = new THREE.Matrix4().lookAt(camPos, new THREE.Vector3(5, 0, 8), new THREE.Vector3(0, 1, 0));
        const camQuat = new THREE.Quaternion().setFromRotationMatrix(lookMat);
        const wallBoxes = [
          { name: 'Wall_Test', minX: 0, minY: 0, minZ: 4.0, maxX: 10, maxY: 3.0, maxZ: 4.3 },
        ];
        const occluded = computeClippedFrustumData(camPos, camQuat, 44, 87, 16.0, 0.015, wallBoxes);
        const localToWorld = new THREE.Matrix4().compose(camPos, camQuat, new THREE.Vector3(1, 1, 1));

        let maxConeWorldZ = -Infinity;
        const tmp = new THREE.Vector3();
        for (let i = 0; i < occluded.conePositions.length; i += 3) {
          tmp.set(occluded.conePositions[i], occluded.conePositions[i + 1], occluded.conePositions[i + 2]).applyMatrix4(localToWorld);
          if (tmp.z > maxConeWorldZ) maxConeWorldZ = tmp.z;
        }
        let maxGroundWorldZ = -Infinity;
        for (let i = 0; i < occluded.groundPositions.length; i += 3) {
          tmp.set(occluded.groundPositions[i], occluded.groundPositions[i + 1], occluded.groundPositions[i + 2]).applyMatrix4(localToWorld);
          if (tmp.z > maxGroundWorldZ) maxGroundWorldZ = tmp.z;
        }

        // 2. Lavanderia back-zone occlusion test for Cam_Portico
        const porticoMeta = manifest.cameras.Cam_Portico;
        const pMat = new THREE.Matrix4().set(...porticoMeta.gltf_transform.matrix_world_gl);
        const pPos = new THREE.Vector3();
        const pQuat = new THREE.Quaternion();
        pMat.decompose(pPos, pQuat, new THREE.Vector3());
        const lavBoxes = [
          { name: 'Wall_Lav_East', minX: 4.45, minY: 0, minZ: 12.63, maxX: 4.65, maxY: 2.7, maxZ: 15.43 },
          { name: 'Wall_Lav_North_01', minX: 0.3, minY: 0, minZ: 12.43, maxX: 2.7, maxY: 2.7, maxZ: 12.63 },
          { name: 'Wall_Lav_North_02', minX: 3.62, minY: 0, minZ: 12.43, maxX: 4.65, maxY: 2.7, maxZ: 12.63 },
          { name: 'Wall_Lav_South_01', minX: 0.3, minY: 0, minZ: 15.23, maxX: 0.82, maxY: 2.7, maxZ: 15.43 },
          { name: 'Wall_Lav_South_02', minX: 1.43, minY: 0, minZ: 15.23, maxX: 3.08, maxY: 2.7, maxZ: 15.43 },
          { name: 'Wall_Lav_South_03', minX: 3.69, minY: 0, minZ: 15.23, maxX: 4.45, maxY: 2.7, maxZ: 15.43 },
          { name: 'Wall_Lav_West', minX: 0.0, minY: 0, minZ: 11.33, maxX: 0.3, maxY: 2.7, maxZ: 15.43 },
        ];
        const lavUnoccluded = computeClippedFrustumData(pPos, pQuat, porticoMeta.fov_v_deg, porticoMeta.fov_h_deg, 16.0, 0.015);
        const lavOccluded = computeClippedFrustumData(pPos, pQuat, porticoMeta.fov_v_deg, porticoMeta.fov_h_deg, 16.0, 0.015, lavBoxes);
        const pLocalToWorld = new THREE.Matrix4().compose(pPos, pQuat, new THREE.Vector3(1, 1, 1));
        const pointInTriXZ = (px, pz, ax, az, bx, bz, cx, cz) => {
          const v0x = cx - ax, v0z = cz - az;
          const v1x = bx - ax, v1z = bz - az;
          const v2x = px - ax, v2z = pz - az;
          const dot00 = v0x * v0x + v0z * v0z;
          const dot01 = v0x * v1x + v0z * v1z;
          const dot02 = v0x * v2x + v0z * v2z;
          const dot11 = v1x * v1x + v1z * v1z;
          const dot12 = v1x * v2x + v1z * v2z;
          const denom = dot00 * dot11 - dot01 * dot01;
          if (Math.abs(denom) < 1e-12) return false;
          const inv = 1 / denom;
          const u = (dot11 * dot02 - dot01 * dot12) * inv;
          const v = (dot00 * dot12 - dot01 * dot02) * inv;
          return u >= -1e-5 && v >= -1e-5 && u + v <= 1 + 1e-5;
        };
        const isGroundCovered = (groundBuf, tx, tz) => {
          const a = new THREE.Vector3();
          const b = new THREE.Vector3();
          const c = new THREE.Vector3();
          for (let i = 0; i < groundBuf.length; i += 9) {
            a.set(groundBuf[i], groundBuf[i + 1], groundBuf[i + 2]).applyMatrix4(pLocalToWorld);
            b.set(groundBuf[i + 3], groundBuf[i + 4], groundBuf[i + 5]).applyMatrix4(pLocalToWorld);
            c.set(groundBuf[i + 6], groundBuf[i + 7], groundBuf[i + 8]).applyMatrix4(pLocalToWorld);
            if (pointInTriXZ(tx, tz, a.x, a.z, b.x, b.z, c.x, c.z)) return true;
          }
          return false;
        };
        const behindLavUnoccluded = isGroundCovered(lavUnoccluded.groundPositions, 1.5, 16.8);
        const behindLavOccluded = isGroundCovered(lavOccluded.groundPositions, 1.5, 16.8);

        // 3. CameraProjector 3-state cycle & Cam_Portico anchor guard
        const storage = {};
        globalThis.localStorage = {
          getItem: (k) => (Object.prototype.hasOwnProperty.call(storage, k) ? storage[k] : null),
          setItem: (k, v) => { storage[k] = String(v); },
          removeItem: (k) => { delete storage[k]; },
        };
        const cameras = new Map();
        for (const [camName, camMeta] of Object.entries(manifest.cameras)) {
          const cam = new THREE.PerspectiveCamera(camMeta.fov_v_deg || 42, camMeta.aspect_ratio || 16 / 9, 0.1, 250);
          cam.name = camName;
          const m = new THREE.Matrix4().set(...camMeta.gltf_transform.matrix_world_gl);
          m.decompose(cam.position, cam.quaternion, new THREE.Vector3());
          cam.updateMatrixWorld(true);
          cameras.set(camName, cam);
        }
        const projector = new CameraProjector(new THREE.Scene(), { cameras, manifest, groundColliders: [] });
        projector.setOcclusionColliders(lavBoxes);
        projector.setupCameraFrustums();

        const porticoVol = projector.frustumVolumes.get('Cam_Portico');
        const snapVol = () => ({
          mode: projector.getFrustumMode(),
          visibleFlag: projector.frustumsVisible,
          cone: porticoVol.coneMesh.visible,
          wire: porticoVol.wireLines.visible,
          ground: porticoVol.groundMesh.visible,
          groundLine: porticoVol.groundLines.visible,
        });
        const stateInitial = snapVol();
        projector.cycleFrustumMode();
        const state3d = snapVol();
        projector.cycleFrustumMode();
        const state2d = snapVol();
        projector.cycleFrustumMode();
        const stateOff = snapVol();

        // Implausible drifted override (>2.2m) must be rejected
        const driftedMat = [...porticoMeta.gltf_transform.matrix_world_gl];
        driftedMat[11] += 8.0; // +8m in Z
        const driftedRes = projector.applyBackendCalibration('Cam_Portico', {
          camera_id: 'Cam_Portico',
          is_calibrated: true,
          fov_v_deg: porticoMeta.fov_v_deg,
          fov_h_deg: porticoMeta.fov_h_deg,
          matrix_world_gl: driftedMat,
        });
        const posAfterDrifted = projector.getCalibratedCameraPose('Cam_Portico').position.toArray();

        // Plausible small offset (0.15m) must be accepted
        const plausibleRes = projector.applyBackendCalibration('Cam_Portico', {
          camera_id: 'Cam_Portico',
          is_calibrated: true,
          fov_v_deg: porticoMeta.fov_v_deg,
          fov_h_deg: porticoMeta.fov_h_deg,
          ui_state: { offsetX: 0.15, offsetY: 0, offsetZ: 0 },
        });
        const posAfterPlausible = projector.getCalibratedCameraPose('Cam_Portico').position.toArray();

        // 4. TopBar 3-state button cycling
        const topBarEl = makeElement('div', 'top-bar');
        const topBar = new TopBar(topBarEl, {
          sceneManager: { isNightMode: false, setNightMode() {} },
          cameraController: { flyToPreset() {}, flyToCameraPOV() {} },
          cameraProjector: projector,
          interactionManager: { toggleBadges: () => false },
          haClient: {
            isAdmin: false,
            isMockMode: true,
            onStatusChange: () => () => {},
            onAuthChange: () => () => {},
          },
        });
        const btn = topBar.frustumsBtn;
        const readBtn = () => ({
          mode: btn.dataset.coverageMode,
          active: btn.classList.contains('active'),
          active2d: btn.classList.contains('active-2d'),
          ariaLabel: btn.getAttribute('aria-label'),
        });
        const uiInit = readBtn();
        btn.click();
        const uiClick1 = readBtn();
        btn.click();
        const uiClick2 = readBtn();
        btn.click();
        const uiClick3 = readBtn();

        return {
          maxConeWorldZ,
          maxGroundWorldZ,
          behindLavUnoccluded,
          behindLavOccluded,
          stateInitial,
          state3d,
          state2d,
          stateOff,
          driftedRes: { applied: driftedRes.applied, reset: driftedRes.reset },
          posAfterDrifted,
          expectedBasePos: porticoMeta.gltf_transform.position,
          plausibleRes: { applied: plausibleRes.applied, reset: plausibleRes.reset },
          posAfterPlausible,
          uiInit,
          uiClick1,
          uiClick2,
          uiClick3,
        };
        """,
    )

    assert js_res["maxConeWorldZ"] <= 4.005
    assert js_res["maxGroundWorldZ"] <= 4.005
    assert js_res["behindLavUnoccluded"] is True
    assert js_res["behindLavOccluded"] is False

    assert js_res["stateInitial"] == {
        "mode": "off", "visibleFlag": False, "cone": False, "wire": False, "ground": False, "groundLine": False
    }
    assert js_res["state3d"] == {
        "mode": "3d", "visibleFlag": True, "cone": True, "wire": True, "ground": True, "groundLine": True
    }
    assert js_res["state2d"] == {
        "mode": "2d", "visibleFlag": True, "cone": False, "wire": False, "ground": True, "groundLine": True
    }
    assert js_res["stateOff"] == {
        "mode": "off", "visibleFlag": False, "cone": False, "wire": False, "ground": False, "groundLine": False
    }

    assert js_res["driftedRes"] == {"applied": False, "reset": True}
    assert js_res["posAfterDrifted"] == pytest.approx(js_res["expectedBasePos"], abs=1e-4)
    assert js_res["plausibleRes"] == {"applied": True, "reset": False}
    assert js_res["posAfterPlausible"][0] == pytest.approx(js_res["expectedBasePos"][0] + 0.15, abs=1e-4)

    assert js_res["uiInit"] == {"mode": "off", "active": False, "active2d": False, "ariaLabel": "Copertura telecamere disattivata"}
    assert js_res["uiClick1"] == {"mode": "3d", "active": True, "active2d": False, "ariaLabel": "Copertura telecamere 3D"}
    assert js_res["uiClick2"] == {"mode": "2d", "active": True, "active2d": True, "ariaLabel": "Copertura telecamere 2D al suolo"}
    assert js_res["uiClick3"] == {"mode": "off", "active": False, "active2d": False, "ariaLabel": "Copertura telecamere disattivata"}


@pytest.mark.tier1
def test_f19_topbar_3state_button_label_and_classes() -> None:
    """Verifies TopBar #btn-toggle-frustums label text, classes, and 3-state cycle in DOM harness."""
    code = """
      const { TopBar } = await loadModule('/src/ui/TopBar.js');
      const topBarEl = ctx.document.getElementById('top-bar');
      let mode = 'off';
      const modes = ['off', '3d', '2d'];
      const topBar = new TopBar(topBarEl, {
        sceneManager: { isNightMode: false, setNightMode() {} },
        cameraController: { flyToPreset() {}, flyToCameraPOV() {} },
        cameraProjector: {
          getFrustumMode: () => mode,
          cycleFrustumMode: () => {
            mode = modes[(modes.indexOf(mode) + 1) % modes.length];
            return mode;
          },
          toggleFrustums: () => false,
        },
        interactionManager: { toggleBadges: () => false },
        haClient: {
          isAdmin: false,
          isMockMode: true,
          onStatusChange: () => () => {},
          onAuthChange: () => () => {},
        },
      });
      const btn = topBar.frustumsBtn;
      const snap = () => ({
        mode: btn.getAttribute('data-coverage-mode') || btn.dataset?.coverageMode || '',
        text: btn.querySelector('#frustums-text')?.textContent?.trim(),
        active: btn.classList.contains('active'),
        active2d: btn.classList.contains('active-2d'),
      });
      const s0 = snap();
      btn.click();
      const s1 = snap();
      btn.click();
      const s2 = snap();
      btn.click();
      const s3 = snap();
      return { s0, s1, s2, s3 };
    """
    res = run_js_scenario({"code": code})
    assert res["ok"] is True, res
    d = res["data"]
    assert d["s0"] == {"mode": "off", "text": "Copertura Camere", "active": False, "active2d": False}
    assert d["s1"] == {"mode": "3d", "text": "Copertura 3D", "active": True, "active2d": False}
    assert d["s2"] == {"mode": "2d", "text": "Copertura 2D", "active": True, "active2d": True}
    assert d["s3"] == {"mode": "off", "text": "Copertura Camere", "active": False, "active2d": False}


@pytest.mark.tier1
def test_f19_backend_solve_pnp_rejects_large_position_jump(tmp_path: Path) -> None:
    """Backend SolvePnPRansac rejects degenerate poses jumping > 3.0m from the physical camera mount."""
    import json

    manifest = json.loads((REPO_ROOT / "public" / "models" / "scene_manifest.json").read_text(encoding="utf-8"))
    model = create_optical_model_from_manifest("Cam_Portico", manifest["cameras"]["Cam_Portico"])
    solver = CameraCalibrationSolver(tmp_path / "camera_calibrations.json")

    correspondences = [
        PnPCorrespondence(world_point=[8.0, 0.0, 12.0], pixel_uv=[0.3, 0.4]),
        PnPCorrespondence(world_point=[10.0, 0.0, 14.0], pixel_uv=[0.6, 0.4]),
        PnPCorrespondence(world_point=[7.0, 0.0, 15.0], pixel_uv=[0.2, 0.7]),
        PnPCorrespondence(world_point=[11.0, 0.0, 11.0], pixel_uv=[0.8, 0.6]),
    ]

    # Mock solvePnPRansac returning a pose 10m away from the physical mount
    rvec_fake = np.zeros((3, 1), dtype=np.float64)
    tvec_fake = np.array([[0.0], [0.0], [10.0]], dtype=np.float64)
    inliers_fake = np.array([[0], [1], [2], [3]], dtype=np.int32)

    with patch.object(cv2, "solvePnPRansac", return_value=(True, rvec_fake, tvec_fake, inliers_fake)):
        with pytest.raises(RuntimeError, match="jumped"):
            solver.solve_pnp_ransac(model, correspondences)


@pytest.mark.tier1
def test_f19_overlay_no_crop_viewport_fov_and_pnp_jump_guard() -> None:
    """Verifies CameraFrustumOverlay preserves full [0,1] UVs under distortion, computes roll/aspect-aware POV FOV, and rejects local PnP jumps."""
    js_res = run_vite_module_script(
        REPO_ROOT,
        r"""
        const fs = await import('fs');
        const { makeElement } = installBrowserShims({ href: 'https://localhost:5173/' });
        const THREE = await server.ssrLoadModule('three');
        const { CameraFrustumOverlay } = await server.ssrLoadModule('/src/spatial/calibration/CameraFrustumOverlay.js');
        const { CameraProjector } = await server.ssrLoadModule('/src/spatial/CameraProjector.js');
        const { CalibrationAssistantUI } = await server.ssrLoadModule('/src/spatial/calibration/CalibrationAssistantUI.js');

        // 1. Overlay UV preservation under strong barrel distortion (k1 = -0.22, k2 = 0.05)
        const overlay = new CameraFrustumOverlay('Cam_Portico', {
          fovV: 48.98,
          fovH: 78.0,
          aspect: 16 / 9,
          distortion: [-0.22, 0.05, 0, 0, 0],
        });
        overlay.setPOVMode(true);
        const uvArr = overlay.geometry.attributes.uv.array;
        const posArr = overlay.geometry.attributes.position.array;
        let minU = Infinity, maxU = -Infinity, minV = Infinity, maxV = -Infinity;
        let maxPosX = 0;
        for (let i = 0; i < uvArr.length / 2; i++) {
          const u = uvArr[i * 2];
          const v = uvArr[i * 2 + 1];
          if (u < minU) minU = u;
          if (u > maxU) maxU = u;
          if (v < minV) minV = v;
          if (v > maxV) maxV = v;
          maxPosX = Math.max(maxPosX, Math.abs(posArr[i * 3]));
        }
        const pinholeHalfW = Math.tan(THREE.MathUtils.degToRad(78.0 * 0.5)) * overlay.depth;
        const fovNarrow15 = overlay.getRequiredViewportFovV(1.5, { rollRad: THREE.MathUtils.degToRad(4.4) });
        const fovWide178 = overlay.getRequiredViewportFovV(16 / 9, { rollRad: 0 });

        // 2. Projector computePovViewportFov & CalibrationAssistantUI PnP > 2.2m rejection
        const manifest = JSON.parse(fs.readFileSync('public/models/scene_manifest.json', 'utf-8'));
        const porticoMeta = manifest.cameras.Cam_Portico;
        const cameras = new Map();
        const cam = new THREE.PerspectiveCamera(porticoMeta.fov_v_deg, porticoMeta.aspect_ratio, 0.1, 250);
        cam.name = 'Cam_Portico';
        new THREE.Matrix4().set(...porticoMeta.gltf_transform.matrix_world_gl).decompose(cam.position, cam.quaternion, new THREE.Vector3());
        cam.updateMatrixWorld(true);
        cameras.set('Cam_Portico', cam);

        const projector = new CameraProjector(new THREE.Scene(), { cameras, manifest, groundColliders: [] });
        projector.setupCameraFrustums();
        const projectorFov15 = projector.computePovViewportFov('Cam_Portico', 1.5);

        const uiLayer = makeElement('div', 'ui-layer');
        uiLayer.classList.add('ui-layer');
        document.body.appendChild(uiLayer);
        const canvas = makeElement('canvas', 'c-pnp');
        const calib = new CalibrationAssistantUI({
          sceneManager: { renderer: { domElement: canvas }, camera: { aspect: 1.5, updateMatrixWorld() {} }, scene: new THREE.Scene(), addUpdateCallback() {}, removeUpdateCallback() {} },
          cameraController: { activePovCameraName: 'Cam_Portico', setPovExitLocked() {}, exitCameraPOV() {}, setInstantCameraPose() {} },
          cameraProjector: projector,
          videoStreamManager: { acquireVideoTexture: async () => ({ texture: {}, provider: { mode: 'webrtc' } }), releaseVideoTexture() {} },
          spatialStreamClient: null,
          assetLoader: { manifest, cameras },
          haClient: { isAdmin: true },
        });
        await calib.open('Cam_Portico');
        const beforeState = { ...calib.state };
        // Feed 4 coplanar-ish correspondences mapped to a far-away fake viewpoint (>3m away)
        calib.correspondences = [
          { world_point: [5.89, 0.0, 12.43], pixel_uv: [0.2, 0.8] },
          { world_point: [5.89, 0.0, 15.13], pixel_uv: [0.8, 0.8] },
          { world_point: [4.65, 0.0, 12.43], pixel_uv: [0.25, 0.3] },
          { world_point: [3.16, 2.08, 12.48], pixel_uv: [0.75, 0.25] },
        ];
        await calib.solvePnP();
        const afterState = { ...calib.state };
        const statusMsg = calib.panelEl?.querySelector('#calib-status-msg')?.textContent || '';

        return {
          minU, maxU, minV, maxV,
          flaredOutward: maxPosX > pinholeHalfW * 1.05,
          fovNarrow15,
          fovWide178,
          projectorFov15,
          statePreserved: JSON.stringify(beforeState) === JSON.stringify(afterState),
          statusMsg,
        };
        """,
    )

    assert js_res["minU"] == pytest.approx(0.0, abs=1e-5)
    assert js_res["maxU"] == pytest.approx(1.0, abs=1e-5)
    assert js_res["minV"] == pytest.approx(0.0, abs=1e-5)
    assert js_res["maxV"] == pytest.approx(1.0, abs=1e-5)
    assert js_res["flaredOutward"] is True
    assert js_res["fovNarrow15"] > js_res["fovWide178"]
    assert js_res["projectorFov15"] > 50.0
    assert js_res["statePreserved"] is True
    assert "scartato" in js_res["statusMsg"].lower() or "non ha trovato" in js_res["statusMsg"].lower()
