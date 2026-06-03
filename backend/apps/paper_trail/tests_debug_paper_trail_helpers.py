"""No-database SimpleTestCase coverage for debug_paper_trail.py pure helpers.

The command itself queries the PaperTrailEntry table (covered by the DB-backed
``tests_debug_paper_trail.py``). The three pure formatting helpers
``_entry_row``, ``_format_human``, and the marker shape do NOT need a database:
they operate on plain objects and dicts. This file pins their exact output so a
mutated literal or slice bound is caught without spinning up a test DB.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.paper_trail.management.commands.debug_paper_trail import (
    _entry_row,
    _format_human,
)


def _fake_entry(**overrides) -> SimpleNamespace:
    base = {
        "id": 7,
        "category": "refactor",
        "status": "open",
        "severity": "high",
        "title": "Tidy the bridge loop",
        "priority_score": 4.5,
        "resolution_lessons": "Trap: x. Fix shape: y.",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class EntryRowTests(SimpleTestCase):
    def test_when_entry_given_then_row_has_exact_fields(self) -> None:
        row = _entry_row(_fake_entry())
        self.assertEqual(
            row,
            {
                "id": 7,
                "category": "refactor",
                "status": "open",
                "severity": "high",
                "title": "Tidy the bridge loop",
                "priority_score": 4.5,
                "lessons": "Trap: x. Fix shape: y.",
            },
        )

    def test_when_lessons_over_150_chars_then_truncated_to_150(self) -> None:
        long_lessons = "z" * 400
        row = _entry_row(_fake_entry(resolution_lessons=long_lessons))
        self.assertEqual(row["lessons"], "z" * 150)
        self.assertEqual(len(row["lessons"]), 150)

    def test_when_lessons_exactly_150_chars_then_kept_whole(self) -> None:
        # A 150-char string is the exact boundary: it must pass through whole.
        # Distinguishes the slice bound from [:149], which would drop a char.
        exactly_150 = "a" * 150
        row = _entry_row(_fake_entry(resolution_lessons=exactly_150))
        self.assertEqual(row["lessons"], exactly_150)
        self.assertEqual(len(row["lessons"]), 150)

    def test_when_lessons_151_chars_then_drops_exactly_the_last_one(self) -> None:
        # 151 distinct-tail string: truncating to [:150] keeps the first 150 and
        # drops the final char. Kills [:151] (would keep all 151) precisely.
        head = "b" * 150
        row = _entry_row(_fake_entry(resolution_lessons=head + "Z"))
        self.assertEqual(row["lessons"], head)
        self.assertNotIn("Z", row["lessons"])


class FormatHumanTests(SimpleTestCase):
    def _payload(self) -> dict:
        return {
            "total": 2,
            "by_category": {"refactor": 1, "other": 1},
            "by_status": {"open": 2},
            "duplicates": [{"canonical_fingerprint": "abc", "count": 2}],
            "top_open": [_entry_row(_fake_entry())],
            "recently_resolved": [],
        }

    def test_when_payload_given_then_marker_line_is_first(self) -> None:
        text = _format_human(self._payload())
        lines = text.split("\n")
        self.assertEqual(
            lines[0],
            '[DEBUG PAPER TRAIL: counts={"other": 1, "refactor": 1}]',
        )

    def test_when_payload_given_then_total_and_summary_present(self) -> None:
        text = _format_human(self._payload())
        self.assertIn("PaperTrail summary", text)
        self.assertIn("Total rows: 2", text)
        self.assertIn("Duplicate fingerprint groups: 1", text)

    def test_when_top_open_row_given_then_listed_with_id_and_title(self) -> None:
        text = _format_human(self._payload())
        self.assertIn("- #7 refactor open Tidy the bridge loop", text)
