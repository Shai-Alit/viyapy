"""viyapy — a Python client for SAS Viya Intelligent Decisioning.

Supports SAS Viya 3.5 and Viya 4 (LTS and Stable) through a version/dialect
layer. The modern ``ViyaClient`` API is introduced across the 3.x line; the
legacy flat helpers in :mod:`viyapy.viya_utils` remain available (deprecated).
"""

from __future__ import annotations

import logging

# Library best practice: attach a NullHandler so importing viyapy never emits
# "No handlers could be found" warnings. Applications configure their own.
logging.getLogger(__name__).addHandler(logging.NullHandler())
