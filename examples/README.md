# Examples

Small runnable scripts showing common `viyapy` workflows. They read configuration
from environment variables — **no credentials are stored in the repo** — and hit a
real Viya deployment when run.

| Script | Env vars | What it does |
|---|---|---|
| `inspect_decision.py` | `VIYA_URL`, `VIYA_TOKEN`, `VIYA_DECISION` | Prints a decision flow's name and model steps |
| `list_modules.py` | `VIYA_URL`, `VIYA_TOKEN` | Lists the MAS modules on the deployment |
| `execute_module.py` | `VIYA_URL`, `VIYA_TOKEN`, `VIYA_MODULE`, `VIYA_INPUTS` (optional) | Executes a MAS module and prints its outputs |

Example:

```bash
export VIYA_URL="https://viya.example.com"
export VIYA_TOKEN="$(cat my-token.txt)"
export VIYA_DECISION="my-decision-id"
python examples/inspect_decision.py
```

These scripts are import-smoke-tested and exercised against mocked HTTP in CI
(`tests/test_examples.py`), so they can't drift out of sync with the library API.
