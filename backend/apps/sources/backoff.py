"""Exponential backoff with AWS full-jitter retry helper.

Reference: Metcalfe & Boggs, "Ethernet: distributed packet switching for
local computer networks" (CACM 1976) introduced binary exponential
backoff; Marc Brooker's 2015 AWS Architecture blog post "Exponential
Backoff And Jitter" formalised the **full-jitter** variant this module
implements:

    sleep = random.uniform(0, min(cap, base * 2 ** attempt))

Why full-jitter over plain 2**attempt: when N clients lose the same
upstream dependency simultaneously, plain exponential has them all
retry in lockstep; the thundering herd repeats at every power-of-two
second. Full jitter decorrelates the retries, spreading the load
uniformly across the waiting window.

The module's public surface is deliberately small:

- :func:`full_jitter_delay` — pure arithmetic, easy to unit-test.
- :func:`retry` — decorator around a sync callable that applies the
  backoff + jitter loop with a caller-supplied ``retryable``
  predicate.
- :func:`retry_context` — explicit generator callers iterate to
  coordinate backoff with non-callable control flow (e.g. SSE
  streams that reconnect, or loops that rebuild a request every pass).

Pure Python, no deps, thread-safe. Does NOT integrate with the
Circuit Breaker in ``apps.pipeline.services.circuit_breaker`` — that
is the caller's job (wrap the retry body in ``breaker.call(...)``).
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, Iterator, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def full_jitter_delay(
    attempt: int,
    *,
    base: float = 1.0,
    cap: float = 60.0,
    rng: random.Random | None = None,
) -> float:
    """Return the jittered delay for *attempt* (0-indexed).

    Attempt 0 returns a value in [0, base).
    Attempt N returns a value in [0, min(cap, base * 2**N)].

    Uses ``random.uniform`` from the default RNG unless *rng* is
    supplied — tests pass a seeded rng for determinism.
    """
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    if base <= 0:
        raise ValueError("base must be > 0")
    if cap <= 0:
        raise ValueError("cap must be > 0")
    # 2**attempt blows up fast; clamp to avoid overflow before the min.
    exp = min(2**attempt, int(cap / base) + 1) if base else 1
    upper = min(cap, base * exp)
    source = rng or random
    return source.uniform(0.0, upper)


def retry(
    fn: Callable[[], T],
    *,
    retryable: Callable[[BaseException], bool] = lambda e: True,
    max_attempts: int = 5,
    base: float = 1.0,
    cap: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Run *fn* with AWS full-jitter exponential backoff retries.

    Parameters
    ----------
    fn
        Zero-arg callable. Bind arguments via ``functools.partial`` or
        a closure — kept zero-arg here so the retry loop is a single,
        easily-tested primitive.
    retryable
        Predicate deciding whether an exception is transient. Defaults
        to "retry anything", which is what you want for a fresh HTTP
        client you're debugging; production calls almost always pass
        a narrower predicate (e.g. only retry on 5xx or network errors).
    max_attempts
        Total attempts including the first. ``max_attempts=1`` disables
        retry entirely — useful when the caller already wraps this in
        its own loop.
    base, cap
        Jitter window is ``[0, min(cap, base * 2**attempt)]``.
    sleep, rng
        Injection points for tests — pass a fake sleep + seeded rng
        to make the loop deterministic.
    on_retry
        Optional hook invoked before each retry sleep with
        ``(attempt_index, exception, delay_seconds)``. Useful for
        logging without coupling to this module's logger.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001 — retry predicate decides
            last_exc = exc
            if attempt == max_attempts - 1 or not retryable(exc):
                raise
            delay = full_jitter_delay(attempt, base=base, cap=cap, rng=rng)
            if on_retry is not None:
                try:
                    on_retry(attempt, exc, delay)
                except Exception:  # noqa: BLE001 — hook failure must not mask retry
                    logger.exception(
                        "backoff.retry on_retry hook raised — continuing",
                    )
            sleep(delay)
    # Unreachable: the loop either returns or re-raises.
    assert last_exc is not None
    raise last_exc


def retry_context(
    *,
    max_attempts: int = 5,
    base: float = 1.0,
    cap: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> Iterator[int]:
    """Yield attempt indices, sleeping between yields.

    Use when :func:`retry` is too restrictive (e.g. the body isn't a
    single callable, or the caller needs to reshape inputs between
    attempts)::

        for attempt in retry_context(max_attempts=5):
            try:
                result = do_flaky_thing(attempt=attempt)
                break
            except FlakyError:
                continue
        else:
            raise RetriesExhausted(...)

    The ``else`` branch fires only if the loop is exhausted without
    ``break``.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    for attempt in range(max_attempts):
        if attempt > 0:
            sleep(full_jitter_delay(attempt - 1, base=base, cap=cap, rng=rng))
        yield attempt
