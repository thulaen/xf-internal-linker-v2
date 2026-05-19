"""Paired tests for `.githooks/check-test-case-mandate.py`.

Strict-TDD Red test for the Mandatory Agent Test Case First Rule (slice 1.6+,
added 2026-05-17). These tests must FAIL on first run because
`check_test_case_mandate` does not yet exist; the Green run lands when the
hook file is authored and ships with the matching validate_markers shape.

The hook validates that every staged production source file is mapped to one
or more `AutoIssue(category='test_case')` rows via `[TEST CASE MAPPING:]`
markers in the staged AGENT-HANDOFF.md diff, OR is grandfathered (one-time,
gated by `docs/TEST-CASE-FIRST-RULE.md` in the staged diff), OR carries a
`[NON-CODEBASE-EDIT TASK:]` bypass when no source file is staged.

Spec: docs/TEST-CASE-FIRST-RULE.md
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent


def _load_hook():
    """Load the hyphenated `check-test-case-mandate.py` as an import-able module."""
    hook_path = HOOKS_DIR / "check-test-case-mandate.py"
    spec = importlib.util.spec_from_file_location("check_test_case_mandate", hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_test_case_mandate"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


# A verifier that always returns 0 (referenced AutoIssue resolves) — injected
# into validate_markers in tests so the suite doesn't shell out to Django.
def _verifier_ok(_test_case_id: int) -> int:
    return 0


def _verifier_missing(_test_case_id: int) -> int:
    """Simulates a test_case AutoIssue ID that doesn't resolve."""
    return 2


_GOOD_MAPPING = (
    "[TEST CASE MAPPING: file=backend/apps/foo/bar.py test_cases=#101,#102]"
)
_GOOD_COMPLIANCE = (
    "[TEST CASE COMMIT COMPLIANCE: pass mapping=1 grandfathered=0 "
    "non_codebase=no agent=claude]"
)
_GOOD_GRANDFATHER = (
    "[TEST CASE GRANDFATHERED: file=services/sidecars/internal/foo/server.go "
    "follow_up_paper_trail=#580]"
)
_GOOD_NON_CODEBASE = (
    "[NON-CODEBASE-EDIT TASK: reason=\"only updating handoff notes and the "
    "plan file with no production source changes touched in this turn\"]"
)
_COMPLIANCE_NON_CODEBASE = (
    "[TEST CASE COMMIT COMPLIANCE: pass mapping=0 grandfathered=0 "
    "non_codebase=yes agent=claude]"
)
_COMPLIANCE_GRANDFATHERED = (
    "[TEST CASE COMMIT COMPLIANCE: pass mapping=0 grandfathered=1 "
    "non_codebase=no agent=claude]"
)


class MarkerPresenceTests(unittest.TestCase):
    """A code-changing commit without any TEST CASE marker must fail."""

    def test_no_marker_with_source_file_fails(self):
        rc = hook.validate_markers(
            diff="",
            staged_files=["backend/apps/foo/bar.py"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)

    def test_no_marker_no_files_passes(self):
        rc = hook.validate_markers(
            diff="",
            staged_files=[],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 0)

    def test_mapping_marker_with_compliance_passes(self):
        diff = _GOOD_MAPPING + "\n" + _GOOD_COMPLIANCE
        rc = hook.validate_markers(
            diff=diff,
            staged_files=["backend/apps/foo/bar.py"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 0)

    def test_test_files_do_not_need_mapping(self):
        """Test files like *_test.go / test_*.py are exempt from MAPPING."""
        rc = hook.validate_markers(
            diff=_COMPLIANCE_NON_CODEBASE.replace("non_codebase=yes", "non_codebase=no"),
            staged_files=["backend/apps/foo/test_bar.py"],
            case_verifier=_verifier_ok,
        )
        # Compliance present but no production sources → ok.
        # mapping=0 is fine because the only staged file is a test file.
        self.assertEqual(rc, 0)


class MarkerShapeTests(unittest.TestCase):
    """Malformed markers must be rejected."""

    def test_mapping_missing_test_case_ids_fails(self):
        bad = "[TEST CASE MAPPING: file=backend/foo.py test_cases=]"
        rc = hook.validate_markers(
            diff=bad + "\n" + _GOOD_COMPLIANCE,
            staged_files=["backend/foo.py"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)

    def test_mapping_with_garbage_ids_fails(self):
        bad = "[TEST CASE MAPPING: file=backend/foo.py test_cases=abc,def]"
        rc = hook.validate_markers(
            diff=bad + "\n" + _GOOD_COMPLIANCE,
            staged_files=["backend/foo.py"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)

    def test_mapping_file_mismatch_fails(self):
        """Mapping marker referencing a file that isn't staged is rejected."""
        diff = (
            "[TEST CASE MAPPING: file=backend/UNRELATED.py test_cases=#101]\n"
            + _GOOD_COMPLIANCE
        )
        rc = hook.validate_markers(
            diff=diff,
            staged_files=["backend/apps/foo/bar.py"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)


class AutoIssueVerifierTests(unittest.TestCase):
    """When a referenced test_case AutoIssue does not resolve, fail."""

    def test_missing_autoissue_fails(self):
        diff = _GOOD_MAPPING + "\n" + _GOOD_COMPLIANCE
        rc = hook.validate_markers(
            diff=diff,
            staged_files=["backend/apps/foo/bar.py"],
            case_verifier=_verifier_missing,
        )
        self.assertEqual(rc, 2)

    def test_real_autoissue_passes(self):
        diff = _GOOD_MAPPING + "\n" + _GOOD_COMPLIANCE
        rc = hook.validate_markers(
            diff=diff,
            staged_files=["backend/apps/foo/bar.py"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 0)


class GrandfatherGateTests(unittest.TestCase):
    """Grandfather form is accepted ONLY when the spec file is staged."""

    def test_grandfather_with_spec_passes(self):
        diff = _GOOD_GRANDFATHER + "\n" + _COMPLIANCE_GRANDFATHERED
        rc = hook.validate_markers(
            diff=diff,
            staged_files=[
                "services/sidecars/internal/foo/server.go",
                hook.GRANDFATHER_GATE_FILE,
            ],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 0)

    def test_grandfather_without_spec_fails(self):
        diff = _GOOD_GRANDFATHER + "\n" + _COMPLIANCE_GRANDFATHERED
        rc = hook.validate_markers(
            diff=diff,
            staged_files=["services/sidecars/internal/foo/server.go"],
            case_verifier=_verifier_ok,
        )
        # docs/TEST-CASE-FIRST-RULE.md not in staged_files → bypass refused.
        self.assertEqual(rc, 2)

    def test_grandfather_missing_paper_trail_fails(self):
        bad = (
            "[TEST CASE GRANDFATHERED: file=services/sidecars/internal/foo/server.go "
            "follow_up_paper_trail=]"
        )
        rc = hook.validate_markers(
            diff=bad + "\n" + _COMPLIANCE_GRANDFATHERED,
            staged_files=[
                "services/sidecars/internal/foo/server.go",
                hook.GRANDFATHER_GATE_FILE,
            ],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)


class NonCodebaseExceptionTests(unittest.TestCase):
    """[NON-CODEBASE-EDIT TASK:] bypass for docs-only commits."""

    def test_non_codebase_bypass_passes_for_docs_only(self):
        diff = _GOOD_NON_CODEBASE + "\n" + _COMPLIANCE_NON_CODEBASE
        rc = hook.validate_markers(
            diff=diff,
            staged_files=["docs/TEST-CASE-FIRST-RULE.md", "AGENT-HANDOFF.md"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 0)

    def test_non_codebase_bypass_with_source_file_fails(self):
        """If any source file is staged, bypass is invalid."""
        diff = _GOOD_NON_CODEBASE + "\n" + _COMPLIANCE_NON_CODEBASE
        rc = hook.validate_markers(
            diff=diff,
            staged_files=["backend/apps/foo/bar.py", "AGENT-HANDOFF.md"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)

    def test_non_codebase_reason_too_short_fails(self):
        bad = "[NON-CODEBASE-EDIT TASK: reason=\"docs\"]"
        rc = hook.validate_markers(
            diff=bad + "\n" + _COMPLIANCE_NON_CODEBASE,
            staged_files=["AGENT-HANDOFF.md"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)


class ComplianceMarkerTests(unittest.TestCase):
    """Commit-compliance summary marker rules."""

    def test_compliance_missing_fails(self):
        rc = hook.validate_markers(
            diff=_GOOD_MAPPING,  # no compliance marker
            staged_files=["backend/apps/foo/bar.py"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)

    def test_compliance_mapping_count_mismatch_fails(self):
        """mapping=2 but only one MAPPING marker present."""
        bad = (
            "[TEST CASE COMMIT COMPLIANCE: pass mapping=2 grandfathered=0 "
            "non_codebase=no agent=claude]"
        )
        rc = hook.validate_markers(
            diff=_GOOD_MAPPING + "\n" + bad,
            staged_files=["backend/apps/foo/bar.py"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)

    def test_compliance_status_fail_rejected(self):
        bad = (
            "[TEST CASE COMMIT COMPLIANCE: fail mapping=1 grandfathered=0 "
            "non_codebase=no agent=claude]"
        )
        rc = hook.validate_markers(
            diff=_GOOD_MAPPING + "\n" + bad,
            staged_files=["backend/apps/foo/bar.py"],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)


class MultiFileTests(unittest.TestCase):
    """Every staged production file needs at least one matching marker."""

    def test_two_files_two_markers_passes(self):
        diff = (
            "[TEST CASE MAPPING: file=backend/apps/foo/bar.py test_cases=#101]\n"
            "[TEST CASE MAPPING: file=backend/apps/foo/baz.py test_cases=#102]\n"
            "[TEST CASE COMMIT COMPLIANCE: pass mapping=2 grandfathered=0 "
            "non_codebase=no agent=claude]"
        )
        rc = hook.validate_markers(
            diff=diff,
            staged_files=[
                "backend/apps/foo/bar.py",
                "backend/apps/foo/baz.py",
            ],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 0)

    def test_two_files_one_marker_fails(self):
        diff = (
            "[TEST CASE MAPPING: file=backend/apps/foo/bar.py test_cases=#101]\n"
            "[TEST CASE COMMIT COMPLIANCE: pass mapping=1 grandfathered=0 "
            "non_codebase=no agent=claude]"
        )
        rc = hook.validate_markers(
            diff=diff,
            staged_files=[
                "backend/apps/foo/bar.py",
                "backend/apps/foo/baz.py",
            ],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)

    def test_mixed_mapping_and_grandfather_with_spec_passes(self):
        diff = (
            "[TEST CASE MAPPING: file=backend/apps/foo/bar.py test_cases=#101]\n"
            + _GOOD_GRANDFATHER
            + "\n"
            "[TEST CASE COMMIT COMPLIANCE: pass mapping=1 grandfathered=1 "
            "non_codebase=no agent=claude]"
        )
        rc = hook.validate_markers(
            diff=diff,
            staged_files=[
                "backend/apps/foo/bar.py",
                "services/sidecars/internal/foo/server.go",
                hook.GRANDFATHER_GATE_FILE,
            ],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 0)


class BatchGrandfatherMarkerTests(unittest.TestCase):
    """[RULE INTRODUCTION BATCH GRANDFATHERED:] form added 2026-05-17 (#586).

    Collapses a wall of [TEST CASE GRANDFATHERED: file=...] markers down to
    one marker whose `files=<glob>` covers every grandfathered file in the
    rule-introduction commit. Gated on the matching spec file being staged
    so the form is self-limiting to rule-introduction commits.
    """

    _BATCH_MARKER = (
        "[RULE INTRODUCTION BATCH GRANDFATHERED: paper_trail=#586 "
        'reason="rule-introduction commit grandfathers many sidecar stubs '
        'of the same shape under the spec gate" '
        "files=services/sidecars/internal/**/server.go]"
    )
    _BATCH_COMPLIANCE = (
        "[TEST CASE COMMIT COMPLIANCE: pass mapping=0 grandfathered=2 "
        "non_codebase=no agent=claude]"
    )

    def test_batch_marker_accepted_when_spec_staged(self):
        diff = self._BATCH_MARKER + "\n" + self._BATCH_COMPLIANCE
        rc = hook.validate_markers(
            diff=diff,
            staged_files=[
                "services/sidecars/internal/snapshotd/server.go",
                "services/sidecars/internal/coordd/server.go",
                hook.GRANDFATHER_GATE_FILE,
            ],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 0)

    def test_batch_marker_rejected_when_spec_not_staged(self):
        diff = self._BATCH_MARKER + "\n" + self._BATCH_COMPLIANCE
        rc = hook.validate_markers(
            diff=diff,
            staged_files=[
                "services/sidecars/internal/snapshotd/server.go",
                "services/sidecars/internal/coordd/server.go",
            ],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)

    def test_batch_marker_short_reason_rejected(self):
        bad_marker = (
            "[RULE INTRODUCTION BATCH GRANDFATHERED: paper_trail=#586 "
            'reason="too short" '
            "files=services/sidecars/internal/**/server.go]"
        )
        diff = bad_marker + "\n" + self._BATCH_COMPLIANCE
        rc = hook.validate_markers(
            diff=diff,
            staged_files=[
                "services/sidecars/internal/snapshotd/server.go",
                hook.GRANDFATHER_GATE_FILE,
            ],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)

    def test_batch_marker_glob_no_match_falls_through_to_per_file(self):
        """A glob that matches no staged file leaves files uncovered."""
        bad_glob_marker = (
            "[RULE INTRODUCTION BATCH GRANDFATHERED: paper_trail=#586 "
            'reason="rule-introduction commit; this glob points at a directory '
            'that has no staged production source files" '
            "files=services/nothing-staged/*.go]"
        )
        diff = bad_glob_marker + "\n" + self._BATCH_COMPLIANCE
        # services/sidecars/internal/snapshotd/server.go is staged but the
        # glob doesn't match it. Per-file marker not present → fail.
        rc = hook.validate_markers(
            diff=diff,
            staged_files=[
                "services/sidecars/internal/snapshotd/server.go",
                hook.GRANDFATHER_GATE_FILE,
            ],
            case_verifier=_verifier_ok,
        )
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
