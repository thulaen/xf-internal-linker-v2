"""Tests for .githooks/check-tdd-preflight.py.

The hook enforces Piece 1 of the PARAMOUNT TDD-pipeline rule:

    Immediately after `[HANDOFF READ: …]` the staged handoff entry MUST
    carry a `[TDD PREFLIGHT: …]` marker proving the agent armed the
    pipeline at session start (via `manage.py preflight_tdd`).

The hook fires FIRST in `scripts/precommit-docker.sh`, so a non-armed
session fails before any other check runs. Pure-docs commits (no
production source files staged) are exempt — the rule only matters
when the agent is touching code.

Written FIRST (Red) per the strict-TDD rule the hook helps enforce.
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
    hook_path = HOOKS_DIR / "check-tdd-preflight.py"
    spec = importlib.util.spec_from_file_location("check_tdd_preflight", hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_tdd_preflight"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _capture_stderr(func, *args, **kwargs):
    buf = io.StringIO()
    with patch.object(sys, "stderr", buf):
        rv = func(*args, **kwargs)
    return rv, buf.getvalue()


# A well-formed preflight marker exactly as `manage.py preflight_tdd` prints.
_GOOD_PREFLIGHT = (
    "[TDD PREFLIGHT: pipeline=SPEC→TEST_CASE→TDD→CODE→CODE_REVIEW→LESSON "
    "spec_citation=on test_case_mandate=on tdd_red_green_refactor=on "
    "5_layer_coverage=on code_review_logging=on lesson_logging=on "
    "decision_point=on artefact_pruning=on no_bypass=on "
    "per_file_lookup=on commit_failure_lookup=on "
    "session_id=11111111-2222-3333-4444-555555555555 "
    "armed_at=2026-05-18T00:30:00Z]"
)

# A canonical session-start block — HANDOFF READ, then PREFLIGHT, then the
# other read markers. The hook is happy with this shape.
_GOOD_SESSION_START = "\n".join(
    [
        "[HANDOFF READ: 2026-05-17 18:00 by Claude — example summary]",
        _GOOD_PREFLIGHT,
        "[REGISTRY READ: 30 open (...) — picked: #1, ...]",
        "[PAPER TRAIL READ: 53 open (...) — picked: #1, ...]",
        "[SNAPSHOTS READ: 0 snapshots attached to 0 open issues — picked: (none)]",
        "[LESSONS BEFORE START: 1 resolved-lesson row reviewed in .githooks]",
    ]
)


def _files_with_one_source() -> list[str]:
    return ["backend/apps/foo.py"]


def _docs_only_files() -> list[str]:
    return ["docs/foo.md", "README.md"]


class MarkerPresenceTests(TestCase):

    def test_good_marker_passes(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_preflight, _GOOD_SESSION_START, _files_with_one_source(),
        )
        self.assertEqual(rv, 0, msg=err)

    def test_missing_marker_with_code_change_fails(self) -> None:
        diff = "[HANDOFF READ: 2026-05-17 18:00 by Claude — example summary]"
        rv, err = _capture_stderr(
            hook.validate_preflight, diff, _files_with_one_source(),
        )
        self.assertEqual(rv, 2)
        self.assertIn("TDD PREFLIGHT", err)

    def test_missing_marker_on_pure_docs_commit_passes(self) -> None:
        diff = "[HANDOFF READ: 2026-05-17 18:00 by Claude — docs sweep]"
        rv, err = _capture_stderr(
            hook.validate_preflight, diff, _docs_only_files(),
        )
        self.assertEqual(rv, 0, msg=err)

    def test_missing_marker_with_no_staged_files_passes(self) -> None:
        rv, err = _capture_stderr(hook.validate_preflight, "", [])
        self.assertEqual(rv, 0, msg=err)


class MarkerShapeTests(TestCase):

    def test_marker_with_off_switch_fails(self) -> None:
        diff = (
            "[HANDOFF READ: 2026-05-17 18:00 by Claude]\n"
            + _GOOD_PREFLIGHT.replace("spec_citation=on", "spec_citation=off")
        )
        rv, err = _capture_stderr(hook.validate_preflight, diff, _files_with_one_source())
        self.assertEqual(rv, 2)
        self.assertIn("spec_citation", err)

    def test_marker_with_missing_pipeline_fails(self) -> None:
        diff = (
            "[HANDOFF READ: 2026-05-17 18:00 by Claude]\n"
            "[TDD PREFLIGHT: spec_citation=on test_case_mandate=on "
            "tdd_red_green_refactor=on 5_layer_coverage=on code_review_logging=on "
            "lesson_logging=on decision_point=on artefact_pruning=on "
            "no_bypass=on per_file_lookup=on commit_failure_lookup=on "
            "session_id=abc armed_at=2026-05-18T00:30:00Z]"
        )
        rv, err = _capture_stderr(hook.validate_preflight, diff, _files_with_one_source())
        self.assertEqual(rv, 2)
        self.assertIn("pipeline", err)

    def test_marker_with_bad_armed_at_fails(self) -> None:
        diff = (
            "[HANDOFF READ: 2026-05-17 18:00 by Claude]\n"
            + _GOOD_PREFLIGHT.replace("armed_at=2026-05-18T00:30:00Z", "armed_at=yesterday")
        )
        rv, err = _capture_stderr(hook.validate_preflight, diff, _files_with_one_source())
        self.assertEqual(rv, 2)
        self.assertIn("armed_at", err)

    def test_marker_with_missing_session_id_fails(self) -> None:
        diff = (
            "[HANDOFF READ: 2026-05-17 18:00 by Claude]\n"
            "[TDD PREFLIGHT: pipeline=SPEC→TEST_CASE→TDD→CODE→CODE_REVIEW→LESSON "
            "spec_citation=on test_case_mandate=on tdd_red_green_refactor=on "
            "5_layer_coverage=on code_review_logging=on lesson_logging=on "
            "decision_point=on artefact_pruning=on no_bypass=on "
            "per_file_lookup=on commit_failure_lookup=on "
            "armed_at=2026-05-18T00:30:00Z]"
        )
        rv, err = _capture_stderr(hook.validate_preflight, diff, _files_with_one_source())
        self.assertEqual(rv, 2)
        self.assertIn("session_id", err)

    def test_marker_with_vague_review_stage_fails(self) -> None:
        old_marker = _GOOD_PREFLIGHT.replace(
            "CODE→CODE_REVIEW→LESSON",
            "CODE→REVIEW→LESSON",
        )
        diff = "[HANDOFF READ: 2026-05-17 18:00 by Claude]\n" + old_marker
        rv, err = _capture_stderr(hook.validate_preflight, diff, _files_with_one_source())
        self.assertEqual(rv, 2)
        self.assertIn("CODE_REVIEW", err)


class MarkerPositionTests(TestCase):

    def test_preflight_before_handoff_read_fails(self) -> None:
        diff = "\n".join(
            [
                _GOOD_PREFLIGHT,
                "[HANDOFF READ: 2026-05-17 18:00 by Claude]",
                "[REGISTRY READ: 30 open (...) — picked: #1]",
            ]
        )
        rv, err = _capture_stderr(hook.validate_preflight, diff, _files_with_one_source())
        self.assertEqual(rv, 2)
        # The hook reports the wrong direction in plain English: preflight
        # appeared BEFORE handoff-read when it must appear AFTER.
        self.assertIn("BEFORE [HANDOFF READ:", err)

    def test_preflight_after_registry_read_fails(self) -> None:
        diff = "\n".join(
            [
                "[HANDOFF READ: 2026-05-17 18:00 by Claude]",
                "[REGISTRY READ: 30 open (...) — picked: #1]",
                _GOOD_PREFLIGHT,
                "[PAPER TRAIL READ: 53 open (...) — picked: #1]",
            ]
        )
        rv, err = _capture_stderr(hook.validate_preflight, diff, _files_with_one_source())
        self.assertEqual(rv, 2)
        self.assertIn("before", err.lower())

    def test_preflight_after_handoff_and_before_registry_passes(self) -> None:
        rv, err = _capture_stderr(
            hook.validate_preflight, _GOOD_SESSION_START, _files_with_one_source(),
        )
        self.assertEqual(rv, 0, msg=err)

    def test_no_handoff_read_marker_fails(self) -> None:
        # The preflight marker requires a [HANDOFF READ:] marker before it.
        # If the handoff diff carries no [HANDOFF READ:] at all, the position
        # rule cannot pass and the hook must fail with a helpful message.
        diff = _GOOD_PREFLIGHT
        rv, err = _capture_stderr(hook.validate_preflight, diff, _files_with_one_source())
        self.assertEqual(rv, 2)
        self.assertIn("HANDOFF READ", err)


if __name__ == "__main__":
    unittest.main()
