"""Tests for the restored-backup schema repair command."""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase

from apps.core.management.commands.repair_restored_backup_schema import (
    SCHEMA_SPECS,
    SchemaSnapshot,
    build_repair_decisions,
)


def _paper_trail_spec():
    return next(spec for spec in SCHEMA_SPECS if spec.app == "paper_trail")


def _auto_issues_spec():
    return next(spec for spec in SCHEMA_SPECS if spec.app == "auto_issues")


def _snapshot_for_spec(spec):
    return SchemaSnapshot(
        tables=set(spec.required_tables),
        columns={
            table: set(names)
            for table, names in spec.required_columns.items()
        },
        indexes=set(spec.required_indexes),
        constraints=set(spec.required_constraints),
    )


def _delete_migration_records(app: str) -> None:
    recorder = MigrationRecorder(connection)
    recorder.Migration.objects.filter(app=app).delete()


def _recorded_migrations(app: str) -> set[str]:
    recorder = MigrationRecorder(connection)
    return set(
        recorder.Migration.objects.filter(app=app).values_list("name", flat=True)
    )


class RepairRestoredBackupSchemaCommandTests(TestCase):
    def test_dry_run_does_not_record_paper_trail_migrations(self) -> None:
        _delete_migration_records("paper_trail")
        out = StringIO()

        call_command("repair_restored_backup_schema", "--dry-run", stdout=out)

        self.assertEqual(_recorded_migrations("paper_trail"), set())
        self.assertIn("DRY RUN", out.getvalue())
        self.assertIn("paper_trail.0001_initial", out.getvalue())

    def test_records_existing_paper_trail_schema_history(self) -> None:
        _delete_migration_records("paper_trail")
        out = StringIO()

        call_command("repair_restored_backup_schema", stdout=out)

        self.assertEqual(_recorded_migrations("paper_trail"), set(_paper_trail_spec().migrations))
        self.assertIn("RECORDED", out.getvalue())

    def test_check_fails_when_repairable_history_is_missing(self) -> None:
        _delete_migration_records("paper_trail")

        with self.assertRaisesMessage(CommandError, "missing migration history"):
            call_command("repair_restored_backup_schema", "--check", stdout=StringIO())

    def test_missing_column_refuses_fake_success(self) -> None:
        spec = _paper_trail_spec()
        columns = _snapshot_for_spec(spec).columns
        columns["paper_trail_papertrailentry"].remove("acceptance_criteria")
        snapshot = SchemaSnapshot(
            tables=set(spec.required_tables),
            columns=columns,
            indexes=set(spec.required_indexes),
            constraints=set(spec.required_constraints),
        )

        decision = build_repair_decisions(snapshot, {"paper_trail": set()})[0]

        self.assertFalse(decision.can_record)
        self.assertIn("paper_trail_papertrailentry.acceptance_criteria", decision.missing_schema)

    def test_auto_issues_known_stale_shape_can_record_history(self) -> None:
        spec = _auto_issues_spec()
        decision = build_repair_decisions(_snapshot_for_spec(spec), {"auto_issues": set()})[0]

        self.assertTrue(decision.can_record)
        self.assertEqual(decision.missing_migrations, spec.migrations)

    def test_auto_issues_missing_concept_tags_blocks_recording(self) -> None:
        spec = _auto_issues_spec()
        snapshot = _snapshot_for_spec(spec)
        snapshot.columns["auto_issues_autoissue"].remove("concept_tags")

        decision = build_repair_decisions(snapshot, {"auto_issues": set()})[0]

        self.assertFalse(decision.can_record)
        self.assertIn("auto_issues_autoissue.concept_tags", decision.missing_schema)

    def test_check_passes_after_repair_records_history(self) -> None:
        _delete_migration_records("paper_trail")
        call_command("repair_restored_backup_schema", stdout=StringIO())
        out = StringIO()

        call_command("repair_restored_backup_schema", "--check", stdout=out)

        self.assertIn("OK", out.getvalue())
