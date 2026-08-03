# viyapy

[![PyPI](https://img.shields.io/pypi/v/viyapy.svg)](https://pypi.org/project/viyapy/)
[![Python versions](https://img.shields.io/pypi/pyversions/viyapy.svg)](https://pypi.org/project/viyapy/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
<!-- CI and coverage badges are added when the CI workflow lands (Phase 4). -->

A typed Python client for **SAS Viya Intelligent Decisioning** — inspect decision
flows and execute [Micro Analytic Score (MAS)](https://developer.sas.com/) modules
over the REST API. It supports both **Viya 3.5** and **Viya 4** (LTS and Stable)
through a version/dialect layer, and is built for production use: one hardened
HTTP stack with mandatory timeouts and retries, a typed exception hierarchy,
guaranteed bearer-token redaction, and full type hints (`py.typed`).

## Install

```bash
pip install viyapy
```

Requires Python 3.9+.

## Quickstart

```python
from viyapy import ViyaClient

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
client = ViyaClient("https://viya.example.com", token=my_token)
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
custom CA, and see the docs before ever disabling it. The bearer token is never
written to logs or `repr`.

## Error handling

Every failure raises a typed `ViyaError` subclass carrying actionable context
(HTTP status, the SAS Viya error code/details, correlation id) — the library
never prints, never swallows exceptions, and never returns `None` to signal
failure. Catch broadly or precisely:

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
- **SAS Viya:** 3.5 (Standard Support for qualifying Linux deployments through
  Oct 1, 2027) and Viya 4 (LTS and Stable tracks)

## License

MIT © Sean Ford. See [`LICENSE`](LICENSE).

## References

1. SAS Institute Inc. 2020. *SAS® Intelligent Decisioning: Decision Management REST API Examples.* Cary, NC: SAS Institute Inc.
2. [SAS Developer — Decision Management REST API](https://developer.sas.com/apis/rest/DecisionManagement/)
