"""viyapy — a Python client for SAS Viya Intelligent Decisioning.

Supports SAS Viya 3.5 and Viya 4 (LTS and Stable) through a version/dialect
layer. The modern ``ViyaClient`` API is introduced across the 3.x line; the
legacy flat helpers in :mod:`viyapy.viya_utils` remain available (deprecated).

The typed exception hierarchy is the stable public surface shipped so far and
is importable directly from the package root.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

from ._logging import RedactingFilter, RedactingNullHandler
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
    "ViyaAPIError",
    "ViyaAuthError",
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
