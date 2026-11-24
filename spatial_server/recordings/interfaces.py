from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional


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
    stream_tier: str = "sub"
    codec: str = "h264"
    width: int = 0
    height: int = 0
    relative_path: str = ""

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
            "stream_tier": self.stream_tier,
            "codec": self.codec,
            "width": self.width,
            "height": self.height,
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
    effective_end_unix: Optional[float] = None
    switch_at_unix: Optional[float] = None
    next_segment: Optional[RecordingSegmentRecord] = None
    next_seek_offset_sec: float = 0.0
    fallback_reason: Optional[str] = None

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "camera_id": self.camera_id,
            "requested_unix": self.requested_unix,
            "seek_offset_sec": round(max(0.0, self.seek_offset_sec), 3),
            "reason": self.reason,
            "segment": self.segment.to_api_dict() if self.segment else None,
            "effective_end_unix": self.effective_end_unix,
            "switch_at_unix": self.switch_at_unix,
            "next_segment": self.next_segment.to_api_dict() if self.next_segment else None,
            "next_seek_offset_sec": round(max(0.0, self.next_seek_offset_sec), 3),
            "fallback_reason": self.fallback_reason,
        }


@dataclass
class EncodedPacket:
    """Pacchetto compresso (video H.264/HEVC o audio AAC) senza decodifica pixel."""

    stream_kind: str  # "video" | "audio"
    data: bytes
    pts: Optional[int]
    dts: Optional[int]
    duration: Optional[int]
    time_base_num: int
    time_base_den: int
    is_keyframe: bool
    wall_ts: float
    codec_name: str = "h264"
    width: int = 0
    height: int = 0
    raw_packet: Any = None
    raw_stream: Any = None


@dataclass(frozen=True)
class StreamMetadata:
    """Parametri di flusso acquisiti all'apertura dello stream RTSP per il remuxing."""

    video_codec: str = "h264"
    width: int = 0
    height: int = 0
    video_time_base: tuple[int, int] = (1, 90000)
    has_audio: bool = False
    audio_codec: Optional[str] = None
    raw_video_stream: Any = None
    raw_audio_stream: Any = None


@dataclass
class GopChunk:
    """Gruppo di pacchetti che inizia rigorosamente da un keyframe (IDR) video."""

    packets: list[EncodedPacket]
    start_wall_ts: float
    end_wall_ts: float
    size_bytes: int
    codec_name: str = "h264"
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class SegmentWriteResult:
    """Esito della scrittura atomica di un segmento MP4 su disco."""

    file_path: Path
    size_bytes: int
    packet_count: int
    video_frame_count: int
    start_wall_ts: float
    end_wall_ts: float
    duration_sec: float
    codec_name: str
    width: int
    height: int


class IMediaPacketSource(ABC):
    """Strategia astratta per leggere pacchetti compressi da un flusso RTSP/locale."""

    @abstractmethod
    def open(self) -> StreamMetadata:
        raise NotImplementedError

    @abstractmethod
    def iter_packets(self) -> Iterator[EncodedPacket]:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class IMediaSegmentWriter(ABC):
    """Strategia astratta per scrivere pacchetti compressi in un file MP4 atomico."""

    @abstractmethod
    def open_segment(self, target_path: Path, metadata: StreamMetadata, start_wall_ts: float) -> None:
        raise NotImplementedError

    @abstractmethod
    def write_packet(self, packet: EncodedPacket) -> None:
        raise NotImplementedError

    @abstractmethod
    def close_segment(self, end_wall_ts: float) -> Optional[SegmentWriteResult]:
        raise NotImplementedError

    @abstractmethod
    def abort_segment(self) -> None:
        raise NotImplementedError


class INvrSegmentIndex(ABC):
    """Indice persistente (es. SQLite WAL) per query O(log N) e switch Sub/Main."""

    @abstractmethod
    def upsert_segment(self, record: RecordingSegmentRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_many(self, records: list[RecordingSegmentRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_segments(self, segment_ids: list[str]) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_cameras(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def query_range(
        self,
        camera_id: str,
        t_start: float,
        t_end: float,
        *,
        stream_tier: Optional[str] = None,
    ) -> list[RecordingSegmentRecord]:
        raise NotImplementedError

    @abstractmethod
    def resolve_at(
        self,
        camera_id: str,
        timestamp_unix: float,
        *,
        prefer_tier: str = "main",
        allow_hevc: bool = True,
        lookahead_sec: float = 120.0,
    ) -> PlaybackResolutionRecord:
        raise NotImplementedError


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


class IDualTierRecorderCoordinator(ABC):
    """Coordinatore del registratore dual-tier (Sub H24 + Main RAM pre-buffer su evento)."""

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def notify_detection_activity(
        self,
        *,
        camera_id: str,
        timestamp: float,
        class_label: str,
        confidence: float,
        track_id: Optional[int] = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def trigger_manual_event(self, camera_id: str, duration_sec: Optional[float] = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_diagnostics(self) -> dict[str, Any]:
        raise NotImplementedError
