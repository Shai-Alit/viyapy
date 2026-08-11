"""Unit tests for the version/dialect layer."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from viyapy.dialects import Dialect, Viya4Dialect, Viya35Dialect, resolve
from viyapy.dialects.base import DEFAULT_MAS_STEP
from viyapy.exceptions import ViyaConfigError, ViyaResponseError

# -- resolution -------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("4", Viya4Dialect),
        ("4.0", Viya4Dialect),
        ("viya4", Viya4Dialect),
        (None, Viya4Dialect),
        ("3.5", Viya35Dialect),
        ("35", Viya35Dialect),
        ("viya3.5", Viya35Dialect),
        ("VIYA3.5", Viya35Dialect),
    ],
)
def test_resolve_versions(version: str | None, expected: type[Dialect]) -> None:
    assert isinstance(resolve(version), expected)


def test_resolve_passes_through_dialect_instance() -> None:
    dialect = Viya4Dialect()
    assert resolve(dialect) is dialect


def test_dialect_repr_names_class_and_generation() -> None:
    assert repr(Viya4Dialect()) == "Viya4Dialect(name='viya4')"
    assert repr(Viya35Dialect()) == "Viya35Dialect(name='viya3.5')"


def test_resolve_unknown_version_raises() -> None:
    with pytest.raises(ViyaConfigError):
        resolve("9")


# -- paths & input building -------------------------------------------------


def test_decision_and_mas_paths() -> None:
    dialect = Viya4Dialect()
    assert dialect.decision_path("d1") == "/decisions/flows/d1"
    assert (
        dialect.mas_execute_path("mod")
        == f"/microanalyticScore/modules/mod/steps/{DEFAULT_MAS_STEP}"
    )
    assert (
        dialect.mas_execute_path("mod", "custom") == "/microanalyticScore/modules/mod/steps/custom"
    )


def test_build_inputs_has_no_name_mangling() -> None:
    # Regression: the legacy helper appended "_" to every input name. It must not.
    body = Viya4Dialect().build_inputs({"input_string": "hello", "count": 3})
    assert body == {
        "inputs": [
            {"name": "input_string", "value": "hello"},
            {"name": "count", "value": 3},
        ]
    }


# -- decision parsing -------------------------------------------------------


def test_parse_decision_extracts_only_model_steps(
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture("viya4", "decision_content.json")
    decision = Viya4Dialect().parse_decision("abc-123-decision", raw)
    assert decision.name == "Sample Credit Decision"
    names = [m.name for m in decision.models]
    assert names == ["Credit Scoring Model", "Fraud Model"]  # ruleset step excluded
    assert decision.models[0].modified_by == "seford"


def test_parse_decision_on_empty_flow_yields_no_models() -> None:
    decision = Viya4Dialect().parse_decision("d1", {"name": "empty", "flow": {"steps": []}})
    assert decision.models == ()


def test_parse_decision_tolerates_missing_flow() -> None:
    decision = Viya4Dialect().parse_decision("d1", {"name": "no-flow"})
    assert decision.models == ()


@pytest.mark.parametrize("dialect", [Viya4Dialect(), Viya35Dialect()])
def test_decisions_flows_path_is_shared(dialect: object) -> None:
    assert dialect.decisions_flows_path() == "/decisions/flows"  # type: ignore[attr-defined]


@pytest.mark.parametrize("dialect", [Viya4Dialect(), Viya35Dialect()])
def test_parse_decision_summary_reads_core_fields(dialect: object) -> None:
    summary = dialect.parse_decision_summary(  # type: ignore[attr-defined]
        {
            "id": "hmeq",
            "name": "HMEQ",
            "description": "demo",
            "type": "decision",
            "createdBy": "sasdemo",
            "modifiedBy": "analyst",
            "creationTimeStamp": "2026-06-24T01:58:36.651Z",
            "modifiedTimeStamp": "2026-06-24T02:23:05.809Z",
        }
    )
    assert summary.id == "hmeq"
    assert summary.name == "HMEQ"
    assert summary.description == "demo"
    assert summary.type == "decision"
    assert summary.created_by == "sasdemo"
    assert summary.modified_by == "analyst"
    assert summary.creation_timestamp == "2026-06-24T01:58:36.651Z"
    assert summary.modified_timestamp == "2026-06-24T02:23:05.809Z"


def test_parse_decision_summary_tolerates_sparse_item() -> None:
    # Only an id is guaranteed; every other field must degrade to None, and a
    # blank string must not survive as "".
    summary = Viya4Dialect().parse_decision_summary({"id": "d1", "name": "   "})
    assert summary.id == "d1"
    assert summary.name is None
    assert summary.description is None
    assert summary.type is None


@pytest.mark.parametrize("bad", [{}, {"id": ""}, {"id": "   "}, {"id": 42}, {"name": "x"}])
def test_parse_decision_summary_without_usable_id_raises(bad: dict[str, object]) -> None:
    with pytest.raises(ViyaResponseError):
        Viya4Dialect().parse_decision_summary(bad)


# -- revision parsing / paths -----------------------------------------------


@pytest.mark.parametrize("dialect", [Viya4Dialect(), Viya35Dialect()])
def test_decision_revision_paths_are_shared(dialect: object) -> None:
    assert dialect.decision_revisions_path("d1") == "/decisions/flows/d1/revisions"  # type: ignore[attr-defined]
    assert (
        dialect.decision_revision_path("d1", "r2")  # type: ignore[attr-defined]
        == "/decisions/flows/d1/revisions/r2"
    )


def test_decision_revision_paths_percent_encode() -> None:
    dialect = Viya4Dialect()
    assert dialect.decision_revisions_path("a/b") == "/decisions/flows/a%2Fb/revisions"
    assert dialect.decision_revision_path("a/b", "c?d") == "/decisions/flows/a%2Fb/revisions/c%3Fd"


@pytest.mark.parametrize("dialect", [Viya4Dialect(), Viya35Dialect()])
def test_decision_code_paths_are_shared(dialect: object) -> None:
    assert dialect.decision_code_path("d1") == "/decisions/flows/d1/code"  # type: ignore[attr-defined]
    assert (
        dialect.decision_revision_code_path("d1", "r2")  # type: ignore[attr-defined]
        == "/decisions/flows/d1/revisions/r2/code"
    )
    # Both generations request the raw DS2 source media type.
    assert dialect.decision_code_media_type == "text/vnd.sas.source.ds2"  # type: ignore[attr-defined]


def test_decision_code_paths_percent_encode() -> None:
    dialect = Viya4Dialect()
    assert dialect.decision_code_path("a/b") == "/decisions/flows/a%2Fb/code"
    assert (
        dialect.decision_revision_code_path("a/b", "c?d")
        == "/decisions/flows/a%2Fb/revisions/c%3Fd/code"
    )


@pytest.mark.parametrize("dialect", [Viya4Dialect(), Viya35Dialect()])
def test_parse_revision_reads_core_fields(dialect: object) -> None:
    revision = dialect.parse_revision(  # type: ignore[attr-defined]
        {
            "id": "rev-2",
            "majorRevision": 1,
            "minorRevision": 3,
            "description": "tuned cutoffs",
            "nodeCount": 4,
            "checkout": True,
            "workflowDefinitionId": "wf-1",
            "createdBy": "sasdemo",
            "modifiedBy": "analyst",
            "creationTimeStamp": "2026-06-24T01:58:36.651Z",
            "modifiedTimeStamp": "2026-06-24T02:23:05.809Z",
        }
    )
    assert revision.id == "rev-2"
    assert revision.major_revision == 1
    assert revision.minor_revision == 3
    assert revision.description == "tuned cutoffs"
    assert revision.node_count == 4
    assert revision.checkout is True
    assert revision.workflow_definition_id == "wf-1"
    assert revision.label == "1.3"


def test_parse_revision_tolerates_sparse_item() -> None:
    # Only an id is guaranteed; other fields degrade to None, and a bool-y int
    # must not be mistaken for a revision number.
    revision = Viya4Dialect().parse_revision({"id": "r1"})
    assert revision.id == "r1"
    assert revision.major_revision is None
    assert revision.checkout is None
    assert revision.label is None


@pytest.mark.parametrize("bad", [{}, {"id": ""}, {"id": "   "}, {"id": 42}, {"majorRevision": 1}])
def test_parse_revision_without_usable_id_raises(bad: dict[str, object]) -> None:
    with pytest.raises(ViyaResponseError):
        Viya4Dialect().parse_revision(bad)


def test_parse_decision_surfaces_revision_metadata(
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture("viya4", "decision_revision.json")
    decision = Viya4Dialect().parse_decision("hmeq-rev-0002", raw)
    assert decision.major_revision == 1
    assert decision.minor_revision == 1
    assert decision.checkout is False


def test_parse_decision_revision_metadata_absent_is_none() -> None:
    decision = Viya4Dialect().parse_decision("d1", {"name": "n", "flow": {"steps": []}})
    assert decision.major_revision is None
    assert decision.minor_revision is None
    assert decision.checkout is None


# -- execution parsing / the output vs outputs matrix -----------------------


def test_viya4_parses_outputs_key(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("viya4", "mas_execute_ok.json")
    result = Viya4Dialect().parse_execution("api_tester1_0", "execute", raw)
    assert result.outputs["output_string"] == "successfully ran decision flow"
    assert result.execution_state == "completed"
    assert result.module_id == "api_tester1_0"


def test_viya35_parses_output_singular_key(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("viya35", "mas_execute_ok.json")
    result = Viya35Dialect().parse_execution("api_tester1_0", "execute", raw)
    assert result.outputs["input_string"] == "this is a test"


@pytest.mark.parametrize("dialect", [Viya4Dialect(), Viya35Dialect()])
def test_both_dialects_tolerate_either_output_key(dialect: Dialect) -> None:
    for key in ("outputs", "output"):
        result = dialect.parse_execution("m", "execute", {key: [{"name": "x", "value": 1}]})
        assert result.outputs == {"x": 1}


def test_missing_output_list_raises_response_error() -> None:
    with pytest.raises(ViyaResponseError):
        Viya4Dialect().parse_execution("m", "execute", {"executionState": "completed"})


# -- compile jobs ----------------------------------------------------------


def test_mas_job_paths_and_media_type() -> None:
    dialect = Viya4Dialect()
    assert dialect.mas_jobs_path() == "/microanalyticScore/jobs"
    assert dialect.mas_job_path("j1") == "/microanalyticScore/jobs/j1"
    # Ids are percent-encoded so a slashed id can't escape the path segment.
    assert dialect.mas_job_path("a/b") == "/microanalyticScore/jobs/a%2Fb"
    assert dialect.mas_job_media_type == "application/vnd.sas.microanalytic.job+json"


@pytest.mark.parametrize("dialect", [Viya4Dialect(), Viya35Dialect()])
def test_parse_compile_job_reads_core_fields(dialect: Dialect) -> None:
    job = dialect.parse_compile_job(
        {
            "id": "job-1",
            "moduleId": "m",
            "operation": "create",
            "state": "completed",
            "errors": [],
        }
    )
    assert job.id == "job-1"
    assert job.module_id == "m"
    assert job.operation == "create"
    assert job.completed


def test_parse_compile_job_coerces_error_entries_to_strings() -> None:
    job = Viya4Dialect().parse_compile_job(
        {"id": "j", "state": "failed", "errors": ["a", 42, {"m": "x"}]}
    )
    assert job.failed
    assert job.errors == ("a", "42", "{'m': 'x'}")


def test_parse_compile_job_tolerates_missing_errors() -> None:
    job = Viya4Dialect().parse_compile_job({"id": "j", "state": "pending"})
    assert job.errors == ()


@pytest.mark.parametrize("raw", [{}, {"id": ""}, {"id": "   "}, {"id": 5}, {"state": "pending"}])
def test_parse_compile_job_without_usable_id_raises(raw: dict[str, Any]) -> None:
    with pytest.raises(ViyaResponseError):
        Viya4Dialect().parse_compile_job(raw)
