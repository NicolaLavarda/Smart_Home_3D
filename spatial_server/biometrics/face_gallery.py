from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("spatial_server.biometrics.gallery")


@dataclass(frozen=True)
class FaceGalleryMatch:
    identity: Optional[str]
    score: float
    second_best_score: float
    margin: float
    passed: bool


def _l2_normalize_rows(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    return (mat / norms).astype(np.float32)


def _select_diverse_representatives(
    embeddings: np.ndarray,
    qualities: np.ndarray,
    centroid: np.ndarray,
    max_reps: int,
) -> np.ndarray:
    n = len(embeddings)
    if n <= max_reps:
        return np.arange(n, dtype=np.int32)

    sims_to_centroid = embeddings @ centroid
    max_q = max(float(np.max(qualities)), 1.0)
    seed_score = sims_to_centroid + 0.15 * (qualities / max_q)
    selected = [int(np.argmax(seed_score))]
    max_sim_to_sel = embeddings @ embeddings[selected[0]]

    while len(selected) < max_reps:
        candidate_scores = max_sim_to_sel - 0.08 * sims_to_centroid
        for idx in selected:
            candidate_scores[idx] = 1e9
        next_idx = int(np.argmin(candidate_scores))
        selected.append(next_idx)
        max_sim_to_sel = np.maximum(max_sim_to_sel, embeddings @ embeddings[next_idx])

    return np.array(selected, dtype=np.int32)


class FaceGalleryIndex:
    """Thread-safe vectorized cosine-similarity face gallery backed by `.npz`."""

    def __init__(self, gallery_path: Optional[Path] = None, max_reps_per_person: int = 8) -> None:
        self.gallery_path = Path(gallery_path) if gallery_path else None
        self.max_reps_per_person = max(1, int(max_reps_per_person))
        self._lock = threading.RLock()

        self.person_names: list[str] = []
        self.centroids: np.ndarray = np.empty((0, 512), dtype=np.float32)
        self.rep_embeddings: np.ndarray = np.empty((0, 512), dtype=np.float32)
        self.rep_person_idx: np.ndarray = np.empty((0,), dtype=np.int32)
        self.rep_qualities: np.ndarray = np.empty((0,), dtype=np.float32)
        self.rec_model_name: str = ""
        self.det_model_name: str = ""

        if self.gallery_path is not None and self.gallery_path.is_file():
            self.load(self.gallery_path)

    @property
    def person_count(self) -> int:
        with self._lock:
            return len(self.person_names)

    @property
    def rep_count(self) -> int:
        with self._lock:
            return int(len(self.rep_embeddings))

    def load(self, path: Optional[Path] = None) -> bool:
        target = Path(path or self.gallery_path or "")
        if not target or not target.is_file():
            return False

        with self._lock:
            try:
                with np.load(target, allow_pickle=False) as data:
                    names = [str(x) for x in data["person_names"].tolist()]
                    if not names:
                        self._clear_locked()
                        return True
                    centroids = _l2_normalize_rows(np.asarray(data["centroids"], dtype=np.float32).reshape(len(names), -1))
                    rep_embs = np.asarray(data["rep_embeddings"], dtype=np.float32)
                    if rep_embs.size > 0:
                        rep_embs = _l2_normalize_rows(rep_embs.reshape(-1, centroids.shape[1]))
                    else:
                        rep_embs = np.empty((0, centroids.shape[1]), dtype=np.float32)
                    rep_pidx = np.asarray(data["rep_person_idx"], dtype=np.int32).reshape(-1)
                    rep_quals = (
                        np.asarray(data["rep_qualities"], dtype=np.float32).reshape(-1)
                        if "rep_qualities" in data
                        else np.ones(len(rep_pidx), dtype=np.float32)
                    )
                    self.person_names = names
                    self.centroids = centroids
                    self.rep_embeddings = rep_embs
                    self.rep_person_idx = rep_pidx
                    self.rep_qualities = rep_quals
                    if "rec_model" in data and data["rec_model"].size > 0:
                        self.rec_model_name = str(data["rec_model"].flat[0])
                    if "det_model" in data and data["det_model"].size > 0:
                        self.det_model_name = str(data["det_model"].flat[0])
                logger.info("Loaded face gallery %s (%d people, %d reps)", target.name, len(self.person_names), len(self.rep_embeddings))
                return True
            except Exception as exc:
                logger.warning("Failed to load face gallery %s: %s", target, exc)
                return False

    def reload(self) -> bool:
        return self.load(self.gallery_path)

    def _clear_locked(self) -> None:
        self.person_names = []
        self.centroids = np.empty((0, 512), dtype=np.float32)
        self.rep_embeddings = np.empty((0, 512), dtype=np.float32)
        self.rep_person_idx = np.empty((0,), dtype=np.int32)
        self.rep_qualities = np.empty((0,), dtype=np.float32)

    def save(self, path: Optional[Path] = None) -> Optional[Path]:
        target = Path(path or self.gallery_path or "")
        if not str(target):
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_suffix(".tmp.npz")
        with self._lock:
            np.savez_compressed(
                tmp_path,
                person_names=np.array(self.person_names, dtype=np.str_),
                centroids=self.centroids.astype(np.float32),
                rep_embeddings=self.rep_embeddings.astype(np.float32),
                rep_person_idx=self.rep_person_idx.astype(np.int32),
                rep_qualities=self.rep_qualities.astype(np.float32),
                rec_model=np.array([self.rec_model_name], dtype=np.str_),
                det_model=np.array([self.det_model_name], dtype=np.str_),
                created_at=np.array([time.time()], dtype=np.float64),
            )
            os.replace(tmp_path, target)
        return target

    def match(
        self,
        embedding: np.ndarray,
        *,
        match_threshold: float = 0.45,
        margin_threshold: float = 0.08,
    ) -> FaceGalleryMatch:
        """Vectorized cosine match combining per-person centroid and K representative embeddings."""
        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vec))
        if norm < 1e-8 or not np.isfinite(norm):
            return FaceGalleryMatch(identity=None, score=0.0, second_best_score=0.0, margin=0.0, passed=False)
        vec = vec / norm

        with self._lock:
            num_people = len(self.person_names)
            if num_people == 0:
                return FaceGalleryMatch(identity=None, score=0.0, second_best_score=0.0, margin=0.0, passed=False)

            scores = (self.centroids @ vec).astype(np.float32)
            if len(self.rep_embeddings) > 0:
                rep_sims = self.rep_embeddings @ vec
                np.maximum.at(scores, self.rep_person_idx, rep_sims)

            order = np.argsort(scores)[::-1]
            best_idx = int(order[0])
            best_score = float(scores[best_idx])
            second_score = float(scores[int(order[1])]) if num_people > 1 else 0.0
            margin = best_score - max(0.0, second_score)

            passed = best_score >= match_threshold and (num_people == 1 or margin >= margin_threshold)
            identity = self.person_names[best_idx] if passed else None
            return FaceGalleryMatch(
                identity=identity,
                score=round(best_score, 4),
                second_best_score=round(second_score, 4),
                margin=round(margin, 4),
                passed=passed,
            )

    def add_embedding(
        self,
        person_name: str,
        embedding: np.ndarray,
        quality: float = 0.8,
        *,
        persist: bool = True,
    ) -> None:
        """Incrementally enroll or update a person's centroid & representative embeddings."""
        clean_name = person_name.strip()
        if not clean_name:
            raise ValueError("person_name must not be empty")

        vec = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(vec))
        if norm < 1e-8:
            raise ValueError("embedding norm is zero")
        vec = (vec / norm).astype(np.float32)
        dim = vec.shape[0]

        with self._lock:
            if clean_name not in self.person_names:
                pidx = len(self.person_names)
                self.person_names.append(clean_name)
                if self.centroids.size == 0:
                    self.centroids = vec[None, :]
                else:
                    self.centroids = np.vstack([self.centroids, vec[None, :]]).astype(np.float32)
                if self.rep_embeddings.size == 0:
                    self.rep_embeddings = vec[None, :]
                    self.rep_person_idx = np.array([pidx], dtype=np.int32)
                    self.rep_qualities = np.array([float(quality)], dtype=np.float32)
                else:
                    self.rep_embeddings = np.vstack([self.rep_embeddings, vec[None, :]]).astype(np.float32)
                    self.rep_person_idx = np.concatenate([self.rep_person_idx, np.array([pidx], dtype=np.int32)])
                    self.rep_qualities = np.concatenate([self.rep_qualities, np.array([float(quality)], dtype=np.float32)])
            else:
                pidx = self.person_names.index(clean_name)
                mask = self.rep_person_idx == pidx
                existing_embs = self.rep_embeddings[mask] if np.any(mask) else np.empty((0, dim), dtype=np.float32)
                existing_quals = self.rep_qualities[mask] if np.any(mask) else np.empty((0,), dtype=np.float32)

                merged_embs = np.vstack([existing_embs, vec[None, :]]) if len(existing_embs) else vec[None, :]
                merged_quals = np.concatenate([existing_quals, np.array([float(quality)], dtype=np.float32)])

                # Update weighted centroid smoothly across old centroid + new sample
                old_weight = max(1.0, float(len(existing_embs)))
                new_centroid = self.centroids[pidx] * old_weight + vec
                c_norm = float(np.linalg.norm(new_centroid))
                if c_norm > 1e-8:
                    self.centroids[pidx] = (new_centroid / c_norm).astype(np.float32)

                keep_idx = _select_diverse_representatives(
                    merged_embs, merged_quals, self.centroids[pidx], self.max_reps_per_person
                )
                kept_embs = merged_embs[keep_idx]
                kept_quals = merged_quals[keep_idx]

                other_mask = ~mask
                self.rep_embeddings = (
                    np.vstack([self.rep_embeddings[other_mask], kept_embs]).astype(np.float32)
                    if np.any(other_mask)
                    else kept_embs.astype(np.float32)
                )
                self.rep_person_idx = np.concatenate(
                    [
                        self.rep_person_idx[other_mask],
                        np.full(len(kept_embs), pidx, dtype=np.int32),
                    ]
                )
                self.rep_qualities = np.concatenate([self.rep_qualities[other_mask], kept_quals])

            if persist and self.gallery_path is not None:
                self.save(self.gallery_path)

    def remove_person(self, person_name: str, *, persist: bool = True) -> bool:
        """Remove a person and re-index all remaining gallery entries."""
        clean_name = person_name.strip()
        with self._lock:
            if clean_name not in self.person_names:
                return False
            rm_idx = self.person_names.index(clean_name)
            self.person_names.pop(rm_idx)

            if not self.person_names:
                self._clear_locked()
            else:
                keep_rows = np.arange(len(self.centroids)) != rm_idx
                self.centroids = self.centroids[keep_rows]
                rep_keep = self.rep_person_idx != rm_idx
                self.rep_embeddings = self.rep_embeddings[rep_keep]
                self.rep_qualities = self.rep_qualities[rep_keep]
                new_pidx = self.rep_person_idx[rep_keep].copy()
                new_pidx[new_pidx > rm_idx] -= 1
                self.rep_person_idx = new_pidx

            if persist and self.gallery_path is not None:
                self.save(self.gallery_path)
            return True

    def list_identities(self) -> list[dict[str, Any]]:
        with self._lock:
            out: list[dict[str, Any]] = []
            for pidx, name in enumerate(self.person_names):
                cnt = int(np.sum(self.rep_person_idx == pidx)) if len(self.rep_person_idx) else 0
                out.append({"name": name, "samples_count": cnt})
            return out
