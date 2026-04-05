from django.test import TestCase
from django.utils import timezone
from apps.health.models import ServiceHealthRecord
from apps.health.services import perform_health_check, HealthCheckRegistry, ServiceHealthResult

class HealthCheckTests(TestCase):
    def test_model_creation(self):
        record = ServiceHealthRecord.objects.create(
            service_key="test_service",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="All good",
            last_check_at=timezone.now(),
            issue_description="No problems found.",
            suggested_fix="Enjoy the uptime."
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
                last_success_at=timezone.now()
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
