"""Logging helpers.

A best-effort redaction backstop that scrubs bearer tokens from log records.
viyapy never logs tokens directly; this filter is defense in depth so that if a
future log line ever includes an ``Authorization`` header, the token is masked
before any application handler emits it.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence

_BEARER_RE = re.compile(r"(?i)(bearer\s+)\S+")
_REDACTED = r"\1***"


class RedactingFilter(logging.Filter):
    """Mask ``Bearer <token>`` occurrences in a log record's message and args.

    Scrubbing recurses into mapping and sequence arguments, so a token nested in
    a logged headers dict (``logger.debug("headers=%s", {"Authorization": ...})``)
    is masked as well.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _BEARER_RE.sub(_REDACTED, record.msg)
        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(self._scrub(a) for a in args)
        elif isinstance(args, Mapping):
            record.args = {key: self._scrub(value) for key, value in args.items()}
        return True

    @classmethod
    def _scrub(cls, value: object) -> object:
        if isinstance(value, str):
            return _BEARER_RE.sub(_REDACTED, value)
        if isinstance(value, Mapping):
            return {key: cls._scrub(item) for key, item in value.items()}
        # Recurse into lists/tuples/sets but never into str/bytes (also Sequences).
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return type(value)(cls._scrub(item) for item in value)  # type: ignore[call-arg]
        return value


class RedactingNullHandler(logging.Handler):
    """A do-nothing handler that still runs its filters.

    Unlike :class:`logging.NullHandler` — whose ``handle`` short-circuits before
    filtering — this lets :class:`RedactingFilter` scrub every record that
    propagates through the package logger, while emitting nothing itself. It also
    suppresses the "no handlers could be found" warning like ``NullHandler``.
    """

    def emit(self, record: logging.LogRecord) -> None:
        pass
