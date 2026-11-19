from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class RecordingSegmentRecord:
    """Metadati di un segmento video registrato (MP4/fMP4) su NVR locale o storage edge."""

    id: str
    camera_id: str
    start_unix: float
    end_unix: float
    stream_url: str
    format: str = "mp4"
    storage_type: str = "pc_nvr_hdd"
    has_motion: bool = False
    size_bytes: int = 0
    file_path: Optional[Path] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "start_unix": self.start_unix,
            "end_unix": self.end_unix,
            "duration_sec": max(0.0, self.end_unix - self.start_unix),
            "stream_url": self.stream_url,
            "format": self.format,
            "storage_type": self.storage_type,
            "has_motion": self.has_motion,
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class PlaybackResolutionRecord:
    available: bool
    camera_id: str
    requested_unix: float
    segment: Optional[RecordingSegmentRecord] = None
    seek_offset_sec: float = 0.0
    reason: str = "no_recording"

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "camera_id": self.camera_id,
            "requested_unix": self.requested_unix,
            "seek_offset_sec": round(max(0.0, self.seek_offset_sec), 3),
            "reason": self.reason,
            "segment": self.segment.to_api_dict() if self.segment else None,
        }


class IVideoArchiveRepository(ABC):
    """Interfaccia astratta (SOLID) per archivi di registrazione video (HDD NVR, Frigate, Edge SD)."""

    @property
    @abstractmethod
    def storage_type(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_cameras(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def query_segments(self, camera_id: str, t_start: float, t_end: float) -> list[RecordingSegmentRecord]:
        raise NotImplementedError

    @abstractmethod
    def resolve_timestamp(self, camera_id: str, timestamp_unix: float) -> PlaybackResolutionRecord:
        raise NotImplementedError

    @abstractmethod
    def resolve_segment_file(self, camera_id: str, filename: str) -> Optional[Path]:
        raise NotImplementedError
