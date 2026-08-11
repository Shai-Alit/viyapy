"""Shared pytest fixtures for the viyapy test suite.

Per-generation Viya response fixtures live under ``tests/fixtures/viya35/`` and
``tests/fixtures/viya4/``; the ``output`` vs ``outputs`` matrix keys off those.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

BASE_URL = "https://viya.example.com"
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# The Viya generations exercised by the version matrix, paired with the
# ``viya_version`` argument ``ViyaClient`` accepts for each.
GENERATIONS = {"viya4": "4", "viya35": "3.5"}


@pytest.fixture
def load_fixture() -> Callable[[str, str], Any]:
    """Return a loader for a per-generation JSON fixture.

    Usage: ``load_fixture("viya4", "mas_execute_ok.json")``.
    """

    def _load(generation: str, name: str) -> Any:
        return json.loads((FIXTURES_DIR / generation / name).read_text(encoding="utf-8"))

    return _load


@pytest.fixture
def load_fixture_text() -> Callable[[str, str], str]:
    """Return a loader for a per-generation raw-text fixture (e.g. ``.ds2``).

    Usage: ``load_fixture_text("viya4", "decision_code.ds2")``. Unlike
    :func:`load_fixture`, the file is returned verbatim rather than JSON-parsed.
    """

    def _load(generation: str, name: str) -> str:
        return (FIXTURES_DIR / generation / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture(params=sorted(GENERATIONS))
def generation(request: pytest.FixtureRequest) -> str:
    """Parametrize a test across every Viya generation (``viya4``, ``viya35``).

    Request this fixture (optionally with ``version_for``) to run the same
    assertions against both generations' fixtures — the version matrix §4 asks
    for. The param id is the fixture-directory name.
    """
    return str(request.param)


@pytest.fixture
def version_for() -> Callable[[str], str]:
    """Map a generation name to the ``ViyaClient(viya_version=...)`` value."""
    return lambda gen: GENERATIONS[gen]
