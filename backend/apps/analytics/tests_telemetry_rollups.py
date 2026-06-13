"""Tests for the DataFusion-backed telemetry breakdown rollups.

Each test redirects the Parquet snapshot to its own temporary directory,
seeds real database rows, and asserts the SQL rollup matches what the
old per-page-load ORM aggregation produced.
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.content.models import ContentItem

from .models import SuggestionTelemetryDaily


# Plain TestCase is sufficient: breakdown_rows refreshes the snapshot with the
# Django ORM, which sees the test transaction's own rows. (The background
# snapshot jobs that DO use ADBC's second connection are covered separately.)
class TelemetryBreakdownRollupTests(TestCase):
    def setUp(self) -> None:
        self.host = ContentItem.objects.create(
            content_id=9001, content_type="thread", title="Host"
        )
        self.destination = ContentItem.objects.create(
            content_id=9002, content_type="thread", title="Destination"
        )
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        patcher = patch(
            "apps.analytics.telemetry_rollups._snapshot_path",
            return_value=Path(self._tmpdir.name) / "telemetry.parquet",
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _row(self, *, days_ago=0, source="ga4", device="desktop", country="", clicks=1, impressions=10, engaged=2):
        return SuggestionTelemetryDaily.objects.create(
            date=timezone.now().date() - timedelta(days=days_ago),
            telemetry_source=source,
            destination=self.destination,
            host=self.host,
            device_category=device,
            country=country,
            impressions=impressions,
            clicks=clicks,
            engaged_sessions=engaged,
        )

    def _breakdown(self, dimension="device_category", days=30, source=None):
        from apps.analytics.telemetry_rollups import breakdown_rows

        return breakdown_rows(dimension, days=days, source=source)

    def test_sums_group_by_dimension_ordered_by_clicks(self) -> None:
        self._row(device="desktop", clicks=5, impressions=50)
        self._row(device="desktop", clicks=3, impressions=30)
        self._row(device="mobile", clicks=4, impressions=100)
        rows = self._breakdown("device_category")
        self.assertEqual(
            rows,
            [
                {
                    "device_category": "desktop",
                    "impressions": 80,
                    "clicks": 8,
                    "engaged_sessions": 4,
                },
                {
                    "device_category": "mobile",
                    "impressions": 100,
                    "clicks": 4,
                    "engaged_sessions": 2,
                },
            ],
        )

    def test_source_filter_only_counts_that_source(self) -> None:
        self._row(source="ga4", clicks=5)
        self._row(source="matomo", clicks=7)
        rows = self._breakdown("device_category", source="ga4")
        self.assertEqual(rows[0]["clicks"], 5)

    def test_blocked_country_rows_are_excluded(self) -> None:
        self._row(country="China", clicks=50)
        self._row(country="Germany", clicks=2)
        rows = self._breakdown("country")
        labels = [r["country"] for r in rows]
        self.assertEqual(labels, ["Germany"])

    def test_days_window_excludes_old_rows(self) -> None:
        self._row(days_ago=40, clicks=50)
        self._row(days_ago=1, clicks=3)
        rows = self._breakdown("device_category", days=7)
        self.assertEqual(rows[0]["clicks"], 3)

    def test_top_six_dimensions_only(self) -> None:
        for n in range(7):
            self._row(device=f"device-{n}", clicks=n + 1)
        rows = self._breakdown("device_category")
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["device_category"], "device-6")

    def test_empty_table_returns_empty_list(self) -> None:
        self.assertEqual(self._breakdown("device_category"), [])

    def test_unknown_dimension_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self._breakdown("suggestion_id")
