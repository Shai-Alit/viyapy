"""SAS Viya 3.5 dialect (frozen generation, Standard Support through Oct 2027)."""

from __future__ import annotations

from .base import Dialect


class Viya35Dialect(Dialect):
    """Dialect for the on-prem Viya 3.5 platform.

    Viya 3.5 synchronous MAS execution returns results under ``output`` (the
    ``outputs`` fallback keeps async/timeout responses working too).
    """

    name = "viya3.5"
    outputs_keys = ("output", "outputs")
