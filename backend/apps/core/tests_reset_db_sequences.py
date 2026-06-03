"""Tests for the reset_db_sequences management command.

AutoIssue #20182: after a database restore the django_celery_results_taskresult
id sequence lagged MAX(id) by ~6000, so every INSERT collided with an existing
row and Postgres logged ~818 duplicate-key errors/hour. This command resets every
model's sequence to MAX(id) (idempotent) so a restored database cannot collide.
"""
from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TransactionTestCase


class ResetDbSequencesTests(TransactionTestCase):
    reset_sequences = True

    def _seq_last_value(self, table: str) -> int:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT last_value FROM {table}_id_seq")
            return cursor.fetchone()[0]

    def _create_rows(self, n: int):
        from apps.audit.models import ErrorLog

        for i in range(n):
            ErrorLog.objects.create(
                job_type=f"job{i}", step=f"step{i}", error_message=f"boom {i}"
            )

    def _rewind_sequence(self, table: str):
        """Simulate a restore that left the id sequence behind MAX(id)."""
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT setval('{table}_id_seq', 1, true)")

    def test_resets_stale_sequence_to_max_and_prevents_collision(self):
        from apps.audit.models import ErrorLog

        table = ErrorLog._meta.db_table
        self._create_rows(3)
        max_id = ErrorLog.objects.order_by("-id").first().id
        self._rewind_sequence(table)
        self.assertLess(self._seq_last_value(table), max_id, "precondition: sequence is stale")

        call_command("reset_db_sequences", app=["audit"], stdout=StringIO())

        self.assertGreaterEqual(self._seq_last_value(table), max_id)
        fresh = ErrorLog.objects.create(job_type="fresh", step="s", error_message="m")
        self.assertGreater(fresh.id, max_id, "a fresh insert must not collide after reset")

    def test_dry_run_prints_sql_without_changing_sequence(self):
        from apps.audit.models import ErrorLog

        table = ErrorLog._meta.db_table
        self._create_rows(2)
        self._rewind_sequence(table)
        before = self._seq_last_value(table)

        out = StringIO()
        call_command("reset_db_sequences", app=["audit"], dry_run=True, stdout=out)

        self.assertIn("setval", out.getvalue().lower())
        self.assertEqual(self._seq_last_value(table), before, "dry-run must not change the sequence")

    def test_unknown_app_label_raises(self):
        with self.assertRaises(CommandError):
            call_command("reset_db_sequences", app=["no_such_app_xyz"], stdout=StringIO())
