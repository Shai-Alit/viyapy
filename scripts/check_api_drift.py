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

import inspect
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
from viyapy.mas import MASClient  # noqa: E402

# Contract query-param names are the wire (camelCase) spelling; map each to the
# MASClient.execute keyword that must exist for the code to actually send it, so
# a declared query param can't drift away from its implementation unnoticed.
QUERY_PARAM_TO_EXECUTE_KW = {"waitTime": "wait_time"}

_ID = "__ID__"
_MODULE = "__MODULE__"
_STEP = "__STEP__"

# Every generation must declare these endpoints; the checker fails if one is
# missing so a deleted entry can't silently pass the gate.
REQUIRED_ENDPOINTS = (
    "get_decision_content",
    "execute_mas_step",
    "list_mas_modules",
    "get_mas_module",
    "create_mas_module",
    "get_mas_module_source",
    "update_mas_module_source",
    "delete_mas_module",
    "submit_mas_compile_job",
    "get_mas_compile_job",
    "get_mas_module_step_signature",
    "validate_mas_module_step_inputs",
)

_JOB = "__JOB__"

# A source-language media type used to exercise the request-body builders below.
_SOURCE_TYPE = "text/vnd.sas.source.ds2"


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

        # Any query param the contract declares must be backed by a real
        # MASClient.execute keyword, so the doc-only field can't silently lie.
        execute_kwargs = inspect.signature(MASClient.execute).parameters
        for param in mas.get("query_params", []):
            kw = QUERY_PARAM_TO_EXECUTE_KW.get(param)
            if kw is None:
                problems.append(
                    f"{tag} execute query param {param!r} is declared but the checker "
                    f"has no mapping for it (add it to QUERY_PARAM_TO_EXECUTE_KW)"
                )
            elif kw not in execute_kwargs:
                problems.append(
                    f"{tag} execute query param {param!r} has no backing "
                    f"MASClient.execute keyword {kw!r} — contract claim is unimplemented"
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

    # -- MAS module create: path, content type, body, accept ----------------
    create = endpoints.get("create_mas_module")
    if create:
        if dialect.mas_modules_path() != create["path"]:
            problems.append(
                f"{tag} create path: code {dialect.mas_modules_path()!r} "
                f"!= contract {create['path']!r}"
            )
        if dialect.mas_module_definition_media_type != create["content_type"]:
            problems.append(
                f"{tag} create Content-Type: code {dialect.mas_module_definition_media_type!r} "
                f"!= contract {create['content_type']!r}"
            )
        if dialect.mas_module_media_type != create["accept"]:
            problems.append(
                f"{tag} create Accept: code {dialect.mas_module_media_type!r} "
                f"!= contract {create['accept']!r}"
            )
        built = list(
            dialect.build_module_definition(
                _MODULE, "src", source_type=_SOURCE_TYPE, scope="public"
            ).keys()
        )
        if built != create["request_fields"]:
            problems.append(
                f"{tag} create request body keys: code {built} "
                f"!= contract {create['request_fields']}"
            )
        if not hasattr(MASClient, "create"):
            problems.append(
                f"{tag} contract declares create_mas_module but MASClient.create is missing"
            )

    # -- MAS module source get/update: path, media types, body --------------
    src_get = endpoints.get("get_mas_module_source")
    if src_get:
        expected = src_get["path"].replace("{module_id}", _MODULE)
        actual = dialect.mas_module_source_path(_MODULE)
        if actual != expected:
            problems.append(
                f"{tag} mas_module_source_path: code {actual!r} != contract {expected!r}"
            )
        if dialect.mas_module_source_media_type != src_get["accept"]:
            problems.append(
                f"{tag} source Accept: code {dialect.mas_module_source_media_type!r} "
                f"!= contract {src_get['accept']!r}"
            )
        if not hasattr(MASClient, "get_source"):
            problems.append(
                f"{tag} contract declares get_mas_module_source but MASClient.get_source is missing"
            )

    src_put = endpoints.get("update_mas_module_source")
    if src_put:
        expected = src_put["path"].replace("{module_id}", _MODULE)
        actual = dialect.mas_module_source_path(_MODULE)
        if actual != expected:
            problems.append(f"{tag} update source path: code {actual!r} != contract {expected!r}")
        if dialect.mas_module_source_media_type != src_put["content_type"]:
            problems.append(
                f"{tag} update source Content-Type: code {dialect.mas_module_source_media_type!r} "
                f"!= contract {src_put['content_type']!r}"
            )
        built = list(dialect.build_source_update(_MODULE, "src", source_type=_SOURCE_TYPE).keys())
        if built != src_put["request_fields"]:
            problems.append(
                f"{tag} update source body keys: code {built} "
                f"!= contract {src_put['request_fields']}"
            )
        # The If-Match precondition is load-bearing; the contract must declare it
        # so a future refactor that drops the header is a reviewable change.
        if "If-Match" not in src_put.get("required_headers", []):
            problems.append(
                f"{tag} update_mas_module_source must declare If-Match in required_headers "
                "(MAS returns 428 without it)"
            )
        if not hasattr(MASClient, "update_source"):
            problems.append(
                f"{tag} contract declares update_mas_module_source but "
                "MASClient.update_source is missing"
            )

    # -- MAS module delete: path --------------------------------------------
    delete = endpoints.get("delete_mas_module")
    if delete:
        expected = delete["path"].replace("{module_id}", _MODULE)
        actual = dialect.mas_module_path(_MODULE)
        if actual != expected:
            problems.append(f"{tag} delete path: code {actual!r} != contract {expected!r}")
        if not hasattr(MASClient, "delete"):
            problems.append(
                f"{tag} contract declares delete_mas_module but MASClient.delete is missing"
            )

    # -- MAS async compile job submit: path, content type, body, accept -----
    submit = endpoints.get("submit_mas_compile_job")
    if submit:
        if dialect.mas_jobs_path() != submit["path"]:
            problems.append(
                f"{tag} submit job path: code {dialect.mas_jobs_path()!r} "
                f"!= contract {submit['path']!r}"
            )
        if dialect.mas_module_definition_media_type != submit["content_type"]:
            problems.append(
                f"{tag} submit job Content-Type: code "
                f"{dialect.mas_module_definition_media_type!r} "
                f"!= contract {submit['content_type']!r}"
            )
        if dialect.mas_job_media_type != submit["accept"]:
            problems.append(
                f"{tag} submit job Accept: code {dialect.mas_job_media_type!r} "
                f"!= contract {submit['accept']!r}"
            )
        # The job is submitted with the same module.definition body as a create.
        built = list(
            dialect.build_module_definition(
                _MODULE, "src", source_type=_SOURCE_TYPE, scope="public"
            ).keys()
        )
        if built != submit["request_fields"]:
            problems.append(
                f"{tag} submit job request body keys: code {built} "
                f"!= contract {submit['request_fields']}"
            )
        if not hasattr(MASClient, "submit_compile_job"):
            problems.append(
                f"{tag} contract declares submit_mas_compile_job but "
                "MASClient.submit_compile_job is missing"
            )

    # -- MAS async compile job poll: path + media type ----------------------
    get_job = endpoints.get("get_mas_compile_job")
    if get_job:
        expected = get_job["path"].replace("{job_id}", _JOB)
        actual = dialect.mas_job_path(_JOB)
        if actual != expected:
            problems.append(f"{tag} mas_job_path: code {actual!r} != contract {expected!r}")
        if dialect.mas_job_media_type != get_job["accept"]:
            problems.append(
                f"{tag} job Accept: code {dialect.mas_job_media_type!r} "
                f"!= contract {get_job['accept']!r}"
            )
        for method in ("get_job", "wait_for_job"):
            if not hasattr(MASClient, method):
                problems.append(
                    f"{tag} contract declares get_mas_compile_job but MASClient.{method} is missing"
                )

    # -- MAS step signature endpoint: path + media type ---------------------
    step = endpoints.get("get_mas_module_step_signature")
    if step:
        expected = step["path"].replace("{module_id}", _MODULE).replace("{step_id}", _STEP)
        actual = dialect.mas_step_path(_MODULE, _STEP)
        if actual != expected:
            problems.append(f"{tag} mas_step_path: code {actual!r} != contract {expected!r}")
        if dialect.mas_step_media_type != step["accept"]:
            problems.append(
                f"{tag} step Accept: code {dialect.mas_step_media_type!r} "
                f"!= contract {step['accept']!r}"
            )

    # -- MAS validation endpoint: path, request body, media type ------------
    val = endpoints.get("validate_mas_module_step_inputs")
    if val:
        expected = val["path"].replace("{module_id}", _MODULE).replace("{step_id}", _STEP)
        actual = dialect.mas_validation_path(_MODULE, _STEP)
        if actual != expected:
            problems.append(f"{tag} mas_validation_path: code {actual!r} != contract {expected!r}")

        # The validations endpoint reuses the execute request body (an inputs list).
        built = list(dialect.build_inputs({"a": 1}).keys())
        if built != val["request_fields"]:
            problems.append(
                f"{tag} validation request body keys: code {built} "
                f"!= contract {val['request_fields']}"
            )

        if dialect.mas_validation_media_type != val["accept"]:
            problems.append(
                f"{tag} validation Accept: code {dialect.mas_validation_media_type!r} "
                f"!= contract {val['accept']!r}"
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

    src_ep = endpoints.get("get_mas_module_source")
    src_file = fixtures / "mas_module_source.json"
    if src_ep:
        if not src_file.exists():
            problems.append(f"{tag} missing fixture {src_file.relative_to(REPO_ROOT)}")
        else:
            raw = _load_json(src_file)
            for field in src_ep.get("response_fields", []):
                if not _has_path(raw, field):
                    problems.append(
                        f"{tag} fixture {src_file.name} missing response field {field!r}"
                    )
            parsed = dialect.parse_module_source(_MODULE, raw)
            if not parsed.source:
                problems.append(f"{tag} {src_file.name}: parser produced no source text")

    # The submit and poll endpoints share the job resource shape; check the poll
    # fixtures (pending/completed/failed) round-trip through the job parser.
    job_ep = endpoints.get("get_mas_compile_job") or endpoints.get("submit_mas_compile_job")
    if job_ep:
        for job_name in (
            "mas_compile_job_pending.json",
            "mas_compile_job_completed.json",
            "mas_compile_job_failed.json",
        ):
            job_file = fixtures / job_name
            if not job_file.exists():
                problems.append(f"{tag} missing fixture {job_file.relative_to(REPO_ROOT)}")
                continue
            raw = _load_json(job_file)
            for field in job_ep.get("response_fields", []):
                if not _has_path(raw, field):
                    problems.append(f"{tag} fixture {job_name} missing response field {field!r}")
            parsed = dialect.parse_compile_job(raw)
            if not parsed.id:
                problems.append(f"{tag} {job_name}: job parsed with no id")
            # The failed fixture must round-trip to a failed job carrying errors.
            if job_name.endswith("failed.json") and not (parsed.failed and parsed.errors):
                problems.append(f"{tag} {job_name}: parser did not read a failed job with errors")
            if job_name.endswith("completed.json") and not parsed.completed:
                problems.append(f"{tag} {job_name}: parser did not read a completed job")

    step_ep = endpoints.get("get_mas_module_step_signature")
    step_file = fixtures / "mas_step_signature.json"
    if step_ep:
        if not step_file.exists():
            problems.append(f"{tag} missing fixture {step_file.relative_to(REPO_ROOT)}")
        else:
            raw = _load_json(step_file)
            for field in step_ep.get("response_fields", []):
                if not _has_path(raw, field):
                    problems.append(
                        f"{tag} fixture {step_file.name} missing response field {field!r}"
                    )
            sig = dialect.parse_step_signature(_MODULE, _STEP, raw)
            if not sig.inputs and not sig.outputs:
                problems.append(
                    f"{tag} {step_file.name}: parser produced no input/output variables"
                )

    val_ep = endpoints.get("validate_mas_module_step_inputs")
    val_file = fixtures / "mas_validation.json"
    if val_ep:
        if not val_file.exists():
            problems.append(f"{tag} missing fixture {val_file.relative_to(REPO_ROOT)}")
        else:
            raw = _load_json(val_file)
            for field in val_ep.get("response_fields", []):
                if not _has_path(raw, field):
                    problems.append(
                        f"{tag} fixture {val_file.name} missing response field {field!r}"
                    )
            result = dialect.parse_validation(_MODULE, _STEP, raw)
            # The captured fixture is a valid (accepted) response, so the parser
            # must round-trip it to valid=True — a drifted shape would flip this.
            if not result.valid:
                problems.append(f"{tag} {val_file.name}: parser read the OK fixture as invalid")

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
