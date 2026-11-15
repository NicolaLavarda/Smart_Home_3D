from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable
from spatial_server.domain.models import DetectionEvent

DetectionBatchCallback = Callable[[list[DetectionEvent]], Awaitable[None]]


class IDetectionSource(ABC):
    """Strategy interface for asynchronous 2D CV detection ingestion sources."""

    mode_name: str

    @abstractmethod
    async def start(self, on_batch: DetectionBatchCallback) -> None:
        """Start producing detection batches cleanly until stop() is awaited."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop source and release network/camera resources."""

    def status_details(self) -> str:
        return self.mode_name

