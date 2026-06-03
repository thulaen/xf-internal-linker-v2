"""Convention-named SimpleTestCase coverage for apps/analytics/tasks.py.

Issue #86 follow-up: the eight Celery tasks here close any stale database
connection before they start work, BUT only when they are not already inside
an open transaction.  Calling ``connection.close()`` while inside an atomic
block detaches the connection mid-transaction and corrupts the transaction
state, so the guard ``if not connection.in_atomic_block`` must hold.

These tests prove the conditional guard both ways on every task that carries
it, without touching the real database: the module-level ``connection`` object
is replaced with a mock and each task body's first real step is mocked so only
the guard runs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

# pylint: disable=no-value-for-parameter
# The *_guard_runs tests call bound Celery tasks (@shared_task(bind=True))
# directly as task(arg); pylint mis-reads the bind signature and raises E1120,
# but Celery binds `self` at runtime and these tests pass.


class _StopAfterGuard(Exception):
    """Sentinel raised right after the connection guard to abort the body."""


class ConnectionCloseGuardTests(SimpleTestCase):
    """The pre-work connection close must be skipped inside an atomic block."""

    def _run_scheduler_with_atomic(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.analytics import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block
        with patch.object(tasks, "connection", fake_conn), patch.object(
            tasks, "_queue_scheduled_sync", return_value={"sync_run_id": 1}
        ):
            tasks.schedule_ga4_telemetry_hourly()
        return fake_conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn = self._run_scheduler_with_atomic(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        fake_conn = self._run_scheduler_with_atomic(in_atomic_block=False)
        fake_conn.close.assert_called_once()


class AllTasksGuardCoverageTests(SimpleTestCase):
    """Exercise the connection guard line in every task that carries one.

    Each task is run with a mocked connection (in_atomic_block=False so the
    close fires and the guarded line is executed) and its first real body step
    mocked so no benchmark, sync, or DB work runs.
    """

    def _conn(self) -> MagicMock:
        c = MagicMock()
        c.in_atomic_block = False
        return c

    def test_sync_matomo_telemetry_guard_runs(self) -> None:
        from apps.analytics import tasks

        conn = self._conn()
        with patch.object(tasks, "connection", conn), patch.object(
            tasks, "_load_sync_run", side_effect=_StopAfterGuard
        ):
            with self.assertRaises(_StopAfterGuard):
                tasks.sync_matomo_telemetry(1)
        conn.close.assert_called_once()

    def test_sync_ga4_telemetry_guard_runs(self) -> None:
        from apps.analytics import tasks

        conn = self._conn()
        with patch.object(tasks, "connection", conn), patch.object(
            tasks, "_load_sync_run", side_effect=_StopAfterGuard
        ):
            with self.assertRaises(_StopAfterGuard):
                tasks.sync_ga4_telemetry(1)
        conn.close.assert_called_once()

    def test_sync_gsc_performance_guard_runs(self) -> None:
        from apps.analytics import tasks

        conn = self._conn()
        with patch.object(tasks, "connection", conn), patch.object(
            tasks, "_load_sync_run", side_effect=_StopAfterGuard
        ):
            with self.assertRaises(_StopAfterGuard):
                tasks.sync_gsc_performance(1)
        conn.close.assert_called_once()

    def test_schedule_ga4_daily_guard_runs(self) -> None:
        from apps.analytics import tasks

        conn = self._conn()
        with patch.object(tasks, "connection", conn), patch.object(
            tasks, "_queue_scheduled_sync", return_value={}
        ):
            tasks.schedule_ga4_telemetry_daily()
        conn.close.assert_called_once()

    def test_schedule_matomo_hourly_guard_runs(self) -> None:
        from apps.analytics import tasks

        conn = self._conn()
        with patch.object(tasks, "connection", conn), patch.object(
            tasks, "_queue_scheduled_sync", return_value={}
        ):
            tasks.schedule_matomo_telemetry_hourly()
        conn.close.assert_called_once()

    def test_schedule_matomo_daily_guard_runs(self) -> None:
        from apps.analytics import tasks

        conn = self._conn()
        with patch.object(tasks, "connection", conn), patch.object(
            tasks, "_queue_scheduled_sync", return_value={}
        ):
            tasks.schedule_matomo_telemetry_daily()
        conn.close.assert_called_once()

    def test_schedule_gsc_daily_guard_runs(self) -> None:
        from apps.analytics import tasks

        conn = self._conn()
        with patch.object(tasks, "connection", conn), patch.object(
            tasks, "_queue_scheduled_sync", return_value={}
        ), patch(
            "apps.analytics.views.get_gsc_settings", return_value={}
        ):
            tasks.schedule_gsc_performance_daily()
        conn.close.assert_called_once()

    def test_refresh_gsc_query_tfidf_guard_runs(self) -> None:
        from apps.analytics import tasks

        conn = self._conn()
        with patch.object(tasks, "connection", conn), patch(
            "apps.analytics.gsc_query_vocab.refresh_gsc_query_tfidf",
            return_value={},
        ):
            tasks.refresh_gsc_query_tfidf(lookback_days=1)
        conn.close.assert_called_once()

    def test_recompute_all_search_impact_guard_runs(self) -> None:
        from apps.analytics import tasks

        conn = self._conn()
        suggestion_cls = MagicMock()
        suggestion_cls.objects.filter.return_value = []
        with patch.object(tasks, "connection", conn), patch(
            "apps.suggestions.models.Suggestion", suggestion_cls
        ):
            result = tasks.recompute_all_search_impact()
        self.assertEqual(result, {"processed_suggestions": 0})
        conn.close.assert_called_once()

    def test_detect_traffic_spikes_guard_runs(self) -> None:
        from apps.analytics import tasks

        conn = self._conn()
        # SearchMetric is the first body query after the guard; returning no
        # latest metric makes the task return immediately, so the guard runs
        # without touching the real database, network, or alert path.
        metric_cls = MagicMock()
        metric_cls.objects.filter.return_value.order_by.return_value.first.return_value = (
            None
        )
        with patch.object(tasks, "connection", conn), patch(
            "apps.analytics.models.SearchMetric", metric_cls
        ):
            result = tasks.detect_traffic_spikes()
        self.assertEqual(result, {"alerts_emitted": 0})
        conn.close.assert_called_once()
