"""Convention-named SimpleTestCase coverage for apps/observability/models.py.

The ``MetricCardinalityBudget`` model declares the per-metric series budget. The
field defaults and the unique/ordering meta options are pinned with exact
assertions so the diff-scoped mutation gate cannot survive a changed literal.
These tests read field metadata only — no database row is created, so no DB
access happens.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.observability.models import MetricCardinalityBudget


def _field(name: str):
    return MetricCardinalityBudget._meta.get_field(name)


class MetricCardinalityBudgetFieldTests(SimpleTestCase):
    def test_metric_name_is_unique_with_160_max_length(self) -> None:
        field = _field("metric_name")
        self.assertTrue(field.unique)
        # assertEqual on the exact max_length kills the +1 mutation.
        self.assertEqual(field.max_length, 160)

    def test_max_series_defaults_to_1000(self) -> None:
        # Exact default kills the literal mutation of the seeded budget.
        self.assertEqual(_field("max_series").default, 1000)

    def test_current_series_estimated_defaults_to_zero(self) -> None:
        self.assertEqual(_field("current_series_estimated").default, 0)

    def test_exceeded_at_is_nullable(self) -> None:
        field = _field("exceeded_at")
        self.assertTrue(field.null)
        self.assertTrue(field.blank)

    def test_default_ordering_is_metric_name(self) -> None:
        self.assertEqual(MetricCardinalityBudget._meta.ordering, ["metric_name"])
