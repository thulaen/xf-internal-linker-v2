"""Focused tests for the public import task wrapper."""
# pylint: disable=no-value-for-parameter
# Calls to pipeline_tasks.import_content(...) hit a Celery @shared_task(bind=True)
# wrapper; Celery supplies `self` at call time, so pylint's "missing self"
# error is a false positive for these test invocations.

from unittest.mock import patch

from django.test import TestCase
from requests.exceptions import ReadTimeout

from apps.pipeline import tasks as pipeline_tasks
from apps.sync.models import SyncJob


class ImportTaskWrapperTests(TestCase):
    def test_import_content_runs_existing_import_helpers(self):
        from apps.pipeline import tasks_import

        def fake_import(state, job, scope_ids, publish_progress):
            self.assertEqual(scope_ids, [1])
            self.assertEqual(job.status, "running")
            self.assertEqual(state.source, "api")
            publish_progress(state.job_id, "running", 0.5, "Half done")
            state.items_synced = 2
            state.items_updated = 1
            state.touched_scope_ids.add(99)

        with (
            patch.object(
                tasks_import,
                "import_xenforo_scopes",
                side_effect=fake_import,
            ),
            patch.object(tasks_import, "update_scope_counts") as update_counts,
            patch.object(tasks_import, "run_post_import_steps") as post_steps,
            patch.object(pipeline_tasks, "_publish_progress"),
            patch(
                "apps.pipeline.services.task_lock.acquire_task_lock",
                return_value=True,
            ),
            patch("apps.pipeline.services.task_lock.release_task_lock"),
        ):
            result = pipeline_tasks.import_content(
                scope_ids=[1],
                mode="full",
                source="api",
                job_id="11111111-1111-1111-1111-111111111111",
            )

        job = SyncJob.objects.get(job_id=result["job_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["items_synced"], 2)
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.progress, 100.0)
        self.assertEqual(job.items_updated, 1)
        update_counts.assert_called_once_with({99})
        post_steps.assert_called_once()

    def test_import_content_marks_missing_jsonl_file_as_failed(self):
        with (
            patch.object(pipeline_tasks, "_publish_progress"),
            patch(
                "apps.pipeline.services.task_lock.acquire_task_lock",
                return_value=True,
            ),
            patch("apps.pipeline.services.task_lock.release_task_lock"),
            self.assertRaisesMessage(
                ValueError,
                "JSONL imports require a saved file path.",
            ),
        ):
            pipeline_tasks.import_content(
                mode="full",
                source="jsonl",
                job_id="22222222-2222-2222-2222-222222222222",
            )

        job = SyncJob.objects.get(job_id="22222222-2222-2222-2222-222222222222")
        self.assertEqual(job.status, "failed")
        self.assertIn("JSONL imports require", job.error_message)

    def test_import_content_marks_pause_without_lower_checkpoint(self):
        from apps.core.pause_contract import JobPaused
        from apps.pipeline import tasks_import

        with (
            patch.object(
                tasks_import,
                "import_xenforo_scopes",
                side_effect=JobPaused("operator pause"),
            ),
            patch.object(pipeline_tasks, "_publish_progress"),
            patch(
                "apps.pipeline.services.task_lock.acquire_task_lock",
                return_value=True,
            ),
            patch("apps.pipeline.services.task_lock.release_task_lock"),
        ):
            result = pipeline_tasks.import_content(
                mode="full",
                source="api",
                job_id="33333333-3333-3333-3333-333333333333",
            )

        job = SyncJob.objects.get(job_id=result["job_id"])
        self.assertEqual(result["status"], "paused")
        self.assertEqual(job.status, "paused")
        self.assertIn("operator pause", job.message)

    def test_import_content_marks_external_timeout_failed_without_reraising(self):
        from apps.pipeline import tasks_import

        with (
            patch.object(
                tasks_import,
                "import_wordpress_content",
                side_effect=ReadTimeout("wp timed out"),
            ),
            patch.object(pipeline_tasks, "_publish_progress"),
            patch.object(pipeline_tasks.logger, "exception") as exception_log,
            patch.object(pipeline_tasks.logger, "warning") as warning_log,
            patch(
                "apps.pipeline.services.task_lock.acquire_task_lock",
                return_value=True,
            ),
            patch("apps.pipeline.services.task_lock.release_task_lock"),
        ):
            result = pipeline_tasks.import_content(
                mode="full",
                source="wp",
                job_id="44444444-4444-4444-4444-444444444444",
            )

        job = SyncJob.objects.get(job_id=result["job_id"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(job.status, "failed")
        self.assertIn("wp timed out", job.error_message)
        warning_log.assert_called_once()
        exception_log.assert_not_called()
