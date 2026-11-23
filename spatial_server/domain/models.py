from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


EntityClassLabel = Literal["person", "car", "truck", "bicycle", "dog", "motorbike"]


class BoundingBox2D(BaseModel):
    """Normalized 2D bounding box in [0, 1]^4 (origin top-left)."""

    x_min: float = Field(ge=0.0, le=1.0)
    y_min: float = Field(ge=0.0, le=1.0)
    x_max: float = Field(ge=0.0, le=1.0)
    y_max: float = Field(ge=0.0, le=1.0)

    def get_ground_contact_uv(self) -> tuple[float, float]:
        """Return bottom-center pixel coordinate (u, v) representing ground contact."""
        u = 0.5 * (self.x_min + self.x_max)
        v = self.y_max
        return (float(min(max(u, 0.0), 1.0)), float(min(max(v, 0.0), 1.0)))


class DetectionEvent(BaseModel):
    """Single-camera 2D detection emitted by an IDetectionSource."""

    camera_id: str
    timestamp: float
    class_label: EntityClassLabel
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox2D
    sub_label: Optional[str] = None
    face_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    plate: Optional[str] = None
    plate_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    track_hint_id: Optional[str] = None


class Ray3D(BaseModel):
    """3D ray in Three.js world space (+X East, +Y Up, +Z South)."""

    origin: tuple[float, float, float]
    direction: tuple[float, float, float]


class SpatialPoint3D(BaseModel):
    """3D kinematic state estimated in world space."""

    x: float
    y: float
    z: float
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    covariance_diag: list[float] = Field(default_factory=lambda: [0.25, 0.05, 0.25])
    camera_sources: list[str] = Field(default_factory=list)


class TrackedEntity3D(BaseModel):
    """Tracked multi-camera 3D entity output consumed by UI & SQLite."""

    track_id: int
    class_label: str
    confidence: float = 0.9
    identity: Optional[str] = None
    identity_confidence: float = 0.0
    plate: Optional[str] = None
    plate_confidence: float = 0.0
    plate_whitelisted: Optional[bool] = None
    plate_owner: Optional[str] = None
    biometric_locked: bool = False
    biometric_status: Literal["none", "pending", "locked", "unknown"] = "none"
    best_crop_id: Optional[str] = None
    state: SpatialPoint3D
    last_seen: float


class CalibrationOverridePayload(BaseModel):
    """Live extrinsic & optical adjustment sent from the POV Calibration UI."""

    camera_id: str
    offset_xyz: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    delta_euler_deg: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    fov_v_deg: Optional[float] = None
    fov_h_deg: Optional[float] = None
    distortion_coeffs: Optional[list[float]] = None
    calibrated_matrix_world_gl: Optional[list[float]] = None
    ui_state: Optional[dict[str, Any]] = None

    @field_validator("calibrated_matrix_world_gl")
    @classmethod
    def check_matrix_len(cls, v: Optional[list[float]]) -> Optional[list[float]]:
        if v is not None and len(v) != 16:
            raise ValueError("calibrated_matrix_world_gl must contain 16 row-major floats")
        return v


class PnPCorrespondence(BaseModel):
    """One 3D-to-2D landmark correspondence collected visually in POV mode."""

    world_point: tuple[float, float, float]
    pixel_uv: tuple[float, float]


class SolvePnPRequest(BaseModel):
    """Batch request to refine camera extrinsics via SolvePnPRansac."""

    camera_id: str
    correspondences: list[PnPCorrespondence] = Field(min_length=4)

