from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.health.models import ServiceHealthRecord
from apps.health.services import (
    perform_health_check,
    HealthCheckRegistry,
    ServiceHealthResult,
)


class HealthCheckTests(TestCase):
    def test_model_creation(self):
        record = ServiceHealthRecord.objects.create(
            service_key="test_service",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="All good",
            last_check_at=timezone.now(),
            issue_description="No problems found.",
            suggested_fix="Enjoy the uptime.",
        )
        self.assertEqual(record.service_key, "test_service")
        self.assertEqual(record.status, "healthy")
        self.assertEqual(record.issue_description, "No problems found.")

    def test_perform_health_check_invalid(self):
        with self.assertRaises(ValueError):
            perform_health_check("invalid_service_random_key_123")

    def test_perform_health_check_logic(self):
        # We'll register a mock checker for testing
        @HealthCheckRegistry.register("mock_service_test")
        def mock_checker():
            return ServiceHealthResult(
                service_key="mock_service_test",
                status=ServiceHealthRecord.STATUS_HEALTHY,
                status_label="Mock is fine",
                issue_description="Mocking is successful.",
                suggested_fix="No action needed.",
                last_success_at=timezone.now(),
            )

        try:
            record = perform_health_check("mock_service_test")
            self.assertEqual(record.status, "healthy")
            self.assertEqual(record.status_label, "Mock is fine")
            self.assertEqual(record.issue_description, "Mocking is successful.")
        finally:
            # Clean up the registry
            checkers = HealthCheckRegistry.get_checkers()
            if "mock_service_test" in checkers:
                del checkers["mock_service_test"]


class HealthApiRouteTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="health-api-user",
            email="health-api@example.com",
            password="health-password-123",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_disk_endpoint_is_not_shadowed_by_viewset_lookup(self):
        response = self.client.get("/api/health/disk/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("db_size_mb", response.data)
        self.assertIn("embeddings_size_mb", response.data)

    def test_gpu_endpoint_is_not_shadowed_by_viewset_lookup(self):
        response = self.client.get("/api/health/gpu/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("available", response.data)
