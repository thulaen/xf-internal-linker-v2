"""Convention-named SimpleTestCase coverage for apps/observability/instruments.py.

These helpers wrap reserved metrics so a broken metric backend never crashes a
caller. The tests drive the wrappers against fake in-memory metrics (no real
Prometheus client, no database, no network) and pin the exact label routing,
the clamped bad-sentence ratio, and the error-swallowing behaviour so the
diff-scoped mutation gate cannot survive a changed operator or guard.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.observability import instruments


class SafeHelperRoutingTests(SimpleTestCase):
    def test_safe_inc_with_labels_calls_labels_then_inc(self) -> None:
        metric = MagicMock()
        instruments.safe_inc(metric, 3.0, source="wordpress")
        metric.labels.assert_called_once_with(source="wordpress")
        metric.labels.return_value.inc.assert_called_once_with(3.0)

    def test_safe_inc_without_labels_calls_inc_directly(self) -> None:
        metric = MagicMock()
        instruments.safe_inc(metric, 2.0)
        metric.labels.assert_not_called()
        metric.inc.assert_called_once_with(2.0)

    def test_safe_set_routes_to_set(self) -> None:
        metric = MagicMock()
        instruments.safe_set(metric, 9.0)
        metric.set.assert_called_once_with(9.0)

    def test_broken_metric_does_not_raise(self) -> None:
        class BrokenMetric:
            def inc(self, amount: float = 1.0) -> None:
                raise RuntimeError("backend unavailable")

        # No exception escapes: the helper swallows it.
        instruments.safe_inc(BrokenMetric())


class SentenceSplitRatioTests(SimpleTestCase):
    """observe_sentence_split must clamp the bad-sentence ratio to [0, 1]."""

    def _captured_ratio(self, total: int, bad: int) -> float:
        captured: dict[str, float] = {}

        def fake_set(metric, value, **labels):
            captured["ratio"] = value

        with patch.object(instruments, "get_metric", return_value=MagicMock()), patch.object(
            instruments, "safe_set", side_effect=fake_set
        ), patch.object(instruments, "safe_observe", MagicMock()):
            instruments.observe_sentence_split(total_sentences=total, bad_sentences=bad)
        return captured["ratio"]

    def test_zero_total_yields_zero_ratio(self) -> None:
        # The guard ``total_sentences <= 0`` must short-circuit to 0.0 — exact
        # value kills the boundary mutation.
        self.assertEqual(self._captured_ratio(0, 5), 0.0)

    def test_partial_ratio_is_exact(self) -> None:
        self.assertEqual(self._captured_ratio(4, 1), 0.25)

    def test_ratio_clamped_to_one(self) -> None:
        self.assertEqual(self._captured_ratio(2, 9), 1.0)


class ObserveHelperRoutingTests(SimpleTestCase):
    """Each observe_* helper must route to the exact reserved metric name with
    the exact label keyword arguments. Every metric lookup is faked, so no real
    Prometheus client, database, or network is touched."""

    def _capture(self, fn, *args, **kwargs) -> list:
        calls: list = []

        def fake_inc(metric, amount=1.0, **labels):
            calls.append(("inc", metric, amount, labels))

        def fake_observe(metric, value, **labels):
            calls.append(("observe", metric, value, labels))

        def fake_set(metric, value, **labels):
            calls.append(("set", metric, value, labels))

        with patch.object(instruments, "get_metric", side_effect=lambda name: name), patch.object(
            instruments, "safe_inc", side_effect=fake_inc
        ), patch.object(instruments, "safe_observe", side_effect=fake_observe), patch.object(
            instruments, "safe_set", side_effect=fake_set
        ):
            fn(*args, **kwargs)
        return calls

    def test_observe_import_posts_routes_count_and_source(self) -> None:
        calls = self._capture(instruments.observe_import_posts, "wordpress", count=5)
        # Exact metric name, exact amount, exact label dict — kills a swapped
        # metric literal, a changed default, or a dropped label.
        self.assertEqual(
            calls,
            [("inc", "xf_import_posts_total", 5, {"source": "wordpress"})],
        )

    def test_observe_import_posts_default_count_is_one(self) -> None:
        calls = self._capture(instruments.observe_import_posts, "wordpress")
        self.assertEqual(calls[0][2], 1)

    def test_observe_import_failure_routes_source_and_reason(self) -> None:
        calls = self._capture(instruments.observe_import_failure, "wp", "timeout")
        self.assertEqual(
            calls,
            [("inc", "xf_import_failures_total", 1.0, {"source": "wp", "reason": "timeout"})],
        )

    def test_observe_webhook_event_routes_source_and_event_type(self) -> None:
        calls = self._capture(instruments.observe_webhook_event, "wp", "post.published")
        self.assertEqual(
            calls,
            [
                (
                    "inc",
                    "xf_import_webhook_events_total",
                    1.0,
                    {"source": "wp", "event_type": "post.published"},
                )
            ],
        )

    def test_observe_cleaning_failure_routes_reason(self) -> None:
        calls = self._capture(instruments.observe_cleaning_failure, "empty")
        self.assertEqual(
            calls,
            [("inc", "xf_cleaning_failures_total", 1.0, {"reason": "empty"})],
        )

    def test_observe_cleaning_result_emits_before_and_after_lengths(self) -> None:
        calls = self._capture(
            instruments.observe_cleaning_result, raw_text="abcd", cleaned_text="ab"
        )
        # One counter inc, then two observes with the exact char counts (4 then
        # 2) under the exact phase labels.
        self.assertEqual(calls[0], ("inc", "xf_cleaning_documents_total", 1.0, {}))
        self.assertEqual(
            calls[1],
            ("observe", "xf_cleaning_text_length_chars", 4, {"phase": "before"}),
        )
        self.assertEqual(
            calls[2],
            ("observe", "xf_cleaning_text_length_chars", 2, {"phase": "after"}),
        )

    def test_observe_cleaning_result_treats_none_text_as_zero_length(self) -> None:
        calls = self._capture(
            instruments.observe_cleaning_result, raw_text=None, cleaned_text=None
        )
        self.assertEqual(calls[1][2], 0)
        self.assertEqual(calls[2][2], 0)

    def test_observe_sentence_split_clamps_negative_total_to_zero(self) -> None:
        # ``max(total_sentences, 0)`` must floor at exactly 0 for the observe.
        calls = self._capture(
            instruments.observe_sentence_split, total_sentences=-4, bad_sentences=0
        )
        observe = next(c for c in calls if c[0] == "observe")
        self.assertEqual(observe[1], "xf_sentence_split_sentences_per_doc")
        self.assertEqual(observe[2], 0)


class SafeObserveAndCallMetricTests(SimpleTestCase):
    def test_safe_observe_with_labels_routes_through_labels(self) -> None:
        metric = MagicMock()
        instruments.safe_observe(metric, 1.5, phase="before")
        metric.labels.assert_called_once_with(phase="before")
        metric.labels.return_value.observe.assert_called_once_with(1.5)

    def test_safe_set_without_labels_calls_set_directly(self) -> None:
        metric = MagicMock()
        instruments.safe_set(metric, 4.0)
        metric.labels.assert_not_called()
        metric.set.assert_called_once_with(4.0)

    def test_broken_metric_observe_is_swallowed(self) -> None:
        class Broken:
            def observe(self, value):
                raise RuntimeError("down")

        # No exception escapes — the helper logs and returns.
        instruments.safe_observe(Broken(), 1.0)


class ObserveDurationTests(SimpleTestCase):
    def test_duration_observes_elapsed_under_the_named_metric(self) -> None:
        captured: dict = {}

        def fake_observe(metric, value, **labels):
            captured["metric"] = metric
            captured["value"] = value
            captured["labels"] = labels

        # Pin perf_counter so the elapsed time is exactly 0.5 seconds.
        with patch.object(instruments, "get_metric", side_effect=lambda name: name), patch.object(
            instruments, "safe_observe", side_effect=fake_observe
        ), patch.object(instruments.time, "perf_counter", side_effect=[10.0, 10.5]):
            with instruments.observe_duration("xf_index_build_seconds"):
                pass
        self.assertEqual(captured["metric"], "xf_index_build_seconds")
        self.assertEqual(captured["value"], 0.5)
        self.assertEqual(captured["labels"], {})
