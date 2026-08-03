# viyapy — Production Readiness Plan

Goal: take `viyapy` from a working side project to the standard Python library for SAS Viya Intelligent Decisioning, held to the standard a senior Python developer would expect. This document is the assessment and the roadmap. It proposes **no feature work** — only the engineering, testing, and documentation needed to make the existing capability production-grade.

---

## 1. Current-state assessment

### 1.1 What exists
The entire library is one module, `src/viyapy/viya_utils.py` (~160 lines, 7 functions), with an empty `__init__.py`. Published to PyPI as `viyapy` 2.0.0.

| Function | Purpose |
|---|---|
| `post` | Raw authenticated POST helper (OAuth2 bearer token) |
| `get` | Raw authenticated GET helper |
| `get_decision_content` | Fetch a decision flow by id |
| `get_models` | Extract model steps from a decision flow |
| `gen_viya_inputs` | Build the MAS input payload from a dict |
| `call_id_api` | Execute a MAS module (`/steps/execute`) |
| `unpack_viya_outputs` | Flatten MAS outputs into a dict |

The core value proposition is sound and genuinely useful: authenticate to Viya, inspect a decision's models, and execute a MAS module against a feature dictionary. That is a real workflow worth standardizing.

### 1.2 Problems, by severity

**Blocking correctness / reliability**
- **Two HTTP stacks.** `post` uses `requests`; `get` uses `urllib`. This is inconsistent, and the `urllib` path swallows errors and returns `None` implicitly on failure, so callers can't tell success from failure.
- **Broken error handling.** `get_models` gates its logic on `response['httpStatusCode'] == 400` — 400 is an error code, so the "success" branch only runs when the request *failed*. The happy path (200, where the key is usually absent) never executes. This function is effectively non-functional against a real server.
- **Bare `except:` clauses** in `get_models` (and the tests) hide all failures, including `KeyboardInterrupt`, and print to stdout instead of raising.
- **`gen_viya_inputs` builds JSON by string concatenation**, then `call_id_api` re-parses it. This is fragile (no escaping of quotes/newlines/unicode in string values → invalid JSON and possible injection of malformed payloads) and unnecessary — it should build a dict and let `requests` serialize it.
- **Hard-coded input-name suffix `"{k}_"`.** Appending `_` to every feature name is an undocumented assumption about how the user named MAS inputs; it will silently mismatch for many modules.

**Reliability / production-hygiene**
- **No timeouts, no retries** on any HTTP call. A hung Viya endpoint hangs the caller forever.
- **No connection reuse.** Every call opens and closes a fresh session; auth, base URL, and TLS settings are passed positionally on every call.
- **`print()` used for error reporting.** A library must never print; it should raise typed exceptions and use `logging`.
- **No TLS/verification story.** The v3 test targets `https://` but there's no place to configure cert verification or a CA bundle.

**Engineering standards**
- **No type hints, no docstrings** in a machine-readable format (comments only).
- **No input validation.** URLs, tokens, and ids are trusted blindly.
- **`__init__.py` is empty** — there is no defined public API surface; users must import from `viyapy.viya_utils`.
- **Naming is non-idiomatic** (`baseUrl`, `accessToken1`, `url1`) — camelCase args, numeric suffixes.
- **Packaging is thin.** `setup.cfg` declares no dependencies (`requests` is unlisted), no `[options.extras_require]`, no version pinning strategy, and `python_requires = >=3.6` (3.6–3.7 are end-of-life).

**Testing**
- **The "tests" are not tests.** `test_package.py` / `test_package_v4.py` are top-level scripts that require a live Viya server, machine-specific `keyring` secrets, hard-coded internal hostnames (`eeclxvm067.exnet.sas.com`, `C:/certs/...`), and print PASS/FAIL instead of asserting. They cannot run in CI and would never pass on another machine. `test_package.py` even calls `unpack_viya_outputs(response['outputs'])` while the function expects the whole response — the two test files disagree on the contract.

**Docs / project meta**
- README is a stub (title, author, two citations). No install instructions, usage, API reference, or examples.
- No `CHANGELOG`, `CONTRIBUTING`, `CODE_OF_CONDUCT`, issue/PR templates, or security policy.
- No CI, no linting, no formatting, no coverage, no release automation.
- Author contact is inconsistent (README says `Sean.Ford@sas.com`; package metadata uses a personal address).

### 1.3 Verdict
The library does one valuable thing, but in its current form it is a personal utility script packaged as a library. Roughly 80% of the work to "production" is not in the feature logic — it is architecture, error handling, typing, a real test suite, CI, and docs. The good news: the surface is small, so a disciplined rewrite is a few days of focused work, not a rewrite of a large system.

### 1.4 Conformance check against current Viya APIs (verified Aug 2026)
I checked what the library does against SAS's current published REST API docs. The two endpoints the library uses still exist and are broadly correct, but there are contract details worth acting on:

- **The Decisions API now publishes a machine-readable OpenAPI spec** — currently `decisions-v28` (`https://developer.sas.com/api/apis/decisions-v28/specifications/openapi.yml`, last updated Jun 2026). This is the single most useful finding: it means conformance can be **automated** (see §7.6), not eyeballed.
- **`GET /decisions/flows/{decisionId}`** (used by `get_decision_content`) is current, with media type `application/vnd.sas.decision+json`. The decision-content shape the library walks (`flow.steps[].type == application/vnd.sas.decision.step.model`) should be re-validated against the v28 schema and captured as a contract fixture.
- **MAS execute** — the library POSTs to `/microanalyticScore/modules/{moduleId}/steps/execute`. That is correct *for published decisions* (the published module exposes a step literally named `execute`), but it is not universal — arbitrary MAS modules expose steps under `/steps/{stepId}`. v3 should make the step id a parameter defaulting to `execute`, and say so in the docs.
- **Output key mismatch (real bug risk).** `unpack_viya_outputs` keys on `outputs` (plural). SAS's current synchronous-execute example returns the results under `output` (singular), while the async/timeout responses use `outputs`. v3 must handle both and cover it with a fixture-based test — this is likely the source of the disagreement between the two old test files.
- **Unused, now-documented capabilities that make the library better without new "features":** the step-signature endpoint `GET /microanalyticScore/modules/{id}/steps/{stepId}` returns the real input/output names — this lets v3 **replace the hardcoded `"{k}_"` input-name suffix** with the actual signature instead of guessing. The validation endpoint (`POST /microanalyticScore/commons/validations/...`) and the execute options (`waitTime` for sync/async/timeout, `metadata` for client/transaction ids, `encoding: b64` for binary) are all documented and should at least be represented in the models/error handling so responses aren't misparsed.
- **Many Decisions endpoints are marked "Internal-Use Only"** in the portal. The two the library depends on are the stable, publicly-exercised ones, but this reinforces the need for drift detection: SAS can and does deprecate endpoints (several summary endpoints are already deprecated in favor of `Accept`-header variants).

None of this requires new features now; it sharpens the v3 contract and, crucially, tells us exactly what the drift-detection job in §7.6 should watch.

### 1.5 Supported Viya versions (why this drives the whole design)
The library must serve **two Viya generations with different release models**, which is the reason the old repo had two different test files:

- **Viya 3.5** — a frozen, on-prem generation. Still in Limited Support in 2026; qualifying Linux deployments (revision 24w44 / Oct 2024 or later) hold **Standard Support through Oct 1, 2027**. Real users remain on it, so v3 must support it. Its REST surface and media-type versions are older and *fixed* — there is no moving spec to track.
- **Viya 4** — cloud-native, continuously delivered on two tracks: **Stable** (monthly, `yyyy.mm`, Standard Support = current + 3 prior ≈ a 4-month window) and **LTS** (every 6 months, `yyyy.mmLTS`, current + 3 prior ≈ a 2-year window). At any moment the "supported Viya 4" surface is a *set* of versions, and it moves every month.

Design consequences that ripple through the rest of this plan: (a) the client needs a **version/dialect layer** (§2) so 3.5-vs-4 endpoint and media-type differences are handled in one place, not sprinkled through call sites; (b) tests run a **Viya-version matrix** with per-generation fixtures (§4); and (c) drift detection is **matrix- and support-window-aware** (§7.6), tracking frozen 3.5 against a pinned baseline while chasing the rolling Viya 4 tracks. Confirm the exact set of Viya 4 LTS/Stable versions to certify against — that list is the config the whole matrix keys off.

---

## 2. Target architecture (v3)

Per the decision to modernize the public API, v3 introduces a **client object** and keeps the old flat functions as a thin deprecated shim for one release.

```
src/viyapy/
  __init__.py          # curated public exports + __version__
  client.py            # ViyaClient: session, auth, base_url, timeout, retries, verify
  decisions.py         # DecisionsAPI: get_decision, list_models
  mas.py               # MASClient: execute(module_id, inputs) -> outputs
  models.py            # dataclasses: Decision, ModelStep, ExecutionResult
  exceptions.py        # ViyaError -> ViyaAuthError, ViyaAPIError, ViyaNotFoundError, ViyaTimeoutError
  _http.py             # internal request/retry/error-translation layer
  _compat.py           # deprecated shims for the old flat functions (warn + delegate)
  dialects/            # version/dialect layer — see below
    __init__.py        # resolve(version|autodetect) -> Dialect
    base.py            # Dialect protocol: paths, media types, response-shape adapters
    viya35.py          # Viya 3.5 endpoints/media types + output-shape quirks
    viya4.py           # Viya 4 (LTS/Stable) endpoints/media types
  py.typed             # PEP 561 marker
```

**Version/dialect layer.** Because Viya 3.5 and Viya 4 differ in endpoints, media-type versions, and response shapes (e.g. the `output`/`outputs` key), those differences live in one place — a `Dialect` object the client resolves once, either from an explicit `viya_version=`/`dialect=` argument or by autodetecting from the server. `ViyaClient`, `decisions`, and `mas` code against the dialect's stable interface and never branch on version inline. Adding a future Viya 4 revision that changes a path or media type is then a small, isolated dialect change (and a new contract/fixture in §7.6), not a scatter of `if version ==` checks.

### 2.1 Packaging decision: one package, not one-per-generation
**Decision: ship a single `viyapy` package that supports both Viya 3.5 and Viya 4 via the dialect layer above — not two separate packages (e.g. a `3.x` line for 3.5 and a `4.x` line for Viya 4).**

Rationale. The two generations share roughly 90% of the code: authentication, the HTTP/retry/timeout layer, the exception hierarchy, models, input building, and output parsing are identical. Splitting into separate distributions would force us to either duplicate all of that shared surface — two test suites, two release pipelines, two changelogs, bugs fixed twice — or extract a third "core" package and maintain three. For a library whose entire surface is a handful of endpoints, that overhead is disproportionate, and it pushes the version choice onto the user at install time (choosing a package) instead of letting the client select a dialect at runtime (better UX).

The dialect approach isolates exactly what actually differs (endpoints, media-type versions, the `output`/`outputs` shape) in `dialects/viya35.py` vs `dialects/viya4.py`, while everything else stays single-sourced. One `pip install viyapy`; the client autodetects or accepts `viya_version=`. When 3.5 support ends (Oct 2027, per §1.5), we delete one dialect module and its fixtures and the rest is untouched — capturing the main upside of a split (clean removal of the old generation) without the ongoing duplication tax.

The **only** condition that would justify splitting is a hard, mutually-incompatible dependency between generations — e.g. if 3.5 required a pinned old `urllib3`/TLS stack that conflicted with Viya 4's requirements. The API conformance check (§1.4) found no such conflict: both are ordinary bearer-token REST over HTTPS. If that assumption is ever violated, revisit this decision; until then, one package with dialects is the more maintainable, more idiomatic choice.


Design principles:
- **One HTTP stack** (`requests` + `requests.adapters.HTTPAdapter` with `urllib3 Retry`). Reuse one `Session` per client.
- **Configuration held once** on the client: `base_url`, `token` (or a pluggable auth callable so token refresh can be added later without an API break), `timeout`, `verify`, `max_retries`, `user_agent`.
- **Raise, don't print.** Every non-2xx response maps to a typed exception carrying status, Viya error code, and message. `logging` for diagnostics.
- **Typed payloads.** `gen_viya_inputs` becomes a validated builder that returns a dict; the input-name suffix becomes an explicit, documented option (default: no suffix).
- **Return dataclasses**, not raw dicts, for `Decision`/`ModelStep`/`ExecutionResult`, with `.raw` retained for escape-hatch access.

Illustrative target usage:

```python
from viyapy import ViyaClient

client = ViyaClient(base_url="https://viya.example.com", token=token, timeout=30)

decision = client.decisions.get("my-decision-id")
for m in decision.models:
    print(m.name, m.modified_by)

result = client.mas.execute("api_tester1_0", {"input_string": "this is a test"})
print(result.outputs["output_string"])
```

Backward-compatibility: `viyapy.viya_utils.call_id_api(...)` still works, emits a `DeprecationWarning`, and delegates to the new client internally. Removed no earlier than v4.

---

## 3. Workstreams

### Phase 0 — Baseline & scaffolding (0.5 day)
1. Pin toolchain: adopt `pyproject.toml` as the single source of truth (move metadata out of `setup.cfg`; keep `setup.cfg` only if needed). Declare `requests` as a runtime dependency and set `requires-python = ">=3.9"`.
2. Add dev tooling config: `ruff` (lint + format), `mypy` (strict), `pytest`, `pytest-cov`, `responses`/`respx` for HTTP mocking, `pre-commit`.
3. Add `py.typed`, `src`-layout confirmation, and editor/CI-friendly `Makefile` or `tox`/`nox` sessions (`lint`, `type`, `test`, `docs`, `build`).

### Phase 1 — Core refactor + hardening (2–2.5 days) — see §6
4. Build `_http.py`: single session, separate connect/read timeouts, backoff-with-jitter `Retry` (respecting `Retry-After`), and a response→exception translator that captures Viya's error code/message and any correlation id.
5. Implement `exceptions.py` hierarchy (see §6.1).
6. Implement `ViyaClient`, `decisions.py`, `mas.py`, `models.py` with input validation at the boundaries and token-redacting `__repr__`.
7. Fix the real bugs found in assessment: the inverted `httpStatusCode == 400` check, JSON-by-string-concatenation, the implicit-`None` `get`, and bare `except`.
8. Add `_compat.py` shims + `DeprecationWarning`s; wire curated exports into `__init__.py` with `__all__` and `__version__`.
9. Add structured `logging` (library-level `NullHandler`) with guaranteed secret redaction.

### Phase 2 — Test architecture (2 days) — see §4
10. Delete the two script "tests"; replace with a real suite.
11. Unit tests with mocked HTTP for every function/method, including error paths and the previously-broken branches.
12. Contract fixtures captured from real Viya responses (sanitized), stored under `tests/fixtures/`.
13. Optional live integration tests, opt-in via env vars and `-m integration`, skipped by default.
14. Coverage gate ≥ 90% on the core modules.

### Phase 3 — Documentation (1–1.5 days) — see §5
15. Rewrite README (badges, install, quickstart, auth, links).
16. Docstrings (Google or NumPy style) on all public API; enforce with `ruff`/pydocstyle.
17. Sphinx (or MkDocs Material) site with autodoc API reference, a getting-started guide, an auth guide, and runnable examples; publish to Read the Docs or GitHub Pages.
18. `CHANGELOG.md` (Keep a Changelog), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, issue/PR templates.

### Phase 4 — CI/CD, automation & release (1–1.5 days) — see §7
19. GitHub Actions CI: matrix across Python 3.9–3.13 (and `os: [ubuntu, windows, macos]` for the lowest/highest versions) running lint → type → test → coverage upload, plus a docs build. Actions pinned to full commit SHAs; `permissions:` set to least privilege; `concurrency` to cancel superseded runs.
20. Security & supply-chain automation: `pip-audit` and `bandit` jobs, `gitleaks`/secret scanning, and a generated SBOM. Fail CI on new high-severity findings.
21. Build/publish workflow using trusted publishing (OIDC) to PyPI on tag — no long-lived API tokens; build sdist + wheel with `python -m build`; verify with `twine check` and a clean-venv `pip install` smoke test.
22. Maintenance automation: Dependabot/Renovate for deps + Actions, `pre-commit.ci` autofixes, Release Drafter (or towncrier) for changelog, CODEOWNERS, and a scheduled nightly job that reruns the suite (and optional live integration) to catch upstream/Viya drift early.
23. Branch protection: require green CI + review before merge. Cut `3.0.0` (SemVer), announce, and mark the flat API deprecated in the changelog.

Estimated total: ~7–9 focused days.

---

## 4. Test architecture (detail)

Structure:
```
tests/
  conftest.py            # shared fixtures: fake client, mocked session, sample tokens
  fixtures/              # sanitized JSON captured from real Viya responses, per generation
    viya35/              # Viya 3.5 payload shapes (older media types, output-key quirks)
      decision_content.json
      mas_execute_ok.json
      mas_execute_error.json
    viya4/               # Viya 4 payload shapes (LTS/Stable)
      decision_content.json
      mas_execute_ok.json
      mas_execute_error.json
  unit/
    test_http.py         # retries, timeouts, error translation
    test_client.py       # construction, config, session reuse
    test_dialects.py     # dialect resolution/autodetect; 3.5 vs 4 paths & media types
    test_decisions.py    # get_decision, list_models (incl. the fixed 400-branch bug)
    test_mas.py          # gen inputs (escaping!), execute, unpack outputs (output/outputs)
    test_exceptions.py
    test_compat.py       # deprecated shims warn + still return correct results
  integration/
    test_live_viya.py    # @pytest.mark.integration, skipped unless VIYAPY_TEST_* env set
```

Principles:
- **No network in unit tests.** Use `responses`/`respx` to stub HTTP; assert on request URL, headers (bearer token present), body, and timeout.
- **Run a Viya-version matrix.** Parameterize the decision/MAS tests across the `viya35` and `viya4` fixture sets so both generations' response shapes (including `output` vs `outputs`) are exercised on every run — this is what the two old, mutually-inconsistent test files should have been.
- **Test the bugs as regressions.** Explicit cases: a 200 decision response yields models; a malformed feature value with quotes/unicode still produces valid JSON; a non-2xx raises the right typed exception rather than printing.
- **Contract fixtures** decouple tests from a live server while staying faithful to real payloads, and are the same per-target fixtures the §7.6 drift job validates. Refresh procedure documented in `CONTRIBUTING`.
- **Integration tests are opt-in and per-generation**, parameterized by `VIYAPY_TEST_35_*` and `VIYAPY_TEST_4_*` (host/token/module) so a maintainer with access to either a 3.5 or a Viya 4 instance can run the live suite against it; they never run in default CI and never store secrets in the repo.
- **Coverage** reported per-module, gated at ≥90% for core; `pytest --cov=viyapy --cov-fail-under=90`.
- **Property-based tests** (`hypothesis`) for `gen_viya_inputs`/`unpack_viya_outputs` to fuzz value types and confirm round-trip JSON validity.

---

## 5. Documentation standard

A library aiming to be "the standard" is judged partly on docs. Target parity with libraries like `httpx`/`requests`:

- **README**: one-paragraph what/why, install, 10-line quickstart, auth note, links to full docs and changelog, CI/coverage/PyPI badges.
- **API reference**: autodoc-generated from typed docstrings — every public class, method, exception, and dataclass documented with args, returns, raises, and a short example.
- **Guides**: Getting Started; Authentication (how to obtain a Viya token, admin token creation, TLS/cert configuration); Working with Decisions; Executing MAS Modules; Error Handling; Migrating from the 2.x flat API to the 3.x client.
- **Runnable examples** under `examples/` that are exercised in CI (via `--doctest-glob` or a smoke job) so docs can't rot.
- **Docstring style** enforced by linter; changelog entry required per PR.

---

## 6. Error handling & hardening (detail)

The single biggest gap between the current code and a production library is what happens when things go wrong. The rule throughout: **the library never prints, never swallows, and never returns `None` to signal failure — it raises a typed, contextual exception, or returns a valid result.**

### 6.1 Exception hierarchy
A single catchable base with specific subclasses so callers can be as coarse or precise as they like:

```
ViyaError(Exception)                     # base — catch-all for the library
├─ ViyaConfigError                       # bad base_url, missing token, invalid args (raised before any network call)
├─ ViyaConnectionError                   # DNS, refused, TLS failure (wraps requests.ConnectionError)
├─ ViyaTimeoutError                      # connect or read timeout exhausted
├─ ViyaAPIError                          # any non-2xx; carries status_code, viya_error_code, message, correlation_id, url, .response
│  ├─ ViyaAuthError                      # 401/403 — token invalid, expired, or insufficient scope
│  ├─ ViyaNotFoundError                  # 404 — decision/module id doesn't exist
│  ├─ ViyaRateLimitError                 # 429 — carries retry_after
│  └─ ViyaServerError                    # 5xx — retryable class
└─ ViyaResponseError                     # 2xx but body is malformed/unexpected (missing 'outputs', invalid JSON)
```

Every `ViyaAPIError` carries the parsed Viya error envelope (`errorCode`, `httpStatusCode`, `details`, `version`) plus the request `url` and any correlation/trace id from the response headers, so a caller's log line or bug report is actionable without re-running.

### 6.2 Retry, timeout & backoff policy
- **Timeouts are mandatory and separated** — a default `(connect=5s, read=30s)`, overridable per client and per call. No code path may issue a request without a timeout.
- **Retries** via `urllib3 Retry` mounted on the session: exponential backoff **with jitter**, a sane cap on attempts, retry on connection errors and 429/5xx, and **honor `Retry-After`**.
- **Idempotency awareness.** GETs retry freely. MAS `execute` (POST) is *not* assumed idempotent by default; retry-on-POST is opt-in per call, and the docs state the trade-off so users don't double-execute a decision.
- **Fail fast on config errors** (`ViyaConfigError`) before touching the network — validate `base_url` scheme/host, non-empty token, and well-formed ids.

### 6.3 Input validation & safe payloads
- Validate and normalize `base_url` (require scheme, strip trailing slash once, reject obviously malformed hosts).
- Reject empty/whitespace tokens and ids with a clear `ViyaConfigError`, not a downstream 404/401.
- Build request bodies as Python objects and let `requests`/`json` serialize — never string-concatenate JSON. This eliminates the escaping/injection bug in `gen_viya_inputs` and correctly handles quotes, newlines, and unicode in feature values.
- Validate response shape before indexing; a missing `outputs` key raises `ViyaResponseError` with the raw body attached, not a `KeyError`.

### 6.4 Secret & transport hardening
- **Never log or repr the token.** `ViyaClient.__repr__`/`__str__` and all log records redact the bearer to `***`; a redacting `logging.Filter` is installed on the library logger as a backstop.
- **TLS verification on by default.** `verify=True`; users can supply a CA bundle path or (loudly documented) disable it for dev — disabling emits a warning.
- Support proxies and a custom `User-Agent` (`viyapy/<version>`) for server-side traceability.
- Do not persist secrets anywhere; the auth callable owns token lifetime so the library never writes tokens to disk.

### 6.5 Defensive coding standards (enforced, not aspirational)
- No bare `except:` and no `except Exception` without re-raise — enforced by `ruff` (`BLE`, `E722`) in CI.
- No `print` in library code — enforced by lint.
- Public functions are fully type-annotated and pass `mypy --strict`.
- Every error branch is covered by a regression test (§4), including the three bugs found in assessment.

---

## 7. Maintenance & automation (detail)

The library should stay healthy with minimal manual effort, so contribution and release are low-friction and safe. Everything that can be a check should be an automated check.

### 7.1 Local quality gate
`pre-commit` runs `ruff` (lint + format), `mypy`, end-of-file/whitespace fixers, and a fast unit-test subset before every commit, so most issues never reach CI. The same commands are exposed as `nox`/`tox` sessions (`lint`, `type`, `test`, `docs`, `build`, `audit`) so local and CI runs are identical and reproducible.

### 7.2 Continuous integration (GitHub Actions)
- **`ci.yml`** on every push/PR: `lint → type → test` across the Python matrix (3.9–3.13), cross-OS for the boundary versions, coverage uploaded to Codecov with a PR status and a ≥90% floor.
- **`docs.yml`**: build the docs on every PR (fail on warnings), deploy to GitHub Pages / Read the Docs on merge to main.
- **`security.yml`**: `pip-audit`, `bandit`, and secret scanning; runs on PR and on a weekly schedule so newly disclosed CVEs surface even without a commit.
- **Hardening of the pipeline itself**: actions pinned to commit SHAs (not tags), workflow `permissions:` least-privilege, `concurrency` groups to cancel superseded runs, and required-status-check branch protection on main.

### 7.3 Dependency & drift management
- **Dependabot/Renovate** for runtime deps, dev deps, and GitHub Actions, grouped to reduce PR noise, with automerge for green patch/minor dev-dependency bumps.
- **Scheduled nightly run** of the full suite (and, gated behind repo secrets, the live-Viya integration tests) so upstream `requests`/`urllib3` changes or Viya API drift are caught before a user hits them, not after.
- **API contract drift detection** (see §7.6) as its own scheduled workflow, since Viya's API can change independently of anything in this repo.

### 7.4 Release automation
- **Trusted publishing (OIDC)** to PyPI triggered by a version tag — no stored API tokens. Build → `twine check` → clean-venv install smoke test → publish, all in `release.yml`.
- **Single source of version truth** (`__version__` / `pyproject.toml`), optionally driven by `setuptools-scm` from tags so releases can't drift from git.
- **Changelog automation** via Release Drafter or towncrier: each PR contributes a news fragment / label, and the release notes assemble themselves. `CHANGELOG.md` follows Keep a Changelog + SemVer.
- **Migration discipline**: deprecations always ship one minor release before removal, with a `DeprecationWarning` and a changelog entry; the 2.x→3.x migration guide is part of the docs.

### 7.5 Contributor experience & governance
- `CONTRIBUTING.md` documents setup (`pip install -e .[dev]`, `pre-commit install`), the test tiers, how to refresh contract fixtures, and the release process.
- Issue/PR templates, `CODEOWNERS`, `SECURITY.md` (how to report a vuln), and a `CODE_OF_CONDUCT.md`.
- A short **maintainer runbook**: how to cut a release, how to rotate the PyPI trusted-publisher config, and how to run the live integration suite against a test Viya.

### 7.6 Automated API contract drift detection — multi-version, multi-cadence
Because SAS evolves the Viya REST APIs on its own cadence, the library needs a mechanism that regularly compares **what we call** against **what SAS documents/ships** — so a breaking change surfaces as a tracked issue, not a user bug report. Crucially, "Viya" is not one target: the library must support **two generations with fundamentally different release models**, so the drift check is **version-matrix-aware**, not latest-only.

**The support matrix we track (as of Aug 2026 — see §1.5 for why):**

| Target | Release model | API baseline source | How drift is checked |
|---|---|---|---|
| **Viya 3.5** | Frozen generation, in Limited Support; qualifying Linux deployments in Standard Support through **Oct 1, 2027** | No live "latest" spec — 3.5 is frozen; baseline is a **pinned spec/fixture set** captured once from the 3.5 docs or a live 3.5 instance | Guard our own regressions against the pinned baseline; optional live-probe against a 3.5 instance. We do **not** chase a moving spec here. |
| **Viya 4 — LTS** | Every 6 months (`yyyy.mmLTS`); Standard Support = current + 3 prior (~2 yrs) | Pinned OpenAPI spec per still-supported LTS | Diff our declared surface against each supported LTS spec; a version that ages out of the support window is flagged for removal. |
| **Viya 4 — Stable** | Monthly (`yyyy.mm`); Standard Support = current + 3 prior (~4 months) | The **latest** published OpenAPI spec (e.g. `decisions-v28`) | Diff against latest; detect spec version bumps (`-v28`→`-v29`) as a signal a new Stable landed. |

Because 3.5 and 4 differ in endpoints and media-type versions, the library carries a **version/dialect layer** (see §2) and the contract is declared **per target**, not once globally.

**How it works (`api-drift.yml`, scheduled weekly + manually dispatchable):**
1. **Declare our surface per target.** `contracts/viya35.yaml`, `contracts/viya4-lts-<ver>.yaml`, `contracts/viya4-stable.yaml` — each listing every endpoint the library touches for that target: method, path template, request/response media types (they differ by generation), and the response fields we depend on (`flow.steps[].type`, `output`/`outputs`, `executionState`, the Viya error-envelope keys). This doubles as living documentation of our dependency footprint per Viya version.
2. **Resolve the matrix.** The job reads a single `supported_viya.yaml` (the table above as config: version ids, track, support-window end dates). This one file is the knob maintainers turn as versions come and go.
3. **Fetch/compare per target.** For **Stable/LTS**: download the relevant published OpenAPI spec and diff. For **3.5 and pinned LTS**: validate against the pinned baseline (nothing to fetch). `openapi-spec-validator` / `schemathesis` validate our declared shapes against each fetched schema; assert declared endpoints still exist with compatible methods/status codes and flag any field we rely on that changed type, was deprecated, or disappeared.
4. **Support-window watch (handles Viya 4's cadence).** Since a Stable ages out roughly every 3 months and a new one drops monthly, the job also: flags any matrix entry whose support window has **ended** (candidate to drop, with a deprecation note in our docs), and flags when a **new** Stable/LTS is detected that isn't yet in the matrix (prompt to add it and capture fixtures). This keeps us aligned with the "modern update cadence" instead of silently falling behind.
5. **Optional live probe per target.** When a test-Viya secret for a given generation is configured (`VIYAPY_TEST_35_*`, `VIYAPY_TEST_4_*`), hit the real step-signature and a canned decision/execute and assert the parsed shape matches that target's fixtures — catching drift docs alone miss (like the `output` vs `outputs` case, which may itself differ between 3.5 and 4).
6. **Report, don't fail silently.** On any drift, the workflow opens (or updates) a GitHub issue labeled with the affected target(s) and pings CODEOWNERS; it does not block unrelated PRs. A clean run is a no-op.

**Keeping fixtures honest.** Fixtures live under `tests/fixtures/<target>/` and are the same shapes the drift job validates per target, so docs, tests, and the drift check never diverge across Viya versions. `CONTRIBUTING.md` documents the per-target refresh procedure.

This makes §1.4/§1.5 an automated, recurring guarantee across **both Viya 3.5 and the rolling Viya 4 tracks**, rather than a snapshot against whatever spec happened to be newest.

### 7.7 Branching, review & merge workflow
All work follows trunk-based development with short-lived branches and mandatory review — nothing lands directly on `main`.

- **`main` is protected and always releasable.** No direct pushes; merges only via reviewed pull request with green CI (§7.2). Linear history via squash-merge keeps `main` readable.
- **One branch per phase (this plan's phases 0–4).** Phases are self-contained and reviewable in isolation, so they map cleanly to branches/PRs. If a phase is large, it may be split into stacked sub-PRs (e.g. `phase-1-http`, `phase-1-client`) that merge in order. Branch naming: `phase-<n>-<slug>` for phase work, `fix/<slug>` / `docs/<slug>` / `chore/<slug>` otherwise.
- **Conventional Commits.** Commit messages use `type(scope): summary` (`feat`, `fix`, `docs`, `test`, `chore`, `refactor`, `ci`), which also feeds the automated changelog (§7.4). Commits are scoped and logical, not a single dump.
- **Review before merge.** Every PR gets a review (CODEOWNERS auto-requested). CI — lint, type, test/coverage, security — must pass before merge. Reviewers check against the Definition of Done (§9) for the relevant phase. Once trusted publishing is set up, tagging a merge commit triggers release (§7.4).
- **Clean line endings.** A `.gitattributes` (`* text=auto eol=lf`, binary fixtures marked `binary`) prevents CRLF/LF churn — important since development spans Windows and CI Linux. Added in Phase 0 before other files so history stays clean.

**Environment note for this engagement.** Commits are prepared locally in the workspace, but this sandbox has no outbound access to GitHub and no `gh` CLI, so **pushes, PR creation, and merges are performed by the maintainer from their own machine** (where the SSH key and `gh`/browser live). Each phase therefore ends with: prepared branch + scoped commits in the working copy, plus a short handoff (the `git push` and PR-open commands, and a summary for the PR description). Code review can be run locally first (e.g. a review pass over the branch diff) before the maintainer opens the PR for human review.

---

## 8. Risks & decisions to confirm

- **Auth model.** ~~Current design assumes a pre-minted bearer token created by an admin.~~ **Resolved (Phase 2, slice 2d):** auth is now a pluggable callable. `ViyaClient` accepts either a static `token` or an `auth` token provider (`TokenProvider = Callable[[], str]`), called per request, so a provider that refreshes internally rotates the token transparently. Only the static-token path ships now; a concrete client-credentials/OAuth flow can be added later as a provider without an API break.
- **Viya version coverage (decided: support both generations — see §1.5).** v3 supports Viya 3.5 (Standard Support for qualifying Linux deployments through Oct 1, 2027) and Viya 4 across its LTS and Stable tracks, via the dialect layer (§2), a version-matrix test suite (§4), and matrix-aware drift detection (§7.6). **Live-access status (Phase 2):** the maintainer has a live **Viya 4** instance, so the Viya 4 integration/live-probe tier is built to run (opt-in via `VIYAPY_TEST_4_*`); the **Viya 3.5** tier ships as a skipped scaffold (`VIYAPY_TEST_35_*`) until a 3.5 instance is available. **Still needed:** the exact list of Viya 4 LTS/Stable versions to certify against and populate `supported_viya.yaml` with (for the §7.6 drift job in Phase 4).
- **Breaking change comms.** ~~Since 2.0.0 is on PyPI, the deprecation shim + a clear migration guide are essential to avoid stranding existing users.~~ **Resolved (Phase 2):** the maintainer confirmed 2.x had effectively no external installs, so 3.0 removes the flat API (`viya_utils`) and the `compat` bridge outright — a clean break rather than a deprecation cycle. `MIGRATION.md` is retained as a porting reference. Nothing is yanked from PyPI.
- **Name/brand.** Confirm whether this stays a personal project or becomes SAS-affiliated — it affects the LICENSE holder, contact email, code-of-conduct owner, and where the docs are hosted.
- **`output` vs `outputs` (confirm against a live server).** SAS's docs show the sync-execute payload under `output` and the async one under `outputs`. v3 should parse both, but we should confirm the real shape a *published decision* returns and lock it into a fixture — this likely explains the two old test files disagreeing.
- **MAS step id.** Default the execute step id to `execute` (correct for published decisions) but expose it as a parameter for arbitrary modules; confirm this matches the deployments you care about.
- **"Internal-Use Only" endpoints.** The Decisions endpoints the library uses are marked internal-use in the portal. Confirm SAS's stability expectations for them, and rely on the §7.6 drift job to catch deprecations early.

---

## 9. Definition of done

The library is "production ready" when:
- it installs cleanly on Python 3.9–3.13 (and on Linux/macOS/Windows) with declared, dependency-pinned requirements;
- the public API is a typed, documented client; **every failure raises a typed `ViyaError` subclass with actionable context — no `print`, no swallowed exceptions, no `None`-as-error, no request without a timeout**;
- retries with backoff/jitter, `Retry-After` handling, TLS-on-by-default, and guaranteed token redaction are in place and tested;
- every public path (including each error branch and the three fixed bugs) has unit tests with ≥90% coverage and **no network in default CI**; opt-in live integration tests exist;
- lint, format, strict type checks, `pip-audit`, `bandit`, and secret scanning all pass in CI on every PR, with the pipeline itself hardened (SHA-pinned actions, least-privilege permissions);
- a documented site with API reference, guides, and a 2.x→3.x migration guide is published and built in CI;
- releases are automated via a tagged, OIDC trusted-publish workflow with an install smoke test, and changelog/dependency updates are automated;
- the 2.x flat API still works behind deprecation warnings.
