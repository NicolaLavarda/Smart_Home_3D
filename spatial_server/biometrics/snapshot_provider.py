from __future__ import annotations

import asyncio
import logging
import re
import time
from concurrent.futures import Executor
from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import httpx
import numpy as np

from spatial_server.domain.models import BoundingBox2D
from .interfaces import IFrameSnapshotProvider
from .models import CropPayload

logger = logging.getLogger("spatial_server.biometrics.snapshot")


def parse_jpeg_dimensions(raw_bytes: bytes) -> Optional[tuple[int, int]]:
    """
    Inspect JPEG SOF marker in RAM (zero pixel decoding) and return (width, height).
    Allows avoiding 48 MB BGR allocation on 16MP panoramic frames.
    """
    if len(raw_bytes) < 4 or raw_bytes[0:2] != b"\xff\xd8":
        return None
    pos = 2
    n = len(raw_bytes)
    while pos + 4 <= n:
        if raw_bytes[pos] != 0xFF:
            pos += 1
            continue
        while pos < n and raw_bytes[pos] == 0xFF:
            pos += 1
        if pos >= n:
            break
        marker = raw_bytes[pos]
        pos += 1
        if marker in (0xD8, 0xD9, 0x00) or (0xD0 <= marker <= 0xD7):
            continue
        if pos + 2 > n:
            break
        seg_len = int.from_bytes(raw_bytes[pos : pos + 2], "big")
        if seg_len < 2 or pos + seg_len > n:
            break
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if pos + 7 <= n:
                height = int.from_bytes(raw_bytes[pos + 3 : pos + 5], "big")
                width = int.from_bytes(raw_bytes[pos + 5 : pos + 7], "big")
                if width > 0 and height > 0:
                    return (width, height)
            break
        pos += seg_len
    return None


def decode_and_crop_jpeg(
    raw_bytes: bytes,
    camera_id: str,
    timestamp: float,
    bbox: BoundingBox2D,
    *,
    expand_ratio: tuple[float, float, float, float] = (0.15, 0.15, 0.15, 0.15),
    max_decode_width: Optional[int] = 3840,
    prefer_upper_fraction: Optional[float] = None,
    is_panoramic_180: bool = False,
    source_variant: str = "go2rtc_snap",
    fetch_ms: float = 0.0,
) -> Optional[CropPayload]:
    """Decode JPEG in memory (half-res for 16MP panoramic), copy subject crop, and free full frame."""
    t_dec0 = time.perf_counter()
    dims = parse_jpeg_dimensions(raw_bytes)
    decode_flag = cv2.IMREAD_COLOR
    if is_panoramic_180 and max_decode_width and dims is not None and dims[0] > int(max_decode_width):
        decode_flag = cv2.IMREAD_REDUCED_COLOR_2

    buf = np.frombuffer(raw_bytes, dtype=np.uint8)
    full_img = cv2.imdecode(buf, decode_flag)
    if full_img is None or full_img.size == 0:
        return None

    fh, fw = full_img.shape[:2]
    bw = max(0.01, float(bbox.x_max - bbox.x_min))
    bh = max(0.01, float(bbox.y_max - bbox.y_min))
    exp_l, exp_t, exp_r, exp_b = expand_ratio

    nx1 = max(0.0, float(bbox.x_min) - bw * exp_l)
    ny1 = max(0.0, float(bbox.y_min) - bh * exp_t)
    nx2 = min(1.0, float(bbox.x_max) + bw * exp_r)
    ny2 = min(1.0, float(bbox.y_max) + bh * exp_b)

    if prefer_upper_fraction is not None and 0.15 <= prefer_upper_fraction < 1.0:
        ny2 = min(ny2, ny1 + (ny2 - ny1) * float(prefer_upper_fraction))

    px1 = max(0, int(round(nx1 * fw)))
    py1 = max(0, int(round(ny1 * fh)))
    px2 = min(fw, int(round(nx2 * fw)))
    py2 = min(fh, int(round(ny2 * fh)))

    if px2 - px1 < 16 or py2 - py1 < 16:
        del full_img
        return None

    crop = full_img[py1:py2, px1:px2].copy()
    if fw > 1280:
        prev_scale = 1280.0 / float(fw)
        preview = cv2.resize(
            full_img,
            (1280, max(1, int(round(fh * prev_scale)))),
            interpolation=cv2.INTER_AREA,
        )
    else:
        preview = full_img.copy()
    del full_img
    decode_ms = (time.perf_counter() - t_dec0) * 1000.0
    return CropPayload(
        camera_id=camera_id,
        timestamp=timestamp,
        crop_bgr=crop,
        full_width=fw,
        full_height=fh,
        crop_bbox_px=(px1, py1, px2, py2),
        source_variant=source_variant,
        fetch_ms=round(fetch_ms, 2),
        decode_ms=round(decode_ms, 2),
        preview_frame_bgr=preview,
    )


@dataclass
class _CameraBreakerState:
    consecutive_failures: int = 0
    open_until_mono: float = 0.0
    total_fetches: int = 0
    total_failures: int = 0


class Go2RtcSnapshotProvider(IFrameSnapshotProvider):
    """
    Fetches high-resolution JPEG frames from go2rtc `/api/frame.jpeg?src=<snap_stream>`
    purely in RAM (zero temp files) with per-camera circuit-breaker and memory-safe
    16MP panoramic decode.
    """

    def __init__(
        self,
        go2rtc_http_base_url: str = "http://127.0.0.1:1984",
        *,
        stream_candidates_by_cam: Optional[dict[str, list[str]]] = None,
        timeout_s: float = 2.5,
        panoramic_max_decode_width: int = 3840,
        breaker_failure_threshold: int = 3,
        breaker_cooldown_s: float = 15.0,
        decode_executor: Optional[Executor] = None,
        substream_fallback_getter: Optional[Callable[[str], Optional[tuple[np.ndarray, float]]]] = None,
        http_transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.base_url = (go2rtc_http_base_url or "http://127.0.0.1:1984").rstrip("/")
        self.stream_candidates_by_cam = dict(stream_candidates_by_cam or {})
        self.timeout_s = max(0.3, float(timeout_s))
        self.panoramic_max_decode_width = int(panoramic_max_decode_width)
        self.breaker_failure_threshold = max(1, int(breaker_failure_threshold))
        self.breaker_cooldown_s = max(1.0, float(breaker_cooldown_s))
        self._decode_executor = decode_executor
        self._substream_fallback_getter = substream_fallback_getter

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_s, connect=min(0.6, self.timeout_s)),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=4),
            transport=http_transport,
        )
        self._breakers: dict[str, _CameraBreakerState] = {}

    def _resolve_streams_for_camera(self, camera_id: str) -> list[str]:
        if camera_id in self.stream_candidates_by_cam and self.stream_candidates_by_cam[camera_id]:
            return self.stream_candidates_by_cam[camera_id]
        slug = re.sub(r"^cam_", "", camera_id, flags=re.IGNORECASE).lower()
        return [f"{slug}_snap", f"{slug}_main"]

    def _breaker(self, camera_id: str) -> _CameraBreakerState:
        st = self._breakers.get(camera_id)
        if st is None:
            st = _CameraBreakerState()
            self._breakers[camera_id] = st
        return st

    def _crop_from_substream_fallback(
        self,
        camera_id: str,
        bbox: BoundingBox2D,
        expand_ratio: tuple[float, float, float, float],
        prefer_upper_fraction: Optional[float],
    ) -> Optional[CropPayload]:
        if self._substream_fallback_getter is None:
            return None
        res = self._substream_fallback_getter(camera_id)
        if res is None:
            return None
        frame, ts = res
        if frame is None or frame.size == 0 or (time.time() - ts) > 2.5:
            return None

        fh, fw = frame.shape[:2]
        bw = max(0.01, float(bbox.x_max - bbox.x_min))
        bh = max(0.01, float(bbox.y_max - bbox.y_min))
        exp_l, exp_t, exp_r, exp_b = expand_ratio
        nx1 = max(0.0, float(bbox.x_min) - bw * exp_l)
        ny1 = max(0.0, float(bbox.y_min) - bh * exp_t)
        nx2 = min(1.0, float(bbox.x_max) + bw * exp_r)
        ny2 = min(1.0, float(bbox.y_max) + bh * exp_b)
        if prefer_upper_fraction is not None and 0.15 <= prefer_upper_fraction < 1.0:
            ny2 = min(ny2, ny1 + (ny2 - ny1) * float(prefer_upper_fraction))
        px1, py1 = max(0, int(round(nx1 * fw))), max(0, int(round(ny1 * fh)))
        px2, py2 = min(fw, int(round(nx2 * fw))), min(fh, int(round(ny2 * fh)))
        if px2 - px1 < 16 or py2 - py1 < 16:
            return None
        if fw > 1280:
            prev_scale = 1280.0 / float(fw)
            preview = cv2.resize(frame, (1280, max(1, int(round(fh * prev_scale)))), interpolation=cv2.INTER_AREA)
        else:
            preview = frame.copy()
        return CropPayload(
            camera_id=camera_id,
            timestamp=ts,
            crop_bgr=frame[py1:py2, px1:px2].copy(),
            full_width=fw,
            full_height=fh,
            crop_bbox_px=(px1, py1, px2, py2),
            source_variant="substream_fallback",
            fetch_ms=0.0,
            decode_ms=0.0,
            preview_frame_bgr=preview,
        )

    async def fetch_crop(
        self,
        camera_id: str,
        bbox: BoundingBox2D,
        *,
        expand_ratio: tuple[float, float, float, float] = (0.15, 0.15, 0.15, 0.15),
        max_decode_width: Optional[int] = None,
        prefer_upper_fraction: Optional[float] = None,
        is_panoramic_180: bool = False,
    ) -> Optional[CropPayload]:
        now_mono = time.monotonic()
        br = self._breaker(camera_id)
        if now_mono < br.open_until_mono:
            return self._crop_from_substream_fallback(camera_id, bbox, expand_ratio, prefer_upper_fraction)

        eff_max_w = max_decode_width if max_decode_width is not None else self.panoramic_max_decode_width
        streams = self._resolve_streams_for_camera(camera_id)

        for stream_name in streams:
            br.total_fetches += 1
            try:
                t0 = time.perf_counter()
                resp = await self._client.get(
                    f"{self.base_url}/api/frame.jpeg",
                    params={"src": stream_name},
                )
                fetch_ms = (time.perf_counter() - t0) * 1000.0
                ctype = (resp.headers.get("content-type") or "").lower()
                if resp.status_code != 200 or ("image" not in ctype and not resp.content.startswith(b"\xff\xd8")):
                    continue

                raw_bytes = resp.content
                loop = asyncio.get_running_loop()
                crop_payload = await loop.run_in_executor(
                    self._decode_executor,
                    lambda: decode_and_crop_jpeg(
                        raw_bytes,
                        camera_id,
                        time.time(),
                        bbox,
                        expand_ratio=expand_ratio,
                        max_decode_width=eff_max_w,
                        prefer_upper_fraction=prefer_upper_fraction,
                        is_panoramic_180=is_panoramic_180,
                        source_variant=stream_name,
                        fetch_ms=fetch_ms,
                    ),
                )
                if crop_payload is not None:
                    br.consecutive_failures = 0
                    return crop_payload
            except Exception as exc:
                logger.debug("Snapshot fetch failed for %s (%s): %s", camera_id, stream_name, type(exc).__name__)
                continue

        br.consecutive_failures += 1
        br.total_failures += 1
        if br.consecutive_failures >= self.breaker_failure_threshold:
            br.open_until_mono = time.monotonic() + self.breaker_cooldown_s
            logger.warning(
                "Snapshot circuit-breaker OPEN for %s (cooldown %.0fs after %d failures)",
                camera_id,
                self.breaker_cooldown_s,
                br.consecutive_failures,
            )
        return self._crop_from_substream_fallback(camera_id, bbox, expand_ratio, prefer_upper_fraction)

    def get_diagnostics(self) -> dict[str, dict[str, float | int | bool]]:
        now_mono = time.monotonic()
        return {
            cam_id: {
                "total_fetches": st.total_fetches,
                "total_failures": st.total_failures,
                "consecutive_failures": st.consecutive_failures,
                "circuit_open": now_mono < st.open_until_mono,
            }
            for cam_id, st in self._breakers.items()
        }

    async def close(self) -> None:
        await self._client.aclose()
