from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

from spatial_server.domain.models import DetectionEvent
from .face_gallery import FaceGalleryIndex
from .face_pipeline import OnnxInsightFaceRecognizer
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
    Local ONNX Face Embedding matcher (SCRFD + MobileFaceNet) backing synchronous/crop callers
    while preserving legacy `IIdentityResolver` compatibility.
    """

    def __init__(
        self,
        gallery_dir: Path,
        similarity_threshold: float = 0.45,
        *,
        recognizer: Optional[OnnxInsightFaceRecognizer] = None,
        models_dir: Optional[Path] = None,
    ) -> None:
        self.gallery_dir = Path(gallery_dir)
        self.similarity_threshold = float(similarity_threshold)
        self.gallery: dict[str, np.ndarray] = {}

        if recognizer is not None:
            self._recognizer: Optional[OnnxInsightFaceRecognizer] = recognizer
            self._gallery_index = recognizer.gallery
        else:
            npz_path = (
                self.gallery_dir
                if self.gallery_dir.suffix == ".npz"
                else self.gallery_dir / "face_gallery.npz"
            )
            self._gallery_index = FaceGalleryIndex(npz_path if npz_path.is_file() else None)
            self._load_legacy_npy_gallery()
            m_root = Path(models_dir) if models_dir else self.gallery_dir.parent / "models" / "biometrics" / "face"
            det_path = m_root / "det_500m.onnx"
            rec_path = m_root / "w600k_mbf.onnx"
            if det_path.is_file() and rec_path.is_file():
                self._recognizer = OnnxInsightFaceRecognizer(
                    det_path,
                    rec_path,
                    self._gallery_index,
                    match_threshold=self.similarity_threshold,
                )
            else:
                self._recognizer = None

    def _load_legacy_npy_gallery(self) -> None:
        if not self.gallery_dir.is_dir():
            return
        for npy_file in self.gallery_dir.glob("*.npy"):
            try:
                emb = np.load(npy_file).astype(np.float32)
                norm = float(np.linalg.norm(emb))
                if norm > 1e-8:
                    unit = emb / norm
                    self.gallery[npy_file.stem] = unit
                    self._gallery_index.add_embedding(npy_file.stem, unit, persist=False)
            except Exception as exc:
                logger.warning("Failed to load identity embedding %s: %s", npy_file.name, exc)

    async def resolve_identity(
        self,
        detection: DetectionEvent,
        frame_crop: Optional[np.ndarray] = None,
    ) -> tuple[Optional[str], float]:
        if detection.sub_label:
            return (detection.sub_label, float(detection.face_confidence or 0.92))
        if frame_crop is None or self._recognizer is None or not self._recognizer.is_ready():
            return (None, 0.0)
        ev = self._recognizer.recognize_crop(frame_crop)
        if ev is None or ev.identity is None:
            return (None, 0.0)
        return (ev.identity, float(ev.similarity))


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
