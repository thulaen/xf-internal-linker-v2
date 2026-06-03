"""Tests for scripts/run_quality_step.py.

BDD:
  Given a check_type that mentions test, mutation, or fuzz
  When _is_test_like() runs
  Then it returns True; otherwise False

  Given a non-empty raw report
  When _failure_summary() runs
  Then it returns a whitespace-collapsed string capped at 600 chars

  Given a command that times out
  When the runner catches TimeoutExpired
  Then the return code is exactly 124
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from unittest import TestCase, mock

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
_MODULE_PATH = _SCRIPTS_DIR / "run_quality_step.py"


def _load():
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("run_quality_step", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_quality_step"] = mod
    spec.loader.exec_module(mod)
    return mod


rqs = _load()


class TestStatusName(TestCase):
    def test_passed_on_zero(self) -> None:
        self.assertEqual(rqs._status_name(0), "passed")

    def test_failed_on_nonzero(self) -> None:
        self.assertEqual(rqs._status_name(1), "failed")
        self.assertEqual(rqs._status_name(124), "failed")


class TestIsTestLike(TestCase):
    def test_true_for_test(self) -> None:
        self.assertTrue(rqs._is_test_like("unit-test"))

    def test_true_for_mutation(self) -> None:
        self.assertTrue(rqs._is_test_like("Mutation"))

    def test_true_for_fuzz(self) -> None:
        self.assertTrue(rqs._is_test_like("FUZZ"))

    def test_false_for_lint(self) -> None:
        self.assertFalse(rqs._is_test_like("lint"))

    def test_false_for_coverage(self) -> None:
        self.assertFalse(rqs._is_test_like("coverage"))


class TestFailureSummary(TestCase):
    def test_fallback_when_empty(self) -> None:
        report = mock.Mock()
        report.read_text.return_value = "   "
        self.assertEqual(rqs._failure_summary(report, "fb"), "fb")

    def test_collapses_whitespace(self) -> None:
        report = mock.Mock()
        report.read_text.return_value = "line one\n   line   two"
        self.assertEqual(rqs._failure_summary(report, "fb"), "line one line two")

    def test_caps_at_600_chars(self) -> None:
        report = mock.Mock()
        report.read_text.return_value = "x" * 1000
        self.assertEqual(len(rqs._failure_summary(report, "fb")), 600)


class TestSummary(TestCase):
    def test_pass_summary_on_zero(self) -> None:
        args = argparse.Namespace(pass_summary="all good", fail_summary="bad")
        self.assertEqual(rqs._summary(args, 0), "all good")

    def test_fail_summary_names_exit_code(self) -> None:
        args = argparse.Namespace(pass_summary="all good", fail_summary="bad")
        self.assertEqual(rqs._summary(args, 7), "bad Exit code was 7.")


class TestArtifactDir(TestCase):
    def test_default_dir(self) -> None:
        with mock.patch.dict(rqs.os.environ, {}, clear=False):
            rqs.os.environ.pop("XF_TEST_ARTIFACT_DIR", None)
            self.assertEqual(rqs._artifact_dir(), Path("/tmp/xf-test-artifacts"))

    def test_env_override(self) -> None:
        with mock.patch.dict(rqs.os.environ, {"XF_TEST_ARTIFACT_DIR": "/custom"}):
            self.assertEqual(rqs._artifact_dir(), Path("/custom"))


class TestFileTestFailure(TestCase):
    def _args(self, **over) -> argparse.Namespace:
        base = dict(
            check_type="unit-test",
            tool_name="pytest",
            file_path="scripts/foo.py",
            command="pytest scripts/foo.py",
            pass_summary="ok",
            fail_summary="bad",
        )
        base.update(over)
        return argparse.Namespace(**base)

    def test_no_op_on_success(self) -> None:
        with mock.patch.object(rqs.subprocess, "run") as run:
            rqs._file_test_failure(self._args(), 0, mock.Mock())
        run.assert_not_called()

    def test_no_op_when_not_test_like(self) -> None:
        with mock.patch.object(rqs.subprocess, "run") as run:
            rqs._file_test_failure(self._args(check_type="lint"), 1, mock.Mock())
        run.assert_not_called()

    def test_disabled_by_env(self) -> None:
        with mock.patch.dict(
            rqs.os.environ, {"XF_AUTOISSUE_ON_TEST_FAILURE": "0"}
        ), mock.patch.object(rqs.subprocess, "run") as run:
            rqs._file_test_failure(self._args(), 1, mock.Mock())
        run.assert_not_called()
