from __future__ import annotations

import re
import time
import uuid
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class Point2D(BaseModel):
    """2D world coordinate on the horizontal Three.js XZ ground plane."""

    x: float
    z: float


class SpatialZoneDefinition(BaseModel):
    """
    2.5D spatial area (closed polygon) or oriented perimeter/tripwire polyline.
    Coordinates are in Three.js world space (+X East, +Y Up, +Z South).
    """

    zone_id: str = Field(default_factory=lambda: f"zone_{uuid.uuid4().hex[:8]}")
    name: str
    geometry_type: Literal["polygon", "perimeter"] = "polygon"
    vertices: list[Point2D] = Field(min_length=2)
    y_min: float = -2.0
    y_max: float = 4.5
    normal_flipped: bool = False
    hysteresis_m: float = Field(default=0.12, ge=0.0, le=2.0)
    color: str = "#38bdf8"
    enabled: bool = True
    notes: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    updated_at: float = Field(default_factory=lambda: round(time.time(), 3))

    @field_validator("zone_id")
    @classmethod
    def sanitize_zone_id(cls, v: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_-]", "_", (v or "").strip())
        return clean or f"zone_{uuid.uuid4().hex[:8]}"

    @field_validator("vertices")
    @classmethod
    def validate_vertices_len(cls, v: list[Point2D], info: Any) -> list[Point2D]:
        geom_type = info.data.get("geometry_type", "polygon")
        if geom_type == "polygon" and len(v) < 3:
            raise ValueError("Un'area poligonale richiede almeno 3 vertici")
        if geom_type == "perimeter" and len(v) < 2:
            raise ValueError("Un perimetro/polilinea richiede almeno 2 vertici")
        return v


class VirtualEntityDefinition(BaseModel):
    """
    Internal program entity (sh3d.*) that can be toggled by users or automations
    and used as a trigger, condition, or action target (e.g. sh3d.allarme_casa).
    """

    entity_id: str
    name: str
    domain: Literal["switch", "boolean", "select", "number", "sensor"] = "switch"
    state: str = "off"
    options: list[str] = Field(default_factory=list)
    unit_of_measurement: Optional[str] = None
    icon: str = "shield"
    attributes: dict[str, Any] = Field(default_factory=dict)
    last_changed: float = Field(default_factory=lambda: round(time.time(), 3))
    updated_at: float = Field(default_factory=lambda: round(time.time(), 3))

    @field_validator("entity_id")
    @classmethod
    def normalize_entity_id(cls, v: str) -> str:
        raw = (v or "").strip().lower()
        if not raw:
            raise ValueError("entity_id obbligatorio")
        if "." in raw:
            prefix, slug = raw.split(".", 1)
            clean_prefix = re.sub(r"[^a-z0-9_]", "", prefix) or "sh3d"
            clean_slug = re.sub(r"[^a-z0-9_]", "_", slug).strip("_")
            if not clean_slug:
                raise ValueError("Slug entità non valido")
            return f"{clean_prefix}.{clean_slug}"
        clean_slug = re.sub(r"[^a-z0-9_]", "_", raw).strip("_")
        if not clean_slug:
            raise ValueError("entity_id non valido")
        return f"sh3d.{clean_slug}"


class SubjectFilterSpec(BaseModel):
    """
    Universal filter matching tracked 3D entities by object class,
    face recognition gallery identity, and license plate whitelist status.
    """

    classes: list[str] = Field(default_factory=list)
    face_mode: Literal["any", "known", "unknown", "include", "exclude"] = "any"
    identities: list[str] = Field(default_factory=list)
    plate_mode: Literal["any", "whitelisted", "not_whitelisted", "include", "exclude"] = "any"
    plates: list[str] = Field(default_factory=list)
    biometric_grace_s: float = Field(default=1.2, ge=0.0, le=15.0)


TriggerTypeLiteral = Literal[
    "zone_presence",
    "perimeter_crossing",
    "zone_transition",
    "kinematic_vector",
    "time_schedule",
    "entity_state_change",
    "biometric_detection",
    "proximity_3d",
]


class TriggerSpec(BaseModel):
    """Polymorphic trigger specification for an automation rule."""

    trigger_id: str = Field(default_factory=lambda: f"trg_{uuid.uuid4().hex[:8]}")
    type: TriggerTypeLiteral
    enabled: bool = True
    label: Optional[str] = None
    subject_filter: SubjectFilterSpec = Field(default_factory=SubjectFilterSpec)
    params: dict[str, Any] = Field(default_factory=dict)


ConditionTypeLiteral = Literal[
    "and",
    "or",
    "not",
    "xor",
    "entity_state",
    "time_window",
    "zone_occupancy",
    "track_kinematics",
]


class ConditionSpec(BaseModel):
    """Recursive boolean AST node for evaluating rule or action conditions."""

    condition_id: str = Field(default_factory=lambda: f"cnd_{uuid.uuid4().hex[:8]}")
    type: ConditionTypeLiteral = "and"
    children: list["ConditionSpec"] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


ActionTypeLiteral = Literal[
    "set_virtual_entity",
    "call_ha_service",
    "send_notification",
    "ui_alert",
    "delay",
    "if_then_else",
    "webhook",
]


class ActionSpec(BaseModel):
    """Recursive command specification supporting procedural IF/THEN/ELSE branching."""

    action_id: str = Field(default_factory=lambda: f"act_{uuid.uuid4().hex[:8]}")
    type: ActionTypeLiteral
    params: dict[str, Any] = Field(default_factory=dict)
    if_condition: Optional[ConditionSpec] = None
    then_actions: list["ActionSpec"] = Field(default_factory=list)
    else_actions: list["ActionSpec"] = Field(default_factory=list)


ConditionSpec.model_rebuild()
ActionSpec.model_rebuild()


class AutomationRuleDefinition(BaseModel):
    """Complete Event-Condition-Action automation rule definition."""

    rule_id: str = Field(default_factory=lambda: f"rule_{uuid.uuid4().hex[:8]}")
    name: str
    description: str = ""
    enabled: bool = True
    execution_mode: Literal["single", "restart", "parallel", "queued"] = "single"
    cooldown_s: float = Field(default=3.0, ge=0.0, le=86400.0)
    triggers: list[TriggerSpec] = Field(default_factory=list)
    condition: Optional[ConditionSpec] = None
    actions: list[ActionSpec] = Field(default_factory=list)
    last_triggered_at: Optional[float] = None
    trigger_count: int = 0
    updated_at: float = Field(default_factory=lambda: round(time.time(), 3))

    @field_validator("rule_id")
    @classmethod
    def sanitize_rule_id(cls, v: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_-]", "_", (v or "").strip())
        return clean or f"rule_{uuid.uuid4().hex[:8]}"


class AutomationExecutionLog(BaseModel):
    """Execution audit entry recorded whenever a rule triggers."""

    id: Optional[int] = None
    rule_id: str
    rule_name: str
    timestamp: float
    trigger_type: str
    trigger_summary: str
    track_id: Optional[int] = None
    identity: Optional[str] = None
    plate: Optional[str] = None
    status: Literal["executed", "condition_blocked", "cooldown_skipped", "error"] = "executed"
    actions_executed: list[dict[str, Any]] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
