from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.diagnostics import health


class HttpWorkerHealthTests(TestCase):
    @override_settings(
        HTTP_WORKER_ENABLED=False,
        HTTP_WORKER_URL="http://http-worker-api:8080",
    )
    def test_check_http_worker_reports_disabled_when_feature_is_off(self):
        state, explanation, next_step, metadata = health.check_http_worker()

        self.assertEqual(state, "disabled")
        self.assertIn("turned off", explanation)
        self.assertIn("HTTP_WORKER_ENABLED=true", next_step)
        self.assertTrue(metadata["python_fallback_active"])
        self.assertEqual(metadata["url"], "http://http-worker-api:8080/api/v1/status")

    @override_settings(
        HTTP_WORKER_ENABLED=True,
        HTTP_WORKER_URL="http://http-worker-api:8080",
    )
    @patch("apps.diagnostics.health.requests.get")
    def test_check_http_worker_marks_healthy_when_worker_heartbeat_is_live(self, mock_get):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "status": "ok",
            "schema_version": "v1",
            "build_version": "1.2.3",
            "redis_connected": True,
            "database_connected": True,
            "queue_depth": 4,
            "worker_online": True,
            "worker_heartbeat_age_seconds": 2.5,
            "worker": {
                "instance_id": "worker-a",
                "retry_count_total": 3,
                "dead_letter_count": 1,
                "last_completed": {"job_type": "broken_link_scan"},
                "last_failed": {"job_type": "sitemap", "error": "timeout"},
            },
        }
        mock_get.return_value = response

        state, explanation, next_step, metadata = health.check_http_worker()

        self.assertEqual(state, "healthy")
        self.assertIn("Queue depth is 4", explanation)
        self.assertEqual(next_step, "No action needed.")
        self.assertTrue(metadata["worker_online"])
        self.assertEqual(metadata["queue_depth"], 4)
        self.assertEqual(metadata["build_version"], "1.2.3")
        self.assertEqual(metadata["worker_instance_id"], "worker-a")
        self.assertEqual(metadata["retry_count_total"], 3)
        self.assertEqual(metadata["dead_letter_count"], 1)
        self.assertEqual(metadata["last_completed_job_type"], "broken_link_scan")
        self.assertEqual(metadata["last_failed_error"], "timeout")
        self.assertFalse(metadata["python_fallback_active"])

    @override_settings(
        HTTP_WORKER_ENABLED=True,
        HTTP_WORKER_URL="http://http-worker-api:8080",
    )
    @patch("apps.diagnostics.health.requests.get")
    def test_check_http_worker_marks_queue_drift_when_redis_is_down(self, mock_get):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "status": "ok",
            "schema_version": "v1",
            "redis_connected": False,
            "database_connected": True,
            "worker_online": False,
            "queue_depth": 9,
        }
        mock_get.return_value = response

        state, explanation, next_step, metadata = health.check_http_worker()

        self.assertEqual(state, "degraded")
        self.assertIn("Redis queue is not healthy", explanation)
        self.assertIn("Restore Redis", next_step)
        self.assertFalse(metadata["redis_connected"])
        self.assertEqual(metadata["queue_depth"], 9)
        self.assertEqual(metadata["schema_version"], "v1")
        mock_get.assert_called_once_with(
            "http://http-worker-api:8080/api/v1/status",
            timeout=5,
        )

    @override_settings(
        HTTP_WORKER_ENABLED=True,
        HTTP_WORKER_URL="http://http-worker-api:8080",
    )
    @patch("apps.diagnostics.health.requests.get")
    def test_check_http_worker_marks_degraded_when_worker_lane_is_offline(self, mock_get):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "status": "ok",
            "schema_version": "v1",
            "redis_connected": True,
            "database_connected": True,
            "queue_depth": 13,
            "worker_online": False,
            "worker_heartbeat_age_seconds": 88,
        }
        mock_get.return_value = response

        state, explanation, next_step, metadata = health.check_http_worker()

        self.assertEqual(state, "degraded")
        self.assertIn("queue-backed worker lane is offline", explanation)
        self.assertIn("http-worker-queue", next_step)
        self.assertTrue(metadata["python_fallback_active"])
        self.assertEqual(metadata["queue_depth"], 13)

    @override_settings(
        HTTP_WORKER_ENABLED=True,
        HTTP_WORKER_URL="http://http-worker-api:8080",
    )
    @patch("apps.diagnostics.health.requests.get")
    def test_check_http_worker_marks_degraded_when_database_is_down(self, mock_get):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "status": "ok",
            "schema_version": "v1",
            "redis_connected": True,
            "database_connected": False,
            "queue_depth": 2,
            "worker_online": True,
            "worker_heartbeat_age_seconds": 1.0,
        }
        mock_get.return_value = response

        state, explanation, next_step, metadata = health.check_http_worker()

        self.assertEqual(state, "degraded")
        self.assertIn("PostgreSQL lane is not healthy", explanation)
        self.assertIn("Postgres connection string", next_step)
        self.assertFalse(metadata["database_connected"])

    @override_settings(CELERY_BEAT_RUNTIME_ENABLED=False)
    def test_check_celery_beat_reports_disabled_when_csharp_scheduler_owns_it(self):
        state, explanation, next_step, metadata = health.check_celery_beat()

        self.assertEqual(state, "disabled")
        self.assertIn("retired", explanation)
        self.assertFalse(metadata["runtime_enabled"])

    def test_check_slate_diversity_runtime_reports_plain_english_status(self):
        state, explanation, next_step, metadata = health.check_slate_diversity_runtime()

        self.assertIn(state, {"healthy", "degraded"})
        self.assertIn("FR-015 slate diversity", explanation)
        self.assertIn("runtime_path", metadata)
        self.assertIn("cpp_fast_path_active", metadata)
        self.assertIn("python_fallback_active", metadata)

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


class RuntimeConflictTests(TestCase):
    @override_settings(
        HTTP_WORKER_ENABLED=False,
        RUNTIME_OWNER_IMPORT="csharp",
        RUNTIME_OWNER_PIPELINE="csharp",
    )
    def test_detect_conflicts_flags_nonexistent_csharp_lane_owners(self):
        conflicts = health.detect_conflicts()
        titles = {conflict["title"] for conflict in conflicts}

        self.assertIn("C# Runtime Ownership Without HttpWorker", titles)
        self.assertIn("Import Lane Points At Nonexistent C# Owner", titles)
        self.assertIn("Pipeline Lane Points At Nonexistent C# Owner", titles)


@override_settings(SCHEDULER_CONTROL_TOKEN="scheduler-secret")
class SchedulerDispatchViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("apps.pipeline.tasks.dispatch_import_content", return_value={"job_id": "abc", "runtime_owner": "celery", "message": "queued"})
    def test_scheduler_dispatch_accepts_import_job_with_token(self, dispatch_import_content):
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
