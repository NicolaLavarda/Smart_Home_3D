from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
import httpx
import numpy as np

from spatial_server.domain.models import DetectionEvent
from .interfaces import IIdentityResolver

logger = logging.getLogger(__name__)


class NoOpIdentityResolver(IIdentityResolver):
    """Default zero-overhead resolver propagating pre-labeled metadata (e.g. Frigate sub_label)."""

    async def resolve_identity(
        self,
        detection: DetectionEvent,
        frame_crop: Optional[np.ndarray] = None,
    ) -> tuple[Optional[str], float]:
        if detection.sub_label:
            return (detection.sub_label, float(detection.face_confidence or 0.90))
        return (None, 0.0)


class OpenVINOInsightFaceResolver(IIdentityResolver):
    """
    Prepared local OpenVINO / ONNX Face Embedding matcher for Intel HD 530 / Skylake CPU.
    Matches cropped detections against saved embeddings in `gallery_dir` without storing video.
    """

    def __init__(self, gallery_dir: Path, similarity_threshold: float = 0.55) -> None:
        self.gallery_dir = gallery_dir
        self.similarity_threshold = similarity_threshold
        self.gallery: dict[str, np.ndarray] = {}
        self._load_gallery()

    def _load_gallery(self) -> None:
        if not self.gallery_dir.exists():
            return
        for npy_file in self.gallery_dir.glob("*.npy"):
            try:
                emb = np.load(npy_file).astype(np.float32)
                norm = float(np.linalg.norm(emb))
                if norm > 1e-8:
                    self.gallery[npy_file.stem] = emb / norm
            except Exception as exc:
                logger.warning("Failed to load identity embedding %s: %s", npy_file.name, exc)

    async def resolve_identity(
        self,
        detection: DetectionEvent,
        frame_crop: Optional[np.ndarray] = None,
    ) -> tuple[Optional[str], float]:
        if detection.sub_label:
            return (detection.sub_label, float(detection.face_confidence or 0.92))
        # When an InsightFace OpenVINO IR model is placed in `spatial_server/models/`,
        # extract the 512-d ArcFace embedding from `frame_crop` and cosine-match against `self.gallery`.
        return (None, 0.0)


class ExternalWebhookIdentityResolver(IIdentityResolver):
    """Delegates face/plate recognition to an external LAN service (e.g., CompreFace / DoubleTake)."""

    def __init__(self, webhook_url: str, timeout_s: float = 1.5) -> None:
        self.webhook_url = webhook_url.strip()
        self.timeout_s = timeout_s

    async def resolve_identity(
        self,
        detection: DetectionEvent,
        frame_crop: Optional[np.ndarray] = None,
    ) -> tuple[Optional[str], float]:
        if detection.sub_label:
            return (detection.sub_label, float(detection.face_confidence or 0.92))
        if not self.webhook_url or frame_crop is None:
            return (None, 0.0)

        try:
            import cv2
            ok, buf = cv2.imencode(".jpg", frame_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                return (None, 0.0)
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.post(
                    self.webhook_url,
                    files={"file": ("crop.jpg", buf.tobytes(), "image/jpeg")},
                    data={"camera_id": detection.camera_id},
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    return (payload.get("identity"), float(payload.get("confidence", 0.0)))
        except Exception:
            pass
        return (None, 0.0)

