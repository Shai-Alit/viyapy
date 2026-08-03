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
_BEARER_RE_BYTES = re.compile(rb"(?i)(bearer\s+)\S+")
_REDACTED_BYTES = rb"\1***"


class RedactingFilter(logging.Filter):
    """Mask ``Bearer <token>`` occurrences in a log record's message and args.

    Scrubbing applies to the message object itself (including a mapping or
    sequence passed as the message) and recurses into mapping, sequence, set, and
    ``bytes`` arguments — so a token nested in a logged headers dict
    (``logger.debug("headers=%s", {"Authorization": ...})``) is masked as well.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact any bearer token in the record's message/args; always keep it."""
        # Scrub the message object itself, not only str messages — a mapping or
        # sequence passed directly as the message must be masked too.
        record.msg = self._scrub(record.msg)
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
        if isinstance(value, (bytes, bytearray)):
            return _BEARER_RE_BYTES.sub(_REDACTED_BYTES, bytes(value))
        if isinstance(value, Mapping):
            return {key: cls._scrub(item) for key, item in value.items()}
        if isinstance(value, (set, frozenset)):
            return type(value)(cls._scrub(item) for item in value)
        # Recurse into other sequences (list/tuple), never into str/bytes above.
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
        """Do nothing (the record is only scrubbed by the attached filter)."""
