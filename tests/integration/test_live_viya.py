"""Opt-in live-Viya integration tests.

These hit a real SAS Viya deployment and are **skipped by default** — each test
skips itself unless the matching ``VIYAPY_TEST_*`` environment variables are set,
so they never run (and never touch the network) in default or CI runs. They also
carry the ``integration`` marker, so ``pytest -m "not integration"`` excludes
them from collection entirely.

The Viya 4 path is runnable today; the Viya 3.5 path is a scaffold that stays
skipped until a 3.5 instance is available. See ``tests/integration/README.md``
for the env vars and how to run.
"""

from __future__ import annotations

import json
import os

import pytest

from viyapy import Decision, ExecutionResult, ValidationResult, ViyaClient

pytestmark = pytest.mark.integration


def _require(prefix: str) -> dict[str, str | None]:
    """Return the configured env for ``prefix``, or skip if host/token absent."""
    host = os.getenv(f"{prefix}_HOST")
    token = os.getenv(f"{prefix}_TOKEN")
    if not host or not token:
        pytest.skip(f"{prefix}_HOST / {prefix}_TOKEN not set")
    return {
        "host": host,
        "token": token,
        "decision": os.getenv(f"{prefix}_DECISION"),
        "module": os.getenv(f"{prefix}_MODULE"),
        "inputs": os.getenv(f"{prefix}_INPUTS"),
    }


def _check_decision(client: ViyaClient, decision_id: str) -> None:
    decision = client.decisions.get(decision_id)
    assert isinstance(decision, Decision)
    assert decision.id == decision_id
    assert isinstance(decision.raw, dict)
    assert isinstance(decision.models, tuple)


def _check_mas(client: ViyaClient, module_id: str, inputs_json: str | None) -> None:
    inputs = json.loads(inputs_json) if inputs_json else {}
    result = client.mas.execute(module_id, inputs)
    assert isinstance(result, ExecutionResult)
    assert isinstance(result.outputs, dict)


def _check_validate(client: ViyaClient, module_id: str, inputs_json: str | None) -> None:
    inputs = json.loads(inputs_json) if inputs_json else {}
    # Ask the server to validate the payload. Use raise_on_invalid=False so the
    # test exercises the endpoint round trip and result shape regardless of
    # whether the configured inputs happen to match the step's signature.
    result = client.mas.validate_remote(module_id, inputs, raise_on_invalid=False)
    assert isinstance(result, ValidationResult)
    assert isinstance(result.valid, bool)
    assert isinstance(result.messages, tuple)


def _run(prefix: str, version: str, kind: str) -> None:
    env = _require(prefix)
    if kind == "decision":
        if not env["decision"]:
            pytest.skip(f"{prefix}_DECISION not set")
        with ViyaClient(env["host"], env["token"], viya_version=version) as client:  # type: ignore[arg-type]
            _check_decision(client, env["decision"])
        return
    if not env["module"]:
        pytest.skip(f"{prefix}_MODULE not set")
    with ViyaClient(env["host"], env["token"], viya_version=version) as client:  # type: ignore[arg-type]
        if kind == "validate":
            _check_validate(client, env["module"], env["inputs"])
        else:
            _check_mas(client, env["module"], env["inputs"])


# -- Viya 4 (runnable when VIYAPY_TEST_4_* is configured) -------------------


def test_viya4_decision_get() -> None:
    _run("VIYAPY_TEST_4", "4", "decision")


def test_viya4_mas_execute() -> None:
    _run("VIYAPY_TEST_4", "4", "mas")


def test_viya4_mas_validate() -> None:
    _run("VIYAPY_TEST_4", "4", "validate")


# -- Viya 3.5 (scaffold — skipped until a 3.5 instance is available) --------


def test_viya35_decision_get() -> None:
    _run("VIYAPY_TEST_35", "3.5", "decision")


def test_viya35_mas_execute() -> None:
    _run("VIYAPY_TEST_35", "3.5", "mas")


def test_viya35_mas_validate() -> None:
    _run("VIYAPY_TEST_35", "3.5", "validate")
