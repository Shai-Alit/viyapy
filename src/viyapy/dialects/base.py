"""The version/dialect abstraction.

A :class:`Dialect` localizes everything that differs between SAS Viya
generations — endpoint paths, media-type versions, and response shapes (notably
the MAS ``output`` vs ``outputs`` key) — so the rest of the library codes against
one stable interface instead of branching on version inline.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from ..exceptions import ViyaResponseError
from ..models import Decision, ExecutionResult, MasModule, ModelStep, StepSignature, Variable

MODEL_STEP_TYPE = "application/vnd.sas.decision.step.model"
DEFAULT_MAS_STEP = "execute"
MAS_MODULE_MEDIA_TYPE = "application/vnd.sas.microanalytic.module+json"
MAS_STEP_MEDIA_TYPE = "application/vnd.sas.microanalytic.module.step+json"


def _coerce_int(value: Any) -> int | None:
    """Return ``value`` if it is a real ``int`` (``bool`` excluded), else ``None``."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _prefer_str(value: Any, fallback: str) -> str:
    """Return ``value`` stripped if it is a non-empty string, else ``fallback``."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


class Dialect:
    """Base dialect with Viya-4-shaped defaults; subclasses override what differs.

    Class attributes:
        name: Human-readable dialect name.
        decision_media_type: ``Accept`` value for fetching decision content.
        outputs_keys: Response keys to look for MAS outputs under, in priority
            order. Both generations are tolerated; the order encodes the shape a
            given generation returns first.
    """

    name: str
    decision_media_type: str = "application/vnd.sas.decision+json"
    mas_module_media_type: str = MAS_MODULE_MEDIA_TYPE
    mas_step_media_type: str = MAS_STEP_MEDIA_TYPE
    outputs_keys: tuple[str, ...] = ("outputs", "output")

    # -- endpoint paths -----------------------------------------------------

    def decision_path(self, decision_id: str) -> str:
        """Return the relative path for fetching a decision flow's content."""
        return f"/decisions/flows/{quote(decision_id, safe='')}"

    def mas_modules_path(self) -> str:
        """Return the relative path for the MAS modules collection."""
        return "/microanalyticScore/modules"

    def mas_module_path(self, module_id: str) -> str:
        """Return the relative path for a single MAS module's metadata."""
        return f"/microanalyticScore/modules/{quote(module_id, safe='')}"

    def mas_execute_path(self, module_id: str, step_id: str = DEFAULT_MAS_STEP) -> str:
        """Return the relative path for executing a MAS module step.

        ``step_id`` defaults to ``"execute"`` (correct for published decisions);
        pass another value for arbitrary modules exposing named steps.

        Both segments are percent-encoded so a reserved character (``/``, ``?``,
        ``#``, …) in an id can't alter the request path.
        """
        return (
            f"/microanalyticScore/modules/{quote(module_id, safe='')}"
            f"/steps/{quote(step_id, safe='')}"
        )

    def mas_step_path(self, module_id: str, step_id: str = DEFAULT_MAS_STEP) -> str:
        """Return the relative path for a MAS step's signature (metadata ``GET``).

        This is the same resource URL as :meth:`mas_execute_path` — a ``GET``
        returns the step's input/output signature, a ``POST`` executes it — so
        the same percent-encoding guarantees apply.
        """
        return self.mas_execute_path(module_id, step_id)

    # -- request building ---------------------------------------------------

    def build_inputs(self, features: Mapping[str, Any]) -> dict[str, Any]:
        """Build a MAS ``/steps/execute`` request body from a feature mapping.

        Values are passed through as-is and serialized as JSON by the HTTP layer
        (no string concatenation, no implicit name-mangling).
        """
        return {"inputs": [{"name": name, "value": value} for name, value in features.items()]}

    # -- response parsing ---------------------------------------------------

    def parse_decision(self, decision_id: str, raw: Mapping[str, Any]) -> Decision:
        """Build a :class:`Decision` from a decision-flow payload.

        Extracts the model steps from ``flow.steps`` (ignoring non-model steps)
        and retains the full payload on :attr:`Decision.raw`.
        """
        flow = raw.get("flow")
        steps = flow.get("steps", []) if isinstance(flow, Mapping) else []
        models = tuple(
            ModelStep(
                name=str((step.get("model") or {}).get("name", "")),
                modified_by=step.get("modifiedBy"),
                modified_timestamp=step.get("modifiedTimeStamp"),
                raw=dict(step),
            )
            for step in steps
            if isinstance(step, Mapping) and step.get("type") == MODEL_STEP_TYPE
        )
        return Decision(id=decision_id, name=raw.get("name"), models=models, raw=dict(raw))

    def parse_module(self, raw: Mapping[str, Any]) -> MasModule:
        """Build a :class:`MasModule` from a MAS module payload.

        Used for both a single-module ``GET`` and each item of the modules
        collection; the full payload is retained on :attr:`MasModule.raw`.

        Raises:
            ViyaResponseError: The payload has no usable string ``id`` — without
                it the returned model would have a false identity (e.g. the
                literal ``"None"``), so a malformed response fails loudly here.
        """
        module_id = raw.get("id")
        if not isinstance(module_id, str) or not module_id.strip():
            raise ViyaResponseError(
                "MAS module payload has no usable 'id' field",
                response_body=dict(raw),
            )
        step_ids = raw.get("stepIds")
        steps = tuple(str(s) for s in step_ids) if isinstance(step_ids, list) else ()
        revision = raw.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int):
            revision = None
        return MasModule(
            id=module_id.strip(),
            name=raw.get("name"),
            description=raw.get("description"),
            revision=revision,
            scope=raw.get("scope"),
            step_ids=steps,
            created_by=raw.get("createdBy"),
            modified_by=raw.get("modifiedBy"),
            creation_timestamp=raw.get("creationTimeStamp"),
            modified_timestamp=raw.get("modifiedTimeStamp"),
            raw=dict(raw),
        )

    def parse_step_signature(
        self, module_id: str, step_id: str, raw: Mapping[str, Any]
    ) -> StepSignature:
        """Build a :class:`StepSignature` from a MAS step payload.

        The step's identity comes from the request (``module_id``/``step_id``);
        the payload's own ``id``/``moduleId`` are preferred when present. Each
        entry of the ``inputs`` and ``outputs`` arrays becomes a :class:`Variable`;
        malformed or nameless entries are skipped rather than crashing the parse.

        Raises:
            ViyaResponseError: The payload carries neither an ``inputs`` nor an
                ``outputs`` list — without either it isn't a usable signature, so
                a malformed response fails loudly here rather than returning an
                empty shape that looks like a real (but signatureless) step.
        """
        inputs_raw = raw.get("inputs")
        outputs_raw = raw.get("outputs")
        if not isinstance(inputs_raw, list) and not isinstance(outputs_raw, list):
            raise ViyaResponseError(
                "MAS step signature payload has no 'inputs' or 'outputs' list",
                response_body=dict(raw),
            )
        return StepSignature(
            id=_prefer_str(raw.get("id"), step_id),
            module_id=_prefer_str(raw.get("moduleId"), module_id),
            inputs=self._parse_variables(inputs_raw),
            outputs=self._parse_variables(outputs_raw),
            raw=dict(raw),
        )

    def _parse_variables(self, items: Any) -> tuple[Variable, ...]:
        """Parse a signature's ``inputs``/``outputs`` array into :class:`Variable`s."""
        if not isinstance(items, list):
            return ()
        variables: list[Variable] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue  # a nameless entry can't be addressed; skip it
            var_type = item.get("type")
            variables.append(
                Variable(
                    name=name.strip(),
                    type=var_type if isinstance(var_type, str) else None,
                    dim=_coerce_int(item.get("dim")),
                    size=_coerce_int(item.get("size")),
                )
            )
        return tuple(variables)

    def parse_execution(
        self, module_id: str, step_id: str, raw: Mapping[str, Any]
    ) -> ExecutionResult:
        """Build an :class:`ExecutionResult` from a MAS execute payload.

        Flattens the generation's output list (``outputs`` or ``output``) into a
        ``{name: value}`` mapping. Raises :class:`ViyaResponseError` if no output
        list is present.
        """
        outputs = {
            item["name"]: item.get("value")
            for item in self._raw_outputs(raw)
            if isinstance(item, Mapping) and "name" in item
        }
        return ExecutionResult(
            outputs=outputs,
            execution_state=raw.get("executionState"),
            module_id=raw.get("moduleId", module_id),
            step_id=raw.get("stepId", step_id),
            raw=dict(raw),
        )

    def _raw_outputs(self, raw: Mapping[str, Any]) -> list[Any]:
        for key in self.outputs_keys:
            value = raw.get(key)
            if isinstance(value, list):
                return value
        raise ViyaResponseError(
            f"MAS response contains no output list (expected one of {self.outputs_keys!r})",
            response_body=dict(raw),
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"
