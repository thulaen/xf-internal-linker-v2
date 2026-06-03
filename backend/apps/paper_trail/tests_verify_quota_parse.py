"""No-database SimpleTestCase coverage for verify_paper_trail_quota helpers.

The command body needs the PaperTrailEntry table (covered by the DB-backed
``tests_verify_quota_command.py``). The timestamp parser ``_parse_resolved_after``
and the per-session-type quota table are pure Python and need no database, so
they are pinned here with exact-value asserts. This catches a mutated format
string or quota literal without spinning up a test DB.
"""

from __future__ import annotations

from datetime import datetime, timezone

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.paper_trail.management.commands.verify_paper_trail_quota import (
    _REQUIRED_QUOTA,
    _SESSION_TYPE_CHOICES,
    _SESSION_TYPE_QUOTAS,
    _parse_resolved_after,
)


class ParseResolvedAfterTests(SimpleTestCase):
    def test_when_none_given_then_returns_none(self) -> None:
        self.assertIsNone(_parse_resolved_after(None))

    def test_when_empty_string_given_then_returns_none(self) -> None:
        self.assertIsNone(_parse_resolved_after(""))

    def test_when_whitespace_only_given_then_command_error(self) -> None:
        # A whitespace string is truthy, so it is stripped to "" and then
        # fails every format, raising CommandError (not None).
        with self.assertRaisesMessage(CommandError, "Could not parse"):
            _parse_resolved_after("   ")

    def test_when_space_separated_given_then_utc_datetime(self) -> None:
        self.assertEqual(
            _parse_resolved_after("2026-05-28 14:30"),
            datetime(2026, 5, 28, 14, 30, tzinfo=timezone.utc),
        )

    def test_when_iso_8601_given_then_utc_datetime(self) -> None:
        self.assertEqual(
            _parse_resolved_after("2026-05-28T14:30:45"),
            datetime(2026, 5, 28, 14, 30, 45, tzinfo=timezone.utc),
        )

    def test_when_date_only_given_then_midnight_utc(self) -> None:
        self.assertEqual(
            _parse_resolved_after("2026-05-28"),
            datetime(2026, 5, 28, 0, 0, 0, tzinfo=timezone.utc),
        )

    def test_when_unparseable_given_then_command_error(self) -> None:
        with self.assertRaisesMessage(CommandError, "Could not parse"):
            _parse_resolved_after("not-a-date")


class SessionTypeQuotaTableTests(SimpleTestCase):
    def test_when_session_types_given_then_quotas_are_exact(self) -> None:
        self.assertEqual(
            _SESSION_TYPE_QUOTAS,
            {
                "docs": 0,
                "reconciliation": 3,
                "infrastructure": 5,
                "feature": 10,
            },
        )

    def test_each_quota_value_is_the_exact_number(self) -> None:
        # Pin each value individually so a single-key +1/-1 mutant on a
        # changed dict line dies even if the whole-dict compare is mutated.
        self.assertEqual(_SESSION_TYPE_QUOTAS["docs"], 0)
        self.assertEqual(_SESSION_TYPE_QUOTAS["reconciliation"], 3)
        self.assertEqual(_SESSION_TYPE_QUOTAS["infrastructure"], 5)
        self.assertEqual(_SESSION_TYPE_QUOTAS["feature"], 10)

    def test_required_quota_default_is_ten(self) -> None:
        # The fallback passed to ``.get(session_type, _REQUIRED_QUOTA)`` and the
        # default ``limit`` of ``_hard_mode_ids``. Pin it so a +1/-1 literal
        # mutant on the changed constant line is killed.
        self.assertEqual(_REQUIRED_QUOTA, 10)

    def test_session_type_choices_tuple_is_exact(self) -> None:
        # Each string literal and the tuple membership are pinned so a mutmut
        # string-wrap ("XXdocsXX") or a dropped/renamed choice on the changed
        # line is caught without a database.
        self.assertEqual(
            _SESSION_TYPE_CHOICES,
            ("docs", "infrastructure", "reconciliation", "feature"),
        )

    def test_choices_and_quota_keys_match_exactly(self) -> None:
        # The choices a user may pass and the quota table keys must stay in
        # sync; a renamed literal on one changed line but not the other is
        # caught by this set-equality assert.
        self.assertEqual(set(_SESSION_TYPE_CHOICES), set(_SESSION_TYPE_QUOTAS))
