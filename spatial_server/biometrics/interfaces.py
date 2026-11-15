from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
import numpy as np
from spatial_server.domain.models import DetectionEvent


class IIdentityResolver(ABC):
    """Strategy interface for resolving person identity (Face Recognition / Re-ID)."""

    @abstractmethod
    async def resolve_identity(
        self,
        detection: DetectionEvent,
        frame_crop: Optional[np.ndarray] = None,
    ) -> tuple[Optional[str], float]:
        """Return (identity_name_or_none, confidence_0_to_1)."""

