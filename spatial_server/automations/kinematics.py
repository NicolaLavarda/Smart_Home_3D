from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
from typing import Literal, Optional

from spatial_server.domain.models import TrackedEntity3D
from .geometry import PerimeterCrossingEvent, SpatialGeometryEngine
from .models import SpatialZoneDefinition


@dataclass(frozen=True)
class KinematicSample:
    """Single timestamped 3D kinematic observation of a tracked entity."""

    timestamp: float
    x: float
    y: float
    z: float
    vx: float
    vy: float
    vz: float
    zones: frozenset[str] = field(default_factory=frozenset)


@dataclass
class ZonePresenceState:
    """Tracks continuous presence of a track inside a polygon zone."""

    zone_id: str
    entered_at: float
    last_seen_at: float
    exited_at: Optional[float] = None
    dwell_triggeredRules: set[str] = field(default_factory=set)

    @property
    def dwell_seconds(self) -> float:
        end_ts = self.exited_at if self.exited_at is not None else self.last_seen_at
        return max(0.0, end_ts - self.entered_at)


@dataclass(frozen=True)
class ZoneTransitionEvent:
    """Emitted when a track moves from one polygon zone to another."""

    track_id: int
    from_zone_id: str
    to_zone_id: str
    exited_from_at: float
    entered_to_at: float
    transit_duration_s: float
    avg_speed_mps: float


@dataclass(frozen=True)
class WindowKinematicMetrics:
    """Aggregated velocity and heading statistics over a sliding time window."""

    track_id: int
    window_s: float
    actual_duration_s: float
    sample_count: int
    mean_speed_mps: float
    net_speed_mps: float
    mean_speed_kmh: float
    mean_azimuth_deg: Optional[float]
    directional_consistency: float
    displacement_m: float
    peak_speed_mps: float = 0.0
    peak_speed_kmh: float = 0.0
    peak_speed_ts: Optional[float] = None
    peak_azimuth_deg: Optional[float] = None
    min_speed_mps: float = 0.0
    current_speed_mps: float = 0.0


@dataclass(frozen=True)
class TrackStepEvents:
    """Spatial & kinematic step events detected for a single track on a frame update."""

    track: TrackedEntity3D
    prev_sample: Optional[KinematicSample]
    curr_sample: KinematicSample
    entered_zones: list[str]
    exited_zones: list[tuple[str, float]]  # (zone_id, dwell_seconds)
    active_zone_dwells: dict[str, float]   # zone_id -> dwell_seconds
    perimeter_crossings: list[PerimeterCrossingEvent]
    zone_transitions: list[ZoneTransitionEvent]


def normalize_azimuth_deg(angle_deg: float) -> float:
    """Normalize azimuth angle into [0.0, 360.0). 0=East(+X), 90=South(+Z), 180=West(-X), 270=North(-Z)."""
    return float(angle_deg % 360.0)


def angular_difference_deg(angle_a: float, angle_b: float) -> float:
    """Return shortest unsigned angular difference in degrees [0.0, 180.0]."""
    diff = (float(angle_a) - float(angle_b) + 180.0) % 360.0 - 180.0
    return abs(diff)


class TrackKinematicHistoryBuffer:
    """
    Per-track sliding window buffer maintaining 3D positions, Kalman velocities,
    polygon zone occupancy, perimeter crossings, and Area A -> Area B transitions.
    """

    def __init__(self, max_history_s: float = 120.0, max_samples_per_track: int = 1200) -> None:
        self.max_history_s = max(10.0, float(max_history_s))
        self.max_samples_per_track = max(50, int(max_samples_per_track))
        self._samples: dict[int, deque[KinematicSample]] = {}
        self._active_zones: dict[int, dict[str, ZonePresenceState]] = {}
        self._completed_zone_visits: dict[int, deque[ZonePresenceState]] = {}
        self._latest_tracks: dict[int, TrackedEntity3D] = {}

    def get_active_track(self, track_id: int) -> Optional[TrackedEntity3D]:
        return self._latest_tracks.get(track_id)

    def get_tracks_in_zone(self, zone_id: str) -> list[TrackedEntity3D]:
        result: list[TrackedEntity3D] = []
        for tid, zmap in self._active_zones.items():
            if zone_id in zmap and tid in self._latest_tracks:
                result.append(self._latest_tracks[tid])
        return result

    def get_track_zone_dwell(self, track_id: int, zone_id: str) -> float:
        zmap = self._active_zones.get(track_id)
        if not zmap or zone_id not in zmap:
            return 0.0
        return zmap[zone_id].dwell_seconds

    def get_track_active_zone_ids(self, track_id: int) -> set[str]:
        zmap = self._active_zones.get(track_id)
        return set(zmap.keys()) if zmap else set()

    def was_track_in_zone_recently(
        self,
        track_id: int,
        zone_id: str,
        now_ts: float,
        *,
        within_s: float = 10.0,
        min_dwell_s: float = 0.0,
    ) -> bool:
        """
        Return True if `track_id` is currently inside `zone_id` (with `dwell >= min_dwell_s`)
        or exited `zone_id` within the last `within_s` seconds (with `dwell >= min_dwell_s`).
        """
        if not zone_id:
            return False
        zmap = self._active_zones.get(track_id)
        if zmap and zone_id in zmap:
            if zmap[zone_id].dwell_seconds >= min_dwell_s:
                return True
        visits = self._completed_zone_visits.get(track_id)
        if not visits:
            return False
        win = max(0.0, float(within_s))
        for visit in reversed(visits):
            if visit.zone_id != zone_id:
                continue
            ref_exit = visit.exited_at if visit.exited_at is not None else visit.last_seen_at
            if (now_ts - ref_exit) <= win and visit.dwell_seconds >= min_dwell_s:
                return True
        return False

    def update_tracks(
        self,
        tracks: list[TrackedEntity3D],
        zones: dict[str, SpatialZoneDefinition],
        now_ts: float,
    ) -> list[TrackStepEvents]:
        """
        Ingest a frame of active TrackedEntity3D states, update sliding kinematic buffers,
        and return all spatial/perimeter/transition events produced in this step.
        """
        step_events: list[TrackStepEvents] = []
        active_ids = {tr.track_id for tr in tracks}
        self._prune_inactive_tracks(active_ids, now_ts)

        polygon_zones = [
            z for z in zones.values() if z.enabled and z.geometry_type == "polygon" and len(z.vertices) >= 3
        ]
        all_enabled_zones = [z for z in zones.values() if z.enabled]

        for tr in tracks:
            tid = tr.track_id
            self._latest_tracks[tid] = tr
            buf = self._samples.setdefault(tid, deque(maxlen=self.max_samples_per_track))
            prev_sample = buf[-1] if buf else None

            active_zmap = self._active_zones.setdefault(tid, {})
            visit_history = self._completed_zone_visits.setdefault(tid, deque(maxlen=32))

            st = tr.state
            sample_ts = max(float(tr.last_seen), float(now_ts))
            if prev_sample is not None and sample_ts < prev_sample.timestamp:
                sample_ts = prev_sample.timestamp

            # 1. Evaluate 2.5D polygon containment with spatial hysteresis
            current_zone_ids: set[str] = set()
            for pzone in polygon_zones:
                was_inside = pzone.zone_id in active_zmap
                if SpatialGeometryEngine.is_point_in_zone_25d(
                    st.x,
                    st.y,
                    st.z,
                    pzone,
                    currently_inside=was_inside,
                ):
                    current_zone_ids.add(pzone.zone_id)

            entered_zones: list[str] = []
            exited_zones: list[tuple[str, float]] = []
            zone_transitions: list[ZoneTransitionEvent] = []

            # Detect exits first so immediate Area A -> Area B boundary handoff is captured
            for old_zid in list(active_zmap.keys()):
                if old_zid not in current_zone_ids:
                    finished = active_zmap.pop(old_zid)
                    finished.exited_at = sample_ts
                    exited_zones.append((old_zid, finished.dwell_seconds))
                    visit_history.append(finished)

            # Detect entries and Area A -> Area B transitions
            for new_zid in current_zone_ids:
                if new_zid in active_zmap:
                    active_zmap[new_zid].last_seen_at = sample_ts
                else:
                    entered_zones.append(new_zid)
                    active_zmap[new_zid] = ZonePresenceState(
                        zone_id=new_zid,
                        entered_at=sample_ts,
                        last_seen_at=sample_ts,
                    )
                    # Check transitions from any recently exited zone or currently overlapping zone
                    candidate_prev_visits: list[ZonePresenceState] = list(visit_history)
                    for other_zid, other_state in active_zmap.items():
                        if other_zid != new_zid:
                            candidate_prev_visits.append(other_state)

                    seen_prev_zids: set[str] = set()
                    for prev_visit in reversed(candidate_prev_visits):
                        if prev_visit.zone_id == new_zid or prev_visit.zone_id in seen_prev_zids:
                            continue
                        seen_prev_zids.add(prev_visit.zone_id)
                        ref_exit_ts = (
                            prev_visit.exited_at
                            if prev_visit.exited_at is not None
                            else prev_visit.last_seen_at
                        )
                        transit_s = max(0.0, sample_ts - ref_exit_ts)
                        win_metrics = self.compute_window_kinematics(
                            tid,
                            window_s=max(1.0, sample_ts - prev_visit.entered_at),
                            now_ts=sample_ts,
                            include_extra_point=(sample_ts, st.x, st.y, st.z, st.vx, st.vy, st.vz),
                        )
                        avg_spd = (
                            win_metrics.mean_speed_mps
                            if win_metrics is not None
                            else math.hypot(st.vx, st.vz)
                        )
                        zone_transitions.append(
                            ZoneTransitionEvent(
                                track_id=tid,
                                from_zone_id=prev_visit.zone_id,
                                to_zone_id=new_zid,
                                exited_from_at=ref_exit_ts,
                                entered_to_at=sample_ts,
                                transit_duration_s=transit_s,
                                avg_speed_mps=avg_spd,
                            )
                        )

            # 2. Evaluate perimeter / polyline crossings if we have a previous position
            perimeter_crossings: list[PerimeterCrossingEvent] = []
            if prev_sample is not None:
                prev_xyz = (prev_sample.x, prev_sample.y, prev_sample.z)
                curr_xyz = (st.x, st.y, st.z)
                for z in all_enabled_zones:
                    crossing = SpatialGeometryEngine.check_perimeter_crossing(prev_xyz, curr_xyz, z)
                    if crossing is not None:
                        perimeter_crossings.append(crossing)

            curr_sample = KinematicSample(
                timestamp=sample_ts,
                x=st.x,
                y=st.y,
                z=st.z,
                vx=st.vx,
                vy=st.vy,
                vz=st.vz,
                zones=frozenset(current_zone_ids),
            )
            buf.append(curr_sample)

            # Prune expired samples from the head of the deque
            cutoff = sample_ts - self.max_history_s
            while len(buf) > 2 and buf[0].timestamp < cutoff:
                buf.popleft()

            active_dwells = {zid: zst.dwell_seconds for zid, zst in active_zmap.items()}
            step_events.append(
                TrackStepEvents(
                    track=tr,
                    prev_sample=prev_sample,
                    curr_sample=curr_sample,
                    entered_zones=entered_zones,
                    exited_zones=exited_zones,
                    active_zone_dwells=active_dwells,
                    perimeter_crossings=perimeter_crossings,
                    zone_transitions=zone_transitions,
                )
            )

        return step_events

    def compute_window_kinematics(
        self,
        track_id: int,
        window_s: float = 2.0,
        now_ts: Optional[float] = None,
        *,
        sub_window_s: float = 1.0,
        include_extra_point: Optional[tuple[float, float, float, float, float, float, float]] = None,
    ) -> Optional[WindowKinematicMetrics]:
        """
        Compute mean speed, net speed, peak/min/current speed, mean heading azimuth (degrees),
        and directional consistency for `track_id` over the last `window_s` seconds.
        """
        buf = self._samples.get(track_id)
        if not buf and include_extra_point is None:
            return None

        samples: list[KinematicSample] = list(buf) if buf else []
        if include_extra_point is not None:
            ts, x, y, z, vx, vy, vz = include_extra_point
            samples.append(KinematicSample(timestamp=ts, x=x, y=y, z=z, vx=vx, vy=vy, vz=vz))

        if not samples:
            return None

        ref_ts = float(now_ts if now_ts is not None else samples[-1].timestamp)
        eff_win = max(0.0, float(window_s))
        cutoff = ref_ts - max(eff_win, 0.05)

        window_samples = [s for s in samples if s.timestamp >= cutoff]
        if not window_samples:
            window_samples = [samples[-1]]
        elif len(window_samples) == 1 and len(samples) >= 2:
            # Include immediate predecessor if within 2x window or 2.5s so displacement is computable
            pred = samples[-2]
            if (ref_ts - pred.timestamp) <= max(eff_win * 1.75, 2.5):
                window_samples.insert(0, pred)

        first = window_samples[0]
        last = window_samples[-1]
        actual_dt = max(0.0, last.timestamp - first.timestamp)
        disp_dx = last.x - first.x
        disp_dz = last.z - first.z
        disp_m = math.hypot(disp_dx, disp_dz)

        kalman_speeds = [math.hypot(s.vx, s.vz) for s in window_samples]
        avg_kalman_speed = sum(kalman_speeds) / len(kalman_speeds)
        net_speed = (disp_m / actual_dt) if actual_dt >= 0.15 else avg_kalman_speed

        # Blend Kalman velocity estimate with net displacement speed
        if actual_dt >= 0.4:
            mean_speed_mps = 0.55 * net_speed + 0.45 * avg_kalman_speed
        else:
            mean_speed_mps = avg_kalman_speed

        # Compute mean direction vector combining net displacement and velocity vectors
        sum_ux = 0.0
        sum_uz = 0.0
        valid_vecs = 0
        for s in window_samples:
            spd = math.hypot(s.vx, s.vz)
            if spd >= 0.08:
                sum_ux += s.vx / spd
                sum_uz += s.vz / spd
                valid_vecs += 1

        if disp_m >= 0.12:
            disp_ux = disp_dx / disp_m
            disp_uz = disp_dz / disp_m
            weight = max(1, valid_vecs)
            sum_ux += disp_ux * weight
            sum_uz += disp_uz * weight
            valid_vecs += weight

        if valid_vecs > 0 and math.hypot(sum_ux, sum_uz) > 1e-6:
            raw_deg = math.degrees(math.atan2(sum_uz, sum_ux))
            mean_azimuth_deg: Optional[float] = normalize_azimuth_deg(raw_deg)
            consistency = min(1.0, math.hypot(sum_ux, sum_uz) / valid_vecs)
        else:
            mean_azimuth_deg = None
            consistency = 0.0

        # Sliding anti-jitter sub-window peak & min speed across the lookback window
        eff_sub = min(max(0.35, float(sub_window_s)), max(0.35, eff_win))
        peak_speed_mps = 0.0
        min_speed_mps = float("inf")
        peak_speed_ts: Optional[float] = None
        peak_azimuth_deg: Optional[float] = mean_azimuth_deg

        if len(window_samples) < 2:
            spd0 = kalman_speeds[0]
            peak_speed_mps = spd0
            min_speed_mps = spd0
            peak_speed_ts = window_samples[0].timestamp
        else:
            min_dt_thresh = min(0.25, actual_dt)
            left = 0
            for j in range(1, len(window_samples)):
                tj = window_samples[j].timestamp
                while left + 1 < j and (tj - window_samples[left + 1].timestamp) >= eff_sub:
                    left += 1
                # Pick i between left and left+1 closest to (tj - eff_sub)
                i = left
                if left + 1 < j:
                    err_l = abs((tj - window_samples[left].timestamp) - eff_sub)
                    err_r = abs((tj - window_samples[left + 1].timestamp) - eff_sub)
                    if err_r < err_l and (tj - window_samples[left + 1].timestamp) >= min_dt_thresh:
                        i = left + 1

                ti = window_samples[i].timestamp
                dt_ij = max(0.0, tj - ti)
                avg_k_ij = sum(kalman_speeds[i : j + 1]) / (j - i + 1)
                dx_ij = window_samples[j].x - window_samples[i].x
                dz_ij = window_samples[j].z - window_samples[i].z
                disp_ij = math.hypot(dx_ij, dz_ij)

                if dt_ij >= min_dt_thresh and dt_ij > 1e-4:
                    sub_speed = 0.55 * (disp_ij / dt_ij) + 0.45 * avg_k_ij
                else:
                    sub_speed = avg_k_ij

                if sub_speed > peak_speed_mps or peak_speed_ts is None:
                    peak_speed_mps = sub_speed
                    peak_speed_ts = tj
                    peak_azimuth_deg = self._compute_slice_azimuth(window_samples[i : j + 1], dx_ij, dz_ij, disp_ij)
                if sub_speed < min_speed_mps:
                    min_speed_mps = sub_speed

            if min_speed_mps == float("inf"):
                min_speed_mps = mean_speed_mps

        # Current speed over most recent <= 0.8s tail
        curr_cutoff = ref_ts - min(0.8, max(0.2, eff_win))
        curr_slice = [s for s in window_samples if s.timestamp >= curr_cutoff]
        if len(curr_slice) >= 2:
            c_first, c_last = curr_slice[0], curr_slice[-1]
            c_dt = max(0.0, c_last.timestamp - c_first.timestamp)
            c_avg_k = sum(math.hypot(s.vx, s.vz) for s in curr_slice) / len(curr_slice)
            if c_dt >= 0.15:
                c_disp = math.hypot(c_last.x - c_first.x, c_last.z - c_first.z)
                current_speed_mps = 0.55 * (c_disp / c_dt) + 0.45 * c_avg_k
            else:
                current_speed_mps = c_avg_k
        else:
            current_speed_mps = kalman_speeds[-1]

        return WindowKinematicMetrics(
            track_id=track_id,
            window_s=eff_win,
            actual_duration_s=actual_dt,
            sample_count=len(window_samples),
            mean_speed_mps=float(round(mean_speed_mps, 3)),
            net_speed_mps=float(round(net_speed, 3)),
            mean_speed_kmh=float(round(mean_speed_mps * 3.6, 2)),
            mean_azimuth_deg=float(round(mean_azimuth_deg, 1)) if mean_azimuth_deg is not None else None,
            directional_consistency=float(round(consistency, 3)),
            displacement_m=float(round(disp_m, 3)),
            peak_speed_mps=float(round(peak_speed_mps, 3)),
            peak_speed_kmh=float(round(peak_speed_mps * 3.6, 2)),
            peak_speed_ts=round(peak_speed_ts, 3) if peak_speed_ts is not None else None,
            peak_azimuth_deg=float(round(peak_azimuth_deg, 1)) if peak_azimuth_deg is not None else None,
            min_speed_mps=float(round(min_speed_mps, 3)),
            current_speed_mps=float(round(current_speed_mps, 3)),
        )

    @staticmethod
    def _compute_slice_azimuth(
        slice_samples: list[KinematicSample],
        disp_dx: float,
        disp_dz: float,
        disp_m: float,
    ) -> Optional[float]:
        sum_ux = 0.0
        sum_uz = 0.0
        valid = 0
        for s in slice_samples:
            spd = math.hypot(s.vx, s.vz)
            if spd >= 0.08:
                sum_ux += s.vx / spd
                sum_uz += s.vz / spd
                valid += 1
        if disp_m >= 0.12:
            w = max(1, valid)
            sum_ux += (disp_dx / disp_m) * w
            sum_uz += (disp_dz / disp_m) * w
            valid += w
        if valid > 0 and math.hypot(sum_ux, sum_uz) > 1e-6:
            return normalize_azimuth_deg(math.degrees(math.atan2(sum_uz, sum_ux)))
        return None

    def _prune_inactive_tracks(self, active_ids: set[int], now_ts: float) -> None:
        stale_cutoff = now_ts - max(self.max_history_s, 60.0)
        for tid in list(self._samples.keys()):
            if tid not in active_ids:
                buf = self._samples[tid]
                if not buf or buf[-1].timestamp < stale_cutoff:
                    self._samples.pop(tid, None)
                    self._active_zones.pop(tid, None)
                    self._completed_zone_visits.pop(tid, None)
                    self._latest_tracks.pop(tid, None)
