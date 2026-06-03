"""Convention-named SimpleTestCase coverage for apps/notifications/tasks.py.

Issue #86 follow-up: the schedule check tasks (``check_zero_suggestion_run``,
``check_post_link_regression``, ``check_autotune_status``) close a stale
database connection before they start, but must skip that close when already
inside a transaction (an open atomic block) — closing mid-transaction corrupts
the transaction state.  This test proves the guard both ways on
``check_zero_suggestion_run`` while mocking the connection and the two ORM
models the body reads, so no real database access happens.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class CheckZeroSuggestionRunConnectionGuardTests(SimpleTestCase):
    def _run_with_atomic(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.notifications import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block

        pipeline_run_cls = MagicMock()
        pipeline_run_cls.objects.filter.return_value.order_by.return_value.first.return_value = (
            None
        )
        content_item_cls = MagicMock()
        content_item_cls.objects.count.return_value = 0

        with patch.object(tasks, "connection", fake_conn), patch(
            "apps.suggestions.models.PipelineRun", pipeline_run_cls
        ), patch("apps.content.models.ContentItem", content_item_cls):
            tasks.check_zero_suggestion_run()
        return fake_conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=False)
        fake_conn.close.assert_called_once()


class _StopAfterGuard(Exception):
    """Sentinel raised right after the connection guard to abort the body."""


class OtherCheckTasksConnectionGuardTests(SimpleTestCase):
    """check_post_link_regression and check_autotune_status carry the same guard."""

    def _run(self, task_name: str, *, in_atomic_block: bool) -> MagicMock:
        from apps.notifications import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block
        task = getattr(tasks, task_name)

        # Both bodies' first real step is a local model import + query; patch the
        # source models so the guard runs and then the body short-circuits.
        with patch.object(tasks, "connection", fake_conn), patch(
            "apps.analytics.models.ImpactReport",
            MagicMock(side_effect=_StopAfterGuard),
        ), patch(
            "apps.suggestions.models.RankingChallenger",
            MagicMock(side_effect=_StopAfterGuard),
        ):
            try:
                task()
            except Exception:
                pass
        return fake_conn

    def test_post_link_regression_close_skipped_in_atomic(self) -> None:
        fake_conn = self._run("check_post_link_regression", in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_post_link_regression_close_called_outside_atomic(self) -> None:
        fake_conn = self._run("check_post_link_regression", in_atomic_block=False)
        fake_conn.close.assert_called_once()

    def test_autotune_status_close_skipped_in_atomic(self) -> None:
        fake_conn = self._run("check_autotune_status", in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_autotune_status_close_called_outside_atomic(self) -> None:
        fake_conn = self._run("check_autotune_status", in_atomic_block=False)
        fake_conn.close.assert_called_once()
