"""The declared API contracts must stay consistent with code and fixtures.

This runs the same check as ``scripts/check_api_drift.py`` inside the test suite,
so a dialect/fixture/contract divergence fails a normal ``pytest`` run too — not
only the scheduled drift workflow.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_api_drift.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_api_drift", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contracts_match_dialects_and_fixtures() -> None:
    problems = _load_checker().check_all()
    assert problems == [], "API drift detected:\n" + "\n".join(problems)
