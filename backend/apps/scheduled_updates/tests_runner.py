"""Tests for the runner / window guard / lock / registry (PR-B.2)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from .lock import (
    RUNNER_LOCK_KEY,
    acquire_runner_lock,
    current_holder,
    release_runner_lock,
)
from .models import (
    JOB_PRIORITY_CRITICAL,
    JOB_PRIORITY_HIGH,
    JOB_PRIORITY_LOW,
    JOB_STATE_COMPLETED,
    JOB_STATE_FAILED,
    JOB_STATE_PAUSED,
    ScheduledJob,
)
from .registry import (
    JOB_REGISTRY,
    lookup,
    scheduled_job,
    unregister_for_test,
)
from .runner import (
    _execute_job,
    pick_next_job,
    run_next_scheduled_job,
)
from .window import (
    WINDOW_END_HOUR,
    WINDOW_START_HOUR,
    is_within_window,
    seconds_remaining_in_window,
    time_until_window_opens,
    would_overflow,
)


# ─────────────────────────────────────────────────────────────────────
# Fake Redis that covers the 3 operations our lock module actually uses.
# Enough for unit-level assertions; no need for the real redis in tests.
# ─────────────────────────────────────────────────────────────────────


class FakeRedis:
    """Minimal in-memory stand-in for redis.Redis.

    Implements ``set(key, value, nx=?, ex=?)``, ``get``, and ``eval``
    (for the safe-release Lua). Does NOT honour TTLs automatically —
    tests call ``expire_now`` to simulate elapsed time.
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    # redis.Redis signature uses positional (name, value, *, ex=None, nx=False, ...).
    def set(self, key, value, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = value.encode("utf-8") if isinstance(value, str) else value
        return True

    def get(self, key):
        return self._store.get(key)

    def eval(self, script, numkeys: int, *keys_and_args):
        # Only need to emulate the release Lua: if GET == token → DEL → 1 else 0.
        assert numkeys == 1, "tests only use numkeys=1 eval"
        key = keys_and_args[0]
        token = keys_and_args[1]
        token_bytes = token.encode("utf-8") if isinstance(token, str) else token
        if self._store.get(key) == token_bytes:
            del self._store[key]
            return 1
        return 0

    # Test-only helper.
    def expire_now(self, key: str) -> None:
        self._store.pop(key, None)


# ─────────────────────────────────────────────────────────────────────
# window.py
# ─────────────────────────────────────────────────────────────────────


class WindowGuardTests(TestCase):
    def _at(self, hour: int, minute: int = 0) -> dt.datetime:
        tz = ZoneInfo("UTC")
        return dt.datetime(2026, 4, 22, hour, minute, tzinfo=tz)

    def test_within_window_between_start_and_end(self) -> None:
        for hour in range(WINDOW_START_HOUR, WINDOW_END_HOUR):
            with self.subTest(hour=hour):
                assert is_within_window(self._at(hour)) is True

    def test_outside_window_before_start(self) -> None:
        for hour in range(0, WINDOW_START_HOUR):
            with self.subTest(hour=hour):
                assert is_within_window(self._at(hour)) is False

    def test_outside_window_at_or_after_end(self) -> None:
        for hour in (WINDOW_END_HOUR, 0, 3):
            with self.subTest(hour=hour):
                assert is_within_window(self._at(hour)) is False

    def test_would_overflow_true_when_finish_past_end(self) -> None:
        # 22:55 + 10 min job → finish at 23:05 → overflow.
        now = self._at(WINDOW_END_HOUR - 1, 55)
        assert would_overflow(600, now=now) is True

    def test_would_overflow_false_when_finish_before_end(self) -> None:
        # WINDOW_START_HOUR + 2 min job → finish 2 min later → safe.
        now = self._at(WINDOW_START_HOUR, 0)
        assert would_overflow(120, now=now) is False

    def test_would_overflow_true_when_window_already_closed(self) -> None:
        # Outside the window, even a 1-second job "overflows" because
        # it can't start at all.
        now = self._at(WINDOW_END_HOUR, 30)
        assert would_overflow(1, now=now) is True

    def test_time_until_window_opens_zero_when_open(self) -> None:
        # Pick the midpoint of the window so we're firmly inside it.
        midpoint = (WINDOW_START_HOUR + WINDOW_END_HOUR) // 2
        now = self._at(midpoint, 0)
        assert time_until_window_opens(now) == dt.timedelta(0)

    def test_time_until_window_opens_same_day_when_pre_window(self) -> None:
        # Two hours before the window opens.
        now = self._at(WINDOW_START_HOUR - 2, 0)
        delta = time_until_window_opens(now)
        assert delta == dt.timedelta(hours=2)

    def test_time_until_window_opens_next_day_when_post_window(self) -> None:
        # 30 min after the window closes → next open is the next day.
        now = self._at(WINDOW_END_HOUR, 30)
        delta = time_until_window_opens(now)
        # (WINDOW_END_HOUR : 30) → (WINDOW_START_HOUR : 00) next day
        # = (24 - WINDOW_END_HOUR) + WINDOW_START_HOUR hours, minus 30 min.
        expected_hours = (24 - WINDOW_END_HOUR) + WINDOW_START_HOUR - 1
        assert delta == dt.timedelta(hours=expected_hours, minutes=30)

    def test_seconds_remaining_in_window(self) -> None:
        now = self._at(WINDOW_END_HOUR - 1, 55)
        assert seconds_remaining_in_window(now) == 5 * 60

    def test_seconds_remaining_zero_outside_window(self) -> None:
        # 8 a.m. is before WINDOW_START_HOUR (11) so it's outside.
        now = self._at(8, 0)
        assert seconds_remaining_in_window(now) == 0


# ─────────────────────────────────────────────────────────────────────
# lock.py
# ─────────────────────────────────────────────────────────────────────


class RunnerLockTests(TestCase):
    def setUp(self) -> None:
        self.redis = FakeRedis()

    def test_acquire_on_empty_succeeds(self) -> None:
        token = acquire_runner_lock(self.redis, ttl_seconds=60)
        assert token is not None
        assert current_holder(self.redis) == token

    def test_acquire_while_held_returns_none(self) -> None:
        first = acquire_runner_lock(self.redis, ttl_seconds=60)
        second = acquire_runner_lock(self.redis, ttl_seconds=60)
        assert first is not None
        assert second is None

    def test_release_by_owner_frees_lock(self) -> None:
        token = acquire_runner_lock(self.redis, ttl_seconds=60)
        assert release_runner_lock(self.redis, token) is True
        assert current_holder(self.redis) is None

    def test_release_with_wrong_token_is_noop(self) -> None:
        token = acquire_runner_lock(self.redis, ttl_seconds=60)
        assert release_runner_lock(self.redis, "someone-elses-token") is False
        # Original holder still owns the lock.
        assert current_holder(self.redis) == token

    def test_release_when_lock_expired_does_not_nuke_next_holder(self) -> None:
        """Tests the regression the Lua guard was added for."""
        first = acquire_runner_lock(self.redis, ttl_seconds=60)
        self.redis.expire_now(RUNNER_LOCK_KEY)  # simulate TTL hit
        second = acquire_runner_lock(self.redis, ttl_seconds=60)
        # First holder now tries to release — must NOT drop second's lock.
        released = release_runner_lock(self.redis, first)
        assert released is False
        assert current_holder(self.redis) == second

    def test_acquire_with_zero_ttl_rejects(self) -> None:
        assert acquire_runner_lock(self.redis, ttl_seconds=0) is None


# ─────────────────────────────────────────────────────────────────────
# registry.py
# ─────────────────────────────────────────────────────────────────────


class RegistryTests(TestCase):
    def tearDown(self) -> None:
        unregister_for_test("registry-test-1")
        unregister_for_test("registry-test-2")

    def test_decorator_registers_and_looks_up(self) -> None:
        @scheduled_job(
            "registry-test-1",
            display_name="Registry test",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            checkpoint(progress_pct=50)

        defn = lookup("registry-test-1")
        assert defn is not None
        assert defn.display_name == "Registry test"
        assert defn.cadence_seconds == 86400

    def test_duplicate_key_raises(self) -> None:
        @scheduled_job(
            "registry-test-2",
            display_name="First",
            cadence_seconds=1,
            estimate_seconds=1,
        )
        def _a(job, checkpoint):
            pass

        with self.assertRaises(RuntimeError):

            @scheduled_job(
                "registry-test-2",
                display_name="Second — should fail",
                cadence_seconds=1,
                estimate_seconds=1,
            )
            def _b(job, checkpoint):
                pass

    def test_lookup_unknown_key_is_none(self) -> None:
        assert lookup("no-such-key-anywhere") is None


# ─────────────────────────────────────────────────────────────────────
# runner.py
# ─────────────────────────────────────────────────────────────────────


class PickNextJobTests(TestCase):
    def test_critical_beats_medium(self) -> None:
        low = ScheduledJob.objects.create(
            key="low-1",
            display_name="low",
            priority=JOB_PRIORITY_LOW,
        )
        crit = ScheduledJob.objects.create(
            key="crit-1",
            display_name="crit",
            priority=JOB_PRIORITY_CRITICAL,
        )
        high = ScheduledJob.objects.create(
            key="high-1",
            display_name="high",
            priority=JOB_PRIORITY_HIGH,
        )
        # Use a known mid-window moment so window-guard always passes.
        now = dt.datetime(2026, 4, 22, 15, 0, tzinfo=ZoneInfo("UTC"))
        picked = pick_next_job(now=now)
        assert picked is not None
        assert picked.pk == crit.pk

    def test_skips_overflowing_job(self) -> None:
        # Job that cannot finish before 23:00 is skipped in favour of
        # a smaller one further down the priority list.
        big = ScheduledJob.objects.create(
            key="big-overflow",
            display_name="big",
            priority=JOB_PRIORITY_CRITICAL,
            duration_estimate_sec=3600,
        )
        small = ScheduledJob.objects.create(
            key="small",
            display_name="small",
            priority=JOB_PRIORITY_LOW,
            duration_estimate_sec=60,
        )
        now = dt.datetime(2026, 4, 22, 22, 55, tzinfo=ZoneInfo("UTC"))
        picked = pick_next_job(now=now)
        assert picked is not None
        assert picked.pk == small.pk

    def test_returns_none_when_nothing_pending(self) -> None:
        ScheduledJob.objects.create(
            key="done-1",
            display_name="done",
            state=JOB_STATE_COMPLETED,
        )
        now = dt.datetime(2026, 4, 22, 15, 0, tzinfo=ZoneInfo("UTC"))
        assert pick_next_job(now=now) is None


class ExecuteJobTests(TestCase):
    def tearDown(self) -> None:
        unregister_for_test("exec-success")
        unregister_for_test("exec-fail")
        unregister_for_test("exec-pause")

    def test_completed_on_normal_return(self) -> None:
        @scheduled_job(
            "exec-success",
            display_name="success",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            checkpoint(progress_pct=50.0, message="halfway")
            return None

        job = ScheduledJob.objects.create(
            key="exec-success",
            display_name="success",
        )
        final = _execute_job(job, JOB_REGISTRY["exec-success"])
        job.refresh_from_db()

        assert final == JOB_STATE_COMPLETED
        assert job.state == JOB_STATE_COMPLETED
        assert job.last_success_at is not None
        assert job.progress_pct == 100.0
        assert job.finished_at is not None

    def test_failed_on_exception_with_traceback_in_log_tail(self) -> None:
        @scheduled_job(
            "exec-fail",
            display_name="fail",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            raise ValueError("boom for tests")

        job = ScheduledJob.objects.create(
            key="exec-fail",
            display_name="fail",
        )
        final = _execute_job(job, JOB_REGISTRY["exec-fail"])
        job.refresh_from_db()

        assert final == JOB_STATE_FAILED
        assert job.state == JOB_STATE_FAILED
        assert "boom for tests" in job.log_tail
        assert job.last_success_at is None

    def test_paused_when_pause_token_flips(self) -> None:
        @scheduled_job(
            "exec-pause",
            display_name="pause",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            # Flip the pause token from inside the entrypoint so the
            # next checkpoint call raises.
            ScheduledJob.objects.filter(pk=job.pk).update(pause_token=True)
            checkpoint(progress_pct=30)

        job = ScheduledJob.objects.create(
            key="exec-pause",
            display_name="pause",
        )
        final = _execute_job(job, JOB_REGISTRY["exec-pause"])
        job.refresh_from_db()

        assert final == JOB_STATE_PAUSED
        assert job.state == JOB_STATE_PAUSED
        assert job.last_success_at is None
        # finished_at stays None so the runner knows the job can resume.
        assert job.finished_at is None


class RunNextScheduledJobTests(TestCase):
    def setUp(self) -> None:
        self.redis = FakeRedis()

    def tearDown(self) -> None:
        unregister_for_test("task-success")
        unregister_for_test("task-unregistered")

    @patch("apps.scheduled_updates.runner._redis_client")
    @patch("apps.scheduled_updates.runner.would_overflow", return_value=False)
    @patch("apps.scheduled_updates.runner.is_within_window", return_value=True)
    def test_runs_next_pending_job_end_to_end(self, _mock_window, _mock_overflow, mock_redis):
        mock_redis.return_value = self.redis

        @scheduled_job(
            "task-success",
            display_name="task success",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            checkpoint(progress_pct=50.0)

        ScheduledJob.objects.create(
            key="task-success",
            display_name="task success",
            priority=JOB_PRIORITY_HIGH,
            duration_estimate_sec=60,
        )
        result = run_next_scheduled_job()

        assert result["status"] == "ran"
        assert result["final_state"] == JOB_STATE_COMPLETED
        # Lock was released (FakeRedis is empty again).
        assert current_holder(self.redis) is None

    @patch("apps.scheduled_updates.runner.is_within_window", return_value=False)
    def test_outside_window_skips(self, _mock_window):
        ScheduledJob.objects.create(
            key="whatever",
            display_name="whatever",
        )
        result = run_next_scheduled_job()
        assert result == {"status": "skipped", "reason": "outside_window"}

    @patch("apps.scheduled_updates.runner._redis_client")
    @patch("apps.scheduled_updates.runner.would_overflow", return_value=False)
    @patch("apps.scheduled_updates.runner.is_within_window", return_value=True)
    def test_lock_busy_returns_busy(self, _mock_window, _mock_overflow, mock_redis):
        mock_redis.return_value = self.redis
        # Pre-populate the lock as if another runner owns it.
        self.redis.set(RUNNER_LOCK_KEY, "someone-else", nx=True, ex=60)

        @scheduled_job(
            "task-success",
            display_name="task success",
            cadence_seconds=86400,
            estimate_seconds=60,
        )
        def _entry(job, checkpoint):
            raise AssertionError("should NOT run — lock is busy")

        ScheduledJob.objects.create(
            key="task-success",
            display_name="task success",
        )
        result = run_next_scheduled_job()
        assert result["status"] == "busy"
        assert "someone-else" in result["holder"]

    @patch("apps.scheduled_updates.runner._redis_client")
    @patch("apps.scheduled_updates.runner.would_overflow", return_value=False)
    @patch("apps.scheduled_updates.runner.is_within_window", return_value=True)
    def test_unregistered_key_marks_failed(self, _mock_window, _mock_overflow, mock_redis):
        mock_redis.return_value = self.redis
        # Deliberately no @scheduled_job for this key.
        ScheduledJob.objects.create(
            key="task-unregistered",
            display_name="unregistered",
        )
        result = run_next_scheduled_job()
        assert result["status"] == "skipped"
        assert result["reason"] == "unregistered_key"
        job = ScheduledJob.objects.get(key="task-unregistered")
        assert job.state == JOB_STATE_FAILED
