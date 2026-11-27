from __future__ import annotations

import asyncio
from collections import deque
import copy
from dataclasses import dataclass
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Coroutine, Optional

from spatial_server.config import SpatialServerConfig, _normalize_ha_url
from spatial_server.domain.models import TrackedEntity3D
from spatial_server.events.narrator import build_scene_sentence_it, build_scene_title_it
from spatial_server.persistence.interfaces import ITrackRepository
from .actions import ActionRegistry, action_tree_contains_delay
from .astronomy import AstronomicalClock
from .correlator import CorrelatedRuleMatch, RuleSequenceCoordinator
from .evaluators import (
    ConditionEvaluator,
    EntityStateSnapshot,
    EvaluationContext,
    SubjectFilterEvaluator,
    TriggerActivationEvent,
    TriggerRegistry,
)
from .kinematics import TrackKinematicHistoryBuffer, TrackStepEvents
from .models import (
    ActionSpec,
    AutomationExecutionLog,
    AutomationRuleDefinition,
    DiagnosticEventLiteral,
    RuleDiagnosticEntry,
    SpatialZoneDefinition,
    TriggerSpec,
    VirtualEntityDefinition,
)

logger = logging.getLogger("spatial_server.automations")


@dataclass
class _DeferredBiometricCheck:
    """Queued spatial/perimeter event waiting briefly for biometric worker verdict."""

    rule_id: str
    stage_key: str  # "main" or f"pre:{stage_id}"
    trigger_spec: TriggerSpec
    activation: TriggerActivationEvent
    track_id: int
    created_at: float
    expires_at: float
    is_positive: bool = False


class DeferredBiometricManager:
    """
    Manages deduplicated late-biometric waiting checks (`biometric_grace_s`) anchored
    to the trigger activation timestamp rather than track creation time.
    """

    def __init__(self) -> None:
        self._checks: list[_DeferredBiometricCheck] = []

    def has_key(self, rule_id: str, stage_key: str, trigger_id: str, track_id: int) -> bool:
        return any(
            c.rule_id == rule_id
            and c.stage_key == stage_key
            and c.trigger_spec.trigger_id == trigger_id
            and c.track_id == track_id
            for c in self._checks
        )

    def clear_rule(self, rule_id: str) -> None:
        self._checks = [c for c in self._checks if c.rule_id != rule_id]

    def enqueue_positive_candidates(
        self,
        rule: AutomationRuleDefinition,
        stage_key: str,
        trig_spec: TriggerSpec,
        evaluator: Any,
        ctx: EvaluationContext,
        rt_state: dict[str, Any],
        *,
        scene_event_id: Optional[str],
    ) -> list[_DeferredBiometricCheck]:
        if trig_spec.subject_filter.biometric_grace_s <= 0.0:
            return []
        if not SubjectFilterEvaluator.has_positive_biometric_filter(trig_spec.subject_filter):
            return []

        relaxed_filter = trig_spec.subject_filter.model_copy(
            update={"face_mode": "any", "plate_mode": "any"}
        )
        relaxed_spec = trig_spec.model_copy(update={"subject_filter": relaxed_filter})
        # Deep copy runtime_state so shadow evaluation never mutates dwell/latch sets!
        shadow_rt = copy.deepcopy(rt_state)
        candidate_events = evaluator.evaluate(rule.rule_id, relaxed_spec, ctx, shadow_rt)

        added: list[_DeferredBiometricCheck] = []
        for cand in candidate_events:
            if cand.track is None:
                continue
            tid = cand.track.track_id
            if SubjectFilterEvaluator.matches(
                cand.track,
                trig_spec.subject_filter,
                known_identities_lower=ctx.known_identities_lower,
                whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            ):
                continue
            if not SubjectFilterEvaluator.should_defer_for_biometrics(
                cand.track,
                trig_spec.subject_filter,
                ctx.now_ts,
                ctx.now_ts,
                for_positive_candidate=True,
            ):
                continue
            if self.has_key(rule.rule_id, stage_key, trig_spec.trigger_id, tid):
                continue

            kin = cand.kinematics or ctx.kinematics_buffer.compute_window_kinematics(
                tid,
                window_s=10.0,
                now_ts=ctx.now_ts,
            )
            enriched_cand = TriggerActivationEvent(
                trigger_id=cand.trigger_id,
                trigger_type=cand.trigger_type,
                timestamp=cand.timestamp,
                summary=cand.summary,
                track=cand.track,
                zone_id=cand.zone_id,
                from_zone_id=cand.from_zone_id,
                to_zone_id=cand.to_zone_id,
                entity_id=cand.entity_id,
                old_state=cand.old_state,
                new_state=cand.new_state,
                kinematics=kin,
                scene_event_id=cand.scene_event_id or scene_event_id,
                extra=dict(cand.extra),
            )
            item = _DeferredBiometricCheck(
                rule_id=rule.rule_id,
                stage_key=stage_key,
                trigger_spec=trig_spec,
                activation=enriched_cand,
                track_id=tid,
                created_at=ctx.now_ts,
                expires_at=ctx.now_ts + trig_spec.subject_filter.biometric_grace_s,
                is_positive=True,
            )
            self._checks.append(item)
            added.append(item)
        return added

    def enqueue_negative_defer(
        self,
        rule: AutomationRuleDefinition,
        stage_key: str,
        trig_spec: TriggerSpec,
        act_ev: TriggerActivationEvent,
        ctx: EvaluationContext,
    ) -> Optional[_DeferredBiometricCheck]:
        if act_ev.track is None:
            return None
        if not SubjectFilterEvaluator.should_defer_for_biometrics(
            act_ev.track,
            trig_spec.subject_filter,
            ctx.now_ts,
            ctx.now_ts,
            for_positive_candidate=False,
        ):
            return None
        tid = act_ev.track.track_id
        if self.has_key(rule.rule_id, stage_key, trig_spec.trigger_id, tid):
            return None
        item = _DeferredBiometricCheck(
            rule_id=rule.rule_id,
            stage_key=stage_key,
            trigger_spec=trig_spec,
            activation=act_ev,
            track_id=tid,
            created_at=ctx.now_ts,
            expires_at=ctx.now_ts + trig_spec.subject_filter.biometric_grace_s,
            is_positive=False,
        )
        self._checks.append(item)
        return item

    def pop_ready(
        self,
        rules: dict[str, AutomationRuleDefinition],
        ctx: EvaluationContext,
    ) -> list[tuple[AutomationRuleDefinition, str, TriggerSpec, TriggerActivationEvent]]:
        if not self._checks:
            return []

        active_by_id = {t.track_id: t for t in ctx.active_tracks}
        remaining: list[_DeferredBiometricCheck] = []
        ready: list[tuple[AutomationRuleDefinition, str, TriggerSpec, TriggerActivationEvent]] = []

        for item in self._checks:
            rule = rules.get(item.rule_id)
            if rule is None or not rule.enabled:
                continue

            tr = (
                active_by_id.get(item.track_id)
                or ctx.kinematics_buffer.get_active_track(item.track_id)
                or item.activation.track
            )
            if tr is None:
                continue

            is_expired = ctx.now_ts >= item.expires_at
            matched = SubjectFilterEvaluator.matches(
                tr,
                item.trigger_spec.subject_filter,
                known_identities_lower=ctx.known_identities_lower,
                whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            )

            if item.is_positive:
                if matched:
                    updated_act = TriggerActivationEvent(
                        trigger_id=item.activation.trigger_id,
                        trigger_type=item.activation.trigger_type,
                        timestamp=ctx.now_ts,
                        summary=item.activation.summary,
                        track=tr,
                        zone_id=item.activation.zone_id,
                        from_zone_id=item.activation.from_zone_id,
                        to_zone_id=item.activation.to_zone_id,
                        kinematics=item.activation.kinematics,
                        scene_event_id=item.activation.scene_event_id,
                        extra={**item.activation.extra, "late_biometric_bound": True},
                    )
                    ready.append((rule, item.stage_key, item.trigger_spec, updated_act))
                elif tr.biometric_locked or is_expired:
                    # Locked to non-matching identity/plate or grace window elapsed -> drop
                    continue
                else:
                    remaining.append(item)
            else:
                is_resolved = (
                    tr.biometric_locked
                    or tr.biometric_status in ("locked", "unknown")
                    or bool(tr.identity)
                    or bool(tr.plate)
                )
                if not is_resolved and not is_expired:
                    remaining.append(item)
                    continue
                if matched:
                    updated_act = TriggerActivationEvent(
                        trigger_id=item.activation.trigger_id,
                        trigger_type=item.activation.trigger_type,
                        timestamp=ctx.now_ts,
                        summary=item.activation.summary,
                        track=tr,
                        zone_id=item.activation.zone_id,
                        from_zone_id=item.activation.from_zone_id,
                        to_zone_id=item.activation.to_zone_id,
                        kinematics=item.activation.kinematics,
                        scene_event_id=item.activation.scene_event_id,
                        extra={**item.activation.extra, "late_biometric_bound": True},
                    )
                    ready.append((rule, item.stage_key, item.trigger_spec, updated_act))

        self._checks = remaining
        return ready


class AutomationEngineService:
    """
    Central OOP reactive automation orchestrator running inside spatial_server:
    - Evaluates 2.5D spatial zones, oriented perimeter crossings, Area A -> Area B transitions,
      sliding window mean velocity & direction vectors, astronomical sunrise/sunset, and
      internal (`sh3d.*`) or Home Assistant entity changes.
    - Supports late biometric binding (grace window when face/ALPR is pending).
    - Executes procedural action pipelines (IF/THEN/ELSE, Delay, Set Virtual Entity,
      Call Home Assistant Service, 3D UI Alert, Webhook).
    """

    def __init__(
        self,
        config: SpatialServerConfig,
        repository: ITrackRepository,
        *,
        broadcast_callback: Optional[Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = None,
        known_identities_provider: Optional[Callable[[], set[str]]] = None,
        whitelisted_plates_provider: Optional[Callable[[], set[str]]] = None,
        ha_bridge: Any = None,
        mqtt_bridge: Any = None,
        scene_event_manager: Any = None,
        signed_media_service: Any = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.broadcast_callback = broadcast_callback
        self._known_identities_provider = known_identities_provider
        self._whitelisted_plates_provider = whitelisted_plates_provider
        self.ha_bridge = ha_bridge
        self.mqtt_bridge = mqtt_bridge
        self.scene_event_manager = scene_event_manager
        self.signed_media_service = signed_media_service

        lat = float(os.getenv("HOME_LATITUDE", "45.55"))
        lon = float(os.getenv("HOME_LONGITUDE", "11.55"))
        self.astronomical_clock = AstronomicalClock(latitude_deg=lat, longitude_deg=lon)
        self.kinematics_buffer = TrackKinematicHistoryBuffer(max_history_s=120.0)

        self.zones: dict[str, SpatialZoneDefinition] = {}
        self.virtual_entities: dict[str, VirtualEntityDefinition] = {}
        self.rules: dict[str, AutomationRuleDefinition] = {}
        self.ha_states: dict[str, EntityStateSnapshot] = {}
        self._telemetry_states: dict[str, EntityStateSnapshot] = {}

        # Per-(rule_id, trigger_id) stateful evaluator memory
        self._trigger_runtime_state: dict[tuple[str, str], dict[str, Any]] = {}
        self.sequence_coordinator = RuleSequenceCoordinator()
        self._deferred_biometrics = DeferredBiometricManager()
        self._diagnostics: dict[str, deque[RuleDiagnosticEntry]] = {}
        self._running_rule_tasks: dict[str, set[asyncio.Task[None]]] = {}
        self._queued_rule_runs: dict[str, deque[tuple[AutomationRuleDefinition, TriggerActivationEvent, EvaluationContext]]] = {}
        self._active_display_tasks: set[asyncio.Task[None]] = set()
        self._pending_notif_updates: dict[str, dict[str, Any]] = {}
        self._track_first_seen: dict[int, float] = {}
        self._pending_entity_changes: list[tuple[str, Optional[str], str]] = []
        self._last_pretrigger_broadcast_mono: float = 0.0
        self._clock_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()

        self.reload_from_repository()

    def reload_from_repository(self) -> None:
        """Load persisted spatial zones, virtual entities, and automation rules from SQLite."""
        self.zones.clear()
        for z_dict in self.repository.list_spatial_zones():
            try:
                z = SpatialZoneDefinition.model_validate(z_dict)
                self.zones[z.zone_id] = z
            except Exception as exc:
                logger.warning("Skipping invalid spatial zone from DB: %s", exc)

        self.virtual_entities.clear()
        for e_dict in self.repository.list_virtual_entities():
            try:
                ve = VirtualEntityDefinition.model_validate(e_dict)
                self.virtual_entities[ve.entity_id] = ve
            except Exception as exc:
                logger.warning("Skipping invalid virtual entity from DB: %s", exc)

        self.rules.clear()
        for r_dict in self.repository.list_automation_rules():
            try:
                rule = AutomationRuleDefinition.model_validate(r_dict)
                self.rules[rule.rule_id] = rule
            except Exception as exc:
                logger.warning("Skipping invalid automation rule from DB: %s", exc)

    async def start(self) -> None:
        if self._clock_task is None or self._clock_task.done():
            self._clock_task = asyncio.create_task(self._periodic_clock_loop())

    async def stop(self) -> None:
        if self._clock_task is not None:
            self._clock_task.cancel()
            try:
                await self._clock_task
            except asyncio.CancelledError:
                pass
            self._clock_task = None
        for task_set in list(self._running_rule_tasks.values()):
            for t in list(task_set):
                t.cancel()
        self._running_rule_tasks.clear()
        for t in list(self._active_display_tasks):
            t.cancel()
        self._active_display_tasks.clear()

    async def _periodic_clock_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                await self.evaluate_periodic_tick(time.time())
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Automation periodic clock tick warning: %s", exc)

    def _get_known_identities_lower(self) -> set[str]:
        if self._known_identities_provider is not None:
            try:
                return {s.strip().lower() for s in self._known_identities_provider() if s}
            except Exception:
                pass
        return set()

    def _get_whitelisted_plates_upper(self) -> set[str]:
        if self._whitelisted_plates_provider is not None:
            try:
                return {re.sub(r"[^A-Z0-9]", "", s.upper()) for s in self._whitelisted_plates_provider() if s}
            except Exception:
                pass
        return set()

    # ========================================================================
    # CRUD & STATE MUTATION API
    # ========================================================================

    async def upsert_zone(self, zone: SpatialZoneDefinition) -> SpatialZoneDefinition:
        zone.updated_at = round(time.time(), 3)
        self.zones[zone.zone_id] = zone
        self.repository.upsert_spatial_zone(zone.model_dump())
        await self._broadcast({"type": "automation_zones_updated", "zones": [z.model_dump() for z in self.list_zones()]})
        return zone

    async def delete_zone(self, zone_id: str) -> bool:
        removed = self.zones.pop(zone_id, None) is not None
        db_removed = self.repository.delete_spatial_zone(zone_id)
        if removed or db_removed:
            await self._broadcast({"type": "automation_zones_updated", "zones": [z.model_dump() for z in self.list_zones()]})
        return removed or db_removed

    def list_zones(self) -> list[SpatialZoneDefinition]:
        return sorted(self.zones.values(), key=lambda z: z.name.lower())

    async def upsert_virtual_entity(
        self,
        entity: VirtualEntityDefinition,
        *,
        trigger_automations: bool = True,
    ) -> VirtualEntityDefinition:
        now_ts = round(time.time(), 3)
        prev = self.virtual_entities.get(entity.entity_id)
        old_state = prev.state if prev is not None else None
        if prev is None or str(prev.state) != str(entity.state):
            entity.last_changed = now_ts
        else:
            entity.last_changed = prev.last_changed
        entity.updated_at = now_ts

        self.virtual_entities[entity.entity_id] = entity
        self.repository.upsert_virtual_entity(entity.model_dump())

        await self._broadcast(
            {
                "type": "virtual_entity_updated",
                "entity": entity.model_dump(),
                "old_state": old_state,
            }
        )

        if trigger_automations and old_state is not None and str(old_state) != str(entity.state):
            await self.notify_entity_state_changed(entity.entity_id, str(old_state), str(entity.state), now_ts)

        if entity.entity_id == "sh3d.allarme" and self.mqtt_bridge is not None:
            try:
                await self.mqtt_bridge.publish_alarm_state(entity.state, entity.options or None)
            except Exception:
                pass

        return entity

    async def set_virtual_entity_state(
        self,
        entity_id: str,
        new_state: Optional[str] = None,
        *,
        operation: str = "set",
        attributes_patch: Optional[dict[str, Any]] = None,
        trigger_automations: bool = True,
    ) -> VirtualEntityDefinition:
        norm_id = VirtualEntityDefinition.normalize_entity_id(entity_id)
        existing = self.virtual_entities.get(norm_id)
        now_ts = round(time.time(), 3)
        if existing is None:
            existing = VirtualEntityDefinition(
                entity_id=norm_id,
                name=norm_id.split(".", 1)[1].replace("_", " ").title(),
                domain="switch",
                state="off",
                last_changed=now_ts,
                updated_at=now_ts,
            )

        op = (operation or "set").strip().lower()
        target_state = str(new_state if new_state is not None else existing.state)
        if op == "turn_on":
            target_state = "on"
        elif op == "turn_off":
            target_state = "off"
        elif op == "toggle":
            target_state = "off" if str(existing.state).strip().lower() == "on" else "on"
        elif op == "increment":
            try:
                step = float(new_state) if new_state is not None else 1.0
                target_state = str(round(float(existing.state) + step, 3))
            except ValueError:
                target_state = "1"

        merged_attrs = dict(existing.attributes)
        if isinstance(attributes_patch, dict):
            merged_attrs.update(attributes_patch)

        updated = existing.model_copy(
            update={
                "state": target_state,
                "attributes": merged_attrs,
            }
        )
        return await self.upsert_virtual_entity(updated, trigger_automations=trigger_automations)

    async def delete_virtual_entity(self, entity_id: str) -> bool:
        norm_id = VirtualEntityDefinition.normalize_entity_id(entity_id)
        removed = self.virtual_entities.pop(norm_id, None) is not None
        db_removed = self.repository.delete_virtual_entity(norm_id)
        if removed or db_removed:
            await self._broadcast(
                {
                    "type": "virtual_entities_list",
                    "entities": [e.model_dump() for e in self.list_virtual_entities()],
                }
            )
        return removed or db_removed

    def list_virtual_entities(self) -> list[VirtualEntityDefinition]:
        return sorted(self.virtual_entities.values(), key=lambda e: e.entity_id)

    async def upsert_rule(self, rule: AutomationRuleDefinition) -> AutomationRuleDefinition:
        rule.updated_at = round(time.time(), 3)
        prev = self.rules.get(rule.rule_id)
        if prev is not None:
            if rule.last_triggered_at is None:
                rule.last_triggered_at = prev.last_triggered_at
            if rule.trigger_count == 0 and prev.trigger_count > 0:
                rule.trigger_count = prev.trigger_count

        self.rules[rule.rule_id] = rule
        # Clear cached runtime state for this rule so updated parameters take effect cleanly
        for key in [k for k in self._trigger_runtime_state if k[0] == rule.rule_id]:
            self._trigger_runtime_state.pop(key, None)
        self._deferred_biometrics.clear_rule(rule.rule_id)
        had_armed = self.sequence_coordinator.reset_rule(rule.rule_id)

        self.repository.upsert_automation_rule(rule.model_dump())
        await self._broadcast({"type": "automation_rules_updated", "rules": [r.model_dump() for r in self.list_rules()]})
        if had_armed:
            await self._broadcast_pretrigger_state(time.time(), force=True)
        return rule

    async def delete_rule(self, rule_id: str) -> bool:
        removed = self.rules.pop(rule_id, None) is not None
        for key in [k for k in self._trigger_runtime_state if k[0] == rule_id]:
            self._trigger_runtime_state.pop(key, None)
        self._deferred_biometrics.clear_rule(rule_id)
        had_armed = self.sequence_coordinator.reset_rule(rule_id)
        self._diagnostics.pop(rule_id, None)
        self._queued_rule_runs.pop(rule_id, None)
        db_removed = self.repository.delete_automation_rule(rule_id)
        if removed or db_removed:
            await self._broadcast({"type": "automation_rules_updated", "rules": [r.model_dump() for r in self.list_rules()]})
            if had_armed:
                await self._broadcast_pretrigger_state(time.time(), force=True)
        return removed or db_removed

    def list_rules(self) -> list[AutomationRuleDefinition]:
        return sorted(self.rules.values(), key=lambda r: r.name.lower())

    def get_armed_states(self, now_ts: Optional[float] = None) -> list[dict[str, Any]]:
        ts = float(now_ts if now_ts is not None else time.time())
        self.sequence_coordinator.prune_expired(ts)
        return [s.model_dump() for s in self.sequence_coordinator.get_armed_snapshots(self.rules, ts)]

    def get_rule_diagnostics(self, rule_id: str, limit: int = 30) -> list[dict[str, Any]]:
        buf = self._diagnostics.get(rule_id)
        if not buf:
            return []
        items = list(buf)[-max(1, min(limit, 100)) :]
        items.reverse()
        return [item.model_dump() for item in items]

    def _record_diagnostic(
        self,
        rule_id: str,
        event: DiagnosticEventLiteral,
        summary: str,
        *,
        timestamp: Optional[float] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        buf = self._diagnostics.setdefault(rule_id, deque(maxlen=40))
        buf.append(
            RuleDiagnosticEntry(
                timestamp=round(float(timestamp if timestamp is not None else time.time()), 3),
                rule_id=rule_id,
                event=event,
                summary=summary,
                details=dict(details or {}),
            )
        )

    async def _broadcast_pretrigger_state(self, now_ts: float, *, force: bool = False) -> None:
        now_mono = time.monotonic()
        if not force and (now_mono - self._last_pretrigger_broadcast_mono) < 2.0:
            return
        self._last_pretrigger_broadcast_mono = now_mono
        snaps = self.sequence_coordinator.get_armed_snapshots(self.rules, now_ts)
        await self._broadcast(
            {
                "type": "automation_pretrigger_updated",
                "armed_states": [s.model_dump() for s in snaps],
                "timestamp": round(now_ts, 3),
            }
        )

    async def sync_ha_states_batch(
        self,
        states: dict[str, dict[str, Any]],
        *,
        trigger_on_diff: bool = True,
    ) -> int:
        """
        Update mirror of Home Assistant entity states (pushed from frontend or HA bridge).
        Emits entity_state_change triggers when state transitions occur.
        """
        now_ts = time.time()
        changes: list[tuple[str, Optional[str], str]] = []

        for eid, payload in states.items():
            if not eid or not isinstance(payload, dict):
                continue
            new_st = str(payload.get("state") if payload.get("state") is not None else "unknown")
            attrs = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
            prev = self.ha_states.get(eid)
            old_st = prev.state if prev is not None else None
            changed = prev is None or old_st != new_st
            self.ha_states[eid] = EntityStateSnapshot(
                entity_id=eid,
                state=new_st,
                attributes=attrs,
                last_changed=now_ts if changed else (prev.last_changed if prev else now_ts),
                source="ha",
            )
            if trigger_on_diff and prev is not None and old_st != new_st:
                changes.append((eid, old_st, new_st))

        if changes:
            for eid, old_st, new_st in changes:
                await self.notify_entity_state_changed(eid, old_st, new_st, now_ts)
        return len(changes)

    async def notify_entity_state_changed(
        self,
        entity_id: str,
        old_state: Optional[str],
        new_state: str,
        now_ts: Optional[float] = None,
    ) -> list[AutomationExecutionLog]:
        ts = float(now_ts if now_ts is not None else time.time())
        ctx = self._build_evaluation_context(
            ts,
            active_tracks=[],
            step_events_by_track={},
            entity_changes=[(entity_id, old_state, new_state)],
        )
        return await self._evaluate_all_rules(ctx)

    # ========================================================================
    # CORE REACTIVE EVALUATION HOOKS (3D TRACKS, BIOMETRICS, CLOCK)
    # ========================================================================

    async def on_tracks_updated(
        self,
        active_tracks: list[TrackedEntity3D],
        now_ts: float,
    ) -> list[AutomationExecutionLog]:
        """
        Hook called at 10-15 Hz right after Kalman3DMultiTracker updates active 3D tracks.
        Computes polygon entries/exits/dwells, perimeter crossings, Area A -> Area B transitions,
        and sliding-window velocity/direction vectors.
        """
        for tr in active_tracks:
            self._track_first_seen.setdefault(tr.track_id, now_ts)

        step_events = self.kinematics_buffer.update_tracks(active_tracks, self.zones, now_ts)
        step_by_tid = {ev.track.track_id: ev for ev in step_events}

        ctx = self._build_evaluation_context(
            now_ts,
            active_tracks=active_tracks,
            step_events_by_track=step_by_tid,
        )
        logs = await self._evaluate_all_rules(ctx)
        deferred_logs = await self._check_deferred_biometric_triggers(ctx)
        return logs + deferred_logs

    async def on_biometric_update(
        self,
        update_dict: dict[str, Any],
        active_tracks: list[TrackedEntity3D],
        now_ts: float,
    ) -> list[AutomationExecutionLog]:
        """
        Hook called when TrackBiometricConsensusManager or Admin HITL resolves a face or plate.
        Evaluates both direct `biometric_detection` triggers and any deferred spatial triggers
        waiting on `biometric_grace_s`.
        """
        for tr in active_tracks:
            self.kinematics_buffer._latest_tracks[tr.track_id] = tr

        ctx = self._build_evaluation_context(
            now_ts,
            active_tracks=active_tracks,
            step_events_by_track={},
            biometric_updates=[update_dict],
        )
        logs = await self._evaluate_all_rules(ctx)
        deferred_logs = await self._check_deferred_biometric_triggers(ctx)
        await self._process_pending_notif_updates(update_dict, active_tracks, now_ts)
        return logs + deferred_logs

    async def evaluate_periodic_tick(self, now_ts: float) -> list[AutomationExecutionLog]:
        """Hook called every 1.0s to evaluate time schedules, sunrise/sunset, and hold timers."""
        ctx = self._build_evaluation_context(
            now_ts,
            active_tracks=list(self.kinematics_buffer._latest_tracks.values()),
            step_events_by_track={},
        )
        logs = await self._evaluate_all_rules(ctx)
        deferred_logs = await self._check_deferred_biometric_triggers(ctx)
        return logs + deferred_logs

    async def on_scene_event_lifecycle(
        self,
        event_kind: str,
        scene_event: Any,
        now_ts: Optional[float] = None,
    ) -> list[AutomationExecutionLog]:
        """Hook invoked when SceneEventManager starts, escalates, or closes an episode."""
        has_scene_rule = any(
            r.enabled
            and (
                any(t.enabled and t.type == "scene_event" for t in r.triggers)
                or any(
                    stg.enabled and any(t.enabled and t.type == "scene_event" for t in stg.triggers)
                    for stg in r.pre_triggers
                )
            )
            for r in self.rules.values()
        )
        if not has_scene_rule:
            return []

        ts = float(now_ts if now_ts is not None else time.time())
        ctx = self._build_evaluation_context(
            ts,
            active_tracks=list(self.kinematics_buffer._latest_tracks.values()),
            step_events_by_track={},
            scene_event=scene_event,
            scene_lifecycle_events=[(event_kind, scene_event)],
        )
        return await self._evaluate_all_rules(ctx)

    def _build_evaluation_context(
        self,
        now_ts: float,
        *,
        active_tracks: list[TrackedEntity3D],
        step_events_by_track: dict[int, TrackStepEvents],
        entity_changes: Optional[list[tuple[str, Optional[str], str]]] = None,
        biometric_updates: Optional[list[dict[str, Any]]] = None,
        scene_event: Any = None,
        scene_lifecycle_events: Optional[list[tuple[str, Any]]] = None,
    ) -> EvaluationContext:
        eff_scene_ev = scene_event
        if eff_scene_ev is None and self.scene_event_manager is not None:
            try:
                eff_scene_ev = self.scene_event_manager.get_active_event()
            except Exception:
                eff_scene_ev = None
        return EvaluationContext(
            now_ts=now_ts,
            kinematics_buffer=self.kinematics_buffer,
            zones=self.zones,
            virtual_entities=self.virtual_entities,
            ha_states={**self._telemetry_states, **self.ha_states},
            astronomical_clock=self.astronomical_clock,
            known_identities_lower=self._get_known_identities_lower(),
            whitelisted_plates_upper=self._get_whitelisted_plates_upper(),
            active_tracks=active_tracks,
            step_events_by_track=step_events_by_track,
            entity_changes=list(entity_changes or []),
            biometric_updates=list(biometric_updates or []),
            scene_event=eff_scene_ev,
            scene_lifecycle_events=list(scene_lifecycle_events or []),
        )

    def sync_telemetry_states(self, entities: list[dict[str, Any]]) -> None:
        """Mirror server telemetry sensor entities into in-memory evaluation state without touching SQLite."""
        now_ts = time.time()
        for ent in entities:
            eid = str(ent.get("entity_id") or "").strip()
            if not eid:
                continue
            state_val = ent.get("state")
            state_str = "unavailable" if state_val is None else str(state_val)
            prev = self._telemetry_states.get(eid)
            changed_at = prev.last_changed if (prev is not None and prev.state == state_str) else float(ent.get("updated_at") or now_ts)
            self._telemetry_states[eid] = EntityStateSnapshot(
                entity_id=eid,
                state=state_str,
                attributes=dict(ent.get("attributes") or {}),
                last_changed=changed_at,
                source="telemetry",
            )

    def _active_scene_event_id(self, ctx: EvaluationContext) -> Optional[str]:
        if ctx.scene_event is not None:
            return getattr(ctx.scene_event, "event_id", None)
        return None

    def _evaluate_trigger_list(
        self,
        rule: AutomationRuleDefinition,
        stage_key: str,
        triggers: list[TriggerSpec],
        ctx: EvaluationContext,
        *,
        scene_event_id: Optional[str],
    ) -> dict[str, list[TriggerActivationEvent]]:
        activations_by_id: dict[str, list[TriggerActivationEvent]] = {}
        for trig_spec in triggers:
            if not trig_spec.enabled:
                continue
            evaluator = TriggerRegistry.get(trig_spec.type)
            if evaluator is None:
                continue

            rt_key = (rule.rule_id, f"{stage_key}:{trig_spec.trigger_id}")
            rt_state = self._trigger_runtime_state.setdefault(rt_key, {})

            if ctx.step_events_by_track and trig_spec.subject_filter.biometric_grace_s > 0.0:
                added_pos = self._deferred_biometrics.enqueue_positive_candidates(
                    rule,
                    stage_key,
                    trig_spec,
                    evaluator,
                    ctx,
                    rt_state,
                    scene_event_id=scene_event_id,
                )
                for item in added_pos:
                    self._record_diagnostic(
                        rule.rule_id,
                        "deferred_biometrics",
                        f"Attesa biometria ({trig_spec.subject_filter.biometric_grace_s:.1f}s) per traccia #{item.track_id}",
                        timestamp=ctx.now_ts,
                    )

            raw_activations = evaluator.evaluate(rule.rule_id, trig_spec, ctx, rt_state)
            ready_list: list[TriggerActivationEvent] = []
            for act_ev in raw_activations:
                if act_ev.track is not None and self._deferred_biometrics.enqueue_negative_defer(
                    rule,
                    stage_key,
                    trig_spec,
                    act_ev,
                    ctx,
                ):
                    self._record_diagnostic(
                        rule.rule_id,
                        "deferred_biometrics",
                        f"Grazia biometria ({trig_spec.subject_filter.biometric_grace_s:.1f}s) per traccia #{act_ev.track.track_id}",
                        timestamp=ctx.now_ts,
                    )
                    continue
                if act_ev.scene_event_id is None and scene_event_id is not None:
                    act_ev = TriggerActivationEvent(
                        trigger_id=act_ev.trigger_id,
                        trigger_type=act_ev.trigger_type,
                        timestamp=act_ev.timestamp,
                        summary=act_ev.summary,
                        track=act_ev.track,
                        zone_id=act_ev.zone_id,
                        from_zone_id=act_ev.from_zone_id,
                        to_zone_id=act_ev.to_zone_id,
                        entity_id=act_ev.entity_id,
                        old_state=act_ev.old_state,
                        new_state=act_ev.new_state,
                        kinematics=act_ev.kinematics,
                        scene_event_id=scene_event_id,
                        extra=act_ev.extra,
                    )
                ready_list.append(act_ev)

            if ready_list:
                activations_by_id[trig_spec.trigger_id] = ready_list
        return activations_by_id

    async def _evaluate_all_rules(self, ctx: EvaluationContext) -> list[AutomationExecutionLog]:
        executed_logs: list[AutomationExecutionLog] = []
        scene_event_id = self._active_scene_event_id(ctx)

        expired_tokens = self.sequence_coordinator.prune_expired(ctx.now_ts)
        if expired_tokens:
            for exp_tok in expired_tokens:
                self._record_diagnostic(
                    exp_tok.rule_id,
                    "pre_trigger_expired",
                    f"Pre-trigger '{exp_tok.stage_name}' scaduto senza conferma",
                    timestamp=ctx.now_ts,
                    details={"stage_id": exp_tok.stage_id, "track_id": exp_tok.track_id},
                )
            await self._broadcast_pretrigger_state(ctx.now_ts, force=True)

        pre_ctx = EvaluationContext(
            now_ts=ctx.now_ts,
            kinematics_buffer=ctx.kinematics_buffer,
            zones=ctx.zones,
            virtual_entities=ctx.virtual_entities,
            ha_states=ctx.ha_states,
            astronomical_clock=ctx.astronomical_clock,
            known_identities_lower=ctx.known_identities_lower,
            whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            active_tracks=ctx.active_tracks,
            step_events_by_track=ctx.step_events_by_track,
            entity_changes=ctx.entity_changes,
            biometric_updates=ctx.biometric_updates,
            scene_event=ctx.scene_event,
            scene_lifecycle_events=ctx.scene_lifecycle_events,
            is_pre_trigger_eval=True,
        )

        for rule in list(self.rules.values()):
            if not rule.enabled:
                continue

            # Phase A: Evaluate Pre-Trigger Stages sequentially
            enabled_prev_stage: Optional[tuple[int, Any]] = None
            for stage_idx, stage in enumerate(rule.pre_triggers):
                if not stage.enabled or not any(t.enabled for t in stage.triggers):
                    continue
                stage_key = f"pre:{stage.stage_id}"
                pre_acts = self._evaluate_trigger_list(
                    rule,
                    stage_key,
                    stage.triggers,
                    pre_ctx,
                    scene_event_id=scene_event_id,
                )
                if pre_acts:
                    changes = self.sequence_coordinator.record_pre_trigger_activations(
                        rule,
                        stage_idx,
                        stage,
                        enabled_prev_stage,
                        pre_acts,
                        pre_ctx,
                        scene_event_id=scene_event_id,
                    )
                    for change_kind, tok in changes:
                        self._record_diagnostic(
                            rule.rule_id,
                            "pre_trigger_armed" if change_kind == "armed" else "pre_trigger_refreshed",
                            f"Pre-trigger '{tok.stage_name}' {'armato' if change_kind == 'armed' else 'rinnovato'} ({stage.max_wait_s:.0f}s): {tok.activation.summary}",
                            timestamp=ctx.now_ts,
                            details={"stage_id": tok.stage_id, "track_id": tok.track_id},
                        )
                    if changes:
                        has_new_arm = any(ck == "armed" for ck, _ in changes)
                        await self._broadcast_pretrigger_state(ctx.now_ts, force=has_new_arm)
                enabled_prev_stage = (stage_idx, stage)

            # Phase B: Evaluate Main Triggers & Correlate with Armed Pre-Triggers
            main_acts = self._evaluate_trigger_list(
                rule,
                "main",
                rule.triggers,
                ctx,
                scene_event_id=scene_event_id,
            )
            if not main_acts:
                continue

            matches = self.sequence_coordinator.resolve_main_activations(
                rule,
                main_acts,
                ctx,
                scene_event_id=scene_event_id,
            )
            for match in matches:
                log_entry = await self._process_correlated_match(rule, match, ctx)
                if log_entry is not None:
                    executed_logs.append(log_entry)

        return executed_logs

    async def _check_deferred_biometric_triggers(self, ctx: EvaluationContext) -> list[AutomationExecutionLog]:
        ready_items = self._deferred_biometrics.pop_ready(self.rules, ctx)
        if not ready_items:
            return []

        scene_event_id = self._active_scene_event_id(ctx)
        grouped: dict[tuple[str, str], tuple[AutomationRuleDefinition, dict[str, list[TriggerActivationEvent]]]] = {}
        for rule, stage_key, trig_spec, updated_act in ready_items:
            grp_key = (rule.rule_id, stage_key)
            if grp_key not in grouped:
                grouped[grp_key] = (rule, {})
            grouped[grp_key][1].setdefault(trig_spec.trigger_id, []).append(updated_act)

        logs: list[AutomationExecutionLog] = []
        for (rule_id, stage_key), (rule, acts_by_id) in grouped.items():
            if stage_key.startswith("pre:"):
                target_sid = stage_key[4:]
                enabled_prev_stage = None
                for idx, stg in enumerate(rule.pre_triggers):
                    if not stg.enabled or not any(t.enabled for t in stg.triggers):
                        continue
                    if stg.stage_id == target_sid:
                        changes = self.sequence_coordinator.record_pre_trigger_activations(
                            rule,
                            idx,
                            stg,
                            enabled_prev_stage,
                            acts_by_id,
                            ctx,
                            scene_event_id=scene_event_id,
                        )
                        if changes:
                            await self._broadcast_pretrigger_state(ctx.now_ts, force=True)
                        break
                    enabled_prev_stage = (idx, stg)
            else:
                matches = self.sequence_coordinator.resolve_main_activations(
                    rule,
                    acts_by_id,
                    ctx,
                    scene_event_id=scene_event_id,
                )
                for match in matches:
                    log_entry = await self._process_correlated_match(rule, match, ctx)
                    if log_entry is not None:
                        logs.append(log_entry)
        return logs

    async def _process_trigger_activation(
        self,
        rule: AutomationRuleDefinition,
        activation: TriggerActivationEvent,
        ctx: EvaluationContext,
        *,
        bypass_cooldown: bool = False,
    ) -> Optional[AutomationExecutionLog]:
        return await self._process_correlated_match(
            rule,
            CorrelatedRuleMatch(activation=activation),
            ctx,
            bypass_cooldown=bypass_cooldown,
        )

    async def _process_correlated_match(
        self,
        rule: AutomationRuleDefinition,
        match: CorrelatedRuleMatch,
        ctx: EvaluationContext,
        *,
        bypass_cooldown: bool = False,
    ) -> Optional[AutomationExecutionLog]:
        activation = match.activation

        # 1. Check Cooldown
        if not bypass_cooldown and rule.cooldown_s > 0.0 and rule.last_triggered_at is not None:
            elapsed = ctx.now_ts - rule.last_triggered_at
            if 0.0 <= elapsed < rule.cooldown_s:
                self._record_diagnostic(
                    rule.rule_id,
                    "cooldown_skipped",
                    f"Saltata per cooldown ({elapsed:.1f}s < {rule.cooldown_s:.1f}s)",
                    timestamp=ctx.now_ts,
                )
                return None

        # 2. Evaluate Boolean Condition AST
        eval_ctx = EvaluationContext(
            now_ts=ctx.now_ts,
            kinematics_buffer=ctx.kinematics_buffer,
            zones=ctx.zones,
            virtual_entities=self.virtual_entities,
            ha_states=ctx.ha_states,
            astronomical_clock=ctx.astronomical_clock,
            known_identities_lower=ctx.known_identities_lower,
            whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            active_tracks=ctx.active_tracks,
            scene_event=ctx.scene_event,
            trigger_event=activation,
        )

        condition_ok = ConditionEvaluator.evaluate(rule.condition, eval_ctx)
        if not condition_ok:
            self._record_diagnostic(
                rule.rule_id,
                "condition_blocked",
                f"Condizione non soddisfatta per: {activation.summary}",
                timestamp=ctx.now_ts,
                details=dict(activation.extra),
            )
            if rule.log_blocked_evaluations:
                tr = activation.track
                blocked_log = AutomationExecutionLog(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    timestamp=round(ctx.now_ts, 3),
                    trigger_type=activation.trigger_type,
                    trigger_summary=activation.summary,
                    track_id=tr.track_id if tr is not None else None,
                    identity=tr.identity if tr is not None else None,
                    plate=tr.plate if tr is not None else None,
                    status="condition_blocked",
                    actions_executed=[],
                    details=dict(activation.extra),
                )
                blocked_log.id = self.repository.record_automation_log(blocked_log.model_dump())
            return None

        # 3. Manage Execution Mode concurrency ('single', 'restart', 'parallel', 'queued')
        running_tasks = self._running_rule_tasks.setdefault(rule.rule_id, set())
        active_tasks = {t for t in running_tasks if not t.done()}
        self._running_rule_tasks[rule.rule_id] = active_tasks

        has_async_delay = action_tree_contains_delay(rule.actions)
        if rule.execution_mode == "single" and active_tasks:
            return None
        if rule.execution_mode == "restart" and active_tasks:
            for t in active_tasks:
                t.cancel()
            active_tasks.clear()
        if rule.execution_mode == "queued" and active_tasks and has_async_delay:
            committed = self.sequence_coordinator.commit_match(rule, match)
            if committed:
                await self._broadcast_pretrigger_state(ctx.now_ts, force=True)
            self._queued_rule_runs.setdefault(rule.rule_id, deque(maxlen=16)).append(
                (rule, activation, eval_ctx)
            )
            return None

        committed = self.sequence_coordinator.commit_match(rule, match)
        if committed:
            await self._broadcast_pretrigger_state(ctx.now_ts, force=True)

        rule.last_triggered_at = round(ctx.now_ts, 3)
        rule.trigger_count += 1
        self.repository.upsert_automation_rule(rule.model_dump())

        if self.scene_event_manager is not None and eval_ctx.scene_event is not None:
            try:
                await self.scene_event_manager.mark_automation_triggered(
                    eval_ctx.scene_event.event_id,
                    rule.rule_id,
                )
            except Exception:
                pass

        if has_async_delay:
            task = asyncio.create_task(
                self._run_rule_actions_and_log_task(rule, activation, eval_ctx),
                name=f"auto-rule-{rule.rule_id}",
            )
            active_tasks.add(task)
            task.add_done_callback(active_tasks.discard)
            return None

        return await self._finalize_rule_execution(rule, activation, eval_ctx)

    async def _finalize_rule_execution(
        self,
        rule: AutomationRuleDefinition,
        activation: TriggerActivationEvent,
        eval_ctx: EvaluationContext,
    ) -> AutomationExecutionLog:
        actions_results = await self._execute_actions_list(rule, rule.actions, eval_ctx)
        has_err = any(not bool(r.get("ok", True)) for r in actions_results)

        tr = activation.track
        log_model = AutomationExecutionLog(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            timestamp=round(eval_ctx.now_ts, 3),
            trigger_type=activation.trigger_type,
            trigger_summary=activation.summary,
            track_id=tr.track_id if tr is not None else None,
            identity=tr.identity if tr is not None else None,
            plate=tr.plate if tr is not None else None,
            status="error" if (has_err and all(not bool(r.get("ok", True)) for r in actions_results)) else "executed",
            actions_executed=actions_results,
            details=dict(activation.extra),
        )
        log_id = self.repository.record_automation_log(log_model.model_dump())
        log_model.id = log_id

        self._record_diagnostic(
            rule.rule_id,
            "error" if log_model.status == "error" else "executed",
            activation.summary,
            timestamp=eval_ctx.now_ts,
            details=dict(activation.extra),
        )

        await self._broadcast(
            {
                "type": "automation_triggered",
                "log": log_model.model_dump(),
                "rule_id": rule.rule_id,
                "trigger_count": rule.trigger_count,
                "last_triggered_at": rule.last_triggered_at,
            }
        )
        return log_model

    async def _run_rule_actions_and_log_task(
        self,
        rule: AutomationRuleDefinition,
        activation: TriggerActivationEvent,
        eval_ctx: EvaluationContext,
    ) -> None:
        try:
            await self._finalize_rule_execution(rule, activation, eval_ctx)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Background rule task failed (%s): %s", rule.rule_id, exc)
            self._record_diagnostic(rule.rule_id, "error", str(exc), timestamp=time.time())
        finally:
            q = self._queued_rule_runs.get(rule.rule_id)
            if q:
                nxt_rule, nxt_act, nxt_ctx = q.popleft()
                nxt_rule.last_triggered_at = round(time.time(), 3)
                nxt_rule.trigger_count += 1
                self.repository.upsert_automation_rule(nxt_rule.model_dump())
                nxt_task = asyncio.create_task(
                    self._run_rule_actions_and_log_task(nxt_rule, nxt_act, nxt_ctx),
                    name=f"auto-rule-{nxt_rule.rule_id}",
                )
                task_set = self._running_rule_tasks.setdefault(nxt_rule.rule_id, set())
                task_set.add(nxt_task)
                nxt_task.add_done_callback(task_set.discard)

    async def trigger_rule_manually(self, rule_id: str) -> AutomationExecutionLog:
        """Manually execute an automation rule's actions (or test its condition) from the UI."""
        rule = self.rules.get(rule_id)
        if rule is None:
            raise ValueError(f"Automazione '{rule_id}' non trovata")

        now_ts = time.time()
        activation = TriggerActivationEvent(
            trigger_id="manual",
            trigger_type="manual_test",
            timestamp=now_ts,
            summary="Esecuzione manuale da Automation Studio",
        )
        ctx = self._build_evaluation_context(
            now_ts,
            active_tracks=list(self.kinematics_buffer._latest_tracks.values()),
            step_events_by_track={},
        )
        ctx.trigger_event = activation

        rule.last_triggered_at = round(now_ts, 3)
        rule.trigger_count += 1
        self.repository.upsert_automation_rule(rule.model_dump())

        actions_results = await self._execute_actions_list(rule, rule.actions, ctx)
        log_model = AutomationExecutionLog(
            rule_id=rule.rule_id,
            rule_name=rule.name,
            timestamp=round(now_ts, 3),
            trigger_type="manual_test",
            trigger_summary="Esecuzione manuale da Automation Studio",
            status="executed",
            actions_executed=actions_results,
        )
        log_model.id = self.repository.record_automation_log(log_model.model_dump())
        await self._broadcast(
            {
                "type": "automation_triggered",
                "log": log_model.model_dump(),
                "rule_id": rule.rule_id,
                "trigger_count": rule.trigger_count,
                "last_triggered_at": rule.last_triggered_at,
            }
        )
        return log_model

    # ========================================================================
    # PROCEDURAL ACTION RUNNER (Command Pattern + IF/THEN/ELSE + Templates)
    # ========================================================================

    async def _execute_actions_list(
        self,
        rule: AutomationRuleDefinition,
        actions: list[ActionSpec],
        ctx: EvaluationContext,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for act in actions:
            res = await self._execute_single_action(rule, act, ctx)
            results.append(res)
        return results

    async def _execute_single_action(
        self,
        rule: AutomationRuleDefinition,
        action: ActionSpec,
        ctx: EvaluationContext,
    ) -> dict[str, Any]:
        atype = action.type
        executor = ActionRegistry.get(atype)
        if executor is None:
            return {"type": atype, "ok": False, "error": f"Tipo azione sconosciuto: {atype}"}
        try:
            return await executor.execute(self, rule, action, ctx)
        except Exception as exc:
            logger.warning("Action %s in rule %s failed: %s", atype, rule.rule_id, exc)
            return {"type": atype, "ok": False, "error": str(exc)}

    async def _execute_send_notification(
        self,
        rule: AutomationRuleDefinition,
        action: ActionSpec,
        ctx: EvaluationContext,
    ) -> dict[str, Any]:
        params = action.params or {}
        ev_trig = ctx.trigger_event
        tr = ev_trig.track if ev_trig is not None else None
        zone_id = str(params.get("zone_id") or (ev_trig.zone_id if ev_trig else "") or "").strip() or None
        zone_name = ctx.zones[zone_id].name if (zone_id and zone_id in ctx.zones) else None
        location_label = str(params.get("location_label") or "").strip() or None

        scene_ctx = (
            self.scene_event_manager.get_active_scene_context(
                zone_id=zone_id,
                zone_name=zone_name,
                track=tr,
            )
            if self.scene_event_manager is not None
            else {"event": None, "subjects": [], "zone_subjects": [], "best_camera_id": None}
        )
        scene_ev = scene_ctx.get("event")
        scene_subjects = scene_ctx.get("zone_subjects") or scene_ctx.get("subjects") or []
        best_cam = scene_ctx.get("best_camera_id")

        image_mode = str(params.get("image_mode") or "annotated").strip().lower()
        if scene_ev is not None and self.scene_event_manager is not None and image_mode in ("annotated", "raw"):
            ensured = await self.scene_event_manager.ensure_event_snapshot(
                scene_ev.event_id,
                preferred_camera_id=best_cam,
            )
            if ensured is not None:
                scene_ev = ensured

        event_id = scene_ev.event_id if scene_ev is not None else None
        priority = str(params.get("priority") or "normal").strip().lower()
        if priority not in ("silent", "normal", "critical"):
            priority = "normal"

        if scene_ev is not None and self.scene_event_manager is not None:
            await self.scene_event_manager.mark_automation_triggered(
                scene_ev.event_id,
                rule.rule_id,
                escalate_importance="alert" if priority == "critical" else None,
            )

        message_mode = str(params.get("message_mode") or "auto_scene").strip().lower()
        if message_mode == "auto_scene" and scene_subjects:
            message = build_scene_sentence_it(
                scene_subjects,
                location_label=location_label,
                zone_names=[zone_name] if zone_name else (scene_ev.zones if scene_ev else None),
                camera_id=best_cam,
            )
        else:
            raw_msg = str(params.get("message") or "").strip()
            if raw_msg:
                message = self._render_template(raw_msg, ctx)
            elif scene_subjects:
                message = build_scene_sentence_it(
                    scene_subjects,
                    location_label=location_label,
                    zone_names=[zone_name] if zone_name else (scene_ev.zones if scene_ev else None),
                    camera_id=best_cam,
                )
            else:
                message = ev_trig.summary if ev_trig else rule.name

        raw_title = str(params.get("title") or "").strip()
        title = self._render_template(raw_title, ctx) if raw_title else (
            "Allarme Casa" if priority == "critical" else "Smart Home 3D"
        )

        raw_tag = str(params.get("tag") or "").strip()
        tag = self._render_template(raw_tag, ctx) if raw_tag else (f"sh3d_evt_{event_id}" if event_id else f"sh3d_{rule.rule_id}")

        base_app_url = (self.config.public_app_url or "").strip().rstrip("/")
        click_override = str(params.get("click_action") or "").strip()
        if click_override:
            click_url = self._render_template(click_override, ctx)
        elif event_id and base_app_url:
            click_url = f"{base_app_url}/?event={event_id}"
        elif event_id:
            click_url = f"/?event={event_id}"
        else:
            click_url = base_app_url or "/"

        image_url = self._resolve_notification_image_url(
            image_mode=image_mode,
            scene_ev=scene_ev,
            track=tr,
            base_app_url=base_app_url,
        )

        # Publish annotated JPEG to MQTT if enabled (for Nest Hub / LAN HA camera entity)
        if self.mqtt_bridge is not None and self.mqtt_bridge.is_connected() and scene_ev is not None and self.scene_event_manager is not None:
            try:
                snap_path = self.scene_event_manager.snapshot_store.resolve_snapshot_path(
                    scene_ev.event_id,
                    "raw" if image_mode == "raw" else "annotated",
                    known_relpath=scene_ev.cover_raw_relpath if image_mode == "raw" else scene_ev.cover_ann_relpath,
                )
                if snap_path is not None and snap_path.is_file():
                    await self.mqtt_bridge.publish_event_image(snap_path.read_bytes())
            except Exception:
                pass

        actions_cfg: list[dict[str, str]] = []
        for item in (params.get("actions") or []):
            if isinstance(item, dict):
                act_id = self._render_template(str(item.get("action") or "").strip(), ctx)
                act_title = self._render_template(str(item.get("title") or "").strip(), ctx)
                if act_id and act_title:
                    actions_cfg.append({"action": act_id, "title": act_title})

        mobile_targets = self._normalize_str_list(params.get("mobile_targets") or params.get("targets"))
        tv_targets = self._normalize_str_list(params.get("tv_targets"))
        tts_targets = self._normalize_str_list(params.get("tts_targets"))
        tts_entity = str(params.get("tts_entity") or "tts.google_translate_en_com").strip()
        display_show_image = bool(params.get("display_show_image", True))
        display_duration_s = max(5.0, min(120.0, float(params.get("display_duration_s") or 25.0)))
        tv_only_when_on = bool(params.get("tv_only_when_on", True))
        update_on_biometrics = bool(params.get("update_on_biometrics", True))

        results = await self._dispatch_notification_bundle(
            mobile_targets=mobile_targets,
            tv_targets=tv_targets,
            tts_targets=tts_targets,
            tts_entity=tts_entity,
            title=title,
            message=message,
            tag=tag,
            priority=priority,
            image_url=image_url,
            click_url=click_url,
            actions=actions_cfg,
            display_show_image=display_show_image,
            display_duration_s=display_duration_s,
            tv_only_when_on=tv_only_when_on,
            silent_update=False,
        )

        if update_on_biometrics and event_id and mobile_targets and tag:
            self._pending_notif_updates[event_id] = {
                "event_id": event_id,
                "expires_at": time.time() + 25.0,
                "mobile_targets": mobile_targets,
                "title": title,
                "tag": tag,
                "image_mode": image_mode,
                "click_url": click_url,
                "actions": actions_cfg,
                "location_label": location_label,
                "zone_name": zone_name,
                "best_cam": best_cam,
                "message_mode": message_mode,
                "raw_message": str(params.get("message") or ""),
            }

        return {
            "type": "send_notification",
            "event_id": event_id,
            "priority": priority,
            "message": message,
            "image_url": image_url,
            "dispatched": results,
            "ok": True,
        }

    def _resolve_notification_image_url(
        self,
        *,
        image_mode: str,
        scene_ev: Any,
        track: Optional[TrackedEntity3D],
        base_app_url: str,
    ) -> Optional[str]:
        if image_mode == "none":
            return None
        if image_mode == "crop":
            if track and track.best_crop_id:
                rel = f"/api/v1/biometrics/crops/{track.best_crop_id}"
                return f"{base_app_url}{rel}" if base_app_url else rel
            return None
        if scene_ev is not None and (scene_ev.cover_ann_relpath or scene_ev.cover_raw_relpath):
            variant = "raw" if image_mode == "raw" else "annotated"
            if self.signed_media_service is not None:
                return self.signed_media_service.build_signed_url(
                    base_app_url,
                    scene_ev.event_id,
                    variant=variant,  # type: ignore[arg-type]
                )
            rel = f"/api/v1/events/{scene_ev.event_id}/{'cover' if variant == 'raw' else 'annotated'}.jpg"
            return f"{base_app_url}{rel}" if base_app_url else rel
        return None

    @staticmethod
    def _normalize_str_list(raw: Any) -> list[str]:
        if isinstance(raw, str):
            return [s.strip() for s in raw.split(",") if s.strip()]
        if isinstance(raw, list):
            return [str(s).strip() for s in raw if str(s).strip()]
        return []

    async def _dispatch_notification_bundle(
        self,
        *,
        mobile_targets: list[str],
        tv_targets: list[str],
        tts_targets: list[str],
        tts_entity: str,
        title: str,
        message: str,
        tag: str,
        priority: str,
        image_url: Optional[str],
        click_url: str,
        actions: list[dict[str, str]],
        display_show_image: bool,
        display_duration_s: float,
        tv_only_when_on: bool,
        silent_update: bool,
    ) -> list[dict[str, Any]]:
        tasks: list[Coroutine[Any, Any, dict[str, Any]]] = []

        # 1. Mobile push notifications (Android + iOS HA Companion)
        for target_svc in mobile_targets:
            domain, svc_name = target_svc.split(".", 1) if "." in target_svc else ("notify", target_svc)
            data_block: dict[str, Any] = {
                "tag": tag,
                "clickAction": click_url,
                "url": click_url,
            }
            if image_url:
                data_block["image"] = image_url
            if actions:
                data_block["actions"] = actions

            if silent_update or priority == "silent":
                data_block["alert_once"] = True
                data_block["channel"] = "Silenzioso"
                data_block["importance"] = "low"
                data_block["push"] = {"sound": "none", "interruption-level": "passive"}
            elif priority == "critical":
                data_block["priority"] = "high"
                data_block["ttl"] = 0
                data_block["channel"] = "Allarme"
                data_block["importance"] = "high"
                data_block["push"] = {
                    "sound": {"name": "default", "critical": 1, "volume": 1.0},
                    "interruption-level": "critical",
                }
            else:
                data_block["channel"] = "Casa"
                data_block["importance"] = "default"

            payload = {"title": title, "message": message, "data": data_block}

            async def _send_mobile(d: str = domain, s: str = svc_name, p: dict[str, Any] = payload) -> dict[str, Any]:
                ok, note = await self._call_home_assistant_service(d, s, p)
                return {"channel": "mobile", "service": f"{d}.{s}", "ok": ok, "note": note}

            tasks.append(_send_mobile())

        if not silent_update:
            # 2. LG WebOS TV toast notifications
            for tv_svc in tv_targets:
                if tv_only_when_on and self._is_tv_off():
                    continue
                domain, svc_name = tv_svc.split(".", 1) if "." in tv_svc else ("notify", tv_svc)
                tv_payload = {"title": title, "message": message}

                async def _send_tv(d: str = domain, s: str = svc_name, p: dict[str, Any] = tv_payload) -> dict[str, Any]:
                    ok, note = await self._call_home_assistant_service(d, s, p)
                    return {"channel": "tv", "service": f"{d}.{s}", "ok": ok, "note": note}

                tasks.append(_send_tv())

            # 3. Nest Hub / Media Player TTS + optional photo display
            for mp_eid in tts_targets:
                async def _send_tts(media_eid: str = mp_eid) -> dict[str, Any]:
                    tts_domain, tts_svc = ("tts", "speak")
                    tts_data: dict[str, Any] = {
                        "entity_id": tts_entity,
                        "media_player_entity_id": media_eid,
                        "message": message,
                        "language": "it",
                        "cache": True,
                    }
                    ok, note = await self._call_home_assistant_service(tts_domain, tts_svc, tts_data)
                    if display_show_image:
                        media_img = self._resolve_lan_display_image_url(image_url)
                        if media_img:
                            t = asyncio.create_task(
                                self._show_image_and_turn_off_display(media_eid, media_img, display_duration_s)
                            )
                            self._active_display_tasks.add(t)
                            t.add_done_callback(self._active_display_tasks.discard)
                    return {"channel": "tts", "entity_id": media_eid, "ok": ok, "note": note}

                tasks.append(_send_tts())

        if not tasks:
            return []
        return list(await asyncio.gather(*tasks, return_exceptions=False))

    def _is_tv_off(self) -> bool:
        tv_states = [
            snap for eid, snap in self.ha_states.items()
            if eid.startswith("media_player.") and ("tv" in eid.lower() or "webos" in eid.lower())
        ]
        if not tv_states:
            return False
        return all(str(st.state).strip().lower() in ("off", "unavailable", "standby") for st in tv_states)

    def _resolve_lan_display_image_url(self, signed_public_url: Optional[str]) -> Optional[str]:
        """For Nest Hub in LAN: prefer local spatial_server URL if reachable or signed public URL."""
        if not signed_public_url:
            return None
        return signed_public_url

    async def _show_image_and_turn_off_display(
        self,
        media_player_eid: str,
        image_url: str,
        duration_s: float,
    ) -> None:
        try:
            await asyncio.sleep(2.5)
            await self._call_home_assistant_service(
                "media_player",
                "play_media",
                {
                    "entity_id": media_player_eid,
                    "media_content_id": image_url,
                    "media_content_type": "image/jpeg",
                },
            )
            await asyncio.sleep(max(2.0, duration_s))
            await self._call_home_assistant_service(
                "media_player",
                "turn_off",
                {"entity_id": media_player_eid},
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("Nest Hub display lifecycle error (%s): %s", media_player_eid, exc)

    async def _process_pending_notif_updates(
        self,
        update_dict: dict[str, Any],
        active_tracks: list[TrackedEntity3D],
        now_ts: float,
    ) -> None:
        if not self._pending_notif_updates or self.scene_event_manager is None:
            return

        # Prune expired entries first
        now_wall = time.time()
        for eid_key in list(self._pending_notif_updates):
            if now_wall > float(self._pending_notif_updates[eid_key].get("expires_at") or 0.0):
                self._pending_notif_updates.pop(eid_key, None)

        if not self._pending_notif_updates:
            return

        tid = int(update_dict.get("track_id") or 0)
        resolved_label = update_dict.get("identity") or update_dict.get("plate")
        if not resolved_label:
            return

        for ev_id, cfg in list(self._pending_notif_updates.items()):
            row = self.repository.get_scene_event(ev_id)
            active_ev = self.scene_event_manager.get_active_event()
            ev_obj = active_ev if (active_ev and active_ev.event_id == ev_id) else None
            if ev_obj is None and row is not None:
                from spatial_server.events.models import SceneEventRecord

                ev_obj = SceneEventRecord.model_validate(row)
            if ev_obj is None or tid not in ev_obj.track_ids:
                continue

            if cfg.get("message_mode") == "auto_scene":
                new_msg = build_scene_sentence_it(
                    ev_obj.subjects,
                    location_label=cfg.get("location_label"),
                    zone_names=[cfg["zone_name"]] if cfg.get("zone_name") else ev_obj.zones,
                    camera_id=cfg.get("best_cam") or ev_obj.best_camera_id,
                )
            else:
                new_msg = build_scene_sentence_it(
                    ev_obj.subjects,
                    location_label=cfg.get("location_label"),
                    zone_names=[cfg["zone_name"]] if cfg.get("zone_name") else ev_obj.zones,
                    camera_id=cfg.get("best_cam") or ev_obj.best_camera_id,
                )

            base_app_url = (self.config.public_app_url or "").strip().rstrip("/")
            tr = next((t for t in active_tracks if t.track_id == tid), None)
            image_url = self._resolve_notification_image_url(
                image_mode=str(cfg.get("image_mode") or "annotated"),
                scene_ev=ev_obj,
                track=tr,
                base_app_url=base_app_url,
            )
            await self._dispatch_notification_bundle(
                mobile_targets=list(cfg.get("mobile_targets") or []),
                tv_targets=[],
                tts_targets=[],
                tts_entity="",
                title=str(cfg.get("title") or "Smart Home 3D"),
                message=new_msg,
                tag=str(cfg.get("tag") or f"sh3d_evt_{ev_id}"),
                priority="silent",
                image_url=image_url,
                click_url=str(cfg.get("click_url") or "/"),
                actions=list(cfg.get("actions") or []),
                display_show_image=False,
                display_duration_s=0.0,
                tv_only_when_on=True,
                silent_update=True,
            )
            self._pending_notif_updates.pop(ev_id, None)

    async def on_ha_notification_action(self, action_name: str, event_data: dict[str, Any]) -> None:
        """
        Handle interactive button clicks from HA Companion notifications:
        - `SH3D_ALARM_SPENTO` / `SH3D_ALARM_OFF`
        - `SH3D_ALARM_SILENZIOSO`
        - `SH3D_ALARM_ACCESO` / `SH3D_ALARM_ON`
        - `SH3D_CALL_SERVICE:<domain>.<service>:<entity_id>`
        """
        act = (action_name or "").strip()
        upper = act.upper()
        alarm_ve = self.virtual_entities.get("sh3d.allarme")
        is_switch = alarm_ve is not None and alarm_ve.domain in ("switch", "boolean")

        if upper in ("SH3D_ALARM_SPENTO", "SH3D_ALARM_OFF"):
            target = "off" if is_switch else "Spento"
            await self.set_virtual_entity_state("sh3d.allarme", target, operation="set", trigger_automations=True)
            return
        if upper == "SH3D_ALARM_SILENZIOSO":
            target = "off" if is_switch else "Silenzioso"
            await self.set_virtual_entity_state("sh3d.allarme", target, operation="set", trigger_automations=True)
            return
        if upper in ("SH3D_ALARM_ACCESO", "SH3D_ALARM_ON"):
            target = "on" if is_switch else "Acceso"
            await self.set_virtual_entity_state("sh3d.allarme", target, operation="set", trigger_automations=True)
            return
        if act.startswith("SH3D_CALL_SERVICE:"):
            parts = act.split(":", 2)
            if len(parts) >= 2 and "." in parts[1]:
                domain, svc = parts[1].split(".", 1)
                data = {"entity_id": parts[2].strip()} if len(parts) == 3 and parts[2].strip() else {}
                await self._call_home_assistant_service(domain.strip(), svc.strip(), data)

    async def _call_home_assistant_service(
        self,
        domain: str,
        service_name: str,
        service_data: dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Execute a Home Assistant service call without duplicate execution:
        1. If backend H24 `ha_bridge` has `HA_TOKEN`, execute directly via backend HTTP client.
        2. Else if `config.ha_token` + HA URL are configured, execute direct REST POST.
        3. Only broadcast `automation_ha_service_call` to UI browsers when no backend token is present (Mock/dev).
        """
        eid = str(service_data.get("entity_id") or "")
        if eid:
            # Optimistically update local HA state cache for immediate chained conditions
            if service_name == "turn_on":
                self.ha_states[eid] = EntityStateSnapshot(entity_id=eid, state="on", last_changed=time.time(), source="ha")
            elif service_name == "turn_off":
                self.ha_states[eid] = EntityStateSnapshot(entity_id=eid, state="off", last_changed=time.time(), source="ha")
            elif service_name == "toggle":
                curr = self.ha_states.get(eid)
                nxt = "off" if (curr and curr.state == "on") else "on"
                self.ha_states[eid] = EntityStateSnapshot(entity_id=eid, state=nxt, last_changed=time.time(), source="ha")

        if self.ha_bridge is not None and self.ha_bridge.has_backend_token():
            ok, note = await self.ha_bridge.call_service(domain, service_name, service_data)
            if ok:
                return (True, note)

        token = (self.config.ha_token or "").strip()
        bases = [
            _normalize_ha_url(raw)
            for raw in (self.config.ha_local_url, self.config.ha_tailscale_url, self.config.ha_public_url)
            if _normalize_ha_url(raw).lower().startswith(("http://", "https://"))
        ]

        if not token or not bases:
            await self._broadcast(
                {
                    "type": "automation_ha_service_call",
                    "domain": domain,
                    "service": service_name,
                    "service_data": service_data,
                }
            )
            return (True, "Inviato via bridge WebSocket UI")

        def _post_ha_sync() -> tuple[bool, str]:
            body_bytes = json.dumps(service_data).encode("utf-8")
            last_err = ""
            for base in bases:
                url = f"{base}/api/services/{domain}/{service_name}"
                req = urllib.request.Request(
                    url,
                    data=body_bytes,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=3.5) as resp:
                        if 200 <= resp.status < 300:
                            return (True, f"Eseguito su Home Assistant ({base})")
                except Exception as exc:
                    last_err = f"{exc} ({base})"
            return (False, f"Errore REST HA: {last_err}")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _post_ha_sync)

    def _render_value(self, value: Any, ctx: EvaluationContext) -> Any:
        if isinstance(value, str):
            return self._render_template(value, ctx)
        if isinstance(value, list):
            return [self._render_value(item, ctx) for item in value]
        if isinstance(value, dict):
            return {k: self._render_value(v, ctx) for k, v in value.items()}
        return value

    def _render_template(self, template_str: str, ctx: EvaluationContext) -> str:
        if "{{" not in template_str:
            return template_str

        ev = ctx.trigger_event
        tr = ev.track if ev is not None else None
        kin = ev.kinematics if ev is not None else None
        zone_name = ""
        if ev and ev.zone_id and ev.zone_id in ctx.zones:
            zone_name = ctx.zones[ev.zone_id].name

        scene_ev = None
        scene_sentence = ""
        scene_title = ""
        scene_zones = ""
        scene_cam = ""
        if self.scene_event_manager is not None:
            sc = self.scene_event_manager.get_active_scene_context(
                zone_id=ev.zone_id if ev else None,
                zone_name=zone_name or None,
                track=tr,
            )
            scene_ev = sc.get("event")
            scene_subs = sc.get("zone_subjects") or sc.get("subjects") or []
            scene_cam = sc.get("best_camera_id") or ""
            if scene_subs:
                scene_sentence = build_scene_sentence_it(
                    scene_subs,
                    zone_names=[zone_name] if zone_name else (scene_ev.zones if scene_ev else None),
                    camera_id=scene_cam or None,
                )
                scene_title = scene_ev.title if scene_ev else build_scene_title_it(scene_subs, camera_id=scene_cam or None)
            if scene_ev is not None:
                scene_zones = ", ".join(scene_ev.zones)

        base_app_url = (self.config.public_app_url or "").strip().rstrip("/")
        event_id = scene_ev.event_id if scene_ev is not None else ""
        event_url = f"{base_app_url}/?event={event_id}" if (event_id and base_app_url) else (f"/?event={event_id}" if event_id else "")

        replacements: dict[str, str] = {
            "trigger.summary": ev.summary if ev else "",
            "trigger.type": ev.trigger_type if ev else "",
            "trigger.zone_id": (ev.zone_id or "") if ev else "",
            "trigger.zone_name": zone_name,
            "zone.name": zone_name,
            "track.id": str(tr.track_id) if tr else "",
            "track.class": tr.class_label if tr else "",
            "track.identity": (tr.identity or "Sconosciuto") if tr else "Sconosciuto",
            "track.plate": (tr.plate or "") if tr else "",
            "track.speed_mps": f"{kin.mean_speed_mps:.2f}" if kin else "0.00",
            "track.speed_kmh": f"{kin.mean_speed_kmh:.1f}" if kin else "0.0",
            "track.peak_speed_mps": f"{kin.peak_speed_mps:.2f}" if kin else "0.00",
            "track.peak_speed_kmh": f"{kin.peak_speed_kmh:.1f}" if kin else "0.0",
            "track.azimuth_deg": f"{kin.mean_azimuth_deg:.0f}" if (kin and kin.mean_azimuth_deg is not None) else "",
            "track.crop_url": f"/api/v1/biometrics/crops/{tr.best_crop_id}" if (tr and tr.best_crop_id) else "",
            "event.id": event_id,
            "event.url": event_url,
            "scene.sentence": scene_sentence,
            "scene.summary": scene_sentence,
            "scene.title": scene_title,
            "scene.camera_id": scene_cam,
            "scene.zones": scene_zones,
            "pre_trigger.summary": str((ev.extra or {}).get("pre_trigger_summary") or "") if ev else "",
            "sequence.elapsed_s": str((ev.extra or {}).get("sequence_elapsed_s") or "0") if ev else "0",
        }

        def _repl(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            if key in replacements:
                return replacements[key]
            snap = ctx.resolve_entity(key)
            if snap is not None:
                return snap.state
            return match.group(0)

        return re.sub(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}", _repl, template_str)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        if self.broadcast_callback is not None:
            try:
                await self.broadcast_callback(payload)
            except Exception as exc:
                logger.debug("Automation broadcast error: %s", exc)
