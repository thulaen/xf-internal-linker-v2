from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django_celery_beat.models import PeriodicTask
from rest_framework.test import APITestCase

from apps.core.models import AppSetting
from apps.sync.models import SyncJob


@override_settings(WORDPRESS_BASE_URL="", WORDPRESS_USERNAME="", WORDPRESS_APP_PASSWORD="")
class WordPressSettingsApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="settings-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_wordpress_settings_round_trip_and_schedule_task(self):
        response = self.client.put(
            "/api/settings/wordpress/",
            {
                "base_url": "https://blog.example.com/",
                "username": "editor",
                "app_password": "secret-token",
                "sync_enabled": True,
                "sync_hour": 4,
                "sync_minute": 15,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "base_url": "https://blog.example.com",
                "username": "editor",
                "app_password_configured": True,
                "sync_enabled": True,
                "sync_hour": 4,
                "sync_minute": 15,
            },
        )
        self.assertEqual(AppSetting.objects.get(key="wordpress.base_url").value, "https://blog.example.com")
        self.assertEqual(AppSetting.objects.get(key="wordpress.username").value, "editor")
        self.assertTrue(AppSetting.objects.get(key="wordpress.app_password").is_secret)

        periodic_task = PeriodicTask.objects.get(name="wordpress-content-sync")
        self.assertTrue(periodic_task.enabled)
        self.assertEqual(periodic_task.queue, "pipeline")
        self.assertIn('"source": "wp"', periodic_task.kwargs)

    def test_schedule_requires_base_url(self):
        response = self.client.put(
            "/api/settings/wordpress/",
            {
                "base_url": "",
                "username": "",
                "sync_enabled": True,
                "sync_hour": 3,
                "sync_minute": 0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("base_url", response.json()["detail"])

    @patch("apps.pipeline.tasks.import_content.delay")
    def test_manual_wordpress_sync_starts_sync_job(self, delay_mock):
        AppSetting.objects.create(
            key="wordpress.base_url",
            value="https://blog.example.com",
            value_type="str",
            category="sync",
            description="WordPress base URL",
        )

        response = self.client.post("/api/sync/wordpress/run/", {}, format="json")

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        job = SyncJob.objects.get(job_id=payload["job_id"])
        self.assertEqual(job.source, "wp")
        self.assertEqual(job.mode, "full")
        delay_mock.assert_called_once()


@override_settings(WORDPRESS_BASE_URL="", WORDPRESS_USERNAME="", WORDPRESS_APP_PASSWORD="")
class WordPressSettingsDefaultsTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="defaults-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_defaults_expose_blank_public_configuration(self):
        response = self.client.get("/api/settings/wordpress/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "base_url": "",
                "username": "",
                "app_password_configured": False,
                "sync_enabled": False,
                "sync_hour": 3,
                "sync_minute": 0,
            },
        )
