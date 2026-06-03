"""SimpleTestCase coverage for the ``__str__`` methods in suggestions/models.py.

The 2026 hardening wrapped the sliced attributes in ``str(...)`` so a non-string
value (for example a lazy translation object, a UUID, or an integer carried on an
unsaved instance) renders instead of raising ``TypeError`` on ``value[:n]``. These
tests call each ``__str__`` as an unbound method against a lightweight stand-in
``self`` carrying NON-string attribute values, then pin the exact rendered string.

Calling the unbound method against a ``SimpleNamespace`` touches no Django model
machinery, no app registry save path, and no database — so this is hang-safe and
DB-free for the mutation gate. If the ``str(...)`` wrapper were removed, slicing a
non-string value would raise ``TypeError`` and these exact-value assertions would
fail, which is what kills the mutant.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.suggestions.models import (
    RankingChallenger,
    ScopePreset,
    Suggestion,
    WeightAdjustmentHistory,
)


class WeightAdjustmentHistoryStrTests(SimpleTestCase):
    def test_when_reason_is_non_string_then_str_renders_without_error(self) -> None:
        fake = SimpleNamespace(source="agent", reason=123456, created_at="2026-06-03")

        rendered = WeightAdjustmentHistory.__str__(fake)

        self.assertEqual(rendered, "[agent] 123456 at 2026-06-03")

    def test_when_reason_long_then_str_truncates_at_eighty_chars(self) -> None:
        fake = SimpleNamespace(source="auto", reason="x" * 200, created_at="t0")

        rendered = WeightAdjustmentHistory.__str__(fake)

        self.assertEqual(rendered, "[auto] " + "x" * 80 + " at t0")


class RankingChallengerStrTests(SimpleTestCase):
    def test_when_run_id_is_non_string_then_str_renders_without_error(self) -> None:
        fake = SimpleNamespace(run_id=987654321012345678, status="running")

        rendered = RankingChallenger.__str__(fake)

        self.assertEqual(rendered, "Challenger 9876543210123456 [running]")

    def test_when_run_id_short_then_str_renders_full_id(self) -> None:
        fake = SimpleNamespace(run_id="abc123", status="done")

        rendered = RankingChallenger.__str__(fake)

        self.assertEqual(rendered, "Challenger abc123 [done]")


class ScopePresetStrTests(SimpleTestCase):
    def test_when_name_is_non_string_then_str_returns_string(self) -> None:
        fake = SimpleNamespace(name=42)

        rendered = ScopePreset.__str__(fake)

        self.assertEqual(rendered, "42")


class SuggestionStrTests(SimpleTestCase):
    def test_when_title_and_anchor_non_string_then_str_renders_without_error(
        self,
    ) -> None:
        fake = SimpleNamespace(
            status="pending",
            destination_title=2026,
            anchor_phrase=99,
            score_final=0.5,
        )

        rendered = Suggestion.__str__(fake)

        self.assertEqual(rendered, "[pending] 2026 ← '99' (score=0.500)")

    def test_when_title_long_then_str_truncates_title_at_fifty_chars(self) -> None:
        fake = SimpleNamespace(
            status="approved",
            destination_title="d" * 100,
            anchor_phrase="anchor",
            score_final=1.0,
        )

        rendered = Suggestion.__str__(fake)

        self.assertEqual(
            rendered,
            "[approved] " + "d" * 50 + " ← 'anchor' (score=1.000)",
        )

    def test_when_anchor_long_then_str_truncates_anchor_at_thirty_chars(self) -> None:
        # Pins the ``anchor_phrase[:30]`` slice boundary: an off-by-one mutant
        # (``[:29]`` or ``[:31]``) renders a different length and this exact
        # assertion fails. The title is kept short so only the anchor slice is
        # under test.
        fake = SimpleNamespace(
            status="pending",
            destination_title="dest",
            anchor_phrase="a" * 90,
            score_final=0.25,
        )

        rendered = Suggestion.__str__(fake)

        self.assertEqual(
            rendered,
            "[pending] dest ← '" + "a" * 30 + "' (score=0.250)",
        )
