"""TDD tests for resolve_paper_trail command."""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.paper_trail.models import PaperTrailEntry


def _make(**overrides) -> PaperTrailEntry:
    defaults = {
        "category": PaperTrailEntry.CATEGORY_OTHER,
        "title": "to be resolved",
        "abstract": (
            "Given the resolve_paper_trail tests need a row, "
            "When _make() constructs one, "
            "Then it passes BDD validation."
        ),
        "deferred_by": "test",
        "risk_on_inaction": "Test only.",
        "acceptance_criteria": "Test passes.",
    }
    defaults.update(overrides)
    return PaperTrailEntry.objects.create(**defaults)


class ResolvePaperTrailTests(TestCase):
    def test_resolves_with_two_part_lesson(self) -> None:
        entry = _make()
        call_command(
            "resolve_paper_trail",
            "--id", str(entry.id),
            "--lessons-learned", "Trap: was tricky. Fix shape: cleaned up.",
            "--agent", "claude",
            stdout=StringIO(),
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, PaperTrailEntry.STATUS_RESOLVED)
        self.assertEqual(entry.resolved_by, "claude")
        self.assertIsNotNone(entry.resolved_at)

    def test_rejects_lesson_missing_trap(self) -> None:
        entry = _make()
        with self.assertRaises(CommandError):
            call_command(
                "resolve_paper_trail",
                "--id", str(entry.id),
                "--lessons-learned", "Fix shape: only one part.",
                stdout=StringIO(),
            )

    def test_rejects_lesson_missing_fix_shape(self) -> None:
        entry = _make()
        with self.assertRaises(CommandError):
            call_command(
                "resolve_paper_trail",
                "--id", str(entry.id),
                "--lessons-learned", "Trap: only one part.",
                stdout=StringIO(),
            )

    def test_resolves_multiple_in_one_call(self) -> None:
        a = _make(title="first")
        b = _make(title="second")
        out = StringIO()
        call_command(
            "resolve_paper_trail",
            "--id", str(a.id),
            "--id", str(b.id),
            "--lessons-learned", "Trap: bulk. Fix shape: in one call.",
            stdout=out,
        )
        self.assertIn("RESOLVED:", out.getvalue())
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.status, PaperTrailEntry.STATUS_RESOLVED)
        self.assertEqual(b.status, PaperTrailEntry.STATUS_RESOLVED)
