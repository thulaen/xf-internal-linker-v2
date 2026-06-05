"""Tests for .githooks/check-gh-actions-read.py."""

from __future__ import annotations

import importlib.util
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

HOOKS_DIR = Path(__file__).resolve().parent
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def _load_hook():
    hook_path = HOOKS_DIR / "check-gh-actions-read.py"
    spec = importlib.util.spec_from_file_location("check_gh_actions_read", hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_gh_actions_read"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _capture_stderr(func, *args, **kwargs):
    buf = io.StringIO()
    with patch.object(sys, "stderr", buf):
        rv = func(*args, **kwargs)
    return rv, buf.getvalue()


class ValidateTests(TestCase):
    def test_hard_blocks_without_marker(self) -> None:
        diff = "[SNAPSHOTS READ: 0 snapshots attached to 0 open issues — picked: (none)]"

        rv, err = _capture_stderr(hook.validate, diff)

        self.assertEqual(rv, 2)
        self.assertIn("missing the [GH ACTIONS READ:", err)
        self.assertIn("UNBLOCK:", err)

    def test_passes_with_correct_marker_format(self) -> None:
        diff = (
            "[SNAPSHOTS READ: 0 snapshots attached to 0 open issues — picked: (none)]\n"
            "[GH ACTIONS READ: 5 failures since last handoff — picked: #5, #4, #3]"
        )

        rv, err = _capture_stderr(hook.validate, diff)

        self.assertEqual(rv, 0, msg=err)

    def test_passes_when_zero_failures_with_zero_marker(self) -> None:
        diff = (
            "[SNAPSHOTS READ: 0 snapshots attached to 0 open issues — picked: (none)]\n"
            "[GH ACTIONS READ: 0 failures since last handoff — picked: none]"
        )

        rv, err = _capture_stderr(hook.validate, diff)

        self.assertEqual(rv, 0, msg=err)


class MainTests(TestCase):
    def test_main_soft_files_when_missing_marker(self) -> None:
        stdout = io.StringIO()
        with (
            patch.object(hook, "_staged_files", return_value=["backend/a.py"]),
            patch.object(hook, "_read_staged_handoff_diff", return_value="[SNAPSHOTS READ: skipped]"),
            patch("_hook_helpers.file_finding_as_autoissue", return_value=456),
            patch.dict(os.environ, {"XF_QUALITY_ENV": "local"}, clear=False),
            patch.object(sys, "stdout", stdout),
        ):
            rv = hook.main()

        self.assertEqual(rv, 0)
        self.assertIn("[FINDING FILED: hook=check-gh-actions-read autoissue=#456 severity=low]", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
