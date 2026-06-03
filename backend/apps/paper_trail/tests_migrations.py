"""Regression tests for Paper Trail migration state."""

from __future__ import annotations

from importlib import import_module

from django.db import migrations
from django.test import SimpleTestCase


class PaperTrailMigrationStateTests(SimpleTestCase):
    def test_0006_tracks_long_abstract_and_status_index(self) -> None:
        migration = import_module(
            "apps.paper_trail.migrations.0006_alter_papertrailentry_abstract_and_status"
        )

        operations = migration.Migration.operations
        self.assertEqual(2, len(operations))
        self.assertIsInstance(operations[0], migrations.AlterField)
        self.assertIsInstance(operations[1], migrations.SeparateDatabaseAndState)

        fields_by_name = {
            operations[0].name: operations[0].field,
            operations[1].state_operations[0].name: (
                operations[1].state_operations[0].field
            ),
        }

        self.assertEqual(80_000, fields_by_name["abstract"].max_length)
        self.assertTrue(fields_by_name["status"].db_index)
        self.assertEqual([], operations[1].database_operations)

    def test_0007_widens_abstract_to_9500(self) -> None:
        migration = import_module(
            "apps.paper_trail.migrations.0007_alter_papertrailentry_abstract"
        )

        operations = migration.Migration.operations
        self.assertEqual(1, len(operations))
        self.assertIsInstance(operations[0], migrations.AlterField)
        self.assertEqual("abstract", operations[0].name)
        self.assertEqual(9_500, operations[0].field.max_length)

    def test_0007_depends_on_0006(self) -> None:
        migration = import_module(
            "apps.paper_trail.migrations.0007_alter_papertrailentry_abstract"
        )
        self.assertEqual(
            [("paper_trail", "0006_alter_papertrailentry_abstract_and_status")],
            migration.Migration.dependencies,
        )
