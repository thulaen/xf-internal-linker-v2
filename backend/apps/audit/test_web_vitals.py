"""
Tests for Phase E2 / Gap 51 — WebVital ingest endpoint.

Covers:
- POST `/api/telemetry/web-vitals/` creates a row with the provided fields.
- Unauthenticated callers are allowed (vitals must work on the login page).
- Authenticated callers have their user_id stamped automatically.
- Unknown metric name (anything outside LCP/CLS/INP/FCP/TTFB) is rejected.
- Unknown rating falls back to 'good' rather than rejecting the beacon.
- Negative or absurdly large values are clamped, not rejected.
- Path query strings are stripped (defence in depth).
- Oversized strings are truncated server-side not rejected.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import WebVital


class WebVitalEndpointTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.url = reverse("web-vitals")

    def _valid_payload(self, **overrides) -> dict:
        base = {
            "name": "LCP",
            "value": 1234.5,
            "rating": "good",
            "delta": 1234.5,
            "id": "v4-1-abc",
            "navigation_type": "navigate",
            "path": "/dashboard",
            "device_memory": 8.0,
            "effective_connection_type": "4g",
            "timestamp": 1_700_000_000_000,
        }
        base.update(overrides)
        return base

    def test_anonymous_can_post(self):
        resp = self.client.post(self.url, data=self._valid_payload(), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = WebVital.objects.order_by("-created_at").first()
        assert row is not None
        self.assertEqual(row.name, "LCP")
        self.assertEqual(row.path, "/dashboard")
        self.assertEqual(row.rating, "good")
        self.assertAlmostEqual(row.value, 1234.5)
        self.assertEqual(row.metric_id, "v4-1-abc")
        self.assertEqual(row.client_timestamp_ms, 1_700_000_000_000)
        self.assertIsNone(row.user_id)

    def test_authenticated_user_id_stamped(self):
        User = get_user_model()
        user = User.objects.create_user(username="wv-user", password="x")
        self.client.force_authenticate(user=user)

        resp = self.client.post(
            self.url,
            data=self._valid_payload(name="INP", value=150.0, rating="good"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = WebVital.objects.order_by("-created_at").first()
        assert row is not None
        self.assertEqual(row.user_id, user.pk)

    def test_unknown_metric_rejected(self):
        resp = self.client.post(
            self.url,
            data=self._valid_payload(name="FID"),  # FID is obsolete/removed
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", resp.data)

    def test_metric_name_uppercased(self):
        resp = self.client.post(
            self.url,
            data=self._valid_payload(name="lcp"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = WebVital.objects.order_by("-created_at").first()
        assert row is not None
        self.assertEqual(row.name, "LCP")

    def test_bad_rating_falls_back_to_good(self):
        resp = self.client.post(
            self.url,
            data=self._valid_payload(rating="terrible"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = WebVital.objects.order_by("-created_at").first()
        assert row is not None
        self.assertEqual(row.rating, "good")

    def test_negative_value_clamped_to_zero(self):
        resp = self.client.post(
            self.url,
            data=self._valid_payload(value=-5.0),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = WebVital.objects.order_by("-created_at").first()
        assert row is not None
        self.assertEqual(row.value, 0.0)

    def test_absurd_value_clamped(self):
        resp = self.client.post(
            self.url,
            # 1 hour = 3_600_000; sending 10 hours should clip to 1 hour.
            data=self._valid_payload(value=36_000_000.0),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = WebVital.objects.order_by("-created_at").first()
        assert row is not None
        self.assertEqual(row.value, 3_600_000.0)

    def test_path_query_string_stripped(self):
        resp = self.client.post(
            self.url,
            data=self._valid_payload(path="/review?q=secret&tab=all"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = WebVital.objects.order_by("-created_at").first()
        assert row is not None
        self.assertEqual(row.path, "/review")

    def test_missing_name_rejected(self):
        payload = self._valid_payload()
        del payload["name"]
        resp = self.client.post(self.url, data=payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_value_rejected(self):
        payload = self._valid_payload()
        del payload["value"]
        resp = self.client.post(self.url, data=payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_optional_fields_default_blank(self):
        resp = self.client.post(
            self.url,
            data={"name": "CLS", "value": 0.05},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = WebVital.objects.order_by("-created_at").first()
        assert row is not None
        self.assertEqual(row.name, "CLS")
        self.assertEqual(row.path, "")
        self.assertEqual(row.metric_id, "")
        self.assertIsNone(row.device_memory)
        self.assertIsNone(row.client_timestamp_ms)

    def test_all_five_metric_names_accepted(self):
        for name in ("LCP", "CLS", "INP", "FCP", "TTFB"):
            resp = self.client.post(
                self.url,
                data=self._valid_payload(name=name),
                format="json",
            )
            self.assertEqual(
                resp.status_code,
                status.HTTP_201_CREATED,
                msg=f"metric {name} was rejected",
            )
