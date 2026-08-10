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

from viyapy import (
    CompileJob,
    Decision,
    ExecutionResult,
    MasModule,
    ModuleSource,
    ValidationResult,
    ViyaClient,
)

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


def _check_submit(client: ViyaClient, module_id: str, inputs_json: str | None) -> None:
    inputs = json.loads(inputs_json) if inputs_json else {}
    # Fire-and-forget: wait_time=0 returns immediately. The server reports
    # executionState "submitted" with empty outputs.
    result = client.mas.submit(module_id, inputs)
    assert isinstance(result, ExecutionResult)
    assert result.submitted is True
    assert result.outputs == {}


def _check_metadata(client: ViyaClient, module_id: str, inputs_json: str | None) -> None:
    inputs = json.loads(inputs_json) if inputs_json else {}
    # MAS echoes correlation ids supplied in the request metadata back on the
    # response, so a round trip should surface them on the result.
    result = client.mas.execute(
        module_id, inputs, client_id="viyapy-live", transaction_id="viyapy-live-txn"
    )
    assert isinstance(result, ExecutionResult)
    assert result.client_id == "viyapy-live"
    assert result.transaction_id == "viyapy-live-txn"


# A tiny, self-contained DS2 module used by the CRUD lifecycle test. It exposes
# an ``execute`` step that echoes an integer, so it compiles without external
# dependencies and can be created and torn down on any deployment.
_CRUD_DS2_SOURCE = (
    "package viyapy_crud / overwrite=yes;\n"
    "  method execute(int in_val, in_out int out_val);\n"
    "    out_val = in_val;\n"
    "  end;\n"
    "endpackage;\n"
)
_CRUD_DS2_SOURCE_V2 = _CRUD_DS2_SOURCE.replace("out_val = in_val;", "out_val = in_val + 1;")


def _check_crud(client: ViyaClient) -> None:
    # Full lifecycle against the live server: create a throwaway module, read and
    # update its source (exercising the ETag/If-Match round trip), then delete it.
    # The module id is unique per run so repeated runs don't collide, and the
    # delete runs in a finally so a mid-test failure still cleans up.
    module_id = f"viyapy_crud_{os.getpid()}"
    created = False
    try:
        module = client.mas.create(module_id, _CRUD_DS2_SOURCE, description="viyapy live CRUD")
        created = True
        assert isinstance(module, MasModule)
        assert module.id == module_id

        src = client.mas.get_source(module_id)
        assert isinstance(src, ModuleSource)
        assert "execute" in src.source

        updated = client.mas.update_source(module_id, _CRUD_DS2_SOURCE_V2)
        assert isinstance(updated, ModuleSource)
        assert "in_val + 1" in updated.source
    finally:
        if created:
            client.mas.delete(module_id)


# A source that parses into a valid package but fails to *compile* (it calls a
# function that doesn't exist). MAS accepts this as a job that then reaches the
# ``failed`` state — the async failure path, distinct from a synchronous 400.
_COMPILE_FAIL_DS2_SOURCE = (
    "package viyapy_jobfail / overwrite=yes;\n"
    "  method execute(int in_val, in_out int out_val);\n"
    "    out_val = viyapy_nonexistent_func(in_val);\n"
    "  end;\n"
    "endpackage;\n"
)


def _check_compile_job(client: ViyaClient) -> None:
    # Full async-compile lifecycle against the live server: submit a compile job,
    # poll it to completion, confirm the module now exists, then delete it. Also
    # exercises the failure path (a parse-ok/compile-fail source -> failed job).
    module_id = f"viyapy_job_{os.getpid()}"
    created = False
    try:
        job = client.mas.submit_compile_job(module_id, _CRUD_DS2_SOURCE)
        assert isinstance(job, CompileJob)
        assert job.id
        assert not job.done  # accepted asynchronously (typically "pending")

        done = client.mas.wait_for_job(job.id)
        assert done.completed
        created = True

        # The compiled module is now real and fetchable.
        module = client.mas.get(done.module_id or module_id)
        assert isinstance(module, MasModule)
        assert module.id == module_id

        # Failure path: a source that compiles-fails yields a terminal failed job
        # carrying diagnostics (not an HTTP error), when not raising.
        failed = client.mas.wait_for_job(
            client.mas.submit_compile_job(f"{module_id}_bad", _COMPILE_FAIL_DS2_SOURCE).id,
            raise_on_failure=False,
        )
        assert failed.failed
        assert failed.errors
    finally:
        if created:
            client.mas.delete(module_id)


def _run(prefix: str, version: str, kind: str) -> None:
    env = _require(prefix)
    if kind == "decision":
        if not env["decision"]:
            pytest.skip(f"{prefix}_DECISION not set")
        with ViyaClient(env["host"], env["token"], viya_version=version) as client:  # type: ignore[arg-type]
            _check_decision(client, env["decision"])
        return
    if kind == "crud":
        # The CRUD lifecycle creates and deletes a module, so it's gated behind a
        # separate explicit opt-in to avoid mutating a deployment by surprise.
        if not os.getenv(f"{prefix}_ALLOW_CRUD"):
            pytest.skip(f"{prefix}_ALLOW_CRUD not set (module-mutating test)")
        with ViyaClient(env["host"], env["token"], viya_version=version) as client:  # type: ignore[arg-type]
            _check_crud(client)
        return
    if kind == "compile_job":
        # Async compile creates and deletes a module too, so gate it behind the
        # same explicit opt-in as the CRUD lifecycle.
        if not os.getenv(f"{prefix}_ALLOW_CRUD"):
            pytest.skip(f"{prefix}_ALLOW_CRUD not set (module-mutating test)")
        with ViyaClient(env["host"], env["token"], viya_version=version) as client:  # type: ignore[arg-type]
            _check_compile_job(client)
        return
    if not env["module"]:
        pytest.skip(f"{prefix}_MODULE not set")
    with ViyaClient(env["host"], env["token"], viya_version=version) as client:  # type: ignore[arg-type]
        if kind == "validate":
            _check_validate(client, env["module"], env["inputs"])
        elif kind == "submit":
            _check_submit(client, env["module"], env["inputs"])
        elif kind == "metadata":
            _check_metadata(client, env["module"], env["inputs"])
        else:
            _check_mas(client, env["module"], env["inputs"])


# -- Viya 4 (runnable when VIYAPY_TEST_4_* is configured) -------------------


def test_viya4_decision_get() -> None:
    _run("VIYAPY_TEST_4", "4", "decision")


def test_viya4_mas_execute() -> None:
    _run("VIYAPY_TEST_4", "4", "mas")


def test_viya4_mas_validate() -> None:
    _run("VIYAPY_TEST_4", "4", "validate")


def test_viya4_mas_submit() -> None:
    _run("VIYAPY_TEST_4", "4", "submit")


def test_viya4_mas_metadata() -> None:
    _run("VIYAPY_TEST_4", "4", "metadata")


def test_viya4_mas_crud() -> None:
    _run("VIYAPY_TEST_4", "4", "crud")


def test_viya4_mas_compile_job() -> None:
    _run("VIYAPY_TEST_4", "4", "compile_job")


# -- Viya 3.5 (scaffold — skipped until a 3.5 instance is available) --------


def test_viya35_decision_get() -> None:
    _run("VIYAPY_TEST_35", "3.5", "decision")


def test_viya35_mas_execute() -> None:
    _run("VIYAPY_TEST_35", "3.5", "mas")


def test_viya35_mas_validate() -> None:
    _run("VIYAPY_TEST_35", "3.5", "validate")


def test_viya35_mas_submit() -> None:
    _run("VIYAPY_TEST_35", "3.5", "submit")


def test_viya35_mas_metadata() -> None:
    _run("VIYAPY_TEST_35", "3.5", "metadata")


def test_viya35_mas_crud() -> None:
    _run("VIYAPY_TEST_35", "3.5", "crud")


def test_viya35_mas_compile_job() -> None:
    _run("VIYAPY_TEST_35", "3.5", "compile_job")
