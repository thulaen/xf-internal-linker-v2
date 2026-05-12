"""Tests for the ci_failed_runs picker — Phase 6 of the test-hardening plan.

Verifies graceful fallback when the `gh` CLI is unavailable. The real
upsert path is exercised in the integration tests that run with a
mocked `subprocess.run`.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.auto_issues.services import ci_failed_runs


class CiFailedRunsPickerTests(SimpleTestCase):
    def test_gh_unavailable_returns_zero(self) -> None:
        with patch.object(ci_failed_runs.subprocess, "run", side_effect=FileNotFoundError):
            self.assertEqual(ci_failed_runs.pick_ci_failed_runs(), 0)

    def test_gh_non_zero_exit_returns_zero(self) -> None:
        fake_result = type("R", (), {"returncode": 1, "stdout": "", "stderr": "no remote"})()
        with patch.object(ci_failed_runs.subprocess, "run", return_value=fake_result):
            self.assertEqual(ci_failed_runs.pick_ci_failed_runs(), 0)

    def test_gh_empty_json_returns_zero(self) -> None:
        fake_result = type("R", (), {"returncode": 0, "stdout": "[]", "stderr": ""})()
        with patch.object(ci_failed_runs.subprocess, "run", return_value=fake_result):
            self.assertEqual(ci_failed_runs.pick_ci_failed_runs(), 0)

    def test_gh_unparseable_json_returns_zero(self) -> None:
        fake_result = type("R", (), {"returncode": 0, "stdout": "not json", "stderr": ""})()
        with patch.object(ci_failed_runs.subprocess, "run", return_value=fake_result):
            self.assertEqual(ci_failed_runs.pick_ci_failed_runs(), 0)
