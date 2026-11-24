from __future__ import annotations

import re
import time
import uuid
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator

VALID_EVENT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")


def generate_event_id(ts: Optional[float] = None) -> str:
    ms = int(round((ts if ts is not None else time.time()) * 1000))
    return f"evt_{ms}_{uuid.uuid4().hex[:4]}"


def is_valid_event_id(event_id: str) -> bool:
    return bool(event_id and VALID_EVENT_ID_RE.fullmatch(event_id))


class SceneSubjectRecord(BaseModel):
    """Aggregated subject participating in a SceneEvent across one or more cameras."""

    track_id: int
    class_label: str
    identity: Optional[str] = None
    identity_confidence: float = 0.0
    plate: Optional[str] = None
    plate_whitelisted: Optional[bool] = None
    plate_owner: Optional[str] = None
    biometric_status: str = "none"
    biometric_event_id: Optional[int] = None
    best_crop_id: Optional[str] = None
    first_seen: float = 0.0
    last_seen: float = 0.0
    cameras: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)


class FrameBoxAnnotation(BaseModel):
    """Normalized [0, 1] bounding-box metadata used to draw/re-draw annotated event frames."""

    track_id: Optional[int] = None
    class_label: str = "person"
    label: str = ""
    category: Literal["known", "unknown", "plate_wl", "plate_guest", "object"] = "object"
    bbox_norm: tuple[float, float, float, float]
    sub_bbox_norm: Optional[tuple[float, float, float, float]] = None


class SceneEventRecord(BaseModel):
    """Unified multi-camera, multi-track scene episode persisted in SQLite."""

    event_id: str = Field(default_factory=generate_event_id)
    status: Literal["active", "closed"] = "active"
    started_at: float
    ended_at: float
    duration_s: float = 0.0
    replay_start_at: float = 0.0
    importance: Literal["routine", "notable", "alert"] = "notable"
    title: str = ""
    summary_it: str = ""
    best_camera_id: Optional[str] = None
    cameras: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)
    zone_ids: list[str] = Field(default_factory=list)
    track_ids: list[int] = Field(default_factory=list)
    subjects: list[SceneSubjectRecord] = Field(default_factory=list)
    cover_raw_relpath: Optional[str] = None
    cover_ann_relpath: Optional[str] = None
    cover_url: Optional[str] = None
    annotated_url: Optional[str] = None
    best_frame_score: float = 0.0
    best_frame_ts: Optional[float] = None
    best_frame_boxes: list[FrameBoxAnnotation] = Field(default_factory=list)
    alarm_state: Optional[str] = None
    automation_rule_ids: list[str] = Field(default_factory=list)
    has_video_clip: bool = False
    has_hd_clip: bool = False
    reviewed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, v: str) -> str:
        clean = (v or "").strip()
        if not is_valid_event_id(clean):
            raise ValueError(f"event_id non valido: {v!r}")
        return clean

    def to_api_dict(self) -> dict[str, Any]:
        """Serialize safely for REST/WebSocket without exposing internal filesystem paths."""
        data = self.model_dump(exclude={"cover_raw_relpath", "cover_ann_relpath"})
        if self.cover_raw_relpath:
            data["cover_url"] = f"/api/v1/events/{self.event_id}/cover.jpg"
        else:
            data["cover_url"] = self.cover_url
        if self.cover_ann_relpath:
            data["annotated_url"] = f"/api/v1/events/{self.event_id}/annotated.jpg"
        else:
            data["annotated_url"] = self.annotated_url or data["cover_url"]
        return data
