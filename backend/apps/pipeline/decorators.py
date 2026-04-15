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
