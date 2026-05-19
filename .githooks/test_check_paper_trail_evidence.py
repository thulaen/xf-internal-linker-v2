"""Paired tests for `.githooks/check-paper-trail-evidence.py`.

Strict-TDD Red test for the Paper Trail Evidence Rule (added 2026-05-17).
These tests must FAIL on first run because `check_paper_trail_evidence`
does not yet exist; the Green run lands when the hook file is authored
with the matching validate_markers shape.

The hook validates that every `[PAPER TRAIL FILED: #N]` marker in the
staged AGENT-HANDOFF.md diff references a paper-trail entry that either
predates the rule's cutoff or carries a full test_case + citations.

Spec: docs/PAPER-TRAIL-EVIDENCE-RULE.md
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent


def _load_hook():
    hook_path = HOOKS_DIR / "check-paper-trail-evidence.py"
    spec = importlib.util.spec_from_file_location(
        "check_paper_trail_evidence", hook_path
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_paper_trail_evidence"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


# Verifier stubs injected via dependency injection so tests stay hermetic
# and do not shell out to Docker.
def _verifier_ok(_pt_id: int) -> int:
    return 0


def _verifier_fail(_pt_id: int) -> int:
    return 2


class MarkerParseTests(unittest.TestCase):
    """Extracts [PAPER TRAIL FILED: #N] IDs from the staged diff."""

    def test_extracts_single_id(self):
        ids = hook.extract_paper_trail_ids("[PAPER TRAIL FILED: #582]")
        self.assertEqual(ids, [582])

    def test_extracts_multiple_ids(self):
        diff = (
            "[PAPER TRAIL FILED: #580]\n"
            "[PAPER TRAIL FILED: #581]\n"
            "[PAPER TRAIL FILED: #582]\n"
        )
        ids = hook.extract_paper_trail_ids(diff)
        self.assertEqual(ids, [580, 581, 582])

    def test_returns_empty_when_no_marker(self):
        self.assertEqual(hook.extract_paper_trail_ids("nothing here"), [])


class ValidatorPassTests(unittest.TestCase):
    """When the verifier returns 0 for every id, validation passes."""

    def test_single_id_passes(self):
        rc = hook.validate_markers(
            diff="[PAPER TRAIL FILED: #582]",
            verifier=_verifier_ok,
        )
        self.assertEqual(rc, 0)

    def test_multiple_ids_pass(self):
        rc = hook.validate_markers(
            diff="[PAPER TRAIL FILED: #580] [PAPER TRAIL FILED: #582]",
            verifier=_verifier_ok,
        )
        self.assertEqual(rc, 0)

    def test_empty_diff_passes(self):
        rc = hook.validate_markers(diff="", verifier=_verifier_ok)
        self.assertEqual(rc, 0)


class ValidatorFailTests(unittest.TestCase):
    """When the verifier returns non-zero for any id, validation fails."""

    def test_one_bad_id_fails(self):
        rc = hook.validate_markers(
            diff="[PAPER TRAIL FILED: #582]",
            verifier=_verifier_fail,
        )
        self.assertEqual(rc, 2)

    def test_one_bad_in_many_fails(self):
        def selective(pt_id: int) -> int:
            return 0 if pt_id == 580 else 2

        rc = hook.validate_markers(
            diff="[PAPER TRAIL FILED: #580] [PAPER TRAIL FILED: #999]",
            verifier=selective,
        )
        self.assertEqual(rc, 2)


class MarkerShapeTests(unittest.TestCase):
    """Malformed PAPER TRAIL FILED markers are ignored, not crashed on."""

    def test_garbage_id_is_ignored(self):
        ids = hook.extract_paper_trail_ids("[PAPER TRAIL FILED: #abc]")
        self.assertEqual(ids, [])

    def test_marker_without_hash_ignored(self):
        ids = hook.extract_paper_trail_ids("[PAPER TRAIL FILED: 582]")
        self.assertEqual(ids, [])

    def test_duplicate_ids_kept_once(self):
        ids = hook.extract_paper_trail_ids(
            "[PAPER TRAIL FILED: #582] [PAPER TRAIL FILED: #582]"
        )
        # Dedup preserves the first occurrence, hook only verifies each once.
        self.assertEqual(ids, [582])


if __name__ == "__main__":
    unittest.main()
