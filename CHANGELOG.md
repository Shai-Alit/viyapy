# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Documentation site (MkDocs Material + mkdocstrings): guides for getting
  started, authentication, decisions, MAS execution, error handling, and 2.x→3.x
  migration, plus an autodoc API reference generated from the docstrings. A
  rewritten README and an enforced docstring gate (ruff pydocstyle) accompany it.

- `ViyaClient` — the public entry point wiring the HTTP layer to a version
  dialect, with `client.decisions` (`get`, `list_models`) and `client.mas`
  (`execute`) operation groups. Exported from the package root, works as a
  context manager, and redacts the token in `repr`.
- Pluggable authentication: pass either a static `token` or an `auth` token
  provider (`TokenProvider`, a zero-arg callable returning the current bearer
  token) — exactly one is required. The provider is called per request, so a
  provider that refreshes internally rotates the token transparently. This makes
  future OAuth/client-credentials flows additive rather than breaking.
- `HttpClient.request_json` helper that raises `ViyaResponseError` when a 2xx
  response body is not JSON, or is JSON that is not an object.
- Boundary validation of identifiers: `decisions.get`/`list_models` and
  `mas.execute` raise `ViyaConfigError` for an empty or non-string
  `decision_id`, `module_id`, or `step` before any request is issued.
- `MIGRATION.md` — maps each legacy 2.x `viya_utils` function to its
  `ViyaClient` equivalent for porting existing scripts.
- Domain dataclasses `Decision`, `ModelStep`, and `ExecutionResult` (exported
  from the package root), each retaining its raw payload on `.raw`.
- Version/dialect layer (`viyapy.dialects`) localizing SAS Viya 3.5 vs Viya 4
  differences — endpoint paths, media types, and the MAS `output` vs `outputs`
  response shape — behind a single `Dialect` interface resolved via
  `dialects.resolve("3.5")` or `dialects.resolve("4")`. A missing output list
  now raises `ViyaResponseError` with the raw body attached.


- Typed exception hierarchy (`ViyaError` and subclasses) carrying HTTP status,
  the SAS Viya error envelope (`errorCode`, `details`), correlation id, and
  request context. Exported from the package root.
- Internal hardened HTTP layer (`HttpClient`): one reused session; mandatory
  connect/read timeouts, overridable per client and per call; retries with
  exponential backoff + jitter honoring `Retry-After` (including the HTTP-date
  form); POST excluded from retries by default; and translation of
  transport/HTTP failures into typed exceptions.
- `base_url`, token, `timeout`, and `max_retries` validation that fails fast
  with `ViyaConfigError`; a `ViyaSecurityWarning` when TLS verification is
  disabled or an `http://` URL is used; a default `viyapy/<version>` User-Agent;
  and bearer-token redaction in `HttpClient.__repr__`.
- `Retry-After` handling is bounded (a runaway server value can no longer block
  the calling thread indefinitely) while the real value is still surfaced on
  `ViyaRateLimitError.retry_after`, normalized to a non-negative finite number.
- Error-envelope parsing captures `remediation` and understands the nested
  `error` and plural `errors` shapes; `ViyaAPIError` carries `remediation`.
- Logging redaction backstop (`RedactingFilter`) attached to the package logger,
  recursing into nested mapping/sequence log arguments.
- Curated package exports (`__all__`) and `__version__`.
- Project foundation: hatchling packaging, `ruff`/`mypy`/`pytest`/coverage
  configuration, `nox` sessions, pre-commit, `py.typed`, and `.gitattributes`.
- Enforced coverage gate: the suite fails under 90% line/branch coverage
  (`--cov-fail-under` via `[tool.coverage.report]`); the modern core sits at
  ~98%.

### Changed

- Require `requests>=2.30` and `urllib3>=2.0` (2.30 is the first `requests`
  release that permits urllib3 2.x; 2.x enables `backoff_jitter`).

### Removed

- The 2.x flat API (`viyapy.viya_utils`) is removed. With no external installs
  to migrate, 3.0 is a clean break rather than a deprecation cycle; port scripts
  to `ViyaClient` using `MIGRATION.md`.
- Legacy script-style tests that required a live Viya server and `keyring`.
