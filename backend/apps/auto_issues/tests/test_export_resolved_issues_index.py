"""Focused tests for the resolved-issues export command."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import resolved_issue_index


class ExportResolvedIssuesIndexCommandTests(TestCase):
    def test_exports_one_entry_per_affected_file_with_required_fields(self) -> None:
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="export-focused",
            fingerprint="export-focused",
            title="Export focused lesson",
            description="Focused export test.",
            affected_files=["backend/apps/demo/service.py"],
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=timezone.now(),
            resolved_by="codex-test",
            lessons_learned=(
                "Trap: resolved lessons disappear when only the database is used.\n"
                "Fix shape: export one JSON line per affected file."
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            audit_dir = Path(tmp) / "audit"
            with patch.object(resolved_issue_index, "AUDIT_DIR", audit_dir), patch.object(
                resolved_issue_index,
                "INDEX_PATH",
                audit_dir / "resolved_issues_index.jsonl",
            ), patch.object(
                resolved_issue_index,
                "REPO_ROOT",
                Path(tmp),
            ):
                call_command("export_resolved_issues_index")
                matches = resolved_issue_index.lookup("backend/apps/demo/service.py")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["issue_title"], "Export focused lesson")
        for field in resolved_issue_index.REQUIRED_FIELDS:
            self.assertIn(field, matches[0])


class ClassifyAffectedHelperTests(TestCase):
    """Unit tests for _classify_affected extracted from _explode_rows (S3776 fix)."""

    def test_test_file_goes_to_tests_list(self):
        from apps.auto_issues.management.commands.export_resolved_issues_index import (
            _classify_affected,
        )
        tests, related = _classify_affected(["backend/tests/test_foo.py", "backend/foo.py"])
        self.assertIn("backend/tests/test_foo.py", tests)
        self.assertIn("backend/foo.py", related)

    def test_spec_ts_goes_to_tests_list(self):
        from apps.auto_issues.management.commands.export_resolved_issues_index import (
            _classify_affected,
        )
        tests, related = _classify_affected(["frontend/foo.spec.ts", "frontend/foo.ts"])
        self.assertIn("frontend/foo.spec.ts", tests)
        self.assertIn("frontend/foo.ts", related)

    def test_empty_strings_are_skipped(self):
        from apps.auto_issues.management.commands.export_resolved_issues_index import (
            _classify_affected,
        )
        tests, related = _classify_affected(["", "  ", "backend/real.py"])
        self.assertEqual(tests, [])
        self.assertEqual(related, ["backend/real.py"])
