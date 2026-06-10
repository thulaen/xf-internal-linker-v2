"""End-to-end tests for the DataFusion-backed traffic spike detector.

detect_traffic_spikes() snapshots the GSC click window to a Parquet file and
runs one DataFusion SQL pass to find pages whose latest daily clicks exceed
4x their 7-day trailing average. These tests build a small real database
(three pages with known click histories) and assert exactly one alert fires,
with the right numbers in its payload.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase

from apps.content.models import ContentItem

from .models import SearchMetric


TARGET = date(2026, 6, 9)


def _seed_history(item: ContentItem, daily: int, latest: int) -> None:
    """Seven days of steady clicks, then `latest` clicks on the target day."""
    for offset in range(7, 0, -1):
        SearchMetric.objects.create(
            content_item=item,
            source="gsc",
            date=TARGET - timedelta(days=offset),
            clicks=daily,
        )
    SearchMetric.objects.create(
        content_item=item, source="gsc", date=TARGET, clicks=latest
    )


class DetectTrafficSpikesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        def make_item(content_id: int, title: str) -> ContentItem:
            return ContentItem.objects.create(
                content_id=content_id,
                content_type="thread",
                title=title,
                url=f"https://forum.example.com/{content_id}",
            )

        cls.spiker = make_item(1, "Spiking Thread")
        cls.steady = make_item(2, "Steady Thread")
        cls.quiet = make_item(3, "Quiet Thread")

        _seed_history(cls.spiker, daily=10, latest=50)  # 5x its average — spike
        _seed_history(cls.steady, daily=10, latest=12)  # 1.2x — no spike
        _seed_history(cls.quiet, daily=1, latest=8)  # 8x but under the 10-click noise floor

    def _run(self):
        from apps.analytics import tasks

        with patch(
            "apps.notifications.services.emit_operator_alert"
        ) as emit:
            result = tasks.detect_traffic_spikes()
        return result, emit

    def test_only_the_spiking_page_fires_an_alert(self) -> None:
        result, emit = self._run()
        self.assertEqual(result, {"alerts_emitted": 1})
        emit.assert_called_once()
        payload = emit.call_args.kwargs["payload"]
        self.assertEqual(payload["item_id"], self.spiker.pk)
        self.assertEqual(payload["latest_clicks"], 50)
        self.assertAlmostEqual(payload["avg_clicks"], 10.0)
        self.assertEqual(payload["date"], str(TARGET))

    def test_alert_dedupe_key_is_stable_per_item_and_day(self) -> None:
        _, emit = self._run()
        self.assertEqual(
            emit.call_args.kwargs["dedupe_key"],
            f"traffic-spike-{self.spiker.pk}-{TARGET}",
        )

    def test_no_gsc_rows_means_no_alerts(self) -> None:
        SearchMetric.objects.all().delete()
        result, emit = self._run()
        self.assertEqual(result, {"alerts_emitted": 0})
        emit.assert_not_called()

    def test_deleted_item_does_not_crash_the_task(self) -> None:
        # An orphan metric row (item deleted after the snapshot filter) must
        # produce an alert with a placeholder title, not a DoesNotExist crash.
        ContentItem.objects.filter(pk=self.spiker.pk).delete()
        # CASCADE removes the spiker's metrics, so re-seed an orphanable spike
        # on the steady item then delete it without cascading (simulate by
        # pointing assertions at a fresh spike whose item vanishes mid-run).
        _seed_history_item = ContentItem.objects.create(
            content_id=99,
            content_type="thread",
            title="Vanishing Thread",
            url="https://forum.example.com/99",
        )
        _seed_history(_seed_history_item, daily=10, latest=99)
        from apps.analytics import tasks

        real_filter = ContentItem.objects.filter

        def filter_no_titles(*args, **kwargs):
            if "pk__in" in kwargs:
                return real_filter(pk__in=[])
            return real_filter(*args, **kwargs)

        with patch(
            "apps.notifications.services.emit_operator_alert"
        ) as emit, patch.object(
            ContentItem.objects, "filter", side_effect=filter_no_titles
        ):
            result = tasks.detect_traffic_spikes()
        self.assertEqual(result["alerts_emitted"], 1)
        title = emit.call_args.kwargs["title"]
        self.assertIn("item #", title)
