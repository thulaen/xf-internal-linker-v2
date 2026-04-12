from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.diagnostics import health


class HealthCheckTests(TestCase):
    def test_check_native_scoring_reports_runtime_metadata(self):
        state, explanation, next_step, metadata = health.check_native_scoring()

        self.assertIn(state, {"healthy", "degraded", "failed"})
        self.assertTrue(explanation)
        self.assertTrue(next_step)
        self.assertIn("runtime_path", metadata)
        self.assertIn("fallback_active", metadata)
        self.assertIn("safe_to_use", metadata)
        self.assertIn("module_statuses", metadata)
        self.assertGreater(len(metadata["module_statuses"]), 0)
        self.assertIn("compiled_module_count", metadata)
        self.assertIn("benchmark_status", metadata)


@override_settings(SCHEDULER_CONTROL_TOKEN="scheduler-secret")
class SchedulerDispatchViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch(
        "apps.pipeline.tasks.dispatch_import_content",
        return_value={"job_id": "abc", "runtime_owner": "celery", "message": "queued"},
    )
    def test_scheduler_dispatch_accepts_import_job_with_token(
        self, dispatch_import_content
    ):
        response = self.client.post(
            "/api/system/status/internal/scheduler/dispatch/",
            {
                "task": "pipeline.import_content",
                "kwargs": {"source": "api", "mode": "full"},
                "periodic_task_name": "nightly-xenforo-sync",
            },
            format="json",
            HTTP_X_SCHEDULER_TOKEN="scheduler-secret",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(response.json()["periodic_task_name"], "nightly-xenforo-sync")
        dispatch_import_content.assert_called_once_with(
            scope_ids=None,
            mode="full",
            source="api",
            file_path=None,
            job_id=None,
            force_reembed=False,
        )

    def test_scheduler_dispatch_rejects_bad_token(self):
        response = self.client.post(
            "/api/system/status/internal/scheduler/dispatch/",
            {
                "task": "pipeline.import_content",
                "kwargs": {"source": "api", "mode": "full"},
            },
            format="json",
            HTTP_X_SCHEDULER_TOKEN="wrong-token",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("did not match", response.json()["detail"])
