# Authentication

viyapy authenticates with an OAuth2 **bearer token**. Provide credentials with
exactly one of `token` or `auth` — passing both, or neither, raises
[`ViyaConfigError`][viyapy.ViyaConfigError].

## Static token

The common case: pass a token string you already hold.

```python
import os

from viyapy import ViyaClient

client = ViyaClient("https://viya.example.com", token=os.environ["VIYA_TOKEN"])
```

Surrounding whitespace is stripped. An empty or non-string token raises
`ViyaConfigError` before any network call.

## Refreshing provider

For tokens that expire, pass an `auth` **token provider** — a zero-argument
callable returning the *current* bearer token. viyapy calls it on **every
request**, so a provider that refreshes and caches internally rotates the token
transparently:

```python
def bearer() -> str:
    return my_oauth_session.current_access_token()  # refreshes as needed

client = ViyaClient("https://viya.example.com", auth=bearer)
```

The provider type is exported as [`TokenProvider`][viyapy.TokenProvider]
(`Callable[[], str]`).

!!! warning "Providers own their I/O"
    viyapy cannot bound a call into arbitrary user code, so a provider is
    responsible for its own timeout and caching. If a provider raises while
    producing a token, viyapy translates the failure into
    [`ViyaAuthError`][viyapy.ViyaAuthError] (embedding only the exception *type*,
    not its message, which could contain the raw token). Make sure your provider
    does not leak the token in its own exceptions or logs.

## Obtaining a Viya token

A bearer token is typically minted by a Viya administrator (or via your
organization's OAuth2 client-credentials / authorization-code flow). Consult your
SAS Viya administrator or the SAS documentation for how tokens are issued in your
environment; viyapy consumes whatever valid bearer token you supply.

## TLS verification

TLS verification is **on by default**. To use a private CA, pass a bundle path:

```python
client = ViyaClient(
    "https://viya.example.com",
    token=os.environ["VIYA_TOKEN"],
    verify="/path/to/ca-bundle.pem",
)
```

Disabling verification (`verify=False`) emits a
[`ViyaSecurityWarning`][viyapy.ViyaSecurityWarning] and sends your token over an
unauthenticated channel — avoid it outside local development. Using an `http://`
base URL similarly warns, since the token would travel in cleartext.

## Token safety

The library never writes the bearer token to its own logs or `repr`; a redaction
filter additionally scrubs any `Bearer <token>` pattern from log records as a
backstop.
