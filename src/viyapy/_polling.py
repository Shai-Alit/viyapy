"""A small, generation-agnostic poller for asynchronous SAS Viya operations.

Several Viya operations are asynchronous: you submit them, get back a resource
that starts in a non-terminal state, and poll it until it reaches a terminal
state. MAS module *compile jobs* are the first such case (phase 5.2d); decision
publishing (5.6) and batch scoring (5.7) follow the same shape, so the polling
logic lives here as reusable infrastructure rather than inside one client.

:func:`poll_until` is deliberately generic — it knows nothing about jobs, HTTP,
or JSON. The caller supplies a ``fetch`` callable that returns the current state
and an ``is_terminal`` predicate; the clock and sleep function are injectable so
the behavior is unit-testable without real waits.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import TypeVar

from .exceptions import ViyaConfigError, ViyaPollTimeoutError

T = TypeVar("T")

# Defaults tuned for MAS compile jobs (a trivial module compiles in seconds), but
# generous enough to cover a slow first-time compile. Callers can override both.
DEFAULT_POLL_TIMEOUT = 300.0
DEFAULT_POLL_INTERVAL = 2.0


def _require_positive(value: float, name: str) -> float:
    """Validate a positive, finite number of seconds, or raise ``ViyaConfigError``.

    ``inf`` and ``nan`` are rejected too: a non-finite budget or interval would
    poison the deadline arithmetic (``deadline = start + timeout``) and never
    behave as a sane wait.
    """
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ViyaConfigError(
            f"{name} must be a positive, finite number of seconds (got {value!r})"
        )
    return float(value)


def poll_until(
    fetch: Callable[[], T],
    is_terminal: Callable[[T], bool],
    *,
    timeout: float = DEFAULT_POLL_TIMEOUT,
    interval: float = DEFAULT_POLL_INTERVAL,
    describe: Callable[[T], str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> T:
    """Poll ``fetch`` until ``is_terminal`` is satisfied, or the budget expires.

    The resource is fetched once immediately, then re-fetched every ``interval``
    seconds until ``is_terminal`` returns ``True`` (the terminal value is
    returned) or ``timeout`` seconds elapse. A fetch is always attempted before
    the deadline is enforced, so the operation is never reported as timed out
    without a final check — and a ``timeout`` shorter than a single ``interval``
    still performs at least one poll.

    Args:
        fetch: Zero-argument callable returning the current state of the resource.
            Called synchronously; any exception it raises propagates unchanged.
        is_terminal: Predicate returning ``True`` when a fetched value is in a
            terminal state and polling should stop.
        timeout: Overall wait budget, in seconds (must be positive).
        interval: Delay between polls, in seconds (must be positive). The final
            sleep is shortened so it never overshoots the deadline by more than a
            single ``fetch``.
        describe: Optional callable rendering a fetched value as a short string
            for the timeout message and :attr:`ViyaPollTimeoutError.last_state`.
        sleep: Injectable sleep function (defaults to :func:`time.sleep`); tests
            pass a no-op.
        monotonic: Injectable monotonic clock (defaults to
            :func:`time.monotonic`); tests pass a controllable clock.

    Returns:
        The first fetched value for which ``is_terminal`` returned ``True``.

    Raises:
        ViyaConfigError: ``timeout`` or ``interval`` is not a positive number.
        ViyaPollTimeoutError: The budget elapsed before a terminal state.
    """
    timeout = _require_positive(timeout, "timeout")
    interval = _require_positive(interval, "interval")

    start = monotonic()
    deadline = start + timeout
    last: T | None = None
    while True:
        last = fetch()
        if is_terminal(last):
            return last
        now = monotonic()
        remaining = deadline - now
        if remaining <= 0:
            break
        # Never sleep past the deadline: a long interval shouldn't stretch the
        # effective wait well beyond the caller's budget.
        sleep(min(interval, remaining))

    elapsed = monotonic() - start
    last_state = describe(last) if (describe is not None and last is not None) else None
    detail = f" (last state: {last_state})" if last_state else ""
    raise ViyaPollTimeoutError(
        f"Polling did not reach a terminal state within {timeout:g}s{detail}",
        elapsed=elapsed,
        last_state=last_state,
    )
