from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from scipy.optimize import linear_sum_assignment

from spatial_server.domain.models import SpatialPoint3D, TrackedEntity3D
from .interfaces import IMultiTargetTracker3D, TrackObservation3D


def _coarse_class(label: str) -> str:
    if label in ("car", "truck", "bus", "motorcycle"):
        return "vehicle"
    return label


@dataclass
class _KalmanTrack:
    track_id: int
    class_label: str
    x: np.ndarray              # [x, y, z, vx, vy, vz]
    P: np.ndarray              # 6x6 state covariance
    last_ts: float
    confidence: float = 0.9
    identity: Optional[str] = None
    identity_confidence: float = 0.0
    hits: int = 1
    camera_sources: dict[str, float] = field(default_factory=dict)

    def predict(self, now_ts: float, process_noise: float = 0.45) -> None:
        dt = max(0.0, min(now_ts - self.last_ts, 2.0))
        if dt <= 1e-5:
            self.last_ts = max(self.last_ts, now_ts)
            return

        F = np.eye(6, dtype=np.float64)
        F[0, 3] = dt
        F[1, 4] = dt
        F[2, 5] = dt

        # Constant-velocity transition with slight velocity decay on y
        self.x = F @ self.x
        self.x[4] *= 0.7

        q_pos = process_noise * (dt ** 2)
        q_vel = process_noise * 1.5 * dt
        Q = np.diag([q_pos, q_pos * 0.25, q_pos, q_vel, q_vel * 0.25, q_vel])
        self.P = F @ self.P @ F.T + Q
        self.last_ts = now_ts

    def correct(self, obs: TrackObservation3D) -> None:
        z_meas = np.array(obs.position, dtype=np.float64)
        H = np.zeros((3, 6), dtype=np.float64)
        H[0, 0] = 1.0
        H[1, 1] = 1.0
        H[2, 2] = 1.0

        # Multi-camera uncertainty scaling: higher confidence & closer camera -> lower measurement variance
        base_var = 0.18
        if obs.range_m is not None:
            r_dist = max(0.0, float(obs.range_m))
            base_var = 0.18 + 0.0012 * (r_dist ** 2)
        r_var = base_var / max(obs.confidence, 0.25)
        R = np.diag([r_var, r_var * 0.35, r_var])

        y_res = z_meas - (H @ self.x)
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)

        self.x = self.x + (K @ y_res)
        I = np.eye(6, dtype=np.float64)
        self.P = (I - K @ H) @ self.P
        self.confidence = float(0.7 * self.confidence + 0.3 * obs.confidence)
        self.last_ts = max(self.last_ts, obs.timestamp)
        self.hits += 1
        self.camera_sources[obs.camera_id] = max(self.camera_sources.get(obs.camera_id, 0.0), obs.timestamp)

        if obs.identity and obs.identity_confidence >= self.identity_confidence:
            self.identity = obs.identity
            self.identity_confidence = obs.identity_confidence

    def to_model(self, now_ts: float) -> TrackedEntity3D:
        recent_cams = [cam for cam, ts in self.camera_sources.items() if now_ts - ts <= 3.5]
        if not recent_cams and self.camera_sources:
            recent_cams = [max(self.camera_sources.items(), key=lambda kv: kv[1])[0]]

        return TrackedEntity3D(
            track_id=self.track_id,
            class_label=self.class_label,
            confidence=round(self.confidence, 3),
            identity=self.identity,
            identity_confidence=round(self.identity_confidence, 3),
            state=SpatialPoint3D(
                x=round(float(self.x[0]), 4),
                y=round(float(self.x[1]), 4),
                z=round(float(self.x[2]), 4),
                vx=round(float(self.x[3]), 4),
                vy=round(float(self.x[4]), 4),
                vz=round(float(self.x[5]), 4),
                covariance_diag=[round(float(self.P[0, 0]), 4), round(float(self.P[1, 1]), 4), round(float(self.P[2, 2]), 4)],
                camera_sources=recent_cams,
            ),
            last_seen=self.last_ts,
        )


class Kalman3DMultiTracker(IMultiTargetTracker3D):
    """
    3D Multi-Target & Multi-Camera Tracker combining:
    - 6D linear constant-velocity Kalman filter [x, y, z, vx, vy, vz]
    - Hungarian optimal bipartite matching (scipy linear_sum_assignment)
    - Multi-camera spatial fusion via sequential Kalman covariance updates
    """

    def __init__(self, track_ttl_s: float = 4.5, max_gate_person_m: float = 2.2, max_gate_vehicle_m: float = 4.2) -> None:
        self.track_ttl_s = track_ttl_s
        self.max_gate_person_m = max_gate_person_m
        self.max_gate_vehicle_m = max_gate_vehicle_m
        self._next_track_id = 1
        self._tracks: dict[int, _KalmanTrack] = {}
        self._last_now = 0.0

    def update(self, observations: list[TrackObservation3D], now_ts: float) -> list[TrackedEntity3D]:
        effective_now = max(self._last_now, now_ts)
        self._last_now = effective_now

        # 1. Predict all existing tracks to current timestamp
        for tr in self._tracks.values():
            tr.predict(effective_now)

        # Prune expired tracks
        expired = [
            tid for tid, tr in self._tracks.items()
            if effective_now - max(tr.camera_sources.values(), default=tr.last_ts) > self.track_ttl_s
        ]
        for tid in expired:
            del self._tracks[tid]

        # 2. Group incoming observations by camera so multi-camera views of the same target fuse sequentially
        obs_by_cam: dict[str, list[TrackObservation3D]] = {}
        for obs in observations:
            obs_by_cam.setdefault(obs.camera_id, []).append(obs)

        for _cam_id, cam_obs in obs_by_cam.items():
            self._associate_and_fuse_camera_batch(cam_obs, effective_now)

        return self.get_active_tracks()

    def _associate_and_fuse_camera_batch(self, obs_list: list[TrackObservation3D], now_ts: float) -> None:
        if not obs_list:
            return

        track_ids = list(self._tracks.keys())
        matched_obs: set[int] = set()

        if track_ids:
            cost_mat = np.full((len(track_ids), len(obs_list)), 1e6, dtype=np.float64)
            for ti, tid in enumerate(track_ids):
                tr = self._tracks[tid]
                for oi, obs in enumerate(obs_list):
                    if _coarse_class(tr.class_label) != _coarse_class(obs.class_label):
                        continue
                    gate = self.max_gate_vehicle_m if _coarse_class(obs.class_label) == "vehicle" else self.max_gate_person_m
                    dist = float(np.linalg.norm(tr.x[:3] - np.array(obs.position, dtype=np.float64)))
                    if dist <= gate:
                        # Small bonus if identities already match
                        id_bonus = -0.5 if (tr.identity and obs.identity and tr.identity == obs.identity) else 0.0
                        cost_mat[ti, oi] = max(0.0, dist + id_bonus)

            row_idx, col_idx = linear_sum_assignment(cost_mat)
            for r, c in zip(row_idx, col_idx):
                if cost_mat[r, c] < 1e5:
                    tid = track_ids[r]
                    self._tracks[tid].correct(obs_list[c])
                    matched_obs.add(c)

        # Create new tracks for unmatched observations
        for oi, obs in enumerate(obs_list):
            if oi in matched_obs:
                continue
            tid = self._next_track_id
            self._next_track_id += 1
            x0 = np.array([obs.position[0], obs.position[1], obs.position[2], 0.0, 0.0, 0.0], dtype=np.float64)
            p0_xz = 0.35
            if obs.range_m is not None:
                p0_xz = 0.35 + 0.002 * (max(0.0, float(obs.range_m)) ** 2)
            P0 = np.diag([p0_xz, 0.1, p0_xz, 1.5, 0.5, 1.5])
            self._tracks[tid] = _KalmanTrack(
                track_id=tid,
                class_label=obs.class_label,
                x=x0,
                P=P0,
                last_ts=obs.timestamp or now_ts,
                confidence=obs.confidence,
                identity=obs.identity,
                identity_confidence=obs.identity_confidence,
                camera_sources={obs.camera_id: obs.timestamp or now_ts},
            )

    def get_active_tracks(self) -> list[TrackedEntity3D]:
        return [tr.to_model(self._last_now) for tr in self._tracks.values()]

