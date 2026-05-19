"""Tests for .githooks/check-snapshotd-ritual.py (slice 1.6).

The hook validates that the staged AGENT-HANDOFF.md diff contains
[SNAPSHOTS READ: ...] AFTER [PAPER TRAIL READ: ...]. Tests pass synthetic
diff strings directly to `hook.validate()` so the suite never needs a
live git checkout.
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
    hook_path = HOOKS_DIR / "check-snapshotd-ritual.py"
    spec = importlib.util.spec_from_file_location("check_snapshotd_ritual", hook_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {hook_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_snapshotd_ritual"] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _capture_stderr(func, *args, **kwargs):
    """Run func and return (return_value, captured_stderr_text)."""
    buf = io.StringIO()
    with patch.object(sys, "stderr", buf):
        rv = func(*args, **kwargs)
    return rv, buf.getvalue()


class ValidateTests(TestCase):
    def test_no_paper_trail_marker_passes_silently(self) -> None:
        # The check-paper-trail-read.py hook owns that case; we do not
        # duplicate the error.
        rv, err = _capture_stderr(hook.validate, "some random handoff text")
        self.assertEqual(rv, 0)
        self.assertEqual(err, "")

    def test_paper_trail_marker_without_snapshots_fails(self) -> None:
        diff = "[PAPER TRAIL READ: 47 open (5 autoissue_deferral / ...)]"
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 2)
        self.assertIn("missing the [SNAPSHOTS READ:", err)
        self.assertIn("UNBLOCK:", err)
        self.assertIn("WHY:", err)

    def test_skipped_form_passes(self) -> None:
        diff = (
            "[PAPER TRAIL READ: 47 open (5 autoissue_deferral / ...)]\n"
            "[SNAPSHOTS READ: skipped — snapshotd unavailable]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 0, msg=err)
        self.assertEqual(err, "")

    def test_skipped_form_with_dash_em_dash_variants(self) -> None:
        for sep in ["—", "--", "-"]:
            diff = (
                "[PAPER TRAIL READ: 47 open]\n"
                f"[SNAPSHOTS READ: skipped {sep} snapshotd unavailable]"
            )
            rv, err = _capture_stderr(hook.validate, diff)
            self.assertEqual(rv, 0, msg=f"sep={sep!r} produced {err!r}")

    def test_full_form_with_three_picks_passes(self) -> None:
        diff = (
            "[PAPER TRAIL READ: 47 open]\n"
            "[SNAPSHOTS READ: 12 snapshots attached to 8 open issues — "
            "picked: #100(critical), #101(error), #102(before)]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 0, msg=err)

    def test_full_form_with_singular_snapshot_passes(self) -> None:
        # The marker should also accept "1 snapshot attached to 1 open issue".
        diff = (
            "[PAPER TRAIL READ: 47 open]\n"
            "[SNAPSHOTS READ: 1 snapshot attached to 1 open issue — "
            "picked: #100(critical), #101(error), #102(before)]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 0, msg=err)

    def test_full_form_with_too_few_picks_fails(self) -> None:
        diff = (
            "[PAPER TRAIL READ: 47 open]\n"
            "[SNAPSHOTS READ: 12 snapshots attached to 8 open issues — "
            "picked: #100(critical), #101(error)]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 2)
        self.assertIn("at least 3 entries", err)

    def test_full_form_with_bad_shape_fails(self) -> None:
        diff = (
            "[PAPER TRAIL READ: 47 open]\n"
            "[SNAPSHOTS READ: I forgot how this marker is supposed to look]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 2)
        self.assertIn("body shape does not match", err)

    def test_snapshots_before_paper_trail_fails(self) -> None:
        diff = (
            "[SNAPSHOTS READ: skipped — snapshotd unavailable]\n"
            "[PAPER TRAIL READ: 47 open]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 2)
        self.assertIn("appears BEFORE", err)

    def test_empty_form_passes(self) -> None:
        """Slice 1.6 — snapshotd is reachable but no open issue has evidence yet."""
        diff = (
            "[PAPER TRAIL READ: 47 open]\n"
            "[SNAPSHOTS READ: 0 snapshots attached to 0 open issues — "
            "picked: (none — no open AutoIssue has an attached snapshot yet)]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 0, msg=err)

    def test_empty_form_singular_phrasing_passes(self) -> None:
        diff = (
            "[PAPER TRAIL READ: 47 open]\n"
            "[SNAPSHOTS READ: 0 snapshot attached to 0 open issue — "
            "picked: (none)]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 0, msg=err)

    def test_case_insensitive_marker_matching(self) -> None:
        diff = (
            "[paper trail read: 47 open]\n"
            "[snapshots read: skipped — snapshotd unavailable]"
        )
        rv, err = _capture_stderr(hook.validate, diff)
        self.assertEqual(rv, 0, msg=err)


class IsCodeChangingTests(TestCase):
    def test_backend_path_is_code_changing(self) -> None:
        self.assertTrue(hook._is_code_changing(["backend/apps/foo.py"]))

    def test_services_path_is_code_changing(self) -> None:
        self.assertTrue(hook._is_code_changing(["services/sidecars/cmd/sidecars/main.go"]))

    def test_githooks_path_is_code_changing(self) -> None:
        self.assertTrue(hook._is_code_changing([".githooks/check-foo.py"]))

    def test_pure_docs_commit_is_not_code_changing(self) -> None:
        self.assertFalse(hook._is_code_changing(["docs/foo.md", "README.md"]))

    def test_empty_staged_list_is_not_code_changing(self) -> None:
        self.assertFalse(hook._is_code_changing([]))


class MainTests(TestCase):
    def test_main_with_no_staged_files_returns_zero(self) -> None:
        with patch.object(hook, "_staged_files", return_value=[]):
            self.assertEqual(hook.main(), 0)

    def test_main_with_docs_only_commit_returns_zero(self) -> None:
        with patch.object(hook, "_staged_files", return_value=["docs/x.md"]):
            self.assertEqual(hook.main(), 0)

    def test_main_with_code_change_but_no_handoff_diff_returns_zero(self) -> None:
        # check-paper-trail-read.py owns the "no handoff" case.
        with (
            patch.object(hook, "_staged_files", return_value=["backend/a.py"]),
            patch.object(hook, "_read_staged_handoff_diff", return_value=""),
        ):
            self.assertEqual(hook.main(), 0)

    def test_main_with_code_change_and_missing_snapshot_marker_returns_two(self) -> None:
        diff = "[PAPER TRAIL READ: 47 open]"
        with (
            patch.object(hook, "_staged_files", return_value=["backend/a.py"]),
            patch.object(hook, "_read_staged_handoff_diff", return_value=diff),
        ):
            rv, err = _capture_stderr(hook.main)
            self.assertEqual(rv, 2)
            self.assertIn("missing the [SNAPSHOTS READ:", err)

    def test_main_passes_with_skipped_form_on_code_change(self) -> None:
        diff = (
            "[PAPER TRAIL READ: 47 open]\n"
            "[SNAPSHOTS READ: skipped — snapshotd unavailable]"
        )
        with (
            patch.object(hook, "_staged_files", return_value=["backend/a.py"]),
            patch.object(hook, "_read_staged_handoff_diff", return_value=diff),
        ):
            rv, err = _capture_stderr(hook.main)
            self.assertEqual(rv, 0, msg=err)


if __name__ == "__main__":
    unittest.main()
