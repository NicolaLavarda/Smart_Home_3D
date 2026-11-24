from __future__ import annotations

import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from spatial_server.recordings.interfaces import (
    IVideoArchiveRepository,
    PlaybackResolutionRecord,
    RecordingSegmentRecord,
)
from spatial_server.recordings.sqlite_index import SQLiteNvrIndexStore

# Convenzioni nome file supportate sull'HDD di videosorveglianza:
# 1. `<tier>_<unix_start>_<duration_s>.mp4` (es. sub_1795092000.250_60.000.mp4, main_1795092010.125_24.500.mp4)
# 2. `<unix_start>_<duration_s>.mp4` (es. 1795092000_60.mp4)
# 3. `YYYYMMDD_HHMMSS.mp4` oppure `YYYY-MM-DD_HH-MM-SS.mp4`
_TIER_UNIX_RE = re.compile(
    r"^(?P<tier>sub|main)_(?P<start>\d{10}(?:\.\d+)?)_(?P<dur>\d+(?:\.\d+)?)\.(mp4|mkv|webm)$",
    re.IGNORECASE,
)
_UNIX_DUR_RE = re.compile(
    r"^(?P<start>\d{10}(?:\.\d+)?)(?:_(?P<dur>\d+(?:\.\d+)?))?\.(mp4|mkv|webm)$",
    re.IGNORECASE,
)
_ISO_NAME_RE = re.compile(
    r"^(?:(?P<tier>sub|main)_)?(?P<y>\d{4})-?(?P<m>\d{2})-?(?P<d>\d{2})[_T-](?P<H>\d{2})-?(?P<M>\d{2})-?(?P<S>\d{2})(?:_(?P<dur>\d+(?:\.\d+)?))?\.(mp4|mkv|webm)$",
    re.IGNORECASE,
)
_SAFE_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


class FilesystemNvrArchiveRepository(IVideoArchiveRepository):
    """Repository NVR locale basato su HDD + indice SQLite WAL (O(log N) e priorità main > sub).

    Struttura cartelle attesa su disco (es. `SPATIAL_NVR_STORAGE_DIR=D:\\Surveillance`):
      <storage_dir>/<camera_id>/<YYYY-MM-DD>/<file>.mp4
      oppure
      <storage_dir>/<camera_id>/<file>.mp4
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        default_segment_duration_s: float = 60.0,
        index_db_name: str = "nvr_index.db",
    ) -> None:
        self._storage_dir = storage_dir
        self._default_duration_s = max(1.0, float(default_segment_duration_s))
        self._index_db_name = Path(index_db_name or "nvr_index.db").name or "nvr_index.db"
        self._index_lock = threading.Lock()
        self._sync_lock = threading.RLock()
        self._index: Optional[SQLiteNvrIndexStore] = None
        self._dir_fingerprints: dict[str, tuple[float, ...]] = {}

    @property
    def storage_type(self) -> str:
        return "pc_nvr_hdd"

    @property
    def storage_dir(self) -> Optional[Path]:
        return self._storage_dir

    @property
    def is_configured(self) -> bool:
        return self._storage_dir is not None and self._storage_dir.exists() and self._storage_dir.is_dir()

    def _get_index(self) -> Optional[SQLiteNvrIndexStore]:
        if not self.is_configured or self._storage_dir is None:
            return None
        with self._index_lock:
            if self._index is None:
                self._index = SQLiteNvrIndexStore(
                    db_path=self._storage_dir / self._index_db_name,
                    storage_root=self._storage_dir,
                )
            return self._index

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
        if name.endswith(".tmp.mp4") or name.startswith("."):
            return None

        start_unix: Optional[float] = None
        duration_s = self._default_duration_s
        stream_tier = "sub"

        m_tier = _TIER_UNIX_RE.match(name)
        if m_tier:
            stream_tier = m_tier.group("tier").lower()
            start_unix = float(m_tier.group("start"))
            duration_s = max(0.2, float(m_tier.group("dur")))
        else:
            m_unix = _UNIX_DUR_RE.match(name)
            if m_unix:
                start_unix = float(m_unix.group("start"))
                if m_unix.group("dur"):
                    duration_s = max(0.2, float(m_unix.group("dur")))
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
                        if m_iso.group("tier"):
                            stream_tier = m_iso.group("tier").lower()
                        if m_iso.group("dur"):
                            duration_s = max(0.2, float(m_iso.group("dur")))
                    except ValueError:
                        start_unix = None

        if start_unix is None:
            return None

        try:
            size_bytes = file_path.stat().st_size
        except OSError:
            size_bytes = 0

        rel_path = ""
        if self._storage_dir is not None:
            try:
                rel_path = str(file_path.resolve().relative_to(self._storage_dir.resolve())).replace("\\", "/")
            except Exception:
                rel_path = f"{camera_id}/{name}"

        stream_url = f"/api/v1/recordings/{camera_id}/file/{name}"
        return RecordingSegmentRecord(
            id=f"{camera_id}:{name}",
            camera_id=camera_id,
            start_unix=start_unix,
            end_unix=start_unix + duration_s,
            stream_url=stream_url,
            format=file_path.suffix.lstrip(".").lower() or "mp4",
            storage_type=self.storage_type,
            has_motion=(stream_tier == "main"),
            size_bytes=size_bytes,
            file_path=file_path,
            stream_tier=stream_tier,
            codec="h264",
            relative_path=rel_path,
        )

    def _compute_dir_fingerprint(self, cam_dir: Path) -> tuple[float, ...]:
        mtimes: list[float] = []
        try:
            mtimes.append(cam_dir.stat().st_mtime)
            for child in sorted(cam_dir.iterdir()):
                if child.is_dir():
                    mtimes.append(child.stat().st_mtime)
        except OSError:
            pass
        return tuple(mtimes)

    def register_recorded_segment(self, record: RecordingSegmentRecord) -> None:
        with self._sync_lock:
            index = self._get_index()
            if index is None:
                return
            index.upsert_segment(record)
            cam_dir = self._safe_camera_dir(record.camera_id)
            if cam_dir is not None:
                self._dir_fingerprints[record.camera_id] = self._compute_dir_fingerprint(cam_dir)

    def sync_camera_from_filesystem(self, camera_id: str, *, force: bool = False) -> int:
        with self._sync_lock:
            index = self._get_index()
            cam_dir = self._safe_camera_dir(camera_id)
            if index is None or cam_dir is None:
                return 0

            fingerprint = self._compute_dir_fingerprint(cam_dir)
            if not force and self._dir_fingerprints.get(camera_id) == fingerprint and index.count_camera_segments(camera_id) > 0:
                return 0

            records: list[RecordingSegmentRecord] = []
            existing_by_id = {
                seg.id: seg
                for seg in index.query_range(camera_id, 0.0, 9999999999.0)
            }
            seen_ids: set[str] = set()

            for path in cam_dir.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in (".mp4", ".mkv", ".webm"):
                    continue
                seg = self._parse_file_segment(camera_id, path)
                if seg is None:
                    continue
                seen_ids.add(seg.id)
                prev = existing_by_id.get(seg.id)
                if prev is not None:
                    # Preserva metadati ricchi (es. codec HEVC, larghezza/altezza, timestamp al ms) già indicizzati
                    if prev.size_bytes == seg.size_bytes and prev.start_unix > 0:
                        continue
                records.append(seg)

            if records:
                index.upsert_many(records)

            stale_ids = [
                seg_id
                for seg_id, seg in existing_by_id.items()
                if seg_id not in seen_ids and (seg.file_path is None or not seg.file_path.exists())
            ]
            if stale_ids:
                index.delete_segments(stale_ids)

            self._dir_fingerprints[camera_id] = fingerprint
            return len(records)

    def reconcile_with_filesystem(self, *, force: bool = True) -> dict[str, int]:
        if not self.is_configured or not self._storage_dir:
            return {}
        results: dict[str, int] = {}
        for p in sorted(self._storage_dir.iterdir()):
            if p.is_dir() and _SAFE_SEGMENT_RE.fullmatch(p.name):
                results[p.name] = self.sync_camera_from_filesystem(p.name, force=force)
        return results

    def list_cameras(self) -> list[str]:
        if not self.is_configured or not self._storage_dir:
            return []
        disk_cams = {
            p.name
            for p in self._storage_dir.iterdir()
            if p.is_dir() and _SAFE_SEGMENT_RE.fullmatch(p.name)
        }
        index = self._get_index()
        indexed_cams = set(index.list_cameras()) if index is not None else set()
        return sorted(disk_cams | indexed_cams)

    def query_segments(
        self,
        camera_id: str,
        t_start: float,
        t_end: float,
        *,
        stream_tier: Optional[str] = None,
    ) -> list[RecordingSegmentRecord]:
        if not self.is_configured:
            return []
        index = self._get_index()
        if index is None:
            return []
        self.sync_camera_from_filesystem(camera_id)
        return index.query_range(camera_id, t_start, t_end, stream_tier=stream_tier)

    def resolve_timestamp(
        self,
        camera_id: str,
        timestamp_unix: float,
        *,
        prefer_tier: str = "main",
        allow_hevc: bool = True,
    ) -> PlaybackResolutionRecord:
        if not self.is_configured:
            return PlaybackResolutionRecord(
                available=False,
                camera_id=camera_id,
                requested_unix=timestamp_unix,
                reason="storage_not_configured",
            )
        index = self._get_index()
        if index is None:
            return PlaybackResolutionRecord(
                available=False,
                camera_id=camera_id,
                requested_unix=timestamp_unix,
                reason="storage_not_configured",
            )
        self.sync_camera_from_filesystem(camera_id)
        return index.resolve_at(
            camera_id,
            timestamp_unix,
            prefer_tier=prefer_tier,
            allow_hevc=allow_hevc,
        )

    def resolve_segment_file(self, camera_id: str, filename: str) -> Optional[Path]:
        if not _SAFE_SEGMENT_RE.fullmatch(filename):
            return None
        cam_dir = self._safe_camera_dir(camera_id)
        if cam_dir is None:
            return None

        index = self._get_index()
        if index is not None:
            rec = index.find_by_filename(camera_id, filename)
            if rec is not None and rec.file_path is not None:
                try:
                    resolved = rec.file_path.resolve()
                    if resolved.is_file() and str(resolved).startswith(str(cam_dir)):
                        return resolved
                except OSError:
                    pass

        for path in cam_dir.rglob(filename):
            if path.is_file():
                resolved = path.resolve()
                if str(resolved).startswith(str(cam_dir)):
                    return resolved
        return None

    def list_oldest_segments(
        self,
        *,
        stream_tier: Optional[str] = None,
        older_than_unix: Optional[float] = None,
        limit: int = 200,
    ) -> list[RecordingSegmentRecord]:
        index = self._get_index()
        if index is None:
            return []
        return index.list_oldest_segments(
            stream_tier=stream_tier,
            older_than_unix=older_than_unix,
            limit=limit,
        )

    def delete_indexed_segments(self, segment_ids: list[str]) -> int:
        index = self._get_index()
        if index is None:
            return 0
        return index.delete_segments(segment_ids)

    def get_storage_stats(self) -> dict[str, Any]:
        index = self._get_index()
        if index is None:
            return {
                "configured": False,
                "total_segments": 0,
                "total_bytes": 0,
                "total_gb": 0.0,
                "sub_count": 0,
                "sub_bytes": 0,
                "main_count": 0,
                "main_bytes": 0,
                "by_camera": {},
            }
        stats = index.get_storage_stats()
        stats["configured"] = True
        return stats

    def close(self) -> None:
        with self._index_lock:
            if self._index is not None:
                self._index.close()
                self._index = None
