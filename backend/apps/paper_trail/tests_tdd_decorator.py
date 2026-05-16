"""Tests for @tdd_benchmark decorator (Red phase first)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.paper_trail.services import lesson_index as svc
from apps.paper_trail.services.tdd_decorator import tdd_benchmark


class TddBenchmarkTests(SimpleTestCase):
    def setUp(self) -> None:
        svc.reset_all_for_tests()

    def test_decorator_preserves_function_behaviour(self) -> None:
        @tdd_benchmark("test_fn_a", window=20)
        def square(x: int) -> int:
            return x * x

        self.assertEqual(square(7), 49)

    def test_decorator_records_timing_after_window(self) -> None:
        @tdd_benchmark("test_fn_b", window=20)
        def fast() -> None:
            return None

        # Run enough times to hit the flush threshold.
        for _ in range(20):
            fast()
        rec = svc.perf_get("test_fn_b")
        self.assertIsNotNone(rec)
        self.assertGreater(rec["samples"], 0)
        self.assertGreaterEqual(rec["p50_ns"], 0)
