from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from spatial_server.domain.models import Ray3D


class ISpatialRaycaster(ABC):
    """Adapter interface for casting 3D rays against walkable ground surfaces."""

    @abstractmethod
    def intersect_ground(self, ray: Ray3D) -> Optional[tuple[float, float, float]]:
        """Return nearest ground hit (x, y, z) within valid camera range, or None."""

