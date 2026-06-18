"""Focused tests for the disk-backed resolved-issue index service."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.auto_issues.services import resolved_issue_index


class ResolvedIssueIndexTests(unittest.TestCase):
    def test_repo_root_prefers_repo_mount_even_without_handoff_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            container_root = Path(tmp)

            detected = resolved_issue_index._detect_repo_root(
                start_path=Path("/app/apps/auto_issues/services/resolved_issue_index.py"),
                container_root=container_root,
            )

            self.assertEqual(detected, container_root)

    def test_repo_root_walks_up_to_handoff_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "backend" / "apps" / "auto_issues"
            nested.mkdir(parents=True)
            (root / "AGENT-HANDOFF.md").write_text("handoff", encoding="utf-8")

            detected = resolved_issue_index._detect_repo_root(
                start_path=nested / "service.py",
                container_root=root / "missing-repo",
            )

            self.assertEqual(detected, root)

    def test_audit_dir_prefers_explicit_environment_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit_dir = Path(tmp) / "custom-audit"

            detected = resolved_issue_index._detect_audit_dir(
                Path(tmp),
                env={resolved_issue_index.AUDIT_DIR_ENV: str(audit_dir)},
            )

            self.assertEqual(detected, audit_dir)

    def test_audit_dir_never_falls_back_to_root_audit(self) -> None:
        root_path = Path("/")

        detected = resolved_issue_index._detect_audit_dir(root_path, env={})

        self.assertNotEqual(detected, Path("/audit"))

    def test_audit_dir_uses_repo_audit_when_parent_is_writable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            detected = resolved_issue_index._detect_audit_dir(root, env={})

            self.assertEqual(detected, root / "audit")

    def test_writable_audit_candidate_rejects_plain_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "audit"
            file_path.write_text("not a directory", encoding="utf-8")

            self.assertFalse(resolved_issue_index._can_write_audit_dir(file_path))

    def test_load_index_skips_bad_rows_and_normalises_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit_dir = Path(tmp)
            index_path = audit_dir / "resolved_issues_index.jsonl"
            index_path.write_text(
                "{bad json\n"
                "{}\n"
                '{"file_path": "backend/apps/demo/service.py", "autoissue_id": 42}',
                encoding="utf-8",
            )
            with patch.object(resolved_issue_index, "INDEX_PATH", index_path), patch.object(
                resolved_issue_index,
                "_index_cache",
                None,
            ), patch.object(resolved_issue_index, "_index_cache_path_mtime", None):
                matches = resolved_issue_index.load_index(force_refresh=True)

            self.assertEqual(list(matches), ["backend/apps/demo/service.py"])

    def test_current_task_id_reads_latest_handoff_session_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp) / "AGENT-HANDOFF.md"
            handoff.write_text(
                "[TDD PREFLIGHT: session_id=12345678-1234-1234-1234-123456789abc]",
                encoding="utf-8",
            )

            with patch.object(resolved_issue_index, "HANDOFF_PATH", handoff):
                task_id = resolved_issue_index.current_task_id()

            self.assertEqual(task_id, "12345678-1234-1234-1234-123456789abc")

    def test_current_task_id_falls_back_when_git_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                resolved_issue_index,
                "HANDOFF_PATH",
                Path(tmp) / "missing.md",
            ), patch.object(
                resolved_issue_index.subprocess,
                "run",
                side_effect=FileNotFoundError,
            ):
                task_id = resolved_issue_index.current_task_id()

            self.assertTrue(task_id.startswith("fallback-no-head-"))

    def test_audit_entries_ignore_malformed_rows_and_filter_by_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "resolved_issues_lookup_log.jsonl"
            log_path.write_text(
                '{"task_id": "session-1", "file_path": "backend/apps/a.py"}\n'
                "{bad json\n"
                '{"task_id": "session-2", "file_path": "backend/apps/b.py"}',
                encoding="utf-8",
            )

            with patch.object(resolved_issue_index, "AUDIT_LOG_PATH", log_path):
                entries = resolved_issue_index.audit_entries_for_task("session-1")

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["file_path"], "backend/apps/a.py")

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
