#!/usr/bin/env python3
"""Assert viyapy's declared REST footprint still matches its code and fixtures.

SAS does not publish versioned, machine-diffable OpenAPI specs, so this checker
does *not* diff against a live upstream spec. Instead it enforces internal
consistency between three things that must always agree:

* ``contracts/*.yaml`` — the endpoints, request bodies, and response shapes
  viyapy claims to depend on, per Viya generation;
* the ``Dialect`` subclasses — the paths, media types, and output keys the code
  actually produces;
* ``tests/fixtures/<generation>/`` — captured SAS payloads the parsers run on.

If any of these drift apart (a path edited, an output key flipped, a fixture
updated to a new SAS shape without updating the contract), the check fails. That
turns a silent upstream/behavioural change into a visible, reviewable signal.

Run directly (``python scripts/check_api_drift.py``) or via ``nox -s drift``.
Exit code is 0 when consistent, 1 when drift is found.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SUPPORTED = REPO_ROOT / "supported_viya.yaml"
CONTRACTS_DIR = REPO_ROOT / "contracts"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

# Import the package from the source tree without requiring an install.
sys.path.insert(0, str(REPO_ROOT / "src"))
import viyapy.dialects as dialects  # noqa: E402  (path set up above)
from viyapy.dialects.base import MODEL_STEP_TYPE  # noqa: E402

_ID = "__ID__"
_MODULE = "__MODULE__"
_STEP = "__STEP__"

# Every generation must declare these endpoints; the checker fails if one is
# missing so a deleted entry can't silently pass the gate.
REQUIRED_ENDPOINTS = ("get_decision_content", "execute_mas_step")


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _has_path(payload: Any, dotted: str) -> bool:
    """Return whether a dotted key path (e.g. ``flow.steps``) exists in a mapping."""
    node = payload
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def _check_generation(name: str, entry: dict[str, Any], problems: list[str]) -> None:
    """Validate one generation's contract against its dialect and fixtures."""
    tag = f"[{name}]"
    contract_path = REPO_ROOT / entry["contract"]
    if not contract_path.exists():
        problems.append(f"{tag} contract file not found: {entry['contract']}")
        return
    contract = _load_yaml(contract_path)

    # The contract's self-declared generation must match the key it's filed under.
    if contract.get("generation") != name:
        problems.append(
            f"{tag} contract generation {contract.get('generation')!r} "
            f"!= supported_viya.yaml key {name!r}"
        )
    # model_step_type is compared directly to the code constant, not just used in
    # a message, so a stale contract value is caught even if a fixture is updated.
    if contract.get("model_step_type") != MODEL_STEP_TYPE:
        problems.append(
            f"{tag} model_step_type {contract.get('model_step_type')!r} "
            f"!= code constant {MODEL_STEP_TYPE!r}"
        )

    dialect_cls = getattr(dialects, contract["dialect"], None)
    if dialect_cls is None:
        problems.append(f"{tag} dialect class {contract['dialect']!r} not found in viyapy.dialects")
        return
    dialect = dialect_cls()

    endpoints = {ep["id"]: ep for ep in contract["endpoints"]}
    for required in REQUIRED_ENDPOINTS:
        if required not in endpoints:
            problems.append(f"{tag} contract is missing required endpoint {required!r}")

    # -- decision endpoint: path + media type -------------------------------
    dec = endpoints.get("get_decision_content")
    if dec:
        expected = dec["path"].replace("{decision_id}", _ID)
        actual = dialect.decision_path(_ID)
        if actual != expected:
            problems.append(f"{tag} decision_path: code {actual!r} != contract {expected!r}")
        if dialect.decision_media_type != dec["accept"]:
            problems.append(
                f"{tag} decision Accept: code {dialect.decision_media_type!r} "
                f"!= contract {dec['accept']!r}"
            )

    # -- MAS execute endpoint: path, request body, output shape -------------
    mas = endpoints.get("execute_mas_step")
    if mas:
        expected = mas["path"].replace("{module_id}", _MODULE).replace("{step_id}", _STEP)
        actual = dialect.mas_execute_path(_MODULE, _STEP)
        if actual != expected:
            problems.append(f"{tag} mas_execute_path: code {actual!r} != contract {expected!r}")

        built = list(dialect.build_inputs({"a": 1}).keys())
        if built != mas["request_fields"]:
            problems.append(
                f"{tag} MAS request body keys: code {built} != contract {mas['request_fields']}"
            )

        if dialect.outputs_keys[0] != mas["outputs_key"]:
            problems.append(
                f"{tag} primary outputs key: code {dialect.outputs_keys[0]!r} "
                f"!= contract {mas['outputs_key']!r}"
            )

    # -- MAS module list/get endpoints: paths + media types -----------------
    modules = endpoints.get("list_mas_modules")
    if modules and dialect.mas_modules_path() != modules["path"]:
        problems.append(
            f"{tag} mas_modules_path: code {dialect.mas_modules_path()!r} "
            f"!= contract {modules['path']!r}"
        )

    module = endpoints.get("get_mas_module")
    if module:
        expected = module["path"].replace("{module_id}", _MODULE)
        actual = dialect.mas_module_path(_MODULE)
        if actual != expected:
            problems.append(f"{tag} mas_module_path: code {actual!r} != contract {expected!r}")
        if dialect.mas_module_media_type != module["accept"]:
            problems.append(
                f"{tag} module Accept: code {dialect.mas_module_media_type!r} "
                f"!= contract {module['accept']!r}"
            )

    _check_fixtures(name, contract, dialect, endpoints, problems)


def _check_fixtures(
    name: str,
    contract: dict[str, Any],
    dialect: Any,
    endpoints: dict[str, dict[str, Any]],
    problems: list[str],
) -> None:
    """Round-trip captured SAS payloads through the parsers to catch shape drift."""
    tag = f"[{name}]"
    fixtures = FIXTURES_DIR / contract["fixtures"]

    mas_ep = endpoints.get("execute_mas_step")
    mas_file = fixtures / "mas_execute_ok.json"
    if mas_ep:
        if not mas_file.exists():
            problems.append(f"{tag} missing fixture {mas_file.relative_to(REPO_ROOT)}")
        else:
            raw = _load_json(mas_file)
            # The generation's declared output key must actually be the one present.
            if mas_ep["outputs_key"] not in raw:
                problems.append(
                    f"{tag} fixture {mas_file.name} has no {mas_ep['outputs_key']!r} key "
                    f"— output shape drifted from the contract"
                )
            for field in mas_ep.get("response_fields", []):
                if not _has_path(raw, field):
                    problems.append(
                        f"{tag} fixture {mas_file.name} missing response field {field!r}"
                    )
            result = dialect.parse_execution(_MODULE, _STEP, raw)
            if not result.outputs:
                problems.append(f"{tag} {mas_file.name}: parser produced no outputs")

    modules_ep = endpoints.get("list_mas_modules")
    modules_file = fixtures / "mas_modules.json"
    if modules_ep:
        if not modules_file.exists():
            problems.append(f"{tag} missing fixture {modules_file.relative_to(REPO_ROOT)}")
        else:
            raw = _load_json(modules_file)
            for field in modules_ep.get("response_fields", []):
                if not _has_path(raw, field):
                    problems.append(
                        f"{tag} fixture {modules_file.name} missing response field {field!r}"
                    )
            items = raw.get("items")
            if not isinstance(items, list) or not items:
                problems.append(f"{tag} {modules_file.name}: collection has no items to parse")
            else:
                parsed = dialect.parse_module(items[0])
                if not parsed.id:
                    problems.append(f"{tag} {modules_file.name}: first item parsed with no id")

    module_ep = endpoints.get("get_mas_module")
    module_file = fixtures / "mas_module.json"
    if module_ep:
        if not module_file.exists():
            problems.append(f"{tag} missing fixture {module_file.relative_to(REPO_ROOT)}")
        else:
            raw = _load_json(module_file)
            for field in module_ep.get("response_fields", []):
                if not _has_path(raw, field):
                    problems.append(
                        f"{tag} fixture {module_file.name} missing response field {field!r}"
                    )
            if not dialect.parse_module(raw).id:
                problems.append(f"{tag} {module_file.name}: module parsed with no id")

    dec_ep = endpoints.get("get_decision_content")
    dec_file = fixtures / "decision_content.json"
    if dec_ep:
        if not dec_file.exists():
            problems.append(f"{tag} missing fixture {dec_file.relative_to(REPO_ROOT)}")
        else:
            raw = _load_json(dec_file)
            for field in dec_ep.get("response_fields", []):
                if not _has_path(raw, field):
                    problems.append(
                        f"{tag} fixture {dec_file.name} missing response field {field!r}"
                    )
            parsed = dialect.parse_decision(_ID, raw)
            if not parsed.models:
                problems.append(
                    f"{tag} {dec_file.name}: no model steps parsed — check model_step_type "
                    f"({contract.get('model_step_type')!r})"
                )


def check_all() -> list[str]:
    """Run every consistency check and return a list of human-readable problems."""
    problems: list[str] = []

    if not SUPPORTED.exists():
        return [f"missing {SUPPORTED.name}"]
    supported = _load_yaml(SUPPORTED)
    generations = supported.get("generations", {})
    if not generations:
        return [f"{SUPPORTED.name} declares no generations"]

    for name, entry in generations.items():
        _check_generation(name, entry, problems)

    # Every contract on disk must be referenced by the support matrix.
    referenced = {(REPO_ROOT / e["contract"]).resolve() for e in generations.values()}
    for path in sorted(CONTRACTS_DIR.glob("*.yaml")):
        if path.resolve() not in referenced:
            problems.append(f"contract {path.name} exists but is not listed in {SUPPORTED.name}")

    return problems


def main() -> int:
    """Print a report and return a process exit code (0 ok, 1 drift)."""
    problems = check_all()
    if problems:
        print("API drift check FAILED:")
        for p in problems:
            print(f"  - {p}")
        print(f"\n{len(problems)} problem(s). Update contracts/, the dialect, or the fixtures.")
        return 1
    print("API drift check passed: contracts, dialects, and fixtures are consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
