"""Fixture-backed error translation through the high-level client paths.

Unit-level envelope parsing lives in ``test_http.py``; here we drive realistic
SAS Viya error bodies (captured as fixtures) through ``decisions.get`` and
``mas.execute`` — across both generations — and assert the typed exception, its
status, and the parsed envelope fields (``errorCode``, ``details``,
``remediation``, ``retry_after``). No network: HTTP is mocked with ``responses``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
import responses

from viyapy import ViyaClient
from viyapy.exceptions import (
    ViyaAPIError,
    ViyaAuthError,
    ViyaNotFoundError,
    ViyaRateLimitError,
    ViyaResponseError,
    ViyaServerError,
)

BASE = "https://viya.example.com"
TOKEN = "test-token"
DECISION_URL = f"{BASE}/decisions/flows/d1"
MAS_URL = f"{BASE}/microanalyticScore/modules/m/steps/execute"


def _client(version: str = "4") -> ViyaClient:
    return ViyaClient(BASE, TOKEN, viya_version=version, max_retries=0)


# -- per-generation matrix (both fixtures are 404) --------------------------


@responses.activate
def test_mas_execute_error_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture(generation, "mas_execute_error.json")
    responses.add(responses.POST, MAS_URL, json=raw, status=raw["httpStatusCode"])

    with pytest.raises(ViyaNotFoundError) as info:
        _client(version_for(generation)).mas.execute("m", {"a": 1})

    err = info.value
    assert err.status_code == 404
    assert err.viya_error_code == raw["errorCode"]
    assert err.details == raw["details"]
    assert err.response_body == raw


@responses.activate
def test_decision_get_error_across_generations(
    generation: str,
    version_for: Callable[[str], str],
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture(generation, "decision_error.json")
    responses.add(responses.GET, DECISION_URL, json=raw, status=raw["httpStatusCode"])

    with pytest.raises(ViyaNotFoundError) as info:
        _client(version_for(generation)).decisions.get("d1")

    err = info.value
    assert err.status_code == 404
    assert err.viya_error_code == raw["errorCode"]
    assert err.details == raw["details"]


# -- envelope-shape variety (shared fixtures under errors/) ------------------


@responses.activate
def test_nested_error_envelope_is_parsed(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("errors", "nested_error_envelope.json")
    responses.add(responses.GET, DECISION_URL, json=raw, status=400)

    with pytest.raises(ViyaAPIError) as info:
        _client().decisions.get("d1")

    err = info.value
    assert type(err) is ViyaAPIError  # 400 maps to the base API error, not a subclass
    assert err.message == "Invalid request payload."
    assert err.viya_error_code == 400013
    assert err.details == ["inputs must be a non-empty array"]


@responses.activate
def test_plural_errors_envelope_is_parsed(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("errors", "plural_errors_envelope.json")
    responses.add(responses.GET, DECISION_URL, json=raw, status=400)

    with pytest.raises(ViyaAPIError) as info:
        _client().decisions.get("d1")

    err = info.value
    assert err.message == "Rule set failed validation."
    assert err.viya_error_code == 90210
    assert err.remediation == "Fix the term reference in rule 3."


@responses.activate
def test_forbidden_surfaces_auth_error_with_remediation(
    load_fixture: Callable[[str, str], Any],
) -> None:
    raw = load_fixture("errors", "forbidden.json")
    responses.add(responses.GET, DECISION_URL, json=raw, status=403)

    with pytest.raises(ViyaAuthError) as info:
        _client().decisions.get("d1")

    err = info.value
    assert err.status_code == 403
    assert err.remediation == "Request the Decisions.Read scope for your token."
    assert err.details == ["required scope: Decisions.Read"]


@responses.activate
def test_rate_limited_surfaces_retry_after(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("errors", "rate_limited.json")
    responses.add(responses.POST, MAS_URL, json=raw, status=429, headers={"Retry-After": "12"})

    with pytest.raises(ViyaRateLimitError) as info:
        _client().mas.execute("m", {"a": 1})

    err = info.value
    assert err.status_code == 429
    assert err.retry_after == 12.0
    assert err.viya_error_code == 4290


@responses.activate
def test_server_error_surfaces(load_fixture: Callable[[str, str], Any]) -> None:
    raw = load_fixture("errors", "server_error.json")
    responses.add(responses.GET, DECISION_URL, json=raw, status=500)

    with pytest.raises(ViyaServerError) as info:
        _client().decisions.get("d1")

    assert info.value.status_code == 500
    assert info.value.viya_error_code == 5000


# -- malformed 2xx through the MAS path -------------------------------------


@responses.activate
def test_mas_execute_2xx_without_output_list_raises_response_error() -> None:
    # A 200 whose body carries no output/outputs list is a contract violation,
    # not a transport error: it must surface as ViyaResponseError.
    responses.add(responses.POST, MAS_URL, json={"executionState": "completed"}, status=200)
    with pytest.raises(ViyaResponseError):
        _client().mas.execute("m", {"a": 1})
