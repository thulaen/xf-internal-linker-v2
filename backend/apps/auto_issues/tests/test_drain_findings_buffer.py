"""Tests for draining buffered hook findings into AutoIssues."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command
from django.test import TransactionTestCase

from apps.auto_issues.models import AutoIssue


class DrainFindingsBufferTests(TransactionTestCase):
    reset_sequences = False

    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "audit").mkdir()
        self.buffer = self.root / "audit" / "findings_buffer.jsonl"

    def tearDown(self) -> None:
        AutoIssue.objects.filter(external_id__startswith="hook_finding::").delete()

    def _line(self, subject: str = "backend/apps/foo/bar.py:42") -> str:
        return json.dumps(
            {
                "category": "tdd_lesson_missing",
                "severity": "medium",
                "subject": subject,
                "message": "Missing [TDD CYCLE STRICT:] marker for foo/bar.py",
                "agent": "codex",
            }
        )

    def _drain(self) -> str:
        out = StringIO()
        call_command("drain_findings_buffer", repo_root=str(self.root), stdout=out)
        return out.getvalue()

    @patch("apps.auto_issues.management.commands.drain_findings_buffer.backend_health_ok", return_value=True)
    def test_drain_files_valid_lines(self, _health) -> None:
        self.buffer.write_text("\n".join(self._line(f"backend/apps/foo/{i}.py:1") for i in range(5)) + "\n")
        output = self._drain()
        self.assertIn("[FINDINGS DRAINED: filed=5 deduped=0 total=5]", output)
        self.assertEqual(5, AutoIssue.objects.filter(external_id__startswith="hook_finding::").count())

    @patch("apps.auto_issues.management.commands.drain_findings_buffer.backend_health_ok", return_value=True)
    def test_drain_dedups_against_existing_autoissues(self, _health) -> None:
        self.buffer.write_text(self._line() + "\n" + self._line() + "\n")
        output = self._drain()
        self.assertIn("[FINDINGS DRAINED: filed=1 deduped=1 total=2]", output)
        row = AutoIssue.objects.get(external_id__startswith="hook_finding::")
        self.assertEqual(2, row.occurrence_count)

    @patch("apps.auto_issues.management.commands.drain_findings_buffer.backend_health_ok", return_value=True)
    def test_drain_handles_malformed_lines(self, _health) -> None:
        self.buffer.write_text(self._line() + "\nnot-json\n" + self._line("backend/apps/foo/baz.py:7") + "\n")
        output = self._drain()
        self.assertIn("[FINDINGS DRAINED: filed=2 deduped=0 total=2]", output)
        errors = (self.root / "audit" / "findings_buffer.errors.jsonl").read_text(encoding="utf-8")
        self.assertIn("parse_error", errors)

    @patch("apps.auto_issues.management.commands.drain_findings_buffer.backend_health_ok", return_value=True)
    def test_drain_rotates_buffer_after_success(self, _health) -> None:
        self.buffer.write_text(self._line() + "\n")
        self._drain()
        drained = list((self.root / "audit").glob("findings_buffer.drained.*.jsonl"))
        self.assertEqual(1, len(drained))
        self.assertEqual("", self.buffer.read_text(encoding="utf-8"))

    @patch("apps.auto_issues.management.commands.drain_findings_buffer.backend_health_ok", return_value=False)
    def test_drain_skips_when_backend_unreachable(self, _health) -> None:
        self.buffer.write_text(self._line() + "\n")
        output = self._drain()
        self.assertIn("[FINDINGS DRAIN SKIPPED: backend unreachable, retry next session]", output)
        self.assertTrue(self.buffer.exists())
        self.assertIn("bar.py:42", self.buffer.read_text(encoding="utf-8"))

    @patch("apps.auto_issues.management.commands.drain_findings_buffer.backend_health_ok", return_value=False)
    def test_drain_exits_zero_even_when_skipped(self, _health) -> None:
        self.buffer.write_text(self._line() + "\n")
        self._drain()
