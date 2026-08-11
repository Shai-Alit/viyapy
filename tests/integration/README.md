# Live-Viya integration tests

These tests exercise `viyapy` against a **real** SAS Viya deployment. They are
**opt-in** and never run in default or CI test runs:

- each test skips itself unless the matching `VIYAPY_TEST_*` environment
  variables are set, so `pytest` with no config just marks them skipped;
- they carry the `integration` marker, so `pytest -m "not integration"`
  excludes them from collection entirely.

No credentials are stored in the repo — you supply host and token via your shell
when you run them.

## Environment variables

Per generation (`VIYAPY_TEST_4_*` for Viya 4, `VIYAPY_TEST_35_*` for Viya 3.5):

| Variable | Required? | Purpose |
|---|---|---|
| `<PREFIX>_HOST` | yes | Base URL, e.g. `https://viya.example.com` |
| `<PREFIX>_TOKEN` | yes | OAuth2 bearer token |
| `<PREFIX>_DECISION` | for the decision + revisions tests | A decision id to `GET` (and whose revision history to read) |
| `<PREFIX>_MODULE` | for the MAS execute/validate/submit/metadata tests | A published module id |
| `<PREFIX>_INPUTS` | optional | JSON object of MAS inputs (default `{}`) |
| `<PREFIX>_ALLOW_CRUD` | for the MAS + decision CRUD lifecycle tests | Set to any value to opt in to the module- and flow-mutating create/update/delete tests |

If `HOST`/`TOKEN` are unset the whole generation is skipped; if only
`DECISION`/`MODULE` are unset, just the test needing it is skipped. The CRUD
lifecycle tests additionally skip unless `<PREFIX>_ALLOW_CRUD` is set, since they
create and delete a module (and a decision flow) on the deployment.

## What each test does

Per generation there are several tests, all driven by the variables above:

- **decision** (`<PREFIX>_DECISION`) — `GET`s a decision flow and checks it parses.
- **decisions list** (host/token only) — pages through the deployment's decision
  flows (`client.decisions.list()`) and checks each item parses into a
  `DecisionSummary` with a usable id. Read-only, needs no `<PREFIX>_DECISION`, and
  tolerates an empty deployment (it only takes a bounded slice of the results).
- **decision revisions** (`<PREFIX>_DECISION`) — read-only: pages the flow's
  revision history (`client.decisions.revisions(...)`), checking each entry parses
  into a `Revision` with a usable id, then fetches the newest revision in full via
  `client.decisions.get_revision(...)` and asserts it round-trips into a
  `Decision`. Tolerates a flow with no separate revision history (it only takes a
  bounded slice, and skips the `get_revision` step if the slice is empty).
- **decision code** (`<PREFIX>_DECISION`) — read-only: fetches the flow's generated
  DS2 for the current revision (`client.decisions.get_code(...)`) and asserts it is
  a non-empty string, then fetches the code at one revision
  (`client.decisions.get_revision_code(...)`) and asserts the same. Tolerates a flow
  with no separate revision history (it stops after the first revision).
- **decision external artifacts** (`<PREFIX>_DECISION`) — read-only: fetches the
  flow's external artifacts for the current revision
  (`client.decisions.external_artifacts(...)`) and asserts each parses into an
  `ExternalArtifact` with a usable name, then fetches the artifacts at one revision
  (`client.decisions.revision_external_artifacts(...)`) and asserts the same. This
  endpoint is not paginated, so both calls return the full tuple in one response.
  Tolerates a flow that references no external artifacts (an empty tuple) and one
  with no separate revision history (it stops after the first revision).
- **decision crud** (`<PREFIX>_ALLOW_CRUD`) — full flow lifecycle: creates a
  throwaway decision flow (an empty `{"steps": []}` flow), reads it back, updates
  its description (exercising the `ETag`/`If-Match` round trip), then deletes it
  and confirms a follow-up get 404s. Self-contained (no `<PREFIX>_DECISION`
  needed) and self-cleaning, but gated behind `ALLOW_CRUD` because it mutates the
  deployment.
- **mas execute** (`<PREFIX>_MODULE`, `<PREFIX>_INPUTS`) — executes the module
  step and checks the outputs parse.
- **mas validate** (`<PREFIX>_MODULE`, `<PREFIX>_INPUTS`) — POSTs the inputs to the
  server-side validations endpoint (`client.mas.validate_remote(...)`). It runs
  with `raise_on_invalid=False`, so it passes whether or not your inputs match the
  step signature — it only asserts the endpoint returns a structured
  `ValidationResult`. Inspect `result.valid` and `result.messages` to see the
  server's verdict for your inputs.
- **mas submit** (`<PREFIX>_MODULE`, `<PREFIX>_INPUTS`) — fire-and-forget execution
  (`client.mas.submit(...)`, i.e. `wait_time=0`). Asserts the server returns an
  `ExecutionResult` with `submitted` set and empty outputs.
- **mas metadata** (`<PREFIX>_MODULE`, `<PREFIX>_INPUTS`) — executes with
  `client_id`/`transaction_id` and asserts the server echoes both back on the
  `ExecutionResult`.
- **mas crud** (`<PREFIX>_ALLOW_CRUD`) — full module lifecycle: creates a small
  throwaway DS2 module, reads its source, updates the source (exercising the
  `ETag`/`If-Match` round trip), then deletes it. Self-contained (no
  `<PREFIX>_MODULE` needed) and self-cleaning, but gated behind `ALLOW_CRUD`
  because it mutates the deployment.
- **mas compile_job** (`<PREFIX>_ALLOW_CRUD`) — async compile lifecycle: submits a
  compile job (`submit_compile_job`), polls it to completion (`wait_for_job`),
  confirms the compiled module exists, then deletes it; also submits a
  parse-ok/compile-fail source and asserts it reaches a `failed` job carrying
  diagnostics. Self-contained and self-cleaning, gated behind the same
  `ALLOW_CRUD` opt-in because it mutates the deployment.

## Running against Viya 4

```bash
export VIYAPY_TEST_4_HOST="https://viya.example.com"
export VIYAPY_TEST_4_TOKEN="$(cat my-token.txt)"
export VIYAPY_TEST_4_DECISION="my-decision-id"
export VIYAPY_TEST_4_MODULE="api_tester1_0"
export VIYAPY_TEST_4_INPUTS='{"input_string": "this is a test"}'

pytest -m integration -v          # run only the integration tests
# or run the whole suite; the configured ones execute, the rest skip:
pytest
```

The Viya 3.5 tests use the same variables with the `VIYAPY_TEST_35_` prefix and
stay skipped until a 3.5 instance is available.
