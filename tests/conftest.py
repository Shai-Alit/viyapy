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


@pytest.fixture
def load_fixture() -> Callable[[str, str], Any]:
    """Return a loader for a per-generation JSON fixture.

    Usage: ``load_fixture("viya4", "mas_execute_ok.json")``.
    """

    def _load(generation: str, name: str) -> Any:
        return json.loads((FIXTURES_DIR / generation / name).read_text(encoding="utf-8"))

    return _load
