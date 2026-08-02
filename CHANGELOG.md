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
- `base_url` and token validation that fails fast with `ViyaConfigError`, a
  warning when TLS verification is disabled or an `http://` URL is used, a
  default `viyapy/<version>` User-Agent, and bearer-token redaction in
  `HttpClient.__repr__`.
- Logging redaction backstop (`RedactingFilter`) attached to the package logger.
- Curated package exports (`__all__`) and `__version__`.
- Project foundation: hatchling packaging, `ruff`/`mypy`/`pytest`/coverage
  configuration, `nox` sessions, pre-commit, `py.typed`, and `.gitattributes`.

### Changed

- Require `urllib3>=2.0` (enables `backoff_jitter`).

### Removed

- Legacy script-style tests that required a live Viya server and `keyring`.
