from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from spatial_server.recordings.filesystem_nvr import FilesystemNvrArchiveRepository
from spatial_server.recordings.interfaces import RecordingSegmentRecord

logger = logging.getLogger("spatial_server.recordings.retention")


@dataclass(frozen=True)
class RetentionSweepReport:
    deleted_sub_count: int = 0
    deleted_main_count: int = 0
    reclaimed_bytes: int = 0
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    archive_used_gb: float = 0.0
    ran_at_unix: float = 0.0


class DiskRetentionManager:
    """Gestore pulizia automatica disco CMR: elimina prima Sub vecchi e preserva le clip Main più a lungo."""

    def __init__(
        self,
        archive: FilesystemNvrArchiveRepository,
        *,
        sub_retention_days: int = 30,
        main_retention_days: int = 60,
        min_free_gb: float = 50.0,
        max_storage_gb: float = 0.0,
    ) -> None:
        self.archive = archive
        self.sub_retention_days = max(1, int(sub_retention_days))
        self.main_retention_days = max(1, int(main_retention_days))
        self.min_free_gb = max(1.0, float(min_free_gb))
        self.max_storage_gb = max(0.0, float(max_storage_gb))

    def _delete_segment_batch(self, segments: list[RecordingSegmentRecord]) -> tuple[int, int, int]:
        deleted_sub = 0
        deleted_main = 0
        reclaimed = 0
        deleted_ids: list[str] = []

        for seg in segments:
            file_bytes = int(seg.size_bytes or 0)
            if seg.file_path is not None and seg.file_path.exists():
                try:
                    file_bytes = seg.file_path.stat().st_size
                    seg.file_path.unlink()
                except OSError as exc:
                    logger.warning("Impossibile eliminare segmento %s: %s", seg.file_path, exc)
                    continue
            deleted_ids.append(seg.id)
            reclaimed += file_bytes
            if seg.stream_tier == "main":
                deleted_main += 1
            else:
                deleted_sub += 1

        if deleted_ids:
            self.archive.delete_indexed_segments(deleted_ids)
        return deleted_sub, deleted_main, reclaimed

    def _cleanup_empty_date_dirs(self, storage_dir: Path) -> None:
        try:
            for cam_dir in storage_dir.iterdir():
                if not cam_dir.is_dir():
                    continue
                for sub_dir in cam_dir.iterdir():
                    if sub_dir.is_dir():
                        try:
                            if not any(sub_dir.iterdir()):
                                sub_dir.rmdir()
                        except OSError:
                            pass
        except OSError:
            pass

    def sweep(self, now_unix: Optional[float] = None) -> RetentionSweepReport:
        now = float(now_unix if now_unix is not None else time.time())
        if not self.archive.is_configured or self.archive.storage_dir is None:
            return RetentionSweepReport(ran_at_unix=now)

        storage_dir = self.archive.storage_dir
        deleted_sub = 0
        deleted_main = 0
        reclaimed = 0

        # 1. Scadenza temporale separata (prima Sub, poi Main)
        sub_cutoff = now - self.sub_retention_days * 86400.0
        while True:
            expired_sub = self.archive.list_oldest_segments(
                stream_tier="sub",
                older_than_unix=sub_cutoff,
                limit=200,
            )
            if not expired_sub:
                break
            ds, dm, rec = self._delete_segment_batch(expired_sub)
            deleted_sub += ds
            deleted_main += dm
            reclaimed += rec
            if ds + dm == 0:
                break

        main_cutoff = now - self.main_retention_days * 86400.0
        while True:
            expired_main = self.archive.list_oldest_segments(
                stream_tier="main",
                older_than_unix=main_cutoff,
                limit=200,
            )
            if not expired_main:
                break
            ds, dm, rec = self._delete_segment_batch(expired_main)
            deleted_sub += ds
            deleted_main += dm
            reclaimed += rec
            if ds + dm == 0:
                break

        # 2. Guardia spazio libero & tetto massimo (sacrifica prima i vecchi Sub, poi i vecchi Main)
        min_free_bytes = int(self.min_free_gb * (1024**3))
        max_storage_bytes = int(self.max_storage_gb * (1024**3)) if self.max_storage_gb > 0 else 0

        for tier in ("sub", "main"):
            while True:
                usage = shutil.disk_usage(storage_dir)
                stats = self.archive.get_storage_stats()
                archive_bytes = int(stats.get("total_bytes", 0))
                need_free = usage.free < min_free_bytes
                over_quota = max_storage_bytes > 0 and archive_bytes > max_storage_bytes
                if not need_free and not over_quota:
                    break
                oldest = self.archive.list_oldest_segments(stream_tier=tier, limit=50)
                if not oldest:
                    break
                ds, dm, rec = self._delete_segment_batch(oldest)
                deleted_sub += ds
                deleted_main += dm
                reclaimed += rec
                if ds + dm == 0:
                    break

        self._cleanup_empty_date_dirs(storage_dir)
        final_usage = shutil.disk_usage(storage_dir)
        final_stats = self.archive.get_storage_stats()
        return RetentionSweepReport(
            deleted_sub_count=deleted_sub,
            deleted_main_count=deleted_main,
            reclaimed_bytes=reclaimed,
            disk_total_gb=round(final_usage.total / (1024**3), 2),
            disk_free_gb=round(final_usage.free / (1024**3), 2),
            archive_used_gb=round(float(final_stats.get("total_bytes", 0)) / (1024**3), 3),
            ran_at_unix=now,
        )
