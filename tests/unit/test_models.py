"""Unit tests for the domain dataclasses."""

from __future__ import annotations

import dataclasses

import pytest

from viyapy.models import CompileJob, Decision, ExecutionResult, ModelStep, Revision


def test_model_step_defaults() -> None:
    step = ModelStep(name="Credit Model")
    assert step.name == "Credit Model"
    assert step.modified_by is None
    assert step.raw == {}


def test_decision_holds_models() -> None:
    decision = Decision(id="d1", name="Demo", models=(ModelStep(name="M"),))
    assert decision.id == "d1"
    assert decision.models[0].name == "M"


def test_decision_revision_metadata_defaults_to_none() -> None:
    # The revision/lock metadata is additive and optional — a decision built
    # without it must report None, not a coerced default.
    decision = Decision(id="d1")
    assert decision.major_revision is None
    assert decision.minor_revision is None
    assert decision.checkout is None


def test_revision_defaults() -> None:
    revision = Revision(id="r1")
    assert revision.id == "r1"
    assert revision.major_revision is None
    assert revision.checkout is None
    assert revision.raw == {}


def test_revision_label_composes_major_minor() -> None:
    assert Revision(id="r1", major_revision=1, minor_revision=3).label == "1.3"
    # A real 0.0 is a valid label, distinct from unknown.
    assert Revision(id="r1", major_revision=0, minor_revision=0).label == "0.0"


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"major_revision": 1}, {"minor_revision": 2}],
)
def test_revision_label_is_none_when_incomplete(kwargs: dict[str, int]) -> None:
    # Missing either component yields None so callers can tell it apart from 0.0.
    assert Revision(id="r1", **kwargs).label is None


def test_revision_raw_excluded_from_repr() -> None:
    assert "payload" not in repr(Revision(id="r1", raw={"big": "payload"}))


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


@pytest.mark.parametrize(
    ("state", "completed", "failed", "done"),
    [
        ("pending", False, False, False),
        ("running", False, False, False),
        ("completed", True, False, True),
        ("failed", False, True, True),
        (None, False, False, False),
    ],
)
def test_compile_job_state_properties(
    state: str | None, completed: bool, failed: bool, done: bool
) -> None:
    job = CompileJob(id="j1", state=state)
    assert job.completed is completed
    assert job.failed is failed
    assert job.done is done


def test_compile_job_defaults() -> None:
    job = CompileJob(id="j1")
    assert job.module_id is None
    assert job.errors == ()
    assert job.raw == {}
