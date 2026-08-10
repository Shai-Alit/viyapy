"""Unit tests for MAS execution (HTTP mocked)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
import responses

from viyapy import ViyaClient
from viyapy.exceptions import (
    ViyaConfigError,
    ViyaNotFoundError,
    ViyaResponseError,
    ViyaServerError,
)

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
@pytest.mark.parametrize("bad", ["", "   "])
def test_execute_blank_module_id_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.execute(bad, {"a": 1})
    assert len(responses.calls) == 0


@responses.activate
def test_execute_blank_step_fails_fast() -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.execute("m", {"a": 1}, step="  ")
    assert len(responses.calls) == 0


@responses.activate
def test_execute_missing_module_raises_not_found() -> None:
    url = f"{BASE}/microanalyticScore/modules/gone/steps/execute"
    responses.add(responses.POST, url, json={"message": "no"}, status=404)
    with pytest.raises(ViyaNotFoundError):
        make_client().mas.execute("gone", {"a": 1})


# -- list / get ------------------------------------------------------------


@responses.activate
@pytest.mark.parametrize("generation", ["viya4", "viya35"])
def test_list_modules_parses_items(
    generation: str, load_fixture: Callable[[str, str], Any], version_for: Callable[[str], str]
) -> None:
    raw = load_fixture(generation, "mas_modules.json")
    responses.add(responses.GET, f"{BASE}/microanalyticScore/modules", json=raw, status=200)

    modules = list(make_client(version_for(generation)).mas.list())

    assert [m.id for m in modules] == ["api_tester1_0", "risk_score2_1"]
    risk = modules[1]
    assert risk.name == "risk_score"
    assert risk.revision == 3
    assert risk.step_ids == ("execute", "score")
    assert risk.modified_by == "analyst"
    # A larger default page size is requested to reduce round trips.
    assert "limit=100" in responses.calls[0].request.url
    assert responses.calls[0].request.headers["Accept"] == "application/vnd.sas.collection+json"


@responses.activate
def test_list_modules_follows_pagination() -> None:
    page1 = {
        "items": [{"id": "m1", "name": "one"}],
        "links": [{"rel": "next", "href": "/microanalyticScore/modules?start=1&limit=1"}],
    }
    page2 = {"items": [{"id": "m2", "name": "two"}], "links": []}
    responses.add(responses.GET, f"{BASE}/microanalyticScore/modules", json=page1, status=200)
    responses.add(
        responses.GET,
        f"{BASE}/microanalyticScore/modules?start=1&limit=1",
        json=page2,
        status=200,
        match_querystring=True,
    )

    modules = list(make_client().mas.list(page_size=1))

    assert [m.id for m in modules] == ["m1", "m2"]
    assert len(responses.calls) == 2


@responses.activate
@pytest.mark.parametrize("bad", [0, -1, "10", 1.5, True])
def test_list_rejects_bad_page_size(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        list(make_client().mas.list(page_size=bad))  # type: ignore[arg-type]
    assert len(responses.calls) == 0


@responses.activate
def test_list_validates_page_size_eagerly() -> None:
    # page_size is validated when list() is called, not lazily on first
    # iteration — so the error surfaces at the call site. Note the absence of an
    # enclosing list(...): the exception must be raised without iterating.
    with pytest.raises(ViyaConfigError):
        make_client().mas.list(page_size=0)
    assert len(responses.calls) == 0


@responses.activate
def test_list_first_page_failure_raises() -> None:
    # A non-2xx on the very first page must surface as a typed error, not an
    # empty iterator.
    responses.add(
        responses.GET, f"{BASE}/microanalyticScore/modules", json={"message": "boom"}, status=500
    )
    with pytest.raises(ViyaServerError):
        list(make_client().mas.list())


@responses.activate
def test_list_later_page_failure_raises() -> None:
    # The first page yields, but a failure while fetching the next page must
    # propagate mid-iteration rather than truncating silently.
    page1 = {
        "items": [{"id": "m1", "name": "one"}],
        "links": [{"rel": "next", "href": "/microanalyticScore/modules?start=1&limit=100"}],
    }
    responses.add(responses.GET, f"{BASE}/microanalyticScore/modules", json=page1, status=200)
    responses.add(
        responses.GET,
        f"{BASE}/microanalyticScore/modules?start=1&limit=100",
        json={"message": "boom"},
        status=503,
        match_querystring=True,
    )
    iterator = make_client().mas.list()
    assert next(iterator).id == "m1"
    with pytest.raises(ViyaServerError):
        list(iterator)


@responses.activate
def test_list_item_without_id_raises_response_error() -> None:
    # A collection item missing a usable id is a malformed payload, not a
    # silently-accepted module with a false identity.
    responses.add(
        responses.GET,
        f"{BASE}/microanalyticScore/modules",
        json={"items": [{"name": "no-id-here"}], "links": []},
        status=200,
    )
    with pytest.raises(ViyaResponseError):
        list(make_client().mas.list())


@responses.activate
@pytest.mark.parametrize("generation", ["viya4", "viya35"])
def test_get_module_parses_payload(
    generation: str, load_fixture: Callable[[str, str], Any], version_for: Callable[[str], str]
) -> None:
    raw = load_fixture(generation, "mas_module.json")
    responses.add(
        responses.GET, f"{BASE}/microanalyticScore/modules/api_tester1_0", json=raw, status=200
    )

    module = make_client(version_for(generation)).mas.get("api_tester1_0")

    assert module.id == "api_tester1_0"
    assert module.name == "api_tester"
    assert module.scope == "public"
    assert module.step_ids == ("execute",)
    assert module.raw["description"] == "Published decision exposed as a MAS module"
    assert (
        responses.calls[0].request.headers["Accept"]
        == "application/vnd.sas.microanalytic.module+json"
    )


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_get_blank_module_id_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.get(bad)
    assert len(responses.calls) == 0


@responses.activate
def test_get_missing_module_raises_not_found() -> None:
    responses.add(
        responses.GET, f"{BASE}/microanalyticScore/modules/gone", json={"message": "no"}, status=404
    )
    with pytest.raises(ViyaNotFoundError):
        make_client().mas.get("gone")


@responses.activate
def test_get_module_tolerates_sparse_payload() -> None:
    # A non-int revision and an absent stepIds list must not raise; they degrade
    # to None / empty tuple.
    responses.add(
        responses.GET,
        f"{BASE}/microanalyticScore/modules/m",
        json={"id": "m", "revision": "n/a"},
        status=200,
    )
    module = make_client().mas.get("m")
    assert module.revision is None
    assert module.step_ids == ()
    assert module.name is None


@responses.activate
def test_get_module_without_id_raises_response_error() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/microanalyticScore/modules/m",
        json={"name": "orphan", "revision": 1},
        status=200,
    )
    with pytest.raises(ViyaResponseError):
        make_client().mas.get("m")


@responses.activate
def test_get_percent_encodes_reserved_chars_in_module_id() -> None:
    # A module id carrying reserved characters must be encoded into a single path
    # segment, not allowed to inject extra path/query structure.
    responses.add(
        responses.GET,
        f"{BASE}/microanalyticScore/modules/weird%2Fid%3Fx",
        json={"id": "weird/id?x"},
        status=200,
    )
    module = make_client().mas.get("weird/id?x")
    assert module.id == "weird/id?x"
    assert "/modules/weird%2Fid%3Fx" in responses.calls[0].request.url


@responses.activate
def test_execute_percent_encodes_path_segments() -> None:
    responses.add(
        responses.POST,
        f"{BASE}/microanalyticScore/modules/a%2Fb/steps/c%3Fd",
        json={"outputs": []},
        status=200,
    )
    make_client().mas.execute("a/b", {}, step="c?d")
    assert "/modules/a%2Fb/steps/c%3Fd" in responses.calls[0].request.url


# -- get_signature ---------------------------------------------------------


@responses.activate
@pytest.mark.parametrize("generation", ["viya4", "viya35"])
def test_get_signature_parses_variables(
    generation: str, load_fixture: Callable[[str, str], Any], version_for: Callable[[str], str]
) -> None:
    raw = load_fixture(generation, "mas_step_signature.json")
    url = f"{BASE}/microanalyticScore/modules/api_tester1_0/steps/execute"
    responses.add(responses.GET, url, json=raw, status=200)

    sig = make_client(version_for(generation)).mas.get_signature("api_tester1_0")

    assert sig.id == "execute"
    assert sig.module_id == "api_tester1_0"
    assert [v.name for v in sig.inputs] == ["input_string"]
    assert sig.inputs[0].type == "string"
    assert sig.inputs[0].dim == 0
    assert sig.inputs[0].size == 256
    assert [v.name for v in sig.outputs] == ["output_string"]
    assert sig.raw["version"] in (1, 2)
    assert (
        responses.calls[0].request.headers["Accept"]
        == "application/vnd.sas.microanalytic.module.step+json"
    )


@responses.activate
def test_get_signature_defaults_to_execute_step() -> None:
    url = f"{BASE}/microanalyticScore/modules/m/steps/execute"
    responses.add(responses.GET, url, json={"inputs": [], "outputs": []}, status=200)
    make_client().mas.get_signature("m")
    assert responses.calls[0].request.url.endswith("/steps/execute")


@responses.activate
def test_get_signature_custom_step_path() -> None:
    url = f"{BASE}/microanalyticScore/modules/m/steps/score"
    responses.add(responses.GET, url, json={"inputs": [], "outputs": []}, status=200)
    sig = make_client().mas.get_signature("m", step="score")
    assert responses.calls[0].request.url.endswith("/steps/score")
    # Identity falls back to the requested ids when the payload omits them.
    assert sig.id == "score"
    assert sig.module_id == "m"


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_get_signature_blank_module_id_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.get_signature(bad)
    assert len(responses.calls) == 0


@responses.activate
def test_get_signature_blank_step_fails_fast() -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.get_signature("m", step="  ")
    assert len(responses.calls) == 0


@responses.activate
def test_get_signature_missing_step_raises_not_found() -> None:
    url = f"{BASE}/microanalyticScore/modules/m/steps/gone"
    responses.add(responses.GET, url, json={"message": "no"}, status=404)
    with pytest.raises(ViyaNotFoundError):
        make_client().mas.get_signature("m", step="gone")


@responses.activate
def test_get_signature_malformed_payload_raises_response_error() -> None:
    # Neither an inputs nor an outputs list — not a usable signature.
    url = f"{BASE}/microanalyticScore/modules/m/steps/execute"
    responses.add(responses.GET, url, json={"id": "execute"}, status=200)
    with pytest.raises(ViyaResponseError):
        make_client().mas.get_signature("m")


@responses.activate
def test_get_signature_tolerates_sparse_and_nameless_variables() -> None:
    # A nameless entry is skipped; non-int dim/size and a missing type degrade to
    # None rather than raising. An outputs-only payload is still a valid signature.
    url = f"{BASE}/microanalyticScore/modules/m/steps/execute"
    responses.add(
        responses.GET,
        url,
        json={
            "inputs": [
                {"type": "string"},  # nameless — skipped
                {"name": "x", "dim": "n/a", "size": None},  # sparse — degrades
            ],
            "outputs": [{"name": "y", "type": "decimal", "dim": 0, "size": 8}],
        },
        status=200,
    )
    sig = make_client().mas.get_signature("m")
    assert [v.name for v in sig.inputs] == ["x"]
    assert sig.inputs[0].type is None
    assert sig.inputs[0].dim is None
    assert sig.inputs[0].size is None
    assert sig.outputs[0].size == 8


@responses.activate
def test_get_signature_skips_non_mapping_and_non_list_arrays() -> None:
    # `inputs` is a list holding a non-mapping entry (skipped), and `outputs` is
    # present but not a list (degrades to an empty tuple) — a signature with only
    # a valid `inputs` list is still usable, so this must not raise.
    url = f"{BASE}/microanalyticScore/modules/m/steps/execute"
    responses.add(
        responses.GET,
        url,
        json={"inputs": ["not-a-mapping", {"name": "x"}], "outputs": "nope"},
        status=200,
    )
    sig = make_client().mas.get_signature("m")
    assert [v.name for v in sig.inputs] == ["x"]
    assert sig.outputs == ()


@responses.activate
def test_get_signature_percent_encodes_path_segments() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/microanalyticScore/modules/a%2Fb/steps/c%3Fd",
        json={"inputs": [], "outputs": []},
        status=200,
    )
    make_client().mas.get_signature("a/b", step="c?d")
    assert "/modules/a%2Fb/steps/c%3Fd" in responses.calls[0].request.url
