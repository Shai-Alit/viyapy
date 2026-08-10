"""Unit tests for MAS execution (HTTP mocked)."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Any

import pytest
import responses

from viyapy import ModuleSource, StepSignature, ValidationResult, Variable, ViyaClient
from viyapy.exceptions import (
    ViyaAPIError,
    ViyaConfigError,
    ViyaNotFoundError,
    ViyaResponseError,
    ViyaServerError,
    ViyaValidationError,
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


# -- execution modes: wait_time / submit -----------------------------------

_EXEC_URL = f"{BASE}/microanalyticScore/modules/m/steps/execute"


@responses.activate
def test_execute_default_sends_no_wait_time() -> None:
    responses.add(responses.POST, _EXEC_URL, json={"outputs": [], "executionState": "completed"})
    make_client().mas.execute("m", {"a": 1})
    assert "waitTime" not in (responses.calls[0].request.url or "")


@responses.activate
def test_execute_timed_sends_wait_time_query() -> None:
    responses.add(responses.POST, _EXEC_URL, json={"outputs": [], "executionState": "completed"})
    make_client().mas.execute("m", {"a": 1}, wait_time=500)
    assert "waitTime=500" in responses.calls[0].request.url


@responses.activate
def test_execute_timed_out_parses_empty_outputs() -> None:
    # A timed run that ran long: no output list, executionState timedOut.
    responses.add(responses.POST, _EXEC_URL, json={"executionState": "timedOut"})
    result = make_client().mas.execute("m", {"a": 1}, wait_time=1)
    assert result.timed_out is True
    assert result.completed is False
    assert result.outputs == {}


@responses.activate
def test_submit_sends_wait_time_zero_and_reports_submitted() -> None:
    responses.add(responses.POST, _EXEC_URL, json={"executionState": "submitted"})
    result = make_client().mas.submit("m", {"a": 1})
    assert "waitTime=0" in responses.calls[0].request.url
    assert result.submitted is True
    assert result.completed is False
    assert result.outputs == {}


@responses.activate
def test_execute_wait_time_zero_matches_submit() -> None:
    responses.add(responses.POST, _EXEC_URL, json={"executionState": "submitted"})
    result = make_client().mas.execute("m", {"a": 1}, wait_time=0)
    assert "waitTime=0" in responses.calls[0].request.url
    assert result.submitted is True


@responses.activate
@pytest.mark.parametrize("bad", [-1, 1.5, "500", True])
def test_execute_bad_wait_time_fails_fast(bad: Any) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.execute("m", {"a": 1}, wait_time=bad)
    assert len(responses.calls) == 0


@responses.activate
def test_execute_completed_without_output_list_still_raises() -> None:
    # A *completed* response with no output list is a real error, not tolerated.
    responses.add(responses.POST, _EXEC_URL, json={"executionState": "completed"})
    with pytest.raises(ViyaResponseError):
        make_client().mas.execute("m", {"a": 1})


@responses.activate
@pytest.mark.parametrize("state", ["timedOut", "submitted"])
def test_execute_async_states_parse_empty_on_viya35(state: str) -> None:
    # The async-mode tolerance lives in the shared base dialect and keys only on
    # executionState, so an empty async response parses on Viya 3.5 too — even
    # though 3.5 carries synchronous outputs under `output` (singular), not
    # `outputs`. Guards against the output-vs-outputs shape bug this lib has a
    # history with regressing.
    responses.add(responses.POST, _EXEC_URL, json={"executionState": state})
    result = make_client("3.5").mas.execute("m", {"a": 1}, wait_time=1)
    assert result.execution_state == state
    assert result.outputs == {}


@responses.activate
def test_execute_timed_completion_uses_singular_output_on_viya35() -> None:
    # A timed run that *does* finish on Viya 3.5 returns outputs under the
    # singular `output` key; confirm the dialect still flattens them.
    responses.add(
        responses.POST,
        _EXEC_URL,
        json={"executionState": "completed", "output": [{"name": "y", "value": 1}]},
    )
    result = make_client("3.5").mas.execute("m", {"a": 1}, wait_time=500)
    assert result.completed is True
    assert result.outputs == {"y": 1}


# -- binary (b64) I/O ------------------------------------------------------


@responses.activate
@pytest.mark.parametrize("payload", [b"\x00\x01\x02hello", bytearray(b"\x00\x01\x02hello")])
def test_execute_binary_input_sent_as_b64(payload: bytes | bytearray) -> None:
    # A bytes/bytearray value is base64-encoded with encoding: "b64" on the wire.
    responses.add(responses.POST, _EXEC_URL, json={"outputs": [], "executionState": "completed"})
    make_client().mas.execute("m", {"blob": payload, "n": 7})
    sent = json.loads(responses.calls[0].request.body)
    expected_b64 = base64.b64encode(bytes(payload)).decode("ascii")
    assert {"name": "blob", "value": expected_b64, "encoding": "b64"} in sent["inputs"]
    # Scalar inputs are untouched — no stray encoding key.
    assert {"name": "n", "value": 7} in sent["inputs"]


@responses.activate
def test_execute_b64_output_decoded_to_bytes() -> None:
    blob = b"\x00\x01\x02hello"
    responses.add(
        responses.POST,
        _EXEC_URL,
        json={
            "executionState": "completed",
            "outputs": [
                {
                    "name": "blob_out",
                    "value": base64.b64encode(blob).decode("ascii"),
                    "encoding": "b64",
                },
                {"name": "n", "value": 3},
            ],
        },
    )
    result = make_client().mas.execute("m", {"a": 1})
    assert result.outputs["blob_out"] == blob
    assert isinstance(result.outputs["blob_out"], bytes)
    assert result.outputs["n"] == 3  # scalar output passes through


@responses.activate
def test_execute_invalid_b64_output_raises() -> None:
    responses.add(
        responses.POST,
        _EXEC_URL,
        json={
            "executionState": "completed",
            "outputs": [{"name": "blob", "value": "not valid base64!!", "encoding": "b64"}],
        },
    )
    with pytest.raises(ViyaResponseError):
        make_client().mas.execute("m", {"a": 1})


@responses.activate
def test_execute_b64_output_non_string_value_raises() -> None:
    responses.add(
        responses.POST,
        _EXEC_URL,
        json={
            "executionState": "completed",
            "outputs": [{"name": "blob", "value": 123, "encoding": "b64"}],
        },
    )
    with pytest.raises(ViyaResponseError):
        make_client().mas.execute("m", {"a": 1})


@responses.activate
def test_execute_b64_output_and_metadata_on_viya35() -> None:
    # The binary decode and metadata echo live in the shared Dialect base, so they
    # must work on Viya 3.5 too — where synchronous outputs come back under the
    # singular `output` key. This guards against a future per-generation override
    # silently breaking 3.5 (per PRODUCTION_PLAN's Viya-version-matrix principle).
    blob = b"\x00\x01\x02hello"
    responses.add(
        responses.POST,
        _EXEC_URL,
        json={
            "executionState": "completed",
            "output": [
                {
                    "name": "blob_out",
                    "value": base64.b64encode(blob).decode("ascii"),
                    "encoding": "b64",
                },
                {"name": "n", "value": 3},
            ],
            "metadata": {"client_id": "cid", "transaction_id": "txn"},
        },
    )
    result = make_client("3.5").mas.execute(
        "m", {"blob": blob}, client_id="cid", transaction_id="txn"
    )
    assert result.outputs["blob_out"] == blob
    assert isinstance(result.outputs["blob_out"], bytes)
    assert result.outputs["n"] == 3
    assert (result.client_id, result.transaction_id) == ("cid", "txn")
    sent = json.loads(responses.calls[0].request.body)
    expected_b64 = base64.b64encode(blob).decode("ascii")
    assert {"name": "blob", "value": expected_b64, "encoding": "b64"} in sent["inputs"]
    assert sent["metadata"] == {"client_id": "cid", "transaction_id": "txn"}


# -- execution metadata (client_id / transaction_id) -----------------------


@responses.activate
def test_execute_sends_metadata_object_when_ids_given() -> None:
    responses.add(responses.POST, _EXEC_URL, json={"outputs": [], "executionState": "completed"})
    make_client().mas.execute("m", {"a": 1}, client_id="cid", transaction_id="txn")
    sent = json.loads(responses.calls[0].request.body)
    assert sent["metadata"] == {"client_id": "cid", "transaction_id": "txn"}


@responses.activate
def test_execute_omits_metadata_when_no_ids() -> None:
    responses.add(responses.POST, _EXEC_URL, json={"outputs": [], "executionState": "completed"})
    make_client().mas.execute("m", {"a": 1})
    sent = json.loads(responses.calls[0].request.body)
    assert "metadata" not in sent


@responses.activate
def test_execute_sends_only_given_metadata_id() -> None:
    responses.add(responses.POST, _EXEC_URL, json={"outputs": [], "executionState": "completed"})
    make_client().mas.execute("m", {"a": 1}, transaction_id="txn")
    sent = json.loads(responses.calls[0].request.body)
    assert sent["metadata"] == {"transaction_id": "txn"}


@responses.activate
def test_execute_parses_metadata_from_response() -> None:
    responses.add(
        responses.POST,
        _EXEC_URL,
        json={
            "executionState": "completed",
            "outputs": [],
            "metadata": {
                "transaction_id": "txn",
                "module_id": "m",
                "step_id": "execute",
                "client_id": "cid",
            },
        },
    )
    result = make_client().mas.execute("m", {"a": 1}, client_id="cid", transaction_id="txn")
    assert result.client_id == "cid"
    assert result.transaction_id == "txn"


@responses.activate
def test_execute_metadata_absent_in_response_is_none() -> None:
    responses.add(responses.POST, _EXEC_URL, json={"outputs": [], "executionState": "completed"})
    result = make_client().mas.execute("m", {"a": 1})
    assert result.client_id is None
    assert result.transaction_id is None


@responses.activate
@pytest.mark.parametrize("field", ["client_id", "transaction_id"])
@pytest.mark.parametrize("bad", ["", "   ", 5, True])
def test_execute_bad_metadata_id_fails_fast(field: str, bad: Any) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.execute("m", {"a": 1}, **{field: bad})
    assert len(responses.calls) == 0


@responses.activate
def test_submit_threads_metadata() -> None:
    responses.add(responses.POST, _EXEC_URL, json={"executionState": "submitted"})
    make_client().mas.submit("m", {"a": 1}, client_id="cid", transaction_id="txn")
    sent = json.loads(responses.calls[0].request.body)
    assert sent["metadata"] == {"client_id": "cid", "transaction_id": "txn"}
    assert "waitTime=0" in responses.calls[0].request.url


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


# -- validate (client-side) ------------------------------------------------


_SIG_URL = f"{BASE}/microanalyticScore/modules/m/steps/execute"
_ONE_INPUT_SIG = {
    "id": "execute",
    "moduleId": "m",
    "inputs": [{"name": "input_string", "type": "string", "dim": 0, "size": 256}],
    "outputs": [{"name": "output_string", "type": "string", "dim": 0, "size": 256}],
}


@responses.activate
def test_validate_passes_when_inputs_match() -> None:
    responses.add(responses.GET, _SIG_URL, json=_ONE_INPUT_SIG, status=200)
    sig = make_client().mas.validate("m", {"input_string": "hi"})
    # Returns the fetched signature and issues exactly the one signature GET.
    assert sig.id == "execute"
    assert [v.name for v in sig.inputs] == ["input_string"]
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "GET"


@responses.activate
def test_validate_raises_on_missing_input() -> None:
    responses.add(responses.GET, _SIG_URL, json=_ONE_INPUT_SIG, status=200)
    with pytest.raises(ViyaValidationError) as excinfo:
        make_client().mas.validate("m", {})
    err = excinfo.value
    assert err.missing == ("input_string",)
    assert err.unexpected == ()
    assert err.module_id == "m"
    assert err.step == "execute"
    assert "missing required input(s): input_string" in str(err)


@responses.activate
def test_validate_raises_on_unexpected_input() -> None:
    responses.add(responses.GET, _SIG_URL, json=_ONE_INPUT_SIG, status=200)
    with pytest.raises(ViyaValidationError) as excinfo:
        make_client().mas.validate("m", {"input_string": "hi", "bogus": 1})
    err = excinfo.value
    assert err.missing == ()
    assert err.unexpected == ("bogus",)
    assert "unexpected input(s): bogus" in str(err)


@responses.activate
def test_validate_reports_both_missing_and_unexpected_sorted() -> None:
    responses.add(
        responses.GET,
        _SIG_URL,
        json={"id": "execute", "moduleId": "m", "inputs": [{"name": "a"}, {"name": "b"}]},
        status=200,
    )
    with pytest.raises(ViyaValidationError) as excinfo:
        make_client().mas.validate("m", {"a": 1, "z": 2, "y": 3})
    err = excinfo.value
    assert err.missing == ("b",)
    assert err.unexpected == ("y", "z")  # sorted, deterministic


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_validate_blank_module_id_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.validate(bad, {"a": 1})
    assert len(responses.calls) == 0


@responses.activate
def test_execute_with_validate_checks_then_executes() -> None:
    responses.add(responses.GET, _SIG_URL, json=_ONE_INPUT_SIG, status=200)
    responses.add(
        responses.POST, _SIG_URL, json={"outputs": [{"name": "output_string", "value": "ok"}]}
    )
    result = make_client().mas.execute("m", {"input_string": "hi"}, validate=True)
    assert result.outputs["output_string"] == "ok"
    # A signature GET precedes the execute POST.
    assert [c.request.method for c in responses.calls] == ["GET", "POST"]


@responses.activate
def test_execute_with_validate_raises_and_skips_post() -> None:
    responses.add(responses.GET, _SIG_URL, json=_ONE_INPUT_SIG, status=200)
    responses.add(responses.POST, _SIG_URL, json={"outputs": []})
    with pytest.raises(ViyaValidationError):
        make_client().mas.execute("m", {"wrong": 1}, validate=True)
    # The mismatch is caught before executing: only the signature GET happened.
    assert [c.request.method for c in responses.calls] == ["GET"]


@responses.activate
def test_execute_validate_forwards_timeout_to_signature_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A caller-supplied timeout must also protect the pre-flight signature GET,
    # not only the execute POST.
    responses.add(responses.POST, _SIG_URL, json={"outputs": []})
    client = make_client()
    captured: dict[str, Any] = {}

    def spy(module_id: str, step: str = "execute", *, timeout: Any = None) -> StepSignature:
        captured["timeout"] = timeout
        return StepSignature(id=step, module_id=module_id, inputs=(Variable("input_string"),))

    monkeypatch.setattr(client.mas, "get_signature", spy)
    client.mas.execute("m", {"input_string": "x"}, validate=True, timeout=(1.0, 2.0))
    assert captured["timeout"] == (1.0, 2.0)


@responses.activate
def test_execute_without_validate_makes_single_request() -> None:
    # The default path stays a single POST — no signature round trip.
    responses.add(responses.POST, _SIG_URL, json={"outputs": []})
    make_client().mas.execute("m", {"anything": 1})
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "POST"


# -- validate_remote (server-side) -----------------------------------------


_VAL_URL = f"{BASE}/microanalyticScore/commons/validations/modules/m/steps/execute"
# A SAS error object as returned in the body of a 201 when the payload is invalid.
_INVALID_BODY = {
    "version": 1,
    "valid": False,
    "error": {
        "message": "Validation failed.",
        "details": ["input_string is required"],
        "errors": [{"message": "input_string: missing required value"}],
    },
}


@responses.activate
@pytest.mark.parametrize("generation", ["viya4", "viya35"])
def test_validate_remote_valid(
    generation: str, load_fixture: Callable[[str, str], Any], version_for: Callable[[str], str]
) -> None:
    raw = load_fixture(generation, "mas_validation.json")
    responses.add(responses.POST, _VAL_URL, json=raw, status=201)

    result = make_client(version_for(generation)).mas.validate_remote("m", {"input_string": "hi"})

    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.version in (1, 2)  # per-generation resource version
    assert result.messages == ()
    assert result.module_id == "m"
    assert result.step == "execute"
    # One POST, to the validations endpoint, with the right media types and body.
    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert request.method == "POST"
    assert request.headers["Accept"] == "application/vnd.sas.validation+json"
    assert (
        request.headers["Content-Type"]
        == "application/vnd.sas.microanalytic.module.step.input+json"
    )
    assert json.loads(request.body) == {"inputs": [{"name": "input_string", "value": "hi"}]}


@responses.activate
def test_validate_remote_invalid_raises_with_messages() -> None:
    # SAS reports an invalid payload as a 201 with valid:false, not a 4xx.
    responses.add(responses.POST, _VAL_URL, json=_INVALID_BODY, status=201)
    with pytest.raises(ViyaValidationError) as excinfo:
        make_client().mas.validate_remote("m", {"wrong": 1})
    err = excinfo.value
    # Server messages are flattened (top-level, details, and nested errors).
    assert "Validation failed." in err.messages
    assert "input_string is required" in err.messages
    assert "input_string: missing required value" in err.messages
    assert err.module_id == "m"
    assert err.step == "execute"
    assert err.response_body == _INVALID_BODY
    # Client-side name partition is empty for a server-side failure.
    assert err.missing == ()
    assert err.unexpected == ()
    assert "MAS rejected the inputs" in str(err)


@responses.activate
def test_validate_remote_invalid_without_raise_returns_result() -> None:
    responses.add(responses.POST, _VAL_URL, json=_INVALID_BODY, status=201)
    result = make_client().mas.validate_remote("m", {"wrong": 1}, raise_on_invalid=False)
    assert result.valid is False
    assert "Validation failed." in result.messages
    assert result.error == _INVALID_BODY["error"]


@responses.activate
def test_validate_remote_invalid_without_error_object() -> None:
    # A bare valid:false (no error object) still raises, with a default message.
    responses.add(responses.POST, _VAL_URL, json={"version": 1, "valid": False}, status=201)
    with pytest.raises(ViyaValidationError) as excinfo:
        make_client().mas.validate_remote("m", {"x": 1})
    assert excinfo.value.messages == ()
    assert "did not accept the inputs" in str(excinfo.value)


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_validate_remote_blank_module_id_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.validate_remote(bad, {"a": 1})
    assert len(responses.calls) == 0


@responses.activate
def test_validate_remote_blank_step_fails_fast() -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.validate_remote("m", {"a": 1}, step="  ")
    assert len(responses.calls) == 0


@responses.activate
def test_validate_remote_missing_step_raises_not_found() -> None:
    url = f"{BASE}/microanalyticScore/commons/validations/modules/m/steps/gone"
    responses.add(responses.POST, url, json={"message": "no"}, status=404)
    with pytest.raises(ViyaNotFoundError):
        make_client().mas.validate_remote("m", {"a": 1}, step="gone")


@responses.activate
def test_validate_remote_malformed_payload_raises_response_error() -> None:
    # A 2xx body with no `valid` field isn't a usable validation result.
    responses.add(responses.POST, _VAL_URL, json={"version": 1}, status=201)
    with pytest.raises(ViyaResponseError):
        make_client().mas.validate_remote("m", {"a": 1})


@responses.activate
def test_validate_remote_dedups_and_tolerates_non_mapping_error() -> None:
    # Duplicate messages across the envelope and nested errors collapse to one,
    # and a non-mapping `error` degrades to no messages / no error object.
    body_dupe = {
        "valid": False,
        "error": {
            "message": "same",
            "errors": [
                {"message": "same"},  # duplicate of the top-level message
                {"details": ["from details"]},  # a nested error with no `message`
                {"message": "other"},
            ],
        },
    }
    responses.add(responses.POST, _VAL_URL, json=body_dupe, status=201)
    result = make_client().mas.validate_remote("m", {"x": 1}, raise_on_invalid=False)
    # Deduped, order preserved; a message-less nested error contributes its details.
    assert result.messages == ("same", "from details", "other")

    responses.reset()
    responses.add(responses.POST, _VAL_URL, json={"valid": False, "error": "boom"}, status=201)
    result = make_client().mas.validate_remote("m", {"x": 1}, raise_on_invalid=False)
    assert result.messages == ()
    assert result.error is None


@responses.activate
def test_validate_remote_percent_encodes_path_segments() -> None:
    responses.add(
        responses.POST,
        f"{BASE}/microanalyticScore/commons/validations/modules/a%2Fb/steps/c%3Fd",
        json={"version": 1, "valid": True},
        status=201,
    )
    make_client().mas.validate_remote("a/b", {}, step="c?d")
    assert "/validations/modules/a%2Fb/steps/c%3Fd" in responses.calls[0].request.url


# -- create ----------------------------------------------------------------

_MODULES_URL = f"{BASE}/microanalyticScore/modules"
_DS2_SOURCE = "ds2_options sas;\npackage pkg / overwrite=yes;\nendpackage;"


@responses.activate
@pytest.mark.parametrize("generation", ["viya4", "viya35"])
def test_create_posts_definition_and_parses_module(
    generation: str, load_fixture: Callable[[str, str], Any], version_for: Callable[[str], str]
) -> None:
    raw = load_fixture(generation, "mas_module.json")
    responses.add(responses.POST, _MODULES_URL, json=raw, status=201)

    module = make_client(version_for(generation)).mas.create("api_tester1_0", _DS2_SOURCE)

    assert module.id == "api_tester1_0"
    req = responses.calls[0].request
    # The create body is sent under the `.definition+json` content type (a plain
    # `.module+json` create body 415s), and the module rep comes back under the
    # `.module+json` accept type.
    assert req.headers["Content-Type"] == "application/vnd.sas.microanalytic.module.definition+json"
    assert req.headers["Accept"] == "application/vnd.sas.microanalytic.module+json"
    sent = json.loads(req.body)
    assert sent == {
        "id": "api_tester1_0",
        "type": "text/vnd.sas.source.ds2",
        "scope": "public",
        "source": _DS2_SOURCE,
    }


@responses.activate
def test_create_python_language_maps_media_type() -> None:
    responses.add(responses.POST, _MODULES_URL, json={"id": "m"}, status=201)
    make_client().mas.create("m", "def execute(a):\n    b = a\n    return b", language="python")
    sent = json.loads(responses.calls[0].request.body)
    assert sent["type"] == "text/x-python"


@responses.activate
def test_create_includes_description_and_custom_scope() -> None:
    responses.add(responses.POST, _MODULES_URL, json={"id": "m"}, status=201)
    make_client().mas.create("m", _DS2_SOURCE, scope="private", description="hi")
    sent = json.loads(responses.calls[0].request.body)
    assert sent["scope"] == "private"
    assert sent["description"] == "hi"


@responses.activate
def test_create_omits_description_when_absent() -> None:
    responses.add(responses.POST, _MODULES_URL, json={"id": "m"}, status=201)
    make_client().mas.create("m", _DS2_SOURCE)
    sent = json.loads(responses.calls[0].request.body)
    assert "description" not in sent


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_create_blank_module_id_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.create(bad, _DS2_SOURCE)
    assert len(responses.calls) == 0


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_create_blank_source_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.create("m", bad)
    assert len(responses.calls) == 0


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_create_blank_scope_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.create("m", _DS2_SOURCE, scope=bad)
    assert len(responses.calls) == 0


@responses.activate
@pytest.mark.parametrize("bad", ["java", "", "DS 2", 5])
def test_create_bad_language_fails_fast(bad: Any) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.create("m", _DS2_SOURCE, language=bad)
    assert len(responses.calls) == 0


@responses.activate
def test_create_language_is_case_insensitive() -> None:
    responses.add(responses.POST, _MODULES_URL, json={"id": "m"}, status=201)
    make_client().mas.create("m", _DS2_SOURCE, language="DS2")
    sent = json.loads(responses.calls[0].request.body)
    assert sent["type"] == "text/vnd.sas.source.ds2"


@responses.activate
def test_create_compile_error_propagates() -> None:
    responses.add(responses.POST, _MODULES_URL, json={"message": "compile failed"}, status=400)
    with pytest.raises(ViyaAPIError):
        make_client().mas.create("m", _DS2_SOURCE)


# -- get_source ------------------------------------------------------------


@responses.activate
@pytest.mark.parametrize("generation", ["viya4", "viya35"])
def test_get_source_parses_payload(
    generation: str, load_fixture: Callable[[str, str], Any], version_for: Callable[[str], str]
) -> None:
    raw = load_fixture(generation, "mas_module_source.json")
    url = f"{BASE}/microanalyticScore/modules/api_tester1_0/source"
    responses.add(responses.GET, url, json=raw, status=200)

    src = make_client(version_for(generation)).mas.get_source("api_tester1_0")

    assert isinstance(src, ModuleSource)
    assert src.module_id == "api_tester1_0"
    assert src.source.startswith("ds2_options sas;")
    assert src.version == 2
    assert src.modified_by == "sasdemo"
    assert (
        responses.calls[0].request.headers["Accept"]
        == "application/vnd.sas.microanalytic.module.source+json"
    )


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_get_source_blank_module_id_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.get_source(bad)
    assert len(responses.calls) == 0


@responses.activate
def test_get_source_missing_module_raises_not_found() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/microanalyticScore/modules/gone/source",
        json={"message": "no"},
        status=404,
    )
    with pytest.raises(ViyaNotFoundError):
        make_client().mas.get_source("gone")


@responses.activate
def test_get_source_without_source_field_raises_response_error() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/microanalyticScore/modules/m/source",
        json={"moduleId": "m", "version": 1},
        status=200,
    )
    with pytest.raises(ViyaResponseError):
        make_client().mas.get_source("m")


# -- update_source ---------------------------------------------------------

_MODULE_URL = f"{BASE}/microanalyticScore/modules/m"
_SOURCE_URL = f"{BASE}/microanalyticScore/modules/m/source"


def _add_module_get_for_etag(*, etag: str = '"abc123"', language: str = "ds2") -> None:
    """Register the module GET that update_source makes to obtain the ETag."""
    responses.add(
        responses.GET,
        _MODULE_URL,
        json={"id": "m", "language": language},
        status=200,
        headers={"ETag": etag},
    )


@responses.activate
def test_update_source_fetches_etag_then_puts_with_if_match() -> None:
    _add_module_get_for_etag(etag='"rev7"')
    responses.add(
        responses.PUT,
        _SOURCE_URL,
        json={"moduleId": "m", "source": _DS2_SOURCE, "version": 3},
        status=200,
    )

    result = make_client().mas.update_source("m", _DS2_SOURCE)

    assert isinstance(result, ModuleSource)
    assert result.version == 3
    get_call, put_call = responses.calls
    assert get_call.request.method == "GET"
    assert put_call.request.method == "PUT"
    # The ETag comes back quoted; it must be forwarded verbatim (quotes kept) as
    # If-Match — MAS rejects an unquoted value.
    assert put_call.request.headers["If-Match"] == '"rev7"'
    assert (
        put_call.request.headers["Content-Type"]
        == "application/vnd.sas.microanalytic.module.source+json"
    )
    sent = json.loads(put_call.request.body)
    assert sent == {"moduleId": "m", "type": "text/vnd.sas.source.ds2", "source": _DS2_SOURCE}


@responses.activate
def test_update_source_reuses_module_language() -> None:
    _add_module_get_for_etag(language="python")
    responses.add(responses.PUT, _SOURCE_URL, json={"moduleId": "m", "source": "x"}, status=200)
    make_client().mas.update_source("m", "def execute(a):\n    return a")
    sent = json.loads(responses.calls[1].request.body)
    assert sent["type"] == "text/x-python"


@responses.activate
def test_update_source_explicit_language_overrides_module() -> None:
    _add_module_get_for_etag(language="ds2")
    responses.add(responses.PUT, _SOURCE_URL, json={"moduleId": "m", "source": "x"}, status=200)
    make_client().mas.update_source("m", "def execute(a):\n    return a", language="python")
    sent = json.loads(responses.calls[1].request.body)
    assert sent["type"] == "text/x-python"
    # The explicit language means the PUT need not depend on the module's own.


@responses.activate
def test_update_source_missing_etag_raises_response_error() -> None:
    # Module GET without an ETag header: we cannot form the concurrency guard, so
    # fail loudly rather than issue an unguarded PUT that would 428 opaquely.
    responses.add(responses.GET, _MODULE_URL, json={"id": "m", "language": "ds2"}, status=200)
    with pytest.raises(ViyaResponseError):
        make_client().mas.update_source("m", _DS2_SOURCE)
    # Only the GET happened; no PUT was attempted.
    assert [c.request.method for c in responses.calls] == ["GET"]


@responses.activate
def test_update_source_missing_language_raises_response_error() -> None:
    responses.add(responses.GET, _MODULE_URL, json={"id": "m"}, status=200, headers={"ETag": '"e"'})
    with pytest.raises(ViyaResponseError):
        make_client().mas.update_source("m", _DS2_SOURCE)
    assert [c.request.method for c in responses.calls] == ["GET"]


@responses.activate
def test_update_source_explicit_language_skips_module_language_need() -> None:
    # Even when the module omits `language`, an explicit language lets the update
    # proceed (the ETag is still required and present here).
    responses.add(responses.GET, _MODULE_URL, json={"id": "m"}, status=200, headers={"ETag": '"e"'})
    responses.add(responses.PUT, _SOURCE_URL, json={"moduleId": "m", "source": "x"}, status=200)
    make_client().mas.update_source("m", _DS2_SOURCE, language="ds2")
    assert responses.calls[1].request.method == "PUT"


@responses.activate
def test_update_source_precondition_failure_propagates() -> None:
    _add_module_get_for_etag()
    responses.add(
        responses.PUT,
        _SOURCE_URL,
        json={"errorCode": 1010, "message": "precondition required"},
        status=428,
    )
    with pytest.raises(ViyaAPIError):
        make_client().mas.update_source("m", _DS2_SOURCE)


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_update_source_blank_module_id_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.update_source(bad, _DS2_SOURCE)
    assert len(responses.calls) == 0


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_update_source_blank_source_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.update_source("m", bad)
    assert len(responses.calls) == 0


@responses.activate
def test_update_source_bad_explicit_language_fails_fast() -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.update_source("m", _DS2_SOURCE, language="cobol")
    assert len(responses.calls) == 0


# -- delete ----------------------------------------------------------------


@responses.activate
def test_delete_issues_delete_and_tolerates_empty_body() -> None:
    # A successful delete is 204 No Content — an empty body must not be treated as
    # a malformed JSON response.
    responses.add(responses.DELETE, _MODULE_URL, status=204)
    assert make_client().mas.delete("m") is None
    assert responses.calls[0].request.method == "DELETE"


@responses.activate
@pytest.mark.parametrize("bad", ["", "   "])
def test_delete_blank_module_id_fails_fast(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        make_client().mas.delete(bad)
    assert len(responses.calls) == 0


@responses.activate
def test_delete_missing_module_raises_not_found() -> None:
    responses.add(
        responses.DELETE,
        f"{BASE}/microanalyticScore/modules/gone",
        json={"message": "no"},
        status=404,
    )
    with pytest.raises(ViyaNotFoundError):
        make_client().mas.delete("gone")


@responses.activate
def test_delete_percent_encodes_module_id() -> None:
    responses.add(responses.DELETE, f"{BASE}/microanalyticScore/modules/a%2Fb", status=204)
    make_client().mas.delete("a/b")
    assert "/modules/a%2Fb" in responses.calls[0].request.url
