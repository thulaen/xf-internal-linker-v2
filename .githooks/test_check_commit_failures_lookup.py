"""Unit tests for check-commit-failures-lookup.py.

Test-first per the 2026-05-18 user directive: agents must look up prior
commit failures before committing, just as they must look up resolved
issues before editing code. The hook is the disk-backed enforcement.

The hook is loaded via importlib because the filename uses a hyphen.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOOK_PATH = Path(__file__).resolve().parent / "check-commit-failures-lookup.py"
_spec = importlib.util.spec_from_file_location(
    "check_commit_failures_lookup", HOOK_PATH
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["check_commit_failures_lookup"] = _mod
_spec.loader.exec_module(_mod)


class TaskIdResolutionTests(unittest.TestCase):
    """Task ID comes from the TDD PREFLIGHT marker when present."""

    def test_preflight_marker_returns_session_id(self):
        text = (
            "# 2026-05-18 22:00 - Claude\n\n"
            "[TDD PREFLIGHT: pipeline=SPEC session_id="
            "5b57d1bc-82a5-44b4-ab75-2f2e499133d0 armed_at=2026-05-18T22:04:20Z]\n"
        )
        fd, raw = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        path = Path(raw)
        try:
            path.write_text(text, encoding="utf-8")
            with mock.patch.object(_mod, "HANDOFF_PATH", path):
                task_id = _mod._current_task_id()
            self.assertEqual(task_id, "5b57d1bc-82a5-44b4-ab75-2f2e499133d0")
        finally:
            path.unlink(missing_ok=True)


class AuditLogReadingTests(unittest.TestCase):
    """The hook reads JSONL audit entries filtered by task_id."""

    def _make_log(self, entries):
        fd, raw = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        path = Path(raw)
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            for entry in entries:
                fh.write(json.dumps(entry) + "\n")
        return path

    def test_one_entry_for_task_passes(self):
        log_path = self._make_log([
            {"task_id": "T1", "result_count": 4, "looked_up_at": "2026-05-18T22:00:00Z"},
        ])
        try:
            with mock.patch.object(_mod, "AUDIT_LOG_PATH", log_path):
                count = _mod._lookup_count_for_task("T1")
            self.assertEqual(count, 1)
        finally:
            log_path.unlink(missing_ok=True)

    def test_zero_entries_for_task_means_no_lookup(self):
        log_path = self._make_log([
            {"task_id": "OTHER", "result_count": 0},
        ])
        try:
            with mock.patch.object(_mod, "AUDIT_LOG_PATH", log_path):
                count = _mod._lookup_count_for_task("T1")
            self.assertEqual(count, 0)
        finally:
            log_path.unlink(missing_ok=True)

    def test_missing_log_returns_zero(self):
        missing = Path(tempfile.gettempdir()) / "definitely-missing-cf.jsonl"
        if missing.exists():
            missing.unlink()
        with mock.patch.object(_mod, "AUDIT_LOG_PATH", missing):
            self.assertEqual(_mod._lookup_count_for_task("T1"), 0)


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


class FailMessageTests(unittest.TestCase):
    """Rule F three-part FAIL messages contain what / why / unblock."""

    def test_fail_messages_include_three_parts(self):
        source = HOOK_PATH.read_text(encoding="utf-8")
        self.assertIn("FAIL check-commit-failures-lookup:", source)
        self.assertIn("WHY:", source)
        self.assertIn("UNBLOCK:", source)

    def test_doctrine_quotes_user_rule(self):
        source = HOOK_PATH.read_text(encoding="utf-8")
        self.assertIn("2026-05-18", source)
        self.assertIn("commit failure", source.lower())


if __name__ == "__main__":
    unittest.main()
