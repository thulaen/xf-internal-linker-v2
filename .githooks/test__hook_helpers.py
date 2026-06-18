"""Unit tests for `.githooks/_hook_helpers.py`.

These tests cover the shared helpers extracted by paper-trail #585 /
test_case #703 so future hooks inherit UTF-8 + cache + production-source
discipline for free.

Run standalone:
    python .githooks/test__hook_helpers.py
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

# Make the helpers importable when the test runs from the repo root.
HOOK_DIR = Path(__file__).resolve().parent
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

import _hook_helpers  # noqa: E402  (path insertion above must happen first)


class GetStagedHandoffDiffTests(unittest.TestCase):
    """get_staged_handoff_diff() returns ADDED lines from staged AGENT-HANDOFF.md."""

    def test_returns_string(self):
        """Returns a string even when git is unavailable."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Not a git repo — git command will fail; helper returns "".
            result = _hook_helpers.get_staged_handoff_diff(root)
        self.assertIsInstance(result, str)

    def test_filters_to_added_lines_only(self):
        """Only `+` lines (excluding `+++` headers) are returned, with `+` stripped."""
        fake_diff = (
            "diff --git a/AGENT-HANDOFF.md b/AGENT-HANDOFF.md\n"
            "index 0000..1111 100644\n"
            "--- a/AGENT-HANDOFF.md\n"
            "+++ b/AGENT-HANDOFF.md\n"
            "@@ -1,3 +1,5 @@\n"
            "+new line one\n"
            "+new line two\n"
            "-removed line\n"
            " context line\n"
            "+new line three\n"
        )
        with mock.patch.object(_hook_helpers, "run_git", return_value=fake_diff):
            with tempfile.TemporaryDirectory() as tmp:
                result = _hook_helpers.get_staged_handoff_diff(Path(tmp))
        self.assertEqual(result, "new line one\nnew line two\nnew line three")

    def test_utf8_decoded_with_errors_replace(self):
        """The shared run_git uses errors=replace; helper inherits that fallback."""
        # Real subprocess test: pass bytes that would crash strict UTF-8 — the
        # `errors='replace'` arg in run_git means we get a string back.
        with mock.patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=["git"], returncode=0,
                stdout="+header line with replacement\n+normal line\n",
                stderr="",
            )
            with tempfile.TemporaryDirectory() as tmp:
                result = _hook_helpers.get_staged_handoff_diff(Path(tmp))
        self.assertIsInstance(result, str)
        self.assertIn("header line with replacement", result)
        self.assertIn("normal line", result)

    def test_returns_empty_when_git_missing(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            with tempfile.TemporaryDirectory() as tmp:
                result = _hook_helpers.get_staged_handoff_diff(Path(tmp))
        self.assertEqual(result, "")


class GetStagedFilesTests(unittest.TestCase):
    """get_staged_files() returns the staged-files list (alias for staged_paths)."""

    def test_returns_list_of_strings(self):
        with mock.patch.object(
            _hook_helpers, "run_git",
            return_value="path/one.py\npath/two.py\n",
        ):
            with tempfile.TemporaryDirectory() as tmp:
                result = _hook_helpers.get_staged_files(Path(tmp))
        self.assertEqual(result, ["path/one.py", "path/two.py"])

    def test_strips_blank_lines(self):
        with mock.patch.object(
            _hook_helpers, "run_git",
            return_value="path/one.py\n\n   \npath/two.py\n",
        ):
            with tempfile.TemporaryDirectory() as tmp:
                result = _hook_helpers.get_staged_files(Path(tmp))
        self.assertEqual(result, ["path/one.py", "path/two.py"])


class IsProductionSourceTests(unittest.TestCase):
    """is_production_source() matches the predicate from check-tdd-strict.py."""

    def test_backend_py_is_production(self):
        self.assertTrue(_hook_helpers.is_production_source("backend/apps/foo/views.py"))

    def test_frontend_ts_is_production(self):
        self.assertTrue(_hook_helpers.is_production_source(
            "frontend/src/app/foo/foo.component.ts"
        ))

    def test_githooks_py_is_production(self):
        self.assertTrue(_hook_helpers.is_production_source(".githooks/check-foo.py"))

    def test_services_go_is_production(self):
        self.assertTrue(_hook_helpers.is_production_source(
            "services/sidecars/cmd/main.go"
        ))

    def test_test_file_is_not_production(self):
        self.assertFalse(_hook_helpers.is_production_source(
            "backend/apps/foo/tests/test_views.py"
        ))

    def test_spec_file_is_not_production(self):
        self.assertFalse(_hook_helpers.is_production_source(
            "frontend/src/app/foo/foo.component.spec.ts"
        ))

    def test_go_test_file_is_not_production(self):
        self.assertFalse(_hook_helpers.is_production_source(
            "services/sidecars/internal/foo/foo_test.go"
        ))

    def test_generated_stubs_not_production(self):
        self.assertFalse(_hook_helpers.is_production_source(
            "backend/apps/_sidecars_pb/snapshotd/api_pb2.py"
        ))
        self.assertFalse(_hook_helpers.is_production_source(
            "services/sidecars/api/gen/snapshotd.pb.go"
        ))

    def test_docs_not_production(self):
        self.assertFalse(_hook_helpers.is_production_source("docs/SOME-RULE.md"))

    def test_handoff_not_production(self):
        self.assertFalse(_hook_helpers.is_production_source("AGENT-HANDOFF.md"))

    def test_non_prefix_path_not_production(self):
        # Paths outside the production prefixes are excluded.
        self.assertFalse(_hook_helpers.is_production_source("README.md"))


class ParseIso8601Tests(unittest.TestCase):
    """parse_iso8601() handles the Z-suffix form used by `date -u +%Y-%m-%dT%H:%M:%SZ`."""

    def test_with_z_suffix(self):
        dt = _hook_helpers.parse_iso8601("2026-05-17T16:40:32Z")
        self.assertEqual(dt, datetime(2026, 5, 17, 16, 40, 32, tzinfo=timezone.utc))

    def test_with_offset(self):
        dt = _hook_helpers.parse_iso8601("2026-05-17T16:40:32+00:00")
        self.assertEqual(dt, datetime(2026, 5, 17, 16, 40, 32, tzinfo=timezone.utc))

    def test_naive_assumes_utc(self):
        dt = _hook_helpers.parse_iso8601("2026-05-17T16:40:32")
        self.assertEqual(dt, datetime(2026, 5, 17, 16, 40, 32, tzinfo=timezone.utc))

    def test_empty_returns_none(self):
        self.assertIsNone(_hook_helpers.parse_iso8601(""))

    def test_invalid_returns_none(self):
        self.assertIsNone(_hook_helpers.parse_iso8601("not a timestamp"))


class CachedVerifierTests(unittest.TestCase):
    """cached_verifier() memoizes verifier results by ID."""

    def test_memoizes_by_id(self):
        call_count = {"n": 0}

        def fake_verify(entry_id: int) -> dict:
            call_count["n"] += 1
            return {"id": entry_id, "ok": True}

        verifier = _hook_helpers.cached_verifier(fake_verify)
        verifier(703)
        verifier(703)  # Should hit cache.
        verifier(704)
        self.assertEqual(call_count["n"], 2)  # Two unique IDs.

    def test_different_callers_independent_caches(self):
        log_a = []
        log_b = []
        verifier_a = _hook_helpers.cached_verifier(lambda i: log_a.append(i) or {"i": i})
        verifier_b = _hook_helpers.cached_verifier(lambda i: log_b.append(i) or {"i": i})
        verifier_a(1)
        verifier_a(1)
        verifier_b(1)
        verifier_b(1)
        self.assertEqual(log_a, [1])
        self.assertEqual(log_b, [1])


class ConstantsExposedTests(unittest.TestCase):
    """The constants previously duplicated across hooks live here now."""

    def test_production_prefixes_exposed(self):
        self.assertIn("backend/", _hook_helpers.PRODUCTION_PREFIXES)
        self.assertIn(".githooks/", _hook_helpers.PRODUCTION_PREFIXES)
        self.assertIn("services/", _hook_helpers.PRODUCTION_PREFIXES)

    def test_test_file_patterns_exposed(self):
        # Constant exists and is non-empty.
        self.assertTrue(len(_hook_helpers.TEST_FILE_PATTERNS) > 0)

    def test_generated_patterns_exposed(self):
        self.assertTrue(len(_hook_helpers.GENERATED_PATTERNS) > 0)


class BackendRunnerTests(unittest.TestCase):
    def test_shell_batch_verify_uses_shared_backend_runner(self):
        seen = {}

        def fake_run(command, **_kwargs):
            seen["command"] = command
            return subprocess.CompletedProcess(command, 0, '{"ok": true}', "")

        with mock.patch.object(_hook_helpers.subprocess, "run", fake_run):
            result = _hook_helpers.shell_batch_verify({"tdd_lessons": [1, 2]})

        self.assertEqual(result, {"ok": True})
        self.assertIn("backend_manage.py", seen["command"][1])
        self.assertNotIn("docker", seen["command"])

    def test_file_finding_uses_shared_backend_runner(self):
        seen = {}
        payload = {
            "category": "quality",
            "severity": "high",
            "subject": "scripts/example.py:12",
            "message": "This test message is long enough to pass validation.",
        }

        def fake_run(command, **_kwargs):
            seen["command"] = command
            return subprocess.CompletedProcess(command, 0, "[HOOK FINDING FILED: AutoIssue=#1]", "")

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(_hook_helpers.subprocess, "run", fake_run):
                result = _hook_helpers._run_file_hook_finding_command(
                    payload,
                    Path(tmp),
                    "codex",
                    10,
                )

        self.assertEqual(result.returncode, 0)
        self.assertIn("backend_manage.py", seen["command"][1])
        self.assertNotIn("docker", seen["command"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
