# viyapy

A typed Python client for **SAS Viya Intelligent Decisioning** — inspect decision
flows and execute [Micro Analytic Score (MAS)](https://developer.sas.com/) modules
over the REST API.

It supports both **Viya 3.5** and **Viya 4** (LTS and Stable) through a
version/dialect layer, and is built for production use:

- one hardened HTTP stack with mandatory timeouts and a configurable retry budget
  (backoff + jitter; the internal retry sleep bounds `Retry-After`);
- a typed exception hierarchy — every failure raises a `ViyaError` subclass with
  actionable context;
- bearer-token redaction in the library's logs and `repr`;
- pluggable authentication (a static token or a refreshing provider callable);
- full type hints (`py.typed`).

## Where to next

- **[Getting Started](getting-started.md)** — install and run your first call.
- **[Authentication](authentication.md)** — static tokens and refreshing providers.
- **[Working with Decisions](decisions.md)** — fetch flows and their models.
- **[Executing MAS Modules](mas.md)** — run a module against a feature dict.
- **[Error Handling](error-handling.md)** — the exception hierarchy and retries.
- **[Migration (2.x → 3.x)](migration.md)** — porting from the old flat API.
- **[API Reference](api-reference.md)** — the full autodoc reference.
