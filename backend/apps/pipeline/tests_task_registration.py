"""Regression tests for Celery task names used by beat schedules."""

from __future__ import annotations

from django.test import SimpleTestCase

from config.celery import app


class PipelineTaskRegistrationTests(SimpleTestCase):
    def test_legacy_prune_stale_data_task_is_registered(self) -> None:
        from apps.pipeline import tasks  # noqa: F401

        self.assertIn("pipeline.prune_stale_data", app.tasks)

    def test_disk_pressure_refresh_task_is_registered(self) -> None:
        from apps.pipeline import tasks_internal_health  # noqa: F401

        self.assertIn("pipeline.refresh_disk_pressure_state", app.tasks)
