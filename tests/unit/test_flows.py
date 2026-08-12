"""Unit tests for the typed flow builder (``viyapy.flows``).

These exercise :class:`TermMapping` and :class:`FlowBuilder` purely as
client-side constructs — no HTTP. The serialized shapes asserted here mirror the
live Viya 4 ``flow.steps`` wire shapes confirmed while designing the builder, so
they double as a drift guard on the emitted JSON.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from viyapy import FlowBuilder, TermMapping
from viyapy.exceptions import ViyaConfigError
from viyapy.flows import (
    DIRECTION_IN_OUT,
    DIRECTION_INPUT,
    DIRECTION_OUTPUT,
    STEP_CONDITION,
    STEP_MODEL,
    STEP_RULESET,
)

# -- TermMapping -----------------------------------------------------------


def test_term_mapping_to_dict_uses_wire_field_names() -> None:
    mapping = TermMapping("DEBTINC", "DEBTINC", DIRECTION_INPUT)
    assert mapping.to_dict() == {
        "targetDecisionTermName": "DEBTINC",
        "direction": "input",
        "stepTermName": "DEBTINC",
    }


def test_term_mapping_constructors_default_step_term_to_decision_term() -> None:
    assert TermMapping.input("DEBTINC").to_dict() == {
        "targetDecisionTermName": "DEBTINC",
        "direction": "input",
        "stepTermName": "DEBTINC",
    }
    assert TermMapping.output("EM_CLASSIFICATION").direction == DIRECTION_OUTPUT
    assert TermMapping.in_out("BAD").direction == DIRECTION_IN_OUT


def test_term_mapping_constructors_accept_distinct_step_term() -> None:
    mapping = TermMapping.input("DEBTINC", "debt_income_ratio")
    assert mapping.decision_term_name == "DEBTINC"
    assert mapping.step_term_name == "debt_income_ratio"
    assert mapping.direction == DIRECTION_INPUT


def test_term_mapping_is_frozen() -> None:
    mapping = TermMapping.input("DEBTINC")
    with pytest.raises(FrozenInstanceError):
        mapping.direction = DIRECTION_OUTPUT  # type: ignore[misc]


@pytest.mark.parametrize("bad", ["", "   "])
def test_term_mapping_rejects_blank_decision_term(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        TermMapping(bad, "step")


@pytest.mark.parametrize("bad", ["", "   "])
def test_term_mapping_rejects_blank_step_term(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        TermMapping("decision", bad)


def test_term_mapping_rejects_unknown_direction() -> None:
    with pytest.raises(ViyaConfigError):
        TermMapping("decision", "step", "sideways")


# -- FlowBuilder: empty / protocol -----------------------------------------


def test_empty_builder_is_falsy_and_builds_empty_steps() -> None:
    builder = FlowBuilder()
    assert len(builder) == 0
    assert not builder
    assert builder.build() == {"steps": []}


def test_builder_with_steps_is_truthy_and_counts() -> None:
    builder = FlowBuilder().model("m-1").ruleset("r-1")
    assert len(builder) == 2
    assert builder


def test_methods_return_self_for_chaining() -> None:
    builder = FlowBuilder()
    assert builder.model("m-1") is builder
    assert builder.ruleset("r-1") is builder
    assert builder.condition("x > 1") is builder
    assert builder.add_step({"type": "custom"}) is builder


# -- FlowBuilder: model step -----------------------------------------------


def test_model_step_minimal_shape() -> None:
    step = FlowBuilder().model("9fadffa1").build()["steps"][0]
    assert step == {
        "type": STEP_MODEL,
        "model": {"id": "9fadffa1"},
        "mappings": [],
    }


def test_model_step_with_name_and_mappings() -> None:
    step = (
        FlowBuilder()
        .model(
            "9fadffa1",
            name="Credit Scoring Model",
            mappings=[TermMapping.input("DEBTINC"), TermMapping.output("EM_CLASSIFICATION")],
        )
        .build()["steps"][0]
    )
    assert step["model"] == {"id": "9fadffa1", "name": "Credit Scoring Model"}
    assert step["mappings"] == [
        {"targetDecisionTermName": "DEBTINC", "direction": "input", "stepTermName": "DEBTINC"},
        {
            "targetDecisionTermName": "EM_CLASSIFICATION",
            "direction": "output",
            "stepTermName": "EM_CLASSIFICATION",
        },
    ]


@pytest.mark.parametrize("bad", ["", "   ", None, 42])
def test_model_rejects_bad_id(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        FlowBuilder().model(bad)  # type: ignore[arg-type]


def test_model_rejects_non_mapping_in_mappings() -> None:
    with pytest.raises(ViyaConfigError):
        FlowBuilder().model("m-1", mappings=[{"not": "a TermMapping"}])  # type: ignore[list-item]


# -- FlowBuilder: ruleset step ---------------------------------------------


def test_ruleset_step_minimal_shape() -> None:
    step = FlowBuilder().ruleset("b2baf806").build()["steps"][0]
    assert step == {
        "type": STEP_RULESET,
        "ruleset": {"id": "b2baf806"},
        "mappings": [],
    }


def test_ruleset_step_with_version_and_mappings() -> None:
    step = (
        FlowBuilder()
        .ruleset(
            "b2baf806",
            name="Approval Rules",
            version_id="v-123",
            version_name="1.0",
            mappings=[TermMapping.in_out("BAD")],
        )
        .build()["steps"][0]
    )
    assert step["ruleset"] == {
        "id": "b2baf806",
        "name": "Approval Rules",
        "versionId": "v-123",
        "versionName": "1.0",
    }
    assert step["mappings"] == [
        {"targetDecisionTermName": "BAD", "direction": "inOut", "stepTermName": "BAD"}
    ]


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_ruleset_rejects_bad_id(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        FlowBuilder().ruleset(bad)  # type: ignore[arg-type]


# -- FlowBuilder: condition step -------------------------------------------


def test_condition_empty_branches() -> None:
    step = FlowBuilder().condition("P_BAD1 < .2").build()["steps"][0]
    assert step == {
        "type": STEP_CONDITION,
        "conditionExpression": "P_BAD1 < .2",
        "onTrue": {"steps": []},
        "onFalse": {"steps": []},
    }


def test_condition_with_name_and_nested_branches() -> None:
    step = (
        FlowBuilder()
        .condition(
            "P_BAD1 < .2",
            name="Low risk?",
            on_true=FlowBuilder().ruleset("approve-rs"),
            on_false=FlowBuilder().ruleset("decline-rs"),
        )
        .build()["steps"][0]
    )
    assert step["name"] == "Low risk?"
    assert step["conditionExpression"] == "P_BAD1 < .2"
    assert step["onTrue"]["steps"][0]["ruleset"]["id"] == "approve-rs"
    assert step["onFalse"]["steps"][0]["ruleset"]["id"] == "decline-rs"


def test_condition_branches_can_nest_conditions() -> None:
    inner = FlowBuilder().condition("score > 700", on_true=FlowBuilder().model("m-inner"))
    step = FlowBuilder().condition("age > 18", on_true=inner).build()["steps"][0]
    nested = step["onTrue"]["steps"][0]
    assert nested["type"] == STEP_CONDITION
    assert nested["onTrue"]["steps"][0]["model"]["id"] == "m-inner"


@pytest.mark.parametrize("bad", ["", "   "])
def test_condition_rejects_blank_expression(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        FlowBuilder().condition(bad)


def test_condition_rejects_non_builder_branch() -> None:
    with pytest.raises(ViyaConfigError):
        FlowBuilder().condition("x > 1", on_true={"steps": []})  # type: ignore[arg-type]


# -- FlowBuilder: add_step escape hatch ------------------------------------


def test_add_step_appends_a_deep_copy() -> None:
    raw = {"type": "application/vnd.sas.decision.step.custom.object", "customObject": {"id": "c1"}}
    builder = FlowBuilder().add_step(raw)
    built = builder.build()["steps"][0]
    assert built == raw
    # A deep copy is stored: mutating the caller's dict afterwards — including
    # nested values — must not leak into the builder's internal state.
    raw["extra"] = "leaked"
    raw["customObject"]["id"] = "mutated"
    stored = builder.build()["steps"][0]
    assert "extra" not in stored
    assert stored["customObject"] == {"id": "c1"}


@pytest.mark.parametrize("bad", [None, 42, ["type"], "type"])
def test_add_step_rejects_non_dict(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        FlowBuilder().add_step(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_type", [{}, {"type": ""}, {"type": "   "}, {"type": 42}])
def test_add_step_rejects_missing_type(bad_type: dict[str, object]) -> None:
    with pytest.raises(ViyaConfigError):
        FlowBuilder().add_step(bad_type)


# -- FlowBuilder: build() copy semantics -----------------------------------


def test_build_returns_fresh_copy_each_call() -> None:
    builder = FlowBuilder().model("m-1")
    first = builder.build()
    second = builder.build()
    assert first == second
    assert first is not second
    assert first["steps"][0] is not second["steps"][0]


def test_builder_is_reusable_after_build() -> None:
    builder = FlowBuilder().model("m-1")
    snapshot = builder.build()
    builder.ruleset("r-1")
    # The earlier snapshot is unaffected by later chaining.
    assert len(snapshot["steps"]) == 1
    assert len(builder.build()["steps"]) == 2


def test_mutating_built_dict_does_not_affect_builder() -> None:
    builder = FlowBuilder().model("m-1")
    built = builder.build()
    built["steps"].append({"type": "injected"})
    assert len(builder.build()["steps"]) == 1


def test_mutating_nested_step_dict_does_not_affect_builder() -> None:
    # build() must deep-copy: mutating a nested field of a built step must not
    # corrupt the builder's internal state for subsequent build() calls.
    builder = FlowBuilder().model("m-1")
    built = builder.build()
    built["steps"][0]["model"]["name"] = "leaked"
    assert "name" not in builder.build()["steps"][0]["model"]


def test_mutating_built_mappings_list_does_not_affect_builder() -> None:
    builder = FlowBuilder().model("m-1", mappings=[TermMapping.input("X")])
    built = builder.build()
    built["steps"][0]["mappings"].append({"extra": "leaked"})
    # The builder still holds exactly one mapping — the nested list was copied.
    assert len(builder.build()["steps"][0]["mappings"]) == 1


def test_mutating_built_condition_branch_does_not_affect_builder() -> None:
    builder = FlowBuilder().condition("x > 1", on_true=FlowBuilder().ruleset("r-1"))
    built = builder.build()
    built["steps"][0]["onTrue"]["steps"][0]["ruleset"]["id"] = "leaked"
    assert builder.build()["steps"][0]["onTrue"]["steps"][0]["ruleset"]["id"] == "r-1"


# -- FlowBuilder: condition branches resolve at build time ------------------


def test_condition_branch_is_resolved_at_build_time_not_attach_time() -> None:
    # Branches follow the same copy-at-build-time rule as the rest of the API:
    # steps added to a branch AFTER it is attached must still be included.
    approve = FlowBuilder()
    decline = FlowBuilder()
    flow = FlowBuilder().condition("x > 1", on_true=approve, on_false=decline)
    approve.ruleset("approve-rs")  # composed after attaching
    decline.ruleset("decline-rs")
    step = flow.build()["steps"][0]
    assert step["onTrue"]["steps"][0]["ruleset"]["id"] == "approve-rs"
    assert step["onFalse"]["steps"][0]["ruleset"]["id"] == "decline-rs"


def test_condition_branch_reflects_latest_state_across_builds() -> None:
    branch = FlowBuilder().model("m-1")
    outer = FlowBuilder().condition("x > 1", on_true=branch)
    assert len(outer.build()["steps"][0]["onTrue"]["steps"]) == 1
    branch.ruleset("r-1")  # keep composing the branch after the first build
    assert len(outer.build()["steps"][0]["onTrue"]["steps"]) == 2


def test_condition_self_reference_raises_cycle_at_build() -> None:
    builder = FlowBuilder()
    builder.condition("x > 1", on_true=builder)  # a direct cycle
    with pytest.raises(ViyaConfigError):
        builder.build()


def test_condition_indirect_cycle_raises_at_build() -> None:
    a = FlowBuilder()
    b = FlowBuilder()
    a.condition("x > 1", on_true=b)
    b.condition("y > 2", on_true=a)  # a -> b -> a
    with pytest.raises(ViyaConfigError):
        a.build()


def test_two_builds_share_no_nested_objects() -> None:
    builder = FlowBuilder().model("m-1", mappings=[TermMapping.input("X")])
    first = builder.build()
    second = builder.build()
    # Every nested container is a distinct object between successive builds.
    assert first["steps"][0] is not second["steps"][0]
    assert first["steps"][0]["model"] is not second["steps"][0]["model"]
    assert first["steps"][0]["mappings"] is not second["steps"][0]["mappings"]


# -- ordering --------------------------------------------------------------


def test_steps_preserve_insertion_order() -> None:
    steps = FlowBuilder().model("m-1").condition("x > 1").ruleset("r-1").build()["steps"]
    assert [s["type"] for s in steps] == [STEP_MODEL, STEP_CONDITION, STEP_RULESET]
