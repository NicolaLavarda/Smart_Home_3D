from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from spatial_server.domain.models import TrackedEntity3D


@dataclass
class TrackObservation3D:
    camera_id: str
    timestamp: float
    class_label: str
    position: tuple[float, float, float]
    confidence: float = 0.9
    identity: Optional[str] = None
    identity_confidence: float = 0.0
    range_m: Optional[float] = None


class IMultiTargetTracker3D(ABC):
    """Strategy interface for 3D multi-object tracking and multi-camera fusion."""

    @abstractmethod
    def update(self, observations: list[TrackObservation3D], now_ts: float) -> list[TrackedEntity3D]:
        """Advance filter state with a batch of 3D observations and return active tracks."""

    @abstractmethod
    def get_active_tracks(self) -> list[TrackedEntity3D]:
        """Return currently active 3D tracks."""

