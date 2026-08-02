"""Version/dialect resolution for SAS Viya 3.5 and Viya 4.

Use :func:`resolve` to turn a version string (or an explicit dialect) into a
:class:`Dialect` instance::

    resolve("4")        # -> Viya4Dialect
    resolve("3.5")      # -> Viya35Dialect
    resolve(None)       # -> the default (Viya 4)
"""

from __future__ import annotations

from ..exceptions import ViyaConfigError
from .base import Dialect
from .viya4 import Viya4Dialect
from .viya35 import Viya35Dialect

DEFAULT_VERSION = "4"

# Accepted version aliases (normalized: lowercased, "viya" prefix stripped).
_REGISTRY: dict[str, type[Dialect]] = {
    "3.5": Viya35Dialect,
    "35": Viya35Dialect,
    "3": Viya35Dialect,
    "4": Viya4Dialect,
    "4.0": Viya4Dialect,
}


def resolve(version: str | Dialect | None = None) -> Dialect:
    """Resolve a Viya version (or explicit dialect) to a :class:`Dialect`.

    Args:
        version: ``"3.5"``/``"4"`` (with or without a ``viya`` prefix), a
            :class:`Dialect` instance (returned as-is), or ``None`` for the
            default (Viya 4).

    Raises:
        ViyaConfigError: If the version is unrecognized.
    """
    if isinstance(version, Dialect):
        return version
    key = str(version if version is not None else DEFAULT_VERSION)
    key = key.strip().lower().removeprefix("viya").strip()
    dialect_cls = _REGISTRY.get(key)
    if dialect_cls is None:
        raise ViyaConfigError(f"Unknown Viya version {version!r}; expected '3.5' or '4'")
    return dialect_cls()


__all__ = ["DEFAULT_VERSION", "Dialect", "Viya4Dialect", "Viya35Dialect", "resolve"]
