"""Boundary input validation shared across operation groups.

Fail fast with a typed :class:`~viyapy.exceptions.ViyaConfigError` when a caller
passes an empty or non-string identifier, rather than interpolating it into a
request path and letting the server reject it opaquely (PRODUCTION_PLAN.md §6.3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .exceptions import ViyaConfigError, ViyaValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .models import StepSignature


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


def require_positive_int(value: object, name: str) -> int:
    """Return ``value`` if it is a positive integer, else raise.

    Args:
        value: The candidate value (e.g. a page size).
        name: Parameter name, used in the error message.

    Returns:
        The validated integer.

    Raises:
        ViyaConfigError: ``value`` is not an ``int`` (``bool`` excluded) or is
            not greater than zero.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ViyaConfigError(f"{name} must be a positive integer (got {value!r})")
    return value


def check_inputs_against_signature(
    signature: StepSignature,
    inputs: Mapping[str, Any],
    *,
    module_id: str | None = None,
    step: str | None = None,
) -> None:
    """Validate ``inputs`` against a step ``signature``, raising on a mismatch.

    Compares the supplied input names to the names the signature declares. A
    declared input that is not supplied is *missing*; a supplied input the
    signature does not declare is *unexpected*. Either raises
    :class:`~viyapy.exceptions.ViyaValidationError`. Values and types are not
    inspected — only the set of names — to avoid false positives against SAS
    Viya's permissive numeric coercion.

    Args:
        signature: The step signature to check against.
        inputs: The input name/value mapping the caller intends to execute.
        module_id: Module id for error context; falls back to ``signature.module_id``.
        step: Step id for error context; falls back to ``signature.id``.

    Raises:
        ViyaValidationError: One or more inputs are missing or unexpected.
    """
    declared = {variable.name for variable in signature.inputs}
    provided = set(inputs)
    missing = tuple(sorted(declared - provided))
    unexpected = tuple(sorted(provided - declared))
    if not missing and not unexpected:
        return

    problems: list[str] = []
    if missing:
        problems.append(f"missing required input(s): {', '.join(missing)}")
    if unexpected:
        problems.append(f"unexpected input(s): {', '.join(unexpected)}")
    raise ViyaValidationError(
        "inputs do not match the step signature — " + "; ".join(problems),
        missing=missing,
        unexpected=unexpected,
        module_id=module_id or signature.module_id,
        step=step or signature.id,
    )
