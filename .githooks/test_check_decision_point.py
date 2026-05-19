"""Tests for .githooks/check-decision-point.py.

Session S3 of the PARAMOUNT TDD-pipeline rule. The hook enforces that
every code-changing commit's staged AGENT-HANDOFF.md diff includes a
`[DECISION POINT: commit=<prior_hash> …]` marker matching the most
recent prior commit (HEAD at the time of staging).

Accepted shape:
  [DECISION POINT: commit=<short_hash> findings=<N>
   improvements=<i> warnings=<w> problems=<p>
   missing_spec=<s> off_track_test_case=<tc> off_track_tdd=<td>
   autoissues_filed=<#…|none> filed_at=<ISO8601>]

Pure-docs commits (no production source files staged) are exempt.

Grandfather form: when docs/TDD-PIPELINE-RULE.md is in the staged diff
(i.e., this commit IS the rule-introduction commit) and no prior
Decision Point marker can exist yet, the hook accepts the missing
marker without failing.

Written FIRST (Red) per the strict-TDD rule the pipeline enforces.
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
    hook_path = HOOKS_DIR / "check-decision-point.py"
    spec = importlib.util.spec_from_file_location("check_decision_point", hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_decision_point"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _capture_stderr(func, *args, **kwargs):
    buf = io.StringIO()
    with patch.object(sys, "stderr", buf):
        rv = func(*args, **kwargs)
    return rv, buf.getvalue()


def _good_marker(commit_hash: str = "abc1234") -> str:
    return (
        f"[DECISION POINT: commit={commit_hash} findings=0 "
        f"improvements=0 warnings=0 problems=0 "
        f"missing_spec=0 off_track_test_case=0 off_track_tdd=0 "
        f"autoissues_filed=none filed_at=2026-05-18T01:00:00Z]"
    )


class MarkerPresenceTests(TestCase):

    def test_marker_matching_prior_commit_passes(self) -> None:
        diff = _good_marker("abc1234")
        rv, err = _capture_stderr(
            hook.validate_decision_point,
            diff,
            prior_commit="abc1234567890abcdef",
            staged_files=["backend/apps/x.py"],
        )
        self.assertEqual(rv, 0, msg=err)

    def test_marker_for_wrong_commit_fails(self) -> None:
        diff = _good_marker("abc1234")
        rv, err = _capture_stderr(
            hook.validate_decision_point,
            diff,
            prior_commit="def5678000000000000",
            staged_files=["backend/apps/x.py"],
        )
        self.assertEqual(rv, 2)
        self.assertIn("def5678", err)

    def test_missing_marker_with_code_change_fails(self) -> None:
        diff = "[HANDOFF READ: 2026-05-17 by Claude]"
        rv, err = _capture_stderr(
            hook.validate_decision_point,
            diff,
            prior_commit="abc1234567890abcdef",
            staged_files=["backend/apps/x.py"],
        )
        self.assertEqual(rv, 2)
        self.assertIn("DECISION POINT", err)


class ExemptionTests(TestCase):

    def test_pure_docs_commit_is_exempt(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_decision_point,
            "",
            prior_commit="abc1234567890abcdef",
            staged_files=["docs/foo.md", "README.md"],
        )
        self.assertEqual(rv, 0, msg=err)

    def test_no_staged_files_is_exempt(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_decision_point,
            "",
            prior_commit="abc1234567890abcdef",
            staged_files=[],
        )
        self.assertEqual(rv, 0, msg=err)

    def test_rule_introduction_commit_grandfathered(self) -> None:
        # The first commit that introduces this rule cannot have a prior
        # Decision Point marker, so the gate is accepted when
        # docs/TDD-PIPELINE-RULE.md is staged.
        rv, err = _capture_stderr(
            hook.validate_decision_point,
            "",
            prior_commit="abc1234567890abcdef",
            staged_files=["docs/TDD-PIPELINE-RULE.md", "backend/apps/x.py"],
        )
        self.assertEqual(rv, 0, msg=err)

    def test_no_prior_commit_passes_only_when_grandfather_staged(self) -> None:
        # If git has no prior commit (fresh repo), the hook accepts an empty
        # prior_commit string only when the spec file is staged.
        rv, err = _capture_stderr(
            hook.validate_decision_point,
            "",
            prior_commit="",
            staged_files=["docs/TDD-PIPELINE-RULE.md", "backend/apps/x.py"],
        )
        self.assertEqual(rv, 0, msg=err)


class MarkerShapeTests(TestCase):

    def test_malformed_marker_fails(self) -> None:
        diff = "[DECISION POINT: commit=abc1234 banana=apple]"
        rv, err = _capture_stderr(
            hook.validate_decision_point,
            diff,
            prior_commit="abc1234567890abcdef",
            staged_files=["backend/apps/x.py"],
        )
        self.assertEqual(rv, 2)
        self.assertIn("shape", err.lower())

    def test_marker_uses_short_hash_prefix(self) -> None:
        # The full HEAD hash is 40 chars; the marker uses the first 7.
        # Hook must compare with startswith, not exact equality.
        diff = _good_marker("abc1234")
        rv, err = _capture_stderr(
            hook.validate_decision_point,
            diff,
            prior_commit="abc1234dddeeefff0000000000000000000",
            staged_files=["backend/apps/x.py"],
        )
        self.assertEqual(rv, 0, msg=err)


if __name__ == "__main__":
    unittest.main()
