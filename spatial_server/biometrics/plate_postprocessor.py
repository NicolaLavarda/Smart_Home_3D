from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

from .models import PlateNormalizedResult, PlateWhitelistEntry

# Italian standard plates (1994+) exclude I, O, Q, U to prevent visual confusion.
IT_VALID_LETTERS = "ABCDEFGHJKLMNPRSTVWXYZ"
IT_STD_REGEX = re.compile(r"^[A-HJ-NPR-TV-Z]{2}[0-9]{3}[A-HJ-NPR-TV-Z]{2}$")
IT_MOTO_REGEX = re.compile(r"^[A-HJ-NPR-TV-Z]{2}[0-9]{5}$")

_DIGIT_TO_IT_LETTER: dict[str, str] = {
    "0": "D",
    "1": "L",
    "2": "Z",
    "4": "A",
    "5": "S",
    "6": "G",
    "8": "B",
}
_INVALID_IT_LETTER_REPAIR: dict[str, str] = {
    "O": "D",
    "Q": "D",
    "I": "L",
    "U": "V",
}
_LETTER_TO_DIGIT: dict[str, str] = {
    "O": "0",
    "D": "0",
    "Q": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "S": "5",
    "G": "6",
    "T": "7",
    "B": "8",
    "A": "4",
}


def _repair_pattern(
    candidate: str,
    slot_types: str,
    *,
    max_repairs: int = 2,
) -> tuple[Optional[str], int]:
    """Repair OCR confusion chars according to positional expectation ('L' or 'D')."""
    if len(candidate) != len(slot_types):
        return None, 99

    out: list[str] = []
    repairs = 0
    for ch, expected in zip(candidate, slot_types):
        if expected == "L":
            if ch in IT_VALID_LETTERS:
                out.append(ch)
            elif ch in _INVALID_IT_LETTER_REPAIR:
                out.append(_INVALID_IT_LETTER_REPAIR[ch])
                repairs += 1
            elif ch in _DIGIT_TO_IT_LETTER:
                out.append(_DIGIT_TO_IT_LETTER[ch])
                repairs += 1
            else:
                return None, 99
        else:  # expected == "D"
            if ch.isdigit():
                out.append(ch)
            elif ch in _LETTER_TO_DIGIT:
                out.append(_LETTER_TO_DIGIT[ch])
                repairs += 1
            else:
                return None, 99

        if repairs > max_repairs:
            return None, 99

    return "".join(out), repairs


def normalize_and_validate_plate(
    raw_ocr: str,
    *,
    pad_char: str = "_",
    max_repairs: int = 2,
    repair_penalty: float = 0.04,
) -> PlateNormalizedResult:
    """
    Normalize OCR plate string and apply deterministic Italian/European post-processing.

    Supports:
    - Standard IT plates (`LLNNNLL`, excluding `I, O, Q, U`) with positional ambiguity repair
    - Italian EU blue-band artifacts (leading `'I'`, trailing province/year suffix)
    - Italian motorcycle plates (`LLNNNNN`)
    - Generic European/vintage/foreign plates (`EU_GENERIC`) without dropping valid non-standard plates
    """
    cleaned = re.sub(r"[^A-Z0-9]", "", (raw_ocr or "").replace(pad_char, "").upper())
    if len(cleaned) < 4:
        return PlateNormalizedResult(plate=None, raw_text=cleaned, plate_format="INVALID", is_valid=False)

    # 1. Exact standard IT or motorcycle match (zero penalty, never mutate exact plates)
    if IT_STD_REGEX.fullmatch(cleaned):
        return PlateNormalizedResult(
            plate=cleaned,
            raw_text=cleaned,
            plate_format="IT_STD",
            repairs_applied=0,
            confidence_penalty=0.0,
            is_valid=True,
        )
    if IT_MOTO_REGEX.fullmatch(cleaned):
        return PlateNormalizedResult(
            plate=cleaned,
            raw_text=cleaned,
            plate_format="IT_MOTO",
            repairs_applied=0,
            confidence_penalty=0.0,
            is_valid=True,
        )

    # 2. Candidate windows for IT standard & IT motorcycle OCR ambiguity repair
    candidates: list[tuple[int, float, str, str]] = []
    if len(cleaned) == 7:
        repaired_std, repairs_std = _repair_pattern(cleaned, "LLNNNLL", max_repairs=max_repairs)
        if repaired_std is not None and IT_STD_REGEX.fullmatch(repaired_std):
            candidates.append((repairs_std, round(repairs_std * repair_penalty, 4), "IT_STD", repaired_std))

        repaired_moto, repairs_moto = _repair_pattern(cleaned, "LLNNNNN", max_repairs=min(1, max_repairs))
        if repaired_moto is not None and IT_MOTO_REGEX.fullmatch(repaired_moto):
            candidates.append((repairs_moto, round(repairs_moto * repair_penalty + 0.005, 4), "IT_MOTO", repaired_moto))
    elif len(cleaned) == 8 and cleaned.startswith("I"):
        win = cleaned[1:]
        repaired_std, repairs_std = _repair_pattern(win, "LLNNNLL", max_repairs=min(1, max_repairs))
        if repaired_std is not None and IT_STD_REGEX.fullmatch(repaired_std):
            candidates.append((repairs_std, round(repairs_std * repair_penalty + 0.01, 4), "IT_STD", repaired_std))
        if IT_MOTO_REGEX.fullmatch(win):
            candidates.append((0, 0.015, "IT_MOTO", win))
    elif len(cleaned) == 9:
        # Handle optional EU 'I' + IT_STD + 1-char noise OR IT_STD + 2-char province/year sticker
        for win, win_pen in (
            *(([(cleaned[1:8], 0.02)] if cleaned.startswith("I") else [])),
            (cleaned[:7], 0.03),
        ):
            if IT_STD_REGEX.fullmatch(win):
                candidates.append((0, win_pen, "IT_STD", win))
            else:
                repaired_std, repairs_std = _repair_pattern(win, "LLNNNLL", max_repairs=min(1, max_repairs))
                if repaired_std is not None and IT_STD_REGEX.fullmatch(repaired_std):
                    candidates.append((repairs_std, round(repairs_std * repair_penalty + win_pen, 4), "IT_STD", repaired_std))

    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]))
        rep_cnt, total_pen, fmt, best_plate = candidates[0]
        return PlateNormalizedResult(
            plate=best_plate,
            raw_text=cleaned,
            plate_format=fmt,  # type: ignore[arg-type]
            repairs_applied=rep_cnt,
            confidence_penalty=total_pen,
            is_valid=True,
        )

    # 4. Generic EU / vintage / foreign plates (at least 4..9 alnum chars with >=1 digit and >=1 letter)
    if 4 <= len(cleaned) <= 9 and any(c.isdigit() for c in cleaned) and any(c.isalpha() for c in cleaned):
        return PlateNormalizedResult(
            plate=cleaned,
            raw_text=cleaned,
            plate_format="EU_GENERIC",
            repairs_applied=0,
            confidence_penalty=0.0,
            is_valid=True,
        )

    return PlateNormalizedResult(plate=None, raw_text=cleaned, plate_format="INVALID", is_valid=False)


def levenshtein_distance(a: str, b: str) -> int:
    """Compute exact Levenshtein edit distance between two short uppercase strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a

    prev = list(range(len(b) + 1))
    for ca in a:
        curr = [prev[0] + 1]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


class PlateWhitelistMatcher:
    """Thread-safe authorized plate whitelist with post-consensus fuzzy matching."""

    def __init__(self, json_path: Optional[Path] = None) -> None:
        self.json_path = Path(json_path) if json_path else None
        self._lock = threading.RLock()
        self._entries: dict[str, PlateWhitelistEntry] = {}
        if self.json_path is not None and self.json_path.is_file():
            self.load_json(self.json_path)

    @staticmethod
    def normalize_key(plate: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", (plate or "").upper())

    def load_json(self, path: Optional[Path] = None) -> int:
        target = Path(path or self.json_path or "")
        if not target or not target.is_file():
            return 0
        raw = json.loads(target.read_text(encoding="utf-8"))
        items = raw.get("plates", []) if isinstance(raw, dict) else raw
        loaded: dict[str, PlateWhitelistEntry] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            key = self.normalize_key(str(item.get("plate", "")))
            owner = str(item.get("owner_name") or "").strip()
            if not key or not owner:
                continue
            loaded[key] = PlateWhitelistEntry(
                plate=key,
                owner_name=owner,
                vehicle_label=item.get("vehicle_label"),
                notes=item.get("notes"),
                updated_at=float(item.get("updated_at") or time.time()),
            )
        with self._lock:
            self._entries = loaded
            return len(self._entries)

    def save_json(self, path: Optional[Path] = None) -> Optional[Path]:
        target = Path(path or self.json_path or "")
        if not str(target):
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp.json")
        with self._lock:
            payload = [entry.model_dump() for entry in self._entries.values()]
        tmp.write_text(json.dumps({"plates": payload}, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
        return target

    def replace_all(self, entries: list[PlateWhitelistEntry]) -> None:
        with self._lock:
            self._entries = {
                self.normalize_key(e.plate): PlateWhitelistEntry(
                    plate=self.normalize_key(e.plate),
                    owner_name=e.owner_name.strip(),
                    vehicle_label=e.vehicle_label,
                    notes=e.notes,
                    updated_at=e.updated_at or time.time(),
                )
                for e in entries
                if self.normalize_key(e.plate) and e.owner_name.strip()
            }

    def upsert(
        self,
        plate: str,
        owner_name: str,
        vehicle_label: Optional[str] = None,
        notes: Optional[str] = None,
        *,
        persist: bool = True,
    ) -> PlateWhitelistEntry:
        key = self.normalize_key(plate)
        if len(key) < 4:
            raise ValueError(f"Invalid plate format: {plate!r}")
        entry = PlateWhitelistEntry(
            plate=key,
            owner_name=owner_name.strip(),
            vehicle_label=vehicle_label.strip() if isinstance(vehicle_label, str) and vehicle_label.strip() else None,
            notes=notes.strip() if isinstance(notes, str) and notes.strip() else None,
            updated_at=time.time(),
        )
        with self._lock:
            self._entries[key] = entry
        if persist and self.json_path is not None:
            self.save_json(self.json_path)
        return entry

    def delete(self, plate: str, *, persist: bool = True) -> bool:
        key = self.normalize_key(plate)
        with self._lock:
            existed = self._entries.pop(key, None) is not None
        if existed and persist and self.json_path is not None:
            self.save_json(self.json_path)
        return existed

    def list_entries(self) -> list[PlateWhitelistEntry]:
        with self._lock:
            return sorted(self._entries.values(), key=lambda e: e.plate)

    def match(
        self,
        plate: str,
        *,
        max_distance: int = 1,
    ) -> tuple[Optional[PlateWhitelistEntry], Optional[int]]:
        """
        Match a consensus plate against whitelist.
        Fuzzy tolerance (`max_distance >= 1`) is applied only when `len >= 6` and rejects ties.
        """
        key = self.normalize_key(plate)
        if not key:
            return None, None

        with self._lock:
            exact = self._entries.get(key)
            if exact is not None:
                return exact, 0
            if max_distance <= 0 or len(key) < 6 or not self._entries:
                return None, None

            best_dist = max_distance + 1
            best_matches: list[PlateWhitelistEntry] = []
            for cand_key, entry in self._entries.items():
                if abs(len(cand_key) - len(key)) > max_distance:
                    continue
                d = levenshtein_distance(key, cand_key)
                if d <= max_distance:
                    if d < best_dist:
                        best_dist = d
                        best_matches = [entry]
                    elif d == best_dist:
                        best_matches.append(entry)

            if len(best_matches) == 1:
                return best_matches[0], best_dist
            return None, None
