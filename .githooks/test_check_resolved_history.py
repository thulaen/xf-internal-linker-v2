"""Unit tests for check-resolved-history.py (disk-backed audit-log variant).

The hook enforces the 2026-05-18 user rule: every staged production source
file must have a SUCCESSFUL search_resolved_issues lookup recorded in the
disk-backed audit log under the current task_id. Memory-only lookups do not
satisfy the mandate.

The hook is loaded via importlib because the filename uses a hyphen.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOK_PATH = Path(__file__).resolve().parent / "check-resolved-history.py"
_spec = importlib.util.spec_from_file_location("check_resolved_history", HOOK_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["check_resolved_history"] = _mod
_spec.loader.exec_module(_mod)


class PathNormalisationTests(unittest.TestCase):
    """Slashes and trailing characters normalise so audit lookup is stable."""

    def test_backslashes_become_forward(self):
        self.assertEqual(
            _mod._normalise_path("backend\\apps\\X.py"),
            "backend/apps/X.py",
        )

    def test_trailing_slash_stripped(self):
        self.assertEqual(
            _mod._normalise_path("backend/apps/X.py/"),
            "backend/apps/X.py",
        )

    def test_leading_slash_stripped(self):
        self.assertEqual(
            _mod._normalise_path("/backend/apps/X.py"),
            "backend/apps/X.py",
        )

    def test_whitespace_stripped(self):
        self.assertEqual(
            _mod._normalise_path("  backend/apps/X.py  "),
            "backend/apps/X.py",
        )


class TaskIdResolutionTests(unittest.TestCase):
    """Task ID comes from the TDD PREFLIGHT marker when present."""

    def test_preflight_marker_returns_session_id(self):
        text = (
            "# 2026-05-18 19:15 - Claude\n\n"
            "[TDD PREFLIGHT: pipeline=SPEC session_id="
            "51e2f5c6-7853-4549-94e2-79c260f0c12a armed_at=2026-05-18T19:04:40Z]\n"
        )
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".md", delete=False
        ) as fh:
            fh.write(text)
            path = Path(fh.name)
        try:
            with mock.patch.object(_mod, "HANDOFF_PATH", path):
                task_id = _mod._current_task_id()
            self.assertEqual(task_id, "51e2f5c6-7853-4549-94e2-79c260f0c12a")
        finally:
            path.unlink(missing_ok=True)

    def test_missing_marker_falls_back_to_sha_plus_date(self):
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".md", delete=False
        ) as fh:
            fh.write("# 2026-05-18\n\nno preflight marker here\n")
            path = Path(fh.name)
        try:
            with mock.patch.object(_mod, "HANDOFF_PATH", path):
                task_id = _mod._current_task_id()
            self.assertTrue(task_id.startswith("fallback-"))
        finally:
            path.unlink(missing_ok=True)


class AuditEntriesForTaskTests(unittest.TestCase):
    """The hook reads JSONL audit entries filtered by task_id."""

    def _make_log(self, entries):
        fd, raw = tempfile.mkstemp(suffix=".jsonl")
        import os as _os
        _os.close(fd)
        path = Path(raw)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for entry in entries:
                fh.write(json.dumps(entry) + "\n")
        return path

    def test_returns_only_matching_task(self):
        log_path = self._make_log([
            {"file_path": "a.py", "task_id": "T1"},
            {"file_path": "b.py", "task_id": "T2"},
            {"file_path": "c.py", "task_id": "T1"},
        ])
        try:
            with mock.patch.object(_mod, "AUDIT_LOG_PATH", log_path):
                entries = _mod._audit_entries_for_task("T1")
            self.assertEqual({e["file_path"] for e in entries}, {"a.py", "c.py"})
        finally:
            log_path.unlink(missing_ok=True)

    def test_missing_log_returns_empty(self):
        missing = Path(tempfile.gettempdir()) / "definitely-missing.jsonl"
        if missing.exists():
            missing.unlink()
        with mock.patch.object(_mod, "AUDIT_LOG_PATH", missing):
            self.assertEqual(_mod._audit_entries_for_task("T1"), [])

    def test_malformed_lines_skipped(self):
        fd, raw = tempfile.mkstemp(suffix=".jsonl")
        import os as _os
        _os.close(fd)
        log_path = Path(raw)
        with log_path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write('not json at all\n')
            fh.write(json.dumps({"file_path": "ok.py", "task_id": "T1"}) + "\n")
        try:
            with mock.patch.object(_mod, "AUDIT_LOG_PATH", log_path):
                entries = _mod._audit_entries_for_task("T1")
            self.assertEqual([e["file_path"] for e in entries], ["ok.py"])
        finally:
            log_path.unlink(missing_ok=True)


class FailMessageTests(unittest.TestCase):
    """Rule F three-part FAIL messages contain what / why / unblock."""

    def test_fail_messages_include_three_parts(self):
        source = HOOK_PATH.read_text(encoding="utf-8")
        self.assertIn("FAIL check-resolved-history:", source)
        self.assertIn("WHY:", source)
        self.assertIn("UNBLOCK:", source)

    def test_doctrine_quotes_user_rule(self):
        source = HOOK_PATH.read_text(encoding="utf-8")
        self.assertIn("2026-05-18", source)
        self.assertIn("memory-only lookup", source.lower())


class StagedProductionFilesTests(unittest.TestCase):
    """The hook filters staged files to production prefixes."""

    def test_code_prefixes_match(self):
        for prefix in _mod._CODE_PREFIXES:
            self.assertTrue(
                prefix.endswith("/"),
                f"prefix {prefix!r} must end with / to avoid partial matches",
            )

    def test_non_source_paths_are_excluded(self):
        self.assertIn("AGENT-HANDOFF.md", _mod._NON_SOURCE_PATHS)
        self.assertIn("AI-CONTEXT.md", _mod._NON_SOURCE_PATHS)
        self.assertIn("docs/", _mod._NON_SOURCE_PATHS)


if __name__ == "__main__":
    unittest.main()
