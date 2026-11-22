from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

load_dotenv(REPO_ROOT / ".env")

logger = logging.getLogger("spatial_server.config")

DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:8765",
    "http://127.0.0.1:8765",
)


def _normalize_ha_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        return ""
    if url.lower().startswith("ws://"):
        url = "http://" + url[5:]
    elif url.lower().startswith("wss://"):
        url = "https://" + url[6:]
    if url.lower().endswith("/api/websocket"):
        url = url[:-14]
    elif url.lower().endswith("/api/websocket/"):
        url = url[:-15]
    return url.rstrip("/")


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    norm = raw.strip().lower()
    if norm in ("1", "true", "yes", "on"):
        return True
    if norm in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"Invalid boolean value for {name}: {raw!r}")


def _extract_origin(raw: str) -> str:
    cleaned = (raw or "").strip()
    if not cleaned or cleaned == "*":
        return ""
    parsed = urlsplit(cleaned)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return f"{scheme}://{parsed.netloc}"


def _derive_ha_public_origins(ha_public_url: str) -> list[str]:
    derived: list[str] = []
    origin = _extract_origin(ha_public_url)
    if not origin:
        return derived
    derived.append(origin)
    parsed = urlsplit(origin)
    hostname = (parsed.hostname or "").lower()
    if hostname.endswith(".ts.net") and parsed.port is not None:
        base_443 = f"{parsed.scheme}://{hostname}"
        if base_443 not in derived:
            derived.append(base_443)
    return derived


def _parse_allowed_origins(raw: str, ha_public_url: str = "") -> tuple[str, ...]:
    origins: list[str] = []
    cleaned_raw = (raw or "").strip()
    if cleaned_raw:
        for item in cleaned_raw.split(","):
            if item.strip() == "*":
                logger.warning("Ignoring wildcard '*' in SPATIAL_ALLOWED_ORIGINS")
                continue
            origin = _extract_origin(item)
            if origin and origin not in origins:
                origins.append(origin)
        if origins:
            return tuple(origins)

    for origin in DEFAULT_ALLOWED_ORIGINS:
        if origin not in origins:
            origins.append(origin)
    for origin in _derive_ha_public_origins(ha_public_url):
        if origin not in origins:
            origins.append(origin)
    return tuple(origins)


def _parse_camera_streams(raw: str) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for item in (raw or "").split(","):
        cleaned = item.strip()
        if not cleaned or "=" not in cleaned:
            continue
        cam_id, rtsp_url = cleaned.split("=", 1)
        cam_id = cam_id.strip()
        rtsp_url = rtsp_url.strip()
        if cam_id and rtsp_url:
            pairs.append((cam_id, rtsp_url))
    return tuple(pairs)


@dataclass(frozen=True)
class SpatialServerConfig:
    host: str
    port: int
    manifest_path: Path
    glb_path: Path
    sqlite_db_path: Path
    calibration_override_path: Path
    data_dir: Path
    models_dir: Path
    default_ingestion_mode: str
    go2rtc_rtsp_url: str
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str
    mqtt_password: str
    mqtt_topic_prefix: str
    openvino_device: str
    openvino_model_path: str
    db_retention_days: int
    face_webhook_url: str
    ha_tailscale_url: str = ""
    ha_local_url: str = ""
    ha_token: str = ""
    openvino_target_fps: float = 7.0
    openvino_conf_threshold: float = 0.35
    persist_min_displacement_m: float = 0.15
    persist_heartbeat_s: float = 10.0
    ha_public_url: str = ""
    auth_required: bool = True
    auth_cache_ttl_s: float = 120.0
    session_secret_key: str = ""
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS
    nvr_storage_dir: Optional[Path] = None
    go2rtc_rtsp_base_url: str = "rtsp://127.0.0.1:8554"
    openvino_camera_streams: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_env(cls) -> "SpatialServerConfig":
        data_dir = BASE_DIR / "data"
        models_dir = BASE_DIR / "models"
        data_dir.mkdir(parents=True, exist_ok=True)
        models_dir.mkdir(parents=True, exist_ok=True)

        ha_public_url = _normalize_ha_url(
            os.getenv("VITE_HA_PUBLIC_URL") or os.getenv("HA_PUBLIC_URL", "")
        )
        host = (os.getenv("SPATIAL_SERVER_HOST") or "127.0.0.1").strip() or "127.0.0.1"
        auth_required = _parse_bool_env("SPATIAL_AUTH_REQUIRED", True)
        auth_cache_ttl_s = max(0.0, float(os.getenv("SPATIAL_AUTH_CACHE_TTL_S", "120.0")))
        session_secret_key = os.getenv("SPATIAL_SESSION_SECRET", "").strip()
        allowed_origins = _parse_allowed_origins(
            os.getenv("SPATIAL_ALLOWED_ORIGINS", ""),
            ha_public_url=ha_public_url,
        )
        raw_nvr_dir = (os.getenv("SPATIAL_NVR_STORAGE_DIR") or "").strip()
        nvr_storage_dir = Path(raw_nvr_dir) if raw_nvr_dir else None
        go2rtc_rtsp_url = os.getenv("GO2RTC_RTSP_CARRAIO_SUB", "rtsp://127.0.0.1:8554/carraio_sub")
        go2rtc_rtsp_base_url = (os.getenv("GO2RTC_RTSP_BASE_URL") or "").strip()
        if not go2rtc_rtsp_base_url:
            parsed_rtsp = urlsplit(go2rtc_rtsp_url)
            if parsed_rtsp.scheme and parsed_rtsp.netloc:
                go2rtc_rtsp_base_url = f"{parsed_rtsp.scheme}://{parsed_rtsp.netloc}"
            else:
                go2rtc_rtsp_base_url = "rtsp://127.0.0.1:8554"
        openvino_camera_streams = _parse_camera_streams(os.getenv("OPENVINO_CAMERA_STREAMS", ""))

        return cls(
            host=host,
            port=int(os.getenv("SPATIAL_SERVER_PORT", "8765")),
            manifest_path=REPO_ROOT / "public" / "models" / "scene_manifest.json",
            glb_path=REPO_ROOT / "public" / "models" / "house_optimized.glb",
            sqlite_db_path=data_dir / "spatial_tracks.db",
            calibration_override_path=data_dir / "camera_calibrations.json",
            data_dir=data_dir,
            models_dir=models_dir,
            default_ingestion_mode=(os.getenv("CV_INGESTION_MODE") or os.getenv("SPATIAL_INGESTION_MODE") or "synthetic").lower(),
            go2rtc_rtsp_url=go2rtc_rtsp_url,
            mqtt_host=os.getenv("MQTT_BROKER_HOST") or os.getenv("MQTT_HOST", "192.168.86.24"),
            mqtt_port=int(os.getenv("MQTT_BROKER_PORT") or os.getenv("MQTT_PORT", "1883")),
            mqtt_user=os.getenv("MQTT_USER", ""),
            mqtt_password=os.getenv("MQTT_PASS") or os.getenv("MQTT_PASSWORD", ""),
            mqtt_topic_prefix=os.getenv("MQTT_FRIGATE_TOPIC") or (f"{os.getenv('MQTT_TOPIC_PREFIX')}/events" if os.getenv("MQTT_TOPIC_PREFIX") else "frigate/events"),
            openvino_device=os.getenv("OPENVINO_DEVICE", "AUTO"),
            openvino_model_path=os.getenv("OPENVINO_YOLO_MODEL", str(models_dir / "yolov8n_openvino_model")),
            db_retention_days=int(os.getenv("SPATIAL_RETENTION_DAYS", "30")),
            face_webhook_url=os.getenv("FACE_RECOGNITION_WEBHOOK_URL", ""),
            ha_tailscale_url=_normalize_ha_url(os.getenv("VITE_HA_TAILSCALE_URL") or os.getenv("VITE_HA_REMOTE_URL", "")),
            ha_local_url=_normalize_ha_url(os.getenv("VITE_HA_LOCAL_URL") or os.getenv("VITE_HA_URL", "")),
            ha_token=(os.getenv("VITE_HA_TOKEN") or os.getenv("HA_TOKEN", "")).strip(),
            openvino_target_fps=float(os.getenv("OPENVINO_FPS_LIMIT", "7.0")),
            openvino_conf_threshold=float(os.getenv("OPENVINO_CONF_THRESHOLD", "0.35")),
            persist_min_displacement_m=float(os.getenv("SPATIAL_PERSIST_MIN_DISPLACEMENT_M", "0.15")),
            persist_heartbeat_s=float(os.getenv("SPATIAL_PERSIST_HEARTBEAT_S", "10.0")),
            ha_public_url=ha_public_url,
            auth_required=auth_required,
            auth_cache_ttl_s=auth_cache_ttl_s,
            session_secret_key=session_secret_key,
            allowed_origins=allowed_origins,
            nvr_storage_dir=nvr_storage_dir,
            go2rtc_rtsp_base_url=go2rtc_rtsp_base_url,
            openvino_camera_streams=openvino_camera_streams,
        )

