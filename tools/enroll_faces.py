"""Idempotent CLI tool to enroll family face folders into a compact ONNX gallery (.npz)
and evaluate Leave-One-Out (LOO) separability and accuracy.

Runs purely on ONNX Runtime + OpenCV + NumPy (no PyTorch, dlib, or insightface package).
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import onnxruntime as ort

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = Path(r"C:\Users\Nicola Lavarda\Jupyter\Domotica\Volti totali")
DEFAULT_MODELS_DIR = REPO_ROOT / "spatial_server" / "models" / "biometrics" / "face"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "spatial_server" / "data" / "biometrics" / "face_gallery.npz"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Standard ArcFace 5-point alignment template for 112x112 recognition input.
ARCFACE_DST = np.array(
    [
        [38.2946, 51.6963],  # Left Eye
        [73.5318, 51.5014],  # Right Eye
        [56.0252, 71.7366],  # Nose Tip
        [41.5493, 92.3655],  # Left Mouth Corner
        [70.7299, 92.2041],  # Right Mouth Corner
    ],
    dtype=np.float32,
)


@dataclass
class FaceSample:
    person_name: str
    image_path: str
    embedding: np.ndarray
    quality_score: float
    face_width: float
    blur_var: float
    yaw_ratio: float
    det_score: float
    used_border_fallback: bool


def load_image_unicode(path: Path) -> np.ndarray | None:
    """Read an image safely on Windows even when paths contain Unicode characters."""
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
        if buf.size == 0:
            return None
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None


def make_ort_session(onnx_path: Path, threads: int = 2) -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = max(1, int(threads))
    opts.inter_op_num_threads = 1
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"])


def _nms_xyxy(boxes: np.ndarray, scores: np.ndarray, iou_thresh: float = 0.4) -> list[int]:
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


def detect_faces_scrfd(
    det_session: ort.InferenceSession,
    img_bgr: np.ndarray,
    *,
    input_size: tuple[int, int] = (640, 640),
    conf_thresh: float = 0.45,
    nms_thresh: float = 0.40,
) -> tuple[np.ndarray, np.ndarray]:
    """Run SCRFD ONNX face detection and return (boxes_xyxy_score, kps_5x2)."""
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

    input_name = det_session.get_inputs()[0].name
    outputs = det_session.run(None, {input_name: blob})

    # Group tensors by spatial stride row-count and trailing channel dim (1=score, 4=bbox, 10=kps)
    strides = [8, 16, 32]
    by_rows: dict[int, dict[int, np.ndarray]] = {}
    for out in outputs:
        arr = out[0] if out.ndim == 3 else out
        if arr.ndim == 1:
            arr = arr[:, None]
        by_rows.setdefault(arr.shape[0], {})[arr.shape[1]] = arr

    all_boxes: list[np.ndarray] = []
    all_scores: list[np.ndarray] = []
    all_kps: list[np.ndarray] = []

    for stride in strides:
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

        # Anchor grid in (x, y) order matching SCRFD layout
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

    keep = _nms_xyxy(cat_boxes, cat_scores, iou_thresh=nms_thresh)
    boxes_out = np.hstack([cat_boxes[keep], cat_scores[keep][:, None]]).astype(np.float32)
    kps_out = cat_kps[keep].astype(np.float32)
    return boxes_out, kps_out


def detect_with_tight_crop_fallback(
    det_session: ort.InferenceSession,
    img_bgr: np.ndarray,
    conf_thresh: float = 0.45,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """Run SCRFD; if no faces found on tight crop, retry once with a 40% border."""
    boxes, kps = detect_faces_scrfd(det_session, img_bgr, conf_thresh=conf_thresh)
    if len(boxes) > 0:
        return boxes, kps, False

    h, w = img_bgr.shape[:2]
    pad_x = max(24, int(round(w * 0.40)))
    pad_y = max(24, int(round(h * 0.40)))
    bordered = cv2.copyMakeBorder(
        img_bgr,
        pad_y,
        pad_y,
        pad_x,
        pad_x,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )
    boxes_b, kps_b = detect_faces_scrfd(det_session, bordered, conf_thresh=max(0.35, conf_thresh - 0.05))
    if len(boxes_b) == 0:
        return boxes_b, kps_b, True

    boxes_b[:, [0, 2]] = np.clip(boxes_b[:, [0, 2]] - pad_x, 0.0, float(w))
    boxes_b[:, [1, 3]] = np.clip(boxes_b[:, [1, 3]] - pad_y, 0.0, float(h))
    kps_b[:, :, 0] -= pad_x
    kps_b[:, :, 1] -= pad_y
    return boxes_b, kps_b, True


def compute_face_quality(
    img_bgr: np.ndarray,
    box_xyxys: np.ndarray,
    kps_5x2: np.ndarray,
) -> tuple[float, float, float]:
    """Return (face_width_px, laplacian_blur_var, yaw_asymmetry_ratio)."""
    h, w = img_bgr.shape[:2]
    x1 = max(0, int(round(float(box_xyxys[0]))))
    y1 = max(0, int(round(float(box_xyxys[1]))))
    x2 = min(w, int(round(float(box_xyxys[2]))))
    y2 = min(h, int(round(float(box_xyxys[3]))))
    face_w = float(max(0, x2 - x1))
    face_h = float(max(0, y2 - y1))
    if face_w < 8 or face_h < 8:
        return face_w, 0.0, 1.0

    crop = img_bgr[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    le_x = float(kps_5x2[0, 0])
    re_x = float(kps_5x2[1, 0])
    nose_x = float(kps_5x2[2, 0])
    eye_span = abs(re_x - le_x)
    if re_x <= le_x or eye_span < 4.0:
        yaw_ratio = 1.0
    else:
        d_left = nose_x - le_x
        d_right = re_x - nose_x
        yaw_ratio = abs(d_left - d_right) / max(eye_span, 1.0)

    return face_w, blur_var, yaw_ratio


def align_and_embed(
    rec_session: ort.InferenceSession,
    img_bgr: np.ndarray,
    kps_5x2: np.ndarray,
) -> np.ndarray | None:
    """Warp face to canonical 112x112 ArcFace template and compute L2-normalized 512-D embedding."""
    M, _ = cv2.estimateAffinePartial2D(kps_5x2.astype(np.float32), ARCFACE_DST, method=cv2.LMEDS)
    if M is None:
        M, _ = cv2.estimateAffinePartial2D(kps_5x2.astype(np.float32), ARCFACE_DST, method=cv2.RANSAC)
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
    input_name = rec_session.get_inputs()[0].name
    emb = rec_session.run(None, {input_name: blob})[0].reshape(-1).astype(np.float32)
    norm = float(np.linalg.norm(emb))
    if norm < 1e-8 or not np.isfinite(norm):
        return None
    return emb / norm


def select_diverse_representatives(
    embeddings: np.ndarray,
    qualities: np.ndarray,
    centroid: np.ndarray,
    max_reps: int,
) -> np.ndarray:
    """Pick up to `max_reps` diverse L2-normalized embeddings via greedy farthest-point sampling."""
    n = len(embeddings)
    if n <= max_reps:
        return np.arange(n, dtype=np.int32)

    sims_to_centroid = embeddings @ centroid
    # Seed with the highest-quality face that stays well aligned with the centroid
    seed_score = sims_to_centroid + 0.15 * (qualities / max(float(np.max(qualities)), 1.0))
    selected = [int(np.argmax(seed_score))]
    # Track max similarity to any already-selected representative (lower = more diverse)
    max_sim_to_sel = embeddings @ embeddings[selected[0]]

    while len(selected) < max_reps:
        candidate_scores = max_sim_to_sel - 0.08 * sims_to_centroid
        for idx in selected:
            candidate_scores[idx] = 1e9
        next_idx = int(np.argmin(candidate_scores))
        selected.append(next_idx)
        max_sim_to_sel = np.maximum(max_sim_to_sel, embeddings @ embeddings[next_idx])

    return np.array(selected, dtype=np.int32)


def run_loo_evaluation(
    samples_by_person: dict[str, list[FaceSample]],
    max_reps: int,
) -> dict[str, Any]:
    """Leave-One-Out evaluation comparing centroid-only vs centroid+representatives matching."""
    persons = sorted(samples_by_person.keys())
    if len(persons) < 2:
        return {"skipped": True, "reason": "Fewer than 2 people"}

    all_embs = np.vstack([s.embedding for p in persons for s in samples_by_person[p]]).astype(np.float32)
    all_quals = np.array([s.quality_score for p in persons for s in samples_by_person[p]], dtype=np.float32)
    all_labels: list[str] = [p for p in persons for _ in samples_by_person[p]]

    # Precompute full-gallery centroids for inter-class similarity analysis
    full_centroids = []
    for p in persons:
        mat = np.vstack([s.embedding for s in samples_by_person[p]])
        c = mat.mean(axis=0)
        c /= max(float(np.linalg.norm(c)), 1e-8)
        full_centroids.append(c)
    full_c_mat = np.vstack(full_centroids)
    inter_mat = full_c_mat @ full_c_mat.T
    closest_pairs: list[dict[str, Any]] = []
    for i in range(len(persons)):
        for j in range(i + 1, len(persons)):
            closest_pairs.append(
                {
                    "pair": [persons[i], persons[j]],
                    "centroid_cosine": round(float(inter_mat[i, j]), 4),
                }
            )
    closest_pairs.sort(key=lambda x: x["centroid_cosine"], reverse=True)

    # LOO loop
    centroid_correct = 0
    hybrid_correct = 0
    total_eval = 0
    intra_scores: list[float] = []
    margins_hybrid: list[float] = []
    confusions: list[dict[str, Any]] = []

    idx_offset = 0
    person_ranges: dict[str, tuple[int, int]] = {}
    for p in persons:
        cnt = len(samples_by_person[p])
        person_ranges[p] = (idx_offset, idx_offset + cnt)
        idx_offset += cnt

    for i, true_person in enumerate(all_labels):
        p_start, p_end = person_ranges[true_person]
        if p_end - p_start < 2:
            continue  # Cannot LOO a single-sample person without removing them from gallery

        probe = all_embs[i]
        gallery_centroids: list[np.ndarray] = []
        gallery_reps: list[np.ndarray] = []
        gallery_rep_pidx: list[int] = []

        for pidx, p in enumerate(persons):
            s_idx, e_idx = person_ranges[p]
            mask = np.ones(e_idx - s_idx, dtype=bool)
            if p == true_person:
                mask[i - s_idx] = False
            sub_embs = all_embs[s_idx:e_idx][mask]
            sub_quals = all_quals[s_idx:e_idx][mask]

            c = sub_embs.mean(axis=0)
            c /= max(float(np.linalg.norm(c)), 1e-8)
            gallery_centroids.append(c)

            rep_idx = select_diverse_representatives(sub_embs, sub_quals, c, max_reps=max_reps)
            for r_i in rep_idx:
                gallery_reps.append(sub_embs[r_i])
                gallery_rep_pidx.append(pidx)

        c_mat = np.vstack(gallery_centroids)
        c_scores = c_mat @ probe
        c_pred_idx = int(np.argmax(c_scores))
        if persons[c_pred_idx] == true_person:
            centroid_correct += 1

        rep_mat = np.vstack(gallery_reps)
        rep_scores = rep_mat @ probe
        rep_pidx_arr = np.array(gallery_rep_pidx, dtype=np.int32)
        hybrid_scores = np.array(
            [
                max(float(c_scores[pidx]), float(np.max(rep_scores[rep_pidx_arr == pidx])))
                for pidx in range(len(persons))
            ],
            dtype=np.float32,
        )

        sorted_order = np.argsort(hybrid_scores)[::-1]
        best_idx = int(sorted_order[0])
        second_idx = int(sorted_order[1])
        true_idx = persons.index(true_person)

        intra_scores.append(float(hybrid_scores[true_idx]))
        margins_hybrid.append(float(hybrid_scores[best_idx] - hybrid_scores[second_idx]))

        if persons[best_idx] == true_person:
            hybrid_correct += 1
        else:
            sample_ref = samples_by_person[true_person][i - p_start]
            confusions.append(
                {
                    "true": true_person,
                    "predicted": persons[best_idx],
                    "best_score": round(float(hybrid_scores[best_idx]), 4),
                    "true_score": round(float(hybrid_scores[true_idx]), 4),
                    "file": Path(sample_ref.image_path).name,
                }
            )
        total_eval += 1

    intra_arr = np.array(intra_scores, dtype=np.float32) if intra_scores else np.array([0.0])
    margin_arr = np.array(margins_hybrid, dtype=np.float32) if margins_hybrid else np.array([0.0])

    return {
        "evaluated_samples": total_eval,
        "centroid_top1_acc": round(centroid_correct / max(total_eval, 1), 4),
        "hybrid_top1_acc": round(hybrid_correct / max(total_eval, 1), 4),
        "intra_cosine": {
            "min": round(float(np.min(intra_arr)), 4),
            "p10": round(float(np.percentile(intra_arr, 10)), 4),
            "median": round(float(np.median(intra_arr)), 4),
            "mean": round(float(np.mean(intra_arr)), 4),
        },
        "margin_best_minus_second": {
            "min": round(float(np.min(margin_arr)), 4),
            "p10": round(float(np.percentile(margin_arr, 10)), 4),
            "median": round(float(np.median(margin_arr)), 4),
        },
        "closest_inter_person_pairs": closest_pairs[:5],
        "confusions": confusions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Enroll face image folders into ONNX gallery (.npz).")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    parser.add_argument("--det-model", type=str, default="det_500m.onnx")
    parser.add_argument("--rec-model", type=str, default="w600k_mbf.onnx")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--max-reps", type=int, default=8)
    parser.add_argument("--min-width", type=float, default=48.0)
    parser.add_argument("--min-blur", type=float, default=25.0)
    parser.add_argument("--max-yaw-ratio", type=float, default=0.55)
    parser.add_argument("--outlier-min-cos", type=float, default=0.30)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    if not args.input.is_dir():
        raise FileNotFoundError(f"Face dataset directory not found: {args.input}")

    det_path = args.models_dir / args.det_model
    rec_path = args.models_dir / args.rec_model
    if not det_path.is_file():
        raise FileNotFoundError(f"Detector model missing: {det_path}")
    if not rec_path.is_file():
        raise FileNotFoundError(f"Recognition model missing: {rec_path}")

    t_start = time.perf_counter()
    det_session = make_ort_session(det_path, threads=args.threads)
    rec_session = make_ort_session(rec_path, threads=args.threads)

    person_dirs = sorted([d for d in args.input.iterdir() if d.is_dir()], key=lambda d: d.name.casefold())
    if not person_dirs:
        raise RuntimeError(f"No person subdirectories found under {args.input}")

    samples_by_person: dict[str, list[FaceSample]] = {}
    rejected_log: list[dict[str, str]] = []
    outliers_log: list[dict[str, Any]] = []

    for pdir in person_dirs:
        person_name = pdir.name
        img_files = sorted(
            [
                f
                for f in pdir.rglob("*")
                if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
            ],
            key=lambda f: f.name.casefold(),
        )
        accepted: list[FaceSample] = []

        for img_file in img_files:
            img = load_image_unicode(img_file)
            if img is None:
                rejected_log.append({"person": person_name, "file": img_file.name, "reason": "decode_error"})
                continue

            boxes, kps, used_fallback = detect_with_tight_crop_fallback(det_session, img)
            if len(boxes) == 0:
                rejected_log.append({"person": person_name, "file": img_file.name, "reason": "no_face_detected"})
                continue

            # Select largest * high-score face when multiple appear in a photo
            areas = np.maximum(1.0, (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1]))
            pick_idx = int(np.argmax(boxes[:, 4] * np.sqrt(areas)))
            box = boxes[pick_idx]
            kp = kps[pick_idx]

            face_w, blur_var, yaw_ratio = compute_face_quality(img, box, kp)
            if face_w < args.min_width:
                rejected_log.append(
                    {"person": person_name, "file": img_file.name, "reason": f"small_face({face_w:.0f}px)"}
                )
                continue
            if blur_var < args.min_blur:
                rejected_log.append(
                    {"person": person_name, "file": img_file.name, "reason": f"blur({blur_var:.1f})"}
                )
                continue
            if yaw_ratio > args.max_yaw_ratio:
                rejected_log.append(
                    {"person": person_name, "file": img_file.name, "reason": f"yaw({yaw_ratio:.2f})"}
                )
                continue

            emb = align_and_embed(rec_session, img, kp)
            if emb is None:
                rejected_log.append({"person": person_name, "file": img_file.name, "reason": "align_embed_failed"})
                continue

            quality_score = float(
                box[4]
                * min(1.0, face_w / 140.0)
                * min(1.0, blur_var / 150.0)
                * max(0.2, 1.0 - yaw_ratio)
            )
            accepted.append(
                FaceSample(
                    person_name=person_name,
                    image_path=str(img_file),
                    embedding=emb,
                    quality_score=quality_score,
                    face_width=face_w,
                    blur_var=blur_var,
                    yaw_ratio=yaw_ratio,
                    det_score=float(box[4]),
                    used_border_fallback=used_fallback,
                )
            )

        # Outlier rejection relative to initial person centroid (only when >= 4 valid photos)
        if len(accepted) >= 4:
            mat0 = np.vstack([s.embedding for s in accepted])
            c0 = mat0.mean(axis=0)
            c0 /= max(float(np.linalg.norm(c0)), 1e-8)
            sims0 = mat0 @ c0
            filtered: list[FaceSample] = []
            for sample, sim in zip(accepted, sims0):
                if float(sim) < args.outlier_min_cos:
                    outliers_log.append(
                        {
                            "person": person_name,
                            "file": Path(sample.image_path).name,
                            "cosine_to_centroid": round(float(sim), 4),
                        }
                    )
                else:
                    filtered.append(sample)
            if len(filtered) >= 2:
                accepted = filtered

        if accepted:
            samples_by_person[person_name] = accepted
        print(
            f"[enroll] {person_name}: total={len(img_files)}, accepted={len(accepted)}, "
            f"rejected={len(img_files) - len(accepted)}"
        )

    if not samples_by_person:
        raise RuntimeError("No valid face embeddings extracted across dataset.")

    # Build final gallery arrays
    person_names = sorted(samples_by_person.keys())
    centroids_list: list[np.ndarray] = []
    rep_embs_list: list[np.ndarray] = []
    rep_pidx_list: list[int] = []
    rep_quals_list: list[float] = []

    for pidx, pname in enumerate(person_names):
        plist = samples_by_person[pname]
        mat = np.vstack([s.embedding for s in plist]).astype(np.float32)
        quals = np.array([s.quality_score for s in plist], dtype=np.float32)
        centroid = mat.mean(axis=0)
        centroid /= max(float(np.linalg.norm(centroid)), 1e-8)
        centroids_list.append(centroid.astype(np.float32))

        rep_idx = select_diverse_representatives(mat, quals, centroid, max_reps=args.max_reps)
        for ri in rep_idx:
            rep_embs_list.append(mat[ri])
            rep_pidx_list.append(pidx)
            rep_quals_list.append(float(quals[ri]))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        person_names=np.array(person_names, dtype=np.str_),
        centroids=np.vstack(centroids_list).astype(np.float32),
        rep_embeddings=np.vstack(rep_embs_list).astype(np.float32),
        rep_person_idx=np.array(rep_pidx_list, dtype=np.int32),
        rep_qualities=np.array(rep_quals_list, dtype=np.float32),
        rec_model=np.array([args.rec_model], dtype=np.str_),
        det_model=np.array([args.det_model], dtype=np.str_),
        created_at=np.array([time.time()], dtype=np.float64),
    )

    elapsed_s = time.perf_counter() - t_start
    print(
        f"\n[SAVED] {args.output} ({args.output.stat().st_size / 1024:.1f} KB, "
        f"{len(person_names)} people, {len(rep_embs_list)} reps) in {elapsed_s:.2f}s"
    )

    if args.report:
        loo = run_loo_evaluation(samples_by_person, max_reps=args.max_reps)
        report = {
            "rec_model": args.rec_model,
            "det_model": args.det_model,
            "people_counts": {p: len(samples_by_person[p]) for p in person_names},
            "rejected_count": len(rejected_log),
            "rejected_samples": rejected_log[:25],
            "outliers_dropped": outliers_log,
            "loo_evaluation": loo,
        }
        print("\n=== ENROLLMENT QUALITY & LOO REPORT ===")
        print(json.dumps(report, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
