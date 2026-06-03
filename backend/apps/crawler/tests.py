"""Crawler app tests."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.crawler.models import CrawlSession


class PulseHeartbeatTimeLimitTests(SimpleTestCase):
    """Issue #317: pulse_heartbeat must have a time_limit long enough to finish.

    The task does Postgres probe + Redis probe + Celery inspect (2s timeout ×
    N workers) + DB write + Redis PUBLISH.  With 4 workers the Celery inspect
    alone takes up to 8 s; 30 s is too tight under load.  The new limit is 60
    s / soft 50 s.
    """

    def test_pulse_heartbeat_time_limit_is_at_least_60(self):
        """time_limit for pulse_heartbeat must be >= 60 to survive inspect load."""
        from apps.crawler.tasks import pulse_heartbeat

        time_limit = pulse_heartbeat.time_limit
        self.assertGreaterEqual(
            time_limit,
            60,
            msg=f"pulse_heartbeat.time_limit={time_limit} — too small; 30 s hits TimeLimitExceeded under Celery inspect load (issue #317)",
        )

    def test_watchdog_check_time_limit_is_at_least_60(self):
        """watchdog_check also runs inspect; same 60 s floor needed."""
        from apps.crawler.tasks import watchdog_check

        time_limit = watchdog_check.time_limit
        self.assertGreaterEqual(
            time_limit,
            60,
            msg=f"watchdog_check.time_limit={time_limit} — must be >= 60 (issue #317)",
        )


class CrawlerResumeApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username="crawler-resume-user",
            password="pass",
        )
        self.client.force_authenticate(user=user)

    @patch("apps.crawler.tasks.run_crawl_session.delay")
    def test_resume_session_does_not_require_site_domain(self, delay_task):
        session = CrawlSession.objects.create(
            site_domain="example.com",
            status="paused",
            is_resumable=True,
        )

        response = self.client.post(
            "/api/crawler/sessions/",
            {"resume_session_id": str(session.session_id)},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.status, "pending")
        delay_task.assert_called_once_with(str(session.session_id))
