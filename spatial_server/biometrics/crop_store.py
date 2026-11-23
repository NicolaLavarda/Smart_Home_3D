from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np

logger = logging.getLogger("spatial_server.biometrics.crops")

_VALID_CROP_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")


class BiometricCropStore:
    """
    Stores solely the single best JPEG crop per biometric track/event under
    `<base_dir>/crops/YYYY-MM-DD/<crop_id>.jpg` with path-traversal protection,
    retention pruning, and absolute disk quota enforcement.
    """

    def __init__(
        self,
        base_dir: Path,
        *,
        jpeg_quality: int = 82,
        max_side_px: int = 320,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.crops_dir = (self.base_dir / "crops").resolve()
        self.crops_dir.mkdir(parents=True, exist_ok=True)
        self.jpeg_quality = max(40, min(int(jpeg_quality), 95))
        self.max_side_px = max(96, int(max_side_px))

    @staticmethod
    def is_valid_crop_id(crop_id: str) -> bool:
        return bool(crop_id and _VALID_CROP_ID_RE.fullmatch(crop_id))

    def _resize_for_thumbnail(self, crop_bgr: np.ndarray) -> np.ndarray:
        h, w = crop_bgr.shape[:2]
        max_dim = max(h, w)
        if max_dim <= self.max_side_px:
            return crop_bgr
        scale = self.max_side_px / float(max_dim)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        return cv2.resize(crop_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def save_best_crop(
        self,
        crop_id: str,
        crop_bgr: np.ndarray,
        *,
        timestamp: Optional[float] = None,
        previous_relpath: Optional[str] = None,
    ) -> tuple[str, str]:
        """Atomically save JPEG thumbnail and remove previous crop file if superseded."""
        if not self.is_valid_crop_id(crop_id):
            raise ValueError(f"Invalid crop_id: {crop_id!r}")
        if crop_bgr is None or crop_bgr.size == 0:
            raise ValueError("Empty crop image")

        ts = float(timestamp if timestamp is not None else time.time())
        day_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        day_dir = (self.crops_dir / day_str).resolve()
        day_dir.relative_to(self.crops_dir)
        day_dir.mkdir(parents=True, exist_ok=True)

        target_path = (day_dir / f"{crop_id}.jpg").resolve()
        target_path.relative_to(self.crops_dir)

        thumb = self._resize_for_thumbnail(crop_bgr)
        ok, encoded = cv2.imencode(
            ".jpg",
            thumb,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if not ok:
            raise RuntimeError("Failed to JPEG-encode crop thumbnail")

        tmp_path = target_path.with_suffix(".tmp.jpg")
        tmp_path.write_bytes(encoded.tobytes())
        os.replace(tmp_path, target_path)

        relpath = target_path.relative_to(self.crops_dir).as_posix()
        if previous_relpath and previous_relpath != relpath:
            self.delete_relpath(previous_relpath)
        return crop_id, relpath

    def resolve_crop_path(self, crop_id: str, known_relpath: Optional[str] = None) -> Optional[Path]:
        """Resolve a crop_id safely within `crops_dir` (never allowing traversal)."""
        if not self.is_valid_crop_id(crop_id):
            return None

        if known_relpath:
            try:
                candidate = (self.crops_dir / known_relpath).resolve()
                candidate.relative_to(self.crops_dir)
                if candidate.is_file():
                    return candidate
            except Exception:
                return None

        # Fallback scan across date buckets
        for match in self.crops_dir.glob(f"*/{crop_id}.jpg"):
            try:
                resolved = match.resolve()
                resolved.relative_to(self.crops_dir)
                if resolved.is_file():
                    return resolved
            except Exception:
                continue
        return None

    def delete_relpath(self, relpath: str) -> bool:
        try:
            target = (self.crops_dir / relpath).resolve()
            target.relative_to(self.crops_dir)
            if target.is_file():
                target.unlink()
                return True
        except Exception:
            pass
        return False

    def get_usage_stats(self) -> dict[str, float | int]:
        total_bytes = 0
        count = 0
        for p in self.crops_dir.rglob("*.jpg"):
            if p.is_file():
                try:
                    total_bytes += p.stat().st_size
                    count += 1
                except OSError:
                    continue
        return {
            "files_count": count,
            "total_mb": round(total_bytes / (1024.0 * 1024.0), 3),
        }

    def prune(
        self,
        *,
        retention_days: int = 14,
        max_disk_mb: float = 250.0,
        extra_relpaths: Iterable[str] = (),
    ) -> int:
        """Delete expired crops, DB-pruned relpaths, and enforce max disk quota FIFO."""
        removed = 0
        for rel in extra_relpaths:
            if rel and self.delete_relpath(rel):
                removed += 1

        cutoff_ts = time.time() - max(1, int(retention_days)) * 86400.0
        entries: list[tuple[float, int, Path]] = []
        total_bytes = 0

        for p in self.crops_dir.rglob("*.jpg"):
            if not p.is_file():
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff_ts:
                try:
                    p.unlink()
                    removed += 1
                except OSError:
                    pass
                continue
            entries.append((st.st_mtime, st.st_size, p))
            total_bytes += st.st_size

        max_bytes = max(1, int(float(max_disk_mb) * 1024 * 1024))
        if total_bytes > max_bytes:
            entries.sort(key=lambda item: item[0])  # Oldest first
            for _mtime, size, path in entries:
                if total_bytes <= max_bytes:
                    break
                try:
                    path.unlink()
                    total_bytes -= size
                    removed += 1
                except OSError:
                    continue

        # Remove empty date directories cleanly
        for d in sorted(self.crops_dir.iterdir()):
            if d.is_dir():
                try:
                    if not any(d.iterdir()):
                        d.rmdir()
                except OSError:
                    pass

        return removed
