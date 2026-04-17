"""
Tests for Phase SEQ — sequential execution lock for ranking signals.

Covers:
- `signal` weight class acquired and released atomically.
- Second acquirer is rejected while the first holds.
- `get_active_locks()` includes the `signal` class key (with None when
  free, owner string when held).
- `with_signal_lock()` decorator calls retry on contention and releases
  the lock in the finally branch.
- SignalQueueView exposes the current holder over HTTP.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.pipeline.decorators import with_signal_lock
from apps.pipeline.services.task_lock import (
    acquire_task_lock,
    get_active_locks,
    is_lock_held,
    release_task_lock,
)


class SignalLockServiceTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_signal_weight_class_acquired_and_released(self):
        self.assertFalse(is_lock_held("signal"))
        self.assertTrue(acquire_task_lock("signal", "test_task"))
        self.assertTrue(is_lock_held("signal"))
        release_task_lock("signal", "test_task")
        self.assertFalse(is_lock_held("signal"))

    def test_second_acquirer_rejected_while_held(self):
        self.assertTrue(acquire_task_lock("signal", "first"))
        self.assertFalse(acquire_task_lock("signal", "second"))
        release_task_lock("signal", "first")

    def test_get_active_locks_includes_signal(self):
        locks = get_active_locks()
        self.assertIn("signal", locks)
        self.assertIsNone(locks["signal"])
        acquire_task_lock("signal", "probe")
        locks = get_active_locks()
        self.assertIsNotNone(locks["signal"])
        self.assertIn("probe", str(locks["signal"]))
        release_task_lock("signal", "probe")

    def test_release_ignores_wrong_owner(self):
        self.assertTrue(acquire_task_lock("signal", "task_a"))
        # Unrelated task tries to release — should be a no-op (warns).
        release_task_lock("signal", "task_b")
        self.assertTrue(is_lock_held("signal"))
        release_task_lock("signal", "task_a")
        self.assertFalse(is_lock_held("signal"))


class WithSignalLockDecoratorTests(TestCase):
    """Proves the decorator composes with the Celery bind=True pattern."""

    def setUp(self) -> None:
        cache.clear()

    def test_runs_underlying_function_when_lock_free(self):
        @with_signal_lock()
        def compute(self, value: int) -> int:  # noqa: N805
            return value * 2

        fake_task = mock.Mock()
        result = compute(fake_task, 5)
        self.assertEqual(result, 10)
        # Lock released after successful run.
        self.assertFalse(is_lock_held("signal"))

    def test_releases_lock_even_on_exception(self):
        @with_signal_lock()
        def compute(self):  # noqa: N805
            raise RuntimeError("signal compute blew up")

        fake_task = mock.Mock()
        with self.assertRaises(RuntimeError):
            compute(fake_task)
        self.assertFalse(is_lock_held("signal"))

    def test_retries_when_lock_held(self):
        # Simulate the lock being held by another worker.
        acquire_task_lock("signal", "the_other_task")

        @with_signal_lock()
        def compute(self):  # noqa: N805
            return "never runs"

        fake_task = mock.Mock()
        fake_task.retry.side_effect = StopIteration  # sentinel to bail out

        with self.assertRaises(StopIteration):
            compute(fake_task)
        # retry was called with SEQ's 30s cadence + 120 max_retries.
        fake_task.retry.assert_called_once()
        kwargs = fake_task.retry.call_args.kwargs
        self.assertEqual(kwargs["countdown"], 30)
        self.assertEqual(kwargs["max_retries"], 120)

        release_task_lock("signal", "the_other_task")


class SignalQueueViewTests(TestCase):
    """The REST endpoint that powers the Mission Critical ranking-signals tile."""

    def setUp(self) -> None:
        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_user(username="seq-view", password="x")
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

    def test_signal_queue_returns_empty_when_idle(self):
        resp = self.client_api.get(reverse("signal-queue"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data["running"])
        self.assertEqual(resp.data["queued"], [])
        self.assertEqual(resp.data["lock_class"], "signal")

    def test_signal_queue_reports_holder(self):
        acquire_task_lock("signal", "compute_signal_authority")
        try:
            resp = self.client_api.get(reverse("signal-queue"))
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertIsNotNone(resp.data["running"])
            self.assertIn("compute_signal_authority", str(resp.data["running"]))
        finally:
            release_task_lock("signal", "compute_signal_authority")
