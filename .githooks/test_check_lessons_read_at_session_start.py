"""Tests for .githooks/check-lessons-read-at-session-start.py.

Written FIRST. Each test names the behaviour the hook must guarantee.
"""

from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def _load_hook():
    hook_path = HOOKS_DIR / "check-lessons-read-at-session-start.py"
    spec = importlib.util.spec_from_file_location("check_lessons_read", hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_lessons_read"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _capture_stderr(func, *args, **kwargs):
    buf = io.StringIO()
    with patch.object(sys, "stderr", buf):
        rv = func(*args, **kwargs)
    return rv, buf.getvalue()


class ValidateTests(TestCase):
    def test_full_marker_passes(self) -> None:
        diff = (
            "[HANDOFF READ: 2026-05-17 by Claude — slice 1.6]\n"
            "[REGISTRY READ: 3 open]\n"
            "[PAPER TRAIL READ: 47 open]\n"
            "[LESSONS BEFORE START: 5 resolved-lesson rows reviewed in "
            "backend/apps/auto_issues, .githooks, services/sidecars]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 0, msg=err)

    def test_zero_lessons_skipped_form_passes(self) -> None:
        diff = (
            "[REGISTRY READ: 3 open]\n"
            "[LESSONS BEFORE START: 0 resolved-lesson rows reviewed in "
            "<no-prior-fixes-in-touched-area>]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 0, msg=err)

    def test_marker_missing_fails(self) -> None:
        diff = (
            "[REGISTRY READ: 3 open]\n"
            "[PAPER TRAIL READ: 47 open]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 2)
        self.assertIn("LESSONS BEFORE START", err)
        self.assertIn("UNBLOCK", err)

    def test_marker_with_bad_shape_fails(self) -> None:
        diff = "[LESSONS BEFORE START: I forgot the count]"
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 2)
        self.assertIn("body shape", err)

    def test_marker_before_registry_read_fails(self) -> None:
        diff = (
            "[LESSONS BEFORE START: 3 resolved-lesson rows reviewed in backend/]\n"
            "[REGISTRY READ: 3 open]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 2)
        self.assertIn("BEFORE", err.upper())


class IsCodeChangingTests(TestCase):
    def test_backend_is_code_changing(self) -> None:
        self.assertTrue(hook.is_code_changing(["backend/apps/foo.py"]))

    def test_docs_only_is_not(self) -> None:
        self.assertFalse(hook.is_code_changing(["docs/x.md", "README.md"]))

    def test_services_is_code_changing(self) -> None:
        self.assertTrue(hook.is_code_changing(["services/sidecars/cmd/sidecars/main.go"]))


class MainTests(TestCase):
    def test_main_with_no_staged_files_returns_zero(self) -> None:
        with patch.object(hook, "_staged_files", return_value=[]):
            self.assertEqual(hook.main(), 0)

    def test_main_with_docs_only_returns_zero(self) -> None:
        with patch.object(hook, "_staged_files", return_value=["docs/x.md"]):
            self.assertEqual(hook.main(), 0)

    def test_main_with_code_change_and_missing_marker_returns_two(self) -> None:
        diff = "[REGISTRY READ: 3 open]"
        with (
            patch.object(hook, "_staged_files", return_value=["backend/a.py"]),
            patch.object(hook, "_read_staged_handoff_diff", return_value=diff),
        ):
            rv, err = _capture_stderr(hook.main)
            self.assertEqual(rv, 2)
            self.assertIn("LESSONS BEFORE START", err)


if __name__ == "__main__":
    unittest.main()
