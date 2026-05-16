"""Tests for the per-module coverage hook."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock


HOOK_PATH = Path(__file__).resolve().with_name("check-per-module-coverage.py")
SPEC = importlib.util.spec_from_file_location("check_per_module_coverage", HOOK_PATH)
assert SPEC is not None
check_per_module_coverage = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_per_module_coverage)


class PerModuleCoverageHookTests(TestCase):
    def test_measure_ignores_repo_wide_pytest_coverage_defaults(self) -> None:
        calls: list[list[str]] = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            if cmd[:2] == ["coverage", "report"]:
                return SimpleNamespace(stdout="TOTAL  10  1  90.0%\n", returncode=0)
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        with mock.patch.object(check_per_module_coverage.subprocess, "run", side_effect=fake_run):
            self.assertEqual(check_per_module_coverage._measure("backend/apps/x.py"), 90.0)

        coverage_run = next(cmd for cmd in calls if cmd[:2] == ["coverage", "run"])
        self.assertIn("--override-ini", coverage_run)
        self.assertIn("addopts=", coverage_run)
        self.assertNotIn("--cov=apps", coverage_run)
        self.assertNotIn("--cov=config", coverage_run)


if __name__ == "__main__":
    import unittest

    unittest.main()
