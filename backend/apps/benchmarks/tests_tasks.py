"""Convention-named SimpleTestCase coverage for apps/benchmarks/tasks.py.

Issue #86 follow-up: ``run_all_benchmarks`` closes a stale database connection
before it starts, but must skip that close when already inside a transaction
(an open atomic block).  Closing mid-transaction corrupts transaction state.
This test proves the guard both ways with a mocked connection so no real
benchmark work or database access happens.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

# pylint: disable=no-value-for-parameter
# The guard test calls the bound Celery task (@shared_task(bind=True)) directly
# as task(...); pylint mis-reads the bind signature and raises E1120, but Celery
# binds `self` at runtime and the test passes.


class _StopAfterGuard(Exception):
    """Sentinel used to abort the task body right after the connection guard."""


class RunAllBenchmarksConnectionGuardTests(SimpleTestCase):
    def _run_with_atomic(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.benchmarks import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block

        # _log_caller_diagnostics is the first call inside the body after the
        # connection guard runs, so raising there proves the guard executed
        # without touching the database or running any benchmark.
        with patch.object(tasks, "connection", fake_conn), patch.object(
            tasks, "_log_caller_diagnostics", side_effect=_StopAfterGuard
        ):
            with self.assertRaises(_StopAfterGuard):
                tasks.run_all_benchmarks(run_id=None, trigger="test")
        return fake_conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=False)
        fake_conn.close.assert_called_once()
