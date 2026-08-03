"""The version/dialect abstraction.

A :class:`Dialect` localizes everything that differs between SAS Viya
generations — endpoint paths, media-type versions, and response shapes (notably
the MAS ``output`` vs ``outputs`` key) — so the rest of the library codes against
one stable interface instead of branching on version inline.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..exceptions import ViyaResponseError
from ..models import Decision, ExecutionResult, ModelStep

MODEL_STEP_TYPE = "application/vnd.sas.decision.step.model"
DEFAULT_MAS_STEP = "execute"


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
    outputs_keys: tuple[str, ...] = ("outputs", "output")

    # -- endpoint paths -----------------------------------------------------

    def decision_path(self, decision_id: str) -> str:
        """Return the relative path for fetching a decision flow's content."""
        return f"/decisions/flows/{decision_id}"

    def mas_execute_path(self, module_id: str, step_id: str = DEFAULT_MAS_STEP) -> str:
        """Return the relative path for executing a MAS module step.

        ``step_id`` defaults to ``"execute"`` (correct for published decisions);
        pass another value for arbitrary modules exposing named steps.
        """
        return f"/microanalyticScore/modules/{module_id}/steps/{step_id}"

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
