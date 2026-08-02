"""Internal HTTP layer.

One :class:`requests.Session` per client, mandatory connect/read timeouts,
retries with exponential backoff + jitter (honoring ``Retry-After``), and
translation of transport/HTTP failures into the typed
:mod:`viyapy.exceptions` hierarchy.

This module is private; public access is through :class:`viyapy.ViyaClient`
(added in a later slice). It never logs or reprs the bearer token.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import (
    ViyaAPIError,
    ViyaAuthError,
    ViyaConfigError,
    ViyaConnectionError,
    ViyaNotFoundError,
    ViyaRateLimitError,
    ViyaServerError,
    ViyaTimeoutError,
)

logger = logging.getLogger(__name__)

# Timeout is (connect, read) seconds, or a single float applied to both.
# No request is ever issued without a timeout.
DEFAULT_TIMEOUT: float | tuple[float, float] = (5.0, 30.0)
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.5
DEFAULT_BACKOFF_JITTER = 0.3
_RETRY_STATUS = (429, 500, 502, 503, 504)
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
_CORRELATION_HEADERS = (
    "X-Correlation-Id",
    "X-SAS-Correlator",
    "X-Request-Id",
    "correlationId",
)


class HttpClient:
    """Thin, hardened wrapper over a :class:`requests.Session`.

    Args:
        base_url: Absolute root URL of the Viya deployment, e.g.
            ``https://viya.example.com``. Must include an ``http``/``https``
            scheme and a host.
        token: OAuth2 bearer token. Surrounding whitespace is stripped.
        timeout: ``(connect, read)`` seconds, or a single float applied to both.
            Must not be ``None`` (that would block forever).
        verify: TLS verification — ``True``, ``False``, or a CA-bundle path.
            ``False`` emits a warning.
        max_retries: Retry budget for transient failures (connection, 429, 5xx).
        retry_on_post: Whether POSTs may be retried. Off by default because MAS
            execution is not assumed idempotent.
        user_agent: ``User-Agent`` header; defaults to ``viyapy/<version>``.
        session: Inject a pre-built session (mainly for testing).

    Raises:
        ViyaConfigError: If ``base_url``, ``token``, or ``timeout`` is invalid.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
        verify: bool | str = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_on_post: bool = False,
        user_agent: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        cleaned_url = str(base_url).strip() if base_url is not None else ""
        if not cleaned_url:
            raise ViyaConfigError("base_url must be a non-empty string")
        parsed = urlparse(cleaned_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ViyaConfigError(
                "base_url must be an absolute http(s) URL, "
                f"e.g. https://viya.example.com (got {base_url!r})"
            )
        if parsed.scheme == "http":
            warnings.warn(
                "base_url uses http://; the bearer token will be sent in cleartext. "
                "Use https:// in production.",
                stacklevel=2,
            )

        cleaned_token = str(token).strip() if token is not None else ""
        if not cleaned_token:
            raise ViyaConfigError("token must be a non-empty string")

        if timeout is None:
            raise ViyaConfigError(
                "timeout must not be None (that would block forever); "
                "pass a float or a (connect, read) tuple"
            )

        if verify is False:
            warnings.warn(
                "TLS verification is disabled; traffic (including the bearer token) is "
                "not protected against interception. Supply a CA-bundle path instead.",
                stacklevel=2,
            )

        self.base_url = cleaned_url.rstrip("/")
        self._token = cleaned_token
        self.timeout = timeout
        self.verify = verify
        self._max_retries = max_retries
        self._retry_on_post = retry_on_post
        self._user_agent = user_agent or _default_user_agent()
        self._session = session or self._build_session()

    # -- session / retry configuration --------------------------------------

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        methods = set(_IDEMPOTENT_METHODS)
        if self._retry_on_post:
            methods.add("POST")
        forcelist = _RETRY_STATUS if self._max_retries > 0 else ()
        retry = Retry(
            total=self._max_retries,
            connect=self._max_retries,
            read=self._max_retries,
            status=self._max_retries,
            backoff_factor=DEFAULT_BACKOFF_FACTOR,
            backoff_jitter=DEFAULT_BACKOFF_JITTER,
            status_forcelist=forcelist,
            allowed_methods=frozenset(methods),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # -- request ------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        accept: str = "application/json",
        content_type: str | None = None,
        json_body: Any = None,
        params: Mapping[str, Any] | None = None,
        timeout: float | tuple[float, float] | None = None,
    ) -> requests.Response:
        """Issue an authenticated request and return the raw response.

        Args:
            method: HTTP method, e.g. ``"GET"`` or ``"POST"``.
            path: Path relative to ``base_url`` (leading slash optional).
            accept: ``Accept`` header value.
            content_type: ``Content-Type`` header; set when sending ``json_body``.
            json_body: Object serialized to a JSON request body.
            params: Query-string parameters.
            timeout: Per-call override of the client timeout; ``None`` uses the
                client default.

        Returns:
            The successful :class:`requests.Response` (2xx).

        Raises:
            ViyaTimeoutError: The connect or read timeout was exceeded.
            ViyaConnectionError: The server could not be reached.
            ViyaAuthError: Authentication/authorization failed (401/403).
            ViyaNotFoundError: The resource does not exist (404).
            ViyaRateLimitError: The client is being rate limited (429).
            ViyaServerError: SAS Viya returned a 5xx error.
            ViyaAPIError: Any other non-2xx response.
        """
        url = self._url(path)
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": accept,
            "User-Agent": self._user_agent,
        }
        if json_body is not None and content_type:
            headers["Content-Type"] = content_type
        effective_timeout = self.timeout if timeout is None else timeout

        logger.debug("Viya request: %s %s", method, url)
        try:
            response = self._session.request(
                method,
                url,
                json=json_body,
                params=dict(params) if params else None,
                headers=headers,
                timeout=effective_timeout,
                verify=self.verify,
            )
        except requests.exceptions.Timeout as exc:
            raise ViyaTimeoutError(f"Request to {url} timed out") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ViyaConnectionError(f"Could not connect to {url}") from exc
        except requests.exceptions.RequestException as exc:
            raise ViyaConnectionError(f"Request to {url} failed: {exc}") from exc

        self._raise_for_status(response, method, url)
        return response

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _raise_for_status(self, response: requests.Response, method: str, url: str) -> None:
        if response.status_code < 400:
            return

        try:
            body: Any = response.json()
        except ValueError:
            body = response.text

        message, viya_code, details = _parse_error_envelope(
            body, default=response.reason or "SAS Viya API error"
        )
        context: dict[str, Any] = {
            "status_code": response.status_code,
            "viya_error_code": viya_code,
            "details": details,
            "correlation_id": _correlation_id(response.headers),
            "url": url,
            "method": method,
            "response_body": body,
        }
        status = response.status_code
        if status in (401, 403):
            raise ViyaAuthError(message, **context)
        if status == 404:
            raise ViyaNotFoundError(message, **context)
        if status == 429:
            raise ViyaRateLimitError(message, retry_after=_retry_after(response.headers), **context)
        if status >= 500:
            raise ViyaServerError(message, **context)
        raise ViyaAPIError(message, **context)

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"HttpClient(base_url={self.base_url!r}, token='***', "
            f"timeout={self.timeout!r}, verify={self.verify!r})"
        )


def _default_user_agent() -> str:
    try:
        return f"viyapy/{version('viyapy')}"
    except PackageNotFoundError:  # pragma: no cover - only when uninstalled
        return "viyapy"


def _parse_error_envelope(body: Any, default: str) -> tuple[str, int | str | None, list[str]]:
    """Extract ``(message, errorCode, details)`` from a Viya error body.

    Handles both the top-level envelope and the nested ``{"error": {...}}``
    form used by validation endpoints.
    """
    if isinstance(body, Mapping):
        nested = body.get("error")
        env: Mapping[str, Any] = nested if isinstance(nested, Mapping) else body
        message = env.get("message") or default
        code = env.get("errorCode")
        raw_details = env.get("details")
        if isinstance(raw_details, str):
            details = [raw_details]
        elif isinstance(raw_details, list):
            details = [str(d) for d in raw_details]
        else:
            details = []
        return str(message), code, details
    return default, None, []


def _correlation_id(headers: Mapping[str, str]) -> str | None:
    for name in _CORRELATION_HEADERS:
        if name in headers:
            return headers[name]
    return None


def _retry_after(headers: Mapping[str, str]) -> float | None:
    """Parse a ``Retry-After`` header as seconds.

    Supports both the delta-seconds form (``"7"``) and the RFC 9110 HTTP-date
    form (``"Wed, 21 Oct 2015 07:28:00 GMT"``), which SAS gateways may emit.
    """
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:  # pragma: no cover - defensive; older stdlib could return None
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
