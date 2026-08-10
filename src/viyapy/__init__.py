"""viyapy — a Python client for SAS Viya Intelligent Decisioning.

Supports SAS Viya 3.5 and Viya 4 (LTS and Stable) through a version/dialect
layer. The ``ViyaClient`` API is the entire public surface and is importable,
with the domain models and typed exception hierarchy, directly from the package
root. (The 2.x flat ``viya_utils`` helpers were removed in 3.0 — see
``MIGRATION.md`` for the mapping to the client API.)
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from ._logging import RedactingFilter, RedactingNullHandler
from .auth import TokenProvider
from .client import ViyaClient
from .exceptions import (
    ViyaAPIError,
    ViyaAuthError,
    ViyaConfigError,
    ViyaConnectionError,
    ViyaError,
    ViyaNotFoundError,
    ViyaRateLimitError,
    ViyaResponseError,
    ViyaSecurityWarning,
    ViyaServerError,
    ViyaTimeoutError,
    ViyaValidationError,
)
from .models import (
    Decision,
    ExecutionResult,
    MasModule,
    ModelStep,
    StepSignature,
    ValidationResult,
    Variable,
)

try:
    __version__ = version("viyapy")
except PackageNotFoundError:  # pragma: no cover - only when running from source tree
    __version__ = "0.0.0.dev0"

# Attach a do-nothing handler so importing viyapy never emits "No handlers could
# be found" warnings, and hang the redaction filter on it as a token-leak
# backstop. The record is scrubbed in place as it propagates through this handler,
# so the mask applies even to handlers configured by the application.
_handler = RedactingNullHandler()
_handler.addFilter(RedactingFilter())
logging.getLogger(__name__).addHandler(_handler)

__all__ = [
    "Decision",
    "ExecutionResult",
    "MasModule",
    "ModelStep",
    "StepSignature",
    "TokenProvider",
    "ValidationResult",
    "Variable",
    "ViyaAPIError",
    "ViyaAuthError",
    "ViyaClient",
    "ViyaConfigError",
    "ViyaConnectionError",
    "ViyaError",
    "ViyaNotFoundError",
    "ViyaRateLimitError",
    "ViyaResponseError",
    "ViyaSecurityWarning",
    "ViyaServerError",
    "ViyaTimeoutError",
    "ViyaValidationError",
    "__version__",
]
