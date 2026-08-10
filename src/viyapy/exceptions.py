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
        remediation: SAS remediation hint from the response envelope, if present
            — usually the most actionable part of the error.
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
        remediation: str | None = None,
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
        self.remediation = remediation
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


class ViyaValidationError(ViyaError):
    """Inputs did not match a MAS step signature.

    Raised in two situations:

    * **Client-side** — :meth:`~viyapy.mas.MASClient.validate` or
      :meth:`~viyapy.mas.MASClient.execute` with ``validate=True`` compares the
      supplied input *names* to the step's declared signature and raises when a
      declared input is missing or an undeclared one was supplied. The offending
      names are on :attr:`missing`/:attr:`unexpected`. SAS rejects a mismatched
      signature regardless, but the failure otherwise surfaces deep in the
      execution chain; raising locally fails fast and names the input directly.
    * **Server-side** — :meth:`~viyapy.mas.MASClient.validate_remote` asks SAS
      Viya to validate the payload and raises when the server reports it invalid
      (unless ``raise_on_invalid=False``). The server's violation messages are on
      :attr:`messages` and the raw validation body on :attr:`response_body`;
      :attr:`missing`/:attr:`unexpected` are empty because the server reports
      free-form messages rather than a name partition.

    Attributes:
        missing: Declared input names that were not supplied (sorted). Client-side
            check only; empty for a server-side failure.
        unexpected: Supplied input names the signature does not declare (sorted).
            Client-side check only; empty for a server-side failure.
        messages: Server-reported violation messages. Server-side check only;
            empty for a client-side failure.
        module_id: The module whose signature was checked, if known.
        step: The step whose signature was checked, if known.
        response_body: The raw server validation body, for a server-side failure.
    """

    def __init__(
        self,
        message: str,
        *,
        missing: tuple[str, ...] = (),
        unexpected: tuple[str, ...] = (),
        messages: tuple[str, ...] = (),
        module_id: str | None = None,
        step: str | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.missing = missing
        self.unexpected = unexpected
        self.messages = messages
        self.module_id = module_id
        self.step = step
        self.response_body = response_body


class ViyaSecurityWarning(UserWarning):
    """Warning for security-relevant configuration.

    Emitted for choices that weaken transport security — for example disabling
    TLS verification or using an ``http://`` base URL that sends the bearer token
    in cleartext. Because it is a distinct category, deployments can filter or
    escalate it precisely (e.g. ``-W error::viyapy.ViyaSecurityWarning``) rather
    than matching on message text.
    """
