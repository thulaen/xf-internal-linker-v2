from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.analytics.models import AnalyticsSyncRun
from apps.core.models import AppSetting


class AnalyticsTelemetrySettingsApiTests(APITestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="analytics-user", password="pass")
        self.client.force_authenticate(user=user)

    def test_ga4_settings_round_trip_masks_secret_and_shared_values(self):
        response = self.client.put(
            "/api/analytics/settings/ga4/",
            {
                "behavior_enabled": True,
                "property_id": "123456789",
                "measurement_id": "G-TEST1234",
                "api_secret": "super-secret",
                "sync_enabled": True,
                "sync_lookback_days": 9,
                "event_schema": "fr016_v1",
                "geo_granularity": "country",
                "retention_days": 365,
                "impression_visible_ratio": 0.6,
                "impression_min_ms": 1200,
                "engaged_min_seconds": 12,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["behavior_enabled"])
        self.assertEqual(payload["measurement_id"], "G-TEST1234")
        self.assertTrue(payload["api_secret_configured"])
        self.assertEqual(payload["sync_lookback_days"], 9)
        self.assertEqual(AppSetting.objects.get(key="analytics.ga4_measurement_id").value, "G-TEST1234")
        self.assertTrue(AppSetting.objects.get(key="analytics.ga4_api_secret").is_secret)
        self.assertEqual(AppSetting.objects.get(key="analytics.telemetry_retention_days").value, "365")

    @patch("apps.analytics.views.requests.post")
    def test_ga4_test_connection_uses_saved_secret(self, post_mock):
        AppSetting.objects.create(
            key="analytics.ga4_measurement_id",
            value="G-TEST1234",
            value_type="str",
            category="analytics",
            description="measurement id",
        )
        AppSetting.objects.create(
            key="analytics.ga4_api_secret",
            value="super-secret",
            value_type="str",
            category="analytics",
            description="api secret",
            is_secret=True,
        )
        post_mock.return_value.json.return_value = {"validationMessages": []}
        post_mock.return_value.raise_for_status.return_value = None

        response = self.client.post("/api/analytics/settings/ga4/test-connection/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "connected")
        post_mock.assert_called_once()

    def test_matomo_settings_round_trip_masks_token(self):
        response = self.client.put(
            "/api/analytics/settings/matomo/",
            {
                "enabled": True,
                "url": "https://matomo.example.com/",
                "site_id_xenforo": "7",
                "site_id_wordpress": "9",
                "token_auth": "token-secret",
                "sync_enabled": True,
                "sync_lookback_days": 4,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["url"], "https://matomo.example.com")
        self.assertEqual(payload["site_id_xenforo"], "7")
        self.assertTrue(payload["token_auth_configured"])
        self.assertTrue(AppSetting.objects.get(key="analytics.matomo_token_auth").is_secret)

    @patch("apps.analytics.views.requests.get")
    def test_matomo_test_connection_returns_connected(self, get_mock):
        AppSetting.objects.create(
            key="analytics.matomo_url",
            value="https://matomo.example.com",
            value_type="str",
            category="analytics",
            description="matomo url",
        )
        AppSetting.objects.create(
            key="analytics.matomo_site_id_xenforo",
            value="7",
            value_type="str",
            category="analytics",
            description="site id",
        )
        AppSetting.objects.create(
            key="analytics.matomo_token_auth",
            value="token-secret",
            value_type="str",
            category="analytics",
            description="token",
            is_secret=True,
        )
        get_mock.return_value.json.return_value = {"idsite": 7, "name": "Forum"}
        get_mock.return_value.raise_for_status.return_value = None

        response = self.client.post("/api/analytics/settings/matomo/test-connection/", {}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "connected")

    def test_overview_returns_last_sync_and_counts(self):
        AnalyticsSyncRun.objects.create(source="ga4", status="completed", rows_written=12, rows_updated=2, rows_read=20)
        response = self.client.get("/api/analytics/telemetry/overview/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("ga4", payload)
        self.assertIn("matomo", payload)
        self.assertEqual(payload["telemetry_row_count"], 0)
        self.assertEqual(payload["coverage_row_count"], 0)
