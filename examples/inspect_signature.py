"""Print the input/output signature of a MAS module step.

Run against a live Viya deployment (no credentials are stored in the repo):

    export VIYA_URL="https://viya.example.com"
    export VIYA_TOKEN="..."          # your OAuth2 bearer token
    export VIYA_MODULE="api_tester1_0"
    export VIYA_STEP="execute"       # optional; defaults to "execute"
    python examples/inspect_signature.py
"""

from __future__ import annotations

import os

from viyapy import ViyaClient


def main() -> None:
    """Print each input and output variable of a module step's signature."""
    step = os.environ.get("VIYA_STEP", "execute")
    with ViyaClient(os.environ["VIYA_URL"], token=os.environ["VIYA_TOKEN"]) as client:
        sig = client.mas.get_signature(os.environ["VIYA_MODULE"], step=step)
        print(f"{sig.module_id} / {sig.id}")
        for kind, variables in (("input", sig.inputs), ("output", sig.outputs)):
            for var in variables:
                print(f"  {kind}: {var.name} ({var.type}, dim={var.dim}, size={var.size})")


if __name__ == "__main__":
    main()
