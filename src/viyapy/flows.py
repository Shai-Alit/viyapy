"""A typed builder for composing decision-flow graphs in Python.

Decision flows are authored (via :meth:`~viyapy.decisions.DecisionsAPI.create`
and :meth:`~viyapy.decisions.DecisionsAPI.update`) as a ``flow`` graph — a
``{"steps": [...]}`` mapping where each step is a small dict discriminated by a
SAS media-type ``type`` string. Hand-writing that JSON is error-prone, so
:class:`FlowBuilder` assembles it from typed, validated calls instead:

.. code-block:: python

    from viyapy import FlowBuilder, TermMapping

    flow = (
        FlowBuilder()
        .model(
            "9fadffa1-...",
            mappings=[TermMapping.input("DEBTINC"), TermMapping.output("EM_CLASSIFICATION")],
        )
        .condition(
            "P_BAD1 < .2",
            on_true=FlowBuilder().ruleset("b2baf806-..."),
            on_false=FlowBuilder().ruleset("46d6af1f-..."),
        )
        .build()
    )
    client.decisions.create("My Flow", flow)

The builder emits only the **authorable** subset of each step — the server
assigns ids, timestamps, ``publishedModule``, and ``links`` on create. It covers
the three most common step types (model, ruleset, and if/else condition); other
step types can be added verbatim with :meth:`FlowBuilder.add_step`.

:meth:`~viyapy.decisions.DecisionsAPI.create` and ``update`` accept a
``FlowBuilder`` directly (they call :meth:`~FlowBuilder.build` for you), so a raw
dict is never required — though it remains accepted as an escape hatch.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ._validation import require_identifier, require_non_empty_str
from .exceptions import ViyaConfigError

# Step-type discriminators — the media-type strings SAS uses to tag each step
# kind within a flow's ``steps`` array (confirmed against a live Viya 4 flow).
STEP_MODEL = "application/vnd.sas.decision.step.model"
STEP_RULESET = "application/vnd.sas.decision.step.ruleset"
STEP_CONDITION = "application/vnd.sas.decision.step.condition"

# Mapping directions — how a step term relates to the decision-level term it is
# wired to. ``inOut`` is used by ruleset steps that both read and write a term.
DIRECTION_INPUT = "input"
DIRECTION_OUTPUT = "output"
DIRECTION_IN_OUT = "inOut"
_DIRECTIONS = frozenset({DIRECTION_INPUT, DIRECTION_OUTPUT, DIRECTION_IN_OUT})


@dataclass(frozen=True)
class TermMapping:
    """One term mapping wiring a step's variable to a decision-level term.

    Model, ruleset, and custom-object steps carry a list of these to connect the
    step's own terms (``step_term_name``) to the flow's decision variables
    (``decision_term_name``). When the two names match — the common case — use
    the :meth:`input`, :meth:`output`, and :meth:`in_out` constructors and give
    the name once.

    Attributes:
        decision_term_name: The decision-level (flow) term name — serialized as
            ``targetDecisionTermName``.
        step_term_name: The step's own term name — serialized as
            ``stepTermName``.
        direction: One of ``"input"``, ``"output"``, or ``"inOut"``.
    """

    decision_term_name: str
    step_term_name: str
    direction: str = DIRECTION_INPUT

    def __post_init__(self) -> None:
        require_non_empty_str(self.decision_term_name, "decision_term_name")
        require_non_empty_str(self.step_term_name, "step_term_name")
        if self.direction not in _DIRECTIONS:
            raise ViyaConfigError(
                f"direction must be one of {sorted(_DIRECTIONS)} (got {self.direction!r})"
            )

    @classmethod
    def input(cls, decision_term_name: str, step_term_name: str | None = None) -> TermMapping:
        """An ``input`` mapping; ``step_term_name`` defaults to the decision term."""
        return cls(decision_term_name, step_term_name or decision_term_name, DIRECTION_INPUT)

    @classmethod
    def output(cls, decision_term_name: str, step_term_name: str | None = None) -> TermMapping:
        """An ``output`` mapping; ``step_term_name`` defaults to the decision term."""
        return cls(decision_term_name, step_term_name or decision_term_name, DIRECTION_OUTPUT)

    @classmethod
    def in_out(cls, decision_term_name: str, step_term_name: str | None = None) -> TermMapping:
        """An ``inOut`` mapping; ``step_term_name`` defaults to the decision term."""
        return cls(decision_term_name, step_term_name or decision_term_name, DIRECTION_IN_OUT)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the wire shape SAS expects for a step mapping."""
        return {
            "targetDecisionTermName": self.decision_term_name,
            "direction": self.direction,
            "stepTermName": self.step_term_name,
        }


def _mappings_to_list(mappings: Iterable[TermMapping]) -> list[dict[str, Any]]:
    """Validate and serialize an iterable of :class:`TermMapping`."""
    out: list[dict[str, Any]] = []
    for mapping in mappings:
        if not isinstance(mapping, TermMapping):
            raise ViyaConfigError(
                f"each mapping must be a TermMapping (got {type(mapping).__name__})"
            )
        out.append(mapping.to_dict())
    return out


class FlowBuilder:
    """Assembles a decision-flow ``{"steps": [...]}`` graph from typed calls.

    Each builder method appends one step and returns ``self``, so calls chain
    fluently. Steps run in the order they are added. Nested branches
    (:meth:`condition`) take their own :class:`FlowBuilder` instances, so a graph
    of any depth composes from the same three methods. Call :meth:`build` to get
    the finished ``dict`` — or just pass the builder straight to
    :meth:`~viyapy.decisions.DecisionsAPI.create`.

    A builder is reusable and non-destructive: :meth:`build` copies its steps, so
    you can keep chaining after building.
    """

    def __init__(self) -> None:
        self._steps: list[dict[str, Any]] = []

    def __len__(self) -> int:
        return len(self._steps)

    def __bool__(self) -> bool:
        # A freshly constructed builder is falsy; one with steps is truthy.
        return bool(self._steps)

    def model(
        self,
        model_id: str,
        *,
        mappings: Iterable[TermMapping] = (),
        name: str | None = None,
    ) -> FlowBuilder:
        """Append a model step referencing the model with id ``model_id``.

        Args:
            model_id: The model's id (from the model repository). Required.
            mappings: Term mappings wiring the model's inputs/outputs to decision
                terms.
            name: Optional model name (cosmetic; the server resolves it from the
                id regardless).

        Returns:
            ``self``, for chaining.

        Raises:
            ViyaConfigError: ``model_id`` is empty/not a string, or a mapping is
                not a :class:`TermMapping`.
        """
        model_id = require_identifier(model_id, "model_id")
        model: dict[str, Any] = {"id": model_id}
        if name is not None:
            model["name"] = require_non_empty_str(name, "name")
        self._steps.append(
            {
                "type": STEP_MODEL,
                "model": model,
                "mappings": _mappings_to_list(mappings),
            }
        )
        return self

    def ruleset(
        self,
        ruleset_id: str,
        *,
        mappings: Iterable[TermMapping] = (),
        name: str | None = None,
        version_id: str | None = None,
        version_name: str | None = None,
    ) -> FlowBuilder:
        """Append a ruleset step referencing the ruleset with id ``ruleset_id``.

        Args:
            ruleset_id: The business ruleset's id. Required.
            mappings: Term mappings wiring the ruleset's terms to decision terms
                (ruleset steps commonly use :meth:`TermMapping.in_out`).
            name: Optional ruleset name (cosmetic).
            version_id: Optional pinned ruleset version id. When omitted, the
                server resolves the ruleset's current version.
            version_name: Optional pinned version label (e.g. ``"1.0"``).

        Returns:
            ``self``, for chaining.

        Raises:
            ViyaConfigError: ``ruleset_id`` is empty/not a string, or a mapping is
                not a :class:`TermMapping`.
        """
        ruleset_id = require_identifier(ruleset_id, "ruleset_id")
        ruleset: dict[str, Any] = {"id": ruleset_id}
        if name is not None:
            ruleset["name"] = require_non_empty_str(name, "name")
        if version_id is not None:
            ruleset["versionId"] = require_identifier(version_id, "version_id")
        if version_name is not None:
            ruleset["versionName"] = require_non_empty_str(version_name, "version_name")
        self._steps.append(
            {
                "type": STEP_RULESET,
                "ruleset": ruleset,
                "mappings": _mappings_to_list(mappings),
            }
        )
        return self

    def condition(
        self,
        expression: str,
        *,
        on_true: FlowBuilder | None = None,
        on_false: FlowBuilder | None = None,
        name: str | None = None,
    ) -> FlowBuilder:
        """Append an if/else condition step.

        The ``expression`` is a SAS boolean expression over decision terms (e.g.
        ``"P_BAD1 < .2"``). Steps in ``on_true`` run when it holds; steps in
        ``on_false`` run otherwise. Either branch may be omitted (an empty
        branch), and each is an independent :class:`FlowBuilder`, so branches
        nest arbitrarily.

        Each branch builder is captured **by reference** and only serialized when
        the outer :meth:`build` runs — not here — so you may keep composing a
        branch *after* attaching it and the later steps are still included.

        Args:
            expression: The condition expression. Required, non-empty.
            on_true: Steps to run when the expression is true.
            on_false: Steps to run when the expression is false.
            name: Optional human-readable label for the condition.

        Returns:
            ``self``, for chaining.

        Raises:
            ViyaConfigError: ``expression`` is empty/not a string, or a branch is
                not a :class:`FlowBuilder`.
        """
        expression = require_non_empty_str(expression, "expression")
        step: dict[str, Any] = {
            "type": STEP_CONDITION,
            "conditionExpression": expression,
            # Store the branch builders by reference; they are resolved to their
            # {"steps": [...]} shape lazily, at build() time. The type is still
            # validated eagerly here so a bad branch fails at the call site.
            "onTrue": _require_branch(on_true, "on_true"),
            "onFalse": _require_branch(on_false, "on_false"),
        }
        if name is not None:
            step["name"] = require_non_empty_str(name, "name")
        self._steps.append(step)
        return self

    def add_step(self, step: dict[str, Any]) -> FlowBuilder:
        """Append a raw, pre-formed step dict (escape hatch).

        For step types the builder does not model yet (custom-object, branch), or
        for reusing a step read back from an existing flow. The dict is
        **deep-copied** and appended verbatim, so later mutations of the caller's
        dict (including nested values) cannot corrupt the builder; only a minimal
        ``type`` sanity check is applied.

        Args:
            step: A step mapping carrying at least a non-empty ``type``.

        Returns:
            ``self``, for chaining.

        Raises:
            ViyaConfigError: ``step`` is not a dict or has no usable ``type``.
        """
        if not isinstance(step, dict):
            raise ViyaConfigError(f"step must be a dict (got {type(step).__name__})")
        step_type = step.get("type")
        if not isinstance(step_type, str) or not step_type.strip():
            raise ViyaConfigError("step must carry a non-empty 'type'")
        self._steps.append(copy.deepcopy(step))
        return self

    def build(self) -> dict[str, Any]:
        """Return the finished flow graph as ``{"steps": [...]}``.

        Returns a fresh **deep copy** each call, so the builder can keep being
        used afterwards and the returned graph can be mutated freely — including
        its nested step dicts, mapping lists, and condition branches — without
        affecting the builder's internal state or any prior/subsequent build.

        Condition branches are resolved from their :class:`FlowBuilder` at this
        point (not when :meth:`condition` was called), so steps added to a branch
        after it was attached are included. A branch that (transitively)
        references one of its own ancestors — a cycle — raises
        :class:`ViyaConfigError` here rather than recursing forever.
        """
        return self._build(frozenset())

    def _build(self, seen: frozenset[int]) -> dict[str, Any]:
        """Serialize this builder's steps, guarding against branch cycles.

        ``seen`` carries the ids of the builders currently being serialized on the
        path from the root, so a branch that references an ancestor is caught.
        """
        if id(self) in seen:
            raise ViyaConfigError("condition branch references an ancestor FlowBuilder (cycle)")
        seen = seen | {id(self)}
        return {"steps": [_serialize_step(step, seen) for step in self._steps]}


def _require_branch(branch: FlowBuilder | None, arg_name: str) -> FlowBuilder:
    """Validate a condition branch, returning the builder to resolve at build time.

    ``None`` becomes a fresh empty builder (an empty branch). The type is checked
    eagerly — an invalid branch fails at the :meth:`FlowBuilder.condition` call,
    not later at build.
    """
    if branch is None:
        return FlowBuilder()
    if not isinstance(branch, FlowBuilder):
        raise ViyaConfigError(
            f"{arg_name} must be a FlowBuilder or None (got {type(branch).__name__})"
        )
    return branch


def _serialize_step(step: dict[str, Any], seen: frozenset[int]) -> dict[str, Any]:
    """Deep-copy a step, resolving any nested :class:`FlowBuilder` branch to its dict."""
    return {key: _serialize_value(value, seen) for key, value in step.items()}


def _serialize_value(value: Any, seen: frozenset[int]) -> Any:
    """Recursively copy a step value; a :class:`FlowBuilder` resolves to its graph."""
    if isinstance(value, FlowBuilder):
        return value._build(seen)
    if isinstance(value, dict):
        return {key: _serialize_value(item, seen) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item, seen) for item in value]
    return copy.deepcopy(value)
