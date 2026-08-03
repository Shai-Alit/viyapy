"""Cross-generation happy-path smoke — the Viya version matrix (§4).

Runs the same client operations against both the viya4 and viya35 fixture sets
so each generation's response shapes (notably MAS ``output`` vs ``outputs``) are
exercised on every run, from one parametrization.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import responses

from viyapy import ViyaClient

BASE = "https://viya.example.com"
TOKEN = "test-token"


@responses.activate
def test_decision_get_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture(generation, "decision_content.json")
    responses.add(responses.GET, f"{BASE}/decisions/flows/d1", json=raw, status=200)

    client = ViyaClient(BASE, TOKEN, viya_version=version_for(generation), max_retries=0)
    decision = client.decisions.get("d1")

    assert decision.id == "d1"
    assert isinstance(decision.models, tuple)
    assert decision.raw == raw


@responses.activate
def test_mas_execute_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture(generation, "mas_execute_ok.json")
    url = f"{BASE}/microanalyticScore/modules/m/steps/execute"
    responses.add(responses.POST, url, json=raw, status=200)

    client = ViyaClient(BASE, TOKEN, viya_version=version_for(generation), max_retries=0)
    result = client.mas.execute("m", {"input_string": "x"})

    # Both generations flatten their (differently keyed) output list to a dict.
    assert isinstance(result.outputs, dict)
    assert result.outputs
    assert result.raw == raw
