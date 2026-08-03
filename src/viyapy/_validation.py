"""Boundary input validation shared across operation groups.

Fail fast with a typed :class:`~viyapy.exceptions.ViyaConfigError` when a caller
passes an empty or non-string identifier, rather than interpolating it into a
request path and letting the server reject it opaquely (PRODUCTION_PLAN.md §6.3).
"""

from __future__ import annotations

from .exceptions import ViyaConfigError


def require_identifier(value: object, name: str) -> str:
    """Return ``value`` stripped, or raise if it is not a non-empty string.

    Args:
        value: The candidate identifier (e.g. a decision id or module id).
        name: Parameter name, used in the error message.

    Returns:
        The whitespace-stripped identifier.

    Raises:
        ViyaConfigError: ``value`` is not a string, or is empty/whitespace.
    """
    if not isinstance(value, str) or not value.strip():
        raise ViyaConfigError(f"{name} must be a non-empty string (got {value!r})")
    return value.strip()
