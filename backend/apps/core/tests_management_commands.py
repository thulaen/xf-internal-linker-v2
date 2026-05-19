"""Tests for lightweight management-command startup helpers."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.services.management_commands import is_lightweight_management_command


class LightweightManagementCommandTests(SimpleTestCase):
    def test_search_resolved_issues_is_lightweight(self) -> None:
        argv = ["manage.py", "search_resolved_issues", "--area", "backend/apps/audit"]

        self.assertTrue(is_lightweight_management_command(argv))

    def test_autoissue_read_commands_are_lightweight(self) -> None:
        for command in ("print_open_issues", "print_resolved_issues"):
            with self.subTest(command=command):
                self.assertTrue(is_lightweight_management_command(["manage.py", command]))

    def test_autoissue_write_commands_are_lightweight(self) -> None:
        for command in (
            "auto_issues_append_registry",
            "backfill_canonical_fingerprint",
            "log_self_review_issue",
            "resolve_autoissue",
        ):
            with self.subTest(command=command):
                self.assertTrue(is_lightweight_management_command(["manage.py", command]))

    def test_quality_evidence_commands_are_lightweight(self) -> None:
        for command in (
            "ingest_quality_evidence",
            "measure_coverage",
            "prune_quality_artifacts",
            "verify_autoissue_quota",
        ):
            with self.subTest(command=command):
                self.assertTrue(is_lightweight_management_command(["manage.py", command]))

    def test_restore_repair_command_is_lightweight(self) -> None:
        self.assertTrue(
            is_lightweight_management_command(["manage.py", "repair_restored_backup_schema"])
        )

    def test_regular_command_is_not_lightweight(self) -> None:
        argv = ["manage.py", "runserver", "0.0.0.0:8000"]

        self.assertFalse(is_lightweight_management_command(argv))
