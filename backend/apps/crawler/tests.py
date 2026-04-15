"""Crawler app tests."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.crawler.models import CrawlSession


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
