"""viyapy — a Python client for SAS Viya Intelligent Decisioning.

Supports SAS Viya 3.5 and Viya 4 (LTS and Stable) through a version/dialect
layer. The modern ``ViyaClient`` API is the supported surface across the 3.x
line and is importable, with the domain models and typed exception hierarchy,
directly from the package root.

The legacy 2.x flat helpers in :mod:`viyapy.viya_utils` remain importable but
are deprecated and slated for removal in 4.0. :mod:`viyapy.compat` offers
same-signature drop-ins that emit ``DeprecationWarning`` and delegate to
``ViyaClient``; see ``MIGRATION.md`` for the mapping and timeline.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from ._logging import RedactingFilter, RedactingNullHandler
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
)
from .models import Decision, ExecutionResult, ModelStep

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
    "ModelStep",
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
    "__version__",
]
