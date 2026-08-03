"""Typed domain objects returned by the client.

These are plain, immutable dataclasses. Version-specific parsing of raw SAS Viya
responses into these shapes lives in :mod:`viyapy.dialects`; each object keeps
its originating payload on ``.raw`` as an escape hatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelStep:
    """A model step within a decision flow.

    Attributes:
        name: The model's name.
        modified_by: User who last modified the step, if reported.
        modified_timestamp: Last-modified timestamp string, if reported.
        raw: The originating step payload.
    """

    name: str
    modified_by: str | None = None
    modified_timestamp: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Decision:
    """A SAS Intelligent Decisioning decision flow.

    Attributes:
        id: The decision id.
        name: The decision's name, if present.
        models: The model steps contained in the flow.
        raw: The originating decision payload.
    """

    id: str
    name: str | None = None
    models: tuple[ModelStep, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ExecutionResult:
    """The result of executing a MAS module step.

    Attributes:
        outputs: Mapping of output name to value.
        execution_state: MAS execution state (e.g. ``"completed"``), if present.
        module_id: The executed module id, if reported.
        step_id: The executed step id, if reported.
        raw: The originating execution payload.
    """

    outputs: dict[str, Any]
    execution_state: str | None = None
    module_id: str | None = None
    step_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def __getitem__(self, key: str) -> Any:
        return self.outputs[key]

    def __contains__(self, key: object) -> bool:
        return key in self.outputs

    def get(self, key: str, default: Any = None) -> Any:
        """Return output ``key``, or ``default`` if it is absent."""
        return self.outputs.get(key, default)
