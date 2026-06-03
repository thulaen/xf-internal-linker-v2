"""DB-free tests for the session-gate marker helpers.

The full ``session_gate`` view reads several tables; those queries are
covered by integration tests. Here we lock the pure string-building
helpers that decide the exact wording of the markers a hook later
parses. ``_format_picks_segment`` is tested only on the
already-have-three branch so it never reaches the drought DB write;
that write is forced through a mocked ``get_or_create`` instead.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.api import session_gate_view as sg


def _issue(issue_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=issue_id)


class NowUtcZTests(SimpleTestCase):
    def test_when_called_then_matches_iso_z_format(self) -> None:
        value = sg._now_utc_z()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_when_called_then_ends_with_z(self) -> None:
        self.assertTrue(sg._now_utc_z().endswith("Z"))


class FormatPicksSegmentFullTests(SimpleTestCase):
    """Three-or-more issues: no drought, no DB, exact id wording."""

    def test_when_three_issues_with_prefix_then_prefixed_ids(self) -> None:
        seg = sg._format_picks_segment(
            sg.AutoIssue.SOURCE_GLITCHTIP,
            "g",
            [_issue(11), _issue(22), _issue(33)],
            agent_pool=[],
            agent_used_ids=set(),
        )
        self.assertEqual(seg, "g: #11, #22, #33")

    def test_when_three_issues_no_prefix_then_bare_ids(self) -> None:
        seg = sg._format_picks_segment(
            sg.AutoIssue.SOURCE_AGENT,
            "",
            [_issue(1), _issue(2), _issue(3)],
            agent_pool=[],
            agent_used_ids=set(),
        )
        self.assertEqual(seg, "#1, #2, #3")

    def test_when_more_than_three_then_only_first_three_used(self) -> None:
        seg = sg._format_picks_segment(
            sg.AutoIssue.SOURCE_AGENT,
            "",
            [_issue(1), _issue(2), _issue(3), _issue(4)],
            agent_pool=[],
            agent_used_ids=set(),
        )
        self.assertEqual(seg, "#1, #2, #3")


class FormatPicksSegmentDroughtTests(SimpleTestCase):
    """Fewer than three issues: agent substitution + drought logging."""

    def test_when_zero_issues_then_three_agent_subs_with_drought_id(self) -> None:
        agent_pool = [_issue(91), _issue(92), _issue(93), _issue(94)]
        with patch.object(sg, "_log_drought_issue", return_value=777):
            seg = sg._format_picks_segment(
                sg.AutoIssue.SOURCE_TEMPO,
                "t",
                [],
                agent_pool=agent_pool,
                agent_used_ids=set(),
            )
        self.assertEqual(
            seg, "t: 0 found + 3 from agent: #91, #92, #93 (drought logged: #777)"
        )

    def test_when_substituting_then_used_ids_are_tracked(self) -> None:
        used: set[int] = set()
        with patch.object(sg, "_log_drought_issue", return_value=1):
            sg._format_picks_segment(
                sg.AutoIssue.SOURCE_TEMPO,
                "t",
                [],
                agent_pool=[_issue(5), _issue(6), _issue(7)],
                agent_used_ids=used,
            )
        self.assertEqual(used, {5, 6, 7})


class SourceOrderTests(SimpleTestCase):
    def test_when_source_order_then_exactly_ten_entries(self) -> None:
        self.assertEqual(len(sg._SOURCE_ORDER), 10)

    def test_when_source_order_then_first_is_agent_no_prefix(self) -> None:
        self.assertEqual(sg._SOURCE_ORDER[0], (sg.AutoIssue.SOURCE_AGENT, ""))

    def test_when_pt_category_order_then_sixteen_entries(self) -> None:
        self.assertEqual(len(sg._PT_CATEGORY_ORDER), 16)
