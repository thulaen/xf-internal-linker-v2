"""Convention-named SimpleTestCase coverage for apps/crawler/tasks.py.

Two behaviour changes are pinned here:

* Issue #317: ``pulse_heartbeat`` and ``watchdog_check`` raised their Celery
  time limits from 30 s / 20 s to 60 s / 50 s.  With several workers the
  Celery ``inspect`` call alone can take many seconds, so 30 s hit
  ``TimeLimitExceeded`` under normal load.  These tests pin the new floor.
* Issue #86: both tasks close a stale database connection before work, but
  only when not already inside an open transaction (atomic block).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class HeartbeatTimeLimitTests(SimpleTestCase):
    # assertEqual (not assertGreaterEqual): the diff-scoped mutation gate mutates
    # the `time_limit=60` / `soft_time_limit=50` literals to 61 / 51, and a
    # `>= 60` assertion would still pass on 61 — leaving that mutant alive and
    # blocking the gate. Pinning the exact configured value kills it and
    # documents the real Issue #317 limit.
    def test_pulse_heartbeat_time_limits_are_60_and_50(self) -> None:
        from apps.crawler.tasks import pulse_heartbeat

        self.assertEqual(pulse_heartbeat.time_limit, 60)
        self.assertEqual(pulse_heartbeat.soft_time_limit, 50)

    def test_watchdog_check_time_limits_are_60_and_50(self) -> None:
        from apps.crawler.tasks import watchdog_check

        self.assertEqual(watchdog_check.time_limit, 60)
        self.assertEqual(watchdog_check.soft_time_limit, 50)


class WatchdogConnectionGuardTests(SimpleTestCase):
    """watchdog_check must skip the pre-work close inside an atomic block."""

    def _run_with_atomic(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.crawler import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block

        sync_job_cls = MagicMock()
        sync_job_cls.objects.filter.return_value = []
        crawl_session_cls = MagicMock()
        crawl_session_cls.objects.filter.return_value = []

        with patch.object(tasks, "connection", fake_conn), patch(
            "apps.sync.models.SyncJob", sync_job_cls
        ), patch("apps.crawler.models.CrawlSession", crawl_session_cls), patch(
            "apps.crawler.models.SystemEvent", MagicMock()
        ), patch(
            "apps.notifications.services.emit_operator_alert", MagicMock()
        ):
            try:
                tasks.watchdog_check()
            except Exception:
                # The guard runs before any branch that could raise; we only
                # assert on the connection close behaviour below.
                pass
        return fake_conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=False)
        fake_conn.close.assert_called_once()


class _StopAfterGuard(Exception):
    """Sentinel raised right after the connection guard to abort the body."""


class PulseHeartbeatConnectionGuardTests(SimpleTestCase):
    """pulse_heartbeat must skip the pre-work close inside an atomic block."""

    def _run_with_atomic(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.crawler import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block

        # Abort the body at its first post-guard statement, `ts = time.time()`,
        # by making time.time() raise. This proves the connection guard ran while
        # NONE of the probe body executes — the real Redis ping, the Celery
        # `inspect(timeout=2.0)`, and `realtime_broadcast` would otherwise make
        # live network calls and hang the mutation gate (each mutant re-runs the
        # body). assertRaises confirms we stopped exactly at the guard boundary.
        fake_time = MagicMock()
        fake_time.time.side_effect = _StopAfterGuard
        with patch.object(tasks, "connection", fake_conn), patch.object(
            tasks, "time", fake_time
        ):
            with self.assertRaises(_StopAfterGuard):
                tasks.pulse_heartbeat()
        return fake_conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=False)
        fake_conn.close.assert_called_once()
