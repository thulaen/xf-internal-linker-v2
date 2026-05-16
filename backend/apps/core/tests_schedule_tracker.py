"""Tests for `apps.core.services.schedule_tracker` (sentient schedules).

Covers:
- `register_schedule` is idempotent on duplicate task_name
- `record_run` is idempotent on (task_name, scheduled_for)
- `find_missed_runs` returns slots with no row in the lookback window
- `recover_missed_runs` fires the callable + writes a 'pending' row
- The unique constraint on the model rejects duplicate (task_name, slot)
- `_is_schema_work_command` blocks schedule recovery during migrations
  (AutoIssue #272 regression)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase

from apps.core.apps import _is_schema_work_command
from apps.core.models import ScheduledTaskRun
from apps.core.services import schedule_tracker


class SchemaWorkGuardTests(SimpleTestCase):
    """Regression for AutoIssue #272 — schedule recovery must skip
    when the user is running schema work (migrate / makemigrations /
    sqlmigrate / showmigrations / squashmigrations).
    """

    def test_migrate_command_is_schema_work(self) -> None:
        self.assertTrue(_is_schema_work_command(["manage.py", "migrate"]))

    def test_migrate_with_app_is_schema_work(self) -> None:
        self.assertTrue(
            _is_schema_work_command(["manage.py", "migrate", "auto_issues"])
        )

    def test_makemigrations_is_schema_work(self) -> None:
        self.assertTrue(_is_schema_work_command(["manage.py", "makemigrations"]))

    def test_sqlmigrate_is_schema_work(self) -> None:
        self.assertTrue(
            _is_schema_work_command(["manage.py", "sqlmigrate", "auto_issues", "0001"])
        )

    def test_runserver_is_not_schema_work(self) -> None:
        self.assertFalse(_is_schema_work_command(["manage.py", "runserver"]))

    def test_test_is_not_schema_work(self) -> None:
        # The existing test-detection path handles 'test'; the new guard
        # must not double-trigger on it.
        self.assertFalse(_is_schema_work_command(["manage.py", "test"]))

    def test_empty_argv_is_not_schema_work(self) -> None:
        self.assertFalse(_is_schema_work_command([]))
        self.assertFalse(_is_schema_work_command(["manage.py"]))


def _noop_fire(slot: datetime) -> None:
    """Test helper — registered fire callables don't do real work in tests."""
    return None


class ScheduleRegistrationTests(TestCase):
    def setUp(self) -> None:
        # Reset module-level registry between tests so each starts clean.
        schedule_tracker._REGISTRY.clear()

    def test_register_then_list_returns_one_entry(self) -> None:
        schedule_tracker.register_schedule(
            "tests.foo",
            "0 9 * * *",
            _noop_fire,
            description="every morning at 9",
        )
        listed = schedule_tracker.list_registered()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["task_name"], "tests.foo")
        self.assertEqual(listed[0]["cron_expr"], "0 9 * * *")
        self.assertEqual(listed[0]["description"], "every morning at 9")

    def test_register_is_idempotent_on_duplicate_name(self) -> None:
        schedule_tracker.register_schedule("tests.foo", "0 9 * * *", _noop_fire)
        schedule_tracker.register_schedule("tests.foo", "*/5 * * * *", _noop_fire)
        listed = schedule_tracker.list_registered()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["cron_expr"], "*/5 * * * *")  # last write wins


class RecordRunTests(TestCase):
    def test_record_creates_row(self) -> None:
        slot = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        schedule_tracker.record_run(
            "tests.foo",
            slot,
            status="succeeded",
            started_at=slot,
            finished_at=slot + timedelta(seconds=10),
        )
        rows = ScheduledTaskRun.objects.filter(task_name="tests.foo")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows[0].status, "succeeded")

    def test_record_is_idempotent_on_same_slot(self) -> None:
        slot = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        schedule_tracker.record_run("tests.foo", slot, status="pending")
        schedule_tracker.record_run("tests.foo", slot, status="succeeded")
        rows = ScheduledTaskRun.objects.filter(task_name="tests.foo")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows[0].status, "succeeded")

    def test_unique_constraint_rejects_raw_duplicate_insert(self) -> None:
        slot = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        ScheduledTaskRun.objects.create(task_name="tests.foo", scheduled_for=slot)
        with self.assertRaises(IntegrityError):
            ScheduledTaskRun.objects.create(task_name="tests.foo", scheduled_for=slot)

    def test_recovered_run_flag_only_set_on_create(self) -> None:
        slot = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        schedule_tracker.record_run(
            "tests.foo", slot, status="pending", recovered_run=True
        )
        # Subsequent update must NOT clear the flag.
        schedule_tracker.record_run("tests.foo", slot, status="succeeded")
        row = ScheduledTaskRun.objects.get(task_name="tests.foo", scheduled_for=slot)
        self.assertTrue(row.recovered_run)
        self.assertEqual(row.status, "succeeded")


class RecoveryTests(TestCase):
    def setUp(self) -> None:
        schedule_tracker._REGISTRY.clear()

    def test_find_missed_returns_slots_without_a_row(self) -> None:
        # Register a daily-9am cron with a 72h lookback.
        schedule_tracker.register_schedule(
            "tests.daily", "0 9 * * *", _noop_fire, max_lookback_hours=72
        )
        # Frozen "now" so lookback covers exactly 3 expected slots.
        fake_now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
        missed = schedule_tracker.find_missed_runs(now=fake_now)
        # 3 days x daily = 3 missed slots.
        self.assertEqual(len(missed), 3)

    def test_find_missed_skips_slots_already_recorded(self) -> None:
        schedule_tracker.register_schedule(
            "tests.daily", "0 9 * * *", _noop_fire, max_lookback_hours=72
        )
        # Mark one slot as already done.
        schedule_tracker.record_run(
            "tests.daily",
            datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
            status="succeeded",
        )
        fake_now = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
        missed = schedule_tracker.find_missed_runs(now=fake_now)
        # Only 2 slots should still be missed.
        slots = [s for _, s in missed]
        self.assertEqual(len(missed), 2)
        self.assertNotIn(datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc), slots)

    def test_recover_fires_callable_and_writes_pending_row(self) -> None:
        fired: list[datetime] = []

        def _fire(slot: datetime) -> None:
            fired.append(slot)

        schedule_tracker.register_schedule(
            "tests.daily", "0 9 * * *", _fire, max_lookback_hours=24
        )
        fake_now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
        count = schedule_tracker.recover_missed_runs(now=fake_now)
        self.assertEqual(count, 1)
        self.assertEqual(len(fired), 1)
        # A `pending` row was written first so a parallel sweep can't double-fire.
        rows = ScheduledTaskRun.objects.filter(task_name="tests.daily")
        self.assertEqual(rows.count(), 1)
        self.assertTrue(rows[0].recovered_run)


class StatusForUiTests(TestCase):
    def setUp(self) -> None:
        schedule_tracker._REGISTRY.clear()

    def test_status_includes_recent_runs_and_next_run(self) -> None:
        schedule_tracker.register_schedule(
            "tests.daily",
            "0 9 * * *",
            _noop_fire,
            description="daily 9am",
        )
        slot = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        schedule_tracker.record_run("tests.daily", slot, status="succeeded")
        snapshot = schedule_tracker.get_status_for_ui()
        self.assertEqual(len(snapshot), 1)
        entry = snapshot[0]
        self.assertEqual(entry["task_name"], "tests.daily")
        self.assertEqual(entry["description"], "daily 9am")
        self.assertEqual(len(entry["recent_runs"]), 1)
        self.assertEqual(entry["recent_runs"][0]["status"], "succeeded")
        # next_run_at is computed by croniter; should be a non-None ISO string.
        self.assertIsNotNone(entry["next_run_at"])
