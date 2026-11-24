from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Callable, Literal, Optional

from .models import is_valid_event_id


class SignedMediaTokenService:
    """
    Generates and verifies short-lived HMAC-SHA256 URL tokens for event cover snapshots
    so Home Assistant Companion notifications (LAN & 4G/5G over Tailscale) can fetch
    the exact event image without requiring a browser session cookie.
    """

    def __init__(
        self,
        secret_provider: Callable[[], bytes],
        *,
        default_ttl_s: int = 86400,
    ) -> None:
        self._secret_provider = secret_provider
        self.default_ttl_s = max(60, int(default_ttl_s))

    def _compute_sig(self, event_id: str, variant: str, exp: int) -> str:
        secret = self._secret_provider()
        msg = f"{event_id}:{variant}:{exp}".encode("utf-8")
        digest = hmac.new(secret, msg, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def sign_media_path(
        self,
        event_id: str,
        variant: Literal["raw", "annotated"] = "annotated",
        *,
        ttl_s: Optional[int] = None,
        now_ts: Optional[float] = None,
    ) -> tuple[int, str]:
        if not is_valid_event_id(event_id):
            raise ValueError(f"Invalid event_id: {event_id!r}")
        if variant not in ("raw", "annotated"):
            raise ValueError(f"Invalid variant: {variant!r}")
        now = float(now_ts if now_ts is not None else time.time())
        eff_ttl = max(30, int(ttl_s if ttl_s is not None else self.default_ttl_s))
        exp = int(round(now)) + eff_ttl
        sig = self._compute_sig(event_id, variant, exp)
        return exp, sig

    def verify_media_signature(
        self,
        event_id: str,
        variant: str,
        exp: int,
        sig: str,
        *,
        now_ts: Optional[float] = None,
    ) -> bool:
        if not is_valid_event_id(event_id) or variant not in ("raw", "annotated"):
            return False
        if not sig or not isinstance(sig, str):
            return False
        now = float(now_ts if now_ts is not None else time.time())
        if int(exp) < int(now):
            return False
        expected = self._compute_sig(event_id, variant, int(exp))
        return hmac.compare_digest(expected, sig.strip())

    def build_signed_url(
        self,
        base_url: str,
        event_id: str,
        variant: Literal["raw", "annotated"] = "annotated",
        *,
        ttl_s: Optional[int] = None,
        now_ts: Optional[float] = None,
    ) -> str:
        exp, sig = self.sign_media_path(event_id, variant, ttl_s=ttl_s, now_ts=now_ts)
        rel = f"/api/v1/events/{event_id}/media/{variant}.jpg?exp={exp}&sig={sig}"
        clean_base = (base_url or "").strip().rstrip("/")
        return f"{clean_base}{rel}" if clean_base else rel
