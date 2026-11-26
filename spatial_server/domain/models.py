from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


EntityClassLabel = Literal["person", "car", "truck", "bicycle", "dog", "motorbike"]

_VEHICLE_CLASS_LABELS = frozenset({"car", "truck", "motorbike", "motorcycle", "bus", "vehicle"})
_ANIMAL_CLASS_LABELS = frozenset({"dog", "cat", "bird", "horse", "sheep", "cow", "bear", "animal"})


def reconstruction_category(class_label: str) -> str:
    """Map fine-grained detection labels into reconstruction categories: person, vehicle, animal, or fallback."""
    norm = (class_label or "").strip().lower()
    if norm == "person":
        return "person"
    if norm in _VEHICLE_CLASS_LABELS:
        return "vehicle"
    if norm in _ANIMAL_CLASS_LABELS:
        return "animal"
    return norm


@dataclass(frozen=True)
class ClassReconstructionRule:
    """Confidence and motion thresholds deciding whether a class is reconstructed in 3D."""

    enabled: bool = True
    stationary_conf_threshold: float = 0.35
    moving_conf_threshold: float = 0.35
    min_speed_mps: float = 0.0

    @property
    def min_detection_conf_threshold(self) -> float:
        return min(float(self.stationary_conf_threshold), float(self.moving_conf_threshold))

    def required_confidence(self, is_moving: bool) -> float:
        return float(self.moving_conf_threshold if is_moving else self.stationary_conf_threshold)


@dataclass(frozen=True)
class SpatialReconstructionPolicy:
    """Per-category 3D reconstruction rules for persons, vehicles, and animals."""

    person: ClassReconstructionRule
    vehicle: ClassReconstructionRule
    animal: ClassReconstructionRule
    fallback_conf_threshold: float = 0.35

    def rule_for(self, class_label: str) -> ClassReconstructionRule:
        cat = reconstruction_category(class_label)
        if cat == "person":
            return self.person
        if cat == "vehicle":
            return self.vehicle
        if cat == "animal":
            return self.animal
        return ClassReconstructionRule(
            enabled=True,
            stationary_conf_threshold=self.fallback_conf_threshold,
            moving_conf_threshold=self.fallback_conf_threshold,
            min_speed_mps=0.0,
        )

    def is_class_enabled(self, class_label: str) -> bool:
        return self.rule_for(class_label).enabled

    def min_detection_conf_floor(self) -> float:
        floors = [
            rule.min_detection_conf_threshold
            for rule in (self.person, self.vehicle, self.animal)
            if rule.enabled
        ]
        floors.append(float(self.fallback_conf_threshold))
        return max(0.05, min(0.99, min(floors)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "person": {
                "enabled": self.person.enabled,
                "stationary_conf_threshold": self.person.stationary_conf_threshold,
                "moving_conf_threshold": self.person.moving_conf_threshold,
                "min_speed_mps": self.person.min_speed_mps,
            },
            "vehicle": {
                "enabled": self.vehicle.enabled,
                "stationary_conf_threshold": self.vehicle.stationary_conf_threshold,
                "moving_conf_threshold": self.vehicle.moving_conf_threshold,
                "min_speed_mps": self.vehicle.min_speed_mps,
            },
            "animal": {
                "enabled": self.animal.enabled,
                "stationary_conf_threshold": self.animal.stationary_conf_threshold,
                "moving_conf_threshold": self.animal.moving_conf_threshold,
                "min_speed_mps": self.animal.min_speed_mps,
            },
            "fallback_conf_threshold": self.fallback_conf_threshold,
        }


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

