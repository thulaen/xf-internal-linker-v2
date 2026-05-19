"""Focused tests for the restored-backup repair command."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.management.commands.repair_restored_backup_schema import (
    SCHEMA_SPECS,
    SchemaSnapshot,
    build_repair_decisions,
)


def _auto_issues_spec():
    return next(spec for spec in SCHEMA_SPECS if spec.app == "auto_issues")


def _snapshot_for_spec(spec):
    return SchemaSnapshot(
        tables=set(spec.required_tables),
        columns={table: set(names) for table, names in spec.required_columns.items()},
        indexes=set(spec.required_indexes),
        constraints=set(spec.required_constraints),
    )


class RepairRestoredBackupSchemaCoreTests(SimpleTestCase):
    def test_valid_schema_can_record_missing_auto_issue_history(self) -> None:
        spec = _auto_issues_spec()

        decision = build_repair_decisions(_snapshot_for_spec(spec), {"auto_issues": set()})[0]

        self.assertTrue(decision.can_record)
        self.assertEqual(decision.missing_migrations, spec.migrations)

    def test_invalid_schema_blocks_fake_history_repair(self) -> None:
        spec = _auto_issues_spec()
        snapshot = _snapshot_for_spec(spec)
        snapshot.columns["auto_issues_autoissue"].remove("concept_tags")

        decision = build_repair_decisions(snapshot, {"auto_issues": set()})[0]

        self.assertFalse(decision.can_record)
        self.assertIn("auto_issues_autoissue.concept_tags", decision.missing_schema)
