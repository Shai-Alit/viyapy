"""Typed domain objects returned by the client.

These are plain, immutable dataclasses. Version-specific parsing of raw SAS Viya
responses into these shapes lives in :mod:`viyapy.dialects`; each object keeps
its originating payload on ``.raw`` as an escape hatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# MAS ``executionState`` values, returned in a step-execution ``stepOutput``.
# Which one you get depends on the request's ``waitTime`` (see MASClient.execute):
# a completed run reports ``completed``; a timed run that ran long reports
# ``timedOut``; a fire-and-forget submit reports ``submitted``.
EXECUTION_COMPLETED = "completed"
EXECUTION_TIMED_OUT = "timedOut"
EXECUTION_SUBMITTED = "submitted"


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
class MasModule:
    """A SAS Micro Analytic Score (MAS) module.

    Attributes:
        id: The module id.
        name: The module's name, if present.
        description: The module's description, if present.
        revision: The module revision number, if reported.
        scope: The module scope (e.g. ``"public"``), if reported.
        step_ids: The names of the steps the module exposes.
        created_by: User who created the module, if reported.
        modified_by: User who last modified the module, if reported.
        creation_timestamp: Creation timestamp string, if reported.
        modified_timestamp: Last-modified timestamp string, if reported.
        raw: The originating module payload.
    """

    id: str
    name: str | None = None
    description: str | None = None
    revision: int | None = None
    scope: str | None = None
    step_ids: tuple[str, ...] = ()
    created_by: str | None = None
    modified_by: str | None = None
    creation_timestamp: str | None = None
    modified_timestamp: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ModuleSource:
    """The source code of a SAS Micro Analytic Score (MAS) module.

    Returned by :meth:`~viyapy.mas.MASClient.get_source` and
    :meth:`~viyapy.mas.MASClient.update_source`. Holds the module's raw source
    text plus the metadata the ``/source`` subresource reports.

    Attributes:
        module_id: The owning module id.
        source: The module's source code (DS2 or Python), verbatim.
        version: The source resource version, if reported.
        created_by: User who created the module, if reported.
        modified_by: User who last modified the source, if reported.
        creation_timestamp: Creation timestamp string, if reported.
        modified_timestamp: Last-modified timestamp string, if reported.
        raw: The originating source payload.
    """

    module_id: str
    source: str
    version: int | None = None
    created_by: str | None = None
    modified_by: str | None = None
    creation_timestamp: str | None = None
    modified_timestamp: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Variable:
    """A single input or output variable in a MAS step signature.

    Attributes:
        name: The variable name.
        type: The variable's data type (e.g. ``"decimal"``, ``"string"``), if
            reported.
        dim: The array dimension (``0`` for a scalar), if reported.
        size: The declared size (e.g. string length), if reported.
    """

    name: str
    type: str | None = None
    dim: int | None = None
    size: int | None = None


@dataclass(frozen=True)
class StepSignature:
    """The input/output signature of a MAS module step.

    Attributes:
        id: The step id (e.g. ``"execute"``).
        module_id: The owning module id, if reported.
        inputs: The step's declared input variables.
        outputs: The step's declared output variables.
        raw: The originating step payload.
    """

    id: str
    module_id: str | None = None
    inputs: tuple[Variable, ...] = ()
    outputs: tuple[Variable, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ValidationResult:
    """The result of validating MAS step inputs server-side.

    Returned by :meth:`~viyapy.mas.MASClient.validate_remote`, which asks SAS Viya
    itself to validate a payload against a step's signature (as opposed to the
    client-side name check in :meth:`~viyapy.mas.MASClient.validate`). An invalid
    payload is reported as ``valid=False`` with the server's violation messages,
    not as an HTTP error.

    Attributes:
        valid: Whether the server accepted the inputs against the step signature.
        version: The validation resource version, if reported.
        messages: Human-readable violation messages when invalid (empty when
            valid), flattened from the server's error envelope.
        error: The raw SAS error object returned when invalid, if present.
        module_id: The module whose step was validated, if known.
        step: The step that was validated, if known.
        raw: The originating validation payload.
    """

    valid: bool
    version: int | None = None
    messages: tuple[str, ...] = ()
    error: dict[str, Any] | None = None
    module_id: str | None = None
    step: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ExecutionResult:
    """The result of executing a MAS module step.

    For a plain synchronous execute this holds the step's ``outputs``. For the
    timed and fire-and-forget modes (see :meth:`viyapy.MASClient.execute` and
    :meth:`~viyapy.MASClient.submit`), ``outputs`` may be empty and
    ``execution_state`` distinguishes what happened — use the
    :attr:`completed`, :attr:`timed_out`, and :attr:`submitted` helpers.

    A binary output (one MAS returned with ``encoding: "b64"``) is decoded from
    base64 back into ``bytes`` in :attr:`outputs`; scalar outputs pass through
    unchanged. ``client_id`` and ``transaction_id`` echo the correlation metadata
    the server returned (populated when it was supplied on the request).

    Attributes:
        outputs: Mapping of output name to value (empty when timed out or
            merely submitted). Binary outputs are decoded to ``bytes``.
        execution_state: MAS execution state (``"completed"``, ``"timedOut"``,
            or ``"submitted"``), if present.
        module_id: The executed module id, if reported.
        step_id: The executed step id, if reported.
        client_id: The correlation ``client_id`` echoed in the response
            ``metadata``, if present.
        transaction_id: The correlation ``transaction_id`` echoed in the
            response ``metadata``, if present.
        raw: The originating execution payload.
    """

    outputs: dict[str, Any]
    execution_state: str | None = None
    module_id: str | None = None
    step_id: str | None = None
    client_id: str | None = None
    transaction_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def __getitem__(self, key: str) -> Any:
        return self.outputs[key]

    def __contains__(self, key: object) -> bool:
        return key in self.outputs

    def get(self, key: str, default: Any = None) -> Any:
        """Return output ``key``, or ``default`` if it is absent."""
        return self.outputs.get(key, default)

    @property
    def completed(self) -> bool:
        """Whether the step finished; ``outputs`` are populated.

        Keyed on an exact ``execution_state == "completed"`` match, so this
        returns ``False`` when the server omits ``executionState`` entirely
        (``execution_state is None``) even though ``outputs`` may be fully
        populated. Check ``outputs`` directly if you need to handle a
        deployment that doesn't report the state on a synchronous run.
        """
        return self.execution_state == EXECUTION_COMPLETED

    @property
    def timed_out(self) -> bool:
        """Whether a timed execute exceeded its ``wait_time`` before finishing.

        The run may still complete server-side; ``outputs`` is empty here.
        """
        return self.execution_state == EXECUTION_TIMED_OUT

    @property
    def submitted(self) -> bool:
        """Whether a fire-and-forget execute was accepted without waiting."""
        return self.execution_state == EXECUTION_SUBMITTED
