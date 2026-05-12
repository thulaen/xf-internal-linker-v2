"""Tests for the auto_issues_append_registry management command.

Phase 6 follow-up landed under FR-251. The command appends one
RPT-<NNN> entry to docs/reports/REPORT-REGISTRY.md per AutoIssue. The
tests exercise the dry-run path (safe everywhere), idempotency check,
and the entry-formatting helper.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.management.commands.auto_issues_append_registry import (
    Command,
)
from apps.auto_issues.models import AutoIssue


class AppendRegistryCommandTests(TestCase):
    def _make_issue(self, **overrides) -> AutoIssue:
        defaults = dict(
            source=AutoIssue.SOURCE_AGENT,
            external_id="test-1",
            fingerprint="abc123",
            canonical_fingerprint="def456",
            title="test issue title",
            description="test issue description",
            affected_files=["backend/apps/test.py"],
            severity=AutoIssue.SEVERITY_MEDIUM,
            priority_score=0.5,
        )
        defaults.update(overrides)
        return AutoIssue.objects.create(**defaults)

    def test_next_rpt_id_increments_from_max(self) -> None:
        existing = "### RPT-001 - foo\n\n### RPT-007 - bar\n"
        self.assertEqual(Command._next_rpt_id(existing), 8)

    def test_next_rpt_id_starts_at_one_when_empty(self) -> None:
        self.assertEqual(Command._next_rpt_id("no RPT here"), 1)

    def test_already_in_registry_detects_fingerprint(self) -> None:
        issue = self._make_issue(canonical_fingerprint="known-fp")
        existing = "## Open Reports\n### RPT-001 - foo\n  canonical_fingerprint: `known-fp`\n"
        self.assertTrue(Command._already_in_registry(existing, issue))

    def test_already_in_registry_returns_false_for_unknown(self) -> None:
        issue = self._make_issue(canonical_fingerprint="never-seen")
        existing = "## Open Reports\n### RPT-001 - foo\n  canonical_fingerprint: `other-fp`\n"
        self.assertFalse(Command._already_in_registry(existing, issue))

    def test_already_in_registry_returns_false_when_fingerprint_blank(self) -> None:
        issue = self._make_issue(canonical_fingerprint="")
        self.assertFalse(Command._already_in_registry("anything", issue))

    def test_format_entry_includes_required_sections(self) -> None:
        issue = self._make_issue(
            title="My title",
            severity=AutoIssue.SEVERITY_HIGH,
            affected_files=["backend/x.py"],
            description="Plain English description.",
        )
        entry = Command._format_entry(42, issue)
        # Heading uses the right RPT number + title:
        self.assertIn("### RPT-042 - My title", entry)
        # Required sections all present:
        for marker in (
            "**Found by:**",
            "**AutoIssue:**",
            "**Status:** OPEN",
            "**Severity:** HIGH",
            "**Area:** `backend/x.py`",
            "**canonical_fingerprint:**",
            "**What is wrong in plain English:**",
            "**Why it matters:**",
            "**Fix shape:**",
        ):
            self.assertIn(marker, entry, f"missing section: {marker}")

    def test_insert_under_open_reports_anchors_correctly(self) -> None:
        existing = "# Header\n\n## Open Reports\n\nold body\n"
        entry = "\n### RPT-001 - new\n"
        result = Command._insert_under_open_reports(existing, entry)
        # The new entry must appear directly after `## Open Reports`
        # and before the old body.
        anchor_idx = result.index("## Open Reports")
        entry_idx = result.index("### RPT-001 - new")
        body_idx = result.index("old body")
        self.assertLess(anchor_idx, entry_idx)
        self.assertLess(entry_idx, body_idx)

    def test_dry_run_emits_entry_without_writing(self) -> None:
        issue = self._make_issue(title="dry run test")
        out = StringIO()
        # The command's _registry_path will resolve to the read-only
        # /repo mount in the container — that's fine for dry-run, since
        # no write happens.
        call_command(
            "auto_issues_append_registry",
            "--issue-id", str(issue.id),
            "--dry-run",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("dry run test", output)
        self.assertIn("would append 1", output)
