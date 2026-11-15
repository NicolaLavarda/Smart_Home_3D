from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from spatial_server.domain.models import Ray3D


class ICameraOpticalModel(ABC):
    """Strategy interface mapping normalized 2D image coordinates <-> 3D world rays."""

    camera_id: str
    optical_type: str

    @abstractmethod
    def pixel_to_world_ray(self, u_norm: float, v_norm: float) -> Ray3D:
        """Convert normalized top-left UV in [0, 1]^2 into a normalized 3D world Ray3D."""

    @abstractmethod
    def world_point_to_pixel(self, point_3d: tuple[float, float, float]) -> Optional[tuple[float, float]]:
        """Project a 3D world coordinate back into normalized [0, 1]^2 UV, or None if behind camera."""

    @abstractmethod
    def update_calibration(
        self,
        extrinsic_cv_to_world: Optional[list[float]] = None,
        fov_h_deg: Optional[float] = None,
        fov_v_deg: Optional[float] = None,
        distortion_coeffs: Optional[list[float]] = None,
    ) -> None:
        """Update live extrinsics/intrinsics without reconstructing dependent services."""

    @abstractmethod
    def to_metadata_dict(self) -> dict[str, Any]:
        """Serialize current intrinsics/extrinsics for persistence & diagnostics."""

