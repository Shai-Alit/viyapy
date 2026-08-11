"""Unit tests for decision-flow operations (HTTP mocked)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import responses

from viyapy import Decision, DecisionSummary, Revision, ViyaClient
from viyapy.exceptions import ViyaConfigError, ViyaNotFoundError, ViyaResponseError

BASE = "https://viya.example.com"
_FLOWS_URL = f"{BASE}/decisions/flows"
_REVISIONS_URL = f"{BASE}/decisions/flows/hmeq-credit-decision/revisions"


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


# -- get: current-revision metadata -----------------------------------------


@responses.activate
def test_get_decision_surfaces_revision_metadata(
    load_fixture: Callable[[str, str], Any],
) -> None:
    # A plain get returns the current revision; the major/minor/checkout metadata
    # must be surfaced when the payload carries it (the revision fixture is a full
    # decision payload with that metadata present).
    raw = load_fixture("viya4", "decision_revision.json")
    responses.add(
        responses.GET, f"{BASE}/decisions/flows/hmeq-credit-decision", json=raw, status=200
    )
    decision = make_client().decisions.get("hmeq-credit-decision")
    assert decision.major_revision == 1
    assert decision.minor_revision == 1
    assert decision.checkout is False


@responses.activate
def test_get_decision_without_revision_metadata_is_none(
    load_fixture: Callable[[str, str], Any],
) -> None:
    # The plain decision_content fixture omits revision metadata; the fields must
    # default to None rather than raising or coercing.
    raw = load_fixture("viya4", "decision_content.json")
    responses.add(responses.GET, f"{BASE}/decisions/flows/abc-123-decision", json=raw, status=200)
    decision = make_client().decisions.get("abc-123-decision")
    assert decision.major_revision is None
    assert decision.minor_revision is None
    assert decision.checkout is None


# -- revisions --------------------------------------------------------------


@responses.activate
@pytest.mark.parametrize("generation", ["viya4", "viya35"])
def test_revisions_parses_summaries(
    generation: str, load_fixture: Callable[[str, str], Any]
) -> None:
    raw = load_fixture(generation, "decision_revisions.json")
    version = "4" if generation == "viya4" else "3.5"
    flow_id, first_id = (
        ("hmeq-credit-decision", "hmeq-rev-0002")
        if generation == "viya4"
        else ("def-456-decision", "legacy-rev-0002")
    )
    url = f"{BASE}/decisions/flows/{flow_id}/revisions"
    responses.add(responses.GET, url, json=raw, status=200)

    revisions = list(make_client(version).decisions.revisions(flow_id))

    assert all(isinstance(r, Revision) for r in revisions)
    first = revisions[0]
    assert first.id == first_id
    assert first.major_revision == raw["items"][0]["majorRevision"]
    assert first.minor_revision == raw["items"][0]["minorRevision"]
    assert first.checkout is False
    assert first.label == f"{first.major_revision}.{first.minor_revision}"
    # A larger default page size is requested and the collection media type sent.
    assert "limit=100" in responses.calls[0].request.url
    assert responses.calls[0].request.headers["Accept"] == "application/vnd.sas.collection+json"


@responses.activate
def test_revisions_follows_pagination() -> None:
    next_href = "/decisions/flows/hmeq-credit-decision/revisions?start=1&limit=1"
    page1 = {
        "items": [{"id": "r1", "majorRevision": 1, "minorRevision": 0}],
        "links": [{"rel": "next", "href": next_href}],
    }
    page2 = {"items": [{"id": "r2", "majorRevision": 1, "minorRevision": 1}], "links": []}
    responses.add(responses.GET, _REVISIONS_URL, json=page1, status=200)
    responses.add(
        responses.GET,
        f"{_REVISIONS_URL}?start=1&limit=1",
        json=page2,
        status=200,
        match_querystring=True,
    )

    revisions = list(make_client().decisions.revisions("hmeq-credit-decision", page_size=1))

    assert [r.id for r in revisions] == ["r1", "r2"]
    assert len(responses.calls) == 2


@responses.activate
@pytest.mark.parametrize("bad_id", ["", "   "])
def test_revisions_blank_flow_id_fails_fast(bad_id: str) -> None:
    with pytest.raises(ViyaConfigError):
        list(make_client().decisions.revisions(bad_id))
    assert len(responses.calls) == 0


@responses.activate
@pytest.mark.parametrize("bad", [0, -1, "10", 1.5, True])
def test_revisions_rejects_bad_page_size(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        list(make_client().decisions.revisions("d1", page_size=bad))  # type: ignore[arg-type]
    assert len(responses.calls) == 0


@responses.activate
def test_revisions_raises_on_item_without_id() -> None:
    responses.add(responses.GET, _REVISIONS_URL, json={"items": [{"majorRevision": 1}]}, status=200)
    with pytest.raises(ViyaResponseError):
        list(make_client().decisions.revisions("hmeq-credit-decision"))


# -- get_revision -----------------------------------------------------------


@responses.activate
def test_get_revision_returns_decision_at_revision(
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture("viya4", "decision_revision.json")
    url = f"{BASE}/decisions/flows/hmeq-credit-decision/revisions/hmeq-rev-0002"
    responses.add(responses.GET, url, json=raw, status=200)

    decision = make_client().decisions.get_revision("hmeq-credit-decision", "hmeq-rev-0002")

    assert isinstance(decision, Decision)
    # The Decision.id is the revision id (the full-revision payload's own id).
    assert decision.id == "hmeq-rev-0002"
    assert decision.name == "HMEQ Credit Decision"
    assert [m.name for m in decision.models] == ["Credit Scoring Model", "Fraud Model"]
    assert decision.major_revision == 1
    assert decision.minor_revision == 1
    assert responses.calls[0].request.headers["Accept"] == "application/vnd.sas.decision+json"


@responses.activate
@pytest.mark.parametrize("bad_id", ["", "   "])
def test_get_revision_blank_ids_fail_fast(bad_id: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().decisions.get_revision("d1", bad_id)
    with pytest.raises(ViyaConfigError):
        make_client().decisions.get_revision(bad_id, "r1")
    assert len(responses.calls) == 0


@responses.activate
def test_get_revision_percent_encodes_ids() -> None:
    raw = {"id": "weird/rev", "name": "n", "flow": {"steps": []}}
    responses.add(
        responses.GET,
        f"{BASE}/decisions/flows/weird%2Fid/revisions/weird%2Frev",
        json=raw,
        status=200,
    )
    decision = make_client().decisions.get_revision("weird/id", "weird/rev")
    assert decision.id == "weird/rev"
    url = responses.calls[0].request.url
    assert "/decisions/flows/weird%2Fid/revisions/weird%2Frev" in url


@responses.activate
def test_get_revision_missing_raises_not_found() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/decisions/flows/d1/revisions/nope",
        json={"message": "no"},
        status=404,
    )
    with pytest.raises(ViyaNotFoundError):
        make_client().decisions.get_revision("d1", "nope")


# -- decision code (raw DS2 text) ------------------------------------------

_DS2 = "ds2_options scond=WARNING;\npackage p; method run(); end; endpackage;"


@responses.activate
def test_get_code_returns_raw_ds2_text() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/decisions/flows/hmeq-credit-decision/code",
        body=_DS2,
        status=200,
        content_type="text/vnd.sas.source.ds2;charset=UTF-8",
    )

    code = make_client().decisions.get_code("hmeq-credit-decision")

    assert code == _DS2
    assert responses.calls[0].request.headers["Accept"] == "text/vnd.sas.source.ds2"


@responses.activate
@pytest.mark.parametrize("bad_id", ["", "   "])
def test_get_code_blank_id_fails_fast(bad_id: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().decisions.get_code(bad_id)
    assert len(responses.calls) == 0


@responses.activate
def test_get_code_percent_encodes_id() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/decisions/flows/weird%2Fid/code",
        body=_DS2,
        status=200,
    )
    make_client().decisions.get_code("weird/id")
    assert "/decisions/flows/weird%2Fid/code" in responses.calls[0].request.url


@responses.activate
def test_get_code_missing_raises_not_found() -> None:
    responses.add(
        responses.GET, f"{BASE}/decisions/flows/nope/code", json={"message": "no"}, status=404
    )
    with pytest.raises(ViyaNotFoundError):
        make_client().decisions.get_code("nope")


@responses.activate
def test_get_revision_code_returns_text_at_revision() -> None:
    url = f"{BASE}/decisions/flows/hmeq-credit-decision/revisions/hmeq-rev-0002/code"
    responses.add(responses.GET, url, body=_DS2, status=200)

    code = make_client().decisions.get_revision_code("hmeq-credit-decision", "hmeq-rev-0002")

    assert code == _DS2
    assert responses.calls[0].request.headers["Accept"] == "text/vnd.sas.source.ds2"


@responses.activate
@pytest.mark.parametrize("bad_id", ["", "   "])
def test_get_revision_code_blank_ids_fail_fast(bad_id: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().decisions.get_revision_code("d1", bad_id)
    with pytest.raises(ViyaConfigError):
        make_client().decisions.get_revision_code(bad_id, "r1")
    assert len(responses.calls) == 0


@responses.activate
def test_get_revision_code_percent_encodes_ids() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/decisions/flows/weird%2Fid/revisions/weird%2Frev/code",
        body=_DS2,
        status=200,
    )
    make_client().decisions.get_revision_code("weird/id", "weird/rev")
    url = responses.calls[0].request.url
    assert "/decisions/flows/weird%2Fid/revisions/weird%2Frev/code" in url
