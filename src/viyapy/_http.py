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
from collections.abc import Mapping
from typing import Any

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

logger = logging.getLogger("viyapy")

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
        base_url: Root URL of the Viya deployment, e.g. ``https://viya.example.com``.
        token: OAuth2 bearer token.
        timeout: ``(connect, read)`` seconds, or a single float applied to both.
        verify: TLS verification — ``True``, ``False``, or a CA-bundle path.
        max_retries: Retry budget for transient failures (connection, 429, 5xx).
        retry_on_post: Whether POSTs may be retried. Off by default because MAS
            execution is not assumed idempotent.
        user_agent: Optional ``User-Agent`` string for server-side traceability.
        session: Inject a pre-built session (mainly for testing).
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
        if not base_url or not str(base_url).strip():
            raise ViyaConfigError("base_url must be a non-empty string")
        if not token or not str(token).strip():
            raise ViyaConfigError("token must be a non-empty string")

        self.base_url = str(base_url).strip().rstrip("/")
        self._token = str(token)
        self.timeout = timeout
        self.verify = verify
        self._max_retries = max_retries
        self._retry_on_post = retry_on_post
        self._user_agent = user_agent
        self._session = session or self._build_session()

    # -- session / retry configuration --------------------------------------

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        methods = set(_IDEMPOTENT_METHODS)
        if self._retry_on_post:
            methods.add("POST")
        forcelist = _RETRY_STATUS if self._max_retries > 0 else ()
        retry_kwargs: dict[str, Any] = {
            "total": self._max_retries,
            "connect": self._max_retries,
            "read": self._max_retries,
            "status": self._max_retries,
            "backoff_factor": DEFAULT_BACKOFF_FACTOR,
            "status_forcelist": forcelist,
            "allowed_methods": frozenset(methods),
            "respect_retry_after_header": True,
            "raise_on_status": False,
        }
        try:
            retry = Retry(**retry_kwargs, backoff_jitter=DEFAULT_BACKOFF_JITTER)
        except TypeError:
            # urllib3 < 2.0 has no backoff_jitter parameter.
            retry = Retry(**retry_kwargs)
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
    ) -> requests.Response:
        """Issue a request and return the raw response, raising on failure."""
        url = self._url(path)
        headers = {"Authorization": f"Bearer {self._token}", "Accept": accept}
        if json_body is not None and content_type:
            headers["Content-Type"] = content_type
        if self._user_agent:
            headers["User-Agent"] = self._user_agent

        logger.debug("Viya request: %s %s", method, url)
        try:
            response = self._session.request(
                method,
                url,
                json=json_body,
                params=dict(params) if params else None,
                headers=headers,
                timeout=self.timeout,
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
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        # HTTP-date form is not parsed here; urllib3 still honors it for retries.
        return None
