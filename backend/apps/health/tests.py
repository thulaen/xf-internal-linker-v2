"""Test suite for the health app."""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from unittest import mock
from unittest.mock import MagicMock, patch, call

from apps.health.models import ServiceHealthRecord
from apps.health.services import (
    perform_health_check,
    HealthCheckRegistry,
    ServiceHealthResult,
)


class HealthTaskConnectionGuardTests(SimpleTestCase):
    """Issues #1338 and #423: run_all_health_checks must reset a failed DB connection.

    When a health check causes a DB error (e.g., check_database_health runs
    cursor() which fails), the Postgres connection ends up in an aborted
    transaction state.  The NEXT perform_health_check call then tries to do
    get_or_create on the same connection and raises InFailedSqlTransaction.

    Fix: after each individual check raises, close+reset the connection before
    continuing so subsequent checks start with a clean state.
    """

    def test_run_all_health_checks_closes_connection_before_work(self):
        """connection.close() must be called at startup when not in_atomic_block (issue #1338)."""
        from apps.health.tasks import run_all_health_checks

        mock_conn = MagicMock()
        mock_conn.in_atomic_block = False

        mock_checkers = {"test_svc": MagicMock(return_value=MagicMock(status="healthy"))}

        with (
            patch("apps.health.tasks.connection", mock_conn),
            patch("apps.health.tasks.HealthCheckRegistry") as mock_reg,
            # Patch perform_health_check so checkers work without DB
            patch("apps.health.tasks.perform_health_check") as mock_phc,
        ):
            mock_reg.get_checkers.return_value = mock_checkers
            mock_phc.return_value = MagicMock(status="healthy")
            run_all_health_checks()

        # At minimum one close() call at startup.
        mock_conn.close.assert_called()

    def test_run_all_health_checks_does_not_close_inside_atomic_block(self):
        """Must not call connection.close() when already in a transaction."""
        from apps.health.tasks import run_all_health_checks

        mock_conn = MagicMock()
        mock_conn.in_atomic_block = True

        mock_checkers = {"test_svc": MagicMock(return_value=MagicMock(status="healthy"))}

        with (
            patch("apps.health.tasks.connection", mock_conn),
            patch("apps.health.tasks.HealthCheckRegistry") as mock_reg,
        ):
            mock_reg.get_checkers.return_value = mock_checkers
            run_all_health_checks()

        mock_conn.close.assert_not_called()

    def test_run_all_health_checks_resets_connection_after_check_exception(self):
        """After a checker raises, close the connection so the next check starts clean.

        This prevents psycopg.errors.InFailedSqlTransaction propagating across
        successive health checks (issues #1338 and #423).
        """
        from apps.health.tasks import run_all_health_checks

        mock_conn = MagicMock()
        mock_conn.in_atomic_block = False

        close_calls = []

        def _track_close():
            close_calls.append(1)

        mock_conn.close.side_effect = _track_close

        def _failing_checker():
            raise RuntimeError("DB unavailable")

        mock_checkers = {
            "failing_svc": _failing_checker,
            "healthy_svc": MagicMock(return_value=MagicMock(status="healthy")),
        }

        with (
            patch("apps.health.tasks.connection", mock_conn),
            patch("apps.health.tasks.HealthCheckRegistry") as mock_reg,
            patch("apps.health.tasks.perform_health_check", side_effect=RuntimeError("DB unavailable")),
        ):
            mock_reg.get_checkers.return_value = mock_checkers
            result = run_all_health_checks()

        # Must have closed the connection at startup and again after the failure.
        self.assertGreaterEqual(len(close_calls), 2)
        self.assertFalse(result["ok"])


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
