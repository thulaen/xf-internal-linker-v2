"""Focused tests for the commit-failure lookup command."""

from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.auto_issues.management.commands import search_commit_failures
from apps.auto_issues.services import resolved_issue_index


class SearchCommitFailuresCommandTests(SimpleTestCase):
    def test_reads_disk_index_and_writes_task_audit_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index_path = root / "audit" / "commit_failures_index.jsonl"
            audit_path = root / "audit" / "commit_failures_lookup_log.jsonl"
            index_path.parent.mkdir(parents=True)
            index_path.write_text(
                json.dumps(
                    {
                        "autoissue_id": 91,
                        "title": "Prior hook failure",
                        "severity": "medium",
                        "root_cause": "Trap: the hook ran too much.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output = StringIO()

            with patch.object(search_commit_failures, "INDEX_PATH", index_path), patch.object(
                search_commit_failures,
                "AUDIT_LOG_PATH",
                audit_path,
            ), patch.object(resolved_issue_index, "current_task_id", return_value="session-1"):
                call_command("search_commit_failures", limit=10, agent="codex", stdout=output)

            self.assertIn("1 prior failure", output.getvalue())
            audit_row = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(audit_row["task_id"], "session-1")
            self.assertEqual(audit_row["agent"], "codex")
            self.assertEqual(audit_row["result_count"], 1)
