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
        # Patch the three best-effort emit helpers so the guard test stays
        # hermetic — no real psutil / Redis / Postgres work runs here.
        with patch.object(tasks, "connection", fake_conn), patch.object(
            tasks, "_emit_system_gauges", return_value={"ok": 1}
        ), patch.object(
            tasks, "_emit_db_latency", return_value=0.001
        ), patch.object(
            tasks, "_emit_queue_depth", return_value={"default": 0.0}
        ):
            result = tasks.collect_system_metrics()
        return fake_conn, result

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn, _ = self._run_with_atomic(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_and_payload_exact_when_not_in_atomic_block(self) -> None:
        # assertEqual on the exact dict pins the collected payload so a dropped
        # source or a renamed key is caught.
        fake_conn, result = self._run_with_atomic(in_atomic_block=False)
        fake_conn.close.assert_called_once()
        self.assertEqual(
            result,
            {"collected": {"system": {"ok": 1}, "db_latency_s": 0.001, "queues": {"default": 0.0}}},
        )


class HelperConstraintMetadataTests(SimpleTestCase):
    """Both tasks must carry the ``@HelperConstraint`` routing metadata.

    The decorator stashes a ``_ConstraintMeta`` on the wrapped callable so the
    helper-machine router can decide where to run the task. Pre-change neither
    task carried this metadata; the change declares both as light, CPU-only,
    Postgres-writing tasks with a 128 MB peak. These tests pin the exact
    declared values so a future edit that drops the decorator or flips a flag
    is caught.
    """

    def _meta(self, task) -> object:
        # The constraint lives on the inner callable that Celery wraps.
        return getattr(task.run, "__helper_constraint__", None)

    def test_detect_gaps_constraint_values(self) -> None:
        from apps.observability import tasks

        meta = self._meta(tasks.detect_observability_gaps)
        self.assertIsNotNone(meta, "detect_observability_gaps lost its @HelperConstraint")
        self.assertFalse(meta.cpu_intensive)
        self.assertFalse(meta.gpu_required)
        self.assertEqual(meta.storage_writes_to, "postgres_main")
        self.assertEqual(meta.ram_peak_mb, 128)

    def test_collect_system_metrics_constraint_values(self) -> None:
        from apps.observability import tasks

        meta = self._meta(tasks.collect_system_metrics)
        self.assertIsNotNone(meta, "collect_system_metrics lost its @HelperConstraint")
        self.assertFalse(meta.cpu_intensive)
        self.assertFalse(meta.gpu_required)
        self.assertEqual(meta.storage_writes_to, "postgres_main")
        self.assertEqual(meta.ram_peak_mb, 128)

    def test_constraint_resolvable_via_get_constraint_by_task_name(self) -> None:
        from apps.core.helpers import get_constraint
        from apps.observability import tasks

        for task in (tasks.detect_observability_gaps, tasks.collect_system_metrics):
            resolved = get_constraint(task.name)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.storage_writes_to, "postgres_main")
            self.assertEqual(resolved.ram_peak_mb, 128)
