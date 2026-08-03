# viyapy

[![PyPI](https://img.shields.io/pypi/v/viyapy.svg)](https://pypi.org/project/viyapy/)
[![Python versions](https://img.shields.io/pypi/pyversions/viyapy.svg)](https://pypi.org/project/viyapy/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://github.com/Shai-Alit/viyapy/actions/workflows/ci.yml/badge.svg)](https://github.com/Shai-Alit/viyapy/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-%E2%89%A590%25-brightgreen.svg)](https://github.com/Shai-Alit/viyapy/actions/workflows/ci.yml)

A typed Python client for **SAS Viya Intelligent Decisioning** — inspect decision
flows and execute [Micro Analytic Score (MAS)](https://developer.sas.com/) modules
over the REST API. It supports both **Viya 3.5** and **Viya 4** (LTS and Stable)
through a version/dialect layer, and is built for production use: one hardened
HTTP stack with mandatory timeouts and retries, a typed exception hierarchy,
bearer-token redaction in the library's logs and `repr`, and full type hints
(`py.typed`).

## Install

> **Pre-release note:** the `ViyaClient` API documented below ships in
> **viyapy 3.0**, which is not yet published to PyPI (the current PyPI release
> predates this API). Until 3.0 is released, install from source:
> `pip install "git+https://github.com/Shai-Alit/viyapy@main"`.

Once 3.0 is published, the usual install applies:

```bash
pip install viyapy
```

Requires Python 3.9+.

## Quickstart

```python
import os

from viyapy import ViyaClient

my_token = os.environ["VIYA_TOKEN"]  # your OAuth2 bearer token
client = ViyaClient("https://viya.example.com", token=my_token)

# Inspect a decision flow and its models
decision = client.decisions.get("my-decision-id")
for model in decision.models:
    print(model.name, model.modified_by)

# Execute a published decision's MAS module against a feature dict
result = client.mas.execute("api_tester1_0", {"input_string": "this is a test"})
print(result.outputs["output_string"])
```

`ViyaClient` is also a context manager (`with ViyaClient(...) as client: ...`),
which closes the underlying HTTP session on exit.

### Choosing the Viya generation

The client targets Viya 4 by default. For a Viya 3.5 deployment, pass
`viya_version`:

```python
client = ViyaClient("https://viya.example.com", token=my_token, viya_version="3.5")
```

The dialect layer handles the endpoint, media-type, and response-shape
differences (including the MAS `output` vs `outputs` key) for you.

## Authentication

Provide credentials with exactly one of `token` or `auth`.

A static bearer token:

```python
client = ViyaClient("https://viya.example.com", token=os.environ["VIYA_TOKEN"])
```

Or an `auth` **token provider** — a zero-argument callable returning the current
token, called on every request. A provider that refreshes and caches internally
gives transparent token rotation:

```python
def bearer() -> str:
    return my_oauth_session.current_access_token()  # refreshes as needed

client = ViyaClient("https://viya.example.com", auth=bearer)
```

TLS verification is on by default; pass `verify="/path/to/ca-bundle.pem"` for a
custom CA, and see the docs before ever disabling it. The library does not write
the bearer token to its logs or `repr`; a redaction filter additionally scrubs
any `Bearer <token>` pattern from log records as a backstop. (A custom `auth`
provider is responsible for not leaking the token in its own exceptions/logs.)

## Error handling

Every failure raises a typed `ViyaError` subclass — the library never prints,
never swallows exceptions, and never returns `None` to signal failure. API
errors (`ViyaAPIError` and its subclasses) carry the HTTP status, the SAS Viya
error code and details, and a correlation id when the server provides one;
local configuration errors (`ViyaConfigError`) and malformed-response errors
(`ViyaResponseError`) carry their own context instead. Catch broadly or
precisely:

```python
from viyapy import ViyaError, ViyaNotFoundError, ViyaRateLimitError

try:
    result = client.mas.execute("api_tester1_0", {"input_string": "x"})
except ViyaNotFoundError:
    ...  # the module or step does not exist
except ViyaRateLimitError as exc:
    retry_after = exc.retry_after
except ViyaError as exc:
    logger.error("Viya call failed: %s", exc)  # base class catches everything
```

## Documentation

Full guides and the autodoc API reference are built with MkDocs (published in a
later release). In the meantime:

- **Migrating from the 2.x flat API:** [`MIGRATION.md`](MIGRATION.md)
- **Changelog:** [`CHANGELOG.md`](CHANGELOG.md)

## Supported versions

- **Python:** 3.9 – 3.13
- **SAS Viya:** 3.5 and Viya 4 (LTS and Stable tracks). Viya 3.5 **revision
  24w44 (October 2024) or later**, deployed on a supported Linux distribution,
  holds Standard Support through **October 1, 2027**; older revisions and other
  platforms fall under Limited Support. Confirm your deployment against SAS's
  current [Viya support policy](https://support.sas.com/).

## License

MIT © Sean Ford. See [`LICENSE`](LICENSE).

## References

1. SAS Institute Inc. 2020. *SAS® Intelligent Decisioning: Decision Management REST API Examples.* Cary, NC: SAS Institute Inc.
2. [SAS Developer — Decision Management REST API](https://developer.sas.com/apis/rest/DecisionManagement/)
