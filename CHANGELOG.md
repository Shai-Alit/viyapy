# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Changed

- Require `requests>=2.30` and `urllib3>=2.0` (2.30 is the first `requests`
  release that permits urllib3 2.x; 2.x enables `backoff_jitter`).

### Removed

- Legacy script-style tests that required a live Viya server and `keyring`.
