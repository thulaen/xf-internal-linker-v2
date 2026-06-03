"""Convention-named SimpleTestCase coverage for apps/content/tasks.py.

Issue #86 follow-up: ``cluster_items`` closes a stale database connection
before it starts, but must skip that close when already inside a transaction
(an open atomic block) — closing mid-transaction corrupts the transaction
state.  The test runs the task with an empty item list (so the clustering loop
is a no-op) and a mocked connection, proving the guard fires only outside an
atomic block.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class ClusterItemsConnectionGuardTests(SimpleTestCase):
    def _run_with_atomic(self, *, in_atomic_block: bool) -> MagicMock:
        from apps.content import tasks

        fake_conn = MagicMock()
        fake_conn.in_atomic_block = in_atomic_block

        with patch.object(tasks, "connection", fake_conn), patch.object(
            tasks, "ClusteringService", return_value=MagicMock()
        ):
            result = tasks.cluster_items([])
        self.assertEqual(result, {"clustered_count": 0, "failed_ids": []})
        return fake_conn

    def test_close_skipped_when_inside_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=True)
        fake_conn.close.assert_not_called()

    def test_close_called_when_not_in_atomic_block(self) -> None:
        fake_conn = self._run_with_atomic(in_atomic_block=False)
        fake_conn.close.assert_called_once()
