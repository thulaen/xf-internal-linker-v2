"""@tdd_benchmark — TDD-driven perf-baseline capture decorator.

Wraps a function so every call (during pytest-benchmark or production
warm-up) records timing into the PerfBaselineCache. The `[PERFORMANCE
PROOF]` marker in the handoff entry reads from this cache.

Usage:
    from apps.paper_trail.services.tdd_decorator import tdd_benchmark

    @tdd_benchmark("apps.pipeline.services.ranker.score_candidate")
    def score_candidate(query, candidate):
        ...
"""

from __future__ import annotations

import functools
import statistics
import threading
import time
from collections import deque
from typing import Callable, TypeVar

from apps.paper_trail.services import lesson_index as svc


_F = TypeVar("_F", bound=Callable)
_DEFAULT_SAMPLE_WINDOW = 100
_samples_by_fn: dict[str, deque[int]] = {}
_lock = threading.Lock()


def tdd_benchmark(fn_id: str, *, window: int = _DEFAULT_SAMPLE_WINDOW) -> Callable[[_F], _F]:
    """Decorator factory. `fn_id` is the canonical function signature
    used as the PerfBaselineCache key.
    """

    def wrap(fn: _F) -> _F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start_ns = time.perf_counter_ns()
            try:
                return fn(*args, **kwargs)
            finally:
                elapsed = time.perf_counter_ns() - start_ns
                _record_sample(fn_id, elapsed, window)
        return wrapper  # type: ignore[return-value]

    return wrap


def _record_sample(fn_id: str, ns: int, window: int) -> None:
    with _lock:
        bucket = _samples_by_fn.setdefault(fn_id, deque(maxlen=window))
        bucket.append(ns)
        if len(bucket) >= max(10, window // 2):
            _flush_to_cache(fn_id, bucket)


def _flush_to_cache(fn_id: str, samples: deque[int]) -> None:
    if not samples:
        return
    data = sorted(samples)
    n = len(data)
    p50 = data[n // 2]
    p95 = data[min(n - 1, int(n * 0.95))]
    p99 = data[min(n - 1, int(n * 0.99))]
    mean = int(statistics.mean(data))
    svc.perf_put(fn_id, p50_ns=p50, p95_ns=p95, p99_ns=p99,
                 mean_ns=mean, samples=n,
                 measured_at_unix=int(time.time()))
