"""Shared pytest fixtures for the viyapy test suite.

Per-generation Viya response fixtures (``tests/fixtures/viya35/`` and
``tests/fixtures/viya4/``) arrive with the client/MAS slice that first consumes
them; the ``output`` vs ``outputs`` matrix keys off those. For now the unit
tests are self-contained, and this module exists as the shared entry point.
"""

from __future__ import annotations

BASE_URL = "https://viya.example.com"
