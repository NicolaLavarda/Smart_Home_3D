from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np

from .crop_store import BiometricCropStore
from .models import FaceEvaluation, PlateEvaluation, TrackBiometricUpdate
from .plate_postprocessor import PlateWhitelistMatcher


@dataclass
class _TrackModalState:
    track_id: int
    modality: Literal["face", "alpr"]
    attempts_count: int = 0
    valid_eval_count: int = 0
    last_attempt_ts: float = 0.0
    locked: bool = False
    status: Literal["pending", "locked", "unknown"] = "pending"
    votes: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    best_conf_by_label: dict[str, float] = field(default_factory=dict)
    meta_by_label: dict[str, dict[str, Optional[str]]] = field(default_factory=dict)
    best_crop_score: float = -1.0
    best_crop_id: Optional[str] = None
    best_crop_relpath: Optional[str] = None


class TrackBiometricConsensusManager:
    """
    Accumulates weighted multi-frame biometric votes per (track_id, modality),
    locks identity/plate once K concordant observations reach threshold, and stores
    solely the single best JPEG crop per track.
    """

    def __init__(
        self,
        *,
        crop_store: Optional[BiometricCropStore] = None,
        whitelist_matcher: Optional[PlateWhitelistMatcher] = None,
        face_consensus_k: int = 2,
        alpr_consensus_k: int = 2,
        min_eval_interval_s: float = 0.6,
        max_fast_attempts: int = 6,
        unknown_backoff_s: float = 4.0,
        whitelist_max_distance: int = 1,
        min_plate_confidence_std: float = 0.55,
        min_plate_confidence_generic: float = 0.72,
    ) -> None:
        self.crop_store = crop_store
        self.whitelist_matcher = whitelist_matcher
        self.face_consensus_k = max(1, int(face_consensus_k))
        self.alpr_consensus_k = max(1, int(alpr_consensus_k))
        self.min_eval_interval_s = max(0.0, float(min_eval_interval_s))
        self.max_fast_attempts = max(1, int(max_fast_attempts))
        self.unknown_backoff_s = max(self.min_eval_interval_s, float(unknown_backoff_s))
        self.whitelist_max_distance = max(0, int(whitelist_max_distance))
        self.min_plate_confidence_std = max(0.0, float(min_plate_confidence_std))
        self.min_plate_confidence_generic = max(0.0, float(min_plate_confidence_generic))

        self._lock = threading.RLock()
        self._states: dict[tuple[int, str], _TrackModalState] = {}

    def is_locked(self, track_id: int, modality: Literal["face", "alpr"]) -> bool:
        with self._lock:
            st = self._states.get((track_id, modality))
            return bool(st and st.locked)

    def can_attempt(self, track_id: int, modality: Literal["face", "alpr"], now_ts: Optional[float] = None) -> bool:
        now = float(now_ts if now_ts is not None else time.time())
        with self._lock:
            st = self._states.get((track_id, modality))
            if st is None:
                return True
            if st.locked:
                return False
            dt = now - st.last_attempt_ts
            cooldown = self.unknown_backoff_s if st.attempts_count >= self.max_fast_attempts else self.min_eval_interval_s
            return dt >= cooldown

    def mark_dispatched(self, track_id: int, modality: Literal["face", "alpr"], now_ts: Optional[float] = None) -> None:
        now = float(now_ts if now_ts is not None else time.time())
        with self._lock:
            key = (track_id, modality)
            st = self._states.get(key)
            if st is None:
                st = _TrackModalState(track_id=track_id, modality=modality)
                self._states[key] = st
            st.last_attempt_ts = now

    def _maybe_save_best_crop(
        self,
        st: _TrackModalState,
        crop_bgr: Optional[np.ndarray],
        crop_score: float,
        timestamp: float,
    ) -> None:
        if self.crop_store is None or crop_bgr is None or crop_bgr.size == 0:
            return
        if crop_score <= st.best_crop_score and st.best_crop_id is not None:
            return
        crop_id = f"{int(timestamp)}_{st.track_id}_{st.modality}_{st.attempts_count}"
        try:
            saved_id, relpath = self.crop_store.save_best_crop(
                crop_id,
                crop_bgr,
                timestamp=timestamp,
                previous_relpath=st.best_crop_relpath,
            )
            st.best_crop_id = saved_id
            st.best_crop_relpath = relpath
            st.best_crop_score = crop_score
        except Exception:
            pass

    def record_face_evaluation(
        self,
        track_id: int,
        evaluation: Optional[FaceEvaluation],
        *,
        camera_id: str,
        timestamp: float,
        camera_weight: float = 1.0,
    ) -> Optional[TrackBiometricUpdate]:
        with self._lock:
            key = (track_id, "face")
            st = self._states.setdefault(key, _TrackModalState(track_id=track_id, modality="face"))
            if st.locked:
                return None

            st.attempts_count += 1
            st.last_attempt_ts = timestamp

            if evaluation is not None:
                crop_rank = float(evaluation.quality_score) * float(camera_weight)
                self._maybe_save_best_crop(st, evaluation.crop_bgr, crop_rank, timestamp)

                if evaluation.metrics.passed and evaluation.identity:
                    st.valid_eval_count += 1
                    label = evaluation.identity
                    weight = max(0.05, float(evaluation.similarity) * max(0.2, float(evaluation.quality_score)) * float(camera_weight))
                    st.votes[label] = st.votes.get(label, 0.0) + weight
                    st.counts[label] = st.counts.get(label, 0) + 1
                    st.best_conf_by_label[label] = max(st.best_conf_by_label.get(label, 0.0), float(evaluation.similarity))

            return self._finalize_face_state(st, camera_id=camera_id, timestamp=timestamp)

    def _finalize_face_state(
        self,
        st: _TrackModalState,
        *,
        camera_id: str,
        timestamp: float,
    ) -> Optional[TrackBiometricUpdate]:
        if st.votes:
            winner = max(st.votes, key=lambda k: st.votes[k])
            win_count = st.counts[winner]
            win_conf = st.best_conf_by_label[winner]
            if win_count >= self.face_consensus_k:
                st.locked = True
                st.status = "locked"
                return TrackBiometricUpdate(
                    track_id=st.track_id,
                    modality="face",
                    identity=winner,
                    identity_confidence=round(win_conf, 4),
                    biometric_locked=True,
                    biometric_status="locked",
                    attempts_count=st.attempts_count,
                    best_crop_id=st.best_crop_id,
                    best_crop_relpath=st.best_crop_relpath,
                    quality_score=round(max(st.best_crop_score, 0.0), 4),
                    camera_id=camera_id,
                    timestamp=timestamp,
                )
            return TrackBiometricUpdate(
                track_id=st.track_id,
                modality="face",
                identity=winner,
                identity_confidence=round(win_conf, 4),
                biometric_locked=False,
                biometric_status="pending",
                attempts_count=st.attempts_count,
                best_crop_id=st.best_crop_id,
                best_crop_relpath=st.best_crop_relpath,
                quality_score=round(max(st.best_crop_score, 0.0), 4),
                camera_id=camera_id,
                timestamp=timestamp,
            )

        if st.attempts_count >= self.max_fast_attempts:
            was_unknown = st.status == "unknown"
            st.status = "unknown"
            if not was_unknown or st.best_crop_id is not None:
                return TrackBiometricUpdate(
                    track_id=st.track_id,
                    modality="face",
                    identity=None,
                    identity_confidence=0.0,
                    biometric_locked=False,
                    biometric_status="unknown",
                    attempts_count=st.attempts_count,
                    best_crop_id=st.best_crop_id,
                    best_crop_relpath=st.best_crop_relpath,
                    quality_score=round(max(st.best_crop_score, 0.0), 4),
                    camera_id=camera_id,
                    timestamp=timestamp,
                )
        return None

    def record_plate_evaluation(
        self,
        track_id: int,
        evaluation: Optional[PlateEvaluation],
        *,
        camera_id: str,
        timestamp: float,
        camera_weight: float = 1.0,
    ) -> Optional[TrackBiometricUpdate]:
        with self._lock:
            key = (track_id, "alpr")
            st = self._states.setdefault(key, _TrackModalState(track_id=track_id, modality="alpr"))
            if st.locked:
                return None

            st.attempts_count += 1
            st.last_attempt_ts = timestamp

            if evaluation is not None:
                crop_rank = float(evaluation.quality_score) * float(camera_weight)
                self._maybe_save_best_crop(st, evaluation.crop_bgr, crop_rank, timestamp)

                if evaluation.metrics.passed and evaluation.plate:
                    label = evaluation.plate
                    fmt = (evaluation.plate_format or "").strip().upper()
                    conf = float(evaluation.confidence)
                    is_exact_wl = bool(
                        self.whitelist_matcher is not None
                        and self.whitelist_matcher.match(label, max_distance=0)[0] is not None
                    )
                    if not is_exact_wl:
                        if fmt == "EU_GENERIC":
                            if len(label) < 5 or conf < self.min_plate_confidence_generic:
                                return self._finalize_alpr_state(st, camera_id=camera_id, timestamp=timestamp)
                        elif conf < self.min_plate_confidence_std:
                            return self._finalize_alpr_state(st, camera_id=camera_id, timestamp=timestamp)

                    st.valid_eval_count += 1
                    weight = max(0.05, conf * max(0.2, float(evaluation.quality_score)) * float(camera_weight))
                    st.votes[label] = st.votes.get(label, 0.0) + weight
                    st.counts[label] = st.counts.get(label, 0) + 1
                    st.best_conf_by_label[label] = max(st.best_conf_by_label.get(label, 0.0), conf)
                    st.meta_by_label[label] = {
                        "plate_raw": evaluation.plate_raw,
                        "plate_format": evaluation.plate_format,
                    }

            return self._finalize_alpr_state(st, camera_id=camera_id, timestamp=timestamp)

    def _finalize_alpr_state(
        self,
        st: _TrackModalState,
        *,
        camera_id: str,
        timestamp: float,
    ) -> Optional[TrackBiometricUpdate]:
        if st.votes:
            winner = max(st.votes, key=lambda k: st.votes[k])
            win_count = st.counts[winner]
            win_conf = st.best_conf_by_label[winner]
            meta = st.meta_by_label.get(winner, {})

            if win_count >= self.alpr_consensus_k:
                st.locked = True
                st.status = "locked"
                wl_entry = None
                if self.whitelist_matcher is not None:
                    wl_entry, _dist = self.whitelist_matcher.match(
                        winner,
                        max_distance=self.whitelist_max_distance,
                    )
                resolved_plate = wl_entry.plate if wl_entry is not None else winner
                return TrackBiometricUpdate(
                    track_id=st.track_id,
                    modality="alpr",
                    identity=wl_entry.owner_name if wl_entry is not None else None,
                    identity_confidence=round(win_conf, 4) if wl_entry is not None else 0.0,
                    plate=resolved_plate,
                    plate_raw=meta.get("plate_raw"),
                    plate_confidence=round(win_conf, 4),
                    plate_format=meta.get("plate_format"),
                    plate_whitelisted=bool(wl_entry is not None),
                    plate_owner=wl_entry.owner_name if wl_entry is not None else None,
                    biometric_locked=True,
                    biometric_status="locked",
                    attempts_count=st.attempts_count,
                    best_crop_id=st.best_crop_id,
                    best_crop_relpath=st.best_crop_relpath,
                    quality_score=round(max(st.best_crop_score, 0.0), 4),
                    camera_id=camera_id,
                    timestamp=timestamp,
                )

            return TrackBiometricUpdate(
                track_id=st.track_id,
                modality="alpr",
                plate=winner,
                plate_raw=meta.get("plate_raw"),
                plate_confidence=round(win_conf, 4),
                plate_format=meta.get("plate_format"),
                biometric_locked=False,
                biometric_status="pending",
                attempts_count=st.attempts_count,
                best_crop_id=st.best_crop_id,
                best_crop_relpath=st.best_crop_relpath,
                quality_score=round(max(st.best_crop_score, 0.0), 4),
                camera_id=camera_id,
                timestamp=timestamp,
            )

        if st.attempts_count >= self.max_fast_attempts:
            was_unknown = st.status == "unknown"
            st.status = "unknown"
            if not was_unknown or st.best_crop_id is not None:
                return TrackBiometricUpdate(
                    track_id=st.track_id,
                    modality="alpr",
                    plate=None,
                    plate_confidence=0.0,
                    biometric_locked=False,
                    biometric_status="unknown",
                    attempts_count=st.attempts_count,
                    best_crop_id=st.best_crop_id,
                    best_crop_relpath=st.best_crop_relpath,
                    quality_score=round(max(st.best_crop_score, 0.0), 4),
                    camera_id=camera_id,
                    timestamp=timestamp,
                )
        return None

    def prune_inactive_tracks(self, active_track_ids: set[int]) -> None:
        with self._lock:
            stale = [k for k in self._states if k[0] not in active_track_ids]
            for k in stale:
                del self._states[k]
