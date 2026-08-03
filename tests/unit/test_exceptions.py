"""Unit tests for the exception hierarchy."""

from __future__ import annotations

import pytest

from viyapy.exceptions import (
    ViyaAPIError,
    ViyaAuthError,
    ViyaConfigError,
    ViyaConnectionError,
    ViyaError,
    ViyaNotFoundError,
    ViyaRateLimitError,
    ViyaResponseError,
    ViyaServerError,
    ViyaTimeoutError,
)


@pytest.mark.parametrize(
    "exc_type",
    [
        ViyaConfigError,
        ViyaConnectionError,
        ViyaTimeoutError,
        ViyaAPIError,
        ViyaAuthError,
        ViyaNotFoundError,
        ViyaRateLimitError,
        ViyaServerError,
        ViyaResponseError,
    ],
)
def test_all_errors_derive_from_base(exc_type: type[ViyaError]) -> None:
    assert issubclass(exc_type, ViyaError)


@pytest.mark.parametrize(
    "exc_type",
    [ViyaAuthError, ViyaNotFoundError, ViyaRateLimitError, ViyaServerError],
)
def test_http_errors_derive_from_api_error(exc_type: type[ViyaAPIError]) -> None:
    assert issubclass(exc_type, ViyaAPIError)


def test_api_error_stores_context() -> None:
    err = ViyaAPIError(
        "bad request",
        status_code=400,
        viya_error_code=1234,
        details=["field x is invalid"],
        correlation_id="abc-123",
        url="https://viya.example.com/decisions/flows/1",
        method="GET",
        response_body={"message": "bad request"},
    )
    assert err.status_code == 400
    assert err.viya_error_code == 1234
    assert err.details == ["field x is invalid"]
    assert err.correlation_id == "abc-123"
    assert err.method == "GET"


def test_api_error_str_includes_context() -> None:
    err = ViyaAPIError(
        "not found",
        status_code=404,
        viya_error_code=404,
        correlation_id="xyz-9",
    )
    text = str(err)
    assert "not found" in text
    assert "HTTP 404" in text
    assert "errorCode=404" in text
    assert "correlationId=xyz-9" in text


def test_api_error_details_default_empty() -> None:
    assert ViyaAPIError("boom").details == []


def test_rate_limit_error_carries_retry_after() -> None:
    err = ViyaRateLimitError("slow down", retry_after=12.0, status_code=429)
    assert err.retry_after == 12.0
    assert err.status_code == 429
    assert isinstance(err, ViyaAPIError)


def test_response_error_carries_body() -> None:
    err = ViyaResponseError(
        "missing outputs",
        url="https://viya.example.com/x",
        response_body={"unexpected": True},
    )
    assert err.url.endswith("/x")
    assert err.response_body == {"unexpected": True}
    assert isinstance(err, ViyaError)
    assert not isinstance(err, ViyaAPIError)


def test_api_error_str_includes_status_code_and_correlation() -> None:
    err = ViyaAPIError(
        "boom",
        status_code=409,
        viya_error_code=1234,
        correlation_id="abc-123",
    )
    text = str(err)
    assert text == "boom (HTTP 409) [errorCode=1234] [correlationId=abc-123]"


def test_api_error_str_omits_absent_fields() -> None:
    assert str(ViyaAPIError("just a message")) == "just a message"
