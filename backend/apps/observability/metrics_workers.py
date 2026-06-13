"""Background-worker / Celery task instrumentation helpers.

Wires xf_celery_task_duration_seconds and xf_celery_deadletter_depth
into the Celery task execution path.

Call sites
----------
- apps.pipeline.tasks  (run_pipeline, recalculate_click_distance_task, etc.)
- apps.scheduled_updates.tasks  (any scheduled beat task)

Usage pattern
-------------
Add at the top of a task::

    from apps.observability.metrics_workers import celery_task_timer

    @shared_task(...)
    def my_task(...):
        with celery_task_timer("my_task"):
            ...

For failure cases the context manager records status="failure"; success
records status="success". The caller does not need to handle the distinction.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from collections.abc import Iterator

from apps.observability.instruments import safe_inc, safe_observe, safe_set
from apps.observability.api import get_metric


@contextmanager
def celery_task_timer(task_name: str) -> Iterator[None]:
    """Time a Celery task and emit xf_celery_task_duration_seconds.

    Status label is "success" on clean exit, "failure" if an exception
    propagates through the context manager.

    Usage::

        with celery_task_timer("pipeline.run_pipeline"):
            result = run_pipeline_service(...)
    """
    started = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "failure"
        raise
    finally:
        elapsed = time.perf_counter() - started
        safe_observe(
            get_metric("xf_celery_task_duration_seconds"),
            elapsed,
            task_name=task_name,
            status=status,
        )


def observe_deadletter_depth(queue_name: str, depth: int) -> None:
    """Set xf_celery_deadletter_depth for a named dead-letter queue.

    Call from a periodic beat task that counts items in the DLQ.
    """
    safe_set(get_metric("xf_celery_deadletter_depth"), float(depth), queue=queue_name)
