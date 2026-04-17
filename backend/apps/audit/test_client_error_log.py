"""
Tests for Phase U1 / Gap 26 — ClientErrorLog ingest endpoint.

Covers:
- POST `/api/telemetry/client-errors/` creates a row with the provided fields.
- Unauthenticated callers are allowed (login page JS errors must still arrive).
- Authenticated callers have their user_id stamped automatically.
- Empty `message` is rejected with 400.
- Oversized `stack` / `user_agent` get server-side-truncated not rejected.
- Malformed `context` (non-object) is rejected with 400.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import ClientErrorLog


class ClientErrorLogEndpointTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.url = reverse("client-error-log")

    def test_anonymous_can_post(self):
        resp = self.client.post(
            self.url,
            data={
                "message": "ReferenceError: foo is not defined",
                "stack": "at Component (x.ts:12:3)",
                "route": "/dashboard",
                "url": "http://localhost/dashboard",
                "user_agent": "Mozilla/5.0 (X11) Chrome/120",
                "app_version": "2.0.0",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = ClientErrorLog.objects.order_by("-created_at").first()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.route, "/dashboard")
        self.assertEqual(row.app_version, "2.0.0")
        self.assertIsNone(row.user_id)

    def test_authenticated_user_id_stamped(self):
        User = get_user_model()
        user = User.objects.create_user(username="cel-user", password="x")
        self.client.force_authenticate(user=user)

        resp = self.client.post(
            self.url,
            data={"message": "TypeError: x is null"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = ClientErrorLog.objects.order_by("-created_at").first()
        assert row is not None
        self.assertEqual(row.user_id, user.pk)

    def test_empty_message_rejected(self):
        resp = self.client.post(
            self.url,
            data={"message": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("message", resp.data)

    def test_missing_message_rejected(self):
        resp = self.client.post(self.url, data={}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_oversized_stack_is_truncated_not_rejected(self):
        big_stack = "frame\n" * 5000  # ~30 kB
        resp = self.client.post(
            self.url,
            data={"message": "boom", "stack": big_stack},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = ClientErrorLog.objects.order_by("-created_at").first()
        assert row is not None
        self.assertLessEqual(len(row.stack), 16000)

    def test_user_agent_truncated_server_side(self):
        long_ua = "A" * 2000
        resp = self.client.post(
            self.url,
            data={"message": "boom", "user_agent": long_ua},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        row = ClientErrorLog.objects.order_by("-created_at").first()
        assert row is not None
        self.assertLessEqual(len(row.user_agent), 500)

    def test_context_must_be_object(self):
        resp = self.client.post(
            self.url,
            data={"message": "boom", "context": ["not", "an", "object"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
