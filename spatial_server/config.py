from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent

load_dotenv(REPO_ROOT / ".env")


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

    @classmethod
    def from_env(cls) -> "SpatialServerConfig":
        data_dir = BASE_DIR / "data"
        models_dir = BASE_DIR / "models"
        data_dir.mkdir(parents=True, exist_ok=True)
        models_dir.mkdir(parents=True, exist_ok=True)

        return cls(
            host=os.getenv("SPATIAL_SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SPATIAL_SERVER_PORT", "8765")),
            manifest_path=REPO_ROOT / "public" / "models" / "scene_manifest.json",
            glb_path=REPO_ROOT / "public" / "models" / "house_optimized.glb",
            sqlite_db_path=data_dir / "spatial_tracks.db",
            calibration_override_path=data_dir / "camera_calibrations.json",
            data_dir=data_dir,
            models_dir=models_dir,
            default_ingestion_mode=(os.getenv("CV_INGESTION_MODE") or os.getenv("SPATIAL_INGESTION_MODE") or "synthetic").lower(),
            go2rtc_rtsp_url=os.getenv("GO2RTC_RTSP_CARRAIO_SUB", "rtsp://127.0.0.1:8554/carraio_sub"),
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
        )

