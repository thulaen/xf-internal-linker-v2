"""Tests for the Redis-backed task locking service."""

from __future__ import annotations


from django.test import TestCase, override_settings

from apps.pipeline.services.task_lock import (
    acquire_task_lock,
    get_active_locks,
    is_lock_held,
    release_task_lock,
)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
class TaskLockTests(TestCase):
    """Test distributed task locking via Django cache."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()

    def test_light_tasks_always_acquire(self):
        assert acquire_task_lock("light", "some-task") is True
        # Second acquire also succeeds — no locking for light.
        assert acquire_task_lock("light", "another-task") is True

    def test_heavy_lock_exclusive(self):
        assert acquire_task_lock("heavy", "task-a") is True
        # Second heavy task cannot acquire.
        assert acquire_task_lock("heavy", "task-b") is False

    def test_release_allows_next_task(self):
        assert acquire_task_lock("heavy", "task-a") is True
        release_task_lock("heavy", "task-a")
        # Now task-b can acquire.
        assert acquire_task_lock("heavy", "task-b") is True

    def test_medium_lock_separate_from_heavy(self):
        assert acquire_task_lock("heavy", "heavy-task") is True
        # Medium uses a different key — can acquire independently.
        assert acquire_task_lock("medium", "medium-task") is True

    def test_get_active_locks_shows_holders(self):
        acquire_task_lock("heavy", "sync-job")
        locks = get_active_locks()
        assert locks["heavy"] is not None
        assert "sync-job" in locks["heavy"]
        assert locks["medium"] is None

    def test_is_lock_held(self):
        assert is_lock_held("heavy") is False
        acquire_task_lock("heavy", "task-a")
        assert is_lock_held("heavy") is True
        assert is_lock_held("light") is False  # light never held
