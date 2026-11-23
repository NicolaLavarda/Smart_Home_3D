from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from spatial_server.domain.models import TrackedEntity3D


class ITrackRepository(ABC):
    """Repository interface for persistent spatiotemporal trajectories."""

    @abstractmethod
    def append_batch(self, entities: list[TrackedEntity3D]) -> int:
        """Persist a batch of TrackedEntity3D states synchronously/atomically."""

    @abstractmethod
    def query_time_range(
        self,
        t_start: float,
        t_end: float,
        classes: Optional[list[str]] = None,
        zone_bbox: Optional[tuple[float, float, float, float]] = None,
        limit: int = 5000,
        identity: Optional[str] = None,
        plate: Optional[str] = None,
        unknown_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Query detections inside [t_start, t_end] optionally filtered by class, XZ zone & biometrics."""

    @abstractmethod
    def query_timeline_density(self, t_start: float, t_end: float, buckets: int = 60) -> list[dict[str, Any]]:
        """Compute activity histogram buckets across [t_start, t_end]."""

    @abstractmethod
    def prune_older_than(self, cutoff_timestamp: float) -> int:
        """Delete records older than cutoff_timestamp and return removed row count."""

    def get_max_track_id(self) -> int:
        """Return highest persisted track_id across history & biometric tables (0 if empty)."""
        return 0

    def backfill_track_biometrics(
        self,
        track_id: int,
        *,
        min_timestamp: float,
        identity: Optional[str] = None,
        identity_confidence: Optional[float] = None,
        plate: Optional[str] = None,
        plate_confidence: Optional[float] = None,
        plate_whitelisted: Optional[bool] = None,
        plate_owner: Optional[str] = None,
        biometric_locked: Optional[bool] = None,
        best_crop_id: Optional[str] = None,
    ) -> int:
        """Retroactively update earlier persisted rows of an identified track."""
        return 0

    def record_biometric_event(self, event: dict[str, Any]) -> int:
        """Insert or update a deduplicated biometric event for a visit and return event id."""
        return 0

    def query_biometric_events(
        self,
        t_start: Optional[float] = None,
        t_end: Optional[float] = None,
        *,
        modality: Optional[str] = None,
        status: Optional[str] = None,
        identity: Optional[str] = None,
        plate: Optional[str] = None,
        track_id: Optional[int] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Query persisted biometric recognition events."""
        return []

    def get_biometric_event(self, event_id: int) -> Optional[dict[str, Any]]:
        """Fetch a single biometric event by primary key id."""
        return None

    def get_crop_relpath(self, crop_id: str) -> Optional[str]:
        """Resolve stored relative crop path for a crop_id, if known."""
        return None

    def prune_biometric_events_older_than(self, cutoff_timestamp: float) -> tuple[int, list[str]]:
        """Delete expired biometric_events rows and return (deleted_count, crop_relpaths)."""
        return (0, [])

    def list_plate_whitelist(self) -> list[dict[str, Any]]:
        """Return all authorized plates stored in persistence."""
        return []

    def upsert_plate_whitelist(
        self,
        plate: str,
        owner_name: str,
        vehicle_label: Optional[str] = None,
        notes: Optional[str] = None,
        updated_at: Optional[float] = None,
    ) -> dict[str, Any]:
        """Insert or update an authorized plate entry."""
        raise NotImplementedError("Plate whitelist persistence not implemented")

    def delete_plate_whitelist(self, plate: str) -> bool:
        """Remove an authorized plate entry and return True if deleted."""
        return False

    def list_face_identities_meta(self) -> list[dict[str, Any]]:
        """Return per-identity metadata aggregated across face embeddings & biometric events."""
        return []

    def update_biometric_event_review(
        self,
        event_id: int,
        *,
        identity: Optional[str] = None,
        identity_confidence: Optional[float] = None,
        plate: Optional[str] = None,
        plate_confidence: Optional[float] = None,
        plate_whitelisted: Optional[bool] = None,
        plate_owner: Optional[str] = None,
        biometric_locked: Optional[bool] = None,
        biometric_status: Optional[str] = None,
        reviewed_by: Optional[str] = None,
        reviewed_at: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """Update an existing biometric event after Admin HITL review and return the updated record."""
        return None

    def add_face_embedding(
        self,
        person_name: str,
        model_name: str,
        embedding_blob: bytes,
        *,
        quality_score: float = 0.0,
        source: str = "hitl",
        created_at: Optional[float] = None,
    ) -> int:
        """Persist a single L2-normalized face embedding sample and return its row id."""
        return 0

    def delete_face_embeddings(self, person_name: str) -> int:
        """Delete persisted face embedding samples for `person_name` and return removed row count."""
        return 0

    # --- Spatial Automations, Zones & Virtual Entities Persistence ---

    def list_spatial_zones(self) -> list[dict[str, Any]]:
        """Return all persisted 2.5D spatial zones and oriented perimeters."""
        return []

    def upsert_spatial_zone(self, zone: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a spatial zone definition."""
        raise NotImplementedError("Spatial zones persistence not implemented")

    def delete_spatial_zone(self, zone_id: str) -> bool:
        """Delete a spatial zone by zone_id and return True if removed."""
        return False

    def list_virtual_entities(self) -> list[dict[str, Any]]:
        """Return all persisted internal program virtual entities (sh3d.*)."""
        return []

    def upsert_virtual_entity(self, entity: dict[str, Any]) -> dict[str, Any]:
        """Insert or update an internal virtual entity definition and state."""
        raise NotImplementedError("Virtual entities persistence not implemented")

    def delete_virtual_entity(self, entity_id: str) -> bool:
        """Delete a virtual entity by entity_id and return True if removed."""
        return False

    def list_automation_rules(self) -> list[dict[str, Any]]:
        """Return all persisted automation rules."""
        return []

    def upsert_automation_rule(self, rule: dict[str, Any]) -> dict[str, Any]:
        """Insert or update an automation rule definition."""
        raise NotImplementedError("Automation rules persistence not implemented")

    def delete_automation_rule(self, rule_id: str) -> bool:
        """Delete an automation rule by rule_id and return True if removed."""
        return False

    def record_automation_log(self, log_entry: dict[str, Any]) -> int:
        """Persist an automation execution log entry and return its primary key id."""
        return 0

    def query_automation_logs(
        self,
        *,
        rule_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return recent automation execution logs."""
        return []

    def clear_automation_logs(self) -> int:
        """Delete all automation execution logs and return deleted row count."""
        return 0


