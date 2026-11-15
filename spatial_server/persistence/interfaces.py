from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from spatial_server.domain.models import TrackedEntity3D


class ITrackRepository(ABC):
    """Repository interface for persistent spatiotemporal trajectories."""

    @abstractmethod
    def append_batch(self, entities: list[TrackedEntity3D]) -> int:
        """Persist a batch of TrackedEntity3D states synchronously/atomically."""

    @abstractmethod
    def query_time_range(
        self,
        t_start: float,
        t_end: float,
        classes: Optional[list[str]] = None,
        zone_bbox: Optional[tuple[float, float, float, float]] = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Query detections inside [t_start, t_end] optionally filtered by class & XZ zone."""

    @abstractmethod
    def query_timeline_density(self, t_start: float, t_end: float, buckets: int = 60) -> list[dict[str, Any]]:
        """Compute activity histogram buckets across [t_start, t_end]."""

    @abstractmethod
    def prune_older_than(self, cutoff_timestamp: float) -> int:
        """Delete records older than cutoff_timestamp and return removed row count."""

