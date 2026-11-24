from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .interfaces import IPlateRecognizer
from .models import PlateEvaluation, PlateQualityMetrics
from .onnx_runtime_utils import build_ort_session_options, resolve_ort_providers
from .plate_postprocessor import normalize_and_validate_plate

logger = logging.getLogger("spatial_server.biometrics.alpr")


class OnnxAlprRecognizer(IPlateRecognizer):
    """
    Pure ONNX Runtime ALPR pipeline executed exclusively on a cropped vehicle image:
    1. YOLOv9-tiny license plate detector (`open-image-models`)
    2. Anti-glare & blur quality gate (+ mild CLAHE for dark night plates)
    3. `fast-plate-ocr` (`cct-xs-v2-global-model` or `european-plates-mobile-vit-v2-model`)
    4. Deterministic IT/EU plate post-processor
    """

    def __init__(
        self,
        det_model_path: Path,
        ocr_model_path: Path,
        ocr_config_path: Path,
        *,
        provider_name: str = "cpu",
        intra_threads: int = 2,
        inter_threads: int = 1,
        det_conf_threshold: float = 0.30,
        min_plate_width_px: float = 55.0,
        min_laplacian: float = 20.0,
        max_glare_ratio: float = 0.65,
    ) -> None:
        self.det_model_path = Path(det_model_path)
        self.ocr_model_path = Path(ocr_model_path)
        self.ocr_config_path = Path(ocr_config_path)
        self.det_conf_threshold = float(det_conf_threshold)
        self.min_plate_width_px = float(min_plate_width_px)
        self.min_laplacian = float(min_laplacian)
        self.max_glare_ratio = float(max_glare_ratio)

        self._detector = None
        self._ocr = None
        self._ocr_color_mode = "rgb"
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))

        if (
            self.det_model_path.is_file()
            and self.ocr_model_path.is_file()
            and self.ocr_config_path.is_file()
        ):
            try:
                from fast_plate_ocr import LicensePlateRecognizer
                from open_image_models.detection.factory import create_detector

                sess_opts = build_ort_session_options(
                    intra_threads=intra_threads,
                    inter_threads=inter_threads,
                )
                providers = resolve_ort_providers(provider_name)

                self._detector = create_detector(
                    self.det_model_path,
                    backend="yolo_v9",
                    class_labels=("License Plate",),
                    conf_thresh=self.det_conf_threshold,
                    providers=providers,
                    sess_options=sess_opts,
                )
                self._ocr = LicensePlateRecognizer(
                    onnx_model_path=self.ocr_model_path,
                    plate_config_path=self.ocr_config_path,
                    providers=providers,
                    sess_options=sess_opts,
                )
                self._ocr_color_mode = str(getattr(self._ocr.config, "image_color_mode", "rgb")).lower()
                logger.info(
                    "Loaded ALPR ONNX models (%s + %s, mode=%s)",
                    self.det_model_path.name,
                    self.ocr_model_path.name,
                    self._ocr_color_mode,
                )
            except Exception as exc:
                logger.warning("Failed to initialize ALPR ONNX models: %s", exc)
                self._detector = None
                self._ocr = None
        else:
            logger.warning(
                "ALPR ONNX models missing (det=%s, ocr=%s); ALPR branch disabled",
                self.det_model_path,
                self.ocr_model_path,
            )

    def is_ready(self) -> bool:
        return self._detector is not None and self._ocr is not None

    def _assess_plate_quality(
        self,
        vehicle_crop_bgr: np.ndarray,
        xyxy: tuple[float, float, float, float],
        det_score: float,
    ) -> tuple[PlateQualityMetrics, Optional[np.ndarray], Optional[np.ndarray]]:
        h, w = vehicle_crop_bgr.shape[:2]
        x1 = max(0, int(round(float(xyxy[0]))))
        y1 = max(0, int(round(float(xyxy[1]))))
        x2 = min(w, int(round(float(xyxy[2]))))
        y2 = min(h, int(round(float(xyxy[3]))))
        pw = float(max(0, x2 - x1))
        ph = float(max(0, y2 - y1))

        if pw < 8 or ph < 6:
            return (
                PlateQualityMetrics(det_score=det_score, plate_width_px=pw, passed=False, reject_reason="empty_plate"),
                None,
                None,
            )

        tight_crop = vehicle_crop_bgr[y1:y2, x1:x2]
        gray = cv2.cvtColor(tight_crop, cv2.COLOR_BGR2GRAY)
        blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        glare_ratio = float(np.mean(gray >= 245))
        mean_luma = float(np.mean(gray))

        reject_reason: Optional[str] = None
        if pw < self.min_plate_width_px:
            reject_reason = "small_plate"
        elif glare_ratio > self.max_glare_ratio:
            reject_reason = "ir_glare"
        elif blur_var < self.min_laplacian:
            reject_reason = "blur"

        # Slightly padded plate crop for UI thumbnail readability
        pad_x = int(round(pw * 0.20))
        pad_y = int(round(ph * 0.25))
        thumb = vehicle_crop_bgr[
            max(0, y1 - pad_y) : min(h, y2 + pad_y),
            max(0, x1 - pad_x) : min(w, x2 + pad_x),
        ].copy()

        metrics = PlateQualityMetrics(
            det_score=round(det_score, 4),
            plate_width_px=round(pw, 1),
            blur_laplacian=round(blur_var, 2),
            glare_ratio=round(glare_ratio, 3),
            mean_luma=round(mean_luma, 1),
            passed=(reject_reason is None),
            reject_reason=reject_reason,
        )
        return metrics, tight_crop, thumb

    def _prepare_ocr_input(self, plate_bgr: np.ndarray, metrics: PlateQualityMetrics) -> np.ndarray:
        """Apply mild CLAHE only on dark low-glare plates, then match model color mode."""
        work = plate_bgr
        if metrics.mean_luma < 80.0 and metrics.glare_ratio < 0.15:
            lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB)
            l_ch, a_ch, b_ch = cv2.split(lab)
            l_ch = self._clahe.apply(l_ch)
            work = cv2.cvtColor(cv2.merge((l_ch, a_ch, b_ch)), cv2.COLOR_LAB2BGR)

        if self._ocr_color_mode == "grayscale":
            return cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(work, cv2.COLOR_BGR2RGB)

    def recognize_crop(self, vehicle_crop_bgr: np.ndarray) -> Optional[PlateEvaluation]:
        if not self.is_ready() or vehicle_crop_bgr is None or vehicle_crop_bgr.size == 0:
            return None

        detections = self._detector.predict(vehicle_crop_bgr)
        if not detections:
            return None

        best_det = max(
            detections,
            key=lambda d: float(d.confidence) * max(1.0, float(d.bounding_box.x2 - d.bounding_box.x1)),
        )
        bb = best_det.bounding_box
        vh, vw = vehicle_crop_bgr.shape[:2]
        px1 = max(0, min(vw - 1, int(round(float(bb.x1)))))
        py1 = max(0, min(vh - 1, int(round(float(bb.y1)))))
        px2 = max(px1 + 1, min(vw, int(round(float(bb.x2)))))
        py2 = max(py1 + 1, min(vh, int(round(float(bb.y2)))))
        plate_box_px = (px1, py1, px2, py2)

        metrics, tight_crop, thumb = self._assess_plate_quality(
            vehicle_crop_bgr,
            (bb.x1, bb.y1, bb.x2, bb.y2),
            float(best_det.confidence),
        )
        if tight_crop is None:
            return None

        base_quality = float(
            metrics.det_score
            * min(1.0, metrics.plate_width_px / 140.0)
            * min(1.0, max(metrics.blur_laplacian, 1.0) / 120.0)
            * max(0.15, 1.0 - metrics.glare_ratio)
        )
        if not metrics.passed:
            return PlateEvaluation(
                plate=None,
                plate_raw="",
                plate_format="INVALID",
                confidence=0.0,
                quality_score=round(base_quality * 0.25, 4),
                metrics=metrics,
                box_crop_px=plate_box_px,
                crop_bgr=thumb,
            )

        ocr_inp = self._prepare_ocr_input(tight_crop, metrics)
        preds = self._ocr.run(ocr_inp, return_confidence=True)
        if not preds:
            return None

        pred = preds[0]
        raw_plate = str(getattr(pred, "plate", "") or "")
        pad_char = str(getattr(self._ocr.config, "pad_char", "_") or "_")
        norm = normalize_and_validate_plate(raw_plate, pad_char=pad_char)

        char_probs = getattr(pred, "char_probs", None)
        if char_probs is not None and len(char_probs) > 0:
            active_len = max(1, min(len(norm.raw_text), len(char_probs)))
            probs_arr = np.asarray(char_probs[:active_len], dtype=np.float32)
            ocr_conf = float(0.7 * np.mean(probs_arr) + 0.3 * np.min(probs_arr))
        else:
            ocr_conf = float(best_det.confidence) * 0.85

        final_conf = max(0.0, min(1.0, ocr_conf - norm.confidence_penalty))
        if not norm.is_valid:
            final_conf *= 0.3

        return PlateEvaluation(
            plate=norm.plate if norm.is_valid else None,
            plate_raw=norm.raw_text,
            plate_format=norm.plate_format,
            confidence=round(final_conf, 4),
            region=getattr(pred, "region", None),
            quality_score=round(base_quality, 4),
            metrics=metrics,
            box_crop_px=plate_box_px,
            crop_bgr=thumb,
        )
