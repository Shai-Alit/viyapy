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
