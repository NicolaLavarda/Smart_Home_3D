from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from spatial_server.domain.models import TrackedEntity3D
from .interfaces import ITrackRepository


class SQLiteWALTrackRepository(ITrackRepository):
    """
    SQLite3 time-series & spatial repository optimized for low-RAM Windows 10 hosts:
    - PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
    - Optional R-Tree virtual index (`track_spatial_idx`) for bounding-box queries
    - Thread-safe connection lock + transactional batch writes
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.has_rtree = False
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
                CREATE TABLE IF NOT EXISTS track_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_id INTEGER NOT NULL,
                    timestamp REAL NOT NULL,
                    class_label TEXT NOT NULL,
                    identity TEXT,
                    identity_confidence REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.9,
                    x REAL NOT NULL,
                    y REAL NOT NULL,
                    z REAL NOT NULL,
                    vx REAL DEFAULT 0.0,
                    vy REAL DEFAULT 0.0,
                    vz REAL DEFAULT 0.0,
                    camera_sources TEXT NOT NULL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_track_ts ON track_history(timestamp, track_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_track_class_ts ON track_history(class_label, timestamp);")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS identities (
                    name TEXT PRIMARY KEY,
                    embedding_blob BLOB,
                    updated_at REAL NOT NULL,
                    notes TEXT
                );
                """
            )

            try:
                cur.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS track_spatial_idx USING rtree(
                        id,
                        min_x, max_x,
                        min_z, max_z
                    );
                    """
                )
                self.has_rtree = True
            except sqlite3.OperationalError:
                self.has_rtree = False
                cur.execute("CREATE INDEX IF NOT EXISTS idx_track_xz ON track_history(x, z);")

            self._conn.commit()

    def get_journal_mode(self) -> str:
        with self._lock:
            row = self._conn.execute("PRAGMA journal_mode;").fetchone()
            return str(row[0]).lower() if row else "unknown"

    def append_batch(self, entities: list[TrackedEntity3D]) -> int:
        if not entities:
            return 0

        with self._lock:
            cur = self._conn.cursor()
            inserted = 0
            try:
                cur.execute("BEGIN;")
                for ent in entities:
                    st = ent.state
                    cur.execute(
                        """
                        INSERT INTO track_history (
                            track_id, timestamp, class_label, identity, identity_confidence,
                            confidence, x, y, z, vx, vy, vz, camera_sources
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            ent.track_id,
                            ent.last_seen,
                            ent.class_label,
                            ent.identity,
                            ent.identity_confidence,
                            ent.confidence,
                            st.x,
                            st.y,
                            st.z,
                            st.vx,
                            st.vy,
                            st.vz,
                            json.dumps(st.camera_sources),
                        ),
                    )
                    if self.has_rtree and cur.lastrowid is not None:
                        pad = 0.25
                        cur.execute(
                            "INSERT OR REPLACE INTO track_spatial_idx (id, min_x, max_x, min_z, max_z) VALUES (?, ?, ?, ?, ?);",
                            (cur.lastrowid, st.x - pad, st.x + pad, st.z - pad, st.z + pad),
                        )
                    inserted += 1
                self._conn.commit()
                return inserted
            except Exception:
                self._conn.rollback()
                raise

    def query_time_range(
        self,
        t_start: float,
        t_end: float,
        classes: Optional[list[str]] = None,
        zone_bbox: Optional[tuple[float, float, float, float]] = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [float(t_start), float(t_end)]

        if zone_bbox is not None and self.has_rtree:
            min_x, max_x, min_z, max_z = zone_bbox
            sql = """
                SELECT th.*
                FROM track_history th
                INNER JOIN track_spatial_idx r ON r.id = th.id
                WHERE th.timestamp >= ? AND th.timestamp <= ?
                  AND r.max_x >= ? AND r.min_x <= ?
                  AND r.max_z >= ? AND r.min_z <= ?
            """
            params.extend([min_x, max_x, min_z, max_z])
        else:
            sql = """
                SELECT th.*
                FROM track_history th
                WHERE th.timestamp >= ? AND th.timestamp <= ?
            """
            if zone_bbox is not None:
                min_x, max_x, min_z, max_z = zone_bbox
                sql += " AND th.x BETWEEN ? AND ? AND th.z BETWEEN ? AND ?"
                params.extend([min_x, max_x, min_z, max_z])

        if classes:
            placeholders = ",".join("?" for _ in classes)
            sql += f" AND th.class_label IN ({placeholders})"
            params.extend(classes)

        sql += " ORDER BY th.timestamp ASC LIMIT ?;"
        params.append(int(limit))

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            results.append(
                {
                    "id": r["id"],
                    "track_id": r["track_id"],
                    "timestamp": r["timestamp"],
                    "class_label": r["class_label"],
                    "identity": r["identity"],
                    "identity_confidence": r["identity_confidence"],
                    "confidence": r["confidence"],
                    "x": r["x"],
                    "y": r["y"],
                    "z": r["z"],
                    "vx": r["vx"],
                    "vy": r["vy"],
                    "vz": r["vz"],
                    "camera_sources": json.loads(r["camera_sources"]),
                }
            )
        return results

    def query_timeline_density(self, t_start: float, t_end: float, buckets: int = 60) -> list[dict[str, Any]]:
        buckets = max(1, min(int(buckets), 360))
        start_f = float(t_start)
        end_f = float(t_end)
        span = max(end_f - start_f, 1.0)
        step = span / buckets
        counts = [0] * buckets

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT CAST((timestamp - ?) / ? AS INTEGER) AS bucket_idx, COUNT(*) AS cnt
                FROM track_history
                WHERE timestamp >= ? AND timestamp <= ?
                GROUP BY bucket_idx;
                """,
                (start_f, step, start_f, end_f),
            ).fetchall()

        for row in rows:
            idx = int(row[0])
            if idx == buckets:
                idx = buckets - 1
            if 0 <= idx < buckets:
                counts[idx] += int(row[1])

        return [
            {
                "bucket": i,
                "t_start": start_f + i * step,
                "t_end": start_f + (i + 1) * step,
                "count": counts[i],
            }
            for i in range(buckets)
        ]

    def prune_older_than(self, cutoff_timestamp: float) -> int:
        with self._lock:
            cur = self._conn.cursor()
            if self.has_rtree:
                cur.execute(
                    "DELETE FROM track_spatial_idx WHERE id IN (SELECT id FROM track_history WHERE timestamp < ?);",
                    (float(cutoff_timestamp),),
                )
            cur.execute("DELETE FROM track_history WHERE timestamp < ?;", (float(cutoff_timestamp),))
            deleted = cur.rowcount or 0
            self._conn.commit()
            if deleted > 0:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            return int(deleted)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

