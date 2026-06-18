"""Tests for the CodeQL AutoIssue commit check."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("check-codeql-autoissues.py")
spec = importlib.util.spec_from_file_location("check_codeql_autoissues", MODULE_PATH)
assert spec and spec.loader
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class CheckCodeQLAutoIssuesTests(unittest.TestCase):
    def test_passes_when_backend_verifier_passes(self) -> None:
        with patch.object(hook.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(hook.main(), 0)
            command = run.call_args.args[0]
            self.assertIn("scripts/backend_manage.py", command)
            self.assertNotIn("docker", command)

    def test_fails_when_backend_verifier_fails(self) -> None:
        with patch.object(hook.subprocess, "run") as run:
            run.return_value.returncode = 1
            self.assertEqual(hook.main(), 1)


if __name__ == "__main__":
    unittest.main()
