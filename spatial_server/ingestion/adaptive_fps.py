from __future__ import annotations

import threading
import time
from typing import Any, Iterable, Optional


class AdaptiveFpsScheduler:
    """
    Dynamic per-camera FPS allocator sharing a global OpenVINO inference budget.

    Priority tiers:
    1. ``person``: highest weight (up to ``max_person_fps``), always boosted regardless of speed.
    2. ``vehicle``: medium weight (up to ``max_vehicle_fps``), only for active/moving foreground vehicles.
    3. ``idle``: baseline monitoring around ``idle_fps`` (floored by ``min_idle_fps`` during bursts).
    """

    _PERSON_WEIGHT = 4.5
    _VEHICLE_WEIGHT = 2.0

    def __init__(
        self,
        camera_ids: Iterable[str],
        *,
        total_budget_fps: float = 7.0,
        idle_fps: float = 1.2,
        min_idle_fps: float = 1.0,
        max_person_fps: float = 5.0,
        max_vehicle_fps: float = 3.5,
        boost_hold_s: float = 5.0,
        enabled: bool = True,
    ) -> None:
        self._lock = threading.RLock()
        self.camera_ids: list[str] = list(dict.fromkeys(str(c) for c in camera_ids if c))
        self.total_budget_fps = max(1.0, float(total_budget_fps))
        self.idle_fps = max(0.5, float(idle_fps))
        self.min_idle_fps = max(0.5, min(self.idle_fps, float(min_idle_fps)))
        self.max_person_fps = max(1.0, float(max_person_fps))
        self.max_vehicle_fps = max(1.0, float(max_vehicle_fps))
        self.boost_hold_s = max(0.0, float(boost_hold_s))
        self.enabled = bool(enabled)

        self._last_person_ts: dict[str, float] = {}
        self._last_vehicle_ts: dict[str, float] = {}
        self._current_tiers: dict[str, str] = {cam: "idle" for cam in self.camera_ids}
        self._current_fps: dict[str, float] = {}
        self._recompute_locked(now_ts=0.0)

    def register_cameras(self, camera_ids: Iterable[str]) -> None:
        with self._lock:
            changed = False
            for cam in camera_ids:
                cam_s = str(cam)
                if cam_s and cam_s not in self.camera_ids:
                    self.camera_ids.append(cam_s)
                    self._current_tiers[cam_s] = "idle"
                    changed = True
            if changed:
                self._recompute_locked(now_ts=time.time())

    def _effective_tier_locked(self, cam_id: str, now_ts: float) -> str:
        if not self.enabled:
            return "even"
        last_p = self._last_person_ts.get(cam_id, -1e18)
        if now_ts - last_p <= self.boost_hold_s:
            return "person"
        last_v = self._last_vehicle_ts.get(cam_id, -1e18)
        if now_ts - last_v <= self.boost_hold_s:
            return "vehicle"
        return "idle"

    def _recompute_locked(self, now_ts: float) -> dict[str, float]:
        n = len(self.camera_ids)
        if n == 0:
            self._current_fps = {}
            return {}

        if not self.enabled:
            even_fps = round(max(1.0, self.total_budget_fps / n), 3)
            self._current_tiers = {cam: "even" for cam in self.camera_ids}
            self._current_fps = {cam: even_fps for cam in self.camera_ids}
            return dict(self._current_fps)

        tiers = {cam: self._effective_tier_locked(cam, now_ts) for cam in self.camera_ids}
        self._current_tiers = tiers

        person_cams = [c for c, t in tiers.items() if t == "person"]
        vehicle_cams = [c for c, t in tiers.items() if t == "vehicle"]
        idle_cams = [c for c, t in tiers.items() if t == "idle"]

        if not person_cams and not vehicle_cams:
            base_idle = round(min(self.idle_fps, self.total_budget_fps / n), 3)
            self._current_fps = {cam: base_idle for cam in self.camera_ids}
            return dict(self._current_fps)

        # Reserve floor for idle cameras so monitoring continuity is never starved
        eff_min_idle = min(self.min_idle_fps, self.total_budget_fps / n)
        alloc: dict[str, float] = {c: eff_min_idle for c in idle_cams}
        remaining = max(0.0, self.total_budget_fps - eff_min_idle * len(idle_cams))

        boosted_weights: dict[str, float] = {}
        boosted_caps: dict[str, float] = {}
        for c in person_cams:
            boosted_weights[c] = self._PERSON_WEIGHT
            boosted_caps[c] = max(eff_min_idle, min(self.max_person_fps, self.total_budget_fps))
        for c in vehicle_cams:
            boosted_weights[c] = self._VEHICLE_WEIGHT
            boosted_caps[c] = max(eff_min_idle, min(self.max_vehicle_fps, self.total_budget_fps))

        for c in boosted_weights:
            alloc[c] = 0.0

        # Water-filling distribution by tier weight under per-tier max FPS caps
        active_set = list(boosted_weights.keys())
        rem = remaining
        while active_set and rem > 1e-6:
            total_w = sum(boosted_weights[c] for c in active_set)
            if total_w <= 0.0:
                break
            next_active: list[str] = []
            overflow = 0.0
            for c in active_set:
                share = rem * (boosted_weights[c] / total_w)
                cap_left = max(0.0, boosted_caps[c] - alloc[c])
                if share >= cap_left - 1e-6:
                    alloc[c] += cap_left
                    overflow += share - cap_left
                else:
                    alloc[c] += share
                    next_active.append(c)
            if len(next_active) == len(active_set):
                break
            active_set = next_active
            rem = overflow

        # If all boosted cameras hit their caps and budget remains, top up idle cameras toward idle_fps
        used_total = sum(alloc.values())
        leftover = max(0.0, self.total_budget_fps - used_total)
        if idle_cams and leftover > 1e-6:
            per_idle_headroom = max(0.0, self.idle_fps - eff_min_idle)
            add_each = min(per_idle_headroom, leftover / len(idle_cams))
            for c in idle_cams:
                alloc[c] += add_each

        self._current_fps = {c: round(max(0.25, alloc[c]), 3) for c in self.camera_ids}
        return dict(self._current_fps)

    def update_camera_activity(
        self,
        person_cameras: Iterable[str],
        active_vehicle_cameras: Iterable[str],
        now_ts: Optional[float] = None,
    ) -> dict[str, float]:
        ts = float(now_ts if now_ts is not None else time.time())
        with self._lock:
            p_set = {str(c) for c in person_cameras if c}
            v_set = {str(c) for c in active_vehicle_cameras if c}
            self.register_cameras(p_set | v_set)
            for c in p_set:
                prev = self._last_person_ts.get(c, -1e18)
                if ts > prev:
                    self._last_person_ts[c] = ts
            for c in v_set:
                prev = self._last_vehicle_ts.get(c, -1e18)
                if ts > prev:
                    self._last_vehicle_ts[c] = ts
            return self._recompute_locked(ts)

    def refresh(self, now_ts: Optional[float] = None) -> dict[str, float]:
        ts = float(now_ts if now_ts is not None else time.time())
        with self._lock:
            return self._recompute_locked(ts)

    def get_target_fps(self, camera_id: str) -> float:
        with self._lock:
            if camera_id in self._current_fps:
                return self._current_fps[camera_id]
            n = max(1, len(self.camera_ids))
            return round(min(self.idle_fps, self.total_budget_fps / n), 3)

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "total_budget_fps": self.total_budget_fps,
                "idle_fps": self.idle_fps,
                "min_idle_fps": self.min_idle_fps,
                "max_person_fps": self.max_person_fps,
                "max_vehicle_fps": self.max_vehicle_fps,
                "boost_hold_s": self.boost_hold_s,
                "total_allocated_fps": round(sum(self._current_fps.values()), 3),
                "cameras": {
                    cam: {
                        "tier": self._current_tiers.get(cam, "idle"),
                        "target_fps": self._current_fps.get(cam, self.idle_fps),
                    }
                    for cam in self.camera_ids
                },
            }
