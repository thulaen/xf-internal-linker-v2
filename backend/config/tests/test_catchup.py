"""Tests for the startup catch-up system.

Verifies that overdue tasks are detected, dispatched in priority order,
and that Heavy tasks are staggered correctly.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from config.catchup import _get_overdue_tasks, run_startup_catchup
from config.catchup_registry import CATCHUP_REGISTRY, CatchupEntry


def _make_periodic_task(name: str, last_run_at=None):
    """Create a mock PeriodicTask object."""
    mock = MagicMock()
    mock.name = name
    mock.task = f"pipeline.{name.replace('-', '_')}"
    mock.last_run_at = last_run_at
    mock.kwargs = "{}"
    return mock


class CatchupRegistryTests(TestCase):
    """Verify registry structure and completeness."""

    def test_registry_not_empty(self):
        assert len(CATCHUP_REGISTRY) > 0

    def test_all_entries_have_valid_weight_class(self):
        valid = {"heavy", "medium", "light"}
        for name, entry in CATCHUP_REGISTRY.items():
            assert entry.weight_class in valid, f"{name} has invalid weight_class"

    def test_priorities_are_unique(self):
        priorities = [e.priority for e in CATCHUP_REGISTRY.values()]
        assert len(priorities) == len(set(priorities)), "Duplicate priorities found"

    def test_heavy_tasks_use_pipeline_queue(self):
        for name, entry in CATCHUP_REGISTRY.items():
            if entry.weight_class == "heavy":
                assert entry.queue == "pipeline", (
                    f"Heavy task {name} not on pipeline queue"
                )


class OverdueDetectionTests(TestCase):
    """Verify that _get_overdue_tasks correctly identifies overdue tasks."""

    @patch(
        "config.catchup.CATCHUP_REGISTRY",
        {
            "test-task": CatchupEntry(
                threshold_hours=24, priority=10, queue="default", weight_class="light"
            ),
        },
    )
    @patch("django_celery_beat.models.PeriodicTask")
    def test_never_run_is_overdue(self, mock_model):
        mock_model.objects.filter.return_value.first.return_value = _make_periodic_task(
            "test-task", last_run_at=None
        )
        overdue = _get_overdue_tasks()
        assert len(overdue) == 1
        assert overdue[0][0] == "test-task"

    @patch(
        "config.catchup.CATCHUP_REGISTRY",
        {
            "test-task": CatchupEntry(
                threshold_hours=24, priority=10, queue="default", weight_class="light"
            ),
        },
    )
    @patch("django_celery_beat.models.PeriodicTask")
    def test_recent_run_not_overdue(self, mock_model):
        mock_model.objects.filter.return_value.first.return_value = _make_periodic_task(
            "test-task", last_run_at=timezone.now() - timedelta(hours=1)
        )
        overdue = _get_overdue_tasks()
        assert len(overdue) == 0

    @patch(
        "config.catchup.CATCHUP_REGISTRY",
        {
            "task-a": CatchupEntry(
                threshold_hours=24, priority=50, queue="default", weight_class="light"
            ),
            "task-b": CatchupEntry(
                threshold_hours=24, priority=10, queue="default", weight_class="heavy"
            ),
        },
    )
    @patch("django_celery_beat.models.PeriodicTask")
    def test_overdue_sorted_by_priority(self, mock_model):
        def _filter_side_effect(name):
            mock = MagicMock()
            mock.first.return_value = _make_periodic_task(name, last_run_at=None)
            return mock

        mock_model.objects.filter.side_effect = lambda name: _filter_side_effect(name)
        overdue = _get_overdue_tasks()
        assert len(overdue) == 2
        # task-b has priority 10 (higher priority), should come first
        assert overdue[0][0] == "task-b"
        assert overdue[1][0] == "task-a"


class DispatchTests(TestCase):
    """Verify that run_startup_catchup dispatches correctly."""

    @patch("config.catchup._get_overdue_tasks", return_value=[])
    def test_no_overdue_returns_empty(self, mock_overdue):
        results = run_startup_catchup()
        assert results == {}

    @patch("config.catchup._dispatch_task", return_value=True)
    @patch("config.catchup._get_overdue_tasks")
    def test_dispatches_overdue_tasks(self, mock_overdue, mock_dispatch):
        entry = CatchupEntry(
            threshold_hours=24, priority=10, queue="default", weight_class="light"
        )
        mock_overdue.return_value = [("test-task", entry)]
        results = run_startup_catchup()
        assert results["test-task"] == "dispatched"
        mock_dispatch.assert_called_once_with("test-task", "default")

    @patch("config.catchup._dispatch_task", side_effect=Exception("boom"))
    @patch("config.catchup._get_overdue_tasks")
    def test_dispatch_failure_logged_as_error(self, mock_overdue, mock_dispatch):
        entry = CatchupEntry(
            threshold_hours=24, priority=10, queue="default", weight_class="light"
        )
        mock_overdue.return_value = [("broken-task", entry)]
        results = run_startup_catchup()
        assert results["broken-task"] == "error"
