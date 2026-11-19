from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from spatial_server.recordings.interfaces import (
    IVideoArchiveRepository,
    PlaybackResolutionRecord,
    RecordingSegmentRecord,
)

# Convenzioni nome file supportate sul futuro HDD di videosorveglianza:
# 1. `<unix_start>_<duration_s>.mp4` (es. 1795092000_60.mp4)
# 2. `YYYYMMDD_HHMMSS.mp4` oppure `YYYY-MM-DD_HH-MM-SS.mp4` (durata default configurabile)
_UNIX_DUR_RE = re.compile(r"^(?P<start>\d{10})(?:_(?P<dur>\d+(?:\.\d+)?))?\.(mp4|mkv|webm)$", re.IGNORECASE)
_ISO_NAME_RE = re.compile(
    r"^(?P<y>\d{4})-?(?P<m>\d{2})-?(?P<d>\d{2})[_T-](?P<H>\d{2})-?(?P<M>\d{2})-?(?P<S>\d{2})(?:_(?P<dur>\d+))?\.(mp4|mkv|webm)$",
    re.IGNORECASE,
)
_SAFE_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


class FilesystemNvrArchiveRepository(IVideoArchiveRepository):
    """Repository NVR locale basato su filesystem (Hard Disk Videosorveglianza collegato al PC).

    Struttura cartelle attesa su disco (es. `SPATIAL_NVR_STORAGE_DIR=D:\\Surveillance`):
      <storage_dir>/<camera_id>/<YYYY-MM-DD>/<file>.mp4
      oppure
      <storage_dir>/<camera_id>/<file>.mp4
    """

    def __init__(self, storage_dir: Optional[Path] = None, default_segment_duration_s: float = 60.0) -> None:
        self._storage_dir = storage_dir
        self._default_duration_s = max(1.0, float(default_segment_duration_s))

    @property
    def storage_type(self) -> str:
        return "pc_nvr_hdd"

    @property
    def storage_dir(self) -> Optional[Path]:
        return self._storage_dir

    @property
    def is_configured(self) -> bool:
        return self._storage_dir is not None and self._storage_dir.exists() and self._storage_dir.is_dir()

    def _safe_camera_dir(self, camera_id: str) -> Optional[Path]:
        if not self.is_configured or not self._storage_dir:
            return None
        if not _SAFE_SEGMENT_RE.fullmatch(camera_id):
            return None
        root = self._storage_dir.resolve()
        cam_dir = (root / camera_id).resolve()
        if not str(cam_dir).startswith(str(root)):
            return None
        if not cam_dir.exists() or not cam_dir.is_dir():
            return None
        return cam_dir

    def _parse_file_segment(self, camera_id: str, file_path: Path) -> Optional[RecordingSegmentRecord]:
        name = file_path.name
        start_unix: Optional[float] = None
        duration_s = self._default_duration_s

        m_unix = _UNIX_DUR_RE.match(name)
        if m_unix:
            start_unix = float(m_unix.group("start"))
            if m_unix.group("dur"):
                duration_s = max(1.0, float(m_unix.group("dur")))
        else:
            m_iso = _ISO_NAME_RE.match(name)
            if m_iso:
                try:
                    dt = datetime(
                        int(m_iso.group("y")),
                        int(m_iso.group("m")),
                        int(m_iso.group("d")),
                        int(m_iso.group("H")),
                        int(m_iso.group("M")),
                        int(m_iso.group("S")),
                    )
                    start_unix = dt.timestamp()
                    if m_iso.group("dur"):
                        duration_s = max(1.0, float(m_iso.group("dur")))
                except ValueError:
                    start_unix = None

        if start_unix is None:
            return None

        try:
            size_bytes = file_path.stat().st_size
        except OSError:
            size_bytes = 0

        rel_id = file_path.name
        stream_url = f"/api/v1/recordings/{camera_id}/file/{rel_id}"
        return RecordingSegmentRecord(
            id=f"{camera_id}:{rel_id}",
            camera_id=camera_id,
            start_unix=start_unix,
            end_unix=start_unix + duration_s,
            stream_url=stream_url,
            format=file_path.suffix.lstrip(".").lower() or "mp4",
            storage_type=self.storage_type,
            has_motion=False,
            size_bytes=size_bytes,
            file_path=file_path,
        )

    def list_cameras(self) -> list[str]:
        if not self.is_configured or not self._storage_dir:
            return []
        return sorted(
            p.name for p in self._storage_dir.iterdir()
            if p.is_dir() and _SAFE_SEGMENT_RE.fullmatch(p.name)
        )

    def _scan_camera_files(self, camera_id: str) -> list[RecordingSegmentRecord]:
        cam_dir = self._safe_camera_dir(camera_id)
        if cam_dir is None:
            return []

        records: list[RecordingSegmentRecord] = []
        for path in cam_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in (".mp4", ".mkv", ".webm"):
                continue
            seg = self._parse_file_segment(camera_id, path)
            if seg is not None:
                records.append(seg)

        records.sort(key=lambda s: s.start_unix)
        return records

    def query_segments(self, camera_id: str, t_start: float, t_end: float) -> list[RecordingSegmentRecord]:
        if not self.is_configured:
            return []
        all_segs = self._scan_camera_files(camera_id)
        return [s for s in all_segs if s.end_unix >= t_start and s.start_unix <= t_end]

    def resolve_timestamp(self, camera_id: str, timestamp_unix: float) -> PlaybackResolutionRecord:
        if not self.is_configured:
            return PlaybackResolutionRecord(
                available=False,
                camera_id=camera_id,
                requested_unix=timestamp_unix,
                reason="storage_not_configured",
            )

        candidates = self.query_segments(camera_id, timestamp_unix - 1.0, timestamp_unix + 1.0)
        for seg in candidates:
            if seg.start_unix <= timestamp_unix <= seg.end_unix:
                return PlaybackResolutionRecord(
                    available=True,
                    camera_id=camera_id,
                    requested_unix=timestamp_unix,
                    segment=seg,
                    seek_offset_sec=max(0.0, timestamp_unix - seg.start_unix),
                    reason="ok",
                )

        return PlaybackResolutionRecord(
            available=False,
            camera_id=camera_id,
            requested_unix=timestamp_unix,
            reason="no_recording",
        )

    def resolve_segment_file(self, camera_id: str, filename: str) -> Optional[Path]:
        if not _SAFE_SEGMENT_RE.fullmatch(filename):
            return None
        cam_dir = self._safe_camera_dir(camera_id)
        if cam_dir is None:
            return None
        for path in cam_dir.rglob(filename):
            if path.is_file():
                resolved = path.resolve()
                if str(resolved).startswith(str(cam_dir)):
                    return resolved
        return None
