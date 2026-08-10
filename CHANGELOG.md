# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- MAS step signatures: `client.mas.get_signature(module_id, step="execute")`
  fetches a module step's input/output signature as the new typed
  `StepSignature` (with `inputs`/`outputs` tuples of `Variable(name, type, dim,
  size)`, both exported from the package root, raw payload on `.raw`). Useful for
  validating a payload or building a form before calling `execute`. Blank
  `module_id`/`step` fail fast with `ViyaConfigError`; a response that isn't a
  usable signature raises `ViyaResponseError`. Declared as the
  `get_mas_module_step_signature` endpoint in both generation contracts with
  per-generation fixtures, and added as a required endpoint in the drift gate.
- MAS module introspection: `client.mas.list()` iterates the deployment's MAS
  modules (lazily, following the collection's pagination links) and
  `client.mas.get(module_id)` fetches a single module's metadata, both returning
  the new typed `MasModule` dataclass (exported from the package root, with its
  raw payload on `.raw`). `list()` accepts a `page_size` (default 100) and
  fails fast with `ViyaConfigError` on a non-positive value.
- Reusable collection pagination (`viyapy._pagination.iter_collection`) that
  walks `application/vnd.sas.collection+json` responses by following `rel="next"`
  links, terminating safely on a self-referential link. This is the shared
  foundation for the `list`-style operations in later phases.
- API-drift coverage for the new `list_mas_modules` and `get_mas_module`
  endpoints: declared in `contracts/viya4.yaml` and `contracts/viya35.yaml`, with
  `mas_modules.json`/`mas_module.json` fixtures per generation and matching checks
  in `scripts/check_api_drift.py`. Both are now required endpoints in the drift
  gate, so a dropped contract entry can't silently bypass the check.

### Changed

- Hardened request-path construction: dynamic segments (`decision_id`,
  `module_id`, and the MAS `step`) are now percent-encoded, so a reserved
  character (`/`, `?`, `#`, …) in an id can no longer alter the request path.
- `parse_module` now raises `ViyaResponseError` when a module payload carries no
  usable string `id`, instead of returning a `MasModule` with a false identity
  (e.g. the literal `"None"`).

### Removed

- Dropped support for Python 3.9 (end-of-life October 2025); the minimum
  supported version is now Python 3.10. `requires-python`, the CI/nightly
  matrices, and the ruff/mypy target versions are updated accordingly.

## [3.0.0] - 2026-08-03

First release of the rewritten library. A clean break from the 2.x flat API;
see `MIGRATION.md`.

### Added

- API-drift detection: `supported_viya.yaml` (the Viya 4 Stable/LTS + Viya 3.5
  support matrix) and per-generation `contracts/*.yaml` declaring the REST
  endpoints and response shapes viyapy depends on, enforced by
  `scripts/check_api_drift.py` (run in the test suite and by an `API Drift`
  workflow) so any divergence between the contracts, the dialect code, and the
  captured fixtures fails CI. Because SAS publishes no machine-diffable specs,
  the workflow also opens a monthly maintainer issue to review new SAS releases.
- CI/CD automation (GitHub Actions): a `CI` workflow (ruff lint/format, mypy
  `--strict`, and a pytest matrix across Python 3.9–3.13 with the coverage gate),
  a `Docs` workflow that builds strictly on PRs and deploys to GitHub Pages from
  main, and a `Security` workflow (pip-audit, bandit, gitleaks secret scan, and a
  CycloneDX SBOM artifact) on PRs, pushes, and a weekly schedule. All actions are
  SHA-pinned with least-privilege permissions.
- Documentation site (MkDocs Material + mkdocstrings): guides for getting
  started, authentication, decisions, MAS execution, error handling, and 2.x→3.x
  migration, plus an autodoc API reference generated from the docstrings. A
  rewritten README and an enforced docstring gate (ruff pydocstyle) accompany it.
- Project-governance files (`CONTRIBUTING.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, and GitHub issue/PR templates) and runnable `examples/`
  scripts that are import- and mock-run-tested in CI so they can't drift.

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

[Unreleased]: https://github.com/Shai-Alit/viyapy/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/Shai-Alit/viyapy/releases/tag/v3.0.0
