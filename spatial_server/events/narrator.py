from __future__ import annotations

import re
from typing import Iterable, Optional

from .models import SceneSubjectRecord

_PREPOSITION_PREFIXES = (
    "al ",
    "alla ",
    "all'",
    "allo ",
    "ai ",
    "alle ",
    "agli ",
    "in ",
    "nel ",
    "nella ",
    "nell'",
    "nello ",
    "nei ",
    "nelle ",
    "sul ",
    "sulla ",
    "sull'",
    "sotto ",
    "davanti ",
    "fuori ",
    "da ",
    "dal ",
    "dalla ",
)

_UNKNOWN_IDENTITIES = frozenset({"", "sconosciuto", "unknown", "none", "pending"})
_VEHICLE_CLASSES = frozenset({"car", "truck", "bus", "motorbike", "motorcycle", "vehicle"})


def _is_known_name(name: Optional[str]) -> bool:
    if not name:
        return False
    return name.strip().lower() not in _UNKNOWN_IDENTITIES


def _friendly_camera_name(camera_id: Optional[str]) -> str:
    if not camera_id:
        return ""
    clean = re.sub(r"^cam_", "", camera_id.strip(), flags=re.IGNORECASE)
    return clean.replace("_", " ").strip()


def format_location_it(
    location_label: Optional[str] = None,
    zone_names: Optional[Iterable[str]] = None,
    camera_id: Optional[str] = None,
) -> str:
    """Format a natural Italian location phrase (e.g. 'al cancelletto', 'all'ingresso')."""
    raw = (location_label or "").strip()
    if not raw and zone_names:
        for z in zone_names:
            if z and str(z).strip():
                raw = str(z).strip()
                break
    if not raw and camera_id:
        raw = _friendly_camera_name(camera_id)

    if not raw:
        return ""

    lower = raw.lower()
    if lower.startswith(_PREPOSITION_PREFIXES):
        return raw

    if "cancelletto" in lower:
        return "al cancelletto"
    if "carraio" in lower or "cancello" in lower:
        return "al carraio"
    if "portico" in lower:
        return "al portico"
    if "ingresso" in lower:
        return "all'ingresso"
    if "stradina" in lower:
        return "sulla stradina"
    if "giardino" in lower:
        return "in giardino"
    if "vialetto" in lower:
        return "sul vialetto"
    return f"in {raw}"


def _format_vehicle_phrase(v: SceneSubjectRecord) -> str:
    plate = (v.plate or "").strip().upper()
    owner = (v.plate_owner or "").strip()
    if plate and v.plate_whitelisted and owner:
        return f"l'auto di {owner} ({plate})"
    if plate and v.plate_whitelisted:
        return f"un veicolo autorizzato ({plate})"
    if plate:
        return f"un veicolo ({plate})"
    if v.class_label == "motorbike":
        return "una moto"
    if v.class_label == "truck":
        return "un furgone"
    return "un veicolo"


def build_scene_sentence_it(
    subjects: list[SceneSubjectRecord],
    *,
    location_label: Optional[str] = None,
    zone_names: Optional[Iterable[str]] = None,
    camera_id: Optional[str] = None,
) -> str:
    """
    Generate a natural Italian description for all subjects currently in the scene/zone.
    Supports known family faces, unknown people, whitelisted/guest vehicles, and animals.
    """
    loc = format_location_it(location_label, zone_names, camera_id)
    loc_suffix = f" {loc}" if loc else ""

    people = [s for s in subjects if s.class_label == "person"]
    vehicles = [s for s in subjects if s.class_label in _VEHICLE_CLASSES]
    animals = [s for s in subjects if s.class_label == "dog"]
    bicycles = [s for s in subjects if s.class_label == "bicycle"]

    known_names: list[str] = []
    seen_known: set[str] = set()
    unknown_count = 0

    for p in people:
        if _is_known_name(p.identity):
            clean = str(p.identity).strip()
            key = clean.lower()
            if key not in seen_known:
                seen_known.add(key)
                known_names.append(clean)
        else:
            unknown_count += 1

    n_known = len(known_names)
    person_sentence = ""

    if people:
        if n_known == 0:
            if unknown_count == 1:
                person_sentence = f"C'è una persona{loc_suffix}."
            else:
                person_sentence = f"Ci sono {unknown_count} persone{loc_suffix}."
        elif n_known == 1 and unknown_count == 0:
            person_sentence = f"C'è {known_names[0]}{loc_suffix}."
        elif n_known >= 1 and unknown_count == 1:
            person_sentence = f"Ci sono {', '.join(known_names)} e un'altra persona{loc_suffix}."
        elif n_known >= 1 and unknown_count > 1:
            person_sentence = f"Ci sono {', '.join(known_names)} e altre {unknown_count} persone{loc_suffix}."
        elif n_known == 2:
            person_sentence = f"Ci sono {known_names[0]} e {known_names[1]}{loc_suffix}."
        else:
            person_sentence = f"Ci sono {', '.join(known_names[:-1])} e {known_names[-1]}{loc_suffix}."

    if person_sentence and not vehicles:
        return person_sentence

    if vehicles and not people:
        if len(vehicles) == 1:
            v = vehicles[0]
            plate = (v.plate or "").strip().upper()
            owner = (v.plate_owner or "").strip()
            if plate and v.plate_whitelisted and owner:
                return f"Auto di {owner} ({plate}){loc_suffix}."
            if plate and v.plate_whitelisted:
                return f"Veicolo autorizzato ({plate}){loc_suffix}."
            if plate:
                return f"Veicolo ({plate}){loc_suffix}."
            if v.class_label == "motorbike":
                return f"C'è una moto{loc_suffix}."
            if v.class_label == "truck":
                return f"C'è un furgone{loc_suffix}."
            return f"C'è un veicolo{loc_suffix}."
        return f"Ci sono {len(vehicles)} veicoli{loc_suffix}."

    if person_sentence and vehicles:
        v_desc = _format_vehicle_phrase(vehicles[0]) if len(vehicles) == 1 else f"{len(vehicles)} veicoli"
        return f"{person_sentence[:-1]} con {v_desc}."

    if bicycles:
        if len(bicycles) == 1:
            return f"C'è una bicicletta{loc_suffix}."
        return f"Ci sono {len(bicycles)} biciclette{loc_suffix}."

    if animals:
        if len(animals) == 1:
            return f"C'è un animale{loc_suffix}."
        return f"Ci sono {len(animals)} animali{loc_suffix}."

    return f"Movimento rilevato{loc_suffix}."


def build_scene_title_it(
    subjects: list[SceneSubjectRecord],
    zone_names: Optional[Iterable[str]] = None,
    camera_id: Optional[str] = None,
) -> str:
    """Build a compact human-readable title for the Daily Events card."""
    parts: list[str] = []

    people = [s for s in subjects if s.class_label == "person"]
    vehicles = [s for s in subjects if s.class_label in _VEHICLE_CLASSES]
    others = [s for s in subjects if s.class_label not in ("person", *_VEHICLE_CLASSES)]

    known_names: list[str] = []
    seen_known: set[str] = set()
    unknown_count = 0
    for p in people:
        if _is_known_name(p.identity):
            clean = str(p.identity).strip()
            if clean.lower() not in seen_known:
                seen_known.add(clean.lower())
                known_names.append(clean)
        else:
            unknown_count += 1

    if known_names and unknown_count > 0:
        parts.append(f"{', '.join(known_names)} + {unknown_count} scon.")
    elif known_names:
        parts.append(", ".join(known_names))
    elif unknown_count == 1:
        parts.append("Persona sconosciuta")
    elif unknown_count > 1:
        parts.append(f"{unknown_count} persone")

    for v in vehicles[:2]:
        plate = (v.plate or "").strip().upper()
        owner = (v.plate_owner or "").strip()
        if plate and owner:
            parts.append(f"{plate} · {owner}")
        elif plate:
            parts.append(plate)
        elif v.class_label == "motorbike":
            parts.append("Moto")
        elif v.class_label == "truck":
            parts.append("Furgone")
        else:
            parts.append("Veicolo")

    if not parts and others:
        cls = others[0].class_label
        if cls == "dog":
            parts.append("Animale")
        elif cls == "bicycle":
            parts.append("Bicicletta")
        else:
            parts.append(cls.title())

    subject_str = " · ".join(parts) if parts else "Movimento"

    place = ""
    if zone_names:
        clean_zones = [str(z).strip() for z in zone_names if z and str(z).strip()]
        if clean_zones:
            place = " → ".join(clean_zones[:2])
    if not place and camera_id:
        place = _friendly_camera_name(camera_id)

    return f"{subject_str} · {place}" if place else subject_str
