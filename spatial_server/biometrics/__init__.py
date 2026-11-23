from .alpr_pipeline import OnnxAlprRecognizer
from .consensus import TrackBiometricConsensusManager
from .crop_store import BiometricCropStore
from .face_gallery import FaceGalleryIndex, FaceGalleryMatch
from .face_pipeline import OnnxInsightFaceRecognizer
from .interfaces import (
    IBiometricCoordinator,
    IFaceRecognizer,
    IFrameSnapshotProvider,
    IIdentityResolver,
    IPlateRecognizer,
)
from .models import (
    BiometricJob,
    CropPayload,
    FaceEvaluation,
    FaceQualityMetrics,
    PlateEvaluation,
    PlateNormalizedResult,
    PlateQualityMetrics,
    PlateWhitelistEntry,
    TrackBiometricUpdate,
)
from .plate_postprocessor import (
    PlateWhitelistMatcher,
    levenshtein_distance,
    normalize_and_validate_plate,
)
from .resolvers import (
    ExternalWebhookIdentityResolver,
    NoOpIdentityResolver,
    OpenVINOInsightFaceResolver,
)
from .snapshot_provider import (
    Go2RtcSnapshotProvider,
    decode_and_crop_jpeg,
    parse_jpeg_dimensions,
)
from .worker import (
    BiometricEligibilityGate,
    BiometricWorkerService,
    TrackCoalescingQueue,
)

__all__ = [
    "BiometricCropStore",
    "BiometricEligibilityGate",
    "BiometricJob",
    "BiometricWorkerService",
    "CropPayload",
    "ExternalWebhookIdentityResolver",
    "FaceEvaluation",
    "FaceGalleryIndex",
    "FaceGalleryMatch",
    "FaceQualityMetrics",
    "Go2RtcSnapshotProvider",
    "IBiometricCoordinator",
    "IFaceRecognizer",
    "IFrameSnapshotProvider",
    "IIdentityResolver",
    "IPlateRecognizer",
    "NoOpIdentityResolver",
    "OnnxAlprRecognizer",
    "OnnxInsightFaceRecognizer",
    "OpenVINOInsightFaceResolver",
    "PlateEvaluation",
    "PlateNormalizedResult",
    "PlateQualityMetrics",
    "PlateWhitelistEntry",
    "PlateWhitelistMatcher",
    "TrackBiometricConsensusManager",
    "TrackBiometricUpdate",
    "TrackCoalescingQueue",
    "decode_and_crop_jpeg",
    "levenshtein_distance",
    "normalize_and_validate_plate",
    "parse_jpeg_dimensions",
]
