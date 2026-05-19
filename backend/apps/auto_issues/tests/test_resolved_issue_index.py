"""Focused tests for the disk-backed resolved-issue index service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.auto_issues.services import resolved_issue_index


class ResolvedIssueIndexTests(unittest.TestCase):
    def test_write_lookup_and_audit_use_exact_file_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audit_dir = root / "audit"
            with patch.object(resolved_issue_index, "AUDIT_DIR", audit_dir), patch.object(
                resolved_issue_index,
                "INDEX_PATH",
                audit_dir / "resolved_issues_index.jsonl",
            ), patch.object(
                resolved_issue_index,
                "AUDIT_LOG_PATH",
                audit_dir / "resolved_issues_lookup_log.jsonl",
            ):
                count = resolved_issue_index.write_index(
                    [
                        {
                            "file_path": "backend/apps/demo/service.py",
                            "issue_title": "Focused lookup",
                            "root_cause": "Trap",
                            "what_failed": "Trap",
                            "what_fixed_it": "Fix",
                            "safe_implementation_notes": "Use exact paths.",
                            "autoissue_id": 42,
                        }
                    ]
                )
                matches = resolved_issue_index.lookup("backend\\apps\\demo\\service.py")
                resolved_issue_index.append_audit_entry(
                    file_path="backend/apps/demo/service.py",
                    task_id="session-1",
                    agent="codex",
                    result_count=len(matches),
                    result_ids=[42],
                )

                self.assertEqual(count, 1)
                self.assertEqual(matches[0]["autoissue_id"], 42)
                self.assertEqual(
                    resolved_issue_index.files_with_lookup_in_task("session-1"),
                    {"backend/apps/demo/service.py"},
                )


if __name__ == "__main__":
    unittest.main()
