from .interfaces import DetectionBatchCallback, IDetectionSource
from .synthetic_source import SyntheticWalkSimulatorSource
from .mqtt_source import MqttFrigateDetectionSource
from .openvino_rtsp_source import OpenVINORtspDetectionSource

__all__ = [
    "DetectionBatchCallback",
    "IDetectionSource",
    "SyntheticWalkSimulatorSource",
    "MqttFrigateDetectionSource",
    "OpenVINORtspDetectionSource",
]

