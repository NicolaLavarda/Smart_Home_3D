from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
import math
import re
from typing import Any, Callable, Optional, Type

from spatial_server.domain.models import TrackedEntity3D
from .astronomy import AstronomicalClock
from .kinematics import (
    TrackKinematicHistoryBuffer,
    TrackStepEvents,
    WindowKinematicMetrics,
    angular_difference_deg,
)
from .models import (
    ConditionSpec,
    SpatialZoneDefinition,
    SubjectFilterSpec,
    TriggerSpec,
    VirtualEntityDefinition,
)


def _coarse_class(label: str) -> str:
    norm = (label or "").strip().lower()
    if norm in ("car", "truck", "bus", "motorcycle", "motorbike", "vehicle"):
        return "vehicle"
    return norm


def _is_known_identity(identity: Optional[str], known_identities_lower: set[str]) -> bool:
    if not identity:
        return False
    norm = identity.strip().lower()
    if not norm or norm in ("sconosciuto", "unknown", "none", "pending"):
        return False
    if known_identities_lower:
        return norm in known_identities_lower
    return True


class SubjectFilterEvaluator:
    """Evaluates whether a TrackedEntity3D satisfies a SubjectFilterSpec."""

    @staticmethod
    def matches(
        track: TrackedEntity3D,
        spec: SubjectFilterSpec,
        *,
        known_identities_lower: set[str],
        whitelisted_plates_upper: set[str],
    ) -> bool:
        # 1. Object Class Filter
        allowed_classes = {c.strip().lower() for c in spec.classes if c and c.strip()}
        if allowed_classes and "any" not in allowed_classes and "all" not in allowed_classes:
            raw_cls = (track.class_label or "").strip().lower()
            coarse_cls = _coarse_class(raw_cls)
            if raw_cls not in allowed_classes and coarse_cls not in allowed_classes:
                return False

        # 2. Face Biometric Filter
        face_mode = spec.face_mode
        if face_mode != "any":
            id_norm = (track.identity or "").strip().lower()
            is_known = _is_known_identity(track.identity, known_identities_lower)
            target_ids = {i.strip().lower() for i in spec.identities if i and i.strip()}

            if face_mode == "known" and not is_known:
                return False
            elif face_mode == "unknown" and is_known:
                return False
            elif face_mode == "include":
                if not is_known or id_norm not in target_ids:
                    return False
            elif face_mode == "exclude":
                if is_known and id_norm in target_ids:
                    return False

        # 3. License Plate (ALPR) Filter
        plate_mode = spec.plate_mode
        if plate_mode != "any":
            raw_plate = re.sub(r"[^A-Z0-9]", "", (track.plate or "").upper())
            is_wl = bool(
                track.plate_whitelisted
                or (raw_plate and raw_plate in whitelisted_plates_upper)
            )
            target_plates = {
                re.sub(r"[^A-Z0-9]", "", p.upper())
                for p in spec.plates
                if p and p.strip()
            }

            if plate_mode == "whitelisted" and not is_wl:
                return False
            elif plate_mode == "not_whitelisted" and is_wl:
                return False
            elif plate_mode == "include":
                if not raw_plate or raw_plate not in target_plates:
                    return False
            elif plate_mode == "exclude":
                if raw_plate and raw_plate in target_plates:
                    return False

        return True

    @staticmethod
    def should_defer_for_biometrics(
        track: TrackedEntity3D,
        spec: SubjectFilterSpec,
        now_ts: float,
        track_first_seen_ts: float,
    ) -> bool:
        """
        Return True if the filter depends on face/plate identity, the track's biometric
        resolution is still pending/none, and we are still inside `spec.biometric_grace_s`.
        """
        if spec.biometric_grace_s <= 0.0:
            return False
        if (now_ts - track_first_seen_ts) > spec.biometric_grace_s:
            return False
        needs_face = spec.face_mode != "any"
        needs_plate = spec.plate_mode != "any"
        if not needs_face and not needs_plate:
            return False
        if track.biometric_locked or track.biometric_status in ("locked", "unknown"):
            return False
        if needs_face and not track.identity:
            return True
        if needs_plate and not track.plate:
            return True
        return False


@dataclass(frozen=True)
class EntityStateSnapshot:
    """Unified snapshot of either an internal `sh3d.*` entity or a Home Assistant entity."""

    entity_id: str
    state: str
    attributes: dict[str, Any] = field(default_factory=dict)
    last_changed: float = 0.0
    source: str = "internal"  # "internal" | "ha"


@dataclass(frozen=True)
class TriggerActivationEvent:
    """Describes why and how a specific trigger fired."""

    trigger_id: str
    trigger_type: str
    timestamp: float
    summary: str
    track: Optional[TrackedEntity3D] = None
    zone_id: Optional[str] = None
    from_zone_id: Optional[str] = None
    to_zone_id: Optional[str] = None
    entity_id: Optional[str] = None
    old_state: Optional[str] = None
    new_state: Optional[str] = None
    kinematics: Optional[WindowKinematicMetrics] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationContext:
    """Read-only world context passed to Trigger and Condition evaluators."""

    now_ts: float
    kinematics_buffer: TrackKinematicHistoryBuffer
    zones: dict[str, SpatialZoneDefinition]
    virtual_entities: dict[str, VirtualEntityDefinition]
    ha_states: dict[str, EntityStateSnapshot]
    astronomical_clock: AstronomicalClock
    known_identities_lower: set[str]
    whitelisted_plates_upper: set[str]
    active_tracks: list[TrackedEntity3D] = field(default_factory=list)
    step_events_by_track: dict[int, TrackStepEvents] = field(default_factory=dict)
    entity_changes: list[tuple[str, Optional[str], str]] = field(default_factory=list)
    biometric_updates: list[dict[str, Any]] = field(default_factory=list)
    trigger_event: Optional[TriggerActivationEvent] = None

    def resolve_entity(self, entity_id: str) -> Optional[EntityStateSnapshot]:
        clean = (entity_id or "").strip()
        if not clean:
            return None
        lower = clean.lower()
        if lower in self.virtual_entities:
            ve = self.virtual_entities[lower]
            return EntityStateSnapshot(
                entity_id=ve.entity_id,
                state=str(ve.state),
                attributes=dict(ve.attributes),
                last_changed=ve.last_changed,
                source="internal",
            )
        if not lower.startswith("sh3d.") and f"sh3d.{lower}" in self.virtual_entities:
            ve = self.virtual_entities[f"sh3d.{lower}"]
            return EntityStateSnapshot(
                entity_id=ve.entity_id,
                state=str(ve.state),
                attributes=dict(ve.attributes),
                last_changed=ve.last_changed,
                source="internal",
            )
        if clean in self.ha_states:
            return self.ha_states[clean]
        if lower in self.ha_states:
            return self.ha_states[lower]
        return None


# ============================================================================
# TRIGGER EVALUATORS (Strategy + Registry Pattern)
# ============================================================================


class BaseTriggerEvaluator(ABC):
    """Abstract base strategy for evaluating a specific TriggerSpec type."""

    trigger_type: str = ""

    @abstractmethod
    def evaluate(
        self,
        rule_id: str,
        spec: TriggerSpec,
        ctx: EvaluationContext,
        runtime_state: dict[str, Any],
    ) -> list[TriggerActivationEvent]:
        """Return a list of TriggerActivationEvents that fired on this tick/step."""


class TriggerRegistry:
    """Open/Closed registry mapping trigger_type strings to BaseTriggerEvaluator classes."""

    _evaluators: dict[str, BaseTriggerEvaluator] = {}

    @classmethod
    def register(cls, trigger_type: str) -> Callable[[Type[BaseTriggerEvaluator]], Type[BaseTriggerEvaluator]]:
        def decorator(subclass: Type[BaseTriggerEvaluator]) -> Type[BaseTriggerEvaluator]:
            subclass.trigger_type = trigger_type
            cls._evaluators[trigger_type] = subclass()
            return subclass

        return decorator

    @classmethod
    def get(cls, trigger_type: str) -> Optional[BaseTriggerEvaluator]:
        return cls._evaluators.get(trigger_type)


@TriggerRegistry.register("zone_presence")
class ZonePresenceTriggerEvaluator(BaseTriggerEvaluator):
    """
    Fires when a matching subject enters, exits, or dwells for `min_dwell_s`
    inside a 2.5D polygonal area (`zone_id`).
    """

    def evaluate(
        self,
        rule_id: str,
        spec: TriggerSpec,
        ctx: EvaluationContext,
        runtime_state: dict[str, Any],
    ) -> list[TriggerActivationEvent]:
        if not ctx.step_events_by_track:
            return []

        zone_id = str(spec.params.get("zone_id") or "").strip()
        if not zone_id or zone_id not in ctx.zones:
            return []
        zone = ctx.zones[zone_id]
        event_mode = str(spec.params.get("event") or "enter").strip().lower()
        min_dwell_s = max(0.0, float(spec.params.get("min_dwell_s") or 0.0))

        dwell_fired: set[int] = runtime_state.setdefault("dwell_fired_tracks", set())
        active_in_zone_ids = {t.track_id for t in ctx.kinematics_buffer.get_tracks_in_zone(zone_id)}
        dwell_fired.intersection_update(active_in_zone_ids)

        activations: list[TriggerActivationEvent] = []
        for tid, step in ctx.step_events_by_track.items():
            tr = step.track
            if not SubjectFilterEvaluator.matches(
                tr,
                spec.subject_filter,
                known_identities_lower=ctx.known_identities_lower,
                whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            ):
                continue

            subj_label = tr.identity or tr.plate or tr.class_label
            if event_mode == "enter" and zone_id in step.entered_zones:
                if min_dwell_s <= 0.0:
                    activations.append(
                        TriggerActivationEvent(
                            trigger_id=spec.trigger_id,
                            trigger_type=spec.type,
                            timestamp=ctx.now_ts,
                            summary=f"{subj_label} (#{tid}) entrato in '{zone.name}'",
                            track=tr,
                            zone_id=zone_id,
                            extra={"event": "enter", "zone_name": zone.name},
                        )
                    )
            elif event_mode == "exit":
                for ex_zid, dwell_s in step.exited_zones:
                    if ex_zid == zone_id and dwell_s >= min_dwell_s:
                        activations.append(
                            TriggerActivationEvent(
                                trigger_id=spec.trigger_id,
                                trigger_type=spec.type,
                                timestamp=ctx.now_ts,
                                summary=f"{subj_label} (#{tid}) uscito da '{zone.name}' (permanenza {dwell_s:.1f}s)",
                                track=tr,
                                zone_id=zone_id,
                                extra={"event": "exit", "zone_name": zone.name, "dwell_s": round(dwell_s, 2)},
                            )
                        )
            if event_mode == "dwell" or (event_mode == "enter" and min_dwell_s > 0.0):
                curr_dwell = step.active_zone_dwells.get(zone_id)
                if curr_dwell is not None and curr_dwell >= max(0.1, min_dwell_s) and tid not in dwell_fired:
                    dwell_fired.add(tid)
                    activations.append(
                        TriggerActivationEvent(
                            trigger_id=spec.trigger_id,
                            trigger_type=spec.type,
                            timestamp=ctx.now_ts,
                            summary=f"{subj_label} (#{tid}) in '{zone.name}' da {curr_dwell:.1f}s",
                            track=tr,
                            zone_id=zone_id,
                            extra={"event": "dwell", "zone_name": zone.name, "dwell_s": round(curr_dwell, 2)},
                        )
                    )

        return activations


@TriggerRegistry.register("perimeter_crossing")
class PerimeterCrossingTriggerEvaluator(BaseTriggerEvaluator):
    """
    Fires when a matching subject's trajectory vector crosses an oriented
    perimeter polyline or polygon boundary in direction `a_to_b`, `b_to_a`, or `both`.
    """

    def evaluate(
        self,
        rule_id: str,
        spec: TriggerSpec,
        ctx: EvaluationContext,
        runtime_state: dict[str, Any],
    ) -> list[TriggerActivationEvent]:
        if not ctx.step_events_by_track:
            return []

        perimeter_id = str(spec.params.get("perimeter_id") or spec.params.get("zone_id") or "").strip()
        if not perimeter_id or perimeter_id not in ctx.zones:
            return []
        zone = ctx.zones[perimeter_id]
        want_dir = str(spec.params.get("direction") or "both").strip().lower()

        activations: list[TriggerActivationEvent] = []
        for tid, step in ctx.step_events_by_track.items():
            if not step.perimeter_crossings:
                continue
            tr = step.track
            if not SubjectFilterEvaluator.matches(
                tr,
                spec.subject_filter,
                known_identities_lower=ctx.known_identities_lower,
                whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            ):
                continue

            for cross in step.perimeter_crossings:
                if cross.zone_id != perimeter_id:
                    continue
                if want_dir not in ("both", "any") and cross.direction != want_dir:
                    continue
                subj_label = tr.identity or tr.plate or tr.class_label
                dir_label = "A → B (Entrata)" if cross.direction == "a_to_b" else "B → A (Uscita)"
                activations.append(
                    TriggerActivationEvent(
                        trigger_id=spec.trigger_id,
                        trigger_type=spec.type,
                        timestamp=ctx.now_ts,
                        summary=f"{subj_label} (#{tid}) ha attraversato '{zone.name}' [{dir_label}]",
                        track=tr,
                        zone_id=perimeter_id,
                        extra={
                            "zone_name": zone.name,
                            "direction": cross.direction,
                            "segment_index": cross.segment_index,
                            "intersection_xz": list(cross.intersection_xz),
                        },
                    )
                )
        return activations


@TriggerRegistry.register("zone_transition")
class ZoneTransitionTriggerEvaluator(BaseTriggerEvaluator):
    """
    Fires when a subject moves from `from_zone_id` to `to_zone_id` within `max_transit_s`,
    with optional mean speed bounds `[min_speed_mps, max_speed_mps]`.
    """

    def evaluate(
        self,
        rule_id: str,
        spec: TriggerSpec,
        ctx: EvaluationContext,
        runtime_state: dict[str, Any],
    ) -> list[TriggerActivationEvent]:
        if not ctx.step_events_by_track:
            return []

        from_zid = str(spec.params.get("from_zone_id") or "").strip()
        to_zid = str(spec.params.get("to_zone_id") or "").strip()
        if not from_zid or not to_zid:
            return []

        max_transit_s = float(spec.params.get("max_transit_s") or 30.0)
        min_speed_mps = float(spec.params.get("min_speed_mps") or 0.0)
        max_speed_mps = (
            float(spec.params["max_speed_mps"])
            if spec.params.get("max_speed_mps") is not None
            else float("inf")
        )

        activations: list[TriggerActivationEvent] = []
        for tid, step in ctx.step_events_by_track.items():
            if not step.zone_transitions:
                continue
            tr = step.track
            if not SubjectFilterEvaluator.matches(
                tr,
                spec.subject_filter,
                known_identities_lower=ctx.known_identities_lower,
                whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            ):
                continue

            for trans in step.zone_transitions:
                if trans.from_zone_id != from_zid or trans.to_zone_id != to_zid:
                    continue
                if trans.transit_duration_s > max_transit_s:
                    continue
                if trans.avg_speed_mps < min_speed_mps or trans.avg_speed_mps > max_speed_mps:
                    continue

                from_name = ctx.zones[from_zid].name if from_zid in ctx.zones else from_zid
                to_name = ctx.zones[to_zid].name if to_zid in ctx.zones else to_zid
                subj_label = tr.identity or tr.plate or tr.class_label
                activations.append(
                    TriggerActivationEvent(
                        trigger_id=spec.trigger_id,
                        trigger_type=spec.type,
                        timestamp=ctx.now_ts,
                        summary=(
                            f"{subj_label} (#{tid}) passato da '{from_name}' a '{to_name}' "
                            f"in {trans.transit_duration_s:.1f}s ({trans.avg_speed_mps:.2f} m/s)"
                        ),
                        track=tr,
                        zone_id=to_zid,
                        from_zone_id=from_zid,
                        to_zone_id=to_zid,
                        extra={
                            "from_zone_name": from_name,
                            "to_zone_name": to_name,
                            "transit_duration_s": round(trans.transit_duration_s, 2),
                            "avg_speed_mps": round(trans.avg_speed_mps, 2),
                            "avg_speed_kmh": round(trans.avg_speed_mps * 3.6, 1),
                        },
                    )
                )
        return activations


@TriggerRegistry.register("kinematic_vector")
class KinematicVectorTriggerEvaluator(BaseTriggerEvaluator):
    """
    Fires when a subject moves with a mean direction (`target_azimuth_deg ± azimuth_tolerance_deg`)
    and/or mean speed (`[min_speed_mps, max_speed_mps]`) sustained over `min_duration_s` seconds.
    """

    def evaluate(
        self,
        rule_id: str,
        spec: TriggerSpec,
        ctx: EvaluationContext,
        runtime_state: dict[str, Any],
    ) -> list[TriggerActivationEvent]:
        if not ctx.step_events_by_track:
            return []

        zone_id = str(spec.params.get("zone_id") or "").strip()
        min_duration_s = max(0.3, float(spec.params.get("min_duration_s") or 1.5))
        target_azimuth = (
            float(spec.params["target_azimuth_deg"])
            if spec.params.get("target_azimuth_deg") is not None and str(spec.params.get("target_azimuth_deg")) != ""
            else None
        )
        azimuth_tol = max(1.0, float(spec.params.get("azimuth_tolerance_deg") or 35.0))
        min_speed_mps = float(spec.params.get("min_speed_mps") or 0.0)
        max_speed_mps = (
            float(spec.params["max_speed_mps"])
            if spec.params.get("max_speed_mps") is not None and str(spec.params.get("max_speed_mps")) != ""
            else float("inf")
        )
        min_consistency = float(spec.params.get("min_consistency") or 0.45)

        latched_tracks: dict[int, float] = runtime_state.setdefault("latched_tracks", {})
        retrigger_after_s = max(min_duration_s * 1.5, 4.0)

        activations: list[TriggerActivationEvent] = []
        for tid, step in ctx.step_events_by_track.items():
            tr = step.track
            if zone_id and zone_id not in step.curr_sample.zones:
                latched_tracks.pop(tid, None)
                continue

            if not SubjectFilterEvaluator.matches(
                tr,
                spec.subject_filter,
                known_identities_lower=ctx.known_identities_lower,
                whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            ):
                continue

            metrics = ctx.kinematics_buffer.compute_window_kinematics(
                tid,
                window_s=min_duration_s,
                now_ts=step.curr_sample.timestamp,
            )
            if metrics is None or metrics.actual_duration_s < min_duration_s * 0.75:
                continue

            if metrics.mean_speed_mps < min_speed_mps or metrics.mean_speed_mps > max_speed_mps:
                latched_tracks.pop(tid, None)
                continue

            if target_azimuth is not None:
                if metrics.mean_azimuth_deg is None:
                    latched_tracks.pop(tid, None)
                    continue
                ang_err = angular_difference_deg(metrics.mean_azimuth_deg, target_azimuth)
                if ang_err > azimuth_tol or metrics.directional_consistency < min_consistency:
                    latched_tracks.pop(tid, None)
                    continue

            last_fired_ts = latched_tracks.get(tid)
            if last_fired_ts is not None and (ctx.now_ts - last_fired_ts) < retrigger_after_s:
                continue

            latched_tracks[tid] = ctx.now_ts
            subj_label = tr.identity or tr.plate or tr.class_label
            dir_part = f", dir {metrics.mean_azimuth_deg:.0f}°" if metrics.mean_azimuth_deg is not None else ""
            activations.append(
                TriggerActivationEvent(
                    trigger_id=spec.trigger_id,
                    trigger_type=spec.type,
                    timestamp=ctx.now_ts,
                    summary=(
                        f"{subj_label} (#{tid}) velocità media {metrics.mean_speed_mps:.2f} m/s "
                        f"({metrics.mean_speed_kmh:.1f} km/h{dir_part}) per {metrics.actual_duration_s:.1f}s"
                    ),
                    track=tr,
                    zone_id=zone_id or None,
                    kinematics=metrics,
                    extra={
                        "mean_speed_mps": metrics.mean_speed_mps,
                        "mean_speed_kmh": metrics.mean_speed_kmh,
                        "mean_azimuth_deg": metrics.mean_azimuth_deg,
                        "directional_consistency": metrics.directional_consistency,
                        "duration_s": round(metrics.actual_duration_s, 2),
                    },
                )
            )
        return activations


@TriggerRegistry.register("time_schedule")
class TimeScheduleTriggerEvaluator(BaseTriggerEvaluator):
    """
    Fires on fixed clock times (`HH:MM`), astronomical `sunrise` / `sunset`
    with `offset_minutes` (±), or periodic intervals.
    """

    def evaluate(
        self,
        rule_id: str,
        spec: TriggerSpec,
        ctx: EvaluationContext,
        runtime_state: dict[str, Any],
    ) -> list[TriggerActivationEvent]:
        mode = str(spec.params.get("mode") or "fixed_time").strip().lower()
        local_dt = datetime.fromtimestamp(ctx.now_ts).astimezone()

        days = spec.params.get("days_of_week")
        if isinstance(days, list) and days:
            allowed_days = {int(d) for d in days if str(d).isdigit()}
            if allowed_days and local_dt.weekday() not in allowed_days:
                return []

        day_key = local_dt.strftime("%Y-%m-%d")

        if mode == "interval":
            interval_s = max(5.0, float(spec.params.get("interval_seconds") or (float(spec.params.get("interval_minutes") or 5.0) * 60.0)))
            last_tick = runtime_state.get("last_interval_ts")
            if last_tick is None:
                runtime_state["last_interval_ts"] = ctx.now_ts
                return []
            if (ctx.now_ts - float(last_tick)) >= interval_s:
                runtime_state["last_interval_ts"] = ctx.now_ts
                return [
                    TriggerActivationEvent(
                        trigger_id=spec.trigger_id,
                        trigger_type=spec.type,
                        timestamp=ctx.now_ts,
                        summary=f"Timer periodico ({interval_s:.0f}s)",
                        extra={"mode": "interval", "interval_seconds": interval_s},
                    )
                ]
            return []

        target_ts: Optional[float] = None
        label = ""

        if mode == "fixed_time":
            hhmm = str(spec.params.get("at") or spec.params.get("time_hhmm") or "00:00").strip()
            parts = hhmm.split(":")
            if len(parts) < 2:
                return []
            try:
                hh, mm = int(parts[0]), int(parts[1])
                ss = int(parts[2]) if len(parts) > 2 else 0
            except ValueError:
                return []
            target_dt = local_dt.replace(hour=max(0, min(23, hh)), minute=max(0, min(59, mm)), second=max(0, min(59, ss)), microsecond=0)
            target_ts = target_dt.timestamp()
            label = f"Orario programmato {hh:02d}:{mm:02d}"
        elif mode in ("sunrise", "sunset"):
            sunrise_ts, sunset_ts = ctx.astronomical_clock.get_sunrise_sunset_unix(ctx.now_ts)
            offset_min = float(spec.params.get("offset_minutes") or 0.0)
            base_ts = sunrise_ts if mode == "sunrise" else sunset_ts
            target_ts = base_ts + offset_min * 60.0
            astro_name = "Alba" if mode == "sunrise" else "Tramonto"
            sign = "+" if offset_min >= 0 else ""
            label = f"{astro_name} ({sign}{offset_min:.0f} min)" if offset_min != 0 else astro_name

        if target_ts is None:
            return []

        fired_day = runtime_state.get("fired_day_key")
        # Fire once on the day when now_ts crosses target_ts within a 45-second window
        if fired_day != day_key and 0.0 <= (ctx.now_ts - target_ts) <= 45.0:
            runtime_state["fired_day_key"] = day_key
            return [
                TriggerActivationEvent(
                    trigger_id=spec.trigger_id,
                    trigger_type=spec.type,
                    timestamp=ctx.now_ts,
                    summary=label,
                    extra={"mode": mode, "target_ts": target_ts},
                )
            ]
        return []


@TriggerRegistry.register("entity_state_change")
class EntityStateChangeTriggerEvaluator(BaseTriggerEvaluator):
    """
    Fires when an internal program entity (`sh3d.*`) or a Home Assistant entity
    transitions from `from_state` to `to_state` (with optional `for_duration_s` hold).
    """

    def evaluate(
        self,
        rule_id: str,
        spec: TriggerSpec,
        ctx: EvaluationContext,
        runtime_state: dict[str, Any],
    ) -> list[TriggerActivationEvent]:
        target_eid = str(spec.params.get("entity_id") or "").strip()
        if not target_eid:
            return []

        want_from = str(spec.params["from_state"]).strip().lower() if spec.params.get("from_state") not in (None, "", "any", "*") else None
        want_to = str(spec.params["to_state"]).strip().lower() if spec.params.get("to_state") not in (None, "", "any", "*") else None
        for_duration_s = max(0.0, float(spec.params.get("for_duration_s") or 0.0))

        target_lower = target_eid.lower()
        activations: list[TriggerActivationEvent] = []

        # 1. Check immediate state transition events in this cycle
        for changed_id, old_st, new_st in ctx.entity_changes:
            c_lower = changed_id.lower()
            if c_lower != target_lower and c_lower != f"sh3d.{target_lower}":
                continue

            old_norm = (old_st or "").strip().lower()
            new_norm = (new_st or "").strip().lower()
            if old_norm == new_norm:
                continue
            if want_from is not None and old_norm != want_from:
                continue
            if want_to is not None and new_norm != want_to:
                runtime_state.pop("pending_hold", None)
                continue

            if for_duration_s <= 0.0:
                activations.append(
                    TriggerActivationEvent(
                        trigger_id=spec.trigger_id,
                        trigger_type=spec.type,
                        timestamp=ctx.now_ts,
                        summary=f"Entità '{changed_id}' passata da '{old_st}' a '{new_st}'",
                        entity_id=changed_id,
                        old_state=old_st,
                        new_state=new_st,
                    )
                )
            else:
                runtime_state["pending_hold"] = {
                    "entity_id": changed_id,
                    "old_state": old_st,
                    "new_state": new_st,
                    "started_at": ctx.now_ts,
                }

        # 2. Check pending `for_duration_s` hold timer
        pending = runtime_state.get("pending_hold")
        if pending is not None and for_duration_s > 0.0:
            snap = ctx.resolve_entity(pending["entity_id"])
            if snap is None or snap.state.strip().lower() != str(pending["new_state"]).strip().lower():
                runtime_state.pop("pending_hold", None)
            elif (ctx.now_ts - float(pending["started_at"])) >= for_duration_s:
                runtime_state.pop("pending_hold", None)
                activations.append(
                    TriggerActivationEvent(
                        trigger_id=spec.trigger_id,
                        trigger_type=spec.type,
                        timestamp=ctx.now_ts,
                        summary=(
                            f"Entità '{pending['entity_id']}' in stato '{pending['new_state']}' "
                            f"da {for_duration_s:.1f}s"
                        ),
                        entity_id=pending["entity_id"],
                        old_state=pending["old_state"],
                        new_state=pending["new_state"],
                    )
                )

        return activations


@TriggerRegistry.register("biometric_detection")
class BiometricDetectionTriggerEvaluator(BaseTriggerEvaluator):
    """Fires immediately when a biometric face/ALPR event matches `subject_filter`."""

    def evaluate(
        self,
        rule_id: str,
        spec: TriggerSpec,
        ctx: EvaluationContext,
        runtime_state: dict[str, Any],
    ) -> list[TriggerActivationEvent]:
        if not ctx.biometric_updates:
            return []

        want_mod = str(spec.params.get("modality") or "any").strip().lower()
        want_cam = str(spec.params.get("camera_id") or "").strip()

        activations: list[TriggerActivationEvent] = []
        for upd in ctx.biometric_updates:
            mod = str(upd.get("modality") or "").lower()
            if want_mod not in ("any", "", "*") and mod != want_mod:
                continue
            cam_id = str(upd.get("camera_id") or "")
            if want_cam and want_cam != cam_id:
                continue

            tid = int(upd.get("track_id") or 0)
            tr = ctx.kinematics_buffer.get_active_track(tid)
            if tr is None:
                continue

            if not SubjectFilterEvaluator.matches(
                tr,
                spec.subject_filter,
                known_identities_lower=ctx.known_identities_lower,
                whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            ):
                continue

            subj_label = tr.identity or tr.plate or "Sconosciuto"
            activations.append(
                TriggerActivationEvent(
                    trigger_id=spec.trigger_id,
                    trigger_type=spec.type,
                    timestamp=ctx.now_ts,
                    summary=f"Riconoscimento {mod.upper()}: '{subj_label}' su {cam_id} (#{tid})",
                    track=tr,
                    extra={"modality": mod, "camera_id": cam_id},
                )
            )
        return activations


@TriggerRegistry.register("proximity_3d")
class Proximity3DTriggerEvaluator(BaseTriggerEvaluator):
    """Fires when a matching subject approaches within `radius_m` of a 3D point for `min_dwell_s`."""

    def evaluate(
        self,
        rule_id: str,
        spec: TriggerSpec,
        ctx: EvaluationContext,
        runtime_state: dict[str, Any],
    ) -> list[TriggerActivationEvent]:
        if not ctx.step_events_by_track:
            return []

        tx = float(spec.params.get("target_x") or 0.0)
        tz = float(spec.params.get("target_z") or 0.0)
        radius_m = max(0.2, float(spec.params.get("radius_m") or 2.0))
        min_dwell_s = max(0.0, float(spec.params.get("min_dwell_s") or 0.0))
        target_name = str(spec.params.get("target_name") or f"Punto ({tx:.1f}, {tz:.1f})")

        entered_at_by_tid: dict[int, float] = runtime_state.setdefault("entered_at_by_tid", {})
        fired_tids: set[int] = runtime_state.setdefault("fired_tids", set())

        activations: list[TriggerActivationEvent] = []
        for tid, step in ctx.step_events_by_track.items():
            tr = step.track
            dist = math.hypot(tr.state.x - tx, tr.state.z - tz)
            if dist > radius_m:
                entered_at_by_tid.pop(tid, None)
                fired_tids.discard(tid)
                continue

            if not SubjectFilterEvaluator.matches(
                tr,
                spec.subject_filter,
                known_identities_lower=ctx.known_identities_lower,
                whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            ):
                continue

            enter_ts = entered_at_by_tid.setdefault(tid, ctx.now_ts)
            dwell_s = max(0.0, ctx.now_ts - enter_ts)
            if dwell_s >= min_dwell_s and tid not in fired_tids:
                fired_tids.add(tid)
                subj_label = tr.identity or tr.plate or tr.class_label
                activations.append(
                    TriggerActivationEvent(
                        trigger_id=spec.trigger_id,
                        trigger_type=spec.type,
                        timestamp=ctx.now_ts,
                        summary=f"{subj_label} (#{tid}) a {dist:.2f}m da '{target_name}'",
                        track=tr,
                        extra={"distance_m": round(dist, 2), "target_name": target_name},
                    )
                )
        return activations


# ============================================================================
# CONDITION EVALUATORS (Specification Pattern / Recursive Boolean AST)
# ============================================================================


def _compare_values(actual: Any, operator: str, expected: Any) -> bool:
    op = (operator or "==").strip().lower()
    if op in ("==", "eq", "equals", "="):
        try:
            return float(actual) == float(expected)
        except (TypeError, ValueError):
            return str(actual).strip().lower() == str(expected).strip().lower()
    if op in ("!=", "ne", "not_equals", "<>"):
        return not _compare_values(actual, "==", expected)
    if op in (">", "gt", ">=", "gte", "<", "lt", "<=", "lte"):
        try:
            a_f = float(actual)
            e_f = float(expected)
        except (TypeError, ValueError):
            return False
        if op in (">", "gt"):
            return a_f > e_f
        if op in (">=", "gte"):
            return a_f >= e_f
        if op in ("<", "lt"):
            return a_f < e_f
        return a_f <= e_f
    if op == "in":
        items = (
            [str(x).strip().lower() for x in expected]
            if isinstance(expected, (list, tuple, set))
            else [s.strip().lower() for s in str(expected).split(",") if s.strip()]
        )
        return str(actual).strip().lower() in items
    if op == "contains":
        return str(expected).strip().lower() in str(actual).strip().lower()
    return False


class ConditionEvaluator:
    """Evaluates recursive ConditionSpec boolean AST trees (AND, OR, NOT, XOR & leaf specifications)."""

    @classmethod
    def evaluate(cls, spec: Optional[ConditionSpec], ctx: EvaluationContext) -> bool:
        if spec is None:
            return True

        ctype = spec.type
        if ctype == "and":
            return all(cls.evaluate(child, ctx) for child in spec.children) if spec.children else True
        if ctype == "or":
            return any(cls.evaluate(child, ctx) for child in spec.children) if spec.children else True
        if ctype == "not":
            if not spec.children:
                return True
            return not all(cls.evaluate(child, ctx) for child in spec.children)
        if ctype == "xor":
            if not spec.children:
                return True
            true_count = sum(1 for child in spec.children if cls.evaluate(child, ctx))
            return (true_count % 2) == 1

        if ctype == "entity_state":
            return cls._eval_entity_state(spec.params, ctx)
        if ctype == "time_window":
            return cls._eval_time_window(spec.params, ctx)
        if ctype == "zone_occupancy":
            return cls._eval_zone_occupancy(spec.params, ctx)
        if ctype == "track_kinematics":
            return cls._eval_track_kinematics(spec.params, ctx)

        return True

    @staticmethod
    def _eval_entity_state(params: dict[str, Any], ctx: EvaluationContext) -> bool:
        entity_id = str(params.get("entity_id") or "").strip()
        if not entity_id:
            return True
        snap = ctx.resolve_entity(entity_id)
        if snap is None:
            return False

        attr_name = str(params.get("attribute") or "").strip()
        actual_val = snap.attributes.get(attr_name) if attr_name else snap.state
        operator = str(params.get("operator") or "==")
        expected_val = params.get("value", params.get("state", "on"))
        return _compare_values(actual_val, operator, expected_val)

    @staticmethod
    def _eval_time_window(params: dict[str, Any], ctx: EvaluationContext) -> bool:
        local_dt = datetime.fromtimestamp(ctx.now_ts).astimezone()

        days = params.get("days_of_week")
        if isinstance(days, list) and days:
            allowed_days = {int(d) for d in days if str(d).isdigit()}
            if allowed_days and local_dt.weekday() not in allowed_days:
                return False

        sun_req = str(params.get("sun_state") or "any").strip().lower()
        if sun_req in ("daylight", "above_horizon", "night", "below_horizon"):
            sunrise_ts, sunset_ts = ctx.astronomical_clock.get_sunrise_sunset_unix(ctx.now_ts)
            sr_off = float(params.get("sunrise_offset_minutes") or 0.0) * 60.0
            ss_off = float(params.get("sunset_offset_minutes") or 0.0) * 60.0
            eff_daylight = (sunrise_ts + sr_off) <= ctx.now_ts <= (sunset_ts + ss_off)
            if sun_req in ("daylight", "above_horizon") and not eff_daylight:
                return False
            if sun_req in ("night", "below_horizon") and eff_daylight:
                return False

        after_str = str(params.get("after_hhmm") or params.get("after") or "").strip()
        before_str = str(params.get("before_hhmm") or params.get("before") or "").strip()
        if after_str or before_str:
            now_min = local_dt.hour * 60 + local_dt.minute
            after_min = ConditionEvaluator._parse_hhmm_minutes(after_str, default_min=0)
            before_min = ConditionEvaluator._parse_hhmm_minutes(before_str, default_min=24 * 60)
            if after_min <= before_min:
                if not (after_min <= now_min <= before_min):
                    return False
            else:
                # Overnight window (e.g. 22:00 -> 06:30)
                if not (now_min >= after_min or now_min <= before_min):
                    return False

        return True

    @staticmethod
    def _parse_hhmm_minutes(raw: str, default_min: int = 0) -> int:
        if not raw or ":" not in raw:
            return default_min
        parts = raw.split(":")
        try:
            return max(0, min(24 * 60, int(parts[0]) * 60 + int(parts[1])))
        except ValueError:
            return default_min

    @staticmethod
    def _eval_zone_occupancy(params: dict[str, Any], ctx: EvaluationContext) -> bool:
        zone_id = str(params.get("zone_id") or "").strip()
        if not zone_id:
            return True

        tracks_in_zone = ctx.kinematics_buffer.get_tracks_in_zone(zone_id)
        raw_filter = params.get("subject_filter")
        subj_spec = (
            SubjectFilterSpec.model_validate(raw_filter)
            if isinstance(raw_filter, dict)
            else SubjectFilterSpec()
        )

        matching_count = sum(
            1
            for tr in tracks_in_zone
            if SubjectFilterEvaluator.matches(
                tr,
                subj_spec,
                known_identities_lower=ctx.known_identities_lower,
                whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            )
        )
        operator = str(params.get("operator") or ">=")
        expected_count = int(params.get("count") if params.get("count") is not None else 1)
        return _compare_values(matching_count, operator, expected_count)

    @staticmethod
    def _eval_track_kinematics(params: dict[str, Any], ctx: EvaluationContext) -> bool:
        tr = ctx.trigger_event.track if ctx.trigger_event is not None else None
        if tr is None:
            return False

        window_s = max(0.5, float(params.get("window_s") or 2.0))
        metrics = ctx.kinematics_buffer.compute_window_kinematics(
            tr.track_id,
            window_s=window_s,
            now_ts=ctx.now_ts,
        )
        if metrics is None:
            return False

        if params.get("min_speed_mps") is not None:
            if metrics.mean_speed_mps < float(params["min_speed_mps"]):
                return False
        if params.get("max_speed_mps") is not None:
            if metrics.mean_speed_mps > float(params["max_speed_mps"]):
                return False
        if params.get("target_azimuth_deg") is not None and str(params.get("target_azimuth_deg")) != "":
            if metrics.mean_azimuth_deg is None:
                return False
            tol = float(params.get("azimuth_tolerance_deg") or 35.0)
            if angular_difference_deg(metrics.mean_azimuth_deg, float(params["target_azimuth_deg"])) > tol:
                return False
        return True
