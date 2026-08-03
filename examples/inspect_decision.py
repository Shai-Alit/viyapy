"""Fetch a decision flow and print its models.

Run against a live Viya deployment (no credentials are stored in the repo):

    export VIYA_URL="https://viya.example.com"
    export VIYA_TOKEN="..."          # your OAuth2 bearer token
    export VIYA_DECISION="my-decision-id"
    python examples/inspect_decision.py
"""

from __future__ import annotations

import os

from viyapy import ViyaClient


def main() -> None:
    """Print the decision's name and each of its model steps."""
    with ViyaClient(os.environ["VIYA_URL"], token=os.environ["VIYA_TOKEN"]) as client:
        decision = client.decisions.get(os.environ["VIYA_DECISION"])
        print(f"Decision: {decision.name}")
        for model in decision.models:
            print(f"  - {model.name} (modified by {model.modified_by})")


if __name__ == "__main__":
    main()
