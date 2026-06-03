"""Convention-named SimpleTestCase coverage for apps/observability/api.py.

The module public surface is the Prometheus registry plus a pure-Python
fallback metric used before the real ``prometheus_client`` is installed. Both
paths run fully in memory, so these tests touch no database or network. Exact
numeric assertions pin the increment/set/observe arithmetic so the diff-scoped
mutation gate cannot survive a changed operator or literal.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability import api


class RegistryContractTests(SimpleTestCase):
    def test_get_registry_returns_the_singleton_registry(self) -> None:
        self.assertIs(api.get_registry(), api._REGISTRY)

    def test_register_metric_is_idempotent_by_name(self) -> None:
        first = api.register_metric(api.Counter, "xf_api_unit_total", "unit test")
        second = api.register_metric(api.Counter, "xf_api_unit_total", "unit test")
        self.assertIs(first, second)
        self.assertIs(api.get_metric("xf_api_unit_total"), first)

    def test_reserved_metric_names_includes_import_posts(self) -> None:
        names = api.reserved_metric_names()
        self.assertIn("xf_import_posts_total", names)
        self.assertEqual(len(names), len(set(names)))


class FallbackMetricArithmeticTests(SimpleTestCase):
    """The in-memory fallback metric must add, set, and observe exactly."""

    def _counter(self):
        registry = api.CollectorRegistry()
        return api.Counter("xf_fallback_total", "fallback", registry=registry)

    def test_inc_default_amount_adds_one(self) -> None:
        metric = self._counter()
        metric.inc()
        # Exact value kills the mutation of the default ``amount=1.0``.
        self.assertEqual(metric.value, 1.0)

    def test_inc_accumulates_exact_amount(self) -> None:
        metric = self._counter()
        metric.inc(2.0)
        metric.inc(3.0)
        self.assertEqual(metric.value, 5.0)

    def test_set_replaces_value(self) -> None:
        metric = self._counter()
        metric.set(7.0)
        self.assertEqual(metric.value, 7.0)

    def test_labels_track_child_values_independently(self) -> None:
        registry = api.CollectorRegistry()
        metric = api.Counter("xf_fallback_lbl_total", "fallback", labelnames=("source",), registry=registry)
        metric.labels(source="wordpress").inc(4.0)
        self.assertEqual(metric.samples[("wordpress",)], 4.0)
