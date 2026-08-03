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
| `<PREFIX>_MODULE` | for the MAS test | A published module id to execute |
| `<PREFIX>_INPUTS` | optional | JSON object of MAS inputs (default `{}`) |

If `HOST`/`TOKEN` are unset the whole generation is skipped; if only
`DECISION`/`MODULE` are unset, just that test is skipped.

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
