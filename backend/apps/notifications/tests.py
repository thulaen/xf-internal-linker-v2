"""
Tests for the notifications app.

These tests run against the real database (no mocks).
They require a live PostgreSQL connection — run inside Docker or CI.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AlertDeliveryAttempt, OperatorAlert
from .services import emit_operator_alert, get_unread_summary


class OperatorAlertModelTest(TestCase):
    def test_create_alert(self):
        alert = OperatorAlert.objects.create(
            event_type="job.completed",
            severity=OperatorAlert.SEVERITY_SUCCESS,
            title="Test",
            message="A test alert.",
            dedupe_key="job.completed:test-1",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )
        self.assertEqual(alert.status, OperatorAlert.STATUS_UNREAD)
        self.assertEqual(alert.occurrence_count, 1)

    def test_str(self):
        alert = OperatorAlert(
            severity=OperatorAlert.SEVERITY_ERROR,
            title="Oops",
            status=OperatorAlert.STATUS_UNREAD,
        )
        self.assertIn("ERROR", str(alert))
        self.assertIn("Oops", str(alert))


class EmitOperatorAlertTest(TestCase):
    def _emit(self, dedupe_key="test:1", **kwargs):
        defaults = dict(
            event_type="job.completed",
            severity=OperatorAlert.SEVERITY_SUCCESS,
            title="Done",
            message="All good.",
            source_area=OperatorAlert.AREA_JOBS,
            dedupe_key=dedupe_key,
        )
        defaults.update(kwargs)
        return emit_operator_alert(**defaults)

    def test_creates_new_alert(self):
        alert = self._emit()
        self.assertIsNotNone(alert.pk)
        self.assertEqual(alert.status, OperatorAlert.STATUS_UNREAD)

    def test_deduplication_increments_count(self):
        first = self._emit(dedupe_key="dedup:1")
        second = self._emit(dedupe_key="dedup:1", cooldown_seconds=3600)
        self.assertEqual(first.pk, second.pk)
        second.refresh_from_db()
        self.assertEqual(second.occurrence_count, 2)

    def test_new_row_after_cooldown_expires(self):
        first = self._emit(dedupe_key="expire:1", cooldown_seconds=0)
        # Force last_seen_at into the past so cooldown has expired
        OperatorAlert.objects.filter(pk=first.pk).update(
            last_seen_at=timezone.now() - timedelta(seconds=10)
        )
        second = self._emit(dedupe_key="expire:1", cooldown_seconds=5)
        self.assertNotEqual(first.pk, second.pk)

    def test_delivery_attempt_logged(self):
        alert = self._emit(dedupe_key="delivery:1")
        attempts = AlertDeliveryAttempt.objects.filter(alert=alert)
        self.assertEqual(attempts.count(), 1)
        self.assertEqual(attempts.first().channel, AlertDeliveryAttempt.CHANNEL_IN_APP)
        self.assertEqual(attempts.first().result, AlertDeliveryAttempt.RESULT_SENT)

    def test_reopens_acknowledged_alert(self):
        alert = self._emit(dedupe_key="reopen:1")
        alert.status = OperatorAlert.STATUS_ACKNOWLEDGED
        alert.acknowledged_at = timezone.now()
        alert.save()
        self._emit(dedupe_key="reopen:1", cooldown_seconds=3600)
        alert.refresh_from_db()
        self.assertEqual(alert.status, OperatorAlert.STATUS_UNREAD)


class GetUnreadSummaryTest(TestCase):
    def test_empty(self):
        summary = get_unread_summary()
        self.assertEqual(summary["total_unread"], 0)
        self.assertIsNone(summary["latest_at"])

    def test_counts_unread(self):
        now = timezone.now()
        OperatorAlert.objects.create(
            event_type="job.failed",
            severity=OperatorAlert.SEVERITY_ERROR,
            title="Fail",
            message="x",
            dedupe_key="fail:1",
            first_seen_at=now,
            last_seen_at=now,
            status=OperatorAlert.STATUS_UNREAD,
        )
        OperatorAlert.objects.create(
            event_type="job.failed",
            severity=OperatorAlert.SEVERITY_WARNING,
            title="Warn",
            message="x",
            dedupe_key="warn:1",
            first_seen_at=now,
            last_seen_at=now,
            status=OperatorAlert.STATUS_UNREAD,
        )
        OperatorAlert.objects.create(
            event_type="job.failed",
            severity=OperatorAlert.SEVERITY_ERROR,
            title="Acked",
            message="x",
            dedupe_key="acked:1",
            first_seen_at=now,
            last_seen_at=now,
            status=OperatorAlert.STATUS_ACKNOWLEDGED,
        )
        summary = get_unread_summary()
        self.assertEqual(summary["total_unread"], 2)
        self.assertEqual(summary["by_severity"][OperatorAlert.SEVERITY_ERROR], 1)
        self.assertEqual(summary["by_severity"][OperatorAlert.SEVERITY_WARNING], 1)


class NotificationApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="notif-api-user",
            email="notif-api@example.com",
            password="notif-password-123",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_alert_detail_returns_matching_alert(self):
        alert = emit_operator_alert(
            event_type="system.test",
            severity=OperatorAlert.SEVERITY_WARNING,
            title="Needs attention",
            message="A detail route should load this alert.",
            source_area=OperatorAlert.AREA_SYSTEM,
            dedupe_key="notification-api-test:detail",
        )

        response = self.client.get(f"/api/notifications/alerts/{alert.alert_id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["alert_id"], str(alert.alert_id))
        self.assertEqual(response.data["title"], "Needs attention")

    def test_alert_detail_returns_404_for_unknown_uuid(self):
        response = self.client.get(
            "/api/notifications/alerts/00000000-0000-0000-0000-000000000000/"
        )

        self.assertEqual(response.status_code, 404)

    def test_alert_list_is_paginated(self):
        """The list endpoint must return DRF's pagination envelope so the
        operator-facing /alerts page can paginate large unread queues
        without rendering thousands of cards in the DOM. Replaces the
        pre-2026-04-26 silent ``qs[:200]`` cap that hid >1k unread alerts
        during outages.
        """
        # Emit 30 alerts — more than the default page size (25) so we
        # can assert both the page slice and the cross-page count.
        for i in range(30):
            emit_operator_alert(
                event_type="system.test",
                severity=OperatorAlert.SEVERITY_WARNING,
                title=f"Alert {i}",
                message=f"message {i}",
                source_area=OperatorAlert.AREA_SYSTEM,
                # Distinct dedupe_keys so emit_operator_alert creates
                # 30 separate rows rather than incrementing one.
                dedupe_key=f"notification-api-test:list:{i}",
            )

        response = self.client.get("/api/notifications/alerts/")

        self.assertEqual(response.status_code, 200)
        # DRF pagination envelope.
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        # 30 alerts total, default page size is 25.
        self.assertEqual(response.data["count"], 30)
        self.assertEqual(len(response.data["results"]), 25)
        # Page 2 returns the remaining 5.
        page_two = self.client.get("/api/notifications/alerts/?page=2")
        self.assertEqual(page_two.status_code, 200)
        self.assertEqual(len(page_two.data["results"]), 5)
