from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit
from dotenv import load_dotenv

from spatial_server.domain.models import ClassReconstructionRule, SpatialReconstructionPolicy

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


def _parse_biometrics_camera_rules(raw: str) -> tuple[tuple[str, str, float], ...]:
    rules: list[tuple[str, str, float]] = []
    for item in (raw or "").split(","):
        cleaned = item.strip()
        if not cleaned or ":" not in cleaned or "=" not in cleaned:
            continue
        cam_part, rest = cleaned.split(":", 1)
        mod_part, range_part = rest.split("=", 1)
        cam_id = cam_part.strip()
        modality = mod_part.strip().lower()
        if not cam_id or modality not in ("face", "alpr"):
            continue
        try:
            max_range_m = float(range_part.strip())
        except ValueError:
            continue
        if max_range_m > 0.0:
            rules.append((cam_id, modality, max_range_m))
    return tuple(rules)


def _parse_nvr_trigger_classes(raw: str) -> tuple[str, ...]:
    classes: list[str] = []
    for item in (raw or "").split(","):
        cleaned = item.strip().lower()
        if cleaned and cleaned not in classes:
            classes.append(cleaned)
    return tuple(classes) if classes else ("person", "car", "truck", "motorbike")


def _parse_nvr_clock_offsets(raw: str) -> tuple[tuple[str, str, float], ...]:
    offsets: list[tuple[str, str, float]] = []
    for item in (raw or "").split(","):
        cleaned = item.strip()
        if not cleaned or ":" not in cleaned or "=" not in cleaned:
            continue
        cam_part, rest = cleaned.split(":", 1)
        tier_part, val_part = rest.split("=", 1)
        cam_id = cam_part.strip()
        tier = tier_part.strip().lower()
        if not cam_id or tier not in ("sub", "main"):
            continue
        try:
            offset_ms = float(val_part.strip())
        except ValueError:
            continue
        offsets.append((cam_id, tier, offset_ms))
    return tuple(offsets)


def _parse_nvr_camera_streams(raw: str) -> tuple[tuple[str, str, str], ...]:
    streams: list[tuple[str, str, str]] = []
    for item in (raw or "").split(","):
        cleaned = item.strip()
        if not cleaned or "=" not in cleaned or "|" not in cleaned:
            continue
        cam_id, urls = cleaned.split("=", 1)
        sub_url, main_url = urls.split("|", 1)
        cam_id = cam_id.strip()
        sub_url = sub_url.strip()
        main_url = main_url.strip()
        if cam_id and (sub_url or main_url):
            streams.append((cam_id, sub_url, main_url))
    return tuple(streams)


def _sanitize_db_filename(raw: str, default: str = "nvr_index.db") -> str:
    candidate = Path((raw or "").strip()).name
    if not candidate or candidate in (".", ".."):
        return default
    if not all(ch.isalnum() or ch in "._-" for ch in candidate):
        return default
    return candidate


def _parse_optional_conf_env(name: str) -> Optional[float]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    return max(0.05, min(0.99, float(raw.strip())))


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
    openvino_cpu_threads: int = 2
    biometrics_enabled: bool = False
    biometrics_face_enabled: bool = True
    biometrics_alpr_enabled: bool = True
    biometrics_onnx_provider: str = "cpu"
    biometrics_onnx_intra_threads: int = 2
    biometrics_onnx_inter_threads: int = 1
    biometrics_queue_maxsize: int = 8
    biometrics_min_eval_interval_s: float = 0.6
    biometrics_max_attempts_per_track: int = 6
    biometrics_unknown_backoff_s: float = 4.0
    go2rtc_http_base_url: str = "http://127.0.0.1:1984"
    biometrics_snapshot_timeout_s: float = 2.5
    biometrics_panoramic_max_width: int = 3840
    biometrics_panoramic_edge_margin_u: float = 0.15
    biometrics_face_det_model: str = "det_500m.onnx"
    biometrics_face_rec_model: str = "w600k_mbf.onnx"
    biometrics_face_min_width_px: float = 48.0
    biometrics_face_min_laplacian: float = 35.0
    biometrics_face_max_yaw_ratio: float = 0.55
    biometrics_face_match_threshold: float = 0.45
    biometrics_face_margin_threshold: float = 0.08
    biometrics_face_consensus_k: int = 2
    biometrics_face_max_range_m: float = 8.0
    biometrics_alpr_det_model: str = "yolo-v9-t-384-license-plate-end2end"
    biometrics_alpr_ocr_model: str = "cct-xs-v2-global-model"
    biometrics_alpr_min_plate_width_px: float = 55.0
    biometrics_alpr_consensus_k: int = 2
    biometrics_alpr_max_range_m: float = 13.0
    biometrics_alpr_whitelist_max_dist: int = 1
    biometrics_crop_retention_days: int = 14
    biometrics_crop_max_mb: float = 250.0
    biometrics_data_dir: Optional[Path] = None
    biometrics_plates_whitelist_file: Optional[Path] = None
    biometrics_camera_rules: tuple[tuple[str, str, float], ...] = ()
    dev_mode: bool = False
    nvr_recorder_enabled: bool = False
    nvr_sub_segment_sec: float = 60.0
    nvr_main_pre_roll_sec: float = 10.0
    nvr_main_inertia_sec: float = 15.0
    nvr_main_max_clip_sec: float = 300.0
    nvr_ram_buffer_max_mb_per_cam: float = 48.0
    nvr_trigger_classes: tuple[str, ...] = ("person", "car", "truck", "motorbike")
    nvr_min_confidence: float = 0.55
    nvr_max_storage_gb: float = 0.0
    nvr_min_free_gb: float = 50.0
    nvr_sub_retention_days: int = 30
    nvr_main_retention_days: int = 60
    nvr_prune_interval_sec: float = 300.0
    nvr_index_db_name: str = "nvr_index.db"
    nvr_camera_clock_offsets: tuple[tuple[str, str, float], ...] = ()
    nvr_camera_streams: tuple[tuple[str, str, str], ...] = ()
    public_app_url: str = ""
    ha_bridge_enabled: bool = True
    ha_mqtt_bridge_enabled: bool = False
    events_inertia_s: float = 18.0
    events_pre_roll_s: float = 3.0
    events_retention_days: int = 30
    events_snapshot_max_mb: float = 400.0
    events_snapshot_max_width: int = 1280
    signed_media_ttl_s: int = 86400
    openvino_adaptive_fps_enabled: bool = True
    openvino_adaptive_idle_fps: float = 1.2
    openvino_adaptive_min_idle_fps: float = 1.0
    openvino_adaptive_max_person_fps: float = 5.0
    openvino_adaptive_max_vehicle_fps: float = 3.5
    openvino_adaptive_boost_hold_s: float = 5.0
    research_telemetry_enabled: Optional[bool] = None
    research_telemetry_max_mb: float = 250.0
    research_telemetry_retention_days: int = 7
    research_telemetry_save_crops: bool = True
    metrics_sample_interval_s: float = 2.0
    metrics_persist_interval_s: float = 15.0
    metrics_ram_window_s: float = 3600.0
    metrics_retention_days: int = 7
    metrics_ha_publish_interval_s: float = 15.0
    reconstruct_person: bool = True
    person_stationary_conf_threshold: Optional[float] = None
    person_moving_conf_threshold: Optional[float] = None
    person_min_speed_mps: float = 0.25
    reconstruct_vehicle: bool = True
    vehicle_stationary_conf_threshold: Optional[float] = None
    vehicle_moving_conf_threshold: Optional[float] = None
    vehicle_min_speed_mps: float = 0.35
    reconstruct_animal: bool = True
    animal_stationary_conf_threshold: Optional[float] = None
    animal_moving_conf_threshold: Optional[float] = None
    animal_min_speed_mps: float = 0.20

    def get_reconstruction_policy(self) -> SpatialReconstructionPolicy:
        """Build the per-category 3D reconstruction confidence & speed policy."""
        base_conf = max(0.05, min(0.99, float(self.openvino_conf_threshold)))

        def _make_rule(
            enabled: bool,
            stat_conf: Optional[float],
            mov_conf: Optional[float],
            min_speed: float,
        ) -> ClassReconstructionRule:
            eff_mov = base_conf if mov_conf is None else max(0.05, min(0.99, float(mov_conf)))
            eff_stat = base_conf if stat_conf is None else max(0.05, min(0.99, float(stat_conf)))
            return ClassReconstructionRule(
                enabled=bool(enabled),
                stationary_conf_threshold=eff_stat,
                moving_conf_threshold=eff_mov,
                min_speed_mps=max(0.0, float(min_speed)),
            )

        return SpatialReconstructionPolicy(
            person=_make_rule(
                self.reconstruct_person,
                self.person_stationary_conf_threshold,
                self.person_moving_conf_threshold,
                self.person_min_speed_mps,
            ),
            vehicle=_make_rule(
                self.reconstruct_vehicle,
                self.vehicle_stationary_conf_threshold,
                self.vehicle_moving_conf_threshold,
                self.vehicle_min_speed_mps,
            ),
            animal=_make_rule(
                self.reconstruct_animal,
                self.animal_stationary_conf_threshold,
                self.animal_moving_conf_threshold,
                self.animal_min_speed_mps,
            ),
            fallback_conf_threshold=base_conf,
        )

    @classmethod
    def from_env(cls) -> "SpatialServerConfig":
        data_dir = BASE_DIR / "data"
        models_dir = BASE_DIR / "models"
        data_dir.mkdir(parents=True, exist_ok=True)
        models_dir.mkdir(parents=True, exist_ok=True)

        dev_mode = _parse_bool_env("SH3D_DEV_MODE", False)
        ha_public_url = _normalize_ha_url(
            os.getenv("VITE_HA_PUBLIC_URL") or os.getenv("HA_PUBLIC_URL", "")
        )
        if dev_mode:
            dev_ha_url = _normalize_ha_url(os.getenv("VITE_HA_DEV_URL", ""))
            if dev_ha_url:
                ha_public_url = dev_ha_url
        host = (os.getenv("SPATIAL_SERVER_HOST") or "127.0.0.1").strip() or "127.0.0.1"
        auth_required = _parse_bool_env("SPATIAL_AUTH_REQUIRED", True)
        if dev_mode and (os.getenv("SPATIAL_DEV_AUTH_REQUIRED") or "").strip():
            auth_required = _parse_bool_env("SPATIAL_DEV_AUTH_REQUIRED", auth_required)
        auth_cache_ttl_s = max(0.0, float(os.getenv("SPATIAL_AUTH_CACHE_TTL_S", "120.0")))
        session_secret_key = os.getenv("SPATIAL_SESSION_SECRET", "").strip()
        allowed_origins = _parse_allowed_origins(
            os.getenv("SPATIAL_ALLOWED_ORIGINS", ""),
            ha_public_url=ha_public_url,
        )
        if dev_mode:
            merged_origins = list(allowed_origins)
            for dev_origin in DEFAULT_ALLOWED_ORIGINS:
                if dev_origin not in merged_origins:
                    merged_origins.append(dev_origin)
            allowed_origins = tuple(merged_origins)
        public_app_url = _normalize_ha_url(os.getenv("SPATIAL_PUBLIC_URL", ""))
        if not public_app_url:
            for orig in allowed_origins:
                parsed_orig = urlsplit(orig)
                orig_host = (parsed_orig.hostname or "").lower()
                if parsed_orig.scheme == "https" and orig_host not in ("localhost", "127.0.0.1"):
                    public_app_url = orig.rstrip("/")
                    break
        if not public_app_url and ha_public_url:
            parsed_ha = urlsplit(ha_public_url)
            ha_host = (parsed_ha.hostname or "").lower()
            if ha_host.endswith(".ts.net"):
                public_app_url = f"{parsed_ha.scheme}://{ha_host}"
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
        go2rtc_api_port = int(os.getenv("GO2RTC_API_PORT", "1984"))
        go2rtc_http_base_url = (
            (os.getenv("GO2RTC_HTTP_BASE_URL") or f"http://127.0.0.1:{go2rtc_api_port}").strip().rstrip("/")
        )
        raw_bio_data_dir = (os.getenv("BIOMETRICS_DATA_DIR") or "").strip()
        biometrics_data_dir = Path(raw_bio_data_dir) if raw_bio_data_dir else (data_dir / "biometrics")
        raw_plates_file = (os.getenv("BIOMETRICS_PLATES_WHITELIST_FILE") or "").strip()
        biometrics_plates_whitelist_file = (
            Path(raw_plates_file) if raw_plates_file else (biometrics_data_dir / "plates_whitelist.json")
        )
        default_ingestion_mode = (
            os.getenv("CV_INGESTION_MODE") or os.getenv("SPATIAL_INGESTION_MODE") or "synthetic"
        ).lower()
        if dev_mode and (os.getenv("CV_DEV_INGESTION_MODE") or "").strip():
            default_ingestion_mode = os.getenv("CV_DEV_INGESTION_MODE", "").strip().lower()
        biometrics_enabled = _parse_bool_env("BIOMETRICS_ENABLED", False)
        if dev_mode and (os.getenv("BIOMETRICS_DEV_ENABLED") or "").strip():
            biometrics_enabled = _parse_bool_env("BIOMETRICS_DEV_ENABLED", biometrics_enabled)

        raw_research_flag = (os.getenv("RESEARCH_TELEMETRY_ENABLED") or "").strip().lower()
        research_telemetry_enabled: Optional[bool]
        if raw_research_flag in ("", "auto"):
            research_telemetry_enabled = None
        else:
            research_telemetry_enabled = _parse_bool_env("RESEARCH_TELEMETRY_ENABLED", not dev_mode)

        return cls(
            host=host,
            port=int(os.getenv("SPATIAL_SERVER_PORT", "8765")),
            manifest_path=REPO_ROOT / "public" / "models" / "scene_manifest.json",
            glb_path=REPO_ROOT / "public" / "models" / "house_optimized.glb",
            sqlite_db_path=data_dir / "spatial_tracks.db",
            calibration_override_path=data_dir / "camera_calibrations.json",
            data_dir=data_dir,
            models_dir=models_dir,
            default_ingestion_mode=default_ingestion_mode,
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
            ha_token=(os.getenv("HA_TOKEN") or os.getenv("VITE_HA_TOKEN", "")).strip(),
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
            openvino_cpu_threads=max(1, int(os.getenv("OPENVINO_CPU_THREADS", "2"))),
            biometrics_enabled=biometrics_enabled,
            biometrics_face_enabled=_parse_bool_env("BIOMETRICS_FACE_ENABLED", True),
            biometrics_alpr_enabled=_parse_bool_env("BIOMETRICS_ALPR_ENABLED", True),
            biometrics_onnx_provider=(os.getenv("BIOMETRICS_ONNX_PROVIDER") or "cpu").strip().lower() or "cpu",
            biometrics_onnx_intra_threads=max(1, int(os.getenv("BIOMETRICS_ONNX_INTRA_THREADS", "2"))),
            biometrics_onnx_inter_threads=max(1, int(os.getenv("BIOMETRICS_ONNX_INTER_THREADS", "1"))),
            biometrics_queue_maxsize=max(1, int(os.getenv("BIOMETRICS_QUEUE_MAXSIZE", "8"))),
            biometrics_min_eval_interval_s=max(0.0, float(os.getenv("BIOMETRICS_MIN_EVAL_INTERVAL_S", "0.6"))),
            biometrics_max_attempts_per_track=max(1, int(os.getenv("BIOMETRICS_MAX_ATTEMPTS_PER_TRACK", "6"))),
            biometrics_unknown_backoff_s=max(0.5, float(os.getenv("BIOMETRICS_UNKNOWN_BACKOFF_S", "4.0"))),
            go2rtc_http_base_url=go2rtc_http_base_url,
            biometrics_snapshot_timeout_s=max(0.3, float(os.getenv("BIOMETRICS_SNAPSHOT_TIMEOUT_S", "2.5"))),
            biometrics_panoramic_max_width=max(640, int(os.getenv("BIOMETRICS_PANORAMIC_MAX_WIDTH", "3840"))),
            biometrics_panoramic_edge_margin_u=max(0.0, min(0.45, float(os.getenv("BIOMETRICS_PANORAMIC_EDGE_MARGIN_U", "0.15")))),
            biometrics_face_det_model=(os.getenv("BIOMETRICS_FACE_DET_MODEL") or "det_500m.onnx").strip() or "det_500m.onnx",
            biometrics_face_rec_model=(os.getenv("BIOMETRICS_FACE_REC_MODEL") or "w600k_mbf.onnx").strip() or "w600k_mbf.onnx",
            biometrics_face_min_width_px=max(16.0, float(os.getenv("BIOMETRICS_FACE_MIN_WIDTH_PX", "48.0"))),
            biometrics_face_min_laplacian=max(0.0, float(os.getenv("BIOMETRICS_FACE_MIN_LAPLACIAN", "35.0"))),
            biometrics_face_max_yaw_ratio=max(0.1, float(os.getenv("BIOMETRICS_FACE_MAX_YAW_RATIO", "0.55"))),
            biometrics_face_match_threshold=max(0.1, min(1.0, float(os.getenv("BIOMETRICS_FACE_MATCH_THRESHOLD", "0.45")))),
            biometrics_face_margin_threshold=max(0.0, min(1.0, float(os.getenv("BIOMETRICS_FACE_MARGIN_THRESHOLD", "0.08")))),
            biometrics_face_consensus_k=max(1, int(os.getenv("BIOMETRICS_FACE_CONSENSUS_K", "2"))),
            biometrics_face_max_range_m=max(1.0, float(os.getenv("BIOMETRICS_FACE_MAX_RANGE_M", "8.0"))),
            biometrics_alpr_det_model=(os.getenv("BIOMETRICS_ALPR_DET_MODEL") or "yolo-v9-t-384-license-plate-end2end").strip() or "yolo-v9-t-384-license-plate-end2end",
            biometrics_alpr_ocr_model=(os.getenv("BIOMETRICS_ALPR_OCR_MODEL") or "cct-xs-v2-global-model").strip() or "cct-xs-v2-global-model",
            biometrics_alpr_min_plate_width_px=max(16.0, float(os.getenv("BIOMETRICS_ALPR_MIN_PLATE_WIDTH_PX", "55.0"))),
            biometrics_alpr_consensus_k=max(1, int(os.getenv("BIOMETRICS_ALPR_CONSENSUS_K", "2"))),
            biometrics_alpr_max_range_m=max(1.0, float(os.getenv("BIOMETRICS_ALPR_MAX_RANGE_M", "13.0"))),
            biometrics_alpr_whitelist_max_dist=max(0, int(os.getenv("BIOMETRICS_ALPR_WHITELIST_MAX_DIST", "1"))),
            biometrics_crop_retention_days=max(1, int(os.getenv("BIOMETRICS_CROP_RETENTION_DAYS", "14"))),
            biometrics_crop_max_mb=max(1.0, float(os.getenv("BIOMETRICS_CROP_MAX_MB", "250.0"))),
            biometrics_data_dir=biometrics_data_dir,
            biometrics_plates_whitelist_file=biometrics_plates_whitelist_file,
            biometrics_camera_rules=_parse_biometrics_camera_rules(os.getenv("BIOMETRICS_CAMERA_RULES", "")),
            dev_mode=dev_mode,
            nvr_recorder_enabled=_parse_bool_env("SPATIAL_NVR_RECORDER_ENABLED", False),
            nvr_sub_segment_sec=max(10.0, float(os.getenv("SPATIAL_NVR_SUB_SEGMENT_SEC", "60.0"))),
            nvr_main_pre_roll_sec=max(0.0, min(60.0, float(os.getenv("SPATIAL_NVR_MAIN_PRE_ROLL_SEC", "10.0")))),
            nvr_main_inertia_sec=max(2.0, min(120.0, float(os.getenv("SPATIAL_NVR_MAIN_INERTIA_SEC", "15.0")))),
            nvr_main_max_clip_sec=max(30.0, float(os.getenv("SPATIAL_NVR_MAIN_MAX_CLIP_SEC", "300.0"))),
            nvr_ram_buffer_max_mb_per_cam=max(8.0, min(256.0, float(os.getenv("SPATIAL_NVR_RAM_BUFFER_MAX_MB_PER_CAM", "48.0")))),
            nvr_trigger_classes=_parse_nvr_trigger_classes(os.getenv("SPATIAL_NVR_TRIGGER_CLASSES", "person,car,truck,motorbike")),
            nvr_min_confidence=max(0.05, min(0.99, float(os.getenv("SPATIAL_NVR_MIN_CONFIDENCE", "0.55")))),
            nvr_max_storage_gb=max(0.0, float(os.getenv("SPATIAL_NVR_MAX_STORAGE_GB", "0.0"))),
            nvr_min_free_gb=max(1.0, float(os.getenv("SPATIAL_NVR_MIN_FREE_GB", "50.0"))),
            nvr_sub_retention_days=max(1, int(os.getenv("SPATIAL_NVR_SUB_RETENTION_DAYS", "30"))),
            nvr_main_retention_days=max(1, int(os.getenv("SPATIAL_NVR_MAIN_RETENTION_DAYS", "60"))),
            nvr_prune_interval_sec=max(10.0, float(os.getenv("SPATIAL_NVR_PRUNE_INTERVAL_SEC", "300.0"))),
            nvr_index_db_name=_sanitize_db_filename(os.getenv("SPATIAL_NVR_INDEX_DB_NAME", "nvr_index.db")),
            nvr_camera_clock_offsets=_parse_nvr_clock_offsets(os.getenv("SPATIAL_NVR_CAMERA_CLOCK_OFFSETS", "")),
            nvr_camera_streams=_parse_nvr_camera_streams(os.getenv("SPATIAL_NVR_CAMERA_STREAMS", "")),
            public_app_url=public_app_url,
            ha_bridge_enabled=_parse_bool_env("HA_BRIDGE_ENABLED", True),
            ha_mqtt_bridge_enabled=_parse_bool_env("HA_MQTT_BRIDGE_ENABLED", False),
            events_inertia_s=max(2.0, min(120.0, float(os.getenv("SPATIAL_EVENTS_INERTIA_S", "18.0")))),
            events_pre_roll_s=max(0.0, min(30.0, float(os.getenv("SPATIAL_EVENTS_PRE_ROLL_S", "3.0")))),
            events_retention_days=max(1, int(os.getenv("SPATIAL_EVENTS_RETENTION_DAYS", "30"))),
            events_snapshot_max_mb=max(10.0, float(os.getenv("SPATIAL_EVENTS_SNAPSHOT_MAX_MB", "400.0"))),
            events_snapshot_max_width=max(480, min(3840, int(os.getenv("SPATIAL_EVENTS_SNAPSHOT_MAX_WIDTH", "1280")))),
            signed_media_ttl_s=max(60, int(os.getenv("SPATIAL_SIGNED_MEDIA_TTL_S", "86400"))),
            openvino_adaptive_fps_enabled=_parse_bool_env("OPENVINO_ADAPTIVE_FPS_ENABLED", True),
            openvino_adaptive_idle_fps=max(0.5, float(os.getenv("OPENVINO_ADAPTIVE_IDLE_FPS", "1.2"))),
            openvino_adaptive_min_idle_fps=max(0.5, float(os.getenv("OPENVINO_ADAPTIVE_MIN_IDLE_FPS", "1.0"))),
            openvino_adaptive_max_person_fps=max(1.0, float(os.getenv("OPENVINO_ADAPTIVE_MAX_PERSON_FPS", "5.0"))),
            openvino_adaptive_max_vehicle_fps=max(1.0, float(os.getenv("OPENVINO_ADAPTIVE_MAX_VEHICLE_FPS", "3.5"))),
            openvino_adaptive_boost_hold_s=max(0.5, float(os.getenv("OPENVINO_ADAPTIVE_BOOST_HOLD_S", "5.0"))),
            research_telemetry_enabled=research_telemetry_enabled,
            research_telemetry_max_mb=max(20.0, float(os.getenv("RESEARCH_TELEMETRY_MAX_MB", "250.0"))),
            research_telemetry_retention_days=max(1, int(os.getenv("RESEARCH_TELEMETRY_RETENTION_DAYS", "7"))),
            research_telemetry_save_crops=_parse_bool_env("RESEARCH_TELEMETRY_SAVE_CROPS", True),
            metrics_sample_interval_s=max(1.0, float(os.getenv("SPATIAL_METRICS_SAMPLE_INTERVAL_S", "2.0"))),
            metrics_persist_interval_s=max(2.0, float(os.getenv("SPATIAL_METRICS_PERSIST_INTERVAL_S", "15.0"))),
            metrics_ram_window_s=max(60.0, float(os.getenv("SPATIAL_METRICS_RAM_WINDOW_S", "3600.0"))),
            metrics_retention_days=max(1, int(os.getenv("SPATIAL_METRICS_RETENTION_DAYS", "7"))),
            metrics_ha_publish_interval_s=max(0.0, float(os.getenv("SPATIAL_METRICS_HA_PUBLISH_INTERVAL_S", "15.0"))),
            reconstruct_person=_parse_bool_env("SPATIAL_RECONSTRUCT_PERSON", True),
            person_stationary_conf_threshold=_parse_optional_conf_env("SPATIAL_PERSON_STATIONARY_CONF_THRESHOLD"),
            person_moving_conf_threshold=_parse_optional_conf_env("SPATIAL_PERSON_MOVING_CONF_THRESHOLD"),
            person_min_speed_mps=max(0.0, float(os.getenv("SPATIAL_PERSON_MIN_SPEED_MPS", "0.25"))),
            reconstruct_vehicle=_parse_bool_env("SPATIAL_RECONSTRUCT_VEHICLE", True),
            vehicle_stationary_conf_threshold=_parse_optional_conf_env("SPATIAL_VEHICLE_STATIONARY_CONF_THRESHOLD"),
            vehicle_moving_conf_threshold=_parse_optional_conf_env("SPATIAL_VEHICLE_MOVING_CONF_THRESHOLD"),
            vehicle_min_speed_mps=max(0.0, float(os.getenv("SPATIAL_VEHICLE_MIN_SPEED_MPS", "0.35"))),
            reconstruct_animal=_parse_bool_env("SPATIAL_RECONSTRUCT_ANIMAL", True),
            animal_stationary_conf_threshold=_parse_optional_conf_env("SPATIAL_ANIMAL_STATIONARY_CONF_THRESHOLD"),
            animal_moving_conf_threshold=_parse_optional_conf_env("SPATIAL_ANIMAL_MOVING_CONF_THRESHOLD"),
            animal_min_speed_mps=max(0.0, float(os.getenv("SPATIAL_ANIMAL_MIN_SPEED_MPS", "0.20"))),
        )

