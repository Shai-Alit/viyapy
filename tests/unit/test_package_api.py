"""Tests for the curated package root: exports and version."""

from __future__ import annotations

import viyapy


def test_version_is_a_string() -> None:
    assert isinstance(viyapy.__version__, str)
    assert viyapy.__version__


def test_exceptions_are_importable_from_root() -> None:
    from viyapy import ViyaAPIError, ViyaError

    assert issubclass(ViyaAPIError, ViyaError)


def test_all_exports_are_resolvable() -> None:
    for name in viyapy.__all__:
        assert hasattr(viyapy, name), f"{name} is in __all__ but not defined"


def test_exception_names_are_exported() -> None:
    for name in [
        "ViyaError",
        "ViyaConfigError",
        "ViyaConnectionError",
        "ViyaTimeoutError",
        "ViyaAPIError",
        "ViyaAuthError",
        "ViyaNotFoundError",
        "ViyaRateLimitError",
        "ViyaServerError",
        "ViyaResponseError",
        "ViyaValidationError",
    ]:
        assert name in viyapy.__all__


def test_model_names_are_exported() -> None:
    for name in [
        "Decision",
        "ModelStep",
        "ExecutionResult",
        "MasModule",
        "Revision",
        "StepSignature",
        "ValidationResult",
        "Variable",
    ]:
        assert name in viyapy.__all__
        assert hasattr(viyapy, name)
