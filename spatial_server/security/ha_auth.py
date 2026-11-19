from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping, Optional

import httpx
import websockets
from fastapi import Depends, HTTPException, Request, Response, WebSocket
from starlette.requests import HTTPConnection
from websockets.exceptions import WebSocketException

if TYPE_CHECKING:
    from spatial_server.config import SpatialServerConfig

logger = logging.getLogger("spatial_server.security")

SH3D_SESSION_COOKIE_NAME = "sh3d_session"


class AuthError(Exception):
    """Base authentication/authorization failure."""


class InvalidAuthTokenError(AuthError):
    """Raised when a Home Assistant Bearer token is missing, malformed, or rejected."""


class InvalidSessionCookieError(AuthError):
    """Raised when an HMAC-signed sh3d_session cookie is missing, tampered, or expired."""


class HomeAssistantUnavailableError(AuthError):
    """Raised when no configured Home Assistant endpoint can verify the token."""


@dataclass(frozen=True)
class HAUserPrincipal:
    user_id: str
    name: str
    is_admin: bool
    is_owner: bool
    authenticated_at: float
    expires_at: float

    @property
    def is_privileged(self) -> bool:
        return bool(self.is_admin or self.is_owner)

    def is_expired(self, now: Optional[float] = None) -> bool:
        current = time.time() if now is None else float(now)
        return current >= self.expires_at

    def to_user_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "is_admin": self.is_admin,
            "is_owner": self.is_owner,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_user_dict(),
            "is_privileged": self.is_privileged,
            "authenticated_at": self.authenticated_at,
            "expires_at": self.expires_at,
        }


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def _normalize_http_base_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        return ""
    low = url.lower()
    if low.startswith("ws://"):
        url = "http://" + url[5:]
    elif low.startswith("wss://"):
        url = "https://" + url[6:]
    if url.lower().endswith("/api/websocket"):
        url = url[:-14]
    elif url.lower().endswith("/api/websocket/"):
        url = url[:-15]
    url = url.rstrip("/")
    if not url.lower().startswith(("http://", "https://")):
        return ""
    return url


def _http_to_ws_url(base_url: str) -> str:
    if base_url.lower().startswith("https://"):
        return "wss://" + base_url[8:] + "/api/websocket"
    return "ws://" + base_url[7:] + "/api/websocket"


def extract_bearer_token(headers: Mapping[str, str]) -> str:
    auth_header = headers.get("authorization") or headers.get("Authorization") or ""
    if not auth_header:
        return ""
    parts = auth_header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


def is_https_request(request: HTTPConnection) -> bool:
    if request.url.scheme.lower() == "https":
        return True
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    first_proto = forwarded_proto.split(",")[0].strip().lower()
    return first_proto == "https"


def set_session_cookie(
    response: Response,
    request: Request,
    cookie_value: str,
    max_age_s: int,
) -> None:
    response.set_cookie(
        key=SH3D_SESSION_COOKIE_NAME,
        value=cookie_value,
        max_age=max(0, int(max_age_s)),
        path="/",
        httponly=True,
        samesite="strict",
        secure=is_https_request(request),
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=SH3D_SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
        secure=is_https_request(request),
    )


def synthetic_local_admin_principal() -> HAUserPrincipal:
    now = time.time()
    return HAUserPrincipal(
        user_id="local_dev",
        name="Local Dev Admin",
        is_admin=True,
        is_owner=True,
        authenticated_at=now,
        expires_at=now + 3600.0,
    )


class HomeAssistantAuthVerifier:
    """Verifies Home Assistant Bearer tokens and signs/verifies sh3d_session cookies."""

    def __init__(
        self,
        ha_local_url: str = "",
        ha_tailscale_url: str = "",
        ha_public_url: str = "",
        cache_ttl_s: float = 120.0,
        session_secret_key: str = "",
        session_ttl_s: float = 43200.0,
        request_timeout_s: float = 3.5,
        max_cache_entries: int = 1024,
    ) -> None:
        self.ha_local_url = _normalize_http_base_url(ha_local_url)
        self.ha_tailscale_url = _normalize_http_base_url(ha_tailscale_url)
        self.ha_public_url = _normalize_http_base_url(ha_public_url)
        self.cache_ttl_s = max(0.0, float(cache_ttl_s))
        self.session_ttl_s = max(1.0, float(session_ttl_s))
        self.request_timeout_s = max(0.2, float(request_timeout_s))
        self.max_cache_entries = max(1, int(max_cache_entries))

        secret_clean = (session_secret_key or "").strip()
        if secret_clean:
            self._session_secret = secret_clean.encode("utf-8")
        else:
            logger.warning(
                "SPATIAL_SESSION_SECRET not set; generating ephemeral per-process HMAC secret"
            )
            self._session_secret = secrets.token_bytes(32)

        self._cache_lock = threading.RLock()
        self._cache: dict[str, HAUserPrincipal] = {}

    @classmethod
    def from_config(cls, config: "SpatialServerConfig") -> "HomeAssistantAuthVerifier":
        return cls(
            ha_local_url=config.ha_local_url,
            ha_tailscale_url=config.ha_tailscale_url,
            ha_public_url=config.ha_public_url,
            cache_ttl_s=config.auth_cache_ttl_s,
            session_secret_key=config.session_secret_key,
        )

    def _candidate_base_urls(self) -> list[str]:
        candidates: list[str] = []
        for raw in (self.ha_local_url, self.ha_tailscale_url, self.ha_public_url):
            norm = _normalize_http_base_url(raw)
            if norm and norm not in candidates:
                candidates.append(norm)
        return candidates

    def _prune_cache_locked(self, now: float) -> None:
        expired = [k for k, v in self._cache.items() if v.is_expired(now)]
        for key in expired:
            del self._cache[key]

    def _get_cached_principal(self, token_hash: str) -> Optional[HAUserPrincipal]:
        if self.cache_ttl_s <= 0.0:
            return None
        now = time.time()
        with self._cache_lock:
            self._prune_cache_locked(now)
            principal = self._cache.get(token_hash)
            if principal is None or principal.is_expired(now):
                self._cache.pop(token_hash, None)
                return None
            return principal

    def _put_cached_principal(self, token_hash: str, principal: HAUserPrincipal) -> None:
        if self.cache_ttl_s <= 0.0:
            return
        now = time.time()
        with self._cache_lock:
            self._prune_cache_locked(now)
            while len(self._cache) >= self.max_cache_entries:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[token_hash] = principal

    async def _verify_via_websocket(
        self, base_url: str, token: str
    ) -> HAUserPrincipal:
        ws_url = _http_to_ws_url(base_url)
        async with websockets.connect(
            ws_url,
            open_timeout=self.request_timeout_s,
            close_timeout=2.0,
            ping_interval=None,
            proxy=None,
        ) as ws:
            greeting_raw = await asyncio.wait_for(
                ws.recv(), timeout=self.request_timeout_s
            )
            greeting = json.loads(greeting_raw)
            if greeting.get("type") != "auth_required":
                raise RuntimeError(
                    f"Unexpected HA WS greeting: {greeting.get('type')!r}"
                )

            await asyncio.wait_for(
                ws.send(json.dumps({"type": "auth", "access_token": token})),
                timeout=self.request_timeout_s,
            )
            auth_raw = await asyncio.wait_for(
                ws.recv(), timeout=self.request_timeout_s
            )
            auth_resp = json.loads(auth_raw)
            auth_type = auth_resp.get("type")
            if auth_type == "auth_invalid":
                raise InvalidAuthTokenError("Home Assistant rejected Bearer token")
            if auth_type != "auth_ok":
                raise RuntimeError(f"Unexpected HA WS auth response: {auth_type!r}")

            await asyncio.wait_for(
                ws.send(json.dumps({"id": 1, "type": "auth/current_user"})),
                timeout=self.request_timeout_s,
            )
            user_raw = await asyncio.wait_for(
                ws.recv(), timeout=self.request_timeout_s
            )
            user_resp = json.loads(user_raw)
            if user_resp.get("success") is not True:
                raise RuntimeError("HA WS auth/current_user returned success=false")

            result = user_resp.get("result")
            if not isinstance(result, dict) or not result.get("id"):
                raise RuntimeError("HA WS auth/current_user returned invalid result")

            now = time.time()
            ttl = self.cache_ttl_s if self.cache_ttl_s > 0.0 else 30.0
            return HAUserPrincipal(
                user_id=str(result["id"]),
                name=str(result.get("name") or "Home Assistant User"),
                is_admin=bool(result.get("is_admin", False)),
                is_owner=bool(result.get("is_owner", False)),
                authenticated_at=now,
                expires_at=now + ttl,
            )

    async def _verify_via_rest(
        self, base_url: str, token: str, token_hash: str
    ) -> Optional[HAUserPrincipal]:
        async with httpx.AsyncClient(timeout=self.request_timeout_s) as client:
            resp = await client.get(
                f"{base_url}/api/",
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code in (401, 403):
            raise InvalidAuthTokenError("Home Assistant REST rejected Bearer token")
        if resp.status_code == 200:
            now = time.time()
            ttl = self.cache_ttl_s if self.cache_ttl_s > 0.0 else 30.0
            # Fail-closed: REST /api/ does not expose user roles/privileges.
            return HAUserPrincipal(
                user_id=f"ha_rest_{token_hash[:12]}",
                name="Home Assistant User",
                is_admin=False,
                is_owner=False,
                authenticated_at=now,
                expires_at=now + ttl,
            )
        return None

    async def verify_token(self, token: str) -> HAUserPrincipal:
        clean_token = (token or "").strip()
        if not clean_token:
            raise InvalidAuthTokenError("Empty Bearer token")

        token_hash = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()
        cached = self._get_cached_principal(token_hash)
        if cached is not None:
            return cached

        candidates = self._candidate_base_urls()
        if not candidates:
            raise HomeAssistantUnavailableError("No Home Assistant URL configured")

        last_err: Optional[Exception] = None

        # Primary: WebSocket auth/current_user
        for base_url in candidates:
            try:
                principal = await self._verify_via_websocket(base_url, clean_token)
                self._put_cached_principal(token_hash, principal)
                return principal
            except InvalidAuthTokenError:
                raise
            except (
                OSError,
                asyncio.TimeoutError,
                WebSocketException,
                json.JSONDecodeError,
                RuntimeError,
                ValueError,
            ) as exc:
                last_err = exc
                logger.warning(
                    "HA WS auth failed for %s (token=%s): %s",
                    base_url,
                    token_hash[:8],
                    exc,
                )

        # Fallback: Fail-closed REST GET /api/
        for base_url in candidates:
            try:
                principal = await self._verify_via_rest(
                    base_url, clean_token, token_hash
                )
                if principal is not None:
                    self._put_cached_principal(token_hash, principal)
                    return principal
            except InvalidAuthTokenError:
                raise
            except (httpx.HTTPError, OSError, asyncio.TimeoutError) as exc:
                last_err = exc
                logger.warning(
                    "HA REST auth fallback failed for %s (token=%s): %s",
                    base_url,
                    token_hash[:8],
                    exc,
                )

        raise HomeAssistantUnavailableError(
            f"Unable to reach Home Assistant for token {token_hash[:8]}: {last_err}"
        )

    def create_session_token(
        self, principal: HAUserPrincipal, ttl_s: Optional[float] = None
    ) -> tuple[str, float]:
        now = time.time()
        effective_ttl = self.session_ttl_s if ttl_s is None else max(0.0, float(ttl_s))
        expires_at = now + effective_ttl
        payload = {
            "v": 1,
            "sub": principal.user_id,
            "name": principal.name,
            "adm": bool(principal.is_admin),
            "own": bool(principal.is_owner),
            "iat": round(now, 3),
            "exp": round(expires_at, 3),
        }
        payload_bytes = json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        payload_b64 = _b64url_encode(payload_bytes)
        sig_digest = hmac.new(
            self._session_secret, payload_b64.encode("ascii"), hashlib.sha256
        ).digest()
        sig_b64 = _b64url_encode(sig_digest)
        return f"{payload_b64}.{sig_b64}", expires_at

    def verify_session_cookie(self, cookie_value: str) -> HAUserPrincipal:
        raw = (cookie_value or "").strip()
        if not raw or "." not in raw:
            raise InvalidSessionCookieError("Missing or malformed session cookie")
        parts = raw.split(".")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise InvalidSessionCookieError("Malformed session cookie structure")

        payload_b64, sig_b64 = parts
        expected_digest = hmac.new(
            self._session_secret, payload_b64.encode("ascii"), hashlib.sha256
        ).digest()
        expected_sig_b64 = _b64url_encode(expected_digest)
        if not hmac.compare_digest(sig_b64, expected_sig_b64):
            raise InvalidSessionCookieError("Invalid session cookie signature")

        try:
            payload_raw = _b64url_decode(payload_b64)
            payload = json.loads(payload_raw.decode("utf-8"))
        except Exception as exc:
            raise InvalidSessionCookieError("Corrupt session cookie payload") from exc

        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise InvalidSessionCookieError("Unsupported session cookie version")

        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub.strip():
            raise InvalidSessionCookieError("Session cookie missing subject")

        try:
            iat = float(payload["iat"])
            exp = float(payload["exp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidSessionCookieError("Session cookie missing timestamps") from exc

        if time.time() >= exp:
            raise InvalidSessionCookieError("Session cookie expired")

        return HAUserPrincipal(
            user_id=sub,
            name=str(payload.get("name") or "Home Assistant User"),
            is_admin=bool(payload.get("adm", False)),
            is_owner=bool(payload.get("own", False)),
            authenticated_at=iat,
            expires_at=exp,
        )


def _get_config_and_verifier(
    conn: HTTPConnection,
) -> tuple["SpatialServerConfig", HomeAssistantAuthVerifier]:
    config = getattr(conn.app.state, "config", None)
    if config is None:
        config = conn.app.state.pipeline.config
    verifier: HomeAssistantAuthVerifier = conn.app.state.auth_verifier
    return config, verifier


async def _resolve_credentials(
    cookies: Mapping[str, str],
    headers: Mapping[str, str],
    config: "SpatialServerConfig",
    verifier: HomeAssistantAuthVerifier,
) -> HAUserPrincipal:
    if not config.auth_required:
        return synthetic_local_admin_principal()

    cookie_val = cookies.get(SH3D_SESSION_COOKIE_NAME, "")
    if cookie_val:
        try:
            return verifier.verify_session_cookie(cookie_val)
        except InvalidSessionCookieError:
            # Allow stale/expired cookies to fall back to a fresh Bearer token.
            pass

    bearer = extract_bearer_token(headers)
    if bearer:
        return await verifier.verify_token(bearer)

    raise InvalidAuthTokenError("Missing or invalid credentials")


async def require_authenticated_user(request: Request) -> HAUserPrincipal:
    config, verifier = _get_config_and_verifier(request)
    try:
        return await _resolve_credentials(
            request.cookies, request.headers, config, verifier
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def require_admin_user(
    principal: HAUserPrincipal = Depends(require_authenticated_user),
) -> HAUserPrincipal:
    if not principal.is_privileged:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return principal


async def authenticate_websocket(websocket: WebSocket) -> Optional[HAUserPrincipal]:
    config, verifier = _get_config_and_verifier(websocket)
    try:
        return await _resolve_credentials(
            websocket.cookies, websocket.headers, config, verifier
        )
    except AuthError:
        return None
