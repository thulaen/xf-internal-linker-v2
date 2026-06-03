"""Convention-named SimpleTestCase coverage for apps/core/tasks.py.

Issue #86 follow-up: the system-level Celery tasks here close any stale
database connection before they start work, BUT only when they are not already
inside an open transaction. Calling ``connection.close()`` inside an atomic
block detaches the connection mid-transaction and corrupts the transaction
state, so the guard ``if not connection.in_atomic_block`` must hold both ways.

Each task imports ``connection`` locally with ``from django.db import
connection``, so we patch ``django.db.connection`` (the real import target) and
abort the body at its first post-guard statement so NO real database, Redis,
or alert call runs and the mutation gate never hangs.

The numeric-literal test pins ``CHECKPOINT_PRUNE_ALERT_THRESHOLD`` with
``assertEqual`` (not ``>=``) so the diff-scoped mutation gate's +1 mutant
(100 -> 101) is killed rather than left alive.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core import tasks


class _StopAfterGuard(Exception):
    """Sentinel raised right after the connection guard to abort the body."""


def _fake_conn(*, in_atomic_block: bool) -> MagicMock:
    conn = MagicMock()
    conn.in_atomic_block = in_atomic_block
    return conn


class CheckpointThresholdLiteralTests(SimpleTestCase):
    # assertEqual (not assertGreaterEqual): the mutation gate mutates the
    # `CHECKPOINT_PRUNE_ALERT_THRESHOLD = 100` literal to 101; a `>= 100`
    # assertion would still pass on 101 and leave that mutant alive, blocking
    # the gate. Pinning the exact value kills it.
    def test_checkpoint_prune_alert_threshold_is_100(self) -> None:
        self.assertEqual(tasks.CHECKPOINT_PRUNE_ALERT_THRESHOLD, 100)

    def test_night_revert_hour_is_6(self) -> None:
        self.assertEqual(tasks.NIGHT_REVERT_HOUR, 6)


class AutoRevertConnectionGuardTests(SimpleTestCase):
    """auto_revert_performance_mode close-guard fires only outside atomic."""

    def _run(self, *, in_atomic_block: bool) -> MagicMock:
        conn = _fake_conn(in_atomic_block=in_atomic_block)
        app_setting = MagicMock()
        # First post-guard statement is `_get_setting(AppSetting, ...)`, which
        # calls AppSetting.objects.filter(...). Abort there so no DB runs.
        app_setting.objects.filter.side_effect = _StopAfterGuard
        with patch("django.db.connection", conn), patch(
            "apps.core.models.AppSetting", app_setting
        ):
            # The task wraps its body in `try/except Exception`, so the sentinel
            # is swallowed; we only assert the guard's close behaviour.
            tasks.auto_revert_performance_mode()
        return conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=True)
        conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=False)
        conn.close.assert_called_once()


class PruneStaleCheckpointsConnectionGuardTests(SimpleTestCase):
    """prune_stale_checkpoints close-guard fires only outside atomic."""

    def _run(self, *, in_atomic_block: bool) -> MagicMock:
        conn = _fake_conn(in_atomic_block=in_atomic_block)
        sync_job = MagicMock()
        # First post-guard model access is SyncJob.objects.filter(...); abort.
        sync_job.objects.filter.side_effect = _StopAfterGuard
        with patch("django.db.connection", conn), patch(
            "apps.sync.models.SyncJob", sync_job
        ):
            with self.assertRaises(_StopAfterGuard):
                tasks.prune_stale_checkpoints()
        return conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=True)
        conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=False)
        conn.close.assert_called_once()


class PruneSupersededEmbeddingsConnectionGuardTests(SimpleTestCase):
    """prune_superseded_embeddings close-guard fires only outside atomic."""

    def _run(self, *, in_atomic_block: bool) -> MagicMock:
        conn = _fake_conn(in_atomic_block=in_atomic_block)
        # First post-guard call is prune_verified_rows(); abort there.
        with patch("django.db.connection", conn), patch(
            "apps.content.supersede.prune_verified_rows",
            side_effect=_StopAfterGuard,
        ):
            # Body wraps the call in try/except Exception, so the sentinel is
            # swallowed and the task returns its failure dict.
            tasks.prune_superseded_embeddings()
        return conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=True)
        conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=False)
        conn.close.assert_called_once()


class ResumeAfterWakeConnectionGuardTests(SimpleTestCase):
    """resume_after_wake close-guard fires only outside atomic."""

    def _run(self, *, in_atomic_block: bool) -> MagicMock:
        conn = _fake_conn(in_atomic_block=in_atomic_block)
        app_setting = MagicMock()
        # First post-guard model access is AppSetting.objects.filter(...).
        app_setting.objects.filter.side_effect = _StopAfterGuard
        with patch("django.db.connection", conn), patch(
            "apps.core.models.AppSetting", app_setting
        ):
            # Body wraps work in try/except Exception, so the sentinel is
            # swallowed and the task returns its error dict.
            tasks.resume_after_wake()
        return conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=True)
        conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=False)
        conn.close.assert_called_once()


class ActivityResumedRevertConnectionGuardTests(SimpleTestCase):
    """activity_resumed_revert close-guard fires only outside atomic."""

    def _run(self, *, in_atomic_block: bool) -> MagicMock:
        conn = _fake_conn(in_atomic_block=in_atomic_block)
        app_setting = MagicMock()
        # First post-guard statement is `_get_setting(AppSetting, ...)`.
        app_setting.objects.filter.side_effect = _StopAfterGuard
        with patch("django.db.connection", conn), patch(
            "apps.core.models.AppSetting", app_setting
        ):
            tasks.activity_resumed_revert()
        return conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=True)
        conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        conn = self._run(in_atomic_block=False)
        conn.close.assert_called_once()
