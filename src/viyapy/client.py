"""The public SAS Viya client."""

from __future__ import annotations

import requests

from ._http import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, HttpClient
from .auth import TokenProvider
from .decisions import DecisionsAPI
from .dialects import resolve
from .dialects.base import Dialect
from .mas import MASClient


class ViyaClient:
    """Entry point for SAS Viya Intelligent Decisioning.

    Wires the hardened HTTP layer to a version dialect and exposes the
    ``decisions`` and ``mas`` operation groups.

    Provide credentials with exactly one of ``token`` or ``auth``::

        ViyaClient(base_url, "my-static-token")           # static bearer token
        ViyaClient(base_url, auth=lambda: refresh())      # refreshing provider

    Args:
        base_url: Root URL of the Viya deployment, e.g. ``https://viya.example.com``.
        token: A static OAuth2 bearer token. Mutually exclusive with ``auth``.
        auth: A token provider — a zero-argument callable returning the current
            bearer token, called on every request (so a provider that refreshes
            internally rotates the token transparently). Mutually exclusive with
            ``token``.
        viya_version: ``"3.5"``/``"4"`` or an explicit :class:`Dialect`.
            ``None`` (the default) resolves to the library default generation
            (Viya 4). Selects endpoint paths, media types, and the ``output``
            vs ``outputs`` response handling.
        timeout: ``(connect, read)`` seconds, or a single positive float.
        verify: TLS verification — ``True``, ``False``, or a CA-bundle path.
        max_retries: Retry budget for transient failures.
        retry_on_post: Whether POSTs (e.g. MAS execute) may be retried.
        user_agent: ``User-Agent`` header override.
        session: Inject a pre-built :class:`requests.Session` (mainly for tests).

    Attributes:
        decisions: Decision-flow operations (:class:`DecisionsAPI`).
        mas: MAS module operations (:class:`MASClient`).
        dialect: The resolved version :class:`Dialect`.

    Raises:
        ViyaConfigError: If configuration is invalid, including neither or both
            of ``token``/``auth`` (URL, version, timeout, etc.).
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        auth: TokenProvider | None = None,
        viya_version: str | Dialect | None = None,
        timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
        verify: bool | str = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_on_post: bool = False,
        user_agent: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.dialect: Dialect = resolve(viya_version)
        self._http = HttpClient(
            base_url,
            token,
            auth=auth,
            timeout=timeout,
            verify=verify,
            max_retries=max_retries,
            retry_on_post=retry_on_post,
            user_agent=user_agent,
            session=session,
        )
        self.decisions = DecisionsAPI(self._http, self.dialect)
        self.mas = MASClient(self._http, self.dialect)

    @property
    def base_url(self) -> str:
        """The normalized root URL of the Viya deployment (no trailing slash)."""
        return self._http.base_url

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._http.close()

    def __enter__(self) -> ViyaClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"ViyaClient(base_url={self.base_url!r}, dialect={self.dialect.name!r})"
