"""Tests for the deprecated viyapy.compat bridge and legacy-module warning."""

from __future__ import annotations

import importlib
import json
import sys
import warnings
from collections.abc import Callable
from typing import Any

import pytest
import responses

from viyapy import compat

BASE = "https://viya.example.com"


def test_importing_viya_utils_warns() -> None:
    sys.modules.pop("viyapy.viya_utils", None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("viyapy.viya_utils")
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


@responses.activate
def test_get_decision_content_warns_and_returns_raw(
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture("viya4", "decision_content.json")
    responses.add(responses.GET, f"{BASE}/decisions/flows/d1", json=raw, status=200)
    with pytest.warns(DeprecationWarning):
        result = compat.get_decision_content(BASE, "d1", "tok")
    assert result == raw


@responses.activate
def test_get_models_returns_legacy_shape(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("viya4", "decision_content.json")
    responses.add(responses.GET, f"{BASE}/decisions/flows/d1", json=raw, status=200)
    with pytest.warns(DeprecationWarning):
        models = compat.get_models(BASE, "d1", "tok")
    assert models[0] == {
        "Model Name": "Credit Scoring Model",
        "Modified By": "seford",
        "Modified Timestamp": models[0]["Modified Timestamp"],
    }
    assert set(models[0]) == {"Model Name", "Modified By", "Modified Timestamp"}


def test_gen_viya_inputs_is_json_string_without_mangling() -> None:
    with pytest.warns(DeprecationWarning):
        body = compat.gen_viya_inputs({"amount": 1000, "name": "x"})
    assert isinstance(body, str)
    assert json.loads(body) == {
        "inputs": [
            {"name": "amount", "value": 1000},
            {"name": "name", "value": "x"},
        ]
    }
    assert "amount_" not in body  # the 2.x trailing-underscore bug is gone


@responses.activate
def test_call_id_api_warns_and_returns_raw(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("viya4", "mas_execute_ok.json")
    url = f"{BASE}/microanalyticScore/modules/m/steps/execute"
    responses.add(responses.POST, url, json=raw, status=200)
    with pytest.warns(DeprecationWarning):
        result = compat.call_id_api(BASE, "tok", {"input_string": "x"}, "m")
    assert result == raw


def test_unpack_viya_outputs_handles_both_keys() -> None:
    with pytest.warns(DeprecationWarning):
        assert compat.unpack_viya_outputs({"outputs": [{"name": "a", "value": 1}]}) == {"a": 1}
    with pytest.warns(DeprecationWarning):
        assert compat.unpack_viya_outputs({"output": [{"name": "b", "value": 2}]}) == {"b": 2}


def test_unpack_viya_outputs_missing_key_returns_empty() -> None:
    with pytest.warns(DeprecationWarning):
        assert compat.unpack_viya_outputs({"executionState": "completed"}) == {}
