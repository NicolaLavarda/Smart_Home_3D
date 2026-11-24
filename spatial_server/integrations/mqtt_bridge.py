from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Optional

from spatial_server.config import SpatialServerConfig

logger = logging.getLogger("spatial_server.integrations.mqtt_bridge")

TOPIC_LATEST_EVENT_IMAGE = "sh3d/events/latest_annotated.jpg"
TOPIC_ALARM_STATE = "sh3d/entity/allarme/state"
TOPIC_ALARM_SET = "sh3d/entity/allarme/set"


class HomeAssistantMqttBridge:
    """
    Optional MQTT Discovery bridge publishing:
    - `camera.sh3d_ultimo_evento` (annotated event JPEG bytes for Nest Hub / LG TV in LAN)
    - `select.sh3d_allarme` (two-way sync for `sh3d.allarme`)
    """

    def __init__(
        self,
        config: SpatialServerConfig,
        *,
        on_alarm_command: Optional[Callable[[str], Coroutine[Any, Any, Any]]] = None,
        initial_alarm_options: Optional[list[str]] = None,
        initial_alarm_state: str = "Spento",
    ) -> None:
        self.config = config
        self.on_alarm_command = on_alarm_command
        self.alarm_options = list(initial_alarm_options or ["Spento", "Silenzioso", "Acceso"])
        self.alarm_state = initial_alarm_state

        self._client: Any = None
        self._connected = False
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    def is_enabled(self) -> bool:
        return bool(self.config.ha_mqtt_bridge_enabled and (self.config.mqtt_host or "").strip())

    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        if self._running or not self.is_enabled():
            return
        self._running = True
        self._task = asyncio.create_task(self._mqtt_loop(), name="ha-mqtt-bridge")

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
        self._client = None

    async def publish_event_image(self, jpeg_bytes: bytes) -> bool:
        if not self._connected or self._client is None or not jpeg_bytes:
            return False
        try:
            await self._client.publish(TOPIC_LATEST_EVENT_IMAGE, payload=jpeg_bytes, qos=0, retain=True)
            return True
        except Exception as exc:
            logger.debug("MQTT publish_event_image failed: %s", exc)
            return False

    async def publish_alarm_state(self, state: str, options: Optional[list[str]] = None) -> bool:
        self.alarm_state = str(state)
        if options:
            self.alarm_options = list(options)
        if not self._connected or self._client is None:
            return False
        try:
            await self._client.publish(TOPIC_ALARM_STATE, payload=self.alarm_state, qos=1, retain=True)
            return True
        except Exception as exc:
            logger.debug("MQTT publish_alarm_state failed: %s", exc)
            return False

    async def _publish_discovery(self, client: Any) -> None:
        device_block = {
            "identifiers": ["smart_home_3d_spatial"],
            "name": "Smart Home 3D",
            "manufacturer": "Smart Home 3D",
            "model": "Spatial CV Engine",
        }
        cam_cfg = {
            "name": "Ultimo Evento 3D",
            "unique_id": "sh3d_ultimo_evento_camera",
            "topic": TOPIC_LATEST_EVENT_IMAGE,
            "device": device_block,
        }
        alarm_cfg = {
            "name": "Allarme Casa 3D",
            "unique_id": "sh3d_allarme_select",
            "state_topic": TOPIC_ALARM_STATE,
            "command_topic": TOPIC_ALARM_SET,
            "options": self.alarm_options,
            "icon": "mdi:shield-home",
            "device": device_block,
        }
        await client.publish(
            "homeassistant/camera/smart_home_3d/ultimo_evento/config",
            payload=json.dumps(cam_cfg),
            qos=1,
            retain=True,
        )
        await client.publish(
            "homeassistant/select/smart_home_3d/allarme/config",
            payload=json.dumps(alarm_cfg),
            qos=1,
            retain=True,
        )
        await client.publish(TOPIC_ALARM_STATE, payload=self.alarm_state, qos=1, retain=True)

    async def _mqtt_loop(self) -> None:
        import aiomqtt

        backoff = 3.0
        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=self.config.mqtt_host,
                    port=int(self.config.mqtt_port),
                    username=self.config.mqtt_user or None,
                    password=self.config.mqtt_password or None,
                ) as client:
                    self._client = client
                    self._connected = True
                    backoff = 3.0
                    await self._publish_discovery(client)
                    await client.subscribe(TOPIC_ALARM_SET)
                    async for message in client.messages:
                        if not self._running:
                            break
                        if str(message.topic) == TOPIC_ALARM_SET:
                            cmd = message.payload.decode("utf-8", errors="ignore").strip()
                            if cmd and self.on_alarm_command is not None:
                                await self.on_alarm_command(cmd)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("HomeAssistantMqttBridge reconnect (%s): %s", self.config.mqtt_host, exc)
            finally:
                self._connected = False
                self._client = None

            if not self._running:
                break
            await asyncio.sleep(backoff)
            backoff = min(30.0, backoff * 1.8)
