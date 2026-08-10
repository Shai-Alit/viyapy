"""Unit tests for the generic async-operation poller (``viyapy._polling``).

The poller is deliberately generation-agnostic: it knows nothing about jobs,
HTTP, or JSON. These tests drive it with plain callables and an injected clock so
its control flow (immediate terminal, repeated polling, deadline handling, and
argument validation) is exercised without any real waiting.
"""

from __future__ import annotations

import pytest

from viyapy._polling import DEFAULT_POLL_INTERVAL, DEFAULT_POLL_TIMEOUT, poll_until
from viyapy.exceptions import ViyaConfigError, ViyaPollTimeoutError


class FakeClock:
    """A controllable monotonic clock whose ``sleep`` advances it by the delay."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_returns_immediately_when_first_fetch_is_terminal() -> None:
    clock = FakeClock()
    calls: list[int] = []

    def fetch() -> str:
        calls.append(1)
        return "done"

    result = poll_until(
        fetch,
        lambda v: v == "done",
        interval=2.0,
        timeout=10.0,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )

    assert result == "done"
    assert len(calls) == 1  # no re-poll once the first fetch is terminal
    assert clock.sleeps == []  # never slept


def test_polls_until_terminal_state() -> None:
    clock = FakeClock()
    states = iter(["pending", "running", "completed"])

    result = poll_until(
        lambda: next(states),
        lambda v: v == "completed",
        interval=2.0,
        timeout=30.0,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )

    assert result == "completed"
    # Two non-terminal fetches -> two sleeps before the terminal third fetch.
    assert clock.sleeps == [2.0, 2.0]


def test_timeout_raises_with_elapsed_and_last_state() -> None:
    clock = FakeClock()

    with pytest.raises(ViyaPollTimeoutError) as excinfo:
        poll_until(
            lambda: "pending",
            lambda v: False,  # never terminal
            interval=2.0,
            timeout=5.0,
            describe=lambda v: v,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )

    err = excinfo.value
    assert err.last_state == "pending"
    assert err.elapsed is not None and err.elapsed >= 5.0
    assert "pending" in str(err)


def test_performs_at_least_one_poll_even_with_tiny_timeout() -> None:
    # A clock that jumps a full second on its first read, so by the time the
    # deadline is checked the tiny budget has already elapsed.
    ticks = iter([0.0, 1.0, 2.0, 3.0])
    calls: list[int] = []
    sleeps: list[float] = []

    def fetch() -> str:
        calls.append(1)
        return "pending"

    with pytest.raises(ViyaPollTimeoutError):
        poll_until(
            fetch,
            lambda v: False,
            interval=2.0,
            timeout=0.0001,  # shorter than a single interval
            sleep=sleeps.append,
            monotonic=lambda: next(ticks),
        )

    assert calls  # fetched at least once before reporting a timeout
    assert sleeps == []  # deadline already passed, so never slept


def test_never_sleeps_past_the_deadline() -> None:
    clock = FakeClock()

    with pytest.raises(ViyaPollTimeoutError):
        poll_until(
            lambda: "pending",
            lambda v: False,
            interval=100.0,  # far larger than the remaining budget
            timeout=5.0,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )

    # The single sleep is clamped to the remaining budget, not the full interval.
    assert clock.sleeps == [5.0]


@pytest.mark.parametrize("bad", [0, -1, -0.5, float("inf"), float("nan"), True, "2", None])
def test_rejects_non_positive_timeout(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        poll_until(lambda: "x", lambda v: True, timeout=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan"), True, "2", None])
def test_rejects_non_positive_interval(bad: object) -> None:
    with pytest.raises(ViyaConfigError):
        poll_until(lambda: "x", lambda v: True, interval=bad)  # type: ignore[arg-type]


def test_terminal_wins_before_interval_validation_is_moot() -> None:
    # A terminal-on-first-fetch poll still validates its arguments up front.
    with pytest.raises(ViyaConfigError):
        poll_until(lambda: "done", lambda v: True, interval=-1)


def test_defaults_are_sane() -> None:
    assert DEFAULT_POLL_TIMEOUT > 0
    assert 0 < DEFAULT_POLL_INTERVAL <= DEFAULT_POLL_TIMEOUT
