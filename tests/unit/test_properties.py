"""Property-based tests (Hypothesis) for the payload builders/parsers.

These fuzz the two pure data transforms that the old string-concatenation code
got wrong — MAS input building and output flattening — to guarantee the
escaping/round-trip bugs can't come back.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from hypothesis import example, given
from hypothesis import strategies as st

from viyapy.dialects import Viya4Dialect

# JSON-safe values: scalars plus arbitrarily nested lists/objects of them.
_json_scalars = (
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text()
)
_json_values = st.recursive(
    _json_scalars,
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=10,
)


# -- build_inputs: never mangles, always round-trips through JSON -----------


@given(features=st.dictionaries(st.text(), _json_values))
@example(features={'quote"and\nnewline\ttab': 'v"al\tue sep\U0001f600'})
@example(features={"amount": 1000, "flag": True, "missing": None})
def test_build_inputs_round_trips_and_preserves(features: dict[str, Any]) -> None:
    body = Viya4Dialect().build_inputs(features)

    # 1. It is valid, round-trippable JSON (the escaping guarantee).
    assert json.loads(json.dumps(body)) == body

    # 2. Names are preserved verbatim — no trailing-underscore mangling, no drops.
    assert [item["name"] for item in body["inputs"]] == list(features)

    # 3. Values are passed through untouched.
    for item in body["inputs"]:
        assert item["value"] == features[item["name"]]


# -- output flattening: preserves well-formed items, tolerates junk ----------


@given(outputs=st.lists(st.fixed_dictionaries({"name": st.text(), "value": _json_values})))
def test_parse_execution_preserves_outputs(outputs: list[dict[str, Any]]) -> None:
    result = Viya4Dialect().parse_execution("m", "execute", {"outputs": outputs})
    # Later duplicates win, matching a plain dict comprehension.
    expected = {item["name"]: item["value"] for item in outputs}
    assert result.outputs == expected


@given(
    outputs=st.lists(
        st.one_of(
            st.fixed_dictionaries({"name": st.text(), "value": _json_values}),
            st.dictionaries(st.text(), _json_values),  # may lack "name"
            st.text(),  # non-mapping junk
            st.integers(),  # non-mapping junk
        )
    )
)
def test_parse_execution_skips_malformed_without_raising(outputs: list[Any]) -> None:
    result = Viya4Dialect().parse_execution("m", "execute", {"outputs": outputs})
    expected = {
        item["name"]: item.get("value")
        for item in outputs
        if isinstance(item, Mapping) and "name" in item
    }
    assert result.outputs == expected
