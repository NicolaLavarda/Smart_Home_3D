from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import json
import time
import urllib.request
from typing import Any, Callable, Optional, Type

from .evaluators import ConditionEvaluator, EvaluationContext
from .models import ActionSpec, AutomationRuleDefinition


class BaseActionExecutor(ABC):
    """Abstract Strategy for executing a single ActionSpec node."""

    action_type: str = ""

    @abstractmethod
    async def execute(
        self,
        engine: Any,
        rule: AutomationRuleDefinition,
        action: ActionSpec,
        ctx: EvaluationContext,
    ) -> dict[str, Any]:
        """Execute the action and return a structured audit dictionary."""


class ActionRegistry:
    """Open/Closed registry mapping action_type strings to BaseActionExecutor instances."""

    _executors: dict[str, BaseActionExecutor] = {}

    @classmethod
    def register(cls, action_type: str) -> Callable[[Type[BaseActionExecutor]], Type[BaseActionExecutor]]:
        def decorator(subclass: Type[BaseActionExecutor]) -> Type[BaseActionExecutor]:
            subclass.action_type = action_type
            cls._executors[action_type] = subclass()
            return subclass

        return decorator

    @classmethod
    def get(cls, action_type: str) -> Optional[BaseActionExecutor]:
        return cls._executors.get(action_type)


def action_tree_contains_delay(actions: list[ActionSpec]) -> bool:
    """Return True if any action (or nested IF/THEN/ELSE branch) contains a `delay` step."""
    for act in actions:
        if act.type == "delay":
            return True
        if act.then_actions and action_tree_contains_delay(act.then_actions):
            return True
        if act.else_actions and action_tree_contains_delay(act.else_actions):
            return True
    return False


@ActionRegistry.register("set_virtual_entity")
class SetVirtualEntityActionExecutor(BaseActionExecutor):
    async def execute(
        self,
        engine: Any,
        rule: AutomationRuleDefinition,
        action: ActionSpec,
        ctx: EvaluationContext,
    ) -> dict[str, Any]:
        params = action.params
        entity_id = str(params.get("entity_id") or "").strip()
        operation = str(params.get("operation") or "set").strip().lower()
        raw_val = params.get("state", params.get("value", "on"))
        rendered_val = engine._render_template(str(raw_val), ctx) if raw_val is not None else None
        updated_ve = await engine.set_virtual_entity_state(
            entity_id,
            rendered_val,
            operation=operation,
            trigger_automations=True,
        )
        return {
            "type": action.type,
            "entity_id": updated_ve.entity_id,
            "state": updated_ve.state,
            "operation": operation,
            "ok": True,
        }


@ActionRegistry.register("call_ha_service")
class CallHaServiceActionExecutor(BaseActionExecutor):
    async def execute(
        self,
        engine: Any,
        rule: AutomationRuleDefinition,
        action: ActionSpec,
        ctx: EvaluationContext,
    ) -> dict[str, Any]:
        params = action.params
        full_service = str(params.get("service") or "").strip()
        domain = str(params.get("domain") or "").strip()
        if "." in full_service and not domain:
            domain, service_name = full_service.split(".", 1)
        else:
            service_name = full_service or "turn_on"
            domain = domain or "homeassistant"

        entity_id = str(params.get("entity_id") or "").strip()
        raw_data = params.get("service_data") if isinstance(params.get("service_data"), dict) else {}
        rendered_data = engine._render_value(raw_data, ctx)
        if not isinstance(rendered_data, dict):
            rendered_data = {}
        if entity_id:
            rendered_data["entity_id"] = entity_id

        ha_ok, ha_note = await engine._call_home_assistant_service(domain, service_name, rendered_data)
        return {
            "type": action.type,
            "service": f"{domain}.{service_name}",
            "entity_id": entity_id,
            "service_data": rendered_data,
            "ok": ha_ok,
            "note": ha_note,
        }


@ActionRegistry.register("send_notification")
class SendNotificationActionExecutor(BaseActionExecutor):
    async def execute(
        self,
        engine: Any,
        rule: AutomationRuleDefinition,
        action: ActionSpec,
        ctx: EvaluationContext,
    ) -> dict[str, Any]:
        return await engine._execute_send_notification(rule, action, ctx)


@ActionRegistry.register("ui_alert")
class UiAlertActionExecutor(BaseActionExecutor):
    async def execute(
        self,
        engine: Any,
        rule: AutomationRuleDefinition,
        action: ActionSpec,
        ctx: EvaluationContext,
    ) -> dict[str, Any]:
        params = action.params
        title = engine._render_template(str(params.get("title") or rule.name), ctx)
        message = engine._render_template(
            str(params.get("message") or (ctx.trigger_event.summary if ctx.trigger_event else "")),
            ctx,
        )
        severity = str(params.get("severity") or "warning")
        sound = bool(params.get("sound", severity == "critical"))
        highlight_zone_id = str(params.get("zone_id") or (ctx.trigger_event.zone_id if ctx.trigger_event else "") or "")
        focus_camera_id = str(params.get("camera_id") or "")
        if engine.scene_event_manager is not None:
            scene_ctx = engine.scene_event_manager.get_active_scene_context(
                zone_id=highlight_zone_id or None,
                track=ctx.trigger_event.track if ctx.trigger_event else None,
            )
            ev_obj = scene_ctx.get("event")
            if ev_obj is not None:
                await engine.scene_event_manager.mark_automation_triggered(
                    ev_obj.event_id,
                    rule.rule_id,
                    escalate_importance="alert" if severity == "critical" else None,
                )
        await engine._broadcast(
            {
                "type": "automation_ui_alert",
                "rule_id": rule.rule_id,
                "rule_name": rule.name,
                "timestamp": time.time(),
                "title": title,
                "message": message,
                "severity": severity,
                "sound": sound,
                "zone_id": highlight_zone_id or None,
                "camera_id": focus_camera_id or None,
                "track_id": ctx.trigger_event.track.track_id if (ctx.trigger_event and ctx.trigger_event.track) else None,
            }
        )
        return {
            "type": action.type,
            "title": title,
            "message": message,
            "severity": severity,
            "ok": True,
        }


@ActionRegistry.register("delay")
class DelayActionExecutor(BaseActionExecutor):
    async def execute(
        self,
        engine: Any,
        rule: AutomationRuleDefinition,
        action: ActionSpec,
        ctx: EvaluationContext,
    ) -> dict[str, Any]:
        delay_s = max(0.0, min(float(action.params.get("seconds") or 1.0), 3600.0))
        if delay_s > 0.0:
            await asyncio.sleep(delay_s)
        ctx.now_ts = time.time()
        return {"type": action.type, "seconds": delay_s, "ok": True}


@ActionRegistry.register("if_then_else")
class IfThenElseActionExecutor(BaseActionExecutor):
    async def execute(
        self,
        engine: Any,
        rule: AutomationRuleDefinition,
        action: ActionSpec,
        ctx: EvaluationContext,
    ) -> dict[str, Any]:
        branch_cond = ConditionEvaluator.evaluate(action.if_condition, ctx)
        chosen_actions = action.then_actions if branch_cond else action.else_actions
        sub_results = await engine._execute_actions_list(rule, chosen_actions, ctx)
        return {
            "type": action.type,
            "condition_matched": branch_cond,
            "branch": "then" if branch_cond else "else",
            "sub_actions": sub_results,
            "ok": True,
        }


@ActionRegistry.register("webhook")
class WebhookActionExecutor(BaseActionExecutor):
    async def execute(
        self,
        engine: Any,
        rule: AutomationRuleDefinition,
        action: ActionSpec,
        ctx: EvaluationContext,
    ) -> dict[str, Any]:
        params = action.params
        url = str(params.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return {"type": action.type, "ok": False, "error": "URL webhook non valido"}
        method = str(params.get("method") or "POST").upper()
        body_payload = {
            "rule_id": rule.rule_id,
            "rule_name": rule.name,
            "timestamp": ctx.now_ts,
            "trigger": ctx.trigger_event.summary if ctx.trigger_event else "manual",
        }
        loop = asyncio.get_running_loop()

        def _send_webhook() -> int:
            req = urllib.request.Request(
                url,
                data=json.dumps(body_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method=method,
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                return int(resp.status)

        status_code = await loop.run_in_executor(None, _send_webhook)
        return {"type": action.type, "url": url, "status_code": status_code, "ok": 200 <= status_code < 400}
