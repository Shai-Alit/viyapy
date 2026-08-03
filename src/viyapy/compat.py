"""Deprecated 2.x-style helpers, kept as a migration bridge.

These functions mirror the signatures of the legacy flat helpers in
:mod:`viyapy.viya_utils` so existing scripts can switch imports with minimal
edits, but each one emits a :class:`DeprecationWarning` and delegates to the
modern :class:`viyapy.ViyaClient` API — so callers get the hardened HTTP layer,
typed errors, and the corrected MAS input handling (no ``_`` name-mangling)
while they migrate.

All of this is scheduled for removal in viyapy 4.0. See ``MIGRATION.md`` for the
per-function replacement and timeline.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from typing import Any

from .client import ViyaClient
from .dialects import Viya4Dialect

__all__ = [
    "call_id_api",
    "gen_viya_inputs",
    "get_decision_content",
    "get_models",
    "unpack_viya_outputs",
]

_REMOVED_IN = "viyapy 4.0"


def _warn(name: str, replacement: str) -> None:
    warnings.warn(
        f"viyapy.compat.{name} is deprecated and will be removed in {_REMOVED_IN}; "
        f"use {replacement} instead. See MIGRATION.md.",
        DeprecationWarning,
        stacklevel=3,
    )


def get_decision_content(base_url: str, decision_id: str, access_token: str) -> dict[str, Any]:
    """Deprecated. Use ``ViyaClient(base_url, token).decisions.get(id).raw``.

    Returns the raw decision-flow payload as a dict, as the 2.x helper did.
    """
    _warn("get_decision_content", "ViyaClient(...).decisions.get(...).raw")
    with ViyaClient(base_url, access_token) as client:
        return client.decisions.get(decision_id).raw


def get_models(base_url: str, decision_id: str, access_token: str) -> list[dict[str, Any]]:
    """Deprecated. Use ``ViyaClient(base_url, token).decisions.list_models(id)``.

    Returns the legacy list-of-dicts shape (``Model Name`` / ``Modified By`` /
    ``Modified Timestamp``) rebuilt from the typed :class:`ModelStep` objects.
    """
    _warn("get_models", "ViyaClient(...).decisions.list_models(...)")
    with ViyaClient(base_url, access_token) as client:
        models = client.decisions.list_models(decision_id)
    return [
        {
            "Model Name": m.name,
            "Modified By": m.modified_by,
            "Modified Timestamp": m.modified_timestamp,
        }
        for m in models
    ]


def gen_viya_inputs(feature_dict: Mapping[str, Any]) -> str:
    """Deprecated. Use ``dialect.build_inputs(feature_dict)`` (returns a dict).

    Returns the MAS request body as a JSON string, as the 2.x helper did, but
    without the trailing-underscore name-mangling that helper applied.
    """
    _warn("gen_viya_inputs", "viyapy.dialects.Viya4Dialect().build_inputs(...)")
    return json.dumps(Viya4Dialect().build_inputs(feature_dict))


def call_id_api(
    base_url: str,
    access_token: str,
    feature_dict: Mapping[str, Any],
    module_id: str,
) -> dict[str, Any]:
    """Deprecated. Use ``ViyaClient(base_url, token).mas.execute(module_id, inputs).raw``.

    Returns the raw MAS execution payload as a dict, as the 2.x helper did.
    """
    _warn("call_id_api", "ViyaClient(...).mas.execute(...).raw")
    with ViyaClient(base_url, access_token) as client:
        return client.mas.execute(module_id, feature_dict).raw


def unpack_viya_outputs(response: Mapping[str, Any]) -> dict[str, Any]:
    """Deprecated. Use ``ExecutionResult.outputs`` from ``mas.execute(...)``.

    Flattens a raw MAS response's output list into a ``{name: value}`` dict.
    Unlike the 2.x helper it accepts either the ``outputs`` (Viya 4) or
    ``output`` (Viya 3.5) key.
    """
    _warn("unpack_viya_outputs", "ViyaClient(...).mas.execute(...).outputs")
    for key in ("outputs", "output"):
        value = response.get(key)
        if isinstance(value, list):
            return {elem["name"]: elem.get("value", "") for elem in value}
    return {}
