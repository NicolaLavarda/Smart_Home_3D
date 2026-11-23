from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from spatial_server.domain.models import BoundingBox2D, EntityClassLabel


class BiometricJob(BaseModel):
    """Asynchronous biometric evaluation request emitted after 3D tracking."""

    track_id: int
    camera_id: str
    class_label: EntityClassLabel
    timestamp: float
    bbox: BoundingBox2D
    obs_range_m: float = Field(ge=0.0)
    world_xyz: tuple[float, float, float]
    velocity_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)
    is_panoramic_180: bool = False
    camera_weight: float = Field(default=1.0, gt=0.0, le=2.0)

    @property
    def modality(self) -> Literal["face", "alpr"]:
        return "face" if self.class_label == "person" else "alpr"


@dataclass
class CropPayload:
    """In-memory BGR crop extracted from a high-resolution camera snapshot."""

    camera_id: str
    timestamp: float
    crop_bgr: np.ndarray
    full_width: int
    full_height: int
    crop_bbox_px: tuple[int, int, int, int]
    source_variant: str
    fetch_ms: float
    decode_ms: float


class FaceQualityMetrics(BaseModel):
    """Quality gate measurements for a detected face crop."""

    det_score: float = 0.0
    face_width_px: float = 0.0
    blur_laplacian: float = 0.0
    yaw_ratio: float = 1.0
    passed: bool = False
    reject_reason: Optional[str] = None


class FaceEvaluation(BaseModel):
    """Single-frame face recognition inference output."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    identity: Optional[str] = None
    similarity: float = 0.0
    second_best_similarity: float = 0.0
    margin: float = 0.0
    quality_score: float = 0.0
    metrics: FaceQualityMetrics
    crop_bgr: Optional[np.ndarray] = Field(default=None, exclude=True)


class PlateQualityMetrics(BaseModel):
    """Quality gate measurements for a detected license plate crop."""

    det_score: float = 0.0
    plate_width_px: float = 0.0
    blur_laplacian: float = 0.0
    glare_ratio: float = 0.0
    mean_luma: float = 0.0
    passed: bool = False
    reject_reason: Optional[str] = None


class PlateNormalizedResult(BaseModel):
    """Deterministic post-processed plate normalization & IT/EU format validation."""

    plate: Optional[str] = None
    raw_text: str = ""
    plate_format: Literal["IT_STD", "IT_MOTO", "EU_GENERIC", "INVALID"] = "INVALID"
    repairs_applied: int = 0
    confidence_penalty: float = 0.0
    is_valid: bool = False


class PlateEvaluation(BaseModel):
    """Single-frame ALPR inference output."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    plate: Optional[str] = None
    plate_raw: str = ""
    plate_format: Literal["IT_STD", "IT_MOTO", "EU_GENERIC", "INVALID"] = "INVALID"
    confidence: float = 0.0
    region: Optional[str] = None
    quality_score: float = 0.0
    metrics: PlateQualityMetrics
    crop_bgr: Optional[np.ndarray] = Field(default=None, exclude=True)


class PlateWhitelistEntry(BaseModel):
    """Authorized family/visitor vehicle plate entry."""

    plate: str
    owner_name: str
    vehicle_label: Optional[str] = None
    notes: Optional[str] = None
    updated_at: float = 0.0


class TrackBiometricUpdate(BaseModel):
    """Consensus biometric update propagated to Kalman3DMultiTracker, SQLite & WS."""

    track_id: int
    modality: Literal["face", "alpr"]
    identity: Optional[str] = None
    identity_confidence: float = 0.0
    plate: Optional[str] = None
    plate_raw: Optional[str] = None
    plate_confidence: float = 0.0
    plate_format: Optional[str] = None
    plate_whitelisted: Optional[bool] = None
    plate_owner: Optional[str] = None
    biometric_locked: bool = False
    biometric_status: Literal["pending", "locked", "unknown"] = "pending"
    attempts_count: int = 0
    best_crop_id: Optional[str] = None
    best_crop_relpath: Optional[str] = None
    quality_score: float = 0.0
    camera_id: str
    timestamp: float
