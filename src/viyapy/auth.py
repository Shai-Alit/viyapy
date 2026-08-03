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
"""

from __future__ import annotations

from collections.abc import Callable

from .exceptions import ViyaConfigError

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
    cleaned = str(token).strip() if token is not None else ""
    if not cleaned:
        raise ViyaConfigError("token must be a non-empty string")
    return lambda: cleaned


def read_token(provider: TokenProvider) -> str:
    """Call ``provider`` and return its token, validated non-empty.

    Raises:
        ViyaConfigError: The provider returned an empty or non-string value.
            Raised before any network call is issued.
    """
    token = provider()
    if not isinstance(token, str) or not token.strip():
        raise ViyaConfigError("the auth token provider returned an empty or non-string token")
    return token.strip()
