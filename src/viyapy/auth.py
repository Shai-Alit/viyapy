"""Pluggable authentication for :class:`viyapy.ViyaClient`.

Auth is a small hook: a **token provider** is any zero-argument callable that
returns the current OAuth2 bearer token as a string. The client calls it on
every request, so a provider that refreshes and caches internally gives
transparent token rotation with no API change. A plain ``str`` token is the
common case and is wrapped into a static provider for you.

Example of a refreshing provider::

    def bearer() -> str:
        return my_oauth_session.current_access_token()  # refreshes as needed

    client = ViyaClient("https://viya.example.com", auth=bearer)

A provider owns its own I/O concerns: it is responsible for its own timeout and
caching (``viyapy`` cannot bound a call into arbitrary user code). If a provider
raises while producing a token, the exception is translated into
:class:`ViyaAuthError` so callers can still catch failures via :class:`ViyaError`.
"""

from __future__ import annotations

from collections.abc import Callable

from .exceptions import ViyaAuthError, ViyaConfigError, ViyaError

TokenProvider = Callable[[], str]
"""A zero-argument callable returning the current bearer token."""


def resolve_token_provider(token: str | None, auth: TokenProvider | None) -> TokenProvider:
    """Collapse a static ``token`` or an ``auth`` callable into one provider.

    Exactly one of ``token`` / ``auth`` must be supplied.

    Raises:
        ViyaConfigError: If both or neither is given, if ``token`` is empty, or
            if ``auth`` is not callable.
    """
    if (token is None) == (auth is None):
        raise ViyaConfigError("provide exactly one of token= or auth=")
    if auth is not None:
        if not callable(auth):
            raise ViyaConfigError("auth must be a callable returning a bearer token")
        return auth
    if not isinstance(token, str) or not token.strip():
        raise ViyaConfigError("token must be a non-empty string")
    cleaned = token.strip()
    return lambda: cleaned


def read_token(provider: TokenProvider) -> str:
    """Call ``provider`` and return its token, validated non-empty.

    Any exception the provider raises while producing a token (e.g. an I/O
    failure in a refreshing provider) is translated into :class:`ViyaAuthError`
    so it stays within the :class:`ViyaError` hierarchy. Raised before any Viya
    network call is issued.

    Raises:
        ViyaConfigError: The provider returned an empty or non-string value.
        ViyaAuthError: The provider raised while producing a token.
    """
    try:
        token = provider()
    except ViyaError:
        raise  # already a typed viyapy error; let it through unchanged
    except Exception as exc:
        # Translate any foreign provider failure into the typed hierarchy.
        raise ViyaAuthError(f"the auth token provider raised {type(exc).__name__}: {exc}") from exc
    if not isinstance(token, str) or not token.strip():
        raise ViyaConfigError("the auth token provider returned an empty or non-string token")
    return token.strip()
