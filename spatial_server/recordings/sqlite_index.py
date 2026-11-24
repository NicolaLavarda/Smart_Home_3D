from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

from spatial_server.recordings.interfaces import (
    INvrSegmentIndex,
    PlaybackResolutionRecord,
    RecordingSegmentRecord,
)

_HEVC_CODECS = frozenset({"hevc", "h265", "hvc1", "hev1"})


class SQLiteNvrIndexStore(INvrSegmentIndex):
    """Indice SQLite WAL per segmenti NVR Sub/Main con risoluzione al millisecondo e lookahead zero-gap."""

    def __init__(self, db_path: Path, storage_root: Optional[Path] = None) -> None:
        self.db_path = db_path
        self.storage_root = storage_root or db_path.parent
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.execute("PRAGMA temp_store=MEMORY;")
            cur.execute("PRAGMA cache_size=-4000;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS nvr_segments (
                    id TEXT PRIMARY KEY,
                    camera_id TEXT NOT NULL,
                    stream_tier TEXT NOT NULL DEFAULT 'sub',
                    start_unix REAL NOT NULL,
                    end_unix REAL NOT NULL,
                    duration_sec REAL NOT NULL,
                    relative_path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    format TEXT NOT NULL DEFAULT 'mp4',
                    codec TEXT NOT NULL DEFAULT 'h264',
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    has_motion INTEGER NOT NULL DEFAULT 0,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_nvr_cam_span ON nvr_segments(camera_id, start_unix, end_unix);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_nvr_cam_tier_span ON nvr_segments(camera_id, stream_tier, start_unix, end_unix);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_nvr_tier_start ON nvr_segments(stream_tier, start_unix);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_nvr_cam_file ON nvr_segments(camera_id, filename);"
            )
            self._conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> RecordingSegmentRecord:
        rel_path = str(row["relative_path"] or "")
        file_path = (self.storage_root / rel_path) if rel_path else None
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
        camera_id = str(row["camera_id"])
        filename = str(row["filename"])
        return RecordingSegmentRecord(
            id=str(row["id"]),
            camera_id=camera_id,
            start_unix=float(row["start_unix"]),
            end_unix=float(row["end_unix"]),
            stream_url=f"/api/v1/recordings/{camera_id}/file/{filename}",
            format=str(row["format"] or "mp4"),
            storage_type="pc_nvr_hdd",
            has_motion=bool(row["has_motion"]),
            size_bytes=int(row["size_bytes"] or 0),
            file_path=file_path,
            metadata=metadata,
            stream_tier=str(row["stream_tier"] or "sub"),
            codec=str(row["codec"] or "h264"),
            width=int(row["width"] or 0),
            height=int(row["height"] or 0),
            relative_path=rel_path,
        )

    def _resolve_rel_path(self, record: RecordingSegmentRecord) -> str:
        if record.relative_path:
            return record.relative_path.replace("\\", "/")
        if record.file_path is not None:
            try:
                return str(record.file_path.resolve().relative_to(self.storage_root.resolve())).replace("\\", "/")
            except Exception:
                return record.file_path.name
        return f"{record.camera_id}/{Path(record.stream_url).name}"

    def upsert_segment(self, record: RecordingSegmentRecord) -> None:
        self.upsert_many([record])

    def upsert_many(self, records: list[RecordingSegmentRecord]) -> None:
        if not records:
            return
        now_ts = time.time()
        rows: list[tuple[Any, ...]] = []
        for rec in records:
            rel_path = self._resolve_rel_path(rec)
            filename = rec.file_path.name if rec.file_path is not None else Path(rel_path).name
            duration_sec = max(0.0, float(rec.end_unix) - float(rec.start_unix))
            tier = "main" if str(rec.stream_tier).lower() == "main" else "sub"
            rows.append(
                (
                    rec.id,
                    rec.camera_id,
                    tier,
                    float(rec.start_unix),
                    float(rec.end_unix),
                    duration_sec,
                    rel_path,
                    filename,
                    rec.format or "mp4",
                    (rec.codec or "h264").lower(),
                    int(rec.width or 0),
                    int(rec.height or 0),
                    1 if rec.has_motion else 0,
                    int(rec.size_bytes or 0),
                    json.dumps(rec.metadata or {}, ensure_ascii=False),
                    now_ts,
                )
            )
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO nvr_segments (
                    id, camera_id, stream_tier, start_unix, end_unix, duration_sec,
                    relative_path, filename, format, codec, width, height,
                    has_motion, size_bytes, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    stream_tier=excluded.stream_tier,
                    start_unix=excluded.start_unix,
                    end_unix=excluded.end_unix,
                    duration_sec=excluded.duration_sec,
                    relative_path=excluded.relative_path,
                    filename=excluded.filename,
                    format=excluded.format,
                    codec=excluded.codec,
                    width=excluded.width,
                    height=excluded.height,
                    has_motion=excluded.has_motion,
                    size_bytes=excluded.size_bytes,
                    metadata_json=excluded.metadata_json;
                """,
                rows,
            )
            self._conn.commit()

    def delete_segments(self, segment_ids: list[str]) -> int:
        if not segment_ids:
            return 0
        deleted = 0
        with self._lock:
            for idx in range(0, len(segment_ids), 200):
                batch = segment_ids[idx : idx + 200]
                placeholders = ",".join("?" for _ in batch)
                cur = self._conn.execute(
                    f"DELETE FROM nvr_segments WHERE id IN ({placeholders});",
                    batch,
                )
                deleted += int(cur.rowcount or 0)
            self._conn.commit()
        return deleted

    def list_cameras(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT camera_id FROM nvr_segments ORDER BY camera_id ASC;"
            ).fetchall()
        return [str(r["camera_id"]) for r in rows]

    def count_camera_segments(self, camera_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS cnt FROM nvr_segments WHERE camera_id = ?;",
                (camera_id,),
            ).fetchone()
        return int(row["cnt"] if row else 0)

    def query_range(
        self,
        camera_id: str,
        t_start: float,
        t_end: float,
        *,
        stream_tier: Optional[str] = None,
    ) -> list[RecordingSegmentRecord]:
        with self._lock:
            if stream_tier in ("sub", "main"):
                rows = self._conn.execute(
                    """
                    SELECT * FROM nvr_segments
                    WHERE camera_id = ? AND stream_tier = ? AND end_unix >= ? AND start_unix <= ?
                    ORDER BY start_unix ASC, stream_tier DESC;
                    """,
                    (camera_id, stream_tier, float(t_start), float(t_end)),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM nvr_segments
                    WHERE camera_id = ? AND end_unix >= ? AND start_unix <= ?
                    ORDER BY start_unix ASC, stream_tier DESC;
                    """,
                    (camera_id, float(t_start), float(t_end)),
                ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def find_by_filename(self, camera_id: str, filename: str) -> Optional[RecordingSegmentRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM nvr_segments WHERE camera_id = ? AND filename = ? LIMIT 1;",
                (camera_id, filename),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def list_oldest_segments(
        self,
        *,
        stream_tier: Optional[str] = None,
        older_than_unix: Optional[float] = None,
        limit: int = 200,
    ) -> list[RecordingSegmentRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if stream_tier in ("sub", "main"):
            clauses.append("stream_tier = ?")
            params.append(stream_tier)
        if older_than_unix is not None:
            clauses.append("end_unix < ?")
            params.append(float(older_than_unix))
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, int(limit)))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM nvr_segments {where_sql} ORDER BY end_unix ASC, start_unix ASC LIMIT ?;",
                params,
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_storage_stats(self) -> dict[str, Any]:
        with self._lock:
            summary = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS total_segments,
                    COALESCE(SUM(size_bytes), 0) AS total_bytes,
                    COALESCE(SUM(CASE WHEN stream_tier = 'sub' THEN 1 ELSE 0 END), 0) AS sub_count,
                    COALESCE(SUM(CASE WHEN stream_tier = 'sub' THEN size_bytes ELSE 0 END), 0) AS sub_bytes,
                    COALESCE(SUM(CASE WHEN stream_tier = 'main' THEN 1 ELSE 0 END), 0) AS main_count,
                    COALESCE(SUM(CASE WHEN stream_tier = 'main' THEN size_bytes ELSE 0 END), 0) AS main_bytes,
                    MIN(start_unix) AS min_start_unix,
                    MAX(end_unix) AS max_end_unix
                FROM nvr_segments;
                """
            ).fetchone()
            cam_rows = self._conn.execute(
                """
                SELECT
                    camera_id,
                    COUNT(*) AS segments,
                    COALESCE(SUM(size_bytes), 0) AS bytes,
                    COALESCE(SUM(CASE WHEN stream_tier = 'main' THEN 1 ELSE 0 END), 0) AS main_segments
                FROM nvr_segments
                GROUP BY camera_id
                ORDER BY camera_id ASC;
                """
            ).fetchall()

        total_bytes = int(summary["total_bytes"] or 0) if summary else 0
        return {
            "total_segments": int(summary["total_segments"] or 0) if summary else 0,
            "total_bytes": total_bytes,
            "total_gb": round(total_bytes / (1024**3), 3),
            "sub_count": int(summary["sub_count"] or 0) if summary else 0,
            "sub_bytes": int(summary["sub_bytes"] or 0) if summary else 0,
            "main_count": int(summary["main_count"] or 0) if summary else 0,
            "main_bytes": int(summary["main_bytes"] or 0) if summary else 0,
            "min_start_unix": float(summary["min_start_unix"]) if summary and summary["min_start_unix"] is not None else None,
            "max_end_unix": float(summary["max_end_unix"]) if summary and summary["max_end_unix"] is not None else None,
            "by_camera": {
                str(r["camera_id"]): {
                    "segments": int(r["segments"] or 0),
                    "bytes": int(r["bytes"] or 0),
                    "main_segments": int(r["main_segments"] or 0),
                }
                for r in cam_rows
            },
        }

    @staticmethod
    def _is_playable(seg: RecordingSegmentRecord, allow_hevc: bool) -> bool:
        if allow_hevc:
            return True
        return seg.codec.lower() not in _HEVC_CODECS

    def _pick_preferred_segment(
        self,
        segments: list[RecordingSegmentRecord],
        *,
        prefer_tier: str,
        allow_hevc: bool,
    ) -> tuple[Optional[RecordingSegmentRecord], Optional[str]]:
        if not segments:
            return None, None
        playable = [s for s in segments if self._is_playable(s, allow_hevc)]
        fallback_reason: Optional[str] = None
        if not playable:
            return None, "codec_unsupported"

        preferred = [s for s in playable if s.stream_tier == prefer_tier]
        if preferred:
            preferred.sort(key=lambda s: (s.end_unix, s.start_unix), reverse=True)
            return preferred[0], None

        # Se prefer_tier == 'main' ma il main era HEVC non supportato dal client -> fallback automatico su sub H.264
        if prefer_tier == "main" and not allow_hevc:
            had_hevc_main = any(s.stream_tier == "main" and not self._is_playable(s, False) for s in segments)
            if had_hevc_main:
                fallback_reason = "hevc_unsupported_fallback_sub"

        playable.sort(key=lambda s: (1 if s.stream_tier == "sub" else 0, s.end_unix), reverse=True)
        return playable[0], fallback_reason

    def resolve_at(
        self,
        camera_id: str,
        timestamp_unix: float,
        *,
        prefer_tier: str = "main",
        allow_hevc: bool = True,
        lookahead_sec: float = 120.0,
    ) -> PlaybackResolutionRecord:
        t = float(timestamp_unix)
        eff_prefer = "sub" if str(prefer_tier).lower() == "sub" else "main"
        window_end = t + max(5.0, float(lookahead_sec))
        candidates = self.query_range(camera_id, t - 0.5, window_end)

        covering = [s for s in candidates if s.start_unix <= t <= s.end_unix]
        if not covering:
            return PlaybackResolutionRecord(
                available=False,
                camera_id=camera_id,
                requested_unix=t,
                reason="no_recording",
            )

        chosen, fallback_reason = self._pick_preferred_segment(
            covering,
            prefer_tier=eff_prefer,
            allow_hevc=allow_hevc,
        )
        if chosen is None:
            return PlaybackResolutionRecord(
                available=False,
                camera_id=camera_id,
                requested_unix=t,
                reason=fallback_reason or "no_recording",
            )

        playable_all = [s for s in candidates if self._is_playable(s, allow_hevc)]
        effective_end = chosen.end_unix
        next_segment: Optional[RecordingSegmentRecord] = None
        next_seek_offset = 0.0

        # Caso 1: stiamo riproducendo Sub ma poco più avanti inizia una clip Main -> anticipiamo lo switch
        if chosen.stream_tier == "sub" and eff_prefer == "main":
            upcoming_main = [
                s
                for s in playable_all
                if s.stream_tier == "main" and t < s.start_unix < chosen.end_unix
            ]
            if upcoming_main:
                upcoming_main.sort(key=lambda s: s.start_unix)
                next_segment = upcoming_main[0]
                effective_end = next_segment.start_unix
                next_seek_offset = 0.0

        # Caso 2: passaggio alla fine naturale di chosen (Main -> Sub sottostante, Main -> Main rollover, Sub -> Sub)
        if next_segment is None:
            t_handover = chosen.end_unix + 0.02
            handover_covering = [
                s
                for s in playable_all
                if s.id != chosen.id and s.start_unix <= t_handover <= s.end_unix
            ]
            if handover_covering:
                next_segment, _ = self._pick_preferred_segment(
                    handover_covering,
                    prefer_tier=eff_prefer,
                    allow_hevc=allow_hevc,
                )
                if next_segment is not None:
                    next_seek_offset = max(0.0, chosen.end_unix - next_segment.start_unix)
            else:
                contiguous = [
                    s
                    for s in playable_all
                    if s.id != chosen.id and (chosen.end_unix - 0.25) <= s.start_unix <= (chosen.end_unix + 2.0)
                ]
                if contiguous:
                    contiguous.sort(key=lambda s: (0 if s.stream_tier == eff_prefer else 1, s.start_unix))
                    next_segment = contiguous[0]
                    next_seek_offset = max(0.0, chosen.end_unix - next_segment.start_unix)

        switch_at = effective_end if next_segment is not None else None
        return PlaybackResolutionRecord(
            available=True,
            camera_id=camera_id,
            requested_unix=t,
            segment=chosen,
            seek_offset_sec=max(0.0, t - chosen.start_unix),
            reason="ok",
            effective_end_unix=effective_end,
            switch_at_unix=switch_at,
            next_segment=next_segment,
            next_seek_offset_sec=next_seek_offset,
            fallback_reason=fallback_reason,
        )

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
