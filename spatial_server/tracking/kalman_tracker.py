from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Literal, Optional
import numpy as np
from scipy.optimize import linear_sum_assignment

from spatial_server.domain.models import SpatialPoint3D, TrackedEntity3D
from .interfaces import IMultiTargetTracker3D, TrackObservation3D


def _coarse_class(label: str) -> str:
    if label in ("car", "truck", "bus", "motorcycle", "motorbike"):
        return "vehicle"
    return label


def _is_meaningful_identity(identity: Optional[str]) -> bool:
    if not identity:
        return False
    norm = identity.strip().lower()
    return bool(norm and norm not in ("sconosciuto", "unknown", "none", "pending"))


def _compute_measurement_variance(obs: TrackObservation3D) -> float:
    """
    Compute adaptive 3D ground measurement variance R_xz based on:
    - Camera-to-target range^2
    - Detector confidence
    - Optical model type (Pinhole vs 180-deg Equirectangular Panoramic & edge distortion)
    - Ray-ground grazing angle (sin(theta))
    - Bottom-of-frame bounding box truncation
    """
    base_var = 0.18
    if obs.range_m is not None:
        r_dist = max(0.0, float(obs.range_m))
        base_var = 0.18 + 0.0012 * (r_dist ** 2)
    r_var = base_var / max(float(obs.confidence), 0.25)

    if obs.is_panoramic:
        if obs.uv_contact is not None:
            u_norm = float(obs.uv_contact[0])
            edge_u = min(1.0, abs(u_norm - 0.5) / 0.5)
            # Equirectangular 180-deg cameras have lower angular resolution and peripheral/seam distortion
            seam_penalty = 1.15 if abs(u_norm - 0.5) < 0.035 else 1.0
            r_var *= 1.45 * (1.0 + 1.25 * (edge_u ** 2)) * seam_penalty
        else:
            r_var *= 1.55

    if obs.uv_contact is not None and float(obs.uv_contact[1]) >= 0.965:
        # Feet/wheels clipped by bottom border of image -> ground contact is overestimated
        r_var *= 3.2

    if obs.ray_grazing_sin is not None:
        sin_g = max(0.06, min(1.0, float(obs.ray_grazing_sin)))
        if sin_g < 0.26:
            r_var *= min(3.2, (0.26 / sin_g) ** 1.2)

    return float(max(0.05, r_var))


def _bbox_2d_iou_and_containment(
    box_a: tuple[float, float, float, float],
    box_b: tuple[float, float, float, float],
) -> tuple[float, float]:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    area_a = max(1e-6, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1e-6, (bx2 - bx1) * (by2 - by1))

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0.0:
        return 0.0, 0.0

    union = max(1e-6, area_a + area_b - inter)
    iou = inter / union
    containment = inter / max(1e-6, min(area_a, area_b))
    return float(iou), float(containment)


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
    plate: Optional[str] = None
    plate_confidence: float = 0.0
    plate_whitelisted: Optional[bool] = None
    plate_owner: Optional[str] = None
    biometric_locked: bool = False
    biometric_status: Literal["none", "pending", "locked", "unknown"] = "none"
    best_crop_id: Optional[str] = None
    created_ts: float = 0.0
    hits: int = 1
    camera_sources: dict[str, float] = field(default_factory=dict)
    camera_last_pos: dict[str, np.ndarray] = field(default_factory=dict)
    camera_last_var: dict[str, float] = field(default_factory=dict)
    camera_hits: dict[str, int] = field(default_factory=dict)
    camera_batch_seq: dict[str, int] = field(default_factory=dict)
    last_camera_id: Optional[str] = None
    stationary_anchor_pos: Optional[np.ndarray] = None
    stationary_since_ts: float = 0.0

    def max_physical_speed(self) -> float:
        return 13.5 if _coarse_class(self.class_label) == "vehicle" else 4.2

    def _clamp_velocity(self) -> None:
        max_v = self.max_physical_speed()
        speed_xz = float(math.hypot(float(self.x[3]), float(self.x[5])))
        if speed_xz > max_v and speed_xz > 1e-6:
            scale = max_v / speed_xz
            self.x[3] *= scale
            self.x[5] *= scale
        self.x[4] = float(np.clip(self.x[4], -1.5, 1.5))

    def predict(self, now_ts: float, process_noise: float = 0.45) -> None:
        dt = max(0.0, min(now_ts - self.last_ts, 2.0))
        if dt <= 1e-5:
            self.last_ts = max(self.last_ts, now_ts)
            return

        F = np.eye(6, dtype=np.float64)
        F[0, 3] = dt
        F[1, 4] = dt
        F[2, 5] = dt

        self.x = F @ self.x
        self.x[4] *= 0.7
        # Gentle velocity decay when coasting without observations to prevent runaway drift
        if dt > 0.25:
            coast_decay = math.exp(-0.45 * (dt - 0.25))
            self.x[3] *= coast_decay
            self.x[5] *= coast_decay
        self._clamp_velocity()

        q_pos = process_noise * (dt ** 2)
        q_vel = process_noise * 1.5 * dt
        Q = np.diag([q_pos, q_pos * 0.25, q_pos, q_vel, q_vel * 0.25, q_vel])
        self.P = F @ self.P @ F.T + Q
        self.last_ts = now_ts

    def expected_position_for_camera(self, camera_id: str, now_ts: Optional[float] = None) -> np.ndarray:
        """
        Return the expected 3D position in `camera_id`'s projection frame.
        If `camera_id` has recently observed this track, accounts for that camera's
        local calibration offset so cross-camera miscalibration never breaks association.
        """
        cam_pos = self.camera_last_pos.get(camera_id)
        cam_ts = self.camera_sources.get(camera_id)
        ref_ts = float(now_ts if now_ts is not None else self.last_ts)
        if cam_pos is not None and cam_ts is not None and (ref_ts - cam_ts) <= 3.5:
            dt = max(0.0, min(ref_ts - cam_ts, 1.5))
            return cam_pos + self.x[3:6] * dt
        return self.x[:3].copy()

    def _compute_multicam_consensus_measurement(
        self,
        obs_cam_id: str,
        z_meas: np.ndarray,
        r_var: float,
        ref_ts: float,
    ) -> tuple[np.ndarray, float, int]:
        """
        Compute precision-weighted consensus 3D position across all cameras currently active
        on this track (within 1.8s). Eliminates position ping-pong when asynchronous cameras
        with imperfect calibration observe the same target.
        """
        active_window_s = 1.8
        total_w = 0.0
        weighted_pos = np.zeros(3, dtype=np.float64)
        active_cams_count = 0

        for cam_id, cam_pos in self.camera_last_pos.items():
            cam_ts = self.camera_sources.get(cam_id, 0.0)
            age = max(0.0, ref_ts - cam_ts)
            if cam_id != obs_cam_id and age > active_window_s:
                continue
            cam_var = max(0.05, float(self.camera_last_var.get(cam_id, r_var)))
            time_decay = math.exp(-0.7 * age) if cam_id != obs_cam_id else 1.0
            w = time_decay / cam_var
            # Project older camera's last measurement forward by damped current track velocity
            dt_proj = min(age, 1.0) if cam_id != obs_cam_id else 0.0
            proj_pos = cam_pos + (self.x[3:6] * (0.5 * dt_proj))
            weighted_pos += w * proj_pos
            total_w += w
            active_cams_count += 1

        if total_w <= 1e-9 or active_cams_count <= 1:
            return z_meas, r_var, 1

        consensus_pos = weighted_pos / total_w
        # Keep effective variance well-conditioned
        eff_var = max(0.05, min(r_var, 1.0 / total_w))
        return consensus_pos, eff_var, active_cams_count

    def correct(self, obs: TrackObservation3D, batch_seq: Optional[int] = None) -> None:
        z_meas = np.array(obs.position, dtype=np.float64)
        r_var = _compute_measurement_variance(obs)
        ref_ts = max(self.last_ts, float(obs.timestamp))

        # Check intra-camera displacement BEFORE overwriting camera_last_pos
        prev_cam_pos = self.camera_last_pos.get(obs.camera_id)
        prev_cam_ts = self.camera_sources.get(obs.camera_id)
        intra_cam_vel: Optional[np.ndarray] = None
        intra_cam_dt: float = 0.0
        if prev_cam_pos is not None and prev_cam_ts is not None:
            dt_cam = float(obs.timestamp) - float(prev_cam_ts)
            if 0.02 <= dt_cam <= 2.5:
                intra_cam_dt = dt_cam
                intra_cam_vel = (z_meas - prev_cam_pos) / dt_cam

        is_cross_cam_switch = (
            self.last_camera_id is not None
            and self.last_camera_id != obs.camera_id
        )

        # Update per-camera state
        self.camera_last_pos[obs.camera_id] = z_meas.copy()
        self.camera_last_var[obs.camera_id] = r_var
        self.camera_sources[obs.camera_id] = max(self.camera_sources.get(obs.camera_id, 0.0), float(obs.timestamp))
        self.camera_hits[obs.camera_id] = self.camera_hits.get(obs.camera_id, 0) + 1
        if batch_seq is not None:
            self.camera_batch_seq[obs.camera_id] = int(batch_seq)
        self.last_camera_id = obs.camera_id

        z_target, r_eff, active_cams_count = self._compute_multicam_consensus_measurement(
            obs.camera_id,
            z_meas,
            r_var,
            ref_ts,
        )

        H = np.zeros((3, 6), dtype=np.float64)
        H[0, 0] = 1.0
        H[1, 1] = 1.0
        H[2, 2] = 1.0

        R = np.diag([r_eff, r_eff * 0.35, r_eff])
        y_res = z_target - (H @ self.x)
        S = H @ self.P @ H.T + R
        K = self.P @ H.T @ np.linalg.inv(S)

        saved_vel = self.x[3:6].copy()
        self.x = self.x + (K @ y_res)
        I = np.eye(6, dtype=np.float64)
        self.P = (I - K @ H) @ self.P

        # Decouple cross-camera calibration offset from physical velocity estimation:
        # If multiple cameras are active or we just switched cameras, never let the
        # cross-camera spatial offset create a fake velocity spike.
        if active_cams_count >= 2 or is_cross_cam_switch:
            if intra_cam_vel is not None:
                # Weight intra-camera velocity innovation by this camera's relative precision
                cam_prec = 1.0 / max(r_var, 0.05)
                tot_prec = sum(
                    1.0 / max(self.camera_last_var.get(c, r_var), 0.05)
                    for c, ts in self.camera_sources.items()
                    if (ref_ts - ts) <= 1.8
                )
                rel_w = min(1.0, max(0.2, cam_prec / max(tot_prec, 1e-6)))
                alpha_v = min(0.65, max(0.18, 0.48 * rel_w))
                self.x[3:6] = (1.0 - alpha_v) * saved_vel + alpha_v * intra_cam_vel
                self.x[4] *= 0.5
            else:
                # First observation from a secondary camera: position fusion only, preserve velocity
                self.x[3:6] = saved_vel * 0.92
        elif intra_cam_vel is not None and intra_cam_dt > 0.0:
            # Single-camera tracking: blend Kalman velocity with direct intra-camera finite difference
            self.x[3:6] = 0.65 * self.x[3:6] + 0.35 * intra_cam_vel
            self.x[4] *= 0.5

        self._clamp_velocity()

        # Maintain highest-priority vehicle sub-class if upgraded
        if _coarse_class(self.class_label) == "vehicle" and _coarse_class(obs.class_label) == "vehicle":
            if self.class_label == "truck" and obs.class_label == "car" and obs.confidence >= self.confidence:
                self.class_label = "car"

        self.confidence = float(0.7 * self.confidence + 0.3 * obs.confidence)
        self.last_ts = max(self.last_ts, float(obs.timestamp))
        self.hits += 1

        if self.stationary_anchor_pos is None:
            self.stationary_anchor_pos = self.x[:3].copy()
            self.stationary_since_ts = float(obs.timestamp or ref_ts)
        else:
            anchor_disp = float(
                math.hypot(
                    float(self.x[0] - self.stationary_anchor_pos[0]),
                    float(self.x[2] - self.stationary_anchor_pos[2]),
                )
            )
            if anchor_disp > 0.65:
                self.stationary_anchor_pos = self.x[:3].copy()
                self.stationary_since_ts = float(obs.timestamp or ref_ts)

        if not self.biometric_locked:
            if obs.identity and obs.identity_confidence >= self.identity_confidence:
                self.identity = obs.identity
                self.identity_confidence = obs.identity_confidence
            if obs.plate and obs.plate_confidence >= self.plate_confidence:
                self.plate = obs.plate
                self.plate_confidence = obs.plate_confidence

    def absorb_other_track(self, other: "_KalmanTrack", now_ts: float) -> None:
        """
        Fuse a duplicate/clone track into `self`, combining covariance-weighted position,
        camera histories, hit counts, and biometric metadata.
        """
        for cam_id, ts in other.camera_sources.items():
            if ts >= self.camera_sources.get(cam_id, 0.0):
                self.camera_sources[cam_id] = ts
                if cam_id in other.camera_last_pos:
                    self.camera_last_pos[cam_id] = other.camera_last_pos[cam_id].copy()
                if cam_id in other.camera_last_var:
                    self.camera_last_var[cam_id] = other.camera_last_var[cam_id]
            self.camera_hits[cam_id] = self.camera_hits.get(cam_id, 0) + other.camera_hits.get(cam_id, 1)
            if cam_id in other.camera_batch_seq:
                self.camera_batch_seq[cam_id] = max(
                    self.camera_batch_seq.get(cam_id, 0),
                    other.camera_batch_seq[cam_id],
                )

        ref_ts = max(self.last_ts, other.last_ts, now_ts)
        # Re-evaluate multi-camera consensus position across all combined camera sources
        if self.camera_last_pos:
            latest_cam = max(self.camera_sources.items(), key=lambda kv: kv[1])[0]
            latest_pos = self.camera_last_pos.get(latest_cam, self.x[:3])
            latest_var = self.camera_last_var.get(latest_cam, 0.25)
            consensus_pos, eff_var, _n_cams = self._compute_multicam_consensus_measurement(
                latest_cam,
                latest_pos,
                latest_var,
                ref_ts,
            )
            self.x[:3] = consensus_pos
            self.P[0, 0] = min(self.P[0, 0], eff_var)
            self.P[2, 2] = min(self.P[2, 2], eff_var)
        else:
            w_self = 1.0 / max(float(self.P[0, 0] + self.P[2, 2]), 0.05)
            w_other = 1.0 / max(float(other.P[0, 0] + other.P[2, 2]), 0.05)
            self.x[:3] = (w_self * self.x[:3] + w_other * other.x[:3]) / (w_self + w_other)

        # Blend velocities conservatively (dampen if opposing directions, which indicates calibration offset)
        dot_v = float(self.x[3] * other.x[3] + self.x[5] * other.x[5])
        if dot_v < 0.0:
            self.x[3:6] *= 0.35
        else:
            self.x[3:6] = 0.65 * self.x[3:6] + 0.35 * other.x[3:6]
        self._clamp_velocity()

        self.hits += other.hits
        self.created_ts = min(self.created_ts, other.created_ts) if self.created_ts > 0 and other.created_ts > 0 else max(self.created_ts, other.created_ts)
        self.last_ts = max(self.last_ts, other.last_ts)
        self.confidence = max(self.confidence, other.confidence)

        if other.stationary_anchor_pos is not None:
            if self.stationary_anchor_pos is None:
                self.stationary_anchor_pos = other.stationary_anchor_pos.copy()
                self.stationary_since_ts = other.stationary_since_ts
            else:
                d_anchors = float(
                    math.hypot(
                        float(self.stationary_anchor_pos[0] - other.stationary_anchor_pos[0]),
                        float(self.stationary_anchor_pos[2] - other.stationary_anchor_pos[2]),
                    )
                )
                if d_anchors <= 1.2:
                    if other.stationary_since_ts > 0.0 and (
                        self.stationary_since_ts <= 0.0 or other.stationary_since_ts < self.stationary_since_ts
                    ):
                        self.stationary_since_ts = other.stationary_since_ts
                else:
                    self.stationary_anchor_pos = self.x[:3].copy()
                    self.stationary_since_ts = ref_ts

        # Merge biometric state (locked state always wins)
        if other.biometric_locked and not self.biometric_locked:
            self.biometric_locked = True
            self.biometric_status = "locked"
            if other.identity:
                self.identity = other.identity
                self.identity_confidence = other.identity_confidence
            if other.plate:
                self.plate = other.plate
                self.plate_confidence = other.plate_confidence
                self.plate_whitelisted = other.plate_whitelisted
                self.plate_owner = other.plate_owner
            if other.best_crop_id:
                self.best_crop_id = other.best_crop_id
        elif not self.biometric_locked:
            if other.identity and other.identity_confidence > self.identity_confidence:
                self.identity = other.identity
                self.identity_confidence = other.identity_confidence
            if other.plate and other.plate_confidence > self.plate_confidence:
                self.plate = other.plate
                self.plate_confidence = other.plate_confidence
                if other.plate_whitelisted is not None:
                    self.plate_whitelisted = other.plate_whitelisted
                if other.plate_owner:
                    self.plate_owner = other.plate_owner
            if not self.best_crop_id and other.best_crop_id:
                self.best_crop_id = other.best_crop_id
            if self.biometric_status == "none" and other.biometric_status != "none":
                self.biometric_status = other.biometric_status

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
            plate=self.plate,
            plate_confidence=round(self.plate_confidence, 3),
            plate_whitelisted=self.plate_whitelisted,
            plate_owner=self.plate_owner,
            biometric_locked=self.biometric_locked,
            biometric_status=self.biometric_status,
            best_crop_id=self.best_crop_id,
            state=SpatialPoint3D(
                x=round(float(self.x[0]), 4),
                y=round(float(self.x[1]), 4),
                z=round(float(self.x[2]), 4),
                vx=round(float(self.x[3]), 4),
                vy=round(float(self.x[4]), 4),
                vz=round(float(self.x[5]), 4),
                covariance_diag=[
                    round(float(self.P[0, 0]), 4),
                    round(float(self.P[1, 1]), 4),
                    round(float(self.P[2, 2]), 4),
                ],
                camera_sources=recent_cams,
            ),
            last_seen=self.last_ts,
        )


@dataclass
class _CameraBatchSummary:
    camera_id: str
    coarse_class: str
    batch_seq: int
    timestamp: float
    count: int
    positions: list[np.ndarray]


class Kalman3DMultiTracker(IMultiTargetTracker3D):
    """
    3D Multi-Target & Multi-Camera Tracker combining:
    - 6D linear constant-velocity Kalman filter [x, y, z, vx, vy, vz]
    - Decoupled per-camera bias & precision-weighted consensus fusion (anti-ping-pong)
    - Intra-camera 2D/3D coarse-class NMS deduplication
    - Two-stage Hungarian optimal bipartite matching (standard gate + cardinality-constrained cross-camera gate)
    - Track-to-track merging & logical zone cardinality enforcement (max tracks <= logical camera object count)
    """

    def __init__(
        self,
        track_ttl_s: float = 4.5,
        max_gate_person_m: float = 2.2,
        max_gate_vehicle_m: float = 4.2,
        cross_cam_gate_person_m: float = 3.8,
        cross_cam_gate_vehicle_m: float = 6.5,
        uncalibrated_zone_person_m: float = 5.5,
        uncalibrated_zone_vehicle_m: float = 9.0,
        merge_radius_person_m: float = 2.6,
        merge_radius_vehicle_m: float = 4.8,
        initial_next_track_id: int = 1,
        camera_visibility_fn: Optional[Callable[[str, tuple[float, float, float]], bool]] = None,
        stationary_vehicle_reid_s: float = 120.0,
        person_reid_s: float = 10.0,
    ) -> None:
        self.track_ttl_s = track_ttl_s
        self.max_gate_person_m = max_gate_person_m
        self.max_gate_vehicle_m = max_gate_vehicle_m
        self.cross_cam_gate_person_m = max(max_gate_person_m, cross_cam_gate_person_m)
        self.cross_cam_gate_vehicle_m = max(max_gate_vehicle_m, cross_cam_gate_vehicle_m)
        self.uncalibrated_zone_person_m = max(self.cross_cam_gate_person_m, uncalibrated_zone_person_m)
        self.uncalibrated_zone_vehicle_m = max(self.cross_cam_gate_vehicle_m, uncalibrated_zone_vehicle_m)
        self.merge_radius_person_m = merge_radius_person_m
        self.merge_radius_vehicle_m = merge_radius_vehicle_m
        self.stationary_vehicle_reid_s = max(0.0, float(stationary_vehicle_reid_s))
        self.person_reid_s = max(0.0, float(person_reid_s))
        self._next_track_id = max(1, int(initial_next_track_id))
        self._tracks: dict[int, _KalmanTrack] = {}
        self._expired_tracks: dict[int, tuple[_KalmanTrack, float]] = {}
        self._recent_merges: list[tuple[int, int]] = []
        self._lifecycle_events: list[dict[str, Any]] = []
        self._last_now = 0.0
        self.camera_visibility_fn = camera_visibility_fn

        self._batch_seq_counter: int = 0
        self._camera_latest_batch_seq: dict[str, int] = {}
        self._camera_batch_summaries: dict[tuple[str, str], _CameraBatchSummary] = {}

    @staticmethod
    def _obs_biometrically_compatible(tr: _KalmanTrack, obs: TrackObservation3D) -> bool:
        if _is_meaningful_identity(tr.identity) and _is_meaningful_identity(obs.identity):
            if tr.identity != obs.identity:
                return False
        if tr.plate and obs.plate and tr.plate != obs.plate:
            return False
        return True

    @staticmethod
    def _tracks_biometrically_compatible(tr_a: _KalmanTrack, tr_b: _KalmanTrack) -> bool:
        if _is_meaningful_identity(tr_a.identity) and _is_meaningful_identity(tr_b.identity):
            if tr_a.identity != tr_b.identity:
                return False
        if tr_a.plate and tr_b.plate and tr_a.plate != tr_b.plate:
            return False
        return True

    def _co_observed_in_same_camera_batch(self, tr_a: _KalmanTrack, tr_b: _KalmanTrack, now_ts: float) -> bool:
        """
        Return True if any single camera observed BOTH `tr_a` and `tr_b` as distinct
        simultaneous detections in that camera's latest active batch.
        """
        for cam_id, seq_a in tr_a.camera_batch_seq.items():
            seq_b = tr_b.camera_batch_seq.get(cam_id)
            if seq_b is not None and seq_a == seq_b:
                latest_seq = self._camera_latest_batch_seq.get(cam_id)
                cam_ts = max(tr_a.camera_sources.get(cam_id, 0.0), tr_b.camera_sources.get(cam_id, 0.0))
                if seq_a == latest_seq and (now_ts - cam_ts) <= 2.5:
                    return True
        return False

    def _is_point_in_camera_zone(
        self,
        camera_id: str,
        point_3d: np.ndarray,
        obs_positions: list[np.ndarray],
        coarse_cls: str,
    ) -> bool:
        zone_rad = self.uncalibrated_zone_vehicle_m if coarse_cls == "vehicle" else self.uncalibrated_zone_person_m
        for op in obs_positions:
            if float(np.linalg.norm(point_3d - op)) <= zone_rad:
                return True
        if self.camera_visibility_fn is not None:
            try:
                if self.camera_visibility_fn(camera_id, (float(point_3d[0]), float(point_3d[1]), float(point_3d[2]))):
                    # Even if visible in wide 180-deg frustum, require reasonable proximity to the cluster
                    for op in obs_positions:
                        if float(np.linalg.norm(point_3d - op)) <= zone_rad * 1.45:
                            return True
            except Exception:
                pass
        return False

    def _deduplicate_camera_batch(
        self,
        indexed_obs_list: list[tuple[int, TrackObservation3D]],
    ) -> tuple[list[tuple[int, TrackObservation3D]], dict[int, int]]:
        """
        Deduplicate observations from a single camera batch that represent the same physical target
        (e.g. a vehicle classified simultaneously as 'car' and 'truck', or split bounding boxes
        projecting to the same 3D footprint).
        Returns (deduplicated_list, duplicate_orig_idx_to_primary_orig_idx).
        """
        if len(indexed_obs_list) <= 1:
            return indexed_obs_list, {}

        ordered = sorted(indexed_obs_list, key=lambda item: float(item[1].confidence), reverse=True)
        kept: list[tuple[int, TrackObservation3D]] = []
        dup_map: dict[int, int] = {}

        for orig_idx, cand in ordered:
            c_cls = _coarse_class(cand.class_label)
            c_pos = np.array(cand.position, dtype=np.float64)
            intra_3d_thresh = 2.25 if c_cls == "vehicle" else 0.58

            matched_primary_idx: Optional[int] = None
            for prim_orig_idx, prim in kept:
                if _coarse_class(prim.class_label) != c_cls:
                    continue
                if _is_meaningful_identity(cand.identity) and _is_meaningful_identity(prim.identity):
                    if cand.identity != prim.identity:
                        continue
                if cand.plate and prim.plate and cand.plate != prim.plate:
                    continue

                p_pos = np.array(prim.position, dtype=np.float64)
                dist_3d = float(np.linalg.norm(c_pos - p_pos))
                is_dup = dist_3d <= intra_3d_thresh

                if not is_dup and cand.bbox_2d is not None and prim.bbox_2d is not None:
                    iou, containment = _bbox_2d_iou_and_containment(cand.bbox_2d, prim.bbox_2d)
                    iou_t = 0.38 if c_cls == "vehicle" else 0.45
                    cont_t = 0.72 if c_cls == "vehicle" else 0.80
                    if iou >= iou_t or containment >= cont_t:
                        is_dup = True

                if is_dup:
                    matched_primary_idx = prim_orig_idx
                    # Enrich primary with biometric attributes if missing
                    if not prim.identity and cand.identity:
                        prim.identity = cand.identity
                        prim.identity_confidence = cand.identity_confidence
                    if not prim.plate and cand.plate:
                        prim.plate = cand.plate
                        prim.plate_confidence = cand.plate_confidence
                    break

            if matched_primary_idx is not None:
                dup_map[orig_idx] = matched_primary_idx
            else:
                kept.append((orig_idx, cand))

        # Preserve original arrival order for determinism
        kept.sort(key=lambda item: item[0])
        return kept, dup_map

    def update(self, observations: list[TrackObservation3D], now_ts: float) -> list[TrackedEntity3D]:
        tracks, _ = self.update_with_assignments(observations, now_ts)
        return tracks

    def update_with_assignments(
        self,
        observations: list[TrackObservation3D],
        now_ts: float,
    ) -> tuple[list[TrackedEntity3D], dict[int, int]]:
        effective_now = max(self._last_now, now_ts)
        self._last_now = effective_now

        # 1. Predict all existing tracks to current timestamp
        for tr in self._tracks.values():
            tr.predict(effective_now)

        # Prune expired tracks (retain briefly in _expired_tracks for flicker/occlusion Re-ID)
        expired = [
            tid for tid, tr in self._tracks.items()
            if effective_now - max(tr.camera_sources.values(), default=tr.last_ts) > self.track_ttl_s
        ]
        for tid in expired:
            tr_exp = self._tracks[tid]
            self._expired_tracks[tid] = (tr_exp, effective_now)
            self._record_lifecycle(
                event="expired",
                track_id=tid,
                class_label=tr_exp.class_label,
                camera_id=tr_exp.last_camera_id,
                timestamp=effective_now,
            )
            del self._tracks[tid]

        max_reid_ttl = max(self.stationary_vehicle_reid_s, self.person_reid_s, 10.0) + 5.0
        stale_reid = [
            tid for tid, (_tr, exp_ts) in self._expired_tracks.items()
            if effective_now - exp_ts > max_reid_ttl
        ]
        for tid in stale_reid:
            del self._expired_tracks[tid]

        # 2. Group incoming observations by camera so multi-camera views of the same target fuse sequentially
        obs_assignments: dict[int, int] = {}
        obs_by_cam: dict[str, list[tuple[int, TrackObservation3D]]] = {}
        for orig_idx, obs in enumerate(observations):
            obs_by_cam.setdefault(obs.camera_id, []).append((orig_idx, obs))

        for cam_id, indexed_obs in obs_by_cam.items():
            self._associate_and_fuse_camera_batch(cam_id, indexed_obs, effective_now, obs_assignments)

        # 3. Post-association track-to-track fusion & logical zone cardinality enforcement
        if len(self._tracks) > 1:
            self._merge_and_enforce_cardinality(effective_now, obs_assignments)

        return self.get_active_tracks(), obs_assignments

    def _effective_distance_and_gate(
        self,
        tr: _KalmanTrack,
        obs: TrackObservation3D,
        now_ts: float,
    ) -> tuple[float, float]:
        coarse_cls = _coarse_class(obs.class_label)
        obs_pos = np.array(obs.position, dtype=np.float64)

        dist_fused = float(np.linalg.norm(tr.x[:3] - obs_pos))
        exp_cam_pos = tr.expected_position_for_camera(obs.camera_id, now_ts)
        dist_cam = float(np.linalg.norm(exp_cam_pos - obs_pos))
        dist = min(dist_fused, dist_cam)

        cam_seen_recently = (
            obs.camera_id in tr.camera_sources
            and (now_ts - tr.camera_sources[obs.camera_id]) <= 3.5
        )
        other_cams_recent = any(
            c != obs.camera_id and (now_ts - ts) <= 3.5
            for c, ts in tr.camera_sources.items()
        )
        is_cross_camera = (not cam_seen_recently) or other_cams_recent

        if coarse_cls == "vehicle":
            base_gate = self.cross_cam_gate_vehicle_m if is_cross_camera else self.max_gate_vehicle_m
            range_bonus = 0.08 * max(0.0, float(obs.range_m or 0.0) - 6.0)
            max_cap = 8.2 if is_cross_camera else 5.5
        else:
            base_gate = self.cross_cam_gate_person_m if is_cross_camera else self.max_gate_person_m
            range_bonus = 0.06 * max(0.0, float(obs.range_m or 0.0) - 5.0)
            max_cap = 5.0 if is_cross_camera else 3.2

        if obs.is_panoramic and is_cross_camera:
            base_gate *= 1.12

        gate = min(max_cap, base_gate + range_bonus)
        return dist, gate

    def _associate_and_fuse_camera_batch(
        self,
        camera_id: str,
        indexed_obs_list: list[tuple[int, TrackObservation3D]],
        now_ts: float,
        obs_assignments: dict[int, int],
    ) -> None:
        if not indexed_obs_list:
            return

        # Step 0: Intra-camera 2D/3D duplicate suppression
        dedup_obs_list, dup_map = self._deduplicate_camera_batch(indexed_obs_list)

        self._batch_seq_counter += 1
        batch_seq = self._batch_seq_counter
        self._camera_latest_batch_seq[camera_id] = batch_seq

        # Record logical count per coarse class for this camera batch
        obs_by_coarse: dict[str, list[np.ndarray]] = {}
        for _orig_idx, obs in dedup_obs_list:
            c_cls = _coarse_class(obs.class_label)
            obs_by_coarse.setdefault(c_cls, []).append(np.array(obs.position, dtype=np.float64))

        batch_ts = max((float(o.timestamp) for _, o in dedup_obs_list), default=now_ts)
        for c_cls, pos_list in obs_by_coarse.items():
            self._camera_batch_summaries[(camera_id, c_cls)] = _CameraBatchSummary(
                camera_id=camera_id,
                coarse_class=c_cls,
                batch_seq=batch_seq,
                timestamp=max(now_ts, batch_ts),
                count=len(pos_list),
                positions=pos_list,
            )

        track_ids = list(self._tracks.keys())
        matched_obs: set[int] = set()
        matched_tids: set[int] = set()

        # Stage 1: Hungarian assignment with adaptive intra/cross-camera gate
        if track_ids:
            cost_mat = np.full((len(track_ids), len(dedup_obs_list)), 1e6, dtype=np.float64)
            for ti, tid in enumerate(track_ids):
                tr = self._tracks[tid]
                for oi, (_orig_idx, obs) in enumerate(dedup_obs_list):
                    if _coarse_class(tr.class_label) != _coarse_class(obs.class_label):
                        continue
                    if not self._obs_biometrically_compatible(tr, obs):
                        continue

                    dist, gate = self._effective_distance_and_gate(tr, obs, now_ts)
                    if dist <= gate:
                        id_adjust = 0.0
                        if _is_meaningful_identity(tr.identity) and _is_meaningful_identity(obs.identity):
                            if tr.identity == obs.identity:
                                id_adjust -= 0.6
                        if tr.plate and obs.plate:
                            if tr.plate == obs.plate:
                                id_adjust -= 0.9
                        # Slight preference for tracks already observed by this camera or with higher hits
                        cam_affinity = -0.15 if camera_id in tr.camera_sources else 0.0
                        cost_mat[ti, oi] = max(0.0, dist + id_adjust + cam_affinity)

            row_idx, col_idx = linear_sum_assignment(cost_mat)
            for r, c in zip(row_idx, col_idx):
                if cost_mat[r, c] < 1e5:
                    tid = track_ids[r]
                    orig_idx, obs = dedup_obs_list[c]
                    self._tracks[tid].correct(obs, batch_seq=batch_seq)
                    obs_assignments[orig_idx] = tid
                    matched_obs.add(c)
                    matched_tids.add(tid)

        # Stage 2: Logical Cardinality & Imperfect-Calibration Fallback Association
        # If an observation was outside the Stage-1 gate due to camera miscalibration,
        # check if there is an unmatched active track of the same class in the shared zone
        # such that creating a new track would exceed the logical object count of the cameras.
        unmatched_ois = [oi for oi in range(len(dedup_obs_list)) if oi not in matched_obs]
        if unmatched_ois and len(matched_tids) < len(track_ids):
            remaining_tids = [tid for tid in track_ids if tid not in matched_tids]
            fallback_cost = np.full((len(remaining_tids), len(unmatched_ois)), 1e6, dtype=np.float64)

            for r_ti, tid in enumerate(remaining_tids):
                tr = self._tracks[tid]
                tr_cls = _coarse_class(tr.class_label)
                zone_limit = (
                    self.uncalibrated_zone_vehicle_m
                    if tr_cls == "vehicle"
                    else self.uncalibrated_zone_person_m
                )

                for u_oi, oi in enumerate(unmatched_ois):
                    _orig_idx, obs = dedup_obs_list[oi]
                    if _coarse_class(obs.class_label) != tr_cls:
                        continue
                    if not self._obs_biometrically_compatible(tr, obs):
                        continue

                    obs_pos = np.array(obs.position, dtype=np.float64)
                    dist, _ = self._effective_distance_and_gate(tr, obs, now_ts)
                    in_zone = dist <= zone_limit or self._is_point_in_camera_zone(
                        camera_id,
                        tr.x[:3],
                        [obs_pos],
                        tr_cls,
                    )
                    if not in_zone:
                        continue

                    # Count existing tracks in this shared zone and compare with logical camera maximum
                    zone_tracks = [
                        other_tr
                        for other_tr in self._tracks.values()
                        if _coarse_class(other_tr.class_label) == tr_cls
                        and float(np.linalg.norm(other_tr.x[:3] - obs_pos)) <= zone_limit
                    ]
                    logical_max = self._compute_zone_logical_max(
                        tr_cls,
                        zone_tracks,
                        extra_cam_id=camera_id,
                        now_ts=now_ts,
                    )
                    if len(zone_tracks) >= logical_max:
                        fallback_cost[r_ti, u_oi] = max(0.0, dist)

            f_rows, f_cols = linear_sum_assignment(fallback_cost)
            for r, c in zip(f_rows, f_cols):
                if fallback_cost[r, c] < 1e5:
                    tid = remaining_tids[r]
                    oi = unmatched_ois[c]
                    orig_idx, obs = dedup_obs_list[oi]
                    self._tracks[tid].correct(obs, batch_seq=batch_seq)
                    obs_assignments[orig_idx] = tid
                    matched_obs.add(oi)
                    matched_tids.add(tid)

        # Stage 3: Re-ID recently expired stationary/flickering tracks before allocating new track_id
        for oi, (orig_idx, obs) in enumerate(dedup_obs_list):
            if oi in matched_obs:
                continue
            p0_xz = _compute_measurement_variance(obs)
            ts0 = float(obs.timestamp or now_ts)
            obs_coarse = _coarse_class(obs.class_label)

            best_reid: Optional[tuple[float, int, _KalmanTrack]] = None
            for exp_tid, (tr_exp, exp_ts) in self._expired_tracks.items():
                if _coarse_class(tr_exp.class_label) != obs_coarse:
                    continue
                if not self._obs_biometrically_compatible(tr_exp, obs):
                    continue
                dt_exp = max(0.0, now_ts - exp_ts)
                d_cur = float(math.hypot(float(obs.position[0] - tr_exp.x[0]), float(obs.position[2] - tr_exp.x[2])))
                d_anchor = (
                    float(
                        math.hypot(
                            float(obs.position[0] - tr_exp.stationary_anchor_pos[0]),
                            float(obs.position[2] - tr_exp.stationary_anchor_pos[2]),
                        )
                    )
                    if tr_exp.stationary_anchor_pos is not None
                    else d_cur
                )
                dist_xz = min(d_cur, d_anchor)

                if obs_coarse == "vehicle":
                    if dt_exp > self.stationary_vehicle_reid_s:
                        continue
                    same_plate = bool(obs.plate and tr_exp.plate and obs.plate == tr_exp.plate)
                    max_r = 6.5 if same_plate else 2.8
                    if dist_xz > max_r:
                        continue
                elif obs_coarse == "person":
                    if dt_exp > self.person_reid_s:
                        continue
                    same_id = bool(
                        _is_meaningful_identity(obs.identity)
                        and _is_meaningful_identity(tr_exp.identity)
                        and obs.identity == tr_exp.identity
                    )
                    same_cam = obs.camera_id in tr_exp.camera_sources
                    max_r = 4.5 if same_id else (min(2.6, 1.4 + 0.35 * dt_exp) if same_cam else 0.0)
                    if dist_xz > max_r:
                        continue
                else:
                    continue

                if best_reid is None or dist_xz < best_reid[0]:
                    best_reid = (dist_xz, exp_tid, tr_exp)

            if best_reid is not None:
                _dist, revive_tid, tr_exp = best_reid
                del self._expired_tracks[revive_tid]
                tr_exp.x[3:6] = 0.0
                tr_exp.last_ts = ts0
                tr_exp.P[0, 0] = max(float(tr_exp.P[0, 0]), p0_xz)
                tr_exp.P[2, 2] = max(float(tr_exp.P[2, 2]), p0_xz)
                tr_exp.correct(obs, batch_seq=batch_seq)
                self._tracks[revive_tid] = tr_exp
                obs_assignments[orig_idx] = revive_tid
                self._record_lifecycle(
                    event="reid_revived",
                    track_id=revive_tid,
                    class_label=obs.class_label,
                    camera_id=obs.camera_id,
                    dt_gap_s=round(max(0.0, now_ts - tr_exp.last_ts), 3),
                    dist_xz_m=round(_dist, 3),
                    timestamp=now_ts,
                )
                continue

            tid = self._next_track_id
            self._next_track_id += 1
            x0 = np.array([obs.position[0], obs.position[1], obs.position[2], 0.0, 0.0, 0.0], dtype=np.float64)
            P0 = np.diag([p0_xz, 0.1, p0_xz, 1.5, 0.5, 1.5])
            pos_arr = np.array(obs.position, dtype=np.float64)
            self._tracks[tid] = _KalmanTrack(
                track_id=tid,
                class_label=obs.class_label,
                x=x0,
                P=P0,
                last_ts=ts0,
                confidence=obs.confidence,
                identity=obs.identity,
                identity_confidence=obs.identity_confidence,
                plate=obs.plate,
                plate_confidence=obs.plate_confidence,
                created_ts=ts0,
                camera_sources={obs.camera_id: ts0},
                camera_last_pos={obs.camera_id: pos_arr},
                camera_last_var={obs.camera_id: p0_xz},
                camera_hits={obs.camera_id: 1},
                camera_batch_seq={obs.camera_id: batch_seq},
                last_camera_id=obs.camera_id,
                stationary_anchor_pos=pos_arr.copy(),
                stationary_since_ts=ts0,
            )
            obs_assignments[orig_idx] = tid
            self._record_lifecycle(
                event="created",
                track_id=tid,
                class_label=obs.class_label,
                camera_id=obs.camera_id,
                timestamp=now_ts,
            )

        # Propagate assignments to any suppressed intra-camera duplicates
        for dup_orig_idx, prim_orig_idx in dup_map.items():
            if prim_orig_idx in obs_assignments:
                obs_assignments[dup_orig_idx] = obs_assignments[prim_orig_idx]

    def _compute_zone_logical_max(
        self,
        coarse_cls: str,
        cluster_tracks: list[_KalmanTrack],
        *,
        extra_cam_id: Optional[str] = None,
        now_ts: float,
    ) -> int:
        """
        Determine the maximum logical number of physical entities of `coarse_cls`
        that can exist in the local overlap cluster based on active camera counts
        and distinct biometric identities/plates.
        """
        relevant_cams: set[str] = set()
        if extra_cam_id:
            relevant_cams.add(extra_cam_id)
        for tr in cluster_tracks:
            for cam_id, ts in tr.camera_sources.items():
                if (now_ts - ts) <= 2.8:
                    relevant_cams.add(cam_id)

        zone_rad = self.uncalibrated_zone_vehicle_m if coarse_cls == "vehicle" else self.uncalibrated_zone_person_m
        cluster_positions = [tr.x[:3] for tr in cluster_tracks]

        max_cam_count = 1
        for cam_id in relevant_cams:
            summary = self._camera_batch_summaries.get((cam_id, coarse_cls))
            if summary is None or (now_ts - summary.timestamp) > 2.8:
                continue
            # Count how many detections in `cam_id`'s latest batch fall within this cluster zone
            if cluster_positions:
                in_cluster_count = sum(
                    1
                    for op in summary.positions
                    if any(float(np.linalg.norm(op - cp)) <= zone_rad for cp in cluster_positions)
                )
                cam_count = max(1, in_cluster_count) if summary.count > 0 else 0
            else:
                cam_count = summary.count
            if cam_count > max_cam_count:
                max_cam_count = cam_count

        # Never collapse demonstrably distinct biometric identities or license plates
        distinct_identities = {
            tr.identity.strip().lower()
            for tr in cluster_tracks
            if _is_meaningful_identity(tr.identity)
        }
        distinct_plates = {
            tr.plate.strip().upper()
            for tr in cluster_tracks
            if tr.plate and tr.plate.strip()
        }
        bio_floor = max(len(distinct_identities), len(distinct_plates), 1)
        return max(max_cam_count, bio_floor)

    @staticmethod
    def _track_priority_key(tr: _KalmanTrack) -> tuple[int, int, int, float, int]:
        """Higher tuple value = higher priority to keep when merging two tracks."""
        has_bio = int(bool(tr.biometric_locked or _is_meaningful_identity(tr.identity) or tr.plate))
        return (
            int(tr.biometric_locked),
            has_bio,
            len(tr.camera_sources),
            float(tr.hits),
            -int(tr.track_id),  # Prefer older (lower) track_id for stability
        )

    def _record_lifecycle(self, **entry: Any) -> None:
        self._lifecycle_events.append(entry)
        if len(self._lifecycle_events) > 500:
            self._lifecycle_events = self._lifecycle_events[-500:]

    def pop_lifecycle_events(self) -> list[dict[str, Any]]:
        """Return and clear recent track lifecycle telemetry entries."""
        items = list(self._lifecycle_events)
        self._lifecycle_events.clear()
        return items

    def pop_merged_tracks(self) -> list[tuple[int, int]]:
        """Return and clear recent ``(kept_track_id, dropped_track_id)`` merges."""
        merges = list(self._recent_merges)
        self._recent_merges.clear()
        return merges

    def _merge_track_pair(
        self,
        tid_keep: int,
        tid_drop: int,
        now_ts: float,
        obs_assignments: dict[int, int],
    ) -> None:
        if tid_keep not in self._tracks or tid_drop not in self._tracks or tid_keep == tid_drop:
            return
        tr_keep = self._tracks[tid_keep]
        tr_drop = self._tracks[tid_drop]
        tr_keep.absorb_other_track(tr_drop, now_ts)
        del self._tracks[tid_drop]
        self._recent_merges.append((tid_keep, tid_drop))
        self._record_lifecycle(
            event="merged",
            track_id=tid_keep,
            dropped_track_id=tid_drop,
            class_label=tr_keep.class_label,
            timestamp=now_ts,
        )
        for obs_idx, assigned_tid in list(obs_assignments.items()):
            if assigned_tid == tid_drop:
                obs_assignments[obs_idx] = tid_keep

    def _merge_and_enforce_cardinality(
        self,
        now_ts: float,
        obs_assignments: dict[int, int],
    ) -> None:
        """
        1. Merge tracks sharing the exact same biometric identity or plate.
        2. Merge cross-camera duplicate tracks within `merge_radius_m` that were not
           simultaneously observed in the same camera frame.
        3. Enforce the logical zone cardinality cap: in any shared overlap cluster,
           the number of active tracks cannot exceed max(N_cam) across the observing cameras.
        """
        # Pass A & B: Biometric match merge & spatial cross-camera overlap merge
        changed = True
        while changed and len(self._tracks) > 1:
            changed = False
            tids = list(self._tracks.keys())
            for i in range(len(tids)):
                tid_a = tids[i]
                if tid_a not in self._tracks:
                    continue
                tr_a = self._tracks[tid_a]
                cls_a = _coarse_class(tr_a.class_label)
                merge_rad = self.merge_radius_vehicle_m if cls_a == "vehicle" else self.merge_radius_person_m

                for j in range(i + 1, len(tids)):
                    tid_b = tids[j]
                    if tid_b not in self._tracks:
                        continue
                    tr_b = self._tracks[tid_b]
                    if _coarse_class(tr_b.class_label) != cls_a:
                        continue
                    if not self._tracks_biometrically_compatible(tr_a, tr_b):
                        continue
                    if self._co_observed_in_same_camera_batch(tr_a, tr_b, now_ts):
                        continue

                    dist = float(np.linalg.norm(tr_a.x[:3] - tr_b.x[:3]))
                    same_identity = (
                        _is_meaningful_identity(tr_a.identity)
                        and _is_meaningful_identity(tr_b.identity)
                        and tr_a.identity == tr_b.identity
                    )
                    same_plate = bool(tr_a.plate and tr_b.plate and tr_a.plate == tr_b.plate)

                    should_merge = False
                    if (same_identity or same_plate) and dist <= 12.0:
                        should_merge = True
                    elif dist <= merge_rad:
                        should_merge = True

                    if should_merge:
                        if self._track_priority_key(tr_a) >= self._track_priority_key(tr_b):
                            self._merge_track_pair(tid_a, tid_b, now_ts, obs_assignments)
                        else:
                            self._merge_track_pair(tid_b, tid_a, now_ts, obs_assignments)
                        changed = True
                        break
                if changed:
                    break

        # Pass C: Connected-component cluster cardinality cap per coarse class
        by_class: dict[str, list[int]] = {}
        for tid, tr in self._tracks.items():
            by_class.setdefault(_coarse_class(tr.class_label), []).append(tid)

        for coarse_cls, class_tids in by_class.items():
            if len(class_tids) <= 1:
                continue
            cluster_rad = (
                self.uncalibrated_zone_vehicle_m
                if coarse_cls == "vehicle"
                else self.uncalibrated_zone_person_m
            )

            # Build connected components within `cluster_rad`
            unvisited = set(class_tids)
            clusters: list[list[int]] = []
            while unvisited:
                seed = next(iter(unvisited))
                unvisited.remove(seed)
                comp = [seed]
                queue = [seed]
                while queue:
                    curr = queue.pop(0)
                    curr_pos = self._tracks[curr].x[:3]
                    for cand in list(unvisited):
                        cand_pos = self._tracks[cand].x[:3]
                        if float(np.linalg.norm(curr_pos - cand_pos)) <= cluster_rad:
                            unvisited.remove(cand)
                            comp.append(cand)
                            queue.append(cand)
                if len(comp) > 1:
                    clusters.append(comp)

            for comp_tids in clusters:
                while True:
                    active_comp = [tid for tid in comp_tids if tid in self._tracks]
                    if len(active_comp) <= 1:
                        break
                    comp_tracks = [self._tracks[tid] for tid in active_comp]
                    logical_max = self._compute_zone_logical_max(
                        coarse_cls,
                        comp_tracks,
                        now_ts=now_ts,
                    )
                    if len(active_comp) <= logical_max:
                        break

                    # Find closest compatible pair not co-observed in the same camera batch
                    best_pair: Optional[tuple[float, int, int]] = None
                    for i in range(len(active_comp)):
                        tid_a = active_comp[i]
                        tr_a = self._tracks[tid_a]
                        for j in range(i + 1, len(active_comp)):
                            tid_b = active_comp[j]
                            tr_b = self._tracks[tid_b]
                            if not self._tracks_biometrically_compatible(tr_a, tr_b):
                                continue
                            if self._co_observed_in_same_camera_batch(tr_a, tr_b, now_ts):
                                continue
                            dist = float(np.linalg.norm(tr_a.x[:3] - tr_b.x[:3]))
                            if dist <= cluster_rad * 1.25:
                                if best_pair is None or dist < best_pair[0]:
                                    best_pair = (dist, tid_a, tid_b)

                    if best_pair is None:
                        break

                    _d, tid_a, tid_b = best_pair
                    tr_a = self._tracks[tid_a]
                    tr_b = self._tracks[tid_b]
                    if self._track_priority_key(tr_a) >= self._track_priority_key(tr_b):
                        self._merge_track_pair(tid_a, tid_b, now_ts, obs_assignments)
                    else:
                        self._merge_track_pair(tid_b, tid_a, now_ts, obs_assignments)

    def apply_biometric_result(self, update: Any) -> Optional[TrackedEntity3D]:
        """Apply an asynchronous biometric consensus update to an active track."""
        tr = self._tracks.get(int(update.track_id))
        if tr is None:
            return None

        if tr.biometric_locked and not bool(update.biometric_locked):
            return None

        if getattr(update, "best_crop_id", None):
            tr.best_crop_id = update.best_crop_id

        modality = getattr(update, "modality", None)
        if modality == "face":
            if getattr(update, "identity", None):
                tr.identity = update.identity
                tr.identity_confidence = float(getattr(update, "identity_confidence", 0.0) or 0.0)
        elif modality == "alpr":
            if getattr(update, "plate", None):
                tr.plate = update.plate
                tr.plate_confidence = float(getattr(update, "plate_confidence", 0.0) or 0.0)
            if getattr(update, "plate_whitelisted", None) is not None:
                tr.plate_whitelisted = bool(update.plate_whitelisted)
            if getattr(update, "plate_owner", None):
                tr.plate_owner = update.plate_owner
            if getattr(update, "identity", None):
                tr.identity = update.identity
                tr.identity_confidence = float(
                    getattr(update, "identity_confidence", 0.0)
                    or getattr(update, "plate_confidence", 0.0)
                    or 0.0
                )

        if bool(getattr(update, "biometric_locked", False)):
            tr.biometric_locked = True
            tr.biometric_status = "locked"
        elif not tr.biometric_locked:
            status = getattr(update, "biometric_status", "pending")
            if status in ("none", "pending", "locked", "unknown"):
                tr.biometric_status = status

        now_eval = max(self._last_now, float(getattr(update, "timestamp", self._last_now)))
        # If biometric recognition reveals this track shares identity/plate with another active track, fuse them
        if len(self._tracks) > 1 and (_is_meaningful_identity(tr.identity) or tr.plate):
            dummy_assign: dict[int, int] = {}
            self._merge_and_enforce_cardinality(now_eval, dummy_assign)
            if int(update.track_id) in self._tracks:
                tr = self._tracks[int(update.track_id)]
            else:
                # Track was merged into an older track with the same identity/plate
                matched = [
                    cand for cand in self._tracks.values()
                    if (tr.identity and cand.identity == tr.identity) or (tr.plate and cand.plate == tr.plate)
                ]
                if matched:
                    tr = matched[0]

        return tr.to_model(now_eval)

    def get_active_tracks(self) -> list[TrackedEntity3D]:
        return [tr.to_model(self._last_now) for tr in self._tracks.values()]
