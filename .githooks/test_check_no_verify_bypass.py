"""Tests for .githooks/check-no-verify-bypass.py (Patch C, 2026-05-16).

Five focused cases:
  1. No stdin input -> hook passes silently (exit 0)
  2. Code-changing commit that also touched AGENT-HANDOFF.md -> pass
  3. Code-changing commit that did NOT touch AGENT-HANDOFF.md -> FAIL
  4. Docs-only commit (no production source touched) -> pass
  5. Branch deletion (local_sha is all-zeros) -> pass

The hook's git calls are stubbed so the test does not rely on the real
repository history.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def _load_hook():
    module_name = "check_no_verify_bypass"
    path = HOOKS_DIR / "check-no-verify-bypass.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


class NoVerifyBypassTests(TestCase):

    def test_no_stdin_input_passes(self) -> None:
        self.assertEqual(hook.main(stdin_lines=[]), 0)

    def test_commit_touching_handoff_is_compliant(self) -> None:
        stdin = ["refs/heads/main aaaa1111 refs/heads/main bbbb2222\n"]
        # Stub git: one commit aaaa1111 that touched both a source file AND
        # the handoff. That counts as compliant.
        def fake_git(args):
            joined = " ".join(args)
            if "rev-list" in joined:
                return "aaaa1111\n"
            if "--name-only" in joined:
                return "backend/apps/realtime/x.py\nAGENT-HANDOFF.md\n"
            if "--format=%s" in joined:
                return "Slice update with handoff\n"
            return ""
        with patch.object(hook, "_git", side_effect=fake_git):
            self.assertEqual(hook.main(stdin_lines=stdin), 0)

    def test_bypass_commit_without_handoff_is_blocked(self) -> None:
        stdin = ["refs/heads/main aaaa1111 refs/heads/main bbbb2222\n"]
        def fake_git(args):
            joined = " ".join(args)
            if "rev-list" in joined:
                return "aaaa1111\n"
            if "--name-only" in joined:
                # Source touched but NO handoff.
                return "backend/apps/realtime/x.py\nbackend/apps/realtime/y.py\n"
            if "--format=%s" in joined:
                return "Snuck in via --no-verify\n"
            return ""
        captured = io.StringIO()
        with patch.object(hook, "_git", side_effect=fake_git), \
             patch.object(hook.sys, "stderr", captured):
            rc = hook.main(stdin_lines=stdin)
        self.assertEqual(rc, 2)
        text = captured.getvalue()
        self.assertIn("FAIL check-no-verify-bypass", text)
        self.assertIn("WHY:", text)
        self.assertIn("UNBLOCK:", text)
        self.assertIn("--no-verify", text)
        self.assertIn("backend/apps/realtime/x.py", text)

    def test_later_handoff_commit_that_names_sha_covers_source_commit(self) -> None:
        stdin = ["refs/heads/main handoff999 refs/heads/main bbbb2222\n"]

        def fake_git(args):
            joined = " ".join(args)
            if "rev-list" in joined:
                return "handoff999\nsource111\n"
            if "--name-only" in joined and "handoff999" in joined:
                return "AGENT-HANDOFF.md\n"
            if "--name-only" in joined and "source111" in joined:
                return "backend/apps/realtime/x.py\n"
            if "handoff999:AGENT-HANDOFF.md" in joined:
                return "Push ledger: source111 changed realtime routing with tests.\n"
            if "--format=%s" in joined:
                return "source commit\n"
            return ""

        with patch.object(hook, "_git", side_effect=fake_git):
            self.assertEqual(hook.main(stdin_lines=stdin), 0)

    def test_generic_later_handoff_commit_does_not_cover_source_commit(self) -> None:
        stdin = ["refs/heads/main handoff999 refs/heads/main bbbb2222\n"]

        def fake_git(args):
            joined = " ".join(args)
            if "rev-list" in joined:
                return "handoff999\nsource111\n"
            if "--name-only" in joined and "handoff999" in joined:
                return "AGENT-HANDOFF.md\n"
            if "--name-only" in joined and "source111" in joined:
                return "backend/apps/realtime/x.py\n"
            if "handoff999:AGENT-HANDOFF.md" in joined:
                return "Generic handoff with no commit reference.\n"
            if "--format=%s" in joined:
                return "source commit\n"
            return ""

        captured = io.StringIO()
        with patch.object(hook, "_git", side_effect=fake_git), \
             patch.object(hook.sys, "stderr", captured):
            self.assertEqual(hook.main(stdin_lines=stdin), 2)
        self.assertIn("source111", captured.getvalue())

    def test_docs_only_commit_passes_without_handoff(self) -> None:
        stdin = ["refs/heads/main aaaa1111 refs/heads/main bbbb2222\n"]
        def fake_git(args):
            joined = " ".join(args)
            if "rev-list" in joined:
                return "aaaa1111\n"
            if "--name-only" in joined:
                return "docs/README.md\ndocs/MODULAR-MONOLITH.md\n"
            if "--format=%s" in joined:
                return "Docs only\n"
            return ""
        with patch.object(hook, "_git", side_effect=fake_git):
            self.assertEqual(hook.main(stdin_lines=stdin), 0)

    def test_branch_deletion_passes(self) -> None:
        zero = "0" * 40
        stdin = [f"refs/heads/main {zero} refs/heads/main bbbb2222\n"]
        with patch.object(hook, "_git", side_effect=lambda args: ""):
            self.assertEqual(hook.main(stdin_lines=stdin), 0)

    def test_test_only_commit_passes_without_handoff(self) -> None:
        """Test-file-only commits do not need a handoff marker; the test
        file itself is the change."""
        stdin = ["refs/heads/main aaaa1111 refs/heads/main bbbb2222\n"]
        def fake_git(args):
            joined = " ".join(args)
            if "rev-list" in joined:
                return "aaaa1111\n"
            if "--name-only" in joined:
                return "backend/apps/realtime/tests_streamd_client.py\n"
            if "--format=%s" in joined:
                return "Add tests\n"
            return ""
        with patch.object(hook, "_git", side_effect=fake_git):
            self.assertEqual(hook.main(stdin_lines=stdin), 0)


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
