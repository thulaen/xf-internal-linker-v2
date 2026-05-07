"""SimpleTestCase coverage for the pure helpers in apps.audit.data_quality.

These tests run without a database (no Docker dependency, no migrations).
They exercise the pure helpers extracted from `scorecard()` plus the
two pre-existing pure helpers (`_clamp_pct`, `_densify`) that previously
had no direct test coverage.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.audit.data_quality import (
    _clamp_pct,
    _content_item_scorecard,
    _densify,
    _hours_since,
    _search_metric_scorecard,
)


_FROZEN_NOW = datetime(2026, 5, 7, 12, 0, 0, tzinfo=dt_timezone.utc)


class ClampPctTests(SimpleTestCase):
    """Floor at 0, cap at 100, otherwise round to one decimal."""

    def test_negative_clamps_to_zero(self):
        self.assertEqual(_clamp_pct(-5.0), 0.0)

    def test_zero_returns_zero(self):
        self.assertEqual(_clamp_pct(0.0), 0.0)

    def test_decimal_value_rounded_to_one_place(self):
        self.assertEqual(_clamp_pct(42.567), 42.6)

    def test_at_or_above_max_clamps_to_full(self):
        self.assertEqual(_clamp_pct(100.0), 100.0)
        self.assertEqual(_clamp_pct(150.0), 100.0)

    def test_just_under_max_passes_through_rounded(self):
        self.assertEqual(_clamp_pct(99.94), 99.9)


class DensifyTests(SimpleTestCase):
    """Produce N daily VolumePoints, fill gaps with zero, preserve order."""

    def test_empty_map_yields_all_zero(self):
        rows = _densify(date(2026, 5, 1), 3, {})
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["count"] for r in rows], [0, 0, 0])
        self.assertEqual(
            [r["day"] for r in rows],
            ["2026-05-01", "2026-05-02", "2026-05-03"],
        )

    def test_partial_fill(self):
        rows = _densify(date(2026, 5, 1), 3, {"2026-05-02": 7})
        self.assertEqual([r["count"] for r in rows], [0, 7, 0])

    def test_zero_days_yields_empty(self):
        self.assertEqual(_densify(date(2026, 5, 1), 0, {}), [])

    def test_day_ordering_preserved(self):
        rows = _densify(date(2026, 5, 1), 5, {})
        days = [r["day"] for r in rows]
        self.assertEqual(days, sorted(days))


class HoursSinceTests(SimpleTestCase):
    """None passthrough; otherwise hours between dt and now (float)."""

    def test_none_returns_none(self):
        self.assertIsNone(_hours_since(None))

    @patch("apps.audit.data_quality.timezone.now", return_value=_FROZEN_NOW)
    def test_one_hour_ago(self, _mock_now):
        self.assertEqual(_hours_since(_FROZEN_NOW - timedelta(hours=1)), 1.0)

    @patch("apps.audit.data_quality.timezone.now", return_value=_FROZEN_NOW)
    def test_24_hours_ago(self, _mock_now):
        self.assertEqual(_hours_since(_FROZEN_NOW - timedelta(hours=24)), 24.0)

    @patch("apps.audit.data_quality.timezone.now", return_value=_FROZEN_NOW)
    def test_zero_seconds_ago_returns_zero(self, _mock_now):
        self.assertEqual(_hours_since(_FROZEN_NOW), 0.0)


class SearchMetricScorecardTests(SimpleTestCase):
    """Pure dict-in / dict-out conversion of one summary row."""

    def test_empty_summary_row_yields_zeros(self):
        result = _search_metric_scorecard("gsc", {})
        self.assertEqual(result["source"], "gsc")
        self.assertEqual(result["sample_size"], 0)
        self.assertEqual(result["completeness_pct"], 0.0)
        self.assertIsNone(result["freshness_hours"])
        self.assertEqual(result["accuracy_pct"], 100.0)

    @patch("apps.audit.data_quality._hours_since", return_value=36.0)
    def test_full_summary_row(self, _mock_hours):
        row = {"source": "gsc", "latest": date(2026, 5, 6), "sample": 30}
        result = _search_metric_scorecard("gsc", row)
        self.assertEqual(result["sample_size"], 30)
        # 30 / 30 (target) * 100 → 100.0%. A fully-loaded connector reports
        # 100 % completeness (matches the content-item path).
        self.assertEqual(result["completeness_pct"], 100.0)
        self.assertEqual(result["freshness_hours"], 36.0)

    @patch("apps.audit.data_quality._hours_since", return_value=12.0)
    def test_half_full_yields_50_percent(self, _mock_hours):
        # 15 / 30 (target) * 100 → 50.0 %.
        row = {"source": "ga4", "latest": date(2026, 5, 6), "sample": 15}
        result = _search_metric_scorecard("ga4", row)
        self.assertEqual(result["completeness_pct"], 50.0)

    def test_no_latest_returns_none_freshness(self):
        result = _search_metric_scorecard("ga4", {"sample": 5})
        self.assertEqual(result["sample_size"], 5)
        self.assertIsNone(result["freshness_hours"])

    def test_no_sample_returns_zero_completeness(self):
        result = _search_metric_scorecard("matomo", {"latest": None, "sample": 0})
        self.assertEqual(result["completeness_pct"], 0.0)
        self.assertEqual(result["sample_size"], 0)

    @patch("apps.audit.data_quality._hours_since", return_value=200.0)
    def test_completeness_clamps_at_100(self, _mock_hours):
        # 50 samples vs target=30 → 166.7 % raw; `_clamp_pct` caps at 100.
        result = _search_metric_scorecard("gsc", {"latest": date(2026, 5, 1), "sample": 50})
        self.assertEqual(result["completeness_pct"], 100.0)

    @patch("apps.audit.data_quality._hours_since", return_value=0.0)
    def test_freshness_zero_renders_as_zero_not_none(self, _mock_hours):
        # Regression: prior code used `if freshness else None`, which
        # rendered an exact 0.0 freshness as None. Now uses `is not None`.
        row = {"source": "gsc", "latest": date(2026, 5, 7), "sample": 1}
        result = _search_metric_scorecard("gsc", row)
        self.assertEqual(result["freshness_hours"], 0.0)
        self.assertIsNotNone(result["freshness_hours"])


class ContentItemScorecardShapeTests(SimpleTestCase):
    """Verify shape/maths of the content scorecard with mocked ORM."""

    def _install_orm_mocks(self, *, total: int, embedded: int, latest_ci):
        ci_patcher = patch("apps.content.models.ContentItem")
        embed_patcher = patch(
            "apps.pipeline.services.embeddings.get_current_embedding_filter",
            return_value={},
        )
        mock_ci = ci_patcher.start()
        embed_patcher.start()
        self.addCleanup(ci_patcher.stop)
        self.addCleanup(embed_patcher.stop)
        mock_ci.objects.count.return_value = total
        filter_mock = MagicMock()
        filter_mock.count.return_value = embedded
        mock_ci.objects.filter.return_value = filter_mock
        mock_ci.objects.aggregate.return_value = {"m": latest_ci}

    def test_total_zero_yields_zero_completeness_and_no_freshness(self):
        self._install_orm_mocks(total=0, embedded=0, latest_ci=None)
        result = _content_item_scorecard()
        self.assertEqual(result["source"], "content")
        self.assertEqual(result["sample_size"], 0)
        self.assertEqual(result["completeness_pct"], 0.0)
        self.assertIsNone(result["freshness_hours"])
        self.assertEqual(result["accuracy_pct"], 100.0)

    @patch("apps.audit.data_quality._hours_since", return_value=2.0)
    def test_full_embed_yields_100_completeness(self, _mock_hours):
        self._install_orm_mocks(total=10, embedded=10, latest_ci=_FROZEN_NOW)
        result = _content_item_scorecard()
        self.assertEqual(result["sample_size"], 10)
        self.assertEqual(result["completeness_pct"], 100.0)
        self.assertEqual(result["freshness_hours"], 2.0)

    @patch("apps.audit.data_quality._hours_since", return_value=None)
    def test_partial_embed_returns_proportional_completeness(self, _mock_hours):
        self._install_orm_mocks(total=10, embedded=5, latest_ci=None)
        result = _content_item_scorecard()
        self.assertEqual(result["completeness_pct"], 50.0)
        self.assertIsNone(result["freshness_hours"])
