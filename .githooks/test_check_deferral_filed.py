#!/usr/bin/env python3
"""Tests for check-deferral-filed.py.

The hook scans the staged AGENT-HANDOFF.md added-lines (not the whole
file) for deferral verbs and requires that the count of
`[PAPER TRAIL FILED: #<N>]` markers in the same added-lines block is
greater than or equal to the count of deferral verbs found.

Rule F compliant: every FAIL message has WHY + UNBLOCK.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock


def _load_hook():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "check_deferral_filed", here / "check-deferral-filed.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_no_deferral_verbs_returns_zero(self):
        text = "What I did:\nFixed a bug.\nAdded a test.\n"
        self.assertEqual(self.hook._count_deferrals(text), 0)

    def test_deferred_verb_detected(self):
        text = "I deferred the upgrade until next session.\n"
        self.assertEqual(self.hook._count_deferrals(text), 1)

    def test_skipping_for_now_detected(self):
        text = "Skipping for now because the env is down.\n"
        self.assertEqual(self.hook._count_deferrals(text), 1)

    def test_postponed_to_next_session_detected(self):
        text = "This is postponed to next session.\n"
        # Matches `postponed` AND `next session`.
        self.assertGreaterEqual(self.hook._count_deferrals(text), 1)

    def test_marker_count(self):
        text = (
            "Filed three things this session.\n"
            "[PAPER TRAIL FILED: #501]\n"
            "[PAPER TRAIL FILED: #502]\n"
            "[PAPER TRAIL FILED: #503]\n"
        )
        self.assertEqual(self.hook._count_markers(text), 3)

    def test_marker_count_zero_when_absent(self):
        text = "Did some work.\nNo markers here.\n"
        self.assertEqual(self.hook._count_markers(text), 0)

    def test_descriptive_rule_text_does_not_trigger(self):
        """Documentation that DEFINES the deferral rule must not trip
        the hook. Only forward-looking first-person commitments count.
        """
        text = (
            "The ABSOLUTE rule says every deferral must be filed in the "
            "paper trail. Silently deferring work is forbidden. The hook "
            "scans for deferral verbs in the staged diff. A deferred row "
            "with `status='resolved'` is still searchable. The previous "
            "session deferred X to the paper trail.\n"
        )
        self.assertEqual(
            self.hook._count_deferrals(text), 0,
            "descriptive mentions must not match — only first-person "
            "forward-looking commitments do",
        )

    def test_forward_looking_first_person_does_trigger(self):
        text = (
            "I will defer the upgrade. We are postponing to next session. "
            "I deferred three items to follow-up. Leaving for the next "
            "session. Out-of-scope this session.\n"
        )
        # At least 4 of the 5 phrasings should match.
        self.assertGreaterEqual(self.hook._count_deferrals(text), 4)


class StagedDiffParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_added_lines_extracted_from_unified_diff(self):
        diff = (
            "diff --git a/AGENT-HANDOFF.md b/AGENT-HANDOFF.md\n"
            "index 0000000..1111111 100644\n"
            "--- a/AGENT-HANDOFF.md\n"
            "+++ b/AGENT-HANDOFF.md\n"
            "@@ -1,3 +1,7 @@\n"
            "+# new entry header\n"
            "+Deferred 5 items.\n"
            "+[PAPER TRAIL FILED: #1]\n"
            "+---\n"
            " # old entry header\n"
            " old line one\n"
            " old line two\n"
        )
        added = self.hook._extract_added_lines(diff)
        self.assertIn("Deferred 5 items.", added)
        self.assertIn("[PAPER TRAIL FILED: #1]", added)
        # Old lines (no `+` prefix) must NOT appear.
        self.assertNotIn("old line one", added)

    def test_plus_plus_plus_header_excluded(self):
        diff = (
            "--- a/AGENT-HANDOFF.md\n"
            "+++ b/AGENT-HANDOFF.md\n"
            "+Real added line.\n"
        )
        added = self.hook._extract_added_lines(diff)
        self.assertIn("Real added line.", added)
        self.assertNotIn("+++ b/AGENT-HANDOFF.md", added)

    def test_ritual_marker_lines_excluded(self):
        """REGISTRY READ / PAPER TRAIL READ / etc. are status reports,
        not commitments. They MUST NOT count toward deferral verbs even
        if the marker text happens to include phrasing like
        '(drought logged: deferred to next session)'.
        """
        diff = (
            "+++ b/AGENT-HANDOFF.md\n"
            "+[REGISTRY READ: drought logged: deferred to next session]\n"
            "+[PAPER TRAIL READ: 0 open — I will defer to next session]\n"
            "+Real body line: I am deferring X to next session.\n"
        )
        added = self.hook._extract_added_lines(diff)
        # The ritual lines must be absent from the scanned text.
        self.assertNotIn("REGISTRY READ", added)
        self.assertNotIn("PAPER TRAIL READ", added)
        # The genuine body deferral must remain.
        self.assertIn("Real body line", added)
        # And the count must only reflect the body.
        self.assertEqual(self.hook._count_deferrals(added), 1)


class HookMainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hook = _load_hook()

    def test_returns_zero_when_handoff_not_staged(self):
        with mock.patch.object(self.hook, "_staged_handoff_diff", return_value=""):
            self.assertEqual(self.hook.main(), 0)

    def test_returns_zero_when_no_deferrals(self):
        diff = (
            "+++ b/AGENT-HANDOFF.md\n"
            "+# new entry header\n"
            "+Did clean work today.\n"
        )
        with mock.patch.object(self.hook, "_staged_handoff_diff", return_value=diff):
            self.assertEqual(self.hook.main(), 0)

    def test_returns_zero_when_deferrals_match_markers(self):
        diff = (
            "+++ b/AGENT-HANDOFF.md\n"
            "+# new entry header\n"
            "+I deferred two items.\n"
            "+We are postponing to next session.\n"
            "+[PAPER TRAIL FILED: #1]\n"
            "+[PAPER TRAIL FILED: #2]\n"
            "+[PAPER TRAIL FILED: #3]\n"
        )
        with mock.patch.object(self.hook, "_staged_handoff_diff", return_value=diff):
            self.assertEqual(self.hook.main(), 0)

    def test_returns_two_when_deferrals_outnumber_markers(self):
        diff = (
            "+++ b/AGENT-HANDOFF.md\n"
            "+# new entry header\n"
            "+I deferred five items.\n"
            "+We are skipping this for now.\n"
            "+[PAPER TRAIL FILED: #1]\n"
        )
        with mock.patch.object(self.hook, "_staged_handoff_diff", return_value=diff), \
             mock.patch.object(sys, "stderr", StringIO()) as err:
            self.assertEqual(self.hook.main(), 2)
            msg = err.getvalue()
            self.assertIn("FAIL", msg)
            self.assertIn("WHY", msg)
            self.assertIn("UNBLOCK", msg)
            self.assertIn("defer_work", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
