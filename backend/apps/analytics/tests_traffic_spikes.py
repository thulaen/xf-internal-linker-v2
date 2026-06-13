"""Tests for the Prophet seasonality-aware traffic-spike detector.

These exercise the real Prophet fit (no mocking of the model), so each
test seeds a multi-week daily click history — Prophet needs enough
active days to model a page's weekly rhythm. TransactionTestCase is used
because the detector reads the seeded rows back through ADBC's separate
Postgres connection, which only sees committed data.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.test import TransactionTestCase

from apps.content.models import ContentItem

from .models import SearchMetric

TARGET = date(2026, 6, 9)  # a Tuesday
_HISTORY_DAYS = 60


def _make_item(content_id: int, title: str) -> ContentItem:
    return ContentItem.objects.create(
        content_id=content_id,
        content_type="thread",
        title=title,
        url=f"https://forum.example.com/{content_id}",
    )


def _seed(item: ContentItem, clicks_for_day) -> None:
    """Seed daily GSC clicks for the history window + the target day.

    ``clicks_for_day`` maps a day-offset-from-target (negative = past,
    0 = target) to a click count via a callable taking the date.
    """
    for offset in range(_HISTORY_DAYS, -1, -1):
        day = TARGET - timedelta(days=offset)
        SearchMetric.objects.create(
            content_item=item, source="gsc", date=day, clicks=clicks_for_day(day)
        )


# TransactionTestCase: detect_spikes reads via ADBC's own connection (committed
# rows only). See apps.analytics.services.adbc_reader.
class DetectSpikesServiceTests(TransactionTestCase):
    def _run(self, **overrides):
        from apps.analytics.services.spike_forecast import detect_spikes

        params = dict(
            history_days=_HISTORY_DAYS,
            noise_floor=10,
            upper_bound_factor=1.2,
            max_items=50,
            min_active_days=14,
        )
        params.update(overrides)
        return detect_spikes(TARGET, **params)

    def test_clear_surge_is_flagged(self) -> None:
        item = _make_item(1, "Steady page that surges")
        _seed(item, lambda d: 80 if d == TARGET else 10)
        findings = self._run()
        self.assertEqual([f.item_id for f in findings], [item.pk])
        self.assertEqual(findings[0].latest_clicks, 80)
        self.assertGreater(findings[0].expected_upper, 0)

    def test_normal_day_is_not_flagged(self) -> None:
        item = _make_item(2, "Steady page, normal day")
        _seed(item, lambda d: 11 if d == TARGET else 10)
        self.assertEqual(self._run(), [])

    def test_expected_weekly_peak_is_not_flagged(self) -> None:
        # Busy every Tuesday (~40), quiet otherwise (~8). The target is a
        # Tuesday at 40 — Prophet learns the Tuesday rhythm, so the expected
        # peak does NOT alert. This is the improvement over a flat average.
        item = _make_item(3, "Weekly-rhythm page")
        _seed(item, lambda d: 40 if d.weekday() == 1 else 8)
        self.assertEqual(self._run(), [])

    def test_below_noise_floor_is_skipped(self) -> None:
        # 8x its own average but under the 10-click floor → ignored.
        item = _make_item(4, "Tiny page")
        _seed(item, lambda d: 8 if d == TARGET else 1)
        self.assertEqual(self._run(), [])

    def test_insufficient_history_is_skipped(self) -> None:
        item = _make_item(5, "Brand-new page")
        # Only 5 active days near the target — below min_active_days.
        for offset in range(4, -1, -1):
            SearchMetric.objects.create(
                content_item=item,
                source="gsc",
                date=TARGET - timedelta(days=offset),
                clicks=100 if offset == 0 else 12,
            )
        self.assertEqual(self._run(), [])

    def test_no_gsc_data_returns_empty(self) -> None:
        self.assertEqual(self._run(), [])


class DetectTrafficSpikesTaskTests(TransactionTestCase):
    def test_task_emits_one_alert_for_a_surge(self) -> None:
        from unittest.mock import patch

        from apps.analytics import tasks

        item = _make_item(7, "Surging page")
        _seed(item, lambda d: 90 if d == TARGET else 10)
        with patch("apps.notifications.services.emit_operator_alert") as emit:
            result = tasks.detect_traffic_spikes()
        self.assertEqual(result, {"alerts_emitted": 1})
        payload = emit.call_args.kwargs["payload"]
        self.assertEqual(payload["item_id"], item.pk)
        self.assertEqual(payload["latest_clicks"], 90)
        self.assertIn("expected_upper", payload)
        self.assertEqual(
            emit.call_args.kwargs["dedupe_key"], f"traffic-spike-{item.pk}-{TARGET}"
        )

    def test_task_no_gsc_data_emits_nothing(self) -> None:
        from unittest.mock import patch

        from apps.analytics import tasks

        with patch("apps.notifications.services.emit_operator_alert") as emit:
            result = tasks.detect_traffic_spikes()
        self.assertEqual(result, {"alerts_emitted": 0})
        emit.assert_not_called()
