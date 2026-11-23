from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

import numpy as np

from spatial_server.domain.models import BoundingBox2D, DetectionEvent
from .models import BiometricJob, CropPayload, FaceEvaluation, PlateEvaluation


class IIdentityResolver(ABC):
    """Strategy interface for resolving person identity (Face Recognition / Re-ID)."""

    @abstractmethod
    async def resolve_identity(
        self,
        detection: DetectionEvent,
        frame_crop: Optional[np.ndarray] = None,
    ) -> tuple[Optional[str], float]:
        """Return (identity_name_or_none, confidence_0_to_1)."""


class IFrameSnapshotProvider(ABC):
    """Fetches a high-resolution frame in RAM, extracts a subject crop, and frees the full frame."""

    @abstractmethod
    async def fetch_crop(
        self,
        camera_id: str,
        bbox: BoundingBox2D,
        *,
        expand_ratio: tuple[float, float, float, float] = (0.15, 0.15, 0.15, 0.15),
        max_decode_width: Optional[int] = None,
        prefer_upper_fraction: Optional[float] = None,
        is_panoramic_180: bool = False,
    ) -> Optional[CropPayload]:
        """Return CropPayload or None if unavailable/timed out."""

    @abstractmethod
    async def close(self) -> None:
        """Release underlying HTTP/client resources."""


class IFaceRecognizer(ABC):
    """Runs face detection, quality gating, landmark alignment, and gallery matching on a person crop."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Return True when required ONNX models are loaded."""

    @abstractmethod
    def recognize_crop(self, person_crop_bgr: np.ndarray) -> Optional[FaceEvaluation]:
        """Evaluate a person crop and return FaceEvaluation or None if no usable face found."""


class IPlateRecognizer(ABC):
    """Runs license plate detection, quality gating, OCR, and IT/EU post-processing on a vehicle crop."""

    @abstractmethod
    def is_ready(self) -> bool:
        """Return True when required ALPR detector & OCR ONNX models are loaded."""

    @abstractmethod
    def recognize_crop(self, vehicle_crop_bgr: np.ndarray) -> Optional[PlateEvaluation]:
        """Evaluate a vehicle crop and return PlateEvaluation or None if no usable plate found."""


class IBiometricCoordinator(ABC):
    """Asynchronous bounded worker orchestrating dual-stream biometric evaluation & track consensus."""

    @abstractmethod
    async def start(self) -> None:
        """Start background biometric worker tasks."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop worker tasks and release pools/HTTP clients cleanly."""

    @abstractmethod
    def enqueue_candidate(self, job: BiometricJob) -> bool:
        """Attempt non-blocking enqueue; returns True if accepted for evaluation."""

    @abstractmethod
    def get_diagnostics(self) -> dict[str, Any]:
        """Return runtime status, latencies, queue depth, and error counters."""
