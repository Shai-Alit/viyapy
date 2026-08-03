"""Execute a MAS module against a feature dict and print its outputs.

Run against a live Viya deployment (no credentials are stored in the repo):

    export VIYA_URL="https://viya.example.com"
    export VIYA_TOKEN="..."          # your OAuth2 bearer token
    export VIYA_MODULE="api_tester1_0"
    export VIYA_INPUTS='{"input_string": "this is a test"}'   # optional, defaults to {}
    python examples/execute_module.py
"""

from __future__ import annotations

import json
import os

from viyapy import ViyaClient


def main() -> None:
    """Execute the module and print each output name/value."""
    inputs = json.loads(os.environ.get("VIYA_INPUTS", "{}"))
    with ViyaClient(os.environ["VIYA_URL"], token=os.environ["VIYA_TOKEN"]) as client:
        result = client.mas.execute(os.environ["VIYA_MODULE"], inputs)
        print(f"execution_state: {result.execution_state}")
        for name, value in result.outputs.items():
            print(f"{name} = {value}")


if __name__ == "__main__":
    main()
