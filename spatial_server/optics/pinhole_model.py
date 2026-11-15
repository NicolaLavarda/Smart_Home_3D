from __future__ import annotations

import math
from typing import Any, Optional
import cv2
import numpy as np

from spatial_server.domain.models import Ray3D
from .interfaces import ICameraOpticalModel

# Basis transform converting OpenCV camera coordinates (+X right, +Y down, +Z forward)
# to Three.js / glTF camera coordinates (+X right, +Y up, -Z forward).
S_GL_FROM_CV = np.diag([1.0, -1.0, -1.0, 1.0])


def matrix_gl_to_cv(matrix_world_gl: np.ndarray) -> np.ndarray:
    """Convert row-major 4x4 Three.js camera->world matrix to CV camera->world matrix."""
    return matrix_world_gl @ S_GL_FROM_CV


def matrix_cv_to_gl(extrinsic_cv_to_world: np.ndarray) -> np.ndarray:
    """Convert row-major 4x4 CV camera->world matrix back to Three.js camera->world matrix."""
    return extrinsic_cv_to_world @ S_GL_FROM_CV


class PinholeRadTanOpticalModel(ICameraOpticalModel):
    """Pinhole + Brown-Conrady radial-tangential optical model (Reolink RLC-540A)."""

    optical_type = "pinhole_radtan"

    def __init__(
        self,
        camera_id: str,
        extrinsic_cv_to_world: list[float],
        fov_h_deg: float = 80.0,
        fov_v_deg: float = 42.0,
        distortion_coeffs: Optional[list[float]] = None,
        image_width: int = 1920,
        image_height: int = 1080,
    ) -> None:
        self.camera_id = camera_id
        self.image_width = int(image_width)
        self.image_height = int(image_height)
        self.fov_h_deg = float(fov_h_deg)
        self.fov_v_deg = float(fov_v_deg)

        dist = list(distortion_coeffs or [-0.18, 0.04, 0.0, 0.0, 0.0])
        while len(dist) < 5:
            dist.append(0.0)
        self.dist_coeffs = np.array(dist[:5], dtype=np.float64)

        self.T_world_cv = np.array(extrinsic_cv_to_world, dtype=np.float64).reshape((4, 4))
        self.K = self._build_intrinsic_matrix(self.fov_h_deg, self.fov_v_deg, self.image_width, self.image_height)

    @staticmethod
    def _build_intrinsic_matrix(fov_h_deg: float, fov_v_deg: float, width: int, height: int) -> np.ndarray:
        fx = (width * 0.5) / max(math.tan(math.radians(fov_h_deg * 0.5)), 1e-6)
        fy = (height * 0.5) / max(math.tan(math.radians(fov_v_deg * 0.5)), 1e-6)
        cx = width * 0.5
        cy = height * 0.5
        return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)

    def pixel_to_world_ray(self, u_norm: float, v_norm: float) -> Ray3D:
        px = float(u_norm) * self.image_width
        py = float(v_norm) * self.image_height
        pts = np.array([[[px, py]]], dtype=np.float64)

        # Undistort pixel to normalized camera plane (Z = +1.0 in OpenCV convention)
        undistorted = cv2.undistortPoints(pts, self.K, self.dist_coeffs)
        x_cam = float(undistorted[0, 0, 0])
        y_cam = float(undistorted[0, 0, 1])

        dir_cv = np.array([x_cam, y_cam, 1.0], dtype=np.float64)
        R_world_cv = self.T_world_cv[:3, :3]
        origin = self.T_world_cv[:3, 3]

        dir_world = R_world_cv @ dir_cv
        norm = float(np.linalg.norm(dir_world))
        if norm > 1e-9:
            dir_world = dir_world / norm

        return Ray3D(
            origin=(float(origin[0]), float(origin[1]), float(origin[2])),
            direction=(float(dir_world[0]), float(dir_world[1]), float(dir_world[2])),
        )

    def world_point_to_pixel(self, point_3d: tuple[float, float, float]) -> Optional[tuple[float, float]]:
        T_cv_world = np.linalg.inv(self.T_world_cv)
        p_w = np.array([point_3d[0], point_3d[1], point_3d[2], 1.0], dtype=np.float64)
        p_cv = T_cv_world @ p_w
        if p_cv[2] <= 0.05:
            return None

        rvec = np.zeros((3, 1), dtype=np.float64)
        tvec = np.zeros((3, 1), dtype=np.float64)
        img_pts, _ = cv2.projectPoints(
            p_cv[:3].reshape((1, 1, 3)),
            rvec,
            tvec,
            self.K,
            self.dist_coeffs,
        )
        u_norm = float(img_pts[0, 0, 0]) / self.image_width
        v_norm = float(img_pts[0, 0, 1]) / self.image_height
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
        if distortion_coeffs is not None:
            dist = list(distortion_coeffs)
            while len(dist) < 5:
                dist.append(0.0)
            self.dist_coeffs = np.array(dist[:5], dtype=np.float64)

        self.K = self._build_intrinsic_matrix(self.fov_h_deg, self.fov_v_deg, self.image_width, self.image_height)

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "optical_model": self.optical_type,
            "fov_h_deg": self.fov_h_deg,
            "fov_v_deg": self.fov_v_deg,
            "distortion_coeffs": self.dist_coeffs.tolist(),
            "extrinsic_cv_to_world": self.T_world_cv.reshape(-1).tolist(),
            "matrix_world_gl": matrix_cv_to_gl(self.T_world_cv).reshape(-1).tolist(),
        }

