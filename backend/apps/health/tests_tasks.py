"""Convention-named SimpleTestCase coverage for apps/health/tasks.py.

Two behaviour rules are pinned here without touching the real database or any
network:

* Issues #1338 / #423 / #86: both Celery tasks close any stale DB connection
  before starting work, BUT only when not already inside an open transaction
  (atomic block). Closing inside an atomic block would detach the connection
  mid-transaction, so the guard ``if not connection.in_atomic_block`` must hold.
* The configured Celery time limits (120 / 90 and 60 / 45) are pinned with
  ``assertEqual`` so the diff-scoped mutation gate cannot keep a ``+1`` literal
  mutant alive (a ``>=`` assertion would still pass on 121).

The task body is aborted right after the guard by patching the first post-guard
collaborator (``HealthCheckRegistry`` / ``perform_health_check``) with a sentinel
exception, so NO real health probe, Redis, DB, or HTTP call runs and the
mutation gate cannot wedge.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class _StopAfterGuard(Exception):
    """Sentinel raised right after the connection guard to abort the body."""


class TimeLimitTests(SimpleTestCase):
    def test_run_all_time_limits_are_120_and_90(self) -> None:
        from apps.health.tasks import run_all_health_checks

        self.assertEqual(run_all_health_checks.time_limit, 120)
        self.assertEqual(run_all_health_checks.soft_time_limit, 90)

    def test_run_single_time_limits_are_60_and_45(self) -> None:
        from apps.health.tasks import run_single_health_check

        self.assertEqual(run_single_health_check.time_limit, 60)
        self.assertEqual(run_single_health_check.soft_time_limit, 45)


class RunAllConnectionGuardTests(SimpleTestCase):
    """run_all_health_checks closes the connection only outside an atomic block."""

    def _run(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.health import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block
        registry = MagicMock()
        registry.get_checkers.side_effect = _StopAfterGuard
        with patch.object(tasks, "connection", fake_conn), patch.object(
            tasks, "HealthCheckRegistry", registry
        ):
            with self.assertRaises(_StopAfterGuard):
                tasks.run_all_health_checks()
        return fake_conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn = self._run(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        fake_conn = self._run(in_atomic_block=False)
        fake_conn.close.assert_called_once()


class RunAllFailureBranchTests(SimpleTestCase):
    """Drive run_all_health_checks through one failing check.

    Pins the per-failure branch added on this diff (issues #1338/#423): the
    exact ``"FAILED_EXECUTION"`` marker, the ``had_failure`` flip that turns
    the return ``ok`` False, and the inner connection reset that fires once per
    failure only when outside an atomic block. Exact-value asserts kill the
    string, boolean, and dict-value mutants the diff-scoped gate would keep.
    """

    def _run(self, *, in_atomic_block: bool) -> tuple[dict, MagicMock]:
        from apps.health import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block
        registry = MagicMock()
        registry.get_checkers.return_value = {"postgres": object()}
        with patch.object(tasks, "connection", fake_conn), patch.object(
            tasks, "HealthCheckRegistry", registry
        ), patch.object(
            tasks, "perform_health_check", side_effect=RuntimeError("boom")
        ):
            result = tasks.run_all_health_checks()
        return result, fake_conn

    def test_when_check_raises_then_marked_failed_execution(self) -> None:
        result, _ = self._run(in_atomic_block=False)
        self.assertEqual(result["checks"], {"postgres": "FAILED_EXECUTION"})
        self.assertEqual(result["ok"], False)

    def test_failure_branch_closes_connection_once_outside_atomic(self) -> None:
        # One pre-start close + one per-failure close = exactly two closes.
        _, fake_conn = self._run(in_atomic_block=False)
        self.assertEqual(fake_conn.close.call_count, 2)

    def test_failure_branch_skips_close_inside_atomic(self) -> None:
        # Inside an atomic block neither the pre-start guard nor the per-failure
        # reset may close — exactly zero closes.
        _, fake_conn = self._run(in_atomic_block=True)
        self.assertEqual(fake_conn.close.call_count, 0)


class RunSingleConnectionGuardTests(SimpleTestCase):
    """run_single_health_check closes the connection only outside an atomic block."""

    def _run(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.health import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block
        with patch.object(tasks, "connection", fake_conn), patch.object(
            tasks, "perform_health_check", side_effect=_StopAfterGuard
        ):
            # The task catches Exception and returns an error dict, so no raise
            # escapes; the guard still ran and perform_health_check is the first
            # post-guard call, proving no real probe executed.
            result = tasks.run_single_health_check("postgres")
        self.assertEqual(result["status"], "error")
        return fake_conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn = self._run(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        fake_conn = self._run(in_atomic_block=False)
        fake_conn.close.assert_called_once()
