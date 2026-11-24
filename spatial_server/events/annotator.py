from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np

from .models import FrameBoxAnnotation, is_valid_event_id

logger = logging.getLogger("spatial_server.events.annotator")

# BGR colors matching Smart Home 3D Material 3 palette
_COLOR_BY_CATEGORY: dict[str, tuple[int, int, int]] = {
    "known": (129, 185, 16),       # Emerald #10b981
    "plate_wl": (129, 185, 16),    # Emerald #10b981
    "unknown": (94, 63, 244),      # Rose #f43f5e
    "plate_guest": (11, 158, 245), # Amber #f59e0b
    "object": (248, 189, 56),      # Sky #38bdf8
}


def _to_px_rect(
    bbox_norm: tuple[float, float, float, float],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    x1 = max(0, min(width - 1, int(round(float(bbox_norm[0]) * width))))
    y1 = max(0, min(height - 1, int(round(float(bbox_norm[1]) * height))))
    x2 = max(x1 + 1, min(width, int(round(float(bbox_norm[2]) * width))))
    y2 = max(y1 + 1, min(height, int(round(float(bbox_norm[3]) * height))))
    return x1, y1, x2, y2


def _draw_label_pill(
    img: np.ndarray,
    text: str,
    anchor_x: int,
    anchor_y: int,
    bg_color: tuple[int, int, int],
    *,
    font_scale: float = 0.56,
    thickness: int = 1,
) -> None:
    clean = (text or "").strip()
    if not clean:
        return
    h, w = img.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(clean, font, font_scale, thickness)
    pad_x = 8
    pad_y = 5
    pill_w = tw + pad_x * 2
    pill_h = th + baseline + pad_y * 2

    px1 = max(2, min(w - pill_w - 2, anchor_x))
    py2 = anchor_y - 4
    py1 = py2 - pill_h
    if py1 < 2:
        py1 = min(h - pill_h - 2, anchor_y + 4)
        py2 = py1 + pill_h

    cv2.rectangle(img, (px1, py1), (px1 + pill_w, py2), bg_color, -1, cv2.LINE_AA)
    cv2.putText(
        img,
        clean,
        (px1 + pad_x, py2 - baseline - pad_y + 1),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def annotate_scene_frame_bgr(
    frame_bgr: np.ndarray,
    boxes: list[FrameBoxAnnotation],
    *,
    camera_label: str = "",
    timestamp: Optional[float] = None,
) -> np.ndarray:
    """
    Draw crisp bounding boxes (person/vehicle + exact face/plate sub-box when available)
    and readable pill labels on a copy of `frame_bgr`.
    """
    annotated = frame_bgr.copy()
    h, w = annotated.shape[:2]
    base_thick = max(2, int(round(min(w, h) / 360.0)))
    font_scale = max(0.48, min(0.78, w / 1600.0))

    for box in boxes:
        color = _COLOR_BY_CATEGORY.get(box.category, _COLOR_BY_CATEGORY["object"])
        bx1, by1, bx2, by2 = _to_px_rect(box.bbox_norm, w, h)

        if box.sub_bbox_norm is not None:
            # Subtle outer subject frame + prominent biometric (face/plate) box with label
            cv2.rectangle(annotated, (bx1, by1), (bx2, by2), color, max(1, base_thick - 1), cv2.LINE_AA)
            sx1, sy1, sx2, sy2 = _to_px_rect(box.sub_bbox_norm, w, h)
            cv2.rectangle(annotated, (sx1, sy1), (sx2, sy2), color, base_thick + 1, cv2.LINE_AA)
            _draw_label_pill(
                annotated,
                box.label,
                sx1,
                sy1,
                color,
                font_scale=font_scale,
                thickness=max(1, base_thick - 1),
            )
        else:
            cv2.rectangle(annotated, (bx1, by1), (bx2, by2), color, base_thick, cv2.LINE_AA)
            _draw_label_pill(
                annotated,
                box.label,
                bx1,
                by1,
                color,
                font_scale=font_scale,
                thickness=max(1, base_thick - 1),
            )

    # Bottom-left subtle camera & timestamp caption
    caption_parts: list[str] = []
    if camera_label:
        caption_parts.append(camera_label.strip())
    if timestamp is not None:
        dt = datetime.fromtimestamp(float(timestamp), tz=timezone.utc).astimezone()
        caption_parts.append(dt.strftime("%H:%M:%S"))
    if caption_parts:
        caption = " · ".join(caption_parts)
        font = cv2.FONT_HERSHEY_SIMPLEX
        cap_scale = max(0.44, font_scale * 0.85)
        (cw, ch), baseline = cv2.getTextSize(caption, font, cap_scale, 1)
        pad_x, pad_y = 10, 6
        x1, y2 = 10, h - 10
        x2 = min(w - 10, x1 + cw + pad_x * 2)
        y1 = max(10, y2 - ch - baseline - pad_y * 2)
        overlay = annotated.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (15, 23, 42), -1)
        cv2.addWeighted(overlay, 0.68, annotated, 0.32, 0.0, annotated)
        cv2.putText(
            annotated,
            caption,
            (x1 + pad_x, y2 - baseline - pad_y + 1),
            font,
            cap_scale,
            (241, 245, 249),
            1,
            cv2.LINE_AA,
        )

    return annotated


class EventSnapshotStore:
    """
    Manages raw and annotated cover snapshots for SceneEvents under
    `<base_dir>/snapshots/YYYY-MM-DD/<event_id>_{raw|ann}.jpg`
    with path-traversal protection, atomic writes, and FIFO disk pruning.
    """

    def __init__(
        self,
        base_dir: Path,
        *,
        jpeg_quality: int = 84,
        max_width_px: int = 1280,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.snapshots_dir = (self.base_dir / "snapshots").resolve()
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.jpeg_quality = max(45, min(int(jpeg_quality), 95))
        self.max_width_px = max(480, int(max_width_px))

    def _resize_for_storage(self, frame_bgr: np.ndarray) -> np.ndarray:
        h, w = frame_bgr.shape[:2]
        if w <= self.max_width_px:
            return frame_bgr
        scale = self.max_width_px / float(w)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        return cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    def _write_jpeg_atomic(self, target_path: Path, img_bgr: np.ndarray) -> None:
        ok, encoded = cv2.imencode(
            ".jpg",
            img_bgr,
            [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
        )
        if not ok:
            raise RuntimeError("Failed to JPEG-encode event snapshot")
        tmp_path = target_path.with_suffix(".tmp.jpg")
        tmp_path.write_bytes(encoded.tobytes())
        os.replace(tmp_path, target_path)

    def save_event_snapshots(
        self,
        event_id: str,
        raw_bgr: np.ndarray,
        boxes: list[FrameBoxAnnotation],
        *,
        camera_label: str = "",
        timestamp: Optional[float] = None,
    ) -> tuple[str, str]:
        if not is_valid_event_id(event_id):
            raise ValueError(f"Invalid event_id: {event_id!r}")
        if raw_bgr is None or raw_bgr.size == 0:
            raise ValueError("Empty snapshot frame")

        ts = float(timestamp if timestamp is not None else time.time())
        day_str = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")
        day_dir = (self.snapshots_dir / day_str).resolve()
        day_dir.relative_to(self.snapshots_dir)
        day_dir.mkdir(parents=True, exist_ok=True)

        raw_path = (day_dir / f"{event_id}_raw.jpg").resolve()
        ann_path = (day_dir / f"{event_id}_ann.jpg").resolve()
        raw_path.relative_to(self.snapshots_dir)
        ann_path.relative_to(self.snapshots_dir)

        resized = self._resize_for_storage(raw_bgr)
        annotated = annotate_scene_frame_bgr(
            resized,
            boxes,
            camera_label=camera_label,
            timestamp=ts,
        )
        self._write_jpeg_atomic(raw_path, resized)
        self._write_jpeg_atomic(ann_path, annotated)

        raw_rel = raw_path.relative_to(self.snapshots_dir).as_posix()
        ann_rel = ann_path.relative_to(self.snapshots_dir).as_posix()
        return raw_rel, ann_rel

    def reannotate_event(
        self,
        event_id: str,
        raw_relpath: Optional[str],
        boxes: list[FrameBoxAnnotation],
        *,
        camera_label: str = "",
        timestamp: Optional[float] = None,
    ) -> Optional[str]:
        """Re-render `<event_id>_ann.jpg` from existing `<event_id>_raw.jpg` without re-fetching."""
        raw_path = self.resolve_snapshot_path(event_id, "raw", known_relpath=raw_relpath)
        if raw_path is None or not raw_path.is_file():
            return None

        raw_bytes = raw_path.read_bytes()
        raw_bgr = cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if raw_bgr is None or raw_bgr.size == 0:
            return None

        ann_path = raw_path.with_name(f"{event_id}_ann.jpg").resolve()
        ann_path.relative_to(self.snapshots_dir)
        annotated = annotate_scene_frame_bgr(
            raw_bgr,
            boxes,
            camera_label=camera_label,
            timestamp=timestamp,
        )
        self._write_jpeg_atomic(ann_path, annotated)
        return ann_path.relative_to(self.snapshots_dir).as_posix()

    def resolve_snapshot_path(
        self,
        event_id: str,
        variant: str = "annotated",
        *,
        known_relpath: Optional[str] = None,
    ) -> Optional[Path]:
        if not is_valid_event_id(event_id):
            return None
        suffix = "raw" if variant == "raw" else "ann"

        if known_relpath:
            try:
                candidate = (self.snapshots_dir / known_relpath).resolve()
                candidate.relative_to(self.snapshots_dir)
                if candidate.is_file():
                    return candidate
            except Exception:
                return None

        for match in self.snapshots_dir.glob(f"*/{event_id}_{suffix}.jpg"):
            try:
                resolved = match.resolve()
                resolved.relative_to(self.snapshots_dir)
                if resolved.is_file():
                    return resolved
            except Exception:
                continue
        return None

    def delete_relpath(self, relpath: Optional[str]) -> bool:
        if not relpath:
            return False
        try:
            target = (self.snapshots_dir / relpath).resolve()
            target.relative_to(self.snapshots_dir)
            if target.is_file():
                target.unlink()
                return True
        except Exception:
            pass
        return False

    def delete_event_files(self, raw_relpath: Optional[str], ann_relpath: Optional[str]) -> int:
        deleted = 0
        if self.delete_relpath(raw_relpath):
            deleted += 1
        if self.delete_relpath(ann_relpath):
            deleted += 1
        return deleted

    def get_usage_stats(self) -> dict[str, float | int]:
        total_bytes = 0
        count = 0
        for p in self.snapshots_dir.rglob("*.jpg"):
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
        retention_days: int = 30,
        max_disk_mb: float = 400.0,
        extra_relpaths: Iterable[str] = (),
    ) -> int:
        removed = 0
        for rel in extra_relpaths:
            if rel and self.delete_relpath(rel):
                removed += 1

        cutoff_ts = time.time() - max(1, int(retention_days)) * 86400.0
        entries: list[tuple[float, int, Path]] = []
        total_bytes = 0

        for p in self.snapshots_dir.rglob("*.jpg"):
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
            entries.sort(key=lambda item: item[0])
            for _mtime, size, path in entries:
                if total_bytes <= max_bytes:
                    break
                try:
                    path.unlink()
                    total_bytes -= size
                    removed += 1
                except OSError:
                    continue

        for d in sorted(self.snapshots_dir.iterdir()):
            if d.is_dir():
                try:
                    if not any(d.iterdir()):
                        d.rmdir()
                except OSError:
                    pass

        return removed
