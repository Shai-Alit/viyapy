"""SAS Viya 4 (LTS and Stable) dialect."""

from __future__ import annotations

from .base import Dialect


class Viya4Dialect(Dialect):
    """Dialect for the cloud-native Viya 4 platform.

    Viya 4 synchronous MAS execution returns results under ``outputs``.
    """

    name: str = "viya4"
    outputs_keys: tuple[str, ...] = ("outputs", "output")
