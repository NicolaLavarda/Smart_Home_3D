from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .face_gallery import FaceGalleryIndex
from .interfaces import IFaceRecognizer
from .models import FaceEvaluation, FaceQualityMetrics
from .onnx_runtime_utils import create_ort_session

logger = logging.getLogger("spatial_server.biometrics.face")

# Standard ArcFace 5-point alignment template for 112x112 recognition input.
ARCFACE_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def _nms_xyxy(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float = 0.40) -> list[int]:
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1 + 1.0) * np.maximum(0.0, y2 - y1 + 1.0)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1 + 1.0) * np.maximum(0.0, yy2 - yy1 + 1.0)
        iou = inter / np.maximum(areas[i] + areas[order[1:]] - inter, 1e-6)
        inds = np.where(iou <= iou_thresh)[0]
        order = order[inds + 1]
    return keep


class OnnxInsightFaceRecognizer(IFaceRecognizer):
    """
    Pure ONNX Runtime Face Recognition pipeline (SCRFD + Quality Gate + 112x112 ArcFace align + MobileFaceNet).
    Runs without insightface PyPI, PyTorch, or dlib.
    """

    def __init__(
        self,
        det_model_path: Path,
        rec_model_path: Path,
        gallery: FaceGalleryIndex,
        *,
        provider_name: str = "cpu",
        intra_threads: int = 2,
        inter_threads: int = 1,
        det_conf_threshold: float = 0.50,
        min_face_width_px: float = 48.0,
        min_laplacian: float = 35.0,
        max_yaw_ratio: float = 0.55,
        match_threshold: float = 0.45,
        margin_threshold: float = 0.08,
    ) -> None:
        self.det_model_path = Path(det_model_path)
        self.rec_model_path = Path(rec_model_path)
        self.gallery = gallery
        self.det_conf_threshold = float(det_conf_threshold)
        self.min_face_width_px = float(min_face_width_px)
        self.min_laplacian = float(min_laplacian)
        self.max_yaw_ratio = float(max_yaw_ratio)
        self.match_threshold = float(match_threshold)
        self.margin_threshold = float(margin_threshold)

        self._det_session = None
        self._rec_session = None
        self._det_input_name = ""
        self._rec_input_name = ""

        if self.det_model_path.is_file() and self.rec_model_path.is_file():
            try:
                self._det_session = create_ort_session(
                    self.det_model_path,
                    provider_name=provider_name,
                    intra_threads=intra_threads,
                    inter_threads=inter_threads,
                )
                self._rec_session = create_ort_session(
                    self.rec_model_path,
                    provider_name=provider_name,
                    intra_threads=intra_threads,
                    inter_threads=inter_threads,
                )
                self._det_input_name = self._det_session.get_inputs()[0].name
                self._rec_input_name = self._rec_session.get_inputs()[0].name
                logger.info(
                    "Loaded face ONNX models (%s + %s, gallery=%d people)",
                    self.det_model_path.name,
                    self.rec_model_path.name,
                    self.gallery.person_count,
                )
            except Exception as exc:
                logger.warning("Failed to initialize face ONNX models: %s", exc)
                self._det_session = None
                self._rec_session = None
        else:
            logger.warning(
                "Face ONNX models missing (det=%s, rec=%s); face branch disabled",
                self.det_model_path,
                self.rec_model_path,
            )

    def is_ready(self) -> bool:
        return self._det_session is not None and self._rec_session is not None

    def _detect_scrfd(
        self,
        img_bgr: np.ndarray,
        *,
        input_size: tuple[int, int] = (640, 640),
        conf_thresh: float = 0.50,
    ) -> tuple[np.ndarray, np.ndarray]:
        assert self._det_session is not None
        h, w = img_bgr.shape[:2]
        in_w, in_h = input_size
        det_scale = min(in_h / max(h, 1), in_w / max(w, 1))
        new_w = max(1, int(round(w * det_scale)))
        new_h = max(1, int(round(h * det_scale)))
        resized = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        canvas = np.zeros((in_h, in_w, 3), dtype=np.uint8)
        canvas[:new_h, :new_w, :] = resized
        blob = cv2.dnn.blobFromImage(
            canvas,
            scalefactor=1.0 / 128.0,
            size=(in_w, in_h),
            mean=(127.5, 127.5, 127.5),
            swapRB=True,
        )
        outputs = self._det_session.run(None, {self._det_input_name: blob})

        by_rows: dict[int, dict[int, np.ndarray]] = {}
        for out in outputs:
            arr = out[0] if out.ndim == 3 else out
            if arr.ndim == 1:
                arr = arr[:, None]
            by_rows.setdefault(arr.shape[0], {})[arr.shape[1]] = arr

        all_boxes: list[np.ndarray] = []
        all_scores: list[np.ndarray] = []
        all_kps: list[np.ndarray] = []

        for stride in (8, 16, 32):
            fh = in_h // stride
            fw = in_w // stride
            cells = fh * fw
            matched_rows = next((r for r in by_rows if r in (cells, cells * 2)), None)
            if matched_rows is None:
                continue
            bucket = by_rows[matched_rows]
            if 1 not in bucket or 4 not in bucket or 10 not in bucket:
                continue

            scores = bucket[1][:, 0]
            bboxes = bucket[4]
            kps = bucket[10]
            num_anchors = max(1, matched_rows // cells)

            centers = np.stack(np.mgrid[:fh, :fw][::-1], axis=-1).astype(np.float32) * float(stride)
            centers = centers.reshape(-1, 2)
            if num_anchors > 1:
                centers = np.repeat(centers, num_anchors, axis=0)

            valid = np.where(scores >= conf_thresh)[0]
            if valid.size == 0:
                continue

            v_scores = scores[valid].astype(np.float32)
            v_boxes = bboxes[valid].astype(np.float32) * float(stride)
            v_kps = kps[valid].astype(np.float32) * float(stride)
            v_centers = centers[valid]

            x1 = (v_centers[:, 0] - v_boxes[:, 0]) / det_scale
            y1 = (v_centers[:, 1] - v_boxes[:, 1]) / det_scale
            x2 = (v_centers[:, 0] + v_boxes[:, 2]) / det_scale
            y2 = (v_centers[:, 1] + v_boxes[:, 3]) / det_scale
            dec_boxes = np.stack([x1, y1, x2, y2], axis=-1)

            dec_kps = v_kps.reshape(-1, 5, 2)
            dec_kps[:, :, 0] = (dec_kps[:, :, 0] + v_centers[:, 0:1]) / det_scale
            dec_kps[:, :, 1] = (dec_kps[:, :, 1] + v_centers[:, 1:2]) / det_scale

            all_boxes.append(dec_boxes)
            all_scores.append(v_scores)
            all_kps.append(dec_kps)

        if not all_boxes:
            return np.empty((0, 5), dtype=np.float32), np.empty((0, 5, 2), dtype=np.float32)

        cat_boxes = np.concatenate(all_boxes, axis=0)
        cat_scores = np.concatenate(all_scores, axis=0)
        cat_kps = np.concatenate(all_kps, axis=0)
        keep = _nms_xyxy(cat_boxes, cat_scores, iou_thresh=0.40)
        return (
            np.hstack([cat_boxes[keep], cat_scores[keep][:, None]]).astype(np.float32),
            cat_kps[keep].astype(np.float32),
        )

    def _detect_with_border_fallback(self, img_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        boxes, kps = self._detect_scrfd(img_bgr, conf_thresh=self.det_conf_threshold)
        if len(boxes) > 0:
            return boxes, kps

        h, w = img_bgr.shape[:2]
        if min(h, w) < 40:
            return boxes, kps
        pad_x = max(24, int(round(w * 0.35)))
        pad_y = max(24, int(round(h * 0.35)))
        bordered = cv2.copyMakeBorder(
            img_bgr, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )
        boxes_b, kps_b = self._detect_scrfd(bordered, conf_thresh=max(0.35, self.det_conf_threshold - 0.05))
        if len(boxes_b) == 0:
            return boxes_b, kps_b

        boxes_b[:, [0, 2]] = np.clip(boxes_b[:, [0, 2]] - pad_x, 0.0, float(w))
        boxes_b[:, [1, 3]] = np.clip(boxes_b[:, [1, 3]] - pad_y, 0.0, float(h))
        kps_b[:, :, 0] -= pad_x
        kps_b[:, :, 1] -= pad_y
        return boxes_b, kps_b

    def _assess_quality(
        self,
        img_bgr: np.ndarray,
        box: np.ndarray,
        kps: np.ndarray,
    ) -> tuple[FaceQualityMetrics, Optional[np.ndarray]]:
        h, w = img_bgr.shape[:2]
        x1 = max(0, int(round(float(box[0]))))
        y1 = max(0, int(round(float(box[1]))))
        x2 = min(w, int(round(float(box[2]))))
        y2 = min(h, int(round(float(box[3]))))
        face_w = float(max(0, x2 - x1))
        face_h = float(max(0, y2 - y1))
        det_score = float(box[4])

        if face_w < 8 or face_h < 8:
            return FaceQualityMetrics(det_score=det_score, face_width_px=face_w, passed=False, reject_reason="empty_face"), None

        crop = img_bgr[y1:y2, x1:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        le_x, re_x, nose_x = float(kps[0, 0]), float(kps[1, 0]), float(kps[2, 0])
        eye_span = abs(re_x - le_x)
        if re_x <= le_x or eye_span < 4.0:
            yaw_ratio = 1.0
        else:
            yaw_ratio = abs((nose_x - le_x) - (re_x - nose_x)) / max(eye_span, 1.0)

        reject_reason: Optional[str] = None
        if face_w < self.min_face_width_px:
            reject_reason = "small_face"
        elif blur_var < self.min_laplacian:
            reject_reason = "blur"
        elif yaw_ratio > self.max_yaw_ratio:
            reject_reason = "extreme_yaw"

        # Extract padded thumbnail crop (useful both for passed faces and HITL unknown review)
        pad_x = int(round(face_w * 0.35))
        pad_y = int(round(face_h * 0.35))
        tx1 = max(0, x1 - pad_x)
        ty1 = max(0, y1 - pad_y)
        tx2 = min(w, x2 + pad_x)
        ty2 = min(h, y2 + pad_y)
        thumb = img_bgr[ty1:ty2, tx1:tx2].copy()

        metrics = FaceQualityMetrics(
            det_score=round(det_score, 4),
            face_width_px=round(face_w, 1),
            blur_laplacian=round(blur_var, 2),
            yaw_ratio=round(yaw_ratio, 3),
            passed=(reject_reason is None),
            reject_reason=reject_reason,
        )
        return metrics, thumb

    def _align_and_embed(self, img_bgr: np.ndarray, kps: np.ndarray) -> Optional[np.ndarray]:
        assert self._rec_session is not None
        M, _ = cv2.estimateAffinePartial2D(kps.astype(np.float32), ARCFACE_DST, method=cv2.LMEDS)
        if M is None:
            M, _ = cv2.estimateAffinePartial2D(kps.astype(np.float32), ARCFACE_DST, method=cv2.RANSAC)
        if M is None:
            return None

        aligned = cv2.warpAffine(img_bgr, M, (112, 112), borderValue=0.0)
        blob = cv2.dnn.blobFromImage(
            aligned,
            scalefactor=1.0 / 127.5,
            size=(112, 112),
            mean=(127.5, 127.5, 127.5),
            swapRB=True,
        )
        emb = self._rec_session.run(None, {self._rec_input_name: blob})[0].reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(emb))
        if norm < 1e-8 or not np.isfinite(norm):
            return None
        return emb / norm

    def extract_face_embedding(
        self,
        image_bgr: np.ndarray,
        *,
        bypass_quality_gate: bool = False,
    ) -> Optional[tuple[np.ndarray, FaceQualityMetrics, Optional[np.ndarray]]]:
        """Detect best face and compute L2-normalized 512-D embedding (also used by HITL assign)."""
        if not self.is_ready() or image_bgr is None or image_bgr.size == 0:
            return None

        boxes, kps = self._detect_with_border_fallback(image_bgr)
        if len(boxes) == 0:
            return None

        areas = np.maximum(1.0, (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]))
        pick_idx = int(np.argmax(boxes[:, 4] * np.sqrt(areas)))
        box = boxes[pick_idx]
        kp = kps[pick_idx]

        metrics, thumb = self._assess_quality(image_bgr, box, kp)
        if not metrics.passed and not bypass_quality_gate:
            return None

        emb = self._align_and_embed(image_bgr, kp)
        if emb is None:
            return None
        return emb, metrics, thumb

    def recognize_crop(self, person_crop_bgr: np.ndarray) -> Optional[FaceEvaluation]:
        if not self.is_ready() or person_crop_bgr is None or person_crop_bgr.size == 0:
            return None

        boxes, kps = self._detect_with_border_fallback(person_crop_bgr)
        if len(boxes) == 0:
            return None

        areas = np.maximum(1.0, (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]))
        pick_idx = int(np.argmax(boxes[:, 4] * np.sqrt(areas)))
        box = boxes[pick_idx]
        kp = kps[pick_idx]

        ch, cw = person_crop_bgr.shape[:2]
        fx1 = max(0, min(cw - 1, int(round(float(box[0])))))
        fy1 = max(0, min(ch - 1, int(round(float(box[1])))))
        fx2 = max(fx1 + 1, min(cw, int(round(float(box[2])))))
        fy2 = max(fy1 + 1, min(ch, int(round(float(box[3])))))
        face_box_px = (fx1, fy1, fx2, fy2)

        metrics, thumb = self._assess_quality(person_crop_bgr, box, kp)
        quality_score = float(
            metrics.det_score
            * min(1.0, metrics.face_width_px / 140.0)
            * min(1.0, max(metrics.blur_laplacian, 1.0) / 140.0)
            * max(0.2, 1.0 - metrics.yaw_ratio)
        )
        if not metrics.passed:
            return FaceEvaluation(
                identity=None,
                similarity=0.0,
                quality_score=round(quality_score * 0.25, 4),
                metrics=metrics,
                box_crop_px=face_box_px,
                crop_bgr=thumb,
            )

        emb = self._align_and_embed(person_crop_bgr, kp)
        if emb is None:
            return None

        match = self.gallery.match(
            emb,
            match_threshold=self.match_threshold,
            margin_threshold=self.margin_threshold,
        )
        return FaceEvaluation(
            identity=match.identity,
            similarity=match.score,
            second_best_similarity=match.second_best_score,
            margin=match.margin,
            quality_score=round(quality_score, 4),
            metrics=metrics,
            box_crop_px=face_box_px,
            crop_bgr=thumb,
        )
