"""Convention-named SimpleTestCase coverage for apps/observability/tasks.py.

The two Celery tasks here close any stale database connection before they
start work, BUT only when they are not already inside an open transaction
(atomic block). Calling ``connection.close()`` inside an atomic block detaches
the connection mid-transaction and corrupts it, so the guard
``if not connection.in_atomic_block`` must hold both ways.

These tests prove the guard without touching the real database, Redis, or
Celery: the module-level ``connection`` object is replaced with a mock, and the
first real post-guard step is patched to abort the body so no live work runs
(which would otherwise wedge the mutation gate, since each mutant re-runs the
body).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class _StopAfterGuard(Exception):
    """Sentinel raised right after the connection guard to abort the body."""


class DetectObservabilityGapsGuardTests(SimpleTestCase):
    """detect_observability_gaps must skip the pre-work close in an atomic block."""

    def _run_with_atomic(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.observability import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block
        # The first post-guard statement imports and calls the gap detector
        # service. Patch that service so the body aborts immediately and no
        # AutoIssue dedup / DB write runs.
        with patch.object(tasks, "connection", fake_conn), patch(
            "apps.observability.services.gap_detector.detect_observability_gaps",
            side_effect=_StopAfterGuard,
        ):
            with self.assertRaises(_StopAfterGuard):
                tasks.detect_observability_gaps()
        return fake_conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=False)
        fake_conn.close.assert_called_once()


class CollectSystemMetricsGuardTests(SimpleTestCase):
    """collect_system_metrics carries the same connection guard and a fixed body."""

    def _run_with_atomic(self, *, in_atomic_block: bool) -> tuple[MagicMock, dict]:
        from apps.observability import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block
        with patch.object(tasks, "connection", fake_conn):
            result = tasks.collect_system_metrics()
        return fake_conn, result

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn, _ = self._run_with_atomic(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_and_payload_exact_when_not_in_atomic_block(self) -> None:
        # assertEqual on the exact dict kills the literal mutation of the
        # returned ``{"collected": True}`` payload (a substring check would let
        # a flipped boolean survive).
        fake_conn, result = self._run_with_atomic(in_atomic_block=False)
        fake_conn.close.assert_called_once()
        self.assertEqual(result, {"collected": True})
