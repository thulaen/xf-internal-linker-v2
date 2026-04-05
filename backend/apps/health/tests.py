from django.test import TestCase
from django.utils import timezone
from apps.health.models import ServiceHealthRecord
from apps.health.services import perform_health_check, CHECKERS

class HealthCheckTests(TestCase):
    def test_model_creation(self):
        record = ServiceHealthRecord.objects.create(
            service_key="test_service",
            status=ServiceHealthRecord.STATUS_HEALTHY,
            status_label="All good",
            last_check_at=timezone.now()
        )
        self.assertEqual(record.service_key, "test_service")
        self.assertEqual(record.status, "healthy")

    def test_perform_health_check_invalid(self):
        with self.assertRaises(ValueError):
            perform_health_check("invalid_service")

    def test_perform_health_check_logic(self):
        # We'll mock a simple checker for testing
        def mock_checker():
            from apps.health.services import ServiceHealthResult
            return ServiceHealthResult(
                service_key="mock_service",
                status="healthy",
                status_label="Mock is fine",
                last_success_at=timezone.now()
            )
        
        # Patch CHECKERS temporarily
        original_checkers = CHECKERS.copy()
        CHECKERS["mock_service"] = mock_checker
        try:
            record = perform_health_check("mock_service")
            self.assertEqual(record.status, "healthy")
            self.assertEqual(record.status_label, "Mock is fine")
        finally:
            # Restore
            CHECKERS.clear()
            CHECKERS.update(original_checkers)
