"""List the MAS modules on a Viya deployment and print each one.

Run against a live Viya deployment (no credentials are stored in the repo):

    export VIYA_URL="https://viya.example.com"
    export VIYA_TOKEN="..."          # your OAuth2 bearer token
    python examples/list_modules.py
"""

from __future__ import annotations

import os

from viyapy import ViyaClient


def main() -> None:
    """Print each module's id, name, and exposed steps."""
    with ViyaClient(os.environ["VIYA_URL"], token=os.environ["VIYA_TOKEN"]) as client:
        for module in client.mas.list():
            steps = ", ".join(module.step_ids) or "-"
            print(f"{module.id}\t{module.name}\tsteps: {steps}")


if __name__ == "__main__":
    main()
