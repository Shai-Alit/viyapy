"""Unit tests for the domain dataclasses."""

from __future__ import annotations

import dataclasses

import pytest

from viyapy.models import Decision, ExecutionResult, ModelStep


def test_model_step_defaults() -> None:
    step = ModelStep(name="Credit Model")
    assert step.name == "Credit Model"
    assert step.modified_by is None
    assert step.raw == {}


def test_decision_holds_models() -> None:
    decision = Decision(id="d1", name="Demo", models=(ModelStep(name="M"),))
    assert decision.id == "d1"
    assert decision.models[0].name == "M"


def test_dataclasses_are_frozen() -> None:
    result = ExecutionResult(outputs={"a": 1})
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.outputs = {}  # type: ignore[misc]


def test_execution_result_mapping_helpers() -> None:
    result = ExecutionResult(outputs={"output_string": "ok"})
    assert result["output_string"] == "ok"
    assert "output_string" in result
    assert "missing" not in result
    assert result.get("output_string") == "ok"
    assert result.get("missing", "default") == "default"


def test_raw_excluded_from_repr() -> None:
    step = ModelStep(name="M", raw={"big": "payload"})
    assert "big" not in repr(step)
