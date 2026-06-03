"""Tests for the file_test_failure management command.

BDD:
  Given a failed distributed-shard test result
  When file_test_failure() is called with tool/target/file/name/summary
  Then an AutoIssue with source='test_failure' is created or updated
  And the external_id encodes the failure fingerprint for deduplication
  And resolved issues are reopened automatically
  And artifact references are stored on the row
"""

from __future__ import annotations

from django.test import TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.management.commands.file_test_failure import (
    file_test_failure,
    _failure_fingerprint,
    _CATEGORY_KEY,
)


_TOOL = "mutmut"
_TARGET = "backend.apps.audit"
_FILE = "apps/audit/tasks.py"
_NAME = "test_mutation_survived_line_42"
_SUMMARY = "Mutant survived: replace + with - on line 42"
_RUN_ID = "run-20260527-001"
_SHARD_ID = "shard-0"


class FileTestFailureCreateTests(TestCase):
    def test_new_failure_creates_autoissue(self) -> None:
        issue, action = file_test_failure(
            tool=_TOOL,
            test_target=_TARGET,
            test_file=_FILE,
            test_name=_NAME,
            failure_summary=_SUMMARY,
            severity="medium",
            run_id=_RUN_ID,
            shard_id=_SHARD_ID,
        )

        self.assertEqual(action, "created")
        self.assertEqual(issue.source, "test_failure")
        self.assertEqual(issue.severity, AutoIssue.SEVERITY_MEDIUM)
        self.assertEqual(issue.status, AutoIssue.STATUS_OPEN)
        self.assertIn("failed_test::", issue.external_id)

    def test_external_id_contains_fingerprint(self) -> None:
        issue, _ = file_test_failure(
            tool=_TOOL,
            test_target=_TARGET,
            test_file=_FILE,
            test_name=_NAME,
            failure_summary=_SUMMARY,
            severity="medium",
            run_id=_RUN_ID,
            shard_id=_SHARD_ID,
        )

        fp = _failure_fingerprint(_SUMMARY)
        self.assertTrue(issue.external_id.endswith(fp), issue.external_id)

    def test_category_is_failed_test(self) -> None:
        issue, _ = file_test_failure(
            tool=_TOOL,
            test_target=_TARGET,
            test_file=_FILE,
            test_name=_NAME,
            failure_summary=_SUMMARY,
            severity="high",
            run_id=_RUN_ID,
            shard_id=_SHARD_ID,
        )

        self.assertEqual(issue.category.key, _CATEGORY_KEY)

    def test_severity_stored_correctly(self) -> None:
        for sev_in, sev_expected in [
            ("high", AutoIssue.SEVERITY_HIGH),
            ("medium", AutoIssue.SEVERITY_MEDIUM),
            ("low", AutoIssue.SEVERITY_LOW),
        ]:
            with self.subTest(severity=sev_in):
                AutoIssue.objects.all().delete()
                issue, _ = file_test_failure(
                    tool=_TOOL,
                    test_target=_TARGET,
                    test_file=_FILE,
                    test_name=f"test_sev_{sev_in}",
                    failure_summary=f"Failure with severity {sev_in}",
                    severity=sev_in,
                    run_id=_RUN_ID,
                    shard_id=_SHARD_ID,
                )
                self.assertEqual(issue.severity, sev_expected)

    def test_artifact_refs_stored(self) -> None:
        refs = [
            {
                "sha256": "abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
                "blob_path": "/srv/xf/artifacts/blob-store/sha256/ab/abc123",
                "tool": "mutmut",
                "run_id": _RUN_ID,
                "shard_id": _SHARD_ID,
                "media_type": "application/json",
            }
        ]
        issue, _ = file_test_failure(
            tool=_TOOL,
            test_target=_TARGET,
            test_file=_FILE,
            test_name=_NAME,
            failure_summary=_SUMMARY,
            severity="medium",
            run_id=_RUN_ID,
            shard_id=_SHARD_ID,
            artifact_refs=refs,
        )

        self.assertEqual(len(issue.artifact_refs), 1)
        self.assertEqual(issue.artifact_refs[0]["sha256"], refs[0]["sha256"])
        self.assertEqual(issue.artifact_refs[0]["tool"], "mutmut")


class FileTestFailureUpdateTests(TestCase):
    def setUp(self) -> None:
        self.issue, _ = file_test_failure(
            tool=_TOOL,
            test_target=_TARGET,
            test_file=_FILE,
            test_name=_NAME,
            failure_summary=_SUMMARY,
            severity="medium",
            run_id=_RUN_ID,
            shard_id=_SHARD_ID,
        )

    def test_duplicate_filing_updates_not_creates(self) -> None:
        before_count = AutoIssue.objects.count()

        _, action = file_test_failure(
            tool=_TOOL,
            test_target=_TARGET,
            test_file=_FILE,
            test_name=_NAME,
            failure_summary=_SUMMARY,
            severity="medium",
            run_id="run-20260527-002",
            shard_id=_SHARD_ID,
        )

        self.assertEqual(action, "updated")
        self.assertEqual(AutoIssue.objects.count(), before_count)

    def test_occurrence_count_incremented_on_update(self) -> None:
        before = self.issue.occurrence_count

        updated, _ = file_test_failure(
            tool=_TOOL,
            test_target=_TARGET,
            test_file=_FILE,
            test_name=_NAME,
            failure_summary=_SUMMARY,
            severity="medium",
            run_id="run-20260527-002",
            shard_id=_SHARD_ID,
        )

        updated.refresh_from_db()
        self.assertEqual(updated.occurrence_count, before + 1)

    def test_resolved_autoissue_gets_reopened(self) -> None:
        self.issue.status = AutoIssue.STATUS_RESOLVED
        self.issue.save()

        _, action = file_test_failure(
            tool=_TOOL,
            test_target=_TARGET,
            test_file=_FILE,
            test_name=_NAME,
            failure_summary=_SUMMARY,
            severity="medium",
            run_id="run-20260527-003",
            shard_id=_SHARD_ID,
        )

        self.assertEqual(action, "reopened")
        self.issue.refresh_from_db()
        self.assertEqual(self.issue.status, AutoIssue.STATUS_OPEN)


class FileTestFailureValidationTests(TestCase):
    def test_missing_tool_raises(self) -> None:
        from django.core.management.base import CommandError

        with self.assertRaises((CommandError, ValueError)):
            file_test_failure(
                tool="",
                test_target=_TARGET,
                test_file=_FILE,
                test_name=_NAME,
                failure_summary=_SUMMARY,
                severity="medium",
                run_id=_RUN_ID,
                shard_id=_SHARD_ID,
            )

    def test_missing_failure_summary_raises(self) -> None:
        from django.core.management.base import CommandError

        with self.assertRaises((CommandError, ValueError)):
            file_test_failure(
                tool=_TOOL,
                test_target=_TARGET,
                test_file=_FILE,
                test_name=_NAME,
                failure_summary="",
                severity="medium",
                run_id=_RUN_ID,
                shard_id=_SHARD_ID,
            )
