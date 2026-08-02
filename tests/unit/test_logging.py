"""Unit tests for the bearer-token redaction backstop."""

from __future__ import annotations

import logging

import pytest

from viyapy._logging import RedactingFilter


def _record(msg: str, args: object = None) -> logging.LogRecord:
    return logging.LogRecord("viyapy", logging.INFO, __file__, 1, msg, args, None)


def test_masks_bearer_in_message() -> None:
    record = _record("Authorization: Bearer abc123def")
    RedactingFilter().filter(record)
    text = record.getMessage()
    assert "abc123def" not in text
    assert "Bearer ***" in text


def test_masks_bearer_in_tuple_args_and_leaves_other_args() -> None:
    record = _record("header %s code %d", ("Bearer topsecret", 42))
    RedactingFilter().filter(record)
    message = record.getMessage()
    assert "topsecret" not in message
    assert "42" in message  # non-string args pass through untouched


def test_masks_bearer_in_dict_args() -> None:
    # logging wraps a single mapping in a 1-tuple; LogRecord then unwraps it.
    record = _record("%(auth)s", ({"auth": "bearer HUNTER2"},))
    RedactingFilter().filter(record)
    assert "HUNTER2" not in record.getMessage()


def test_masks_bearer_in_nested_mapping_arg() -> None:
    record = _record("headers=%s", ({"Authorization": "Bearer deep-secret"},))
    RedactingFilter().filter(record)
    assert "deep-secret" not in record.getMessage()


def test_masks_bearer_in_nested_sequence_arg() -> None:
    record = _record("items=%s", (["Bearer a", ["Bearer b"]],))
    RedactingFilter().filter(record)
    message = record.getMessage()
    assert "Bearer a" not in message
    assert "Bearer b" not in message


def test_leaves_non_token_text_untouched() -> None:
    record = _record("plain message with no secrets")
    RedactingFilter().filter(record)
    assert record.getMessage() == "plain message with no secrets"


def test_non_string_msg_is_untouched() -> None:
    record = _record(42)  # type: ignore[arg-type]
    assert RedactingFilter().filter(record) is True
    assert record.getMessage() == "42"


def test_backstop_redacts_records_propagated_to_root(caplog: pytest.LogCaptureFixture) -> None:
    # The filter rides on the package logger's handler, so tokens are masked
    # before any application/root handler (like caplog) emits them.
    logger = logging.getLogger("viyapy._http")
    with caplog.at_level(logging.DEBUG, logger="viyapy"):
        logger.debug("Authorization: Bearer leaky-token")
    assert "leaky-token" not in caplog.text
