"""Unit tests for MAS execution (HTTP mocked)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
import responses

from viyapy import ViyaClient
from viyapy.exceptions import ViyaNotFoundError

BASE = "https://viya.example.com"


def make_client(version: str = "4") -> ViyaClient:
    return ViyaClient(BASE, "tok", viya_version=version, max_retries=0)


@responses.activate
def test_execute_posts_inputs_and_parses_outputs(
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture("viya4", "mas_execute_ok.json")
    url = f"{BASE}/microanalyticScore/modules/api_tester1_0/steps/execute"
    responses.add(responses.POST, url, json=raw, status=200)

    result = make_client().mas.execute("api_tester1_0", {"input_string": "this is a test"})

    assert result.outputs["output_string"] == "successfully ran decision flow"
    sent = json.loads(responses.calls[0].request.body)
    assert sent == {"inputs": [{"name": "input_string", "value": "this is a test"}]}
    assert responses.calls[0].request.headers["Content-Type"] == "application/json"


@responses.activate
def test_execute_viya35_output_shape(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("viya35", "mas_execute_ok.json")  # uses singular "output"
    url = f"{BASE}/microanalyticScore/modules/m/steps/execute"
    responses.add(responses.POST, url, json=raw, status=200)
    result = make_client("3.5").mas.execute("m", {"input_string": "x"})
    assert result.outputs["input_string"] == "this is a test"


@responses.activate
def test_execute_custom_step_path() -> None:
    url = f"{BASE}/microanalyticScore/modules/m/steps/score"
    responses.add(responses.POST, url, json={"outputs": []}, status=200)
    make_client().mas.execute("m", {}, step="score")
    assert responses.calls[0].request.url.endswith("/steps/score")


@responses.activate
def test_execute_missing_module_raises_not_found() -> None:
    url = f"{BASE}/microanalyticScore/modules/gone/steps/execute"
    responses.add(responses.POST, url, json={"message": "no"}, status=404)
    with pytest.raises(ViyaNotFoundError):
        make_client().mas.execute("gone", {"a": 1})
