"""Unit tests for the internal HTTP layer. No real network: HTTP is mocked."""

from __future__ import annotations

from unittest import mock

import pytest
import requests
import responses

from viyapy._http import (
    DEFAULT_TIMEOUT,
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


def mock_session() -> mock.Mock:
    session = mock.Mock(spec=requests.Session)
    session.request.return_value = mock.Mock(status_code=200)
    return session


# -- construction / validation ---------------------------------------------


def test_base_url_trailing_slash_is_normalized() -> None:
    assert make_client().base_url == BASE
    assert HttpClient(BASE + "/", "tok", max_retries=0).base_url == BASE


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_empty_base_url_raises_config_error(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        HttpClient(bad, "tok")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["viya.example.com", "ftp://viya.example.com", "://x", "https://"])
def test_non_absolute_http_url_raises_config_error(bad: str) -> None:
    with pytest.raises(ViyaConfigError):
        HttpClient(bad, "tok")


def test_http_scheme_warns_about_cleartext() -> None:
    with pytest.warns(UserWarning, match="cleartext"):
        HttpClient("http://viya.example.com", "tok", max_retries=0)


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_empty_token_raises_config_error(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        HttpClient(BASE, bad)  # type: ignore[arg-type]


def test_token_is_stripped() -> None:
    client = HttpClient(BASE, "  tok-with-newline\n", max_retries=0)
    assert client._token == "tok-with-newline"


def test_timeout_none_raises_config_error() -> None:
    with pytest.raises(ViyaConfigError):
        HttpClient(BASE, "tok", timeout=None)  # type: ignore[arg-type]


def test_verify_false_warns() -> None:
    with pytest.warns(UserWarning, match="TLS verification is disabled"):
        HttpClient(BASE, "tok", verify=False, max_retries=0)


def test_repr_redacts_token() -> None:
    text = repr(make_client())
    assert "secret-token" not in text
    assert "***" in text


# -- happy path -------------------------------------------------------------


@responses.activate
def test_get_ok_returns_response_and_sends_bearer() -> None:
    responses.add(responses.GET, f"{BASE}/ping", json={"ok": True}, status=200)
    resp = make_client().request("GET", "/ping")
    assert resp.json() == {"ok": True}
    assert responses.calls[0].request.headers["Authorization"] == "Bearer secret-token"
    assert responses.calls[0].request.headers["Accept"] == "application/json"


@responses.activate
def test_default_user_agent_is_sent() -> None:
    responses.add(responses.GET, f"{BASE}/ping", json={}, status=200)
    make_client().request("GET", "/ping")
    assert responses.calls[0].request.headers["User-Agent"].startswith("viyapy/")


@responses.activate
def test_custom_user_agent_is_sent() -> None:
    responses.add(responses.GET, f"{BASE}/ping", json={}, status=200)
    HttpClient(BASE, "tok", max_retries=0, user_agent="myapp/1.0").request("GET", "/ping")
    assert responses.calls[0].request.headers["User-Agent"] == "myapp/1.0"


@responses.activate
def test_post_sets_content_type_and_body() -> None:
    responses.add(responses.POST, f"{BASE}/exec", json={"done": 1}, status=200)
    make_client().request(
        "POST", "/exec", content_type="application/json", json_body={"inputs": []}
    )
    sent = responses.calls[0].request
    assert sent.headers["Content-Type"] == "application/json"
    assert b'"inputs"' in sent.body


def test_timeout_and_verify_are_forwarded_to_the_session() -> None:
    session = mock_session()
    client = HttpClient(BASE, "tok", timeout=(1.0, 2.0), verify="/ca.pem", session=session)
    client.request("GET", "/ping")
    kwargs = session.request.call_args.kwargs
    assert kwargs["timeout"] == (1.0, 2.0)
    assert kwargs["verify"] == "/ca.pem"


def test_per_call_timeout_overrides_client_default() -> None:
    session = mock_session()
    client = HttpClient(BASE, "tok", timeout=DEFAULT_TIMEOUT, session=session)
    client.request("GET", "/ping", timeout=0.5)
    assert session.request.call_args.kwargs["timeout"] == 0.5


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


@responses.activate
def test_generic_request_exception_translates() -> None:
    responses.add(responses.GET, f"{BASE}/x", body=requests.exceptions.RequestException("boom"))
    with pytest.raises(ViyaConnectionError):
        make_client().request("GET", "/x")


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


@responses.activate
def test_non_json_error_body_kept_as_text() -> None:
    responses.add(responses.GET, f"{BASE}/r", body="upstream exploded", status=500)
    with pytest.raises(ViyaServerError) as info:
        make_client().request("GET", "/r")
    assert info.value.response_body == "upstream exploded"


# -- retry behavior (not just configuration) --------------------------------


def test_retry_config_defaults() -> None:
    retry = HttpClient(BASE, "tok")._session.get_adapter("https://x").max_retries
    assert retry.total == 3
    assert 429 in retry.status_forcelist
    assert retry.respect_retry_after_header is True
    assert "POST" not in retry.allowed_methods  # MAS execute is not assumed idempotent


@responses.activate
def test_retries_transient_5xx_then_succeeds() -> None:
    responses.add(responses.GET, f"{BASE}/r", status=503)
    responses.add(responses.GET, f"{BASE}/r", json={"ok": True}, status=200)
    resp = HttpClient(BASE, "tok", max_retries=2).request("GET", "/r")
    assert resp.status_code == 200
    assert len(responses.calls) == 2


@responses.activate
def test_retries_exhausted_raises_typed_server_error() -> None:
    responses.add(responses.GET, f"{BASE}/r", status=503)
    responses.add(responses.GET, f"{BASE}/r", status=503)
    with pytest.raises(ViyaServerError):
        HttpClient(BASE, "tok", max_retries=1).request("GET", "/r")
    assert len(responses.calls) == 2


@responses.activate
def test_post_not_retried_by_default() -> None:
    responses.add(responses.POST, f"{BASE}/exec", status=503)
    with pytest.raises(ViyaServerError):
        HttpClient(BASE, "tok", max_retries=3).request("POST", "/exec")
    assert len(responses.calls) == 1  # no double-execution


@responses.activate
def test_post_retried_when_opted_in() -> None:
    responses.add(responses.POST, f"{BASE}/exec", status=503)
    responses.add(responses.POST, f"{BASE}/exec", json={"ok": True}, status=200)
    resp = HttpClient(BASE, "tok", max_retries=2, retry_on_post=True).request("POST", "/exec")
    assert resp.status_code == 200
    assert len(responses.calls) == 2


# -- lifecycle --------------------------------------------------------------


def test_context_manager_closes_session() -> None:
    session = mock_session()
    with HttpClient(BASE, "tok", session=session) as client:
        assert isinstance(client, HttpClient)
    session.close.assert_called_once()


# -- helpers ----------------------------------------------------------------


def test_parse_error_envelope_nested_form() -> None:
    body = {"error": {"message": "invalid", "errorCode": 7, "details": "one detail"}}
    message, code, details = _parse_error_envelope(body, default="fallback")
    assert (message, code, details) == ("invalid", 7, ["one detail"])


def test_parse_error_envelope_non_mapping_uses_default() -> None:
    assert _parse_error_envelope("plain text error", default="fallback") == ("fallback", None, [])


@pytest.mark.parametrize(("headers", "expected"), [({"Retry-After": "5"}, 5.0), ({}, None)])
def test_retry_after_numeric_and_absent(headers: dict[str, str], expected: float | None) -> None:
    assert _retry_after(headers) == expected


def test_retry_after_http_date_form_returns_non_negative() -> None:
    # A past date should clamp to 0.0 rather than go negative.
    result = _retry_after({"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
    assert result is not None
    assert result >= 0.0


def test_retry_after_unparseable_is_none() -> None:
    assert _retry_after({"Retry-After": "not-a-date"}) is None


def test_correlation_id_absent_is_none() -> None:
    assert _correlation_id({}) is None
