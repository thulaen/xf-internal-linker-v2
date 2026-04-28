"""Celery task decorators that compose with @shared_task.

Currently provides ``with_weight_lock`` — enforces the golden rule from
docs/PERFORMANCE.md §4 that no two Heavy (or Medium) tasks run at once,
by acquiring a Redis-backed lock around the wrapped task. If the lock is
already held, the task re-queues itself via ``self.retry(countdown=60)``
for FIFO-style defer behaviour (max ~1 hour patience).

Wraps ``acquire_task_lock`` / ``release_task_lock`` from
``apps.pipeline.services.task_lock``. The lower-level helpers existed
since the task_lock service was added but were not previously called from
any production code path.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

# Max retries for signal-lock contention. Combined with the 30s countdown
# below, this yields ~1 hour total retry window before a deferred signal
# task gives up. Extracted from the inline literal so the magic-number
# linter passes on changed files.
_SIGNAL_LOCK_MAX_RETRIES = 120


def with_weight_lock(
    weight_class: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Acquire the lock for ``weight_class`` before running the wrapped task.

    The wrapped task MUST be defined with ``bind=True`` on its
    ``@shared_task`` so that ``self.retry`` is available for the defer
    path.

    On lock contention, ``self.retry(countdown=60, max_retries=60)`` defers
    the task by ~1 minute. With max_retries=60 a deferred task will keep
    re-queueing for up to ~1 hour before Celery gives up.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            from apps.pipeline.services.task_lock import (
                acquire_task_lock,
                release_task_lock,
            )

            if not acquire_task_lock(weight_class, func.__name__):
                # FIFO-style defer: re-enqueue and let the lock holder finish first.
                raise self.retry(countdown=60, max_retries=60)
            try:
                return func(self, *args, **kwargs)
            finally:
                release_task_lock(weight_class, func.__name__)

        return wrapper

    return decorator


# ─────────────────────────────────────────────────────────────────────────
# Phase SEQ — Sequential Execution for Ranking Signals
# ─────────────────────────────────────────────────────────────────────────


def with_signal_lock() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Run a ranking-signal compute task one-at-a-time across the fleet.

    Phase SEQ of the approved master plan. Rationale: the 23 existing
    ranking signals (plus the pending forward-declared signals in
    ``recommended_weights_forward_settings.py``) all compete for the
    same GPU, CPU, and Postgres connection pool. Running them in
    parallel is pathologically slow because each one saturates the
    hot path — a pipeline doing 3 signals at once is slower than doing
    them back-to-back on constrained hardware ("The Tail at Scale").

    This decorator is semantically a specialisation of
    ``with_weight_lock("signal")``: it lives on its own Redis key
    namespace so medium / heavy tasks can still run alongside signal
    computes. On contention, the FIFO-defer timing is shorter (30s
    retry × ``_SIGNAL_LOCK_MAX_RETRIES`` ≈ 1 hour patience) because
    signals are typically faster than full pipeline runs.

    The wrapped task MUST be defined with ``bind=True``.

    Example
    -------
        @shared_task(bind=True, name="suggestions.compute_signal_authority")
        @with_signal_lock()
        def compute_signal_authority(self, run_id: str) -> dict:
            ...

    Future signals (FR-099 through FR-224) adopt this decorator by
    convention. A CI test asserts new ``compute_signal_*`` tasks use it.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            from apps.pipeline.services.task_lock import (
                acquire_task_lock,
                release_task_lock,
            )

            if not acquire_task_lock("signal", func.__name__):
                # Shorter retry cadence than with_weight_lock so the signal
                # queue drains quickly during a busy compute window.
                raise self.retry(countdown=30, max_retries=_SIGNAL_LOCK_MAX_RETRIES)
            try:
                return func(self, *args, **kwargs)
            finally:
                release_task_lock("signal", func.__name__)

        return wrapper

    return decorator
