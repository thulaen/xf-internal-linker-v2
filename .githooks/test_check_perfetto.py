"""Tests for the Perfetto AutoIssue commit check."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("check-perfetto.py")
spec = importlib.util.spec_from_file_location("check_perfetto", MODULE_PATH)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class CheckPerfettoTests(unittest.TestCase):
    def test_passes_when_backend_verifier_passes(self) -> None:
        with patch.object(hook.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "[PERFETTO AUTOISSUES VERIFIED: open=0 max=10]"
            run.return_value.stderr = ""
            self.assertEqual(hook.main(), 0)

    def test_fails_when_backend_verifier_fails(self) -> None:
        with patch.object(hook.subprocess, "run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            run.return_value.stderr = "2 open: #4, #5"
            self.assertEqual(hook.main(), 1)

    def test_fails_plainly_when_docker_missing(self) -> None:
        with patch.object(hook.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(hook.main(), 1)

    def test_fail_message_has_three_parts(self) -> None:
        with patch.object(hook.sys.stderr, "write") as werr:
            hook._fail("detail here")
        written = "".join(call.args[0] for call in werr.call_args_list)
        self.assertIn("FAIL check-perfetto", written)
        self.assertIn("WHY:", written)
        self.assertIn("UNBLOCK:", written)


if __name__ == "__main__":
    unittest.main()
