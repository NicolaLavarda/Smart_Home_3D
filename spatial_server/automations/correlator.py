from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Optional

from spatial_server.domain.models import TrackedEntity3D
from .evaluators import EvaluationContext, TriggerActivationEvent, _coarse_class, _is_known_identity
from .models import (
    ArmedPreTriggerSnapshot,
    AutomationRuleDefinition,
    ConditionSpec,
    CorrelationScopeLiteral,
    PreTriggerStageSpec,
)


def _norm_plate(plate: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", (plate or "").upper())


def _extract_track_identity_fields(
    track: Optional[TrackedEntity3D],
) -> tuple[Optional[int], Optional[str], Optional[str], Optional[str]]:
    if track is None:
        return None, None, None, None
    tid = int(track.track_id)
    coarse = _coarse_class(track.class_label)
    ident = track.identity.strip() if track.identity and track.identity.strip() else None
    plate = _norm_plate(track.plate) or None
    return tid, coarse, ident, plate


@dataclass
class ArmedStageToken:
    """Represents an armed pre-trigger stage or buffered sub-trigger awaiting confirmation."""

    rule_id: str
    stage_id: str
    stage_index: int
    stage_name: str
    first_armed_at: float
    last_armed_at: float
    expires_at: float
    activation: TriggerActivationEvent
    track_id: Optional[int] = None
    coarse_class: Optional[str] = None
    identity: Optional[str] = None
    plate: Optional[str] = None
    scene_event_id: Optional[str] = None
    prior_chain: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_activation(
        cls,
        *,
        rule_id: str,
        stage_id: str,
        stage_index: int,
        stage_name: str,
        now_ts: float,
        expires_at: float,
        activation: TriggerActivationEvent,
        scene_event_id: Optional[str] = None,
        prior_chain: Optional[list[dict[str, Any]]] = None,
    ) -> "ArmedStageToken":
        tid, coarse, ident, plate = _extract_track_identity_fields(activation.track)
        eff_scene_id = activation.scene_event_id or scene_event_id
        return cls(
            rule_id=rule_id,
            stage_id=stage_id,
            stage_index=stage_index,
            stage_name=stage_name,
            first_armed_at=now_ts,
            last_armed_at=now_ts,
            expires_at=expires_at,
            activation=activation,
            track_id=tid,
            coarse_class=coarse,
            identity=ident,
            plate=plate,
            scene_event_id=eff_scene_id,
            prior_chain=list(prior_chain or []),
        )

    def refresh(
        self,
        now_ts: float,
        new_expires_at: float,
        activation: TriggerActivationEvent,
        *,
        scene_event_id: Optional[str] = None,
    ) -> None:
        self.last_armed_at = now_ts
        self.expires_at = max(self.expires_at, new_expires_at)
        self.activation = activation
        tid, coarse, ident, plate = _extract_track_identity_fields(activation.track)
        if tid is not None:
            self.track_id = tid
        if coarse is not None:
            self.coarse_class = coarse
        if ident is not None:
            self.identity = ident
        if plate is not None:
            self.plate = plate
        if activation.scene_event_id or scene_event_id:
            self.scene_event_id = activation.scene_event_id or scene_event_id

    def to_snapshot(self, rule_name: str, now_ts: float) -> ArmedPreTriggerSnapshot:
        return ArmedPreTriggerSnapshot(
            rule_id=self.rule_id,
            rule_name=rule_name,
            stage_id=self.stage_id,
            stage_index=self.stage_index,
            stage_name=self.stage_name or f"Pre-trigger {self.stage_index + 1}",
            armed_at=round(self.first_armed_at, 3),
            last_armed_at=round(self.last_armed_at, 3),
            expires_at=round(self.expires_at, 3),
            remaining_s=round(max(0.0, self.expires_at - now_ts), 2),
            track_id=self.track_id,
            coarse_class=self.coarse_class,
            identity=self.identity,
            plate=self.plate,
            scene_event_id=self.scene_event_id,
            summary=self.activation.summary,
        )


@dataclass
class CorrelatedRuleMatch:
    """Resolved rule match combining pre-trigger chain and main trigger(s)."""

    activation: TriggerActivationEvent
    consumed_tokens: list[tuple[str, int, ArmedStageToken]] = field(default_factory=list)
    consumed_main_rule_id: Optional[str] = None


class CorrelationPolicy:
    """Determines whether an armed token and a subsequent activation refer to the same entity/episode."""

    @staticmethod
    def matches(
        token: ArmedStageToken,
        candidate: TriggerActivationEvent,
        scope: CorrelationScopeLiteral,
        *,
        active_track_ids: set[int],
        candidate_scene_event_id: Optional[str],
        known_identities_lower: Optional[set[str]] = None,
    ) -> bool:
        if scope == "any":
            return True

        cand_tid, cand_coarse, cand_ident, cand_plate = _extract_track_identity_fields(candidate.track)
        cand_scene_id = candidate.scene_event_id or candidate_scene_event_id
        known_ids = known_identities_lower or set()

        if scope == "same_scene_event":
            return bool(token.scene_event_id and cand_scene_id and token.scene_event_id == cand_scene_id)

        if scope == "same_track":
            if token.track_id is None or cand_tid is None:
                return False
            if token.track_id == cand_tid:
                return True
            if token.plate and cand_plate and token.plate == cand_plate:
                return True
            if (
                _is_known_identity(token.identity, known_ids)
                and _is_known_identity(cand_ident, known_ids)
                and token.identity.lower() == cand_ident.lower()  # type: ignore[union-attr]
            ):
                return True
            return False

        # Default: "same_subject"
        if token.track_id is None or cand_tid is None:
            # Cross-domain (e.g. entity_state_change / time_schedule / scene_event without track)
            return True

        if token.coarse_class and cand_coarse and token.coarse_class != cand_coarse:
            return False

        # Strict biometric incompatibility check
        if token.plate and cand_plate and token.plate != cand_plate:
            return False
        if (
            _is_known_identity(token.identity, known_ids)
            and _is_known_identity(cand_ident, known_ids)
            and token.identity.lower() != cand_ident.lower()  # type: ignore[union-attr]
        ):
            return False

        if token.track_id == cand_tid:
            return True

        if token.plate and cand_plate and token.plate == cand_plate:
            return True
        if (
            _is_known_identity(token.identity, known_ids)
            and _is_known_identity(cand_ident, known_ids)
            and token.identity.lower() == cand_ident.lower()  # type: ignore[union-attr]
        ):
            return True

        # Multi-target isolation guard: if the previous track is STILL simultaneously active
        # as a distinct object on screen, never mix two live targets into one sequence!
        if token.track_id in active_track_ids:
            return False

        # Previous track was lost/occluded: allow handoff within the same SceneEvent (or unit test without SceneEvent)
        if token.scene_event_id and cand_scene_id:
            return token.scene_event_id == cand_scene_id
        return token.scene_event_id is None and cand_scene_id is None


class RuleSequenceCoordinator:
    """
    Stateful OOP orchestrator for multi-stage pre-triggers (`rule.pre_triggers`)
    and windowed multi-trigger conjunction (`rule.trigger_logic == 'and_within'`).
    """

    MAX_TOKENS_PER_STAGE = 32

    def __init__(self) -> None:
        self._armed_stages: dict[tuple[str, int], list[ArmedStageToken]] = {}
        self._stage_and_buffers: dict[tuple[str, str], dict[str, list[ArmedStageToken]]] = {}
        self._main_and_buffers: dict[str, dict[str, list[ArmedStageToken]]] = {}

    def prune_expired(self, now_ts: float) -> list[ArmedStageToken]:
        expired: list[ArmedStageToken] = []

        for key in list(self._armed_stages.keys()):
            kept: list[ArmedStageToken] = []
            for tok in self._armed_stages[key]:
                if now_ts > tok.expires_at:
                    expired.append(tok)
                else:
                    kept.append(tok)
            if kept:
                self._armed_stages[key] = kept
            else:
                self._armed_stages.pop(key, None)

        for key in list(self._stage_and_buffers.keys()):
            trig_map = self._stage_and_buffers[key]
            for trig_id in list(trig_map.keys()):
                kept_buf = [t for t in trig_map[trig_id] if now_ts <= t.expires_at]
                if kept_buf:
                    trig_map[trig_id] = kept_buf
                else:
                    trig_map.pop(trig_id, None)
            if not trig_map:
                self._stage_and_buffers.pop(key, None)

        for rule_id in list(self._main_and_buffers.keys()):
            trig_map = self._main_and_buffers[rule_id]
            for trig_id in list(trig_map.keys()):
                kept_buf = [t for t in trig_map[trig_id] if now_ts <= t.expires_at]
                if kept_buf:
                    trig_map[trig_id] = kept_buf
                else:
                    trig_map.pop(trig_id, None)
            if not trig_map:
                self._main_and_buffers.pop(rule_id, None)

        return expired

    def reset_rule(self, rule_id: str) -> bool:
        had_armed = any(k[0] == rule_id for k in self._armed_stages)
        for key in [k for k in self._armed_stages if k[0] == rule_id]:
            self._armed_stages.pop(key, None)
        for key in [k for k in self._stage_and_buffers if k[0] == rule_id]:
            self._stage_and_buffers.pop(key, None)
        self._main_and_buffers.pop(rule_id, None)
        return had_armed

    def get_armed_snapshots(
        self,
        rules: dict[str, AutomationRuleDefinition],
        now_ts: float,
    ) -> list[ArmedPreTriggerSnapshot]:
        snaps: list[ArmedPreTriggerSnapshot] = []
        for (rule_id, _stage_idx), tokens in self._armed_stages.items():
            rule = rules.get(rule_id)
            rule_name = rule.name if rule is not None else rule_id
            for tok in tokens:
                if now_ts <= tok.expires_at:
                    snaps.append(tok.to_snapshot(rule_name, now_ts))
        snaps.sort(key=lambda s: (s.rule_name.lower(), s.stage_index, s.armed_at))
        return snaps

    @staticmethod
    def _active_track_ids(ctx: EvaluationContext) -> set[int]:
        ids = {tr.track_id for tr in ctx.active_tracks}
        if not ids:
            ids = set(ctx.kinematics_buffer._latest_tracks.keys())
        return ids

    @staticmethod
    def _eval_stage_condition(
        condition: Optional[ConditionSpec],
        activation: TriggerActivationEvent,
        ctx: EvaluationContext,
    ) -> bool:
        if condition is None:
            return True
        from .evaluators import ConditionEvaluator

        cond_ctx = EvaluationContext(
            now_ts=ctx.now_ts,
            kinematics_buffer=ctx.kinematics_buffer,
            zones=ctx.zones,
            virtual_entities=ctx.virtual_entities,
            ha_states=ctx.ha_states,
            astronomical_clock=ctx.astronomical_clock,
            known_identities_lower=ctx.known_identities_lower,
            whitelisted_plates_upper=ctx.whitelisted_plates_upper,
            active_tracks=ctx.active_tracks,
            scene_event=ctx.scene_event,
            trigger_event=activation,
        )
        return ConditionEvaluator.evaluate(condition, cond_ctx)

    def _find_matching_prior_token(
        self,
        rule_id: str,
        prior_stage_index: int,
        prior_stage: PreTriggerStageSpec,
        candidate: TriggerActivationEvent,
        ctx: EvaluationContext,
        scene_event_id: Optional[str],
    ) -> Optional[ArmedStageToken]:
        tokens = self._armed_stages.get((rule_id, prior_stage_index))
        if not tokens:
            return None
        active_ids = self._active_track_ids(ctx)
        best: Optional[ArmedStageToken] = None
        for tok in tokens:
            if ctx.now_ts > tok.expires_at:
                continue
            if (ctx.now_ts - tok.first_armed_at) < prior_stage.min_delay_s:
                continue
            if CorrelationPolicy.matches(
                tok,
                candidate,
                prior_stage.correlation_scope,
                active_track_ids=active_ids,
                candidate_scene_event_id=scene_event_id,
                known_identities_lower=ctx.known_identities_lower,
            ):
                if best is None or tok.last_armed_at > best.last_armed_at:
                    best = tok
        return best

    def record_pre_trigger_activations(
        self,
        rule: AutomationRuleDefinition,
        stage_index: int,
        stage: PreTriggerStageSpec,
        enabled_prev_stage: Optional[tuple[int, PreTriggerStageSpec]],
        trig_activations_by_id: dict[str, list[TriggerActivationEvent]],
        ctx: EvaluationContext,
        *,
        scene_event_id: Optional[str],
    ) -> list[tuple[str, ArmedStageToken]]:
        """
        Process trigger activations for `stage`.
        Returns list of `(change_kind, ArmedStageToken)` where `change_kind` is
        `'armed'` or `'refreshed'`.
        """
        enabled_trigs = [t for t in stage.triggers if t.enabled]
        if not enabled_trigs:
            return []

        events_out: list[tuple[str, ArmedStageToken]] = []
        stage_label = stage.name.strip() or f"Pre-trigger {stage_index + 1}"

        if stage.match_mode == "all" and len(enabled_trigs) > 1:
            buf_key = (rule.rule_id, stage.stage_id)
            trig_map = self._stage_and_buffers.setdefault(buf_key, {})
            for trig_spec in enabled_trigs:
                for act in trig_activations_by_id.get(trig_spec.trigger_id, []):
                    tok = ArmedStageToken.from_activation(
                        rule_id=rule.rule_id,
                        stage_id=stage.stage_id,
                        stage_index=stage_index,
                        stage_name=stage_label,
                        now_ts=ctx.now_ts,
                        expires_at=ctx.now_ts + stage.stage_window_s,
                        activation=act,
                        scene_event_id=scene_event_id,
                    )
                    lst = trig_map.setdefault(trig_spec.trigger_id, [])
                    lst.append(tok)
                    if len(lst) > self.MAX_TOKENS_PER_STAGE:
                        del lst[: len(lst) - self.MAX_TOKENS_PER_STAGE]

            # Check if every enabled trigger in this stage has a mutually correlated token
            active_ids = self._active_track_ids(ctx)
            anchor_trig = enabled_trigs[0]
            anchor_tokens = trig_map.get(anchor_trig.trigger_id, [])
            for anch in list(anchor_tokens):
                matched_by_tid: dict[str, ArmedStageToken] = {anchor_trig.trigger_id: anch}
                all_ok = True
                for other_t in enabled_trigs[1:]:
                    cand_list = trig_map.get(other_t.trigger_id, [])
                    found = next(
                        (
                            c
                            for c in reversed(cand_list)
                            if CorrelationPolicy.matches(
                                anch,
                                c.activation,
                                stage.correlation_scope,
                                active_track_ids=active_ids,
                                candidate_scene_event_id=scene_event_id or c.scene_event_id,
                                known_identities_lower=ctx.known_identities_lower,
                            )
                        ),
                        None,
                    )
                    if found is None:
                        all_ok = False
                        break
                    matched_by_tid[other_t.trigger_id] = found
                if not all_ok:
                    continue

                latest_tok = max(matched_by_tid.values(), key=lambda t: t.last_armed_at)
                if not self._eval_stage_condition(stage.condition, latest_tok.activation, ctx):
                    continue

                prior_chain: list[dict[str, Any]] = []
                if enabled_prev_stage is not None:
                    prev_idx, prev_stage = enabled_prev_stage
                    prior_tok = self._find_matching_prior_token(
                        rule.rule_id,
                        prev_idx,
                        prev_stage,
                        latest_tok.activation,
                        ctx,
                        scene_event_id,
                    )
                    if prior_tok is None:
                        continue
                    prior_chain = list(prior_tok.prior_chain) + [
                        {
                            "stage_id": prior_tok.stage_id,
                            "stage_name": prior_tok.stage_name,
                            "summary": prior_tok.activation.summary,
                            "armed_at": prior_tok.first_armed_at,
                        }
                    ]

                # Remove consumed sub-tokens from stage AND buffer
                for tid_k, consumed_tok in matched_by_tid.items():
                    if tid_k in trig_map and consumed_tok in trig_map[tid_k]:
                        trig_map[tid_k].remove(consumed_tok)

                res = self._arm_or_refresh_stage_token(
                    rule=rule,
                    stage_index=stage_index,
                    stage=stage,
                    stage_label=stage_label,
                    activation=latest_tok.activation,
                    prior_chain=prior_chain,
                    ctx=ctx,
                    scene_event_id=scene_event_id,
                )
                if res is not None:
                    events_out.append(res)
            return events_out

        # Default: match_mode == "any" (or single trigger)
        for trig_spec in enabled_trigs:
            for act in trig_activations_by_id.get(trig_spec.trigger_id, []):
                if not self._eval_stage_condition(stage.condition, act, ctx):
                    continue
                prior_chain = []
                if enabled_prev_stage is not None:
                    prev_idx, prev_stage = enabled_prev_stage
                    prior_tok = self._find_matching_prior_token(
                        rule.rule_id,
                        prev_idx,
                        prev_stage,
                        act,
                        ctx,
                        scene_event_id,
                    )
                    if prior_tok is None:
                        continue
                    prior_chain = list(prior_tok.prior_chain) + [
                        {
                            "stage_id": prior_tok.stage_id,
                            "stage_name": prior_tok.stage_name,
                            "summary": prior_tok.activation.summary,
                            "armed_at": prior_tok.first_armed_at,
                        }
                    ]

                res = self._arm_or_refresh_stage_token(
                    rule=rule,
                    stage_index=stage_index,
                    stage=stage,
                    stage_label=stage_label,
                    activation=act,
                    prior_chain=prior_chain,
                    ctx=ctx,
                    scene_event_id=scene_event_id,
                )
                if res is not None:
                    events_out.append(res)
        return events_out

    def _arm_or_refresh_stage_token(
        self,
        *,
        rule: AutomationRuleDefinition,
        stage_index: int,
        stage: PreTriggerStageSpec,
        stage_label: str,
        activation: TriggerActivationEvent,
        prior_chain: list[dict[str, Any]],
        ctx: EvaluationContext,
        scene_event_id: Optional[str],
    ) -> Optional[tuple[str, ArmedStageToken]]:
        key = (rule.rule_id, stage_index)
        tokens = self._armed_stages.setdefault(key, [])
        active_ids = self._active_track_ids(ctx)
        new_expires = ctx.now_ts + stage.max_wait_s

        # Check if an existing token for the same subject is already armed
        for tok in tokens:
            if ctx.now_ts > tok.expires_at:
                continue
            if CorrelationPolicy.matches(
                tok,
                activation,
                stage.correlation_scope,
                active_track_ids=active_ids,
                candidate_scene_event_id=scene_event_id,
                known_identities_lower=ctx.known_identities_lower,
            ):
                if stage.refresh_on_rearm:
                    tok.refresh(ctx.now_ts, new_expires, activation, scene_event_id=scene_event_id)
                    if prior_chain:
                        tok.prior_chain = prior_chain
                    return ("refreshed", tok)
                return None

        new_tok = ArmedStageToken.from_activation(
            rule_id=rule.rule_id,
            stage_id=stage.stage_id,
            stage_index=stage_index,
            stage_name=stage_label,
            now_ts=ctx.now_ts,
            expires_at=new_expires,
            activation=activation,
            scene_event_id=scene_event_id,
            prior_chain=prior_chain,
        )
        tokens.append(new_tok)
        if len(tokens) > self.MAX_TOKENS_PER_STAGE:
            del tokens[: len(tokens) - self.MAX_TOKENS_PER_STAGE]
        return ("armed", new_tok)

    def resolve_main_activations(
        self,
        rule: AutomationRuleDefinition,
        trig_activations_by_id: dict[str, list[TriggerActivationEvent]],
        ctx: EvaluationContext,
        *,
        scene_event_id: Optional[str],
    ) -> list[CorrelatedRuleMatch]:
        enabled_main = [t for t in rule.triggers if t.enabled]
        if not enabled_main:
            return []

        enabled_stages = [
            (idx, stg)
            for idx, stg in enumerate(rule.pre_triggers)
            if stg.enabled and any(t.enabled for t in stg.triggers)
        ]
        last_stage: Optional[tuple[int, PreTriggerStageSpec]] = enabled_stages[-1] if enabled_stages else None

        if rule.trigger_logic == "and_within" and len(enabled_main) > 1:
            return self._resolve_main_and_within(
                rule,
                enabled_main,
                last_stage,
                trig_activations_by_id,
                ctx,
                scene_event_id=scene_event_id,
            )

        # Standard OR across main triggers, gated by optional final pre-trigger stage
        matches: list[CorrelatedRuleMatch] = []
        for trig_spec in enabled_main:
            for act in trig_activations_by_id.get(trig_spec.trigger_id, []):
                if last_stage is None:
                    matches.append(CorrelatedRuleMatch(activation=act))
                    continue

                prev_idx, prev_stage = last_stage
                prior_tok = self._find_matching_prior_token(
                    rule.rule_id,
                    prev_idx,
                    prev_stage,
                    act,
                    ctx,
                    scene_event_id,
                )
                if prior_tok is None:
                    continue

                chain = list(prior_tok.prior_chain) + [
                    {
                        "stage_id": prior_tok.stage_id,
                        "stage_name": prior_tok.stage_name,
                        "summary": prior_tok.activation.summary,
                        "armed_at": prior_tok.first_armed_at,
                    }
                ]
                elapsed_s = round(max(0.0, ctx.now_ts - float(chain[0]["armed_at"])), 2)
                enriched = TriggerActivationEvent(
                    trigger_id=act.trigger_id,
                    trigger_type=act.trigger_type,
                    timestamp=act.timestamp,
                    summary=act.summary,
                    track=act.track or prior_tok.activation.track,
                    zone_id=act.zone_id or prior_tok.activation.zone_id,
                    from_zone_id=act.from_zone_id or prior_tok.activation.from_zone_id,
                    to_zone_id=act.to_zone_id or prior_tok.activation.to_zone_id,
                    entity_id=act.entity_id,
                    old_state=act.old_state,
                    new_state=act.new_state,
                    kinematics=act.kinematics or prior_tok.activation.kinematics,
                    scene_event_id=act.scene_event_id or prior_tok.scene_event_id or scene_event_id,
                    extra={
                        **act.extra,
                        "pre_trigger_chain": chain,
                        "pre_trigger_summary": prior_tok.activation.summary,
                        "sequence_elapsed_s": elapsed_s,
                    },
                )
                matches.append(
                    CorrelatedRuleMatch(
                        activation=enriched,
                        consumed_tokens=[(rule.rule_id, prev_idx, prior_tok)],
                    )
                )
        return matches

    def _resolve_main_and_within(
        self,
        rule: AutomationRuleDefinition,
        enabled_main: list[Any],
        last_stage: Optional[tuple[int, PreTriggerStageSpec]],
        trig_activations_by_id: dict[str, list[TriggerActivationEvent]],
        ctx: EvaluationContext,
        *,
        scene_event_id: Optional[str],
    ) -> list[CorrelatedRuleMatch]:
        trig_map = self._main_and_buffers.setdefault(rule.rule_id, {})
        any_new = False
        for trig_spec in enabled_main:
            for act in trig_activations_by_id.get(trig_spec.trigger_id, []):
                any_new = True
                tok = ArmedStageToken.from_activation(
                    rule_id=rule.rule_id,
                    stage_id="main",
                    stage_index=0,
                    stage_name="main",
                    now_ts=ctx.now_ts,
                    expires_at=ctx.now_ts + rule.trigger_window_s,
                    activation=act,
                    scene_event_id=scene_event_id,
                )
                lst = trig_map.setdefault(trig_spec.trigger_id, [])
                lst.append(tok)
                if len(lst) > self.MAX_TOKENS_PER_STAGE:
                    del lst[: len(lst) - self.MAX_TOKENS_PER_STAGE]

        if not any_new:
            return []

        active_ids = self._active_track_ids(ctx)
        anchor_trig = enabled_main[0]
        anchor_tokens = trig_map.get(anchor_trig.trigger_id, [])
        matches: list[CorrelatedRuleMatch] = []

        for anch in list(anchor_tokens):
            if ctx.now_ts > anch.expires_at:
                continue
            matched_tokens: list[ArmedStageToken] = [anch]
            all_ok = True
            for other_t in enabled_main[1:]:
                cand_list = trig_map.get(other_t.trigger_id, [])
                found = next(
                    (
                        c
                        for c in reversed(cand_list)
                        if ctx.now_ts <= c.expires_at
                        and CorrelationPolicy.matches(
                            anch,
                            c.activation,
                            rule.trigger_correlation_scope,
                            active_track_ids=active_ids,
                            candidate_scene_event_id=scene_event_id or c.scene_event_id,
                            known_identities_lower=ctx.known_identities_lower,
                        )
                    ),
                    None,
                )
                if found is None:
                    all_ok = False
                    break
                matched_tokens.append(found)
            if not all_ok:
                continue

            # Pick the richest activation as primary (prefer one with locked biometrics / plate / identity / zone)
            primary_tok = max(
                matched_tokens,
                key=lambda t: (
                    1 if (t.activation.track and t.activation.track.biometric_locked) else 0,
                    1 if (t.plate or t.identity) else 0,
                    1 if t.activation.zone_id else 0,
                    t.last_armed_at,
                ),
            )
            primary_act = primary_tok.activation

            consumed_pre: list[tuple[str, int, ArmedStageToken]] = []
            chain: list[dict[str, Any]] = []
            if last_stage is not None:
                prev_idx, prev_stage = last_stage
                prior_tok = self._find_matching_prior_token(
                    rule.rule_id,
                    prev_idx,
                    prev_stage,
                    primary_act,
                    ctx,
                    scene_event_id,
                )
                if prior_tok is None:
                    continue
                consumed_pre.append((rule.rule_id, prev_idx, prior_tok))
                chain = list(prior_tok.prior_chain) + [
                    {
                        "stage_id": prior_tok.stage_id,
                        "stage_name": prior_tok.stage_name,
                        "summary": prior_tok.activation.summary,
                        "armed_at": prior_tok.first_armed_at,
                    }
                ]

            earliest_ts = min(
                [t.first_armed_at for t in matched_tokens]
                + ([float(chain[0]["armed_at"])] if chain else [])
            )
            combined_summary = " + ".join(t.activation.summary for t in matched_tokens)
            merged_track = primary_act.track or next(
                (t.activation.track for t in matched_tokens if t.activation.track is not None),
                None,
            )
            merged_zone = primary_act.zone_id or next(
                (t.activation.zone_id for t in matched_tokens if t.activation.zone_id),
                None,
            )
            merged_kin = primary_act.kinematics or next(
                (t.activation.kinematics for t in matched_tokens if t.activation.kinematics is not None),
                None,
            )
            enriched = TriggerActivationEvent(
                trigger_id=primary_act.trigger_id,
                trigger_type=primary_act.trigger_type,
                timestamp=ctx.now_ts,
                summary=combined_summary,
                track=merged_track,
                zone_id=merged_zone,
                from_zone_id=primary_act.from_zone_id,
                to_zone_id=primary_act.to_zone_id,
                entity_id=primary_act.entity_id,
                old_state=primary_act.old_state,
                new_state=primary_act.new_state,
                kinematics=merged_kin,
                scene_event_id=primary_act.scene_event_id or scene_event_id,
                extra={
                    **primary_act.extra,
                    "matched_triggers": [t.activation.trigger_type for t in matched_tokens],
                    "pre_trigger_chain": chain,
                    "pre_trigger_summary": chain[-1]["summary"] if chain else "",
                    "sequence_elapsed_s": round(max(0.0, ctx.now_ts - earliest_ts), 2),
                },
            )
            matches.append(
                CorrelatedRuleMatch(
                    activation=enriched,
                    consumed_tokens=consumed_pre,
                    consumed_main_rule_id=rule.rule_id,
                )
            )
            break

        return matches

    def commit_match(self, rule: AutomationRuleDefinition, match: CorrelatedRuleMatch) -> bool:
        """Consume armed pre-trigger tokens and AND buffers once the rule actually fires."""
        changed = False
        for rule_id, stage_idx, tok in match.consumed_tokens:
            stage = rule.pre_triggers[stage_idx] if 0 <= stage_idx < len(rule.pre_triggers) else None
            if stage is not None and not stage.consume_on_fire:
                continue
            lst = self._armed_stages.get((rule_id, stage_idx))
            if lst and tok in lst:
                lst.remove(tok)
                if not lst:
                    self._armed_stages.pop((rule_id, stage_idx), None)
                changed = True
            # Also clear earlier stages for the same rule if they share the same subject
            for idx in range(stage_idx):
                prev_lst = self._armed_stages.get((rule_id, idx))
                if prev_lst:
                    self._armed_stages[(rule_id, idx)] = [
                        pt for pt in prev_lst if pt.track_id != tok.track_id
                    ]
                    if not self._armed_stages[(rule_id, idx)]:
                        self._armed_stages.pop((rule_id, idx), None)
                    changed = True

        if match.consumed_main_rule_id:
            if self._main_and_buffers.pop(match.consumed_main_rule_id, None) is not None:
                changed = True

        return changed
