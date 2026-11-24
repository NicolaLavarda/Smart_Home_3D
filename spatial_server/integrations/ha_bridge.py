from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Optional

import httpx
import websockets

from spatial_server.config import SpatialServerConfig, _normalize_ha_url

logger = logging.getLogger("spatial_server.integrations.ha_bridge")

_ACTION_DOMAIN_PREFIXES = ("switch.", "light.", "lock.", "cover.", "script.", "button.")


def _http_to_ws(base_url: str) -> str:
    if base_url.lower().startswith("https://"):
        return "wss://" + base_url[8:] + "/api/websocket"
    return "ws://" + base_url[7:] + "/api/websocket"


class HomeAssistantBridgeService:
    """
    Persistent H24 backend-to-backend bridge to Home Assistant:
    - Maintains an authenticated WebSocket connection (`HA_TOKEN`) even when all browsers are closed.
    - Mirrors HA entity states into `AutomationEngineService` in real time.
    - Auto-discovers `notify.*`, `media_player.*`, `tts.*`, and controllable action entities.
    - Executes `call_service` via persistent `httpx.AsyncClient` (zero duplicate browser calls).
    - Listens for `mobile_app_notification_action` events from phone notification buttons.
    """

    def __init__(
        self,
        config: SpatialServerConfig,
        *,
        on_states_batch: Optional[Callable[[dict[str, dict[str, Any]], bool], Coroutine[Any, Any, Any]]] = None,
        on_notification_action: Optional[Callable[[str, dict[str, Any]], Coroutine[Any, Any, Any]]] = None,
        http_transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.config = config
        self.on_states_batch = on_states_batch
        self.on_notification_action = on_notification_action

        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(4.5, connect=1.2),
            limits=httpx.Limits(max_connections=6, max_keepalive_connections=4),
            transport=http_transport,
        )
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._connected = False
        self._active_base_url: str = ""
        self._last_error: Optional[str] = None

        self._notify_services: list[dict[str, str]] = []
        self._media_players: list[dict[str, str]] = []
        self._tts_entities: list[dict[str, str]] = []
        self._action_entities: list[dict[str, str]] = []
        self._states_snapshot: dict[str, dict[str, Any]] = {}

    def _candidate_base_urls(self) -> list[str]:
        candidates: list[str] = []
        for raw in (self.config.ha_local_url, self.config.ha_tailscale_url, self.config.ha_public_url):
            clean = _normalize_ha_url(raw)
            if clean.lower().startswith(("http://", "https://")) and clean not in candidates:
                candidates.append(clean)
        return candidates

    def has_backend_token(self) -> bool:
        return bool((self.config.ha_token or "").strip())

    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        if self._running:
            return
        if not self.config.ha_bridge_enabled or not self.has_backend_token() or not self._candidate_base_urls():
            logger.info(
                "HomeAssistantBridgeService in standby (enabled=%s, token=%s, urls=%d)",
                self.config.ha_bridge_enabled,
                self.has_backend_token(),
                len(self._candidate_base_urls()),
            )
            return
        self._running = True
        self._task = asyncio.create_task(self._ws_loop(), name="ha-bridge-ws")

    async def stop(self) -> None:
        self._running = False
        self._connected = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._http_client.aclose()

    def parse_services_and_states(
        self,
        services_payload: Optional[dict[str, Any]],
        states_payload: Optional[list[dict[str, Any]]],
    ) -> None:
        if isinstance(services_payload, dict):
            notify_block = services_payload.get("notify") or {}
            notifies: list[dict[str, str]] = []
            for svc_name, meta in sorted(notify_block.items()):
                clean_svc = str(svc_name or "").strip()
                if not clean_svc or clean_svc in ("send_message", "persistent_notification"):
                    continue
                lower = clean_svc.lower()
                if lower.startswith("mobile_app_"):
                    kind = "mobile_app"
                    friendly = clean_svc[len("mobile_app_") :].replace("_", " ").title()
                elif "tv" in lower or "webos" in lower:
                    kind = "tv"
                    friendly = clean_svc.replace("_", " ").title()
                else:
                    kind = "other"
                    friendly = (meta.get("name") if isinstance(meta, dict) else None) or clean_svc.replace("_", " ").title()
                notifies.append(
                    {
                        "service": f"notify.{clean_svc}",
                        "name": str(friendly),
                        "kind": kind,
                    }
                )
            self._notify_services = notifies

        if isinstance(states_payload, list):
            players: list[dict[str, str]] = []
            tts_list: list[dict[str, str]] = []
            actions: list[dict[str, str]] = []
            snap_map: dict[str, dict[str, Any]] = {}

            for st in states_payload:
                if not isinstance(st, dict):
                    continue
                eid = str(st.get("entity_id") or "").strip()
                if not eid:
                    continue
                state_val = str(st.get("state") if st.get("state") is not None else "unknown")
                attrs = st.get("attributes") if isinstance(st.get("attributes"), dict) else {}
                snap_map[eid] = {"state": state_val, "attributes": attrs}
                fname = str(attrs.get("friendly_name") or eid)

                if eid.startswith("media_player."):
                    players.append({"entity_id": eid, "name": fname, "state": state_val})
                elif eid.startswith("tts."):
                    tts_list.append({"entity_id": eid, "name": fname})
                elif eid.startswith(_ACTION_DOMAIN_PREFIXES):
                    actions.append({"entity_id": eid, "name": fname, "state": state_val})

            self._states_snapshot = snap_map
            self._media_players = sorted(players, key=lambda x: x["name"].lower())
            self._tts_entities = sorted(tts_list, key=lambda x: x["name"].lower())
            self._action_entities = sorted(actions, key=lambda x: x["entity_id"].lower())

    def get_discovery_summary(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "has_backend_token": self.has_backend_token(),
            "ha_base_url": self._active_base_url or (self._candidate_base_urls()[0] if self._candidate_base_urls() else ""),
            "last_error": self._last_error,
            "notify_services": list(self._notify_services),
            "media_players": list(self._media_players),
            "tts_entities": list(self._tts_entities),
            "action_entities": list(self._action_entities),
        }

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any],
    ) -> tuple[bool, str]:
        token = (self.config.ha_token or "").strip()
        bases = self._candidate_base_urls()
        if not token or not bases:
            return False, "HA_TOKEN o URL Home Assistant non configurati"

        ordered_bases = list(bases)
        if self._active_base_url and self._active_base_url in ordered_bases:
            ordered_bases.remove(self._active_base_url)
            ordered_bases.insert(0, self._active_base_url)

        last_err = "Home Assistant non raggiungibile"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        for base in ordered_bases:
            url = f"{base}/api/services/{domain}/{service}"
            try:
                resp = await self._http_client.post(url, json=service_data or {}, headers=headers)
                if 200 <= resp.status_code < 300:
                    return True, f"Eseguito su Home Assistant ({base})"
                last_err = f"HTTP {resp.status_code} su {base}"
            except Exception as exc:
                last_err = f"{type(exc).__name__} ({base})"
        return False, last_err

    async def handle_notification_action_event(self, event_data: dict[str, Any]) -> None:
        action_name = str((event_data or {}).get("action") or "").strip()
        if not action_name:
            return
        logger.info("Received HA mobile_app_notification_action: %s", action_name)
        if self.on_notification_action is not None:
            try:
                await self.on_notification_action(action_name, dict(event_data or {}))
            except Exception as exc:
                logger.warning("Notification action handler error (%s): %s", action_name, exc)

    async def _ws_loop(self) -> None:
        backoff = 2.0
        while self._running:
            bases = self._candidate_base_urls()
            if not bases:
                await asyncio.sleep(5.0)
                continue

            connected_this_round = False
            for base in bases:
                if not self._running:
                    break
                ws_url = _http_to_ws(base)
                try:
                    async with websockets.connect(ws_url, open_timeout=4.0, ping_interval=25.0, ping_timeout=15.0) as ws:
                        raw_hello = await asyncio.wait_for(ws.recv(), timeout=4.0)
                        hello = json.loads(raw_hello)
                        if hello.get("type") != "auth_required":
                            continue

                        await ws.send(json.dumps({"type": "auth", "access_token": self.config.ha_token}))
                        raw_auth = await asyncio.wait_for(ws.recv(), timeout=4.0)
                        auth_res = json.loads(raw_auth)
                        if auth_res.get("type") != "auth_ok":
                            self._last_error = f"Auth HA rifiutata su {base}"
                            continue

                        self._connected = True
                        self._active_base_url = base
                        self._last_error = None
                        connected_this_round = True
                        backoff = 2.0
                        logger.info("HomeAssistantBridgeService connesso a %s", base)

                        await ws.send(json.dumps({"id": 1, "type": "get_states"}))
                        await ws.send(json.dumps({"id": 2, "type": "get_services"}))
                        await ws.send(json.dumps({"id": 3, "type": "subscribe_events", "event_type": "state_changed"}))
                        await ws.send(json.dumps({"id": 4, "type": "subscribe_events", "event_type": "mobile_app_notification_action"}))

                        states_cache: Optional[list[dict[str, Any]]] = None
                        services_cache: Optional[dict[str, Any]] = None

                        async for raw_msg in ws:
                            if not self._running:
                                break
                            msg = json.loads(raw_msg)
                            mtype = msg.get("type")
                            if mtype == "result" and msg.get("success"):
                                req_id = msg.get("id")
                                if req_id == 1:
                                    states_cache = msg.get("result") or []
                                    self.parse_services_and_states(services_cache, states_cache)
                                    if self.on_states_batch is not None and self._states_snapshot:
                                        await self.on_states_batch(self._states_snapshot, False)
                                elif req_id == 2:
                                    services_cache = msg.get("result") or {}
                                    self.parse_services_and_states(services_cache, states_cache)
                            elif mtype == "event":
                                ev = msg.get("event") or {}
                                ev_type = ev.get("event_type")
                                data = ev.get("data") or {}
                                if ev_type == "state_changed":
                                    eid = str(data.get("entity_id") or "").strip()
                                    new_st = data.get("new_state")
                                    if eid and isinstance(new_st, dict):
                                        payload = {
                                            "state": str(new_st.get("state") if new_st.get("state") is not None else "unknown"),
                                            "attributes": new_st.get("attributes") if isinstance(new_st.get("attributes"), dict) else {},
                                        }
                                        self._states_snapshot[eid] = payload
                                        if self.on_states_batch is not None:
                                            await self.on_states_batch({eid: payload}, True)
                                elif ev_type == "mobile_app_notification_action":
                                    await self.handle_notification_action_event(data)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._last_error = f"{type(exc).__name__}: {exc}"
                finally:
                    self._connected = False

            if not self._running:
                break
            await asyncio.sleep(2.0 if connected_this_round else backoff)
            backoff = min(30.0, backoff * 1.8)
