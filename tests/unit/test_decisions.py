"""Unit tests for decision-flow operations (HTTP mocked)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import responses

from viyapy import DecisionSummary, ViyaClient
from viyapy.exceptions import ViyaConfigError, ViyaNotFoundError, ViyaResponseError

BASE = "https://viya.example.com"
_FLOWS_URL = f"{BASE}/decisions/flows"


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
def test_get_percent_encodes_reserved_chars_in_decision_id() -> None:
    # A decision id carrying reserved characters must be encoded into a single
    # path segment, not allowed to inject extra path/query structure.
    raw = {"id": "weird/id?x", "name": "n", "flow": {"steps": []}}
    responses.add(responses.GET, f"{BASE}/decisions/flows/weird%2Fid%3Fx", json=raw, status=200)
    decision = make_client().decisions.get("weird/id?x")
    assert decision.id == "weird/id?x"
    assert "/decisions/flows/weird%2Fid%3Fx" in responses.calls[0].request.url


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


# -- list -------------------------------------------------------------------


@responses.activate
@pytest.mark.parametrize("generation", ["viya4", "viya35"])
def test_list_flows_parses_summaries(
    generation: str, load_fixture: Callable[[str, str], Any]
) -> None:
    raw = load_fixture(generation, "decision_flows.json")
    responses.add(responses.GET, _FLOWS_URL, json=raw, status=200)

    version = "4" if generation == "viya4" else "3.5"
    flows = list(make_client(version).decisions.list())

    assert [f.id for f in flows] == ["hmeq-credit-decision", "nbo-offer-flow"]
    assert all(isinstance(f, DecisionSummary) for f in flows)
    hmeq = flows[0]
    assert hmeq.name == "HMEQ Credit Decision"
    assert hmeq.description == "Demo home-equity loan decision flow"
    assert hmeq.type == "decision"
    assert hmeq.created_by == "sasdemo"
    assert hmeq.modified_by == "sasdemo"
    assert hmeq.creation_timestamp == "2026-06-24T01:58:36.651Z"
    assert hmeq.modified_timestamp == "2026-06-24T02:23:05.809Z"
    # The second item omits description; it must parse to None, not "".
    assert flows[1].description is None
    # A larger default page size is requested to reduce round trips, and the
    # collection media type is sent.
    assert "limit=100" in responses.calls[0].request.url
    assert responses.calls[0].request.headers["Accept"] == "application/vnd.sas.collection+json"


@responses.activate
def test_list_flows_follows_pagination() -> None:
    page1 = {
        "items": [{"id": "d1", "name": "one"}],
        "links": [{"rel": "next", "href": "/decisions/flows?start=1&limit=1"}],
    }
    page2 = {"items": [{"id": "d2", "name": "two"}], "links": []}
    responses.add(responses.GET, _FLOWS_URL, json=page1, status=200)
    responses.add(
        responses.GET,
        f"{_FLOWS_URL}?start=1&limit=1",
        json=page2,
        status=200,
        match_querystring=True,
    )

    flows = list(make_client().decisions.list(page_size=1))

    assert [f.id for f in flows] == ["d1", "d2"]
    assert len(responses.calls) == 2


@responses.activate
@pytest.mark.parametrize("bad", [0, -1, "10", 1.5, True])
def test_list_flows_rejects_bad_page_size(bad: object) -> None:
    # Validation must raise before any HTTP call; responses would error on one.
    with pytest.raises(ViyaConfigError):
        list(make_client().decisions.list(page_size=bad))  # type: ignore[arg-type]
    assert len(responses.calls) == 0


@responses.activate
def test_list_flows_raises_on_item_without_id() -> None:
    # A malformed item (no usable id) must fail loudly rather than yield a
    # summary with a false identity.
    responses.add(responses.GET, _FLOWS_URL, json={"items": [{"name": "no id"}]}, status=200)
    with pytest.raises(ViyaResponseError):
        list(make_client().decisions.list())
