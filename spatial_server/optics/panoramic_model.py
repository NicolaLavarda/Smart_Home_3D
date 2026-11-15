from __future__ import annotations

import math
from typing import Any, Optional
import numpy as np

from spatial_server.domain.models import Ray3D
from .interfaces import ICameraOpticalModel
from .pinhole_model import matrix_cv_to_gl


class EquirectangularPanoramicOpticalModel(ICameraOpticalModel):
    """
    Optical model for wide 180-deg stitched panoramic cameras (e.g. Reolink Duo 3 PoE).
    Maps normalized image coordinates (u, v) to azimuth/elevation angles (theta, phi)
    in camera frame (+X right, +Y down, +Z forward) before transforming to world space.
    """

    optical_type = "equirectangular_180"

    def __init__(
        self,
        camera_id: str,
        extrinsic_cv_to_world: list[float],
        fov_h_deg: float = 180.0,
        fov_v_deg: float = 55.0,
    ) -> None:
        self.camera_id = camera_id
        self.fov_h_deg = float(fov_h_deg)
        self.fov_v_deg = float(fov_v_deg)
        self.T_world_cv = np.array(extrinsic_cv_to_world, dtype=np.float64).reshape((4, 4))

    def pixel_to_world_ray(self, u_norm: float, v_norm: float) -> Ray3D:
        theta = math.radians((float(u_norm) - 0.5) * self.fov_h_deg)
        phi = math.radians((float(v_norm) - 0.5) * self.fov_v_deg)

        # OpenCV camera frame: +X right, +Y down, +Z forward
        cos_phi = math.cos(phi)
        dir_cv = np.array(
            [
                cos_phi * math.sin(theta),
                math.sin(phi),
                cos_phi * math.cos(theta),
            ],
            dtype=np.float64,
        )

        dir_world = self.T_world_cv[:3, :3] @ dir_cv
        norm = float(np.linalg.norm(dir_world))
        if norm > 1e-9:
            dir_world = dir_world / norm

        origin = self.T_world_cv[:3, 3]
        return Ray3D(
            origin=(float(origin[0]), float(origin[1]), float(origin[2])),
            direction=(float(dir_world[0]), float(dir_world[1]), float(dir_world[2])),
        )

    def world_point_to_pixel(self, point_3d: tuple[float, float, float]) -> Optional[tuple[float, float]]:
        T_cv_world = np.linalg.inv(self.T_world_cv)
        p_w = np.array([point_3d[0], point_3d[1], point_3d[2], 1.0], dtype=np.float64)
        p_cv = (T_cv_world @ p_w)[:3]
        dist = float(np.linalg.norm(p_cv))
        if dist < 0.05:
            return None

        theta = math.atan2(float(p_cv[0]), float(p_cv[2]))
        phi = math.asin(max(-1.0, min(1.0, float(p_cv[1]) / dist)))

        u_norm = 0.5 + math.degrees(theta) / max(self.fov_h_deg, 1e-6)
        v_norm = 0.5 + math.degrees(phi) / max(self.fov_v_deg, 1e-6)
        if abs(math.degrees(theta)) > self.fov_h_deg * 0.55:
            return None
        return (u_norm, v_norm)

    def update_calibration(
        self,
        extrinsic_cv_to_world: Optional[list[float]] = None,
        fov_h_deg: Optional[float] = None,
        fov_v_deg: Optional[float] = None,
        distortion_coeffs: Optional[list[float]] = None,
    ) -> None:
        if extrinsic_cv_to_world is not None:
            self.T_world_cv = np.array(extrinsic_cv_to_world, dtype=np.float64).reshape((4, 4))
        if fov_h_deg is not None:
            self.fov_h_deg = float(fov_h_deg)
        if fov_v_deg is not None:
            self.fov_v_deg = float(fov_v_deg)

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "optical_model": self.optical_type,
            "fov_h_deg": self.fov_h_deg,
            "fov_v_deg": self.fov_v_deg,
            "distortion_coeffs": [],
            "extrinsic_cv_to_world": self.T_world_cv.reshape(-1).tolist(),
            "matrix_world_gl": matrix_cv_to_gl(self.T_world_cv).reshape(-1).tolist(),
        }

