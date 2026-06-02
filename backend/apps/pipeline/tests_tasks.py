"""
Tests for apps.pipeline.tasks connection-reset behaviour.

Named ``tests_tasks.py`` (matching the ``tasks.py`` source stem) so the
diff-scoped mutation gate (.githooks/check-scoped-mutation.py:_convention_tests)
discovers them as the killing tests for the changed lines in ``tasks.py``
(the ``if not connection.in_atomic_block: connection.close()`` guards in
``_purge_aged_rows`` and ``_purge_with_bitmap_preview``).

Root cause: psycopg3 3.2.4 raises ProgrammingError("the last operation
didn't produce a result") when a pooled connection returns COMMAND_OK where
TUPLES_OK is expected. Without closing the connection in the except block,
the broken connection goes back into the pool and the next purge step (or
ErrorLog.objects.create) reuses it, failing again.

Fix: call connection.close() before ErrorLog.objects.create() in every
except block, guarded by ``not connection.in_atomic_block`` so we never close
an open transaction.

AutoIssues: #2556, #2557, #2558, #2559, #18935, #18936, #19964
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.db import DatabaseError
from django.test import SimpleTestCase


# ---------------------------------------------------------------------------
# _purge_aged_rows
# ---------------------------------------------------------------------------

class PurgeAgedRowsConnectionResetTests(SimpleTestCase):
    """_purge_aged_rows must close the connection after a DatabaseError."""

    def _call(self, *, in_atomic_block: bool):
        from apps.pipeline.tasks import _purge_aged_rows  # noqa: PLC0415

        mock_model = MagicMock()
        mock_model.objects.filter.return_value.delete.side_effect = DatabaseError(
            "the last operation didn't produce a result"
        )
        with (
            patch("apps.pipeline.tasks.connection") as mock_conn,
            patch("apps.audit.models.ErrorLog.objects.create"),
        ):
            mock_conn.in_atomic_block = in_atomic_block
            result = _purge_aged_rows(
                model_cls=mock_model,
                cutoff_field="created_at",
                cutoff=MagicMock(),
                label="TestPurge",
                step="test_step",
                fix_hint="check test",
            )
        return mock_conn, result

    def test_closes_connection_when_not_in_atomic_block(self):
        """After DatabaseError, connection.close() is called so the next step gets a fresh connection."""
        mock_conn, result = self._call(in_atomic_block=False)
        mock_conn.close.assert_called_once()
        self.assertEqual(result, 0)

    def test_does_not_close_connection_when_in_atomic_block(self):
        """Inside a transaction we must NOT close — that would abort the transaction."""
        mock_conn, _ = self._call(in_atomic_block=True)
        mock_conn.close.assert_not_called()

    def test_returns_zero_on_database_error(self):
        """Existing behaviour: returns 0 so the caller can continue with other purge steps."""
        _, result = self._call(in_atomic_block=False)
        self.assertEqual(result, 0)

    def test_closes_connection_before_error_log_write(self):
        """Error logging must use a fresh connection after the purge query breaks."""
        from apps.pipeline.tasks import _purge_aged_rows  # noqa: PLC0415

        events: list[str] = []
        mock_model = MagicMock()
        mock_model.objects.filter.return_value.delete.side_effect = DatabaseError(
            "stale connection"
        )

        with (
            patch("apps.pipeline.tasks.connection") as mock_conn,
            patch("apps.audit.models.ErrorLog.objects.create") as create_log,
        ):
            mock_conn.in_atomic_block = False
            mock_conn.close.side_effect = lambda: events.append("close")
            create_log.side_effect = lambda **_: events.append("log")

            _purge_aged_rows(
                model_cls=mock_model,
                cutoff_field="created_at",
                cutoff=MagicMock(),
                label="TestPurge",
                step="test_step",
                fix_hint="check test",
            )

        self.assertEqual(events, ["close", "log"])


# ---------------------------------------------------------------------------
# _purge_with_bitmap_preview
# ---------------------------------------------------------------------------

class PurgeWithBitmapPreviewConnectionResetTests(SimpleTestCase):
    """_purge_with_bitmap_preview must close the connection after a DatabaseError."""

    def _call(self, *, in_atomic_block: bool):
        from apps.pipeline.tasks import _purge_with_bitmap_preview  # noqa: PLC0415

        mock_qs = MagicMock()
        with (
            patch("apps.pipeline.tasks.connection") as mock_conn,
            patch("apps.audit.models.ErrorLog.objects.create"),
            patch(
                "apps.pipeline.services.waste_bitmaps.bitmap_from_pks",
                side_effect=DatabaseError("stale connection"),
            ),
        ):
            mock_conn.in_atomic_block = in_atomic_block
            result = _purge_with_bitmap_preview(
                queryset=mock_qs,
                use_bitmap=True,
                label="TestBitmapPurge",
                step="test_bitmap_step",
                fix_hint="check test",
            )
        return mock_conn, result

    def test_closes_connection_when_not_in_atomic_block(self):
        mock_conn, result = self._call(in_atomic_block=False)
        mock_conn.close.assert_called_once()
        self.assertEqual(result, 0)

    def test_does_not_close_connection_when_in_atomic_block(self):
        mock_conn, _ = self._call(in_atomic_block=True)
        mock_conn.close.assert_not_called()

    def test_closes_connection_before_error_log_write(self):
        """Bitmap preview failures also need a fresh connection before logging."""
        from apps.pipeline.tasks import _purge_with_bitmap_preview  # noqa: PLC0415

        events: list[str] = []
        with (
            patch("apps.pipeline.tasks.connection") as mock_conn,
            patch("apps.audit.models.ErrorLog.objects.create") as create_log,
            patch(
                "apps.pipeline.services.waste_bitmaps.bitmap_from_pks",
                side_effect=DatabaseError("stale connection"),
            ),
        ):
            mock_conn.in_atomic_block = False
            mock_conn.close.side_effect = lambda: events.append("close")
            create_log.side_effect = lambda **_: events.append("log")

            _purge_with_bitmap_preview(
                queryset=MagicMock(),
                use_bitmap=True,
                label="TestBitmapPurge",
                step="test_bitmap_step",
                fix_hint="check test",
            )

        self.assertEqual(events, ["close", "log"])


# ---------------------------------------------------------------------------
# Cascade prevention — root cause of Loki hot_pattern #408 and warn_burst
# #1836: one failing purge step flooded the log with tracebacks because
# subsequent steps reused the broken connection.
# ---------------------------------------------------------------------------

class PurgeAgedRowsCascadePreventionTests(SimpleTestCase):
    """After one purge step fails, subsequent steps must succeed with a fresh connection."""

    def test_second_purge_step_succeeds_when_first_fails(self):
        """Connection is closed after step-1 DatabaseError so step-2 gets a clean connection."""
        from apps.pipeline.tasks import _purge_aged_rows  # noqa: PLC0415

        call_count = {"n": 0}

        def delete_side_effect():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise DatabaseError("the last operation didn't produce a result")
            return (5, {})  # 5 rows deleted on the second call

        mock_model = MagicMock()
        mock_model.objects.filter.return_value.delete.side_effect = delete_side_effect

        with (
            patch("apps.pipeline.tasks.connection") as mock_conn,
            patch("apps.audit.models.ErrorLog.objects.create"),
        ):
            mock_conn.in_atomic_block = False
            result_step1 = _purge_aged_rows(
                model_cls=mock_model,
                cutoff_field="created_at",
                cutoff=MagicMock(),
                label="Step1",
                step="step1",
                fix_hint="hint",
            )
            result_step2 = _purge_aged_rows(
                model_cls=mock_model,
                cutoff_field="created_at",
                cutoff=MagicMock(),
                label="Step2",
                step="step2",
                fix_hint="hint",
            )

        self.assertEqual(result_step1, 0, "Step 1 should return 0 on failure")
        self.assertEqual(result_step2, 5, "Step 2 should succeed after connection reset")
