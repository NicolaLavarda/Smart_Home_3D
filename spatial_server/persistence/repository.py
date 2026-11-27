from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
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

            existing_cols = {
                str(row["name"]).lower()
                for row in cur.execute("PRAGMA table_info(track_history);").fetchall()
            }
            for col_name, col_def in (
                ("plate", "TEXT"),
                ("plate_confidence", "REAL DEFAULT 0.0"),
                ("plate_whitelisted", "INTEGER"),
                ("plate_owner", "TEXT"),
                ("biometric_locked", "INTEGER DEFAULT 0"),
                ("best_crop_id", "TEXT"),
            ):
                if col_name not in existing_cols:
                    cur.execute(f"ALTER TABLE track_history ADD COLUMN {col_name} {col_def};")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_track_identity_ts ON track_history(identity, timestamp);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_track_plate_ts ON track_history(plate, timestamp);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_track_id_ts ON track_history(track_id, timestamp);")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS biometric_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_id INTEGER NOT NULL,
                    modality TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    identity TEXT,
                    identity_confidence REAL DEFAULT 0.0,
                    plate TEXT,
                    plate_raw TEXT,
                    plate_confidence REAL DEFAULT 0.0,
                    plate_format TEXT,
                    plate_whitelisted INTEGER,
                    plate_owner TEXT,
                    biometric_locked INTEGER DEFAULT 0,
                    biometric_status TEXT NOT NULL,
                    attempts_count INTEGER DEFAULT 0,
                    quality_score REAL DEFAULT 0.0,
                    best_crop_id TEXT,
                    best_crop_relpath TEXT,
                    reviewed_by TEXT,
                    reviewed_at REAL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bio_events_ts ON biometric_events(timestamp DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bio_events_track_mod ON biometric_events(track_id, modality);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bio_events_crop ON biometric_events(best_crop_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bio_events_identity ON biometric_events(identity, timestamp DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_bio_events_plate ON biometric_events(plate, timestamp DESC);")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS face_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person_name TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    embedding_blob BLOB NOT NULL,
                    quality_score REAL DEFAULT 0.0,
                    source TEXT DEFAULT 'enroll',
                    created_at REAL NOT NULL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_face_emb_person ON face_embeddings(person_name);")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS plate_whitelist (
                    plate TEXT PRIMARY KEY,
                    owner_name TEXT NOT NULL,
                    vehicle_label TEXT,
                    notes TEXT,
                    updated_at REAL NOT NULL
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS spatial_zones (
                    zone_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    geometry_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS virtual_entities (
                    entity_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_rules (
                    rule_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_summary TEXT NOT NULL,
                    track_id INTEGER,
                    identity TEXT,
                    plate TEXT,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_auto_logs_ts ON automation_logs(timestamp DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_auto_logs_rule ON automation_logs(rule_id, timestamp DESC);")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scene_events (
                    event_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL NOT NULL,
                    importance TEXT NOT NULL,
                    best_camera_id TEXT,
                    cameras_json TEXT NOT NULL DEFAULT '[]',
                    zones_json TEXT NOT NULL DEFAULT '[]',
                    zone_ids_json TEXT NOT NULL DEFAULT '[]',
                    track_ids_json TEXT NOT NULL DEFAULT '[]',
                    identities_text TEXT NOT NULL DEFAULT '',
                    plates_text TEXT NOT NULL DEFAULT '',
                    classes_text TEXT NOT NULL DEFAULT '',
                    has_unknown_person INTEGER NOT NULL DEFAULT 0,
                    cover_raw_relpath TEXT,
                    cover_ann_relpath TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_scene_events_started ON scene_events(started_at DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_scene_events_importance ON scene_events(importance, started_at DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_scene_events_status ON scene_events(status, ended_at DESC);")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS system_metrics_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    cpu_pct REAL NOT NULL,
                    gpu_pct REAL,
                    gpu_mem_mb REAL,
                    ram_pct REAL NOT NULL,
                    ram_used_mb REAL NOT NULL,
                    proc_cpu_pct REAL NOT NULL,
                    proc_rss_mb REAL NOT NULL,
                    cv_fps_total REAL NOT NULL,
                    cv_fps_target REAL NOT NULL,
                    cv_fps_person REAL NOT NULL,
                    cv_fps_vehicle REAL NOT NULL,
                    cv_fps_idle REAL NOT NULL,
                    cv_read_fps REAL NOT NULL,
                    cv_infer_ms REAL NOT NULL,
                    cv_infer_ms_max REAL NOT NULL,
                    person_det_fps REAL NOT NULL,
                    vehicle_det_fps REAL NOT NULL,
                    animal_det_fps REAL NOT NULL,
                    bio_fps REAL NOT NULL,
                    bio_face_ms REAL NOT NULL,
                    bio_alpr_ms REAL NOT NULL,
                    bio_queue REAL NOT NULL,
                    tracks_total REAL NOT NULL,
                    tracks_person REAL NOT NULL,
                    tracks_vehicle REAL NOT NULL,
                    tracks_animal REAL NOT NULL,
                    nvr_ram_mb REAL NOT NULL,
                    ws_clients REAL NOT NULL,
                    cameras_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_sys_metrics_ts ON system_metrics_history(timestamp);")

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
                    plate_wl_int = None if ent.plate_whitelisted is None else (1 if ent.plate_whitelisted else 0)
                    locked_int = 1 if ent.biometric_locked else 0
                    cur.execute(
                        """
                        INSERT INTO track_history (
                            track_id, timestamp, class_label, identity, identity_confidence,
                            confidence, x, y, z, vx, vy, vz, camera_sources,
                            plate, plate_confidence, plate_whitelisted, plate_owner, biometric_locked, best_crop_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                            ent.plate,
                            float(ent.plate_confidence or 0.0),
                            plate_wl_int,
                            ent.plate_owner,
                            locked_int,
                            ent.best_crop_id,
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
        identity: Optional[str] = None,
        plate: Optional[str] = None,
        unknown_only: bool = False,
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

        if identity and identity.strip():
            sql += " AND LOWER(COALESCE(th.identity, '')) = LOWER(?)"
            params.append(identity.strip())

        if plate and plate.strip():
            clean_plate = re.sub(r"[^A-Z0-9]", "", plate.upper())
            if clean_plate:
                sql += " AND UPPER(COALESCE(th.plate, '')) LIKE ?"
                params.append(f"%{clean_plate}%")

        if unknown_only:
            sql += " AND (th.identity IS NULL OR th.identity = '') AND (th.plate IS NULL OR th.plate = '')"

        sql += " ORDER BY th.timestamp ASC LIMIT ?;"
        params.append(int(limit))

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            raw_wl = r["plate_whitelisted"]
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
                    "plate": r["plate"],
                    "plate_confidence": float(r["plate_confidence"] or 0.0),
                    "plate_whitelisted": None if raw_wl is None else bool(raw_wl),
                    "plate_owner": r["plate_owner"],
                    "biometric_locked": bool(r["biometric_locked"]) if r["biometric_locked"] is not None else False,
                    "best_crop_id": r["best_crop_id"],
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

    def get_max_track_id(self) -> int:
        with self._lock:
            row1 = self._conn.execute("SELECT COALESCE(MAX(track_id), 0) AS m FROM track_history;").fetchone()
            row2 = self._conn.execute("SELECT COALESCE(MAX(track_id), 0) AS m FROM biometric_events;").fetchone()
            return max(int(row1[0] or 0), int(row2[0] or 0))

    def backfill_track_biometrics(
        self,
        track_id: int,
        *,
        min_timestamp: float,
        identity: Optional[str] = None,
        identity_confidence: Optional[float] = None,
        plate: Optional[str] = None,
        plate_confidence: Optional[float] = None,
        plate_whitelisted: Optional[bool] = None,
        plate_owner: Optional[str] = None,
        biometric_locked: Optional[bool] = None,
        best_crop_id: Optional[str] = None,
    ) -> int:
        sets: list[str] = []
        params: list[Any] = []
        if identity is not None:
            sets.append("identity = ?")
            params.append(identity)
        if identity_confidence is not None:
            sets.append("identity_confidence = ?")
            params.append(float(identity_confidence))
        if plate is not None:
            sets.append("plate = ?")
            params.append(plate)
        if plate_confidence is not None:
            sets.append("plate_confidence = ?")
            params.append(float(plate_confidence))
        if plate_whitelisted is not None:
            sets.append("plate_whitelisted = ?")
            params.append(1 if plate_whitelisted else 0)
        if plate_owner is not None:
            sets.append("plate_owner = ?")
            params.append(plate_owner)
        if biometric_locked is not None:
            sets.append("biometric_locked = ?")
            params.append(1 if biometric_locked else 0)
        if best_crop_id is not None:
            sets.append("best_crop_id = ?")
            params.append(best_crop_id)

        if not sets:
            return 0

        sql = f"UPDATE track_history SET {', '.join(sets)} WHERE track_id = ? AND timestamp >= ?;"
        params.extend([int(track_id), float(min_timestamp)])

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            self._conn.commit()
            return int(cur.rowcount or 0)

    @staticmethod
    def _row_to_biometric_event(r: sqlite3.Row) -> dict[str, Any]:
        raw_wl = r["plate_whitelisted"]
        return {
            "id": int(r["id"]),
            "track_id": int(r["track_id"]),
            "modality": str(r["modality"]),
            "camera_id": str(r["camera_id"]),
            "timestamp": float(r["timestamp"]),
            "identity": r["identity"],
            "identity_confidence": float(r["identity_confidence"] or 0.0),
            "plate": r["plate"],
            "plate_raw": r["plate_raw"],
            "plate_confidence": float(r["plate_confidence"] or 0.0),
            "plate_format": r["plate_format"],
            "plate_whitelisted": None if raw_wl is None else bool(raw_wl),
            "plate_owner": r["plate_owner"],
            "biometric_locked": bool(r["biometric_locked"]) if r["biometric_locked"] is not None else False,
            "biometric_status": str(r["biometric_status"]),
            "attempts_count": int(r["attempts_count"] or 0),
            "quality_score": float(r["quality_score"] or 0.0),
            "best_crop_id": r["best_crop_id"],
            "best_crop_relpath": r["best_crop_relpath"],
            "reviewed_by": r["reviewed_by"],
            "reviewed_at": r["reviewed_at"],
        }

    def record_biometric_event(self, event: dict[str, Any]) -> int:
        track_id = int(event["track_id"])
        modality = str(event["modality"])
        camera_id = str(event["camera_id"])
        ts = float(event["timestamp"])
        inc_wl = event.get("plate_whitelisted")
        inc_wl_int = None if inc_wl is None else (1 if inc_wl else 0)
        inc_locked = 1 if event.get("biometric_locked") else 0

        with self._lock:
            cur = self._conn.cursor()
            existing = cur.execute(
                """
                SELECT * FROM biometric_events
                WHERE track_id = ? AND modality = ?
                ORDER BY id DESC LIMIT 1;
                """,
                (track_id, modality),
            ).fetchone()

            if existing is not None and abs(float(existing["timestamp"]) - ts) <= 3600.0:
                was_locked = bool(existing["biometric_locked"])
                if was_locked and not inc_locked:
                    identity = existing["identity"]
                    id_conf = float(existing["identity_confidence"] or 0.0)
                    plate = existing["plate"]
                    plate_raw = existing["plate_raw"]
                    plate_conf = float(existing["plate_confidence"] or 0.0)
                    plate_format = existing["plate_format"]
                    plate_wl_int = existing["plate_whitelisted"]
                    plate_owner = existing["plate_owner"]
                    eff_locked = 1
                    status = str(existing["biometric_status"])
                else:
                    identity = event.get("identity") if event.get("identity") is not None else existing["identity"]
                    id_conf = float(event.get("identity_confidence") or existing["identity_confidence"] or 0.0)
                    plate = event.get("plate") if event.get("plate") is not None else existing["plate"]
                    plate_raw = event.get("plate_raw") if event.get("plate_raw") is not None else existing["plate_raw"]
                    plate_conf = float(event.get("plate_confidence") or existing["plate_confidence"] or 0.0)
                    plate_format = event.get("plate_format") if event.get("plate_format") is not None else existing["plate_format"]
                    plate_wl_int = inc_wl_int if inc_wl is not None else existing["plate_whitelisted"]
                    plate_owner = event.get("plate_owner") if event.get("plate_owner") is not None else existing["plate_owner"]
                    eff_locked = 1 if (was_locked or inc_locked) else 0
                    status = str(event.get("biometric_status") or existing["biometric_status"])

                crop_id = event.get("best_crop_id") or existing["best_crop_id"]
                crop_rel = event.get("best_crop_relpath") or existing["best_crop_relpath"]
                attempts = max(int(existing["attempts_count"] or 0), int(event.get("attempts_count") or 0))
                quality = max(float(existing["quality_score"] or 0.0), float(event.get("quality_score") or 0.0))

                cur.execute(
                    """
                    UPDATE biometric_events
                    SET camera_id = ?, timestamp = ?, identity = ?, identity_confidence = ?,
                        plate = ?, plate_raw = ?, plate_confidence = ?, plate_format = ?,
                        plate_whitelisted = ?, plate_owner = ?, biometric_locked = ?,
                        biometric_status = ?, attempts_count = ?, quality_score = ?,
                        best_crop_id = ?, best_crop_relpath = ?
                    WHERE id = ?;
                    """,
                    (
                        camera_id,
                        max(float(existing["timestamp"]), ts),
                        identity,
                        id_conf,
                        plate,
                        plate_raw,
                        plate_conf,
                        plate_format,
                        plate_wl_int,
                        plate_owner,
                        eff_locked,
                        status,
                        attempts,
                        quality,
                        crop_id,
                        crop_rel,
                        int(existing["id"]),
                    ),
                )
                self._conn.commit()
                return int(existing["id"])

            cur.execute(
                """
                INSERT INTO biometric_events (
                    track_id, modality, camera_id, timestamp, identity, identity_confidence,
                    plate, plate_raw, plate_confidence, plate_format, plate_whitelisted,
                    plate_owner, biometric_locked, biometric_status, attempts_count,
                    quality_score, best_crop_id, best_crop_relpath, reviewed_by, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    track_id,
                    modality,
                    camera_id,
                    ts,
                    event.get("identity"),
                    float(event.get("identity_confidence") or 0.0),
                    event.get("plate"),
                    event.get("plate_raw"),
                    float(event.get("plate_confidence") or 0.0),
                    event.get("plate_format"),
                    inc_wl_int,
                    event.get("plate_owner"),
                    inc_locked,
                    str(event.get("biometric_status") or "pending"),
                    int(event.get("attempts_count") or 0),
                    float(event.get("quality_score") or 0.0),
                    event.get("best_crop_id"),
                    event.get("best_crop_relpath"),
                    event.get("reviewed_by"),
                    event.get("reviewed_at"),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def query_biometric_events(
        self,
        t_start: Optional[float] = None,
        t_end: Optional[float] = None,
        *,
        modality: Optional[str] = None,
        status: Optional[str] = None,
        identity: Optional[str] = None,
        plate: Optional[str] = None,
        track_id: Optional[int] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM biometric_events WHERE 1=1"
        params: list[Any] = []
        if t_start is not None:
            sql += " AND timestamp >= ?"
            params.append(float(t_start))
        if t_end is not None:
            sql += " AND timestamp <= ?"
            params.append(float(t_end))
        if modality and modality.strip():
            sql += " AND modality = ?"
            params.append(modality.strip().lower())
        if status and status.strip():
            sql += " AND biometric_status = ?"
            params.append(status.strip().lower())
        if identity and identity.strip():
            sql += " AND LOWER(COALESCE(identity, '')) = LOWER(?)"
            params.append(identity.strip())
        if plate and plate.strip():
            clean_plate = re.sub(r"[^A-Z0-9]", "", plate.upper())
            if clean_plate:
                sql += " AND UPPER(COALESCE(plate, '')) LIKE ?"
                params.append(f"%{clean_plate}%")
        if track_id is not None:
            sql += " AND track_id = ?"
            params.append(int(track_id))

        eff_limit = max(1, min(int(limit), 1000))
        sql += " ORDER BY timestamp DESC, id DESC LIMIT ?;"
        params.append(eff_limit)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_biometric_event(r) for r in rows]

    def get_biometric_event(self, event_id: int) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM biometric_events WHERE id = ?;",
                (int(event_id),),
            ).fetchone()
        return self._row_to_biometric_event(row) if row is not None else None

    def get_crop_relpath(self, crop_id: str) -> Optional[str]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT best_crop_relpath FROM biometric_events
                WHERE best_crop_id = ? AND best_crop_relpath IS NOT NULL
                ORDER BY id DESC LIMIT 1;
                """,
                (crop_id,),
            ).fetchone()
        return str(row["best_crop_relpath"]) if row is not None else None

    def prune_biometric_events_older_than(self, cutoff_timestamp: float) -> tuple[int, list[str]]:
        cutoff_f = float(cutoff_timestamp)
        with self._lock:
            cur = self._conn.cursor()
            rel_rows = cur.execute(
                """
                SELECT DISTINCT best_crop_relpath FROM biometric_events
                WHERE timestamp < ? AND best_crop_relpath IS NOT NULL;
                """,
                (cutoff_f,),
            ).fetchall()
            relpaths = [str(r[0]) for r in rel_rows if r[0]]
            cur.execute("DELETE FROM biometric_events WHERE timestamp < ?;", (cutoff_f,))
            deleted = int(cur.rowcount or 0)
            self._conn.commit()
            if deleted > 0:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            return deleted, relpaths

    def list_plate_whitelist(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT plate, owner_name, vehicle_label, notes, updated_at FROM plate_whitelist ORDER BY plate ASC;"
            ).fetchall()
        return [
            {
                "plate": str(r["plate"]),
                "owner_name": str(r["owner_name"]),
                "vehicle_label": r["vehicle_label"],
                "notes": r["notes"],
                "updated_at": float(r["updated_at"]),
            }
            for r in rows
        ]

    def upsert_plate_whitelist(
        self,
        plate: str,
        owner_name: str,
        vehicle_label: Optional[str] = None,
        notes: Optional[str] = None,
        updated_at: Optional[float] = None,
    ) -> dict[str, Any]:
        key = re.sub(r"[^A-Z0-9]", "", (plate or "").upper())
        clean_owner = (owner_name or "").strip()
        if len(key) < 4 or not clean_owner:
            raise ValueError(f"Invalid whitelist entry: plate={plate!r}, owner_name={owner_name!r}")
        v_label = vehicle_label.strip() if isinstance(vehicle_label, str) and vehicle_label.strip() else None
        clean_notes = notes.strip() if isinstance(notes, str) and notes.strip() else None
        ts = float(updated_at if updated_at is not None else time.time())

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO plate_whitelist (plate, owner_name, vehicle_label, notes, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(plate) DO UPDATE SET
                    owner_name = excluded.owner_name,
                    vehicle_label = excluded.vehicle_label,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at;
                """,
                (key, clean_owner, v_label, clean_notes, ts),
            )
            self._conn.commit()
        return {
            "plate": key,
            "owner_name": clean_owner,
            "vehicle_label": v_label,
            "notes": clean_notes,
            "updated_at": ts,
        }

    def delete_plate_whitelist(self, plate: str) -> bool:
        key = re.sub(r"[^A-Z0-9]", "", (plate or "").upper())
        if not key:
            return False
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM plate_whitelist WHERE plate = ?;", (key,))
            self._conn.commit()
            return bool(cur.rowcount and cur.rowcount > 0)

    def list_face_identities_meta(self) -> list[dict[str, Any]]:
        with self._lock:
            emb_rows = self._conn.execute(
                """
                SELECT person_name, COUNT(*) AS emb_count, MAX(created_at) AS emb_updated_at
                FROM face_embeddings
                GROUP BY LOWER(person_name);
                """
            ).fetchall()
            ev_rows = self._conn.execute(
                """
                SELECT identity, COUNT(*) AS events_count, MAX(timestamp) AS last_seen
                FROM biometric_events
                WHERE modality = 'face' AND identity IS NOT NULL AND identity != ''
                GROUP BY LOWER(identity);
                """
            ).fetchall()

        merged: dict[str, dict[str, Any]] = {}
        for r in emb_rows:
            name = str(r["person_name"])
            merged[name.lower()] = {
                "name": name,
                "samples_count": int(r["emb_count"] or 0),
                "events_count": 0,
                "last_seen": None,
                "updated_at": r["emb_updated_at"],
            }
        for r in ev_rows:
            name = str(r["identity"])
            key = name.lower()
            entry = merged.setdefault(
                key,
                {
                    "name": name,
                    "samples_count": 0,
                    "events_count": 0,
                    "last_seen": None,
                    "updated_at": None,
                },
            )
            entry["events_count"] = int(r["events_count"] or 0)
            entry["last_seen"] = float(r["last_seen"]) if r["last_seen"] is not None else None
        return sorted(merged.values(), key=lambda x: str(x["name"]).lower())

    def update_biometric_event_review(
        self,
        event_id: int,
        *,
        identity: Optional[str] = None,
        identity_confidence: Optional[float] = None,
        plate: Optional[str] = None,
        plate_confidence: Optional[float] = None,
        plate_whitelisted: Optional[bool] = None,
        plate_owner: Optional[str] = None,
        biometric_locked: Optional[bool] = None,
        biometric_status: Optional[str] = None,
        reviewed_by: Optional[str] = None,
        reviewed_at: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        sets: list[str] = []
        params: list[Any] = []
        if identity is not None:
            sets.append("identity = ?")
            params.append(identity)
        if identity_confidence is not None:
            sets.append("identity_confidence = ?")
            params.append(float(identity_confidence))
        if plate is not None:
            sets.append("plate = ?")
            params.append(plate)
        if plate_confidence is not None:
            sets.append("plate_confidence = ?")
            params.append(float(plate_confidence))
        if plate_whitelisted is not None:
            sets.append("plate_whitelisted = ?")
            params.append(1 if plate_whitelisted else 0)
        if plate_owner is not None:
            sets.append("plate_owner = ?")
            params.append(plate_owner)
        if biometric_locked is not None:
            sets.append("biometric_locked = ?")
            params.append(1 if biometric_locked else 0)
        if biometric_status is not None:
            sets.append("biometric_status = ?")
            params.append(str(biometric_status))
        if reviewed_by is not None:
            sets.append("reviewed_by = ?")
            params.append(reviewed_by)
            sets.append("reviewed_at = ?")
            params.append(float(reviewed_at if reviewed_at is not None else time.time()))
        elif reviewed_at is not None:
            sets.append("reviewed_at = ?")
            params.append(float(reviewed_at))

        with self._lock:
            existing = self._conn.execute(
                "SELECT * FROM biometric_events WHERE id = ?;",
                (int(event_id),),
            ).fetchone()
            if existing is None:
                return None

            if sets:
                sql = f"UPDATE biometric_events SET {', '.join(sets)} WHERE id = ?;"
                params.append(int(event_id))
                self._conn.execute(sql, params)
                self._conn.commit()
                updated = self._conn.execute(
                    "SELECT * FROM biometric_events WHERE id = ?;",
                    (int(event_id),),
                ).fetchone()
                return self._row_to_biometric_event(updated) if updated is not None else None
            return self._row_to_biometric_event(existing)

    def add_face_embedding(
        self,
        person_name: str,
        model_name: str,
        embedding_blob: bytes,
        *,
        quality_score: float = 0.0,
        source: str = "hitl",
        created_at: Optional[float] = None,
    ) -> int:
        clean_name = (person_name or "").strip()
        if not clean_name or not embedding_blob:
            raise ValueError("person_name and non-empty embedding_blob are required")
        ts = float(created_at if created_at is not None else time.time())
        clean_model = (model_name or "w600k_mbf.onnx").strip() or "w600k_mbf.onnx"
        clean_source = (source or "hitl").strip() or "hitl"
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO face_embeddings (person_name, model_name, embedding_blob, quality_score, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (clean_name, clean_model, sqlite3.Binary(embedding_blob), float(quality_score), clean_source, ts),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def delete_face_embeddings(self, person_name: str) -> int:
        clean_name = (person_name or "").strip()
        if not clean_name:
            return 0
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM face_embeddings WHERE LOWER(person_name) = LOWER(?);", (clean_name,))
            self._conn.commit()
            return int(cur.rowcount or 0)

    # --- Spatial Automations, Zones & Virtual Entities Persistence ---

    def list_spatial_zones(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM spatial_zones ORDER BY LOWER(name) ASC;"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            try:
                result.append(json.loads(r["payload_json"]))
            except Exception:
                continue
        return result

    def upsert_spatial_zone(self, zone: dict[str, Any]) -> dict[str, Any]:
        zone_id = str(zone.get("zone_id") or "").strip()
        name = str(zone.get("name") or zone_id).strip()
        gtype = str(zone.get("geometry_type") or "polygon").strip()
        ts = float(zone.get("updated_at") or time.time())
        payload = json.dumps(zone)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO spatial_zones (zone_id, name, geometry_type, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(zone_id) DO UPDATE SET
                    name = excluded.name,
                    geometry_type = excluded.geometry_type,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at;
                """,
                (zone_id, name, gtype, payload, ts),
            )
            self._conn.commit()
        return zone

    def delete_spatial_zone(self, zone_id: str) -> bool:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM spatial_zones WHERE zone_id = ?;", (zone_id,))
            self._conn.commit()
            return bool(cur.rowcount and cur.rowcount > 0)

    def list_virtual_entities(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM virtual_entities ORDER BY entity_id ASC;"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            try:
                result.append(json.loads(r["payload_json"]))
            except Exception:
                continue
        return result

    def upsert_virtual_entity(self, entity: dict[str, Any]) -> dict[str, Any]:
        eid = str(entity.get("entity_id") or "").strip()
        name = str(entity.get("name") or eid).strip()
        domain = str(entity.get("domain") or "switch").strip()
        state = str(entity.get("state") or "off")
        ts = float(entity.get("updated_at") or time.time())
        payload = json.dumps(entity)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO virtual_entities (entity_id, name, domain, state, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    name = excluded.name,
                    domain = excluded.domain,
                    state = excluded.state,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at;
                """,
                (eid, name, domain, state, payload, ts),
            )
            self._conn.commit()
        return entity

    def delete_virtual_entity(self, entity_id: str) -> bool:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM virtual_entities WHERE entity_id = ?;", (entity_id,))
            self._conn.commit()
            return bool(cur.rowcount and cur.rowcount > 0)

    def list_automation_rules(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM automation_rules ORDER BY LOWER(name) ASC;"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            try:
                result.append(json.loads(r["payload_json"]))
            except Exception:
                continue
        return result

    def upsert_automation_rule(self, rule: dict[str, Any]) -> dict[str, Any]:
        rule_id = str(rule.get("rule_id") or "").strip()
        name = str(rule.get("name") or rule_id).strip()
        enabled_int = 1 if rule.get("enabled", True) else 0
        ts = float(rule.get("updated_at") or time.time())
        payload = json.dumps(rule)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO automation_rules (rule_id, name, enabled, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(rule_id) DO UPDATE SET
                    name = excluded.name,
                    enabled = excluded.enabled,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at;
                """,
                (rule_id, name, enabled_int, payload, ts),
            )
            self._conn.commit()
        return rule

    def delete_automation_rule(self, rule_id: str) -> bool:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM automation_rules WHERE rule_id = ?;", (rule_id,))
            self._conn.commit()
            return bool(cur.rowcount and cur.rowcount > 0)

    def record_automation_log(self, log_entry: dict[str, Any]) -> int:
        rule_id = str(log_entry.get("rule_id") or "")
        rule_name = str(log_entry.get("rule_name") or rule_id)
        ts = float(log_entry.get("timestamp") or time.time())
        trig_type = str(log_entry.get("trigger_type") or "")
        trig_sum = str(log_entry.get("trigger_summary") or "")
        track_id = log_entry.get("track_id")
        identity = log_entry.get("identity")
        plate = log_entry.get("plate")
        status = str(log_entry.get("status") or "executed")
        payload = json.dumps(log_entry)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO automation_logs (
                    rule_id, rule_name, timestamp, trigger_type, trigger_summary,
                    track_id, identity, plate, status, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (rule_id, rule_name, ts, trig_type, trig_sum, track_id, identity, plate, status, payload),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def query_automation_logs(
        self,
        *,
        rule_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        eff_limit = max(1, min(int(limit), 500))
        sql = "SELECT id, payload_json FROM automation_logs WHERE 1=1"
        params: list[Any] = []
        if rule_id and rule_id.strip():
            sql += " AND rule_id = ?"
            params.append(rule_id.strip())
        sql += " ORDER BY timestamp DESC, id DESC LIMIT ?;"
        params.append(eff_limit)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []
        for r in rows:
            try:
                item = json.loads(r["payload_json"])
                item["id"] = int(r["id"])
                result.append(item)
            except Exception:
                continue
        return result

    def clear_automation_logs(self) -> int:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM automation_logs;")
            self._conn.commit()
            return int(cur.rowcount or 0)

    # --- Unified SceneEvent Persistence ---

    def upsert_scene_event(self, event: dict[str, Any]) -> dict[str, Any]:
        event_id = str(event.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("event_id obbligatorio")
        status = str(event.get("status") or "active")
        started_at = float(event.get("started_at") or time.time())
        ended_at = float(event.get("ended_at") or started_at)
        importance = str(event.get("importance") or "notable")
        best_cam = event.get("best_camera_id")
        cameras = [str(c) for c in (event.get("cameras") or []) if c]
        zones = [str(z) for z in (event.get("zones") or []) if z]
        zone_ids = [str(z) for z in (event.get("zone_ids") or []) if z]
        track_ids = [int(t) for t in (event.get("track_ids") or [])]
        subjects = event.get("subjects") or []

        identities: list[str] = []
        plates: list[str] = []
        classes: list[str] = []
        has_unknown = 0
        for s in subjects:
            if not isinstance(s, dict):
                continue
            cls = str(s.get("class_label") or "").strip().lower()
            if cls and cls not in classes:
                classes.append(cls)
            ident = str(s.get("identity") or "").strip()
            if ident and ident.lower() not in ("sconosciuto", "unknown", "none", "pending"):
                identities.append(ident.lower())
            elif cls == "person":
                has_unknown = 1
            pl = re.sub(r"[^A-Z0-9]", "", str(s.get("plate") or "").upper())
            if pl:
                plates.append(pl)

        raw_rel = event.get("cover_raw_relpath")
        ann_rel = event.get("cover_ann_relpath")
        payload = json.dumps(event, ensure_ascii=False)
        now_ts = time.time()

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO scene_events (
                    event_id, status, started_at, ended_at, importance, best_camera_id,
                    cameras_json, zones_json, zone_ids_json, track_ids_json,
                    identities_text, plates_text, classes_text, has_unknown_person,
                    cover_raw_relpath, cover_ann_relpath, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                    status = excluded.status,
                    started_at = excluded.started_at,
                    ended_at = excluded.ended_at,
                    importance = excluded.importance,
                    best_camera_id = excluded.best_camera_id,
                    cameras_json = excluded.cameras_json,
                    zones_json = excluded.zones_json,
                    zone_ids_json = excluded.zone_ids_json,
                    track_ids_json = excluded.track_ids_json,
                    identities_text = excluded.identities_text,
                    plates_text = excluded.plates_text,
                    classes_text = excluded.classes_text,
                    has_unknown_person = excluded.has_unknown_person,
                    cover_raw_relpath = excluded.cover_raw_relpath,
                    cover_ann_relpath = excluded.cover_ann_relpath,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    event_id,
                    status,
                    started_at,
                    ended_at,
                    importance,
                    best_cam,
                    json.dumps(cameras),
                    json.dumps(zones),
                    json.dumps(zone_ids),
                    json.dumps(track_ids),
                    "|" + "|".join(identities) + "|" if identities else "",
                    "|" + "|".join(plates) + "|" if plates else "",
                    "|" + "|".join(classes) + "|" if classes else "",
                    has_unknown,
                    raw_rel,
                    ann_rel,
                    payload,
                    now_ts,
                ),
            )
            self._conn.commit()
        return event

    def get_scene_event(self, event_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM scene_events WHERE event_id = ?;",
                (event_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["payload_json"])
        except Exception:
            return None

    def query_scene_events(
        self,
        t_start: Optional[float] = None,
        t_end: Optional[float] = None,
        *,
        importance: Optional[str] = None,
        camera_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        identity: Optional[str] = None,
        plate: Optional[str] = None,
        unknown_only: bool = False,
        subject_class: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        sql = "SELECT payload_json FROM scene_events WHERE 1=1"
        params: list[Any] = []
        if t_start is not None:
            sql += " AND ended_at >= ?"
            params.append(float(t_start))
        if t_end is not None:
            sql += " AND started_at <= ?"
            params.append(float(t_end))
        if importance and importance.strip():
            imp_vals = [v.strip().lower() for v in importance.split(",") if v.strip()]
            if len(imp_vals) == 1:
                sql += " AND importance = ?"
                params.append(imp_vals[0])
            elif imp_vals:
                placeholders = ",".join("?" for _ in imp_vals)
                sql += f" AND importance IN ({placeholders})"
                params.extend(imp_vals)
        if camera_id and camera_id.strip():
            sql += " AND cameras_json LIKE ?"
            params.append(f'%"{camera_id.strip()}"%')
        if zone_id and zone_id.strip():
            sql += " AND zone_ids_json LIKE ?"
            params.append(f'%"{zone_id.strip()}"%')
        if identity and identity.strip():
            sql += " AND identities_text LIKE ?"
            params.append(f"%|{identity.strip().lower()}|%")
        if plate and plate.strip():
            clean_plate = re.sub(r"[^A-Z0-9]", "", plate.upper())
            if clean_plate:
                sql += " AND plates_text LIKE ?"
                params.append(f"%{clean_plate}%")
        if unknown_only:
            sql += " AND has_unknown_person = 1"
        if subject_class and subject_class.strip():
            norm_cls = subject_class.strip().lower()
            if norm_cls == "vehicle":
                sql += " AND (classes_text LIKE '%|car|%' OR classes_text LIKE '%|truck|%' OR classes_text LIKE '%|motorbike|%')"
            else:
                sql += " AND classes_text LIKE ?"
                params.append(f"%|{norm_cls}|%")

        eff_limit = max(1, min(int(limit), 500))
        sql += " ORDER BY started_at DESC LIMIT ?;"
        params.append(eff_limit)

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                out.append(json.loads(r["payload_json"]))
            except Exception:
                continue
        return out

    def find_scene_event_by_track_id(self, track_id: int) -> Optional[dict[str, Any]]:
        tid = int(track_id)
        with self._lock:
            rows = self._conn.execute(
                "SELECT track_ids_json, payload_json FROM scene_events ORDER BY started_at DESC LIMIT 120;"
            ).fetchall()
        for r in rows:
            try:
                tids = json.loads(r["track_ids_json"] or "[]")
                if tid in tids:
                    return json.loads(r["payload_json"])
            except Exception:
                continue
        return None

    def delete_scene_event(self, event_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM scene_events WHERE event_id = ?;",
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            self._conn.execute("DELETE FROM scene_events WHERE event_id = ?;", (event_id,))
            self._conn.commit()
        try:
            return json.loads(row["payload_json"])
        except Exception:
            return {"event_id": event_id}

    def prune_scene_events_older_than(self, cutoff_timestamp: float) -> tuple[int, list[str]]:
        cutoff_f = float(cutoff_timestamp)
        with self._lock:
            cur = self._conn.cursor()
            rel_rows = cur.execute(
                """
                SELECT cover_raw_relpath, cover_ann_relpath
                FROM scene_events
                WHERE ended_at < ?;
                """,
                (cutoff_f,),
            ).fetchall()
            relpaths: list[str] = []
            for r in rel_rows:
                if r["cover_raw_relpath"]:
                    relpaths.append(str(r["cover_raw_relpath"]))
                if r["cover_ann_relpath"]:
                    relpaths.append(str(r["cover_ann_relpath"]))
            cur.execute("DELETE FROM scene_events WHERE ended_at < ?;", (cutoff_f,))
            deleted = int(cur.rowcount or 0)
            self._conn.commit()
            if deleted > 0:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            return deleted, relpaths

    # --- System & CV Telemetry Persistence ---

    def append_system_metrics_sample(self, sample: dict[str, Any]) -> int:
        ts = float(sample.get("t") or sample.get("timestamp") or time.time())
        cams_json = json.dumps(sample.get("cameras") or {}, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO system_metrics_history (
                    timestamp, cpu_pct, gpu_pct, gpu_mem_mb, ram_pct, ram_used_mb,
                    proc_cpu_pct, proc_rss_mb, cv_fps_total, cv_fps_target,
                    cv_fps_person, cv_fps_vehicle, cv_fps_idle, cv_read_fps,
                    cv_infer_ms, cv_infer_ms_max, person_det_fps, vehicle_det_fps,
                    animal_det_fps, bio_fps, bio_face_ms, bio_alpr_ms, bio_queue,
                    tracks_total, tracks_person, tracks_vehicle, tracks_animal,
                    nvr_ram_mb, ws_clients, cameras_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    ts,
                    float(sample.get("cpu_pct") or 0.0),
                    float(sample["gpu_pct"]) if sample.get("gpu_pct") is not None else None,
                    float(sample["gpu_mem_mb"]) if sample.get("gpu_mem_mb") is not None else None,
                    float(sample.get("ram_pct") or 0.0),
                    float(sample.get("ram_used_mb") or 0.0),
                    float(sample.get("proc_cpu_pct") or 0.0),
                    float(sample.get("proc_rss_mb") or 0.0),
                    float(sample.get("cv_fps_total") or 0.0),
                    float(sample.get("cv_fps_target") or 0.0),
                    float(sample.get("cv_fps_person") or 0.0),
                    float(sample.get("cv_fps_vehicle") or 0.0),
                    float(sample.get("cv_fps_idle") or 0.0),
                    float(sample.get("cv_read_fps") or 0.0),
                    float(sample.get("cv_infer_ms") or 0.0),
                    float(sample.get("cv_infer_ms_max") or 0.0),
                    float(sample.get("person_det_fps") or 0.0),
                    float(sample.get("vehicle_det_fps") or 0.0),
                    float(sample.get("animal_det_fps") or 0.0),
                    float(sample.get("bio_fps") or 0.0),
                    float(sample.get("bio_face_ms") or 0.0),
                    float(sample.get("bio_alpr_ms") or 0.0),
                    float(sample.get("bio_queue") or 0.0),
                    float(sample.get("tracks_total") or 0.0),
                    float(sample.get("tracks_person") or 0.0),
                    float(sample.get("tracks_vehicle") or 0.0),
                    float(sample.get("tracks_animal") or 0.0),
                    float(sample.get("nvr_ram_mb") or 0.0),
                    float(sample.get("ws_clients") or 0.0),
                    cams_json,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid or 0)

    def query_system_metrics(
        self,
        t_start: float,
        t_end: float,
        *,
        max_points: int = 180,
    ) -> list[dict[str, Any]]:
        start_f = float(t_start)
        end_f = float(t_end)
        eff_max = max(10, min(int(max_points), 500))

        with self._lock:
            cnt_row = self._conn.execute(
                "SELECT COUNT(*) AS cnt FROM system_metrics_history WHERE timestamp >= ? AND timestamp <= ?;",
                (start_f, end_f),
            ).fetchone()
            total_rows = int(cnt_row["cnt"] if cnt_row else 0)
            if total_rows == 0:
                return []

            if total_rows <= eff_max:
                rows = self._conn.execute(
                    """
                    SELECT *
                    FROM system_metrics_history
                    WHERE timestamp >= ? AND timestamp <= ?
                    ORDER BY timestamp ASC;
                    """,
                    (start_f, end_f),
                ).fetchall()
                out: list[dict[str, Any]] = []
                for r in rows:
                    try:
                        cams = json.loads(r["cameras_json"] or "{}")
                    except Exception:
                        cams = {}
                    ts_val = round(float(r["timestamp"]), 3)
                    out.append(
                        {
                            "t": ts_val,
                            "timestamp": ts_val,
                            "cpu_pct": round(float(r["cpu_pct"]), 1),
                            "gpu_pct": round(float(r["gpu_pct"]), 1) if r["gpu_pct"] is not None else None,
                            "gpu_mem_mb": round(float(r["gpu_mem_mb"]), 1) if r["gpu_mem_mb"] is not None else None,
                            "ram_pct": round(float(r["ram_pct"]), 1),
                            "ram_used_mb": round(float(r["ram_used_mb"]), 1),
                            "proc_cpu_pct": round(float(r["proc_cpu_pct"]), 1),
                            "proc_rss_mb": round(float(r["proc_rss_mb"]), 1),
                            "cv_fps_total": round(float(r["cv_fps_total"]), 2),
                            "cv_fps_target": round(float(r["cv_fps_target"]), 2),
                            "cv_fps_person": round(float(r["cv_fps_person"]), 2),
                            "cv_fps_vehicle": round(float(r["cv_fps_vehicle"]), 2),
                            "cv_fps_idle": round(float(r["cv_fps_idle"]), 2),
                            "cv_read_fps": round(float(r["cv_read_fps"]), 2),
                            "cv_infer_ms": round(float(r["cv_infer_ms"]), 2),
                            "cv_infer_ms_max": round(float(r["cv_infer_ms_max"]), 2),
                            "person_det_fps": round(float(r["person_det_fps"]), 2),
                            "vehicle_det_fps": round(float(r["vehicle_det_fps"]), 2),
                            "animal_det_fps": round(float(r["animal_det_fps"]), 2),
                            "bio_fps": round(float(r["bio_fps"]), 2),
                            "bio_face_ms": round(float(r["bio_face_ms"]), 2),
                            "bio_alpr_ms": round(float(r["bio_alpr_ms"]), 2),
                            "bio_queue": round(float(r["bio_queue"]), 1),
                            "tracks_total": round(float(r["tracks_total"]), 1),
                            "tracks_person": round(float(r["tracks_person"]), 1),
                            "tracks_vehicle": round(float(r["tracks_vehicle"]), 1),
                            "tracks_animal": round(float(r["tracks_animal"]), 1),
                            "nvr_ram_mb": round(float(r["nvr_ram_mb"]), 1),
                            "ws_clients": round(float(r["ws_clients"]), 1),
                            "cameras": cams,
                        }
                    )
                return out

            span = max(end_f - start_f, 1.0)
            step = span / float(eff_max)
            rows = self._conn.execute(
                """
                SELECT
                    CAST((timestamp - ?) / ? AS INTEGER) AS bucket_idx,
                    AVG(timestamp) AS avg_ts,
                    AVG(cpu_pct) AS cpu_pct,
                    AVG(gpu_pct) AS gpu_pct,
                    AVG(gpu_mem_mb) AS gpu_mem_mb,
                    AVG(ram_pct) AS ram_pct,
                    AVG(ram_used_mb) AS ram_used_mb,
                    AVG(proc_cpu_pct) AS proc_cpu_pct,
                    AVG(proc_rss_mb) AS proc_rss_mb,
                    AVG(cv_fps_total) AS cv_fps_total,
                    AVG(cv_fps_target) AS cv_fps_target,
                    AVG(cv_fps_person) AS cv_fps_person,
                    AVG(cv_fps_vehicle) AS cv_fps_vehicle,
                    AVG(cv_fps_idle) AS cv_fps_idle,
                    AVG(cv_read_fps) AS cv_read_fps,
                    AVG(cv_infer_ms) AS cv_infer_ms,
                    MAX(cv_infer_ms_max) AS cv_infer_ms_max,
                    AVG(person_det_fps) AS person_det_fps,
                    AVG(vehicle_det_fps) AS vehicle_det_fps,
                    AVG(animal_det_fps) AS animal_det_fps,
                    AVG(bio_fps) AS bio_fps,
                    AVG(bio_face_ms) AS bio_face_ms,
                    AVG(bio_alpr_ms) AS bio_alpr_ms,
                    AVG(bio_queue) AS bio_queue,
                    AVG(tracks_total) AS tracks_total,
                    AVG(tracks_person) AS tracks_person,
                    AVG(tracks_vehicle) AS tracks_vehicle,
                    AVG(tracks_animal) AS tracks_animal,
                    AVG(nvr_ram_mb) AS nvr_ram_mb,
                    AVG(ws_clients) AS ws_clients
                FROM system_metrics_history
                WHERE timestamp >= ? AND timestamp <= ?
                GROUP BY bucket_idx
                ORDER BY bucket_idx ASC;
                """,
                (start_f, step, start_f, end_f),
            ).fetchall()

        out_agg: list[dict[str, Any]] = []
        for r in rows:
            ts_val = round(float(r["avg_ts"]), 3)
            out_agg.append(
                {
                    "t": ts_val,
                    "timestamp": ts_val,
                    "cpu_pct": round(float(r["cpu_pct"]), 1),
                    "gpu_pct": round(float(r["gpu_pct"]), 1) if r["gpu_pct"] is not None else None,
                    "gpu_mem_mb": round(float(r["gpu_mem_mb"]), 1) if r["gpu_mem_mb"] is not None else None,
                    "ram_pct": round(float(r["ram_pct"]), 1),
                    "ram_used_mb": round(float(r["ram_used_mb"]), 1),
                    "proc_cpu_pct": round(float(r["proc_cpu_pct"]), 1),
                    "proc_rss_mb": round(float(r["proc_rss_mb"]), 1),
                    "cv_fps_total": round(float(r["cv_fps_total"]), 2),
                    "cv_fps_target": round(float(r["cv_fps_target"]), 2),
                    "cv_fps_person": round(float(r["cv_fps_person"]), 2),
                    "cv_fps_vehicle": round(float(r["cv_fps_vehicle"]), 2),
                    "cv_fps_idle": round(float(r["cv_fps_idle"]), 2),
                    "cv_read_fps": round(float(r["cv_read_fps"]), 2),
                    "cv_infer_ms": round(float(r["cv_infer_ms"]), 2),
                    "cv_infer_ms_max": round(float(r["cv_infer_ms_max"]), 2),
                    "person_det_fps": round(float(r["person_det_fps"]), 2),
                    "vehicle_det_fps": round(float(r["vehicle_det_fps"]), 2),
                    "animal_det_fps": round(float(r["animal_det_fps"]), 2),
                    "bio_fps": round(float(r["bio_fps"]), 2),
                    "bio_face_ms": round(float(r["bio_face_ms"]), 2),
                    "bio_alpr_ms": round(float(r["bio_alpr_ms"]), 2),
                    "bio_queue": round(float(r["bio_queue"]), 1),
                    "tracks_total": round(float(r["tracks_total"]), 1),
                    "tracks_person": round(float(r["tracks_person"]), 1),
                    "tracks_vehicle": round(float(r["tracks_vehicle"]), 1),
                    "tracks_animal": round(float(r["tracks_animal"]), 1),
                    "nvr_ram_mb": round(float(r["nvr_ram_mb"]), 1),
                    "ws_clients": round(float(r["ws_clients"]), 1),
                }
            )
        return out_agg

    def get_system_metrics_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS cnt FROM system_metrics_history;").fetchone()
            return int(row["cnt"] if row else 0)

    def prune_system_metrics_older_than(self, cutoff_timestamp: float) -> int:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM system_metrics_history WHERE timestamp < ?;", (float(cutoff_timestamp),))
            deleted = int(cur.rowcount or 0)
            self._conn.commit()
            if deleted > 0:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            return deleted

    def close(self) -> None:
        with self._lock:
            self._conn.close()

