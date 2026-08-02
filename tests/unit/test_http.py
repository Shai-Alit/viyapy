"""Unit tests for the internal HTTP layer. No real network: HTTP is mocked."""

from __future__ import annotations

import pytest
import requests
import responses

from viyapy._http import (
    HttpClient,
    _correlation_id,
    _parse_error_envelope,
    _retry_after,
)
from viyapy.exceptions import (
    ViyaAPIError,
    ViyaAuthError,
    ViyaConfigError,
    ViyaConnectionError,
    ViyaNotFoundError,
    ViyaRateLimitError,
    ViyaServerError,
    ViyaTimeoutError,
)

BASE = "https://viya.example.com"


def make_client(**kwargs: object) -> HttpClient:
    # Retries disabled by default so error-path tests don't sleep/backoff.
    kwargs.setdefault("max_retries", 0)
    return HttpClient(BASE, "secret-token", **kwargs)  # type: ignore[arg-type]


# -- construction / validation ---------------------------------------------


def test_base_url_trailing_slash_is_normalized() -> None:
    client = make_client()
    assert client.base_url == BASE
    other = HttpClient(BASE + "/", "tok", max_retries=0)
    assert other.base_url == BASE


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_empty_base_url_raises_config_error(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        HttpClient(bad, "tok")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_empty_token_raises_config_error(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        HttpClient(BASE, bad)  # type: ignore[arg-type]


def test_repr_redacts_token() -> None:
    text = repr(make_client())
    assert "secret-token" not in text
    assert "***" in text


# -- happy path -------------------------------------------------------------


@responses.activate
def test_get_ok_returns_response_and_sends_bearer() -> None:
    responses.add(responses.GET, f"{BASE}/ping", json={"ok": True}, status=200)
    client = make_client()
    resp = client.request("GET", "/ping")
    assert resp.json() == {"ok": True}
    assert responses.calls[0].request.headers["Authorization"] == "Bearer secret-token"
    assert responses.calls[0].request.headers["Accept"] == "application/json"


@responses.activate
def test_post_sets_content_type_and_body() -> None:
    responses.add(responses.POST, f"{BASE}/exec", json={"done": 1}, status=200)
    client = make_client()
    client.request(
        "POST",
        "/exec",
        content_type="application/json",
        json_body={"inputs": []},
    )
    sent = responses.calls[0].request
    assert sent.headers["Content-Type"] == "application/json"
    assert b'"inputs"' in sent.body


# -- transport failures -----------------------------------------------------


@responses.activate
def test_timeout_translates() -> None:
    responses.add(responses.GET, f"{BASE}/slow", body=requests.exceptions.ReadTimeout())
    with pytest.raises(ViyaTimeoutError):
        make_client().request("GET", "/slow")


@responses.activate
def test_connection_error_translates() -> None:
    responses.add(responses.GET, f"{BASE}/down", body=requests.exceptions.ConnectionError())
    with pytest.raises(ViyaConnectionError):
        make_client().request("GET", "/down")


# -- HTTP status translation ------------------------------------------------


@responses.activate
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ViyaAuthError),
        (403, ViyaAuthError),
        (404, ViyaNotFoundError),
        (500, ViyaServerError),
        (503, ViyaServerError),
        (400, ViyaAPIError),
    ],
)
def test_status_codes_translate_to_typed_errors(status: int, expected: type[ViyaAPIError]) -> None:
    responses.add(responses.GET, f"{BASE}/r", json={"message": "nope"}, status=status)
    with pytest.raises(expected) as info:
        make_client().request("GET", "/r")
    assert info.value.status_code == status
    assert info.value.url.endswith("/r")


@responses.activate
def test_rate_limit_parses_retry_after() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/r",
        json={"message": "slow down"},
        status=429,
        headers={"Retry-After": "7"},
    )
    with pytest.raises(ViyaRateLimitError) as info:
        make_client().request("GET", "/r")
    assert info.value.retry_after == 7.0


@responses.activate
def test_error_envelope_is_parsed() -> None:
    responses.add(
        responses.GET,
        f"{BASE}/r",
        json={"message": "bad input", "errorCode": 42, "details": ["x too big"]},
        status=400,
        headers={"X-Correlation-Id": "corr-9"},
    )
    with pytest.raises(ViyaAPIError) as info:
        make_client().request("GET", "/r")
    err = info.value
    assert err.viya_error_code == 42
    assert err.details == ["x too big"]
    assert err.correlation_id == "corr-9"


# -- retry configuration ----------------------------------------------------


def test_retry_config_defaults() -> None:
    client = HttpClient(BASE, "tok")  # default retries
    retry = client._session.get_adapter("https://x").max_retries
    assert retry.total == 3
    assert 429 in retry.status_forcelist
    assert retry.respect_retry_after_header is True
    # POST is not retried by default (MAS execution is not assumed idempotent).
    assert "POST" not in retry.allowed_methods


def test_retry_on_post_opt_in() -> None:
    client = HttpClient(BASE, "tok", retry_on_post=True)
    retry = client._session.get_adapter("https://x").max_retries
    assert "POST" in retry.allowed_methods


# -- envelope helper --------------------------------------------------------


def test_parse_error_envelope_nested_form() -> None:
    body = {"error": {"message": "invalid", "errorCode": 7, "details": "one detail"}}
    message, code, details = _parse_error_envelope(body, default="fallback")
    assert message == "invalid"
    assert code == 7
    assert details == ["one detail"]


def test_parse_error_envelope_non_mapping_uses_default() -> None:
    message, code, details = _parse_error_envelope("plain text error", default="fallback")
    assert message == "fallback"
    assert code is None
    assert details == []


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Retry-After": "5"}, 5.0),
        ({"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}, None),  # HTTP-date form
        ({}, None),
    ],
)
def test_retry_after_parsing(headers: dict[str, str], expected: float | None) -> None:
    assert _retry_after(headers) == expected


def test_correlation_id_absent_is_none() -> None:
    assert _correlation_id({}) is None


# -- misc request behavior --------------------------------------------------


@responses.activate
def test_user_agent_header_is_sent() -> None:
    responses.add(responses.GET, f"{BASE}/ping", json={}, status=200)
    client = HttpClient(BASE, "tok", max_retries=0, user_agent="viyapy/test")
    client.request("GET", "/ping")
    assert responses.calls[0].request.headers["User-Agent"] == "viyapy/test"


@responses.activate
def test_non_json_error_body_kept_as_text() -> None:
    responses.add(responses.GET, f"{BASE}/r", body="upstream exploded", status=500)
    with pytest.raises(ViyaServerError) as info:
        make_client().request("GET", "/r")
    assert info.value.response_body == "upstream exploded"


@responses.activate
def test_generic_request_exception_translates() -> None:
    responses.add(responses.GET, f"{BASE}/x", body=requests.exceptions.RequestException("boom"))
    with pytest.raises(ViyaConnectionError):
        make_client().request("GET", "/x")


def test_context_manager_closes_session() -> None:
    with make_client() as client:
        assert isinstance(client, HttpClient)
    # close() is idempotent and safe to call again after the context exits.
    client.close()
