"""Unit tests for pluggable auth (static token and token-provider callable)."""

from __future__ import annotations

from collections.abc import Callable
from itertools import count

import pytest
import responses

from viyapy import ViyaClient
from viyapy._http import HttpClient
from viyapy.auth import read_token, resolve_token_provider
from viyapy.exceptions import ViyaConfigError

BASE = "https://viya.example.com"


def _auth_header() -> str:
    return responses.calls[0].request.headers["Authorization"]


# -- static token (backward compatible) -------------------------------------


@responses.activate
@pytest.mark.parametrize(
    "build",
    [lambda: HttpClient(BASE, "tok"), lambda: HttpClient(BASE, token="tok")],
)
def test_static_token_positional_or_keyword_sends_bearer(build: Callable[[], HttpClient]) -> None:
    responses.add(responses.GET, f"{BASE}/ping", json={}, status=200)
    build().request("GET", "/ping")
    assert _auth_header() == "Bearer tok"


# -- token provider callable ------------------------------------------------


@responses.activate
def test_auth_callable_invoked_on_every_request() -> None:
    calls = count(1)
    seen: list[int] = []

    def provider() -> str:
        n = next(calls)
        seen.append(n)
        return "tok"

    responses.add(responses.GET, f"{BASE}/a", json={}, status=200)
    responses.add(responses.GET, f"{BASE}/b", json={}, status=200)
    client = HttpClient(BASE, auth=provider)
    client.request("GET", "/a")
    client.request("GET", "/b")
    assert seen == [1, 2]  # called once per request, not cached


@responses.activate
def test_auth_provider_refresh_is_reflected() -> None:
    tokens = iter(["tok-1", "tok-2"])
    responses.add(responses.GET, f"{BASE}/a", json={}, status=200)
    responses.add(responses.GET, f"{BASE}/b", json={}, status=200)
    client = HttpClient(BASE, auth=lambda: next(tokens))

    client.request("GET", "/a")
    assert responses.calls[0].request.headers["Authorization"] == "Bearer tok-1"
    client.request("GET", "/b")
    assert responses.calls[1].request.headers["Authorization"] == "Bearer tok-2"


@responses.activate
def test_auth_empty_return_raises_before_network() -> None:
    responses.add(responses.GET, f"{BASE}/ping", json={}, status=200)
    with pytest.raises(ViyaConfigError):
        HttpClient(BASE, auth=lambda: "  ").request("GET", "/ping")
    assert len(responses.calls) == 0  # failed fast, no request issued


@responses.activate
def test_auth_non_string_return_raises() -> None:
    with pytest.raises(ViyaConfigError):
        HttpClient(BASE, auth=lambda: 12345).request("GET", "/ping")  # type: ignore[arg-type,return-value]


# -- one-of validation & redaction ------------------------------------------


def test_both_token_and_auth_raises() -> None:
    with pytest.raises(ViyaConfigError):
        ViyaClient(BASE, "tok", auth=lambda: "tok")


def test_neither_credential_raises() -> None:
    with pytest.raises(ViyaConfigError):
        ViyaClient(BASE)


def test_repr_redacts_with_callable() -> None:
    text = repr(HttpClient(BASE, auth=lambda: "super-secret"))
    assert "super-secret" not in text
    assert "***" in text


# -- helpers ----------------------------------------------------------------


def test_resolve_token_provider_wraps_static_token() -> None:
    provider = resolve_token_provider("  padded\n", None)
    assert provider() == "padded"


def test_resolve_token_provider_passes_callable_through() -> None:
    def fn() -> str:
        return "tok"

    assert resolve_token_provider(None, fn) is fn


def test_resolve_token_provider_rejects_empty_and_both_and_neither() -> None:
    for token, auth in [("", None), (None, None), ("tok", lambda: "tok")]:
        with pytest.raises(ViyaConfigError):
            resolve_token_provider(token, auth)


def test_resolve_token_provider_rejects_non_callable_auth() -> None:
    with pytest.raises(ViyaConfigError):
        resolve_token_provider(None, "not-callable")  # type: ignore[arg-type]


def test_read_token_strips_and_validates() -> None:
    assert read_token(lambda: "  tok\n") == "tok"
    with pytest.raises(ViyaConfigError):
        read_token(lambda: "")
