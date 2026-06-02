"""
Tests for apps.pipeline.tasks_tuning connection-reset behaviour.

Named ``tests_tasks_tuning.py`` (matching the ``tasks_tuning.py`` source stem)
so the diff-scoped mutation gate (.githooks/check-scoped-mutation.py:
_convention_tests) discovers them as the killing tests for the changed lines in
``tasks_tuning.py`` (the ``if not connection.in_atomic_block: connection.close()``
guards in ``monthly_weight_tune`` and ``monthly_meta_tune`` except blocks).

Root cause and fix are identical to apps.pipeline.tasks (see tests_tasks.py):
a DatabaseError must close the pooled connection before ErrorLog.objects.create
so the error record is not written on the broken connection, guarded by
``not connection.in_atomic_block``.

AutoIssues: #2556, #2557, #2558, #2559, #18935, #18936, #19964
"""
from __future__ import annotations

from unittest.mock import patch

from django.db import DatabaseError
from django.test import SimpleTestCase


# ---------------------------------------------------------------------------
# monthly_weight_tune
# ---------------------------------------------------------------------------

class MonthlyWeightTuneConnectionResetTests(SimpleTestCase):
    """monthly_weight_tune must close the connection in its except block."""

    def test_uses_medium_weight_lock(self):
        """monthly_weight_tune must share the normal medium task lock."""
        from apps.pipeline.tasks_tuning import monthly_weight_tune  # noqa: PLC0415

        with (
            patch("apps.pipeline.services.task_lock.acquire_task_lock") as acquire,
            patch("apps.pipeline.services.task_lock.release_task_lock"),
            patch("apps.pipeline.tasks_tuning.connection") as mock_conn,
            patch(
                "apps.suggestions.services.weight_tuner.WeightTuner.run",
                side_effect=DatabaseError("stale connection"),
            ),
            patch("apps.audit.models.ErrorLog.objects.create"),
        ):
            acquire.return_value = True
            mock_conn.in_atomic_block = False
            monthly_weight_tune.run()

        acquire.assert_called_once_with("medium", "monthly_weight_tune")

    def test_close_called_twice_on_database_error(self):
        """connection.close() is called at start AND again after DatabaseError."""
        from apps.pipeline.tasks_tuning import monthly_weight_tune  # noqa: PLC0415

        with (
            patch("apps.pipeline.tasks_tuning.connection") as mock_conn,
            patch(
                "apps.suggestions.services.weight_tuner.WeightTuner.run",
                side_effect=DatabaseError("stale connection"),
            ),
            patch("apps.audit.models.ErrorLog.objects.create"),
            patch("apps.pipeline.services.task_lock.cache") as mock_cache,
        ):
            mock_cache.add.return_value = True
            mock_conn.in_atomic_block = False
            result = monthly_weight_tune.run()

        # Current code: close() called once (at start).
        # Fixed code: close() called twice (at start + in except block).
        self.assertGreaterEqual(
            mock_conn.close.call_count,
            2,
            "connection.close() must be called in the except block so ErrorLog "
            "gets a fresh connection, not the broken one.",
        )
        self.assertEqual(result["status"], "error")

    def test_closes_before_tune_and_before_error_log_write(self):
        """The start and failure closes protect both the tune run and the error record."""
        from apps.pipeline.tasks_tuning import monthly_weight_tune  # noqa: PLC0415

        events: list[str] = []

        def fail_tune(*_, **__):
            events.append("run")
            raise DatabaseError("stale connection")

        with (
            patch("apps.pipeline.tasks_tuning.connection") as mock_conn,
            patch(
                "apps.suggestions.services.weight_tuner.WeightTuner.run",
                side_effect=fail_tune,
            ),
            patch("apps.audit.models.ErrorLog.objects.create") as create_log,
            patch("apps.pipeline.services.task_lock.cache") as mock_cache,
        ):
            mock_cache.add.return_value = True
            mock_conn.in_atomic_block = False
            mock_conn.close.side_effect = lambda: events.append("close")
            create_log.side_effect = lambda **_: events.append("log")

            result = monthly_weight_tune.run()

        self.assertEqual(result["status"], "error")
        self.assertEqual(events, ["close", "run", "close", "log"])


# ---------------------------------------------------------------------------
# monthly_meta_tune
# ---------------------------------------------------------------------------

class MonthlyMetaTuneConnectionResetTests(SimpleTestCase):
    """monthly_meta_tune must close the connection in its except block."""

    def test_close_called_twice_on_database_error(self):
        """connection.close() is called at start AND again after DatabaseError."""
        from apps.pipeline.tasks_tuning import monthly_meta_tune  # noqa: PLC0415

        with (
            patch("apps.pipeline.tasks_tuning.connection") as mock_conn,
            patch(
                "apps.suggestions.services.meta_tuner.MetaAlgorithmTuner.propose",
                side_effect=DatabaseError("stale connection"),
            ),
            patch("apps.audit.models.ErrorLog.objects.create"),
            patch("apps.pipeline.services.task_lock.cache") as mock_cache,
        ):
            mock_cache.add.return_value = True
            mock_conn.in_atomic_block = False
            result = monthly_meta_tune.run()

        self.assertGreaterEqual(
            mock_conn.close.call_count,
            2,
            "connection.close() must be called in the except block.",
        )
        self.assertEqual(result["status"], "error")

    def test_closes_before_tune_and_before_error_log_write(self):
        """The meta tune task must reset the connection before logging a failure."""
        from apps.pipeline.tasks_tuning import monthly_meta_tune  # noqa: PLC0415

        events: list[str] = []

        def fail_propose(*_, **__):
            events.append("propose")
            raise DatabaseError("stale connection")

        with (
            patch("apps.pipeline.tasks_tuning.connection") as mock_conn,
            patch(
                "apps.suggestions.services.meta_tuner.MetaAlgorithmTuner.propose",
                side_effect=fail_propose,
            ),
            patch("apps.audit.models.ErrorLog.objects.create") as create_log,
            patch("apps.pipeline.services.task_lock.cache") as mock_cache,
        ):
            mock_cache.add.return_value = True
            mock_conn.in_atomic_block = False
            mock_conn.close.side_effect = lambda: events.append("close")
            create_log.side_effect = lambda **_: events.append("log")

            result = monthly_meta_tune.run()

        self.assertEqual(result["status"], "error")
        self.assertEqual(events, ["close", "propose", "close", "log"])
