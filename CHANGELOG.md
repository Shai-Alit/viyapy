# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `parse_execution` no longer raises `TypeError` when a MAS output entry carries
  a non-string `name` (e.g. a list or number). Such a name can't address an
  output, so the entry is now skipped — matching how nameless entries are already
  handled — instead of being used as an (unhashable) dict key. Surfaced by a
  Hypothesis property test.

### Added

- A typed flow builder (`FlowBuilder`, `TermMapping`), exported from the package
  root, for composing a decision flow's `flow` graph in Python instead of
  hand-writing the SAS step JSON. `FlowBuilder` chains fluently — `.model(id,
  mappings=..., name=...)`, `.ruleset(id, mappings=..., version_id=...)`, and
  `.condition(expression, on_true=..., on_false=...)` (if/else branches are
  themselves `FlowBuilder` instances, so graphs nest to any depth) — and
  `.build()` returns the `{"steps": [...]}` dict. `TermMapping.input`/`output`/
  `in_out` construct the step-to-decision term wiring, defaulting the step term
  to the decision term for the common matching-name case. Step types the builder
  doesn't model yet (custom-object, branch) can be appended verbatim with
  `.add_step(dict)`. `client.decisions.create` and `update` now accept a
  `FlowBuilder` directly (calling `.build()` for you); a raw dict remains
  accepted. The builder is client-side and generation-agnostic; it emits only the
  authorable subset of each step (the server assigns ids, timestamps, and links),
  serializing to the flow-step shapes confirmed against a live Viya 4 instance.
- Authoring decision flows on `client.decisions`: `create`, `update`, and
  `delete`. `create(name, flow, ...)` posts a new flow
  (`POST /decisions/flows`) — for now the `flow` graph is passed through as a
  **raw dict** (an empty `{"steps": []}` is valid); the optional `description`,
  `signature`, and `properties` are forwarded verbatim, and the server-assigned
  id and revision numbers are surfaced on the returned `Decision`.
  `update(decision_id, ...)` changes a flow's authorable fields
  (`PUT /decisions/flows/{id}`): it fetches the flow to read its `ETag`, overlays
  only the fields you pass onto the current representation (so unspecified fields
  are preserved, not wiped), and sends the guarded `PUT` with `If-Match` — a
  concurrent change surfaces as a precondition failure (HTTP 412) rather than a
  silent overwrite. `delete(decision_id)` removes a flow
  (`DELETE /decisions/flows/{id}`, 204). Create and update both use the
  `application/vnd.sas.decision+json` media type for the request and response.
  Wire shapes were confirmed against a live Viya 4 instance; pinned in both
  generation contracts and covered by unit and opt-in (CRUD-gated) live
  integration tests. The `flow` graph may be passed as a raw dict or composed
  with the typed `FlowBuilder` (see above).
- Reading a decision flow's external artifacts on `client.decisions`.
  `external_artifacts(flow_id)` returns the resources a flow depends on outside
  the flow itself — most commonly the analytic store backing a model step — for
  its current revision (`GET /decisions/flows/{id}/externalArtifacts`), and
  `revision_external_artifacts(flow_id, revision_id)` returns them *at* a
  specific revision. Unlike the other decision collections this endpoint is
  **not** paginated — the server returns every artifact in one response — so both
  methods eagerly return a full `tuple` of the new `ExternalArtifact` (its
  `name`, `artifact_type`, `parent_uri`, a type-dependent `properties` dict, and
  the raw payload), exported from the package root. Wire shapes were confirmed
  against a live Viya 4 instance; pinned in both generation contracts and covered
  by unit and opt-in live integration tests.
- Reading a decision flow's generated code on `client.decisions`.
  `get_code(flow_id)` returns the flow's server-generated SAS **DS2** source for
  its current revision as raw text (`GET /decisions/flows/{id}/code`,
  `text/vnd.sas.source.ds2`), and `get_revision_code(flow_id, revision_id)`
  returns the DS2 *at* a specific revision. Both return the source verbatim as a
  string. Backed by a new `HttpClient.request_text` primitive for plain-text
  (non-JSON) endpoints. The related SAS *mapped code* endpoint (a POST binding
  the flow to input/output tables) is intentionally out of scope for now. Wire
  shapes were confirmed against a live Viya 4 instance; pinned in both generation
  contracts and covered by unit and opt-in live integration tests.
- Reading a decision flow's revision history on `client.decisions`.
  `revisions(flow_id)` lazily paginates `GET /decisions/flows/{id}/revisions`
  and yields a new lightweight `Revision` per entry — the `major.minor` version
  pair (with a convenience `label`), a `checkout` lock indicator, node count,
  and audit metadata; `get_revision(flow_id, revision_id)` returns the flow's
  full `Decision` content *at* that revision. A plain `get(flow_id)` now also
  surfaces the current revision's `major_revision`/`minor_revision`/`checkout`
  (additive, defaulting to `None` when the server omits them). Both read
  operations come from a reusable `RevisionsMixin` (a foundation for later
  ruleset revisions and lock/unlock), and `Revision` is exported from the
  package root. The revision wire shapes were confirmed against a live Viya 4
  instance; pinned in both generation contracts and covered by unit and opt-in
  live integration tests.
- Listing decision flows on `client.decisions`. `list()` lazily paginates
  `GET /decisions/flows` (following the collection's `next` links) and yields a
  new lightweight `DecisionSummary` per flow — identity plus audit metadata
  (`id`, `name`, `description`, `type`, `created_by`/`modified_by`,
  `creation_timestamp`/`modified_timestamp`, and the raw payload), but not the
  flow body; call `decisions.get(summary.id)` for the full `Decision`. `page_size`
  (default 100) is validated eagerly, raising `ViyaConfigError` at the call site.
  Reuses the shared pagination iterator. `DecisionSummary` is exported from the
  package root. The collection wire shape was confirmed against a live Viya 4
  instance; pinned in both generation contracts and covered by unit and opt-in
  live integration tests.
- Asynchronous MAS module compilation on `client.mas`. `create` gains a `wait`
  flag: `create(..., wait=True)` submits an async *compile job*, blocks until it
  settles, and returns the compiled `MasModule` (tuned by `poll_timeout`/
  `poll_interval`), while the default `wait=False` keeps the single synchronous
  `POST /modules`. The underlying steps are also exposed directly:
  `submit_compile_job` posts the module definition to `POST /microanalyticScore/jobs`
  (202) and returns a `pending` `CompileJob`; `get_job` re-fetches a job's state;
  and `wait_for_job` polls to a terminal state, raising `ViyaJobError` with the
  compiler diagnostics on a failed job (or returning it when
  `raise_on_failure=False`). A grossly unparseable source is still rejected
  synchronously as a `ViyaAPIError`; only a source that parses but fails to compile
  becomes a `failed` job. Polling is built on a new generation-agnostic helper
  (reused by later async features), which raises `ViyaPollTimeoutError` when the
  budget elapses without cancelling the server-side work. New `CompileJob`,
  `ViyaJobError`, and `ViyaPollTimeoutError` are exported from the package root. The
  submit/poll wire shapes and the sync-vs-async boundary were confirmed against a
  live Viya 4 instance; documented in both generation contracts and covered by unit
  and opt-in live integration tests.
- MAS module lifecycle management on `client.mas`: `create` compiles a module from
  source (`language` `"ds2"`/`"python"`, `scope`, optional `description`) and
  returns the resulting `MasModule`; `get_source` reads a module's source
  subresource as the new typed `ModuleSource`; `update_source` replaces a module's
  source in place; and `delete` removes a module. `update_source` honors MAS's
  optimistic concurrency by first fetching the module to read its current `ETag`
  and forwarding it verbatim as an `If-Match` header (the PUT returns `428
  Precondition Required` without it); when `language` is omitted it reuses the
  module's current language. Blank ids/source/scope and unsupported languages raise
  `ViyaConfigError` before any request; a missing `ETag` or unresolvable language
  raises `ViyaResponseError`. The create/source/update/delete wire shapes and the
  ETag/`If-Match` requirement were confirmed against a live Viya 4 instance;
  documented in both generation contracts and covered by unit and opt-in live
  integration tests. `ModuleSource` is exported from the package root.
- Binary (base64) MAS I/O and execution correlation metadata on
  `client.mas.execute`/`submit`. A `bytes`/`bytearray` input value is sent as
  base64 with `encoding: "b64"` (MAS accepts this for `binary`/`any`-typed
  variables); binary outputs marked `encoding: "b64"` are decoded back into
  `bytes` on `ExecutionResult.outputs` (an output that isn't valid base64 raises
  `ViyaResponseError`). Two new optional arguments, `client_id` and
  `transaction_id`, are sent in the request `metadata` object and echoed onto the
  new `ExecutionResult.client_id`/`transaction_id` fields; each must be a
  non-empty string when given (otherwise `ViyaConfigError` before any request),
  and omitting them sends no `metadata`. The binary wire shape and the snake_case
  `metadata.client_id`/`transaction_id` echo were confirmed against a live Viya 4
  instance; documented in both generation contracts and covered by unit and
  opt-in live integration tests.
- Asynchronous MAS execution modes on `client.mas.execute`, surfacing SAS's
  `waitTime` query parameter (milliseconds) as a new `wait_time` argument.
  Omitting it (the default) runs synchronously and returns outputs; a positive
  value runs *timed* — the call returns as soon as the run finishes, or early with
  empty outputs and `executionState: timedOut` if it doesn't; `0` is
  fire-and-forget, returning immediately with `executionState: submitted` and empty
  outputs. `wait_time` must be a non-negative integer (bool, float, str, and
  negatives raise `ViyaConfigError` before any request). Added a `client.mas.submit`
  convenience for the fire-and-forget case (`wait_time=0`), and three
  `ExecutionResult` helper properties — `completed`, `timed_out`, `submitted` — that
  read the returned `execution_state`. Timed-out and submitted responses carry no
  outputs by design, so the dialect parser now treats a missing output list as an
  empty mapping for those states (a 2xx `completed` response with no output list
  still raises `ViyaResponseError`). Documented the optional `waitTime` query param
  in both generation contracts and covered by unit and opt-in live integration
  tests. Note: MAS exposes no per-execution result-polling endpoint, so
  fire-and-forget outputs are not retrievable later.

### Fixed

- Removed the stale "pre-release / install from source" note from the README and
  the getting-started guide. viyapy is published on PyPI, so `pip install viyapy`
  is the install path; the note lingered on the PyPI project description.

## [3.1.0] - 2026-08-09

### Added

- Server-side MAS input validation: `client.mas.validate_remote(module_id, inputs,
  step="execute")` POSTs the inputs to SAS Viya's validations endpoint and returns
  the new typed `ValidationResult` (exported from the package root: `valid`,
  `version`, `messages`, `error`, `raw`). Unlike the client-side name check, the
  server also inspects types and constraints. SAS reports an invalid payload as an
  HTTP 201 with `valid: false` and an error object (not a 4xx); by default that is
  raised as `ViyaValidationError` with the server's messages on `.messages` and the
  raw body on `.response_body` — pass `raise_on_invalid=False` to get the result
  and branch on `.valid` yourself. Declared as the `validate_mas_module_step_inputs`
  endpoint (a required drift-gate endpoint) in both generation contracts with
  `mas_validation.json` fixtures, and covered by opt-in live integration tests.
- Client-side MAS input validation: `client.mas.validate(module_id, inputs,
  step="execute")` fetches the step signature and checks the supplied input names
  against it, raising the new `ViyaValidationError` (exported from the package
  root) when a declared input is missing or an undeclared one is supplied — the
  offending names are on `.missing`/`.unexpected`, with `.module_id`/`.step` for
  context. `execute` gains an opt-in `validate=True` that runs the same check
  before executing (an extra round trip; off by default so a normal execute stays
  a single request). Only names are checked, not values or types, to avoid false
  positives against Viya's permissive numeric coercion.
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

[Unreleased]: https://github.com/Shai-Alit/viyapy/compare/v3.1.0...HEAD
[3.1.0]: https://github.com/Shai-Alit/viyapy/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/Shai-Alit/viyapy/releases/tag/v3.0.0
