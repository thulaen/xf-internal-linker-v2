"""Tests for .githooks/check-tdd-strict.py (PARAMOUNT strict-TDD rule).

Written FIRST per the rule the hook itself enforces. Each test names the
behaviour the hook must guarantee; the hook implementation follows.
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
    hook_path = HOOKS_DIR / "check-tdd-strict.py"
    spec = importlib.util.spec_from_file_location("check_tdd_strict", hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_tdd_strict"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _capture_stderr(func, *args, **kwargs):
    buf = io.StringIO()
    with patch.object(sys, "stderr", buf):
        rv = func(*args, **kwargs)
    return rv, buf.getvalue()


_GOOD_MARKER = (
    "[TDD CYCLE STRICT: file=backend/apps/foo.py "
    "red=backend/apps/test_foo.py:10 red_run_at=2026-05-17T04:01:12Z "
    "red_result=FAIL green=backend/apps/foo.py:5 "
    "green_run_at=2026-05-17T04:02:30Z green_result=PASS "
    'refactor="none" lesson_autoissue=#42]'
)

# 2026-05-17 — paired coverage marker required per the 5-layer rule.
_GOOD_COVERAGE = (
    "[TDD COVERAGE: file=backend/apps/foo.py edge_cases=2 "
    "resource_release=1 latency=1 smoke=1 e2e=1]"
)

# Combined good markers — the pair the hook expects per touched file.
_FULL_GOOD = _GOOD_MARKER + "\n" + _GOOD_COVERAGE

_REFACTOR_ONLY_MARKER = (
    "[REFACTOR ONLY: file=backend/apps/foo.py "
    "green_run_at=2026-05-17T04:02:30Z green_result=PASS "
    "regression_test=backend/apps/test_foo.py:10 lesson_autoissue=#42]"
)
_REFACTOR_ONLY_COVERAGE = (
    "[TDD COVERAGE: file=backend/apps/foo.py edge_cases=0 "
    'resource_release=N/A:"pure rename refactor that does not add state" '
    'latency=N/A:"refactor does not change algorithmic complexity" '
    "smoke=1 "
    'e2e=N/A:"refactor preserves behaviour; existing E2E suite covers it"]'
)
_FULL_REFACTOR_GOOD = _REFACTOR_ONLY_MARKER + "\n" + _REFACTOR_ONLY_COVERAGE

_TRIVIAL_MARKER = (
    "[TRIVIAL CHANGE: file=backend/apps/foo.py "
    'reason="typo fix in the user-facing error message; no behaviour change"]'
)


class MarkerParsingTests(TestCase):
    """The strict marker shape MUST satisfy each subfield contract."""

    def test_well_formed_marker_parses_cleanly(self) -> None:
        parsed = hook.parse_strict_markers(_GOOD_MARKER)
        self.assertEqual(len(parsed), 1)
        m = parsed[0]
        self.assertEqual(m["file"], "backend/apps/foo.py")
        self.assertEqual(m["red_result"], "FAIL")
        self.assertEqual(m["green_result"], "PASS")
        self.assertEqual(m["lesson_autoissue"], 42)
        self.assertLess(m["red_run_at"], m["green_run_at"])

    def test_refactor_only_marker_parses(self) -> None:
        parsed = hook.parse_strict_markers(_REFACTOR_ONLY_MARKER)
        self.assertEqual(len(parsed), 1)
        self.assertTrue(parsed[0].get("refactor_only"))

    def test_two_markers_in_one_diff(self) -> None:
        diff = _GOOD_MARKER + "\n" + _GOOD_MARKER.replace("foo.py", "bar.py").replace("#42", "#43")
        parsed = hook.parse_strict_markers(diff)
        self.assertEqual(len(parsed), 2)
        files = sorted(m["file"] for m in parsed)
        self.assertEqual(files, ["backend/apps/bar.py", "backend/apps/foo.py"])

    def test_marker_with_red_result_not_FAIL_is_rejected(self) -> None:
        diff = _GOOD_MARKER.replace("red_result=FAIL", "red_result=PASS")
        rv, err = _capture_stderr(hook.validate_markers, diff, _files_under_code_prefix(), lambda _id: 0)
        self.assertEqual(rv, 2)
        self.assertIn("red_result", err)
        self.assertIn("FAIL", err)

    def test_marker_with_green_result_not_PASS_is_rejected(self) -> None:
        diff = _GOOD_MARKER.replace("green_result=PASS", "green_result=FAIL")
        rv, err = _capture_stderr(hook.validate_markers, diff, _files_under_code_prefix(), lambda _id: 0)
        self.assertEqual(rv, 2)
        self.assertIn("green_result", err)

    def test_red_after_green_is_rejected(self) -> None:
        diff = (
            "[TDD CYCLE STRICT: file=backend/apps/foo.py "
            "red=backend/apps/test_foo.py:10 red_run_at=2026-05-17T04:02:30Z "
            "red_result=FAIL green=backend/apps/foo.py:5 "
            "green_run_at=2026-05-17T04:01:12Z green_result=PASS "
            'refactor="none" lesson_autoissue=#42]'
        )
        rv, err = _capture_stderr(hook.validate_markers, diff, _files_under_code_prefix(), lambda _id: 0)
        self.assertEqual(rv, 2)
        self.assertIn("red_run_at", err)
        self.assertIn("green_run_at", err)


class StagedFileCoverageTests(TestCase):
    """The number of markers must match the number of touched production files."""

    def test_marker_present_for_each_staged_source_passes(self) -> None:
        diff = _FULL_GOOD
        staged = ["backend/apps/foo.py"]
        rv, err = _capture_stderr(hook.validate_markers, diff, staged, lambda _id: 0)
        self.assertEqual(rv, 0, msg=err)

    def test_one_marker_two_staged_files_fails(self) -> None:
        diff = _FULL_GOOD
        staged = ["backend/apps/foo.py", "backend/apps/bar.py"]
        rv, err = _capture_stderr(hook.validate_markers, diff, staged, lambda _id: 0)
        self.assertEqual(rv, 2)
        self.assertIn("bar.py", err)

    def test_test_files_do_not_count_as_production(self) -> None:
        diff = _FULL_GOOD
        staged = ["backend/apps/foo.py", "backend/apps/test_foo.py", "backend/x.spec.ts"]
        rv, err = _capture_stderr(hook.validate_markers, diff, staged, lambda _id: 0)
        self.assertEqual(rv, 0, msg=err)

    def test_pure_docs_commit_does_not_need_markers(self) -> None:
        diff = ""
        staged = ["docs/foo.md", "README.md"]
        rv, err = _capture_stderr(hook.validate_markers, diff, staged, lambda _id: 0)
        self.assertEqual(rv, 0, msg=err)

    def test_generated_pb_files_are_exempt(self) -> None:
        diff = _FULL_GOOD
        staged = [
            "backend/apps/foo.py",
            "backend/apps/_sidecars_pb/snapshotd/snapshotd_pb2.py",
            "services/sidecars/api/gen/snapshotd.pb.go",
        ]
        rv, err = _capture_stderr(hook.validate_markers, diff, staged, lambda _id: 0)
        self.assertEqual(rv, 0, msg=err)


class CoverageMarkerTests(TestCase):
    """Slice-1.6+ 5-layer coverage marker."""

    def test_full_coverage_marker_passes(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_markers, _FULL_GOOD, ["backend/apps/foo.py"], lambda _id: 0,
        )
        self.assertEqual(rv, 0, msg=err)

    def test_missing_coverage_marker_fails(self) -> None:
        # TDD CYCLE STRICT present but no TDD COVERAGE.
        rv, err = _capture_stderr(
            hook.validate_markers, _GOOD_MARKER, ["backend/apps/foo.py"], lambda _id: 0,
        )
        self.assertEqual(rv, 2)
        self.assertIn("missing coverage", err)

    def test_coverage_marker_with_NA_and_real_reason_passes(self) -> None:
        diff = _GOOD_MARKER + "\n" + (
            "[TDD COVERAGE: file=backend/apps/foo.py edge_cases=2 "
            'resource_release=N/A:"function is a pure transformer with no state" '
            'latency=N/A:"helper runs once per process at boot, not on a hot path" '
            "smoke=1 e2e=1]"
        )
        rv, err = _capture_stderr(
            hook.validate_markers, diff, ["backend/apps/foo.py"], lambda _id: 0,
        )
        self.assertEqual(rv, 0, msg=err)

    def test_coverage_marker_with_short_NA_reason_fails(self) -> None:
        diff = _GOOD_MARKER + "\n" + (
            "[TDD COVERAGE: file=backend/apps/foo.py edge_cases=2 "
            'resource_release=N/A:"short" '
            'latency=N/A:"none" '
            "smoke=1 e2e=1]"
        )
        rv, err = _capture_stderr(
            hook.validate_markers, diff, ["backend/apps/foo.py"], lambda _id: 0,
        )
        self.assertEqual(rv, 2)
        self.assertIn("justification", err)

    def test_coverage_marker_with_forbidden_reason_fails(self) -> None:
        diff = _GOOD_MARKER + "\n" + (
            "[TDD COVERAGE: file=backend/apps/foo.py edge_cases=2 "
            'resource_release=N/A:"too small to test" '
            'latency=N/A:"this is a long enough sentence to pass length" '
            "smoke=1 e2e=1]"
        )
        rv, err = _capture_stderr(
            hook.validate_markers, diff, ["backend/apps/foo.py"], lambda _id: 0,
        )
        self.assertEqual(rv, 2)
        self.assertIn("forbidden", err.lower())

    def test_trivial_change_bypass_passes(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_markers, _TRIVIAL_MARKER, ["backend/apps/foo.py"], lambda _id: 0,
        )
        self.assertEqual(rv, 0, msg=err)

    def test_trivial_change_with_short_reason_fails(self) -> None:
        diff = (
            "[TRIVIAL CHANGE: file=backend/apps/foo.py "
            'reason="too small"]'
        )
        rv, err = _capture_stderr(
            hook.validate_markers, diff, ["backend/apps/foo.py"], lambda _id: 0,
        )
        self.assertEqual(rv, 2)

    def test_trivial_change_with_forbidden_reason_fails(self) -> None:
        diff = (
            "[TRIVIAL CHANGE: file=backend/apps/foo.py "
            'reason="trivial change so I do not need a test for it ever"]'
        )
        rv, err = _capture_stderr(
            hook.validate_markers, diff, ["backend/apps/foo.py"], lambda _id: 0,
        )
        self.assertEqual(rv, 2)
        self.assertIn("forbidden", err.lower())

    def test_mixed_trivial_and_strict_in_same_commit(self) -> None:
        # foo.py is a real change with the full pair; bar.py is trivial.
        diff = _FULL_GOOD + "\n" + (
            "[TRIVIAL CHANGE: file=backend/apps/bar.py "
            'reason="renamed a private constant to match the public API spelling"]'
        )
        staged = ["backend/apps/foo.py", "backend/apps/bar.py"]
        rv, err = _capture_stderr(
            hook.validate_markers, diff, staged, lambda _id: 0,
        )
        self.assertEqual(rv, 0, msg=err)


class IsCodeChangingTests(TestCase):
    def test_backend_path(self) -> None:
        self.assertTrue(hook.is_production_source("backend/apps/foo.py"))

    def test_test_file_is_not_production(self) -> None:
        self.assertFalse(hook.is_production_source("backend/apps/test_foo.py"))

    def test_spec_file_is_not_production(self) -> None:
        self.assertFalse(hook.is_production_source("frontend/src/app/foo.spec.ts"))

    def test_generated_proto_file_is_not_production(self) -> None:
        self.assertFalse(hook.is_production_source(
            "backend/apps/_sidecars_pb/snapshotd/snapshotd_pb2.py"
        ))
        self.assertFalse(hook.is_production_source(
            "services/sidecars/api/gen/snapshotd.pb.go"
        ))

    def test_docs_file_is_not_production(self) -> None:
        self.assertFalse(hook.is_production_source("docs/foo.md"))
        self.assertFalse(hook.is_production_source("README.md"))


def _files_under_code_prefix() -> list[str]:
    return ["backend/apps/foo.py"]


class GrandfatherMarkerTests(TestCase):
    """One-time rule-introduction bypass."""

    _GOOD_GRANDFATHER = (
        "[TDD CYCLE GRANDFATHERED: file=backend/apps/foo.py "
        'reason="file shipped before the strict-TDD rule landed; '
        'behaviour is covered by the existing test suite" '
        "regression_tests=backend/apps/tests/test_foo.py "
        "follow_up_paper_trail=#999]"
    )

    def test_grandfather_with_gate_file_staged_passes(self) -> None:
        # Gate file present → grandfather form accepted.
        staged = ["backend/apps/foo.py", "docs/TDD-STRICT-RULE.md"]
        rv, err = _capture_stderr(
            hook.validate_markers, self._GOOD_GRANDFATHER, staged, lambda _id: 0,
        )
        self.assertEqual(rv, 0, msg=err)

    def test_grandfather_without_gate_file_fails(self) -> None:
        # No gate file → form rejected (this commit is NOT the rule intro).
        staged = ["backend/apps/foo.py"]
        rv, err = _capture_stderr(
            hook.validate_markers, self._GOOD_GRANDFATHER, staged, lambda _id: 0,
        )
        self.assertEqual(rv, 2)
        self.assertIn("docs/TDD-STRICT-RULE.md", err)

    def test_grandfather_with_short_reason_fails(self) -> None:
        diff = (
            "[TDD CYCLE GRANDFATHERED: file=backend/apps/foo.py "
            'reason="too short" '
            "regression_tests=backend/apps/tests/test_foo.py "
            "follow_up_paper_trail=#999]"
        )
        staged = ["backend/apps/foo.py", "docs/TDD-STRICT-RULE.md"]
        rv, err = _capture_stderr(
            hook.validate_markers, diff, staged, lambda _id: 0,
        )
        self.assertEqual(rv, 2)
        self.assertIn("insufficient", err)

    def test_grandfather_with_no_regression_tests_fails(self) -> None:
        diff = (
            "[TDD CYCLE GRANDFATHERED: file=backend/apps/foo.py "
            'reason="file shipped before the rule landed but has no covering test" '
            "regression_tests=none "
            "follow_up_paper_trail=#999]"
        )
        staged = ["backend/apps/foo.py", "docs/TDD-STRICT-RULE.md"]
        rv, err = _capture_stderr(
            hook.validate_markers, diff, staged, lambda _id: 0,
        )
        self.assertEqual(rv, 2)
        self.assertIn("regression_tests", err)


class BatchGrandfatherMarkerTests(TestCase):
    """[RULE INTRODUCTION BATCH GRANDFATHERED:] form added 2026-05-17 (#586)."""

    _BATCH_MARKER = (
        "[RULE INTRODUCTION BATCH GRANDFATHERED: paper_trail=#586 "
        'reason="three hooks share the same rule-intro shape and grandfather '
        'cleanly under the spec gate" files=backend/apps/*.py]'
    )

    def test_batch_marker_accepted_when_spec_staged(self) -> None:
        staged = [
            "backend/apps/foo.py",
            "backend/apps/bar.py",
            "docs/TDD-STRICT-RULE.md",
        ]
        rv, err = _capture_stderr(
            hook.validate_markers, self._BATCH_MARKER, staged, lambda _id: 0,
        )
        self.assertEqual(rv, 0, msg=err)

    def test_batch_marker_rejected_when_spec_not_staged(self) -> None:
        staged = ["backend/apps/foo.py", "backend/apps/bar.py"]
        rv, err = _capture_stderr(
            hook.validate_markers, self._BATCH_MARKER, staged, lambda _id: 0,
        )
        self.assertEqual(rv, 2)
        self.assertIn("docs/TDD-STRICT-RULE.md", err)

    def test_batch_marker_short_reason_rejected(self) -> None:
        diff = (
            "[RULE INTRODUCTION BATCH GRANDFATHERED: paper_trail=#586 "
            'reason="too short" files=backend/apps/*.py]'
        )
        staged = ["backend/apps/foo.py", "docs/TDD-STRICT-RULE.md"]
        rv, err = _capture_stderr(
            hook.validate_markers, diff, staged, lambda _id: 0,
        )
        self.assertEqual(rv, 2)
        self.assertIn("reason", err.lower())

    def test_batch_marker_glob_no_match_rejected(self) -> None:
        diff = (
            "[RULE INTRODUCTION BATCH GRANDFATHERED: paper_trail=#586 "
            'reason="glob points at a folder that has no production source files staged" '
            "files=services/nonexistent/*.go]"
        )
        # No file under services/nonexistent/ is staged.
        staged = ["backend/apps/foo.py", "docs/TDD-STRICT-RULE.md"]
        rv, err = _capture_stderr(
            hook.validate_markers, diff, staged, lambda _id: 0,
        )
        # Marker is valid in form but covers nothing — foo.py still lacks a
        # per-file marker, so the hook must fail.
        self.assertEqual(rv, 2)
        # The failure must mention foo.py (still uncovered).
        self.assertIn("foo.py", err)

    def test_batch_marker_covers_glob_match(self) -> None:
        """All glob-matching files are treated as grandfathered."""
        staged = [
            "backend/apps/foo.py",
            "backend/apps/bar.py",
            "backend/apps/baz.py",
            "docs/TDD-STRICT-RULE.md",
        ]
        rv, err = _capture_stderr(
            hook.validate_markers, self._BATCH_MARKER, staged, lambda _id: 0,
        )
        # All three foo/bar/baz.py match the glob; the spec is staged; pass.
        self.assertEqual(rv, 0, msg=err)


if __name__ == "__main__":
    unittest.main()
