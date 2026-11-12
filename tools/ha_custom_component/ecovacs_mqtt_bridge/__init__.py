"""
Ecovacs MQTT Telemetry Bridge per Home Assistant (DEEBOT X1 TURBO)
===================================================================
Estrae in tempo reale e a latenza zero le coordinate vettoriali (LiDAR dToF)
dalla mappa attiva in memoria dell'integrazione ufficiale Ecovacs (`image.deebot_map`),
senza inviare comandi invasivi al cloud Ecovacs che rischierebbero disconnessioni.

Pubblica su MQTT: homeassistant/deebot/pose
"""

import asyncio
import json
import logging
import math
import re
import time
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ecovacs_mqtt_bridge"
TOPIC = "homeassistant/deebot/pose"

# Pattern per estrarre le coordinate vettoriali dell'SVG
# #d = Robot Deebot, #c = Base di ricarica (Charger)
ROBOT_PATTERN = re.compile(r'<use\s+href="#d"\s+x="([^"]+)"\s+y="([^"]+)"')
DOCK_PATTERN = re.compile(r'<use\s+href="#c"\s+x="([^"]+)"\s+y="([^"]+)"')


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Inizializzazione del componente all'avvio di Home Assistant."""
    _LOGGER.info("[Ecovacs MQTT Bridge] Avvio servizio telemetria MQTT per Deebot...")

    # Stato interno per tracciamento coordinate e angolo
    last_pose = {
        "x": 0.0,
        "y": 0.0,
        "angle": 0.0,
        "dock_x": 0.0,
        "dock_y": 0.0,
        "timestamp": 0,
    }

    async def _publish_mqtt(payload_dict):
        """Pubblica in modo asincrono sul broker MQTT."""
        try:
            from homeassistant.components import mqtt
            await mqtt.async_publish(
                hass,
                TOPIC,
                json.dumps(payload_dict),
                qos=0,
                retain=False,
            )
        except Exception:
            try:
                await hass.services.async_call(
                    "mqtt",
                    "publish",
                    {
                        "topic": TOPIC,
                        "payload": json.dumps(payload_dict),
                        "qos": 0,
                        "retain": False,
                    },
                )
            except Exception as err:
                _LOGGER.warning("[Ecovacs MQTT Bridge] Errore pubblicazione MQTT: %s", err)

    def _process_svg(svg_content: str, source_label: str = "map"):
        """Estrae le coordinate dall'SVG vettoriale e pubblica su MQTT."""
        if not svg_content:
            return

        m_rob = ROBOT_PATTERN.search(svg_content)
        m_dock = DOCK_PATTERN.search(svg_content)

        if not m_rob:
            return

        try:
            svg_rx = float(m_rob.group(1))
            svg_ry = float(m_rob.group(2))

            # Fattore di scala matematico: 1 unità SVG = 50 mm reali
            # L'asse Y SVG è invertito rispetto al sistema cartesiano del robot
            rx = round(svg_rx * 50.0, 1)
            ry = round(-svg_ry * 50.0, 1)

            cx, cy = last_pose["dock_x"], last_pose["dock_y"]
            if m_dock:
                cx = round(float(m_dock.group(1)) * 50.0, 1)
                cy = round(-float(m_dock.group(2)) * 50.0, 1)
                last_pose["dock_x"] = cx
                last_pose["dock_y"] = cy

            # Calcolo dinamico dell'angolo di prua se il robot si è spostato (> 40 mm)
            dx = rx - last_pose["x"]
            dy = ry - last_pose["y"]
            dist = math.hypot(dx, dy)

            current_angle = last_pose["angle"]
            if dist > 40.0:
                current_angle = round(math.degrees(math.atan2(dy, dx)), 1)
                last_pose["angle"] = current_angle

            last_pose["x"] = rx
            last_pose["y"] = ry
            last_pose["timestamp"] = int(time.time())

            vac_entity = hass.states.get("vacuum.deebot")
            vac_state = vac_entity.state if vac_entity else "cleaning"

            payload = {
                "timestamp": int(time.time()),
                "device": "DEEBOT X1 TURBO",
                "state": vac_state,
                "robot": {
                    "x": rx,
                    "y": ry,
                    "angle": current_angle,
                },
                "dock": {
                    "x": cx,
                    "y": cy,
                },
            }

            _LOGGER.info(
                "[Ecovacs MQTT Bridge] Pose live -> X: %.1f mm, Y: %.1f mm, Angolo: %.1f° (stato: %s)",
                rx,
                ry,
                current_angle,
                vac_state,
            )

            # Invia subito su MQTT
            if hass.loop.is_running():
                hass.loop.call_soon_threadsafe(
                    lambda: hass.async_create_task(_publish_mqtt(payload))
                )
        except Exception as err:
            _LOGGER.debug("[Ecovacs MQTT Bridge] Errore calcolo coordinate SVG: %s", err)

    async def _get_svg_from_ha() -> str | None:
        """Legge l'SVG della mappa direttamente dalla memoria di Home Assistant."""
        # 1. Prova tramite deebot_client device.map (zero overhead)
        for entry in hass.config_entries.async_entries("ecovacs"):
            controller = getattr(entry, "runtime_data", None)
            if controller and hasattr(controller, "devices"):
                for dev in controller.devices:
                    if hasattr(dev, "map") and hasattr(dev.map, "get_svg_map"):
                        try:
                            svg = dev.map.get_svg_map()
                            if svg:
                                return svg
                        except Exception:
                            pass

        # 2. Prova tramite ImageEntity
        try:
            image_comp = hass.data.get("entity_components", {}).get("image")
            if image_comp:
                entity = image_comp.get_entity("image.deebot_map")
                if entity and hasattr(entity, "async_image"):
                    raw_bytes = await entity.async_image()
                    if raw_bytes:
                        return raw_bytes.decode("utf-8")
        except Exception:
            pass

        return None

    # Callback attivata ogni volta che image.deebot_map si aggiorna nativamente
    async def _on_map_state_changed(event):
        svg = await _get_svg_from_ha()
        if svg:
            _process_svg(svg, "state_change")

    # Monitoraggio periodico ad alta frequenza (1 secondo) durante la pulizia
    async def _fast_monitor_loop():
        _LOGGER.info("[Ecovacs MQTT Bridge] Loop di campionamento in memoria avviato con successo.")
        while True:
            try:
                vac = hass.states.get("vacuum.deebot")
                st = vac.state if vac else "docked"

                if st in ("cleaning", "returning", "paused"):
                    svg = await _get_svg_from_ha()
                    if svg:
                        _process_svg(svg, "poll")
                    await asyncio.sleep(1.0)
                else:
                    # Quando è alla base a riposo: controlla ogni 10 secondi
                    await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.debug("[Ecovacs MQTT Bridge] Loop monitor: %s", e)
                await asyncio.sleep(2.0)

    async def _start_bridge(_=None):
        # Registra il listener sugli aggiornamenti dell'entità mappa
        async_track_state_change_event(hass, ["image.deebot_map"], _on_map_state_changed)

        # Avvia il loop di lettura in memoria
        hass.loop.create_task(_fast_monitor_loop())
        _LOGGER.info("[Ecovacs MQTT Bridge] Bridge operativo! Telemetria in streaming continuo su '%s'", TOPIC)

    async_call_later(hass, 2, _start_bridge)
    return True
