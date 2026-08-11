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
| `<PREFIX>_DECISION` | for the decision test | A decision id to `GET` |
| `<PREFIX>_MODULE` | for the MAS execute/validate/submit/metadata tests | A published module id |
| `<PREFIX>_INPUTS` | optional | JSON object of MAS inputs (default `{}`) |
| `<PREFIX>_ALLOW_CRUD` | for the MAS CRUD lifecycle test | Set to any value to opt in to the module-mutating create/update/delete test |

If `HOST`/`TOKEN` are unset the whole generation is skipped; if only
`DECISION`/`MODULE` are unset, just the test needing it is skipped. The CRUD
lifecycle test additionally skips unless `<PREFIX>_ALLOW_CRUD` is set, since it
creates and deletes a module on the deployment.

## What each test does

Per generation there are several tests, all driven by the variables above:

- **decision** (`<PREFIX>_DECISION`) — `GET`s a decision flow and checks it parses.
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
