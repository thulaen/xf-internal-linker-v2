#!/usr/bin/env python3
"""Tests for ``.githooks/check-rewrite-quota.py``."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


_HOOK_PATH = Path(__file__).resolve().parent / "check-rewrite-quota.py"


def _load_hook_module():
    spec = importlib.util.spec_from_file_location(
        "check_rewrite_quota_under_test", _HOOK_PATH
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("could not load check-rewrite-quota.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load_hook_module()


class _StderrCollector:
    def __init__(self, bucket: list[str]) -> None:
        self._bucket = bucket

    def write(self, msg: str) -> int:
        self._bucket.append(msg)
        return len(msg)

    def flush(self) -> None:  # pragma: no cover
        return None


def _run_with(
    *,
    code_files: list[str],
    handoff: str,
    verifier_result: tuple[bool, str] = (True, ""),
) -> tuple[int, str]:
    captured: list[str] = []
    with patch.object(
        hook, "_staged_code_files", return_value=code_files
    ), patch.object(
        hook, "_staged_handoff_diff", return_value=handoff
    ), patch.object(
        hook, "_verify_exemption", return_value=verifier_result
    ), patch.object(hook.sys, "stderr", new=_StderrCollector(captured)):
        rc = hook.main()
    return rc, "".join(captured)


class HappyPathTests(unittest.TestCase):
    def test_total_at_or_above_quota_passes(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff="[REWRITE COUNT: rewrites=2 refactorings=1 total=3]",
        )
        self.assertEqual(rc, 0, msg=out)

    def test_total_above_quota_passes(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff="[REWRITE COUNT: rewrites=3 refactorings=4 total=7]",
        )
        self.assertEqual(rc, 0, msg=out)


class ExemptionTests(unittest.TestCase):
    def test_bootstrap_marker_short_circuits(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff="[REWRITE QUOTA BOOTSTRAP: commit=introduces-rule]",
        )
        self.assertEqual(rc, 0, msg=out)

    def test_low_total_with_valid_evidence_passes(self) -> None:
        handoff = (
            "[REWRITE COUNT: rewrites=0 refactorings=1 total=1]\n"
            "[REWRITE QUOTA EXEMPTION: touched_area=backend/apps/example "
            "python_lines_remaining=0 baseline=10.0 projected_after=8.0 "
            "projected_gain_pct=20.0 threshold_pct=30.0 "
            "verdict=tiny_gain_or_no_python_remains "
            "evidence_file=docs/rewrite-evidence/session-x.json]"
        )
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff=handoff,
            verifier_result=(True, ""),
        )
        self.assertEqual(rc, 0, msg=out)

    def test_low_total_with_failing_verifier_blocks(self) -> None:
        handoff = (
            "[REWRITE COUNT: rewrites=0 refactorings=1 total=1]\n"
            "[REWRITE QUOTA EXEMPTION: touched_area=backend/apps/example "
            "python_lines_remaining=0 baseline=10.0 projected_after=5.0 "
            "projected_gain_pct=50.0 threshold_pct=30.0 "
            "verdict=tiny_gain_or_no_python_remains "
            "evidence_file=docs/rewrite-evidence/session-x.json]"
        )
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff=handoff,
            verifier_result=(False, "gain 50.0% is at or above threshold 30.0%"),
        )
        self.assertEqual(rc, 2)
        self.assertIn("refused by verify_rewrite_exemption", out)
        self.assertIn("50.0", out)

    def test_pure_docs_commit_exempt(self) -> None:
        rc, out = _run_with(code_files=[], handoff="")
        self.assertEqual(rc, 0, msg=out)


class FailureTests(unittest.TestCase):
    def test_missing_marker_on_code_commit_blocks(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff="some prose without the marker",
        )
        self.assertEqual(rc, 2)
        self.assertIn("REWRITE COUNT", out)

    def test_low_total_no_exemption_blocks(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff="[REWRITE COUNT: rewrites=0 refactorings=1 total=1]",
        )
        self.assertEqual(rc, 2)
        self.assertIn("below the minimum of 3", out)

    def test_count_arithmetic_mismatch_blocks(self) -> None:
        rc, out = _run_with(
            code_files=["backend/apps/example/views.py"],
            handoff="[REWRITE COUNT: rewrites=2 refactorings=2 total=5]",
        )
        self.assertEqual(rc, 2)
        self.assertIn("arithmetic", out)


if __name__ == "__main__":
    sys.exit(unittest.main(verbosity=2))
