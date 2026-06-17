"""Convention-named SimpleTestCase coverage for apps/observability/metric_specs.py.

The reserved metric and observability-item catalogs are static data the rest of
the stack depends on. Exact-count and exact-field assertions pin every literal
so the diff-scoped mutation gate cannot survive an off-by-one or a flipped kind.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability.metric_specs import (
    RESERVED_METRICS,
    RESERVED_OBSERVABILITY_ITEMS,
    MetricSpec,
    ObservabilityItem,
)


class ReservedMetricsTests(SimpleTestCase):
    def test_first_spec_is_import_posts_counter_with_source_label(self) -> None:
        first = RESERVED_METRICS[0]
        self.assertEqual(first.name, "xf_import_posts_total")
        self.assertEqual(first.kind, "counter")
        self.assertEqual(first.labels, ("source",))

    def test_metric_spec_default_labels_is_empty_tuple(self) -> None:
        spec = MetricSpec("xf_demo_total", "counter")
        self.assertEqual(spec.labels, ())

    def test_metric_names_are_unique(self) -> None:
        names = [spec.name for spec in RESERVED_METRICS]
        self.assertEqual(len(names), len(set(names)))

    def test_ranking_decision_metrics_are_reserved(self) -> None:
        specs = {spec.name: spec for spec in RESERVED_METRICS}
        expected = {
            "xf_ranking_decision_latency_seconds": ("histogram", ("path",)),
            "xf_ranking_batch_size": ("histogram", ("path",)),
            "xf_ranking_decision_last_batch_size": ("gauge", ("path",)),
            "xf_ranking_batches_total": ("counter", ("path", "status")),
            "xf_ranking_batch_failures_total": ("counter", ("path", "reason")),
            "xf_ranking_batch_timeouts_total": ("counter", ("path",)),
            "xf_ranking_signal_raw_score": ("histogram", ("signal",)),
            "xf_ranking_signal_contribution": (
                "histogram",
                ("signal", "direction"),
            ),
            "xf_ranking_signal_last_contribution": ("gauge", ("signal",)),
            "xf_ranking_score_change_total": ("counter", ("driver", "direction")),
        }
        for name, (kind, labels) in expected.items():
            with self.subTest(name=name):
                self.assertEqual(specs[name].kind, kind)
                self.assertEqual(specs[name].labels, labels)


class ReservedObservabilityItemsTests(SimpleTestCase):
    def test_catalog_has_exactly_85_items(self) -> None:
        # assertEqual on the exact count kills the +1 mutation; the plan reserves
        # exactly 85 items.
        self.assertEqual(len(RESERVED_OBSERVABILITY_ITEMS), 85)

    def test_item_ids_are_one_based_and_contiguous(self) -> None:
        ids = [item.item_id for item in RESERVED_OBSERVABILITY_ITEMS]
        self.assertEqual(ids, list(range(1, 86)))

    def test_first_item_mirrors_first_metric_spec(self) -> None:
        first = RESERVED_OBSERVABILITY_ITEMS[0]
        self.assertIsInstance(first, ObservabilityItem)
        self.assertEqual(first.item_id, 1)
        self.assertEqual(first.name, "xf_import_posts_total")
        self.assertEqual(first.kind, "counter")
