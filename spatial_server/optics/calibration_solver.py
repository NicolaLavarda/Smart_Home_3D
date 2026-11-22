from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import cv2
import numpy as np

from spatial_server.domain.models import PnPCorrespondence
from .interfaces import ICameraOpticalModel
from .panoramic_model import EquirectangularPanoramicOpticalModel
from .pinhole_model import PinholeRadTanOpticalModel, matrix_cv_to_gl

logger = logging.getLogger("spatial_server.calibration")


def create_optical_model_from_manifest(camera_id: str, cam_entry: dict[str, Any]) -> ICameraOpticalModel:
    """Factory creating the appropriate ICameraOpticalModel strategy from scene_manifest.json."""
    gltf_tf = cam_entry.get("gltf_transform", {})
    extrinsic = gltf_tf.get("extrinsic_cv_to_world")
    if not extrinsic or len(extrinsic) != 16:
        extrinsic = np.eye(4, dtype=np.float64).reshape(-1).tolist()

    optical_type = str(cam_entry.get("optical_model", "pinhole_radtan")).lower()
    fov_h = float(cam_entry.get("fov_h_deg", 80.0))
    fov_v = float(cam_entry.get("fov_v_deg", 42.0))

    if "equirectangular" in optical_type or "panoramic" in optical_type or fov_h >= 150.0:
        return EquirectangularPanoramicOpticalModel(
            camera_id=camera_id,
            extrinsic_cv_to_world=extrinsic,
            fov_h_deg=fov_h,
            fov_v_deg=fov_v,
        )

    return PinholeRadTanOpticalModel(
        camera_id=camera_id,
        extrinsic_cv_to_world=extrinsic,
        fov_h_deg=fov_h,
        fov_v_deg=fov_v,
        distortion_coeffs=cam_entry.get("distortion_coeffs", [-0.18, 0.04, 0.0, 0.0, 0.0]),
    )


@dataclass
class PnPSolveResult:
    extrinsic_cv_to_world: list[float]
    matrix_world_gl: list[float]
    reprojection_error_px: float
    inliers_count: int


class CameraCalibrationSolver:
    """Service refining 6-DoF camera extrinsics from 3D<->2D landmark correspondences."""

    def __init__(self, override_path: Path) -> None:
        self.override_path = override_path
        self._file_lock = threading.RLock()

    def solve_pnp_ransac(
        self,
        optical_model: PinholeRadTanOpticalModel,
        correspondences: list[PnPCorrespondence],
    ) -> PnPSolveResult:
        if len(correspondences) < 4:
            raise ValueError("At least 4 3D-2D correspondences are required for SolvePnPRansac")

        obj_pts = np.array([c.world_point for c in correspondences], dtype=np.float64)
        img_pts = np.array(
            [[c.pixel_uv[0] * optical_model.image_width, c.pixel_uv[1] * optical_model.image_height] for c in correspondences],
            dtype=np.float64,
        )

        # Initialize extrinsic guess from current pose for fast convergence
        T_cv_world_init = np.linalg.inv(optical_model.T_world_cv)
        rvec_init, _ = cv2.Rodrigues(T_cv_world_init[:3, :3])
        tvec_init = T_cv_world_init[:3, 3].reshape((3, 1))

        ok, rvec, tvec, inliers = cv2.solvePnPRansac(
            obj_pts,
            img_pts,
            optical_model.K,
            optical_model.dist_coeffs,
            rvec=rvec_init,
            tvec=tvec_init,
            useExtrinsicGuess=True,
            iterationsCount=200,
            reprojectionError=12.0,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )

        if not ok:
            # Fallback without extrinsic guess if initial pose is rotated ~180 deg away
            flags = cv2.SOLVEPNP_SQPNP if len(correspondences) >= 4 else cv2.SOLVEPNP_EPNP
            ok, rvec, tvec, inliers = cv2.solvePnPRansac(
                obj_pts,
                img_pts,
                optical_model.K,
                optical_model.dist_coeffs,
                useExtrinsicGuess=False,
                iterationsCount=300,
                reprojectionError=16.0,
                flags=flags,
            )

        if not ok:
            raise RuntimeError("cv2.solvePnPRansac failed to converge on supplied points")

        projected, _ = cv2.projectPoints(obj_pts, rvec, tvec, optical_model.K, optical_model.dist_coeffs)
        errors = np.linalg.norm(projected.reshape((-1, 2)) - img_pts, axis=1)
        mean_err = float(np.mean(errors))

        R_cv_world, _ = cv2.Rodrigues(rvec)
        T_cv_world = np.eye(4, dtype=np.float64)
        T_cv_world[:3, :3] = R_cv_world
        T_cv_world[:3, 3] = tvec.reshape(3)

        T_world_cv = np.linalg.inv(T_cv_world)
        extrinsic_list = T_world_cv.reshape(-1).tolist()
        gl_list = matrix_cv_to_gl(T_world_cv).reshape(-1).tolist()

        return PnPSolveResult(
            extrinsic_cv_to_world=extrinsic_list,
            matrix_world_gl=gl_list,
            reprojection_error_px=mean_err,
            inliers_count=int(len(inliers)) if inliers is not None else len(correspondences),
        )

    def _write_all_overrides_locked(self, all_data: dict[str, dict[str, Any]]) -> None:
        self.override_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(all_data, indent=2)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.override_path.parent),
            prefix=f".{self.override_path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(serialized)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.override_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def save_override(self, camera_id: str, metadata: dict[str, Any]) -> None:
        with self._file_lock:
            all_data = self.load_all_overrides()
            all_data[camera_id] = metadata
            self._write_all_overrides_locked(all_data)

    def delete_override(self, camera_id: str) -> bool:
        with self._file_lock:
            all_data = self.load_all_overrides()
            if camera_id not in all_data:
                return False
            del all_data[camera_id]
            self._write_all_overrides_locked(all_data)
            return True

    def load_all_overrides(self) -> dict[str, dict[str, Any]]:
        with self._file_lock:
            if not self.override_path.exists():
                return {}
            try:
                raw = json.loads(self.override_path.read_text(encoding="utf-8"))
                return raw if isinstance(raw, dict) else {}
            except Exception as exc:
                logger.warning("Failed to load calibration overrides from %s: %s", self.override_path, exc)
                return {}

