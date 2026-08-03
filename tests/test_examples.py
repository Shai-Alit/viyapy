"""Smoke tests for the example scripts — no live network.

Every script under ``examples/`` is imported (which never runs its ``main()``,
guarded by ``if __name__ == "__main__"``) to prove it stays import-valid, and
each ``main()`` is exercised against mocked HTTP so a drifted method name or
signature fails here rather than in a user's copy.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
import responses

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
EXAMPLE_FILES = sorted(EXAMPLES_DIR.glob("*.py"))
BASE = "https://viya.example.com"


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_imports_cleanly(path: Path) -> None:
    module = _load(path)
    assert callable(module.main)


def test_examples_are_discovered() -> None:
    # Guard against the glob silently matching nothing (which would pass vacuously).
    assert {p.name for p in EXAMPLE_FILES} >= {"inspect_decision.py", "execute_module.py"}


@responses.activate
def test_inspect_decision_example_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/decisions/flows/d1",
        json={"id": "d1", "name": "Demo Decision", "flow": {"steps": []}},
        status=200,
    )
    monkeypatch.setenv("VIYA_URL", BASE)
    monkeypatch.setenv("VIYA_TOKEN", "tok")
    monkeypatch.setenv("VIYA_DECISION", "d1")

    _load(EXAMPLES_DIR / "inspect_decision.py").main()

    assert "Demo Decision" in capsys.readouterr().out


@responses.activate
def test_execute_module_example_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses.add(
        responses.POST,
        f"{BASE}/microanalyticScore/modules/m/steps/execute",
        json={"outputs": [{"name": "out", "value": 42}]},
        status=200,
    )
    monkeypatch.setenv("VIYA_URL", BASE)
    monkeypatch.setenv("VIYA_TOKEN", "tok")
    monkeypatch.setenv("VIYA_MODULE", "m")
    monkeypatch.setenv("VIYA_INPUTS", json.dumps({"input_string": "x"}))

    _load(EXAMPLES_DIR / "execute_module.py").main()

    assert "out = 42" in capsys.readouterr().out
