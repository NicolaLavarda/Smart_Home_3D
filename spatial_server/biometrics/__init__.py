from .interfaces import IIdentityResolver
from .resolvers import (
    ExternalWebhookIdentityResolver,
    NoOpIdentityResolver,
    OpenVINOInsightFaceResolver,
)

__all__ = [
    "IIdentityResolver",
    "NoOpIdentityResolver",
    "OpenVINOInsightFaceResolver",
    "ExternalWebhookIdentityResolver",
]

