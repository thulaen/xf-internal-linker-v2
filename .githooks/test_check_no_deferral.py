#!/usr/bin/env python3
"""Tests for ``.githooks/check-no-deferral.py``.

These tests stub ``subprocess.run`` and the helper module's private
functions so no live Docker or git calls are needed.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


_HOOK_PATH = Path(__file__).resolve().parent / "check-no-deferral.py"


def _load_hook_module():
    spec = importlib.util.spec_from_file_location(
        "check_no_deferral_under_test", _HOOK_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load check-no-deferral.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook_module()


class HappyPathTests(unittest.TestCase):
    def test_no_phrases_no_todos_returns_zero(self) -> None:
        with patch.object(
            hook, "_staged_handoff_diff", return_value="Routine work landed cleanly."
        ), patch.object(hook, "_staged_files", return_value=[]):
            self.assertEqual(hook.main(), 0)


class ForbiddenPhraseTests(unittest.TestCase):
    def _run_with_handoff(self, body: str) -> tuple[int, str]:
        captured: list[str] = []

        class _Bucket:
            def write(self, msg: str) -> int:  # noqa: D401
                captured.append(msg)
                return len(msg)

            def flush(self) -> None:  # pragma: no cover
                return None

        with patch.object(
            hook, "_staged_handoff_diff", return_value=body
        ), patch.object(hook, "_staged_files", return_value=[]), patch.object(
            hook.sys, "stderr", new=_Bucket()
        ):
            rc = hook.main()
        return rc, "".join(captured)

    def test_postponed_phrase_blocks(self) -> None:
        rc, out = self._run_with_handoff("This work was postponed for next month.")
        self.assertEqual(rc, 2)
        self.assertIn("postponed", out.lower())

    def test_out_of_scope_blocks(self) -> None:
        rc, out = self._run_with_handoff("That work is out-of-scope here.")
        self.assertEqual(rc, 2)
        self.assertIn("out-of-scope", out.lower())

    def test_not_in_this_session_blocks(self) -> None:
        rc, out = self._run_with_handoff("That fix is not in this session.")
        self.assertEqual(rc, 2)
        self.assertIn("not in this session", out.lower())


class TodoCommentTests(unittest.TestCase):
    def _run_with_file(self, path: str, blob: str) -> tuple[int, str]:
        captured: list[str] = []

        class _Bucket:
            def write(self, msg: str) -> int:  # noqa: D401
                captured.append(msg)
                return len(msg)

            def flush(self) -> None:  # pragma: no cover
                return None

        with patch.object(
            hook, "_staged_handoff_diff", return_value=""
        ), patch.object(hook, "_staged_files", return_value=[path]), patch.object(
            hook, "_staged_blob", return_value=blob
        ), patch.object(hook.sys, "stderr", new=_Bucket()):
            rc = hook.main()
        return rc, "".join(captured)

    def test_bare_todo_in_python_comment_blocks(self) -> None:
        rc, out = self._run_with_file(
            "backend/example.py", "# TODO: revisit this branch\n"
        )
        self.assertEqual(rc, 2)
        self.assertIn("TODO", out)
        self.assertIn("backend/example.py", out)

    def test_linked_todo_with_existing_row_passes(self) -> None:
        # _row_exists returns True for known ids; we stub it.
        with patch.object(hook, "_row_exists", return_value=True):
            rc, out = self._run_with_file(
                "backend/example.py",
                "# TODO(paper-trail #42): revisit when the spec lands\n",
            )
        self.assertEqual(rc, 0, msg=out)

    def test_linked_todo_with_missing_row_blocks(self) -> None:
        with patch.object(hook, "_row_exists", return_value=False):
            rc, out = self._run_with_file(
                "backend/example.py",
                "# TODO(AutoIssue #999999): the row does not exist\n",
            )
        self.assertEqual(rc, 2)
        self.assertIn("non-existent", out)

    def test_todo_outside_a_comment_does_not_block(self) -> None:
        # A `TODO` inside ordinary code (not a comment) must not trip.
        rc, out = self._run_with_file(
            "backend/example.py", "TODO = 'a constant name'\n"
        )
        self.assertEqual(rc, 0, msg=out)

    def test_bare_fixme_in_js_comment_blocks(self) -> None:
        rc, out = self._run_with_file(
            "frontend/src/x.ts", "// FIXME: handle the empty case\n"
        )
        self.assertEqual(rc, 2)
        self.assertIn("FIXME", out)


class MultiViolationTests(unittest.TestCase):
    def test_multiple_violations_are_all_listed(self) -> None:
        captured: list[str] = []

        class _Bucket:
            def write(self, msg: str) -> int:  # noqa: D401
                captured.append(msg)
                return len(msg)

            def flush(self) -> None:  # pragma: no cover
                return None

        handoff = "Work was postponed.\nAlso out-of-scope this round.\n"
        with patch.object(
            hook, "_staged_handoff_diff", return_value=handoff
        ), patch.object(hook, "_staged_files", return_value=[]), patch.object(
            hook.sys, "stderr", new=_Bucket()
        ):
            rc = hook.main()
        joined = "".join(captured)
        self.assertEqual(rc, 2)
        self.assertIn("postponed", joined.lower())
        self.assertIn("out-of-scope", joined.lower())


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))
