"""Unit tests for decision-flow operations (HTTP mocked)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import responses

from viyapy import ViyaClient
from viyapy.exceptions import ViyaConfigError, ViyaNotFoundError, ViyaResponseError

BASE = "https://viya.example.com"


def make_client(version: str = "4") -> ViyaClient:
    return ViyaClient(BASE, "tok", viya_version=version, max_retries=0)


@responses.activate
def test_get_decision_parses_and_sends_media_type(
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture("viya4", "decision_content.json")
    responses.add(responses.GET, f"{BASE}/decisions/flows/abc-123-decision", json=raw, status=200)

    decision = make_client().decisions.get("abc-123-decision")

    assert decision.name == "Sample Credit Decision"
    assert [m.name for m in decision.models] == ["Credit Scoring Model", "Fraud Model"]
    assert responses.calls[0].request.headers["Accept"] == "application/vnd.sas.decision+json"


@responses.activate
def test_list_models_returns_model_steps(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("viya4", "decision_content.json")
    responses.add(responses.GET, f"{BASE}/decisions/flows/d1", json=raw, status=200)
    models = make_client().decisions.list_models("d1")
    assert models[0].modified_by == "seford"


@responses.activate
def test_get_decision_viya35_generation(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("viya35", "decision_content.json")
    responses.add(responses.GET, f"{BASE}/decisions/flows/d1", json=raw, status=200)
    decision = make_client("3.5").decisions.get("d1")
    assert decision.id == "d1"
    assert decision.raw == raw


@responses.activate
@pytest.mark.parametrize("bad_id", ["", "   "])
def test_get_blank_decision_id_fails_fast(bad_id: str) -> None:
    # Validation must raise before any HTTP call; responses would error on one.
    with pytest.raises(ViyaConfigError):
        make_client().decisions.get(bad_id)
    assert len(responses.calls) == 0


@responses.activate
def test_get_missing_decision_raises_not_found() -> None:
    responses.add(responses.GET, f"{BASE}/decisions/flows/nope", json={"message": "no"}, status=404)
    with pytest.raises(ViyaNotFoundError):
        make_client().decisions.get("nope")


@responses.activate
def test_non_json_decision_body_raises_response_error() -> None:
    responses.add(
        responses.GET, f"{BASE}/decisions/flows/d1", body="<html>not json</html>", status=200
    )
    with pytest.raises(ViyaResponseError):
        make_client().decisions.get("d1")


@responses.activate
def test_json_but_non_object_decision_body_raises_response_error() -> None:
    # Valid JSON, wrong shape: an array (or any non-object) must raise a typed
    # ViyaResponseError rather than blowing up later in the dialect parser.
    responses.add(responses.GET, f"{BASE}/decisions/flows/d1", json=[1, 2, 3], status=200)
    with pytest.raises(ViyaResponseError):
        make_client().decisions.get("d1")
