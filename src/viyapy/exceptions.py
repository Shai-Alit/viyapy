"""Typed exception hierarchy for viyapy.

Every failure raised by the library is a subclass of :class:`ViyaError`, so
callers can catch broadly (``except ViyaError``) or precisely
(``except ViyaNotFoundError``). API errors carry structured context — the HTTP
status, the SAS Viya error envelope, and any correlation id — so a log line or
bug report is actionable without having to re-run the request.
"""

from __future__ import annotations

from typing import Any


class ViyaError(Exception):
    """Base class for all errors raised by viyapy."""


class ViyaConfigError(ViyaError):
    """Invalid configuration or arguments, raised before any network call."""


class ViyaConnectionError(ViyaError):
    """The request could not reach the server (DNS, refused, or TLS failure)."""


class ViyaTimeoutError(ViyaError):
    """The request exceeded its connect or read timeout."""


class ViyaAPIError(ViyaError):
    """A non-2xx HTTP response was returned by SAS Viya.

    Attributes:
        status_code: HTTP status code of the response.
        viya_error_code: SAS error code from the response envelope, if present.
        details: Detail strings from the response envelope (may be empty).
        correlation_id: Request correlation/trace id from the response headers.
        url: The request URL.
        method: The HTTP method.
        response_body: The parsed (or raw text) response body, when available.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        viya_error_code: int | str | None = None,
        details: list[str] | None = None,
        correlation_id: str | None = None,
        url: str | None = None,
        method: str | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.viya_error_code = viya_error_code
        self.details: list[str] = details or []
        self.correlation_id = correlation_id
        self.url = url
        self.method = method
        self.response_body = response_body

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"(HTTP {self.status_code})")
        if self.viya_error_code is not None:
            parts.append(f"[errorCode={self.viya_error_code}]")
        if self.correlation_id:
            parts.append(f"[correlationId={self.correlation_id}]")
        return " ".join(parts)


class ViyaAuthError(ViyaAPIError):
    """Authentication or authorization failed (HTTP 401 or 403)."""


class ViyaNotFoundError(ViyaAPIError):
    """The requested resource does not exist (HTTP 404)."""


class ViyaRateLimitError(ViyaAPIError):
    """The client is being rate limited (HTTP 429).

    Attributes:
        retry_after: Seconds to wait before retrying, if the server sent a
            numeric ``Retry-After`` header; otherwise ``None``.
    """

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ViyaServerError(ViyaAPIError):
    """SAS Viya returned a server error (HTTP 5xx)."""


class ViyaResponseError(ViyaError):
    """A 2xx response was returned but its body was missing or malformed.

    Attributes:
        url: The request URL.
        response_body: The parsed (or raw text) response body, when available.
    """

    def __init__(self, message: str, *, url: str | None = None, response_body: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.url = url
        self.response_body = response_body
