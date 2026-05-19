"""TDD tests for print_open_paper_trail command."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import picker
from apps.paper_trail.tests_helpers import valid_paper_trail_defaults


def _make(**overrides) -> PaperTrailEntry:
    defaults = valid_paper_trail_defaults(
        category=PaperTrailEntry.CATEGORY_OTHER,
        title="to be printed",
        abstract=(
            "Given the print_open_paper_trail tests need a row, "
            "When _make() constructs one, "
            "Then it passes BDD validation."
        ),
    )
    defaults.update(overrides)
    return PaperTrailEntry.objects.create(**defaults)


class PrintOpenPaperTrailTests(TestCase):
    def test_emits_marker_with_zero_open(self) -> None:
        out = StringIO()
        call_command("print_open_paper_trail", stdout=out)
        self.assertIn("[PAPER TRAIL READ:", out.getvalue())
        self.assertIn("0 open", out.getvalue())

    def test_emits_marker_with_open_entries(self) -> None:
        _make(category=PaperTrailEntry.CATEGORY_CVE_UPGRADE, title="cve1")
        _make(category=PaperTrailEntry.CATEGORY_RUFF_SWEEP, title="ruff1")
        out = StringIO()
        call_command("print_open_paper_trail", stdout=out)
        text = out.getvalue()
        self.assertIn("[PAPER TRAIL READ:", text)
        self.assertIn("2 open", text)
        self.assertIn("1 cve_upgrade", text)
        self.assertIn("1 ruff_sweep", text)

    def test_breakdown_lists_all_16_categories(self) -> None:
        out = StringIO()
        call_command("print_open_paper_trail", stdout=out)
        for cat, _label in PaperTrailEntry.CATEGORY_CHOICES:
            self.assertIn(cat, out.getvalue())

    def test_count_by_category_keeps_unknown_database_values_visible(self) -> None:
        entry = _make()
        PaperTrailEntry.objects.filter(pk=entry.pk).update(category="unexpected")

        counts = picker.count_by_category()

        self.assertEqual(counts["unexpected"], 1)

    def test_drought_form_when_under_10(self) -> None:
        _make(title="only one entry")
        out = StringIO()
        call_command("print_open_paper_trail", stdout=out)
        self.assertIn("drought", out.getvalue())

    def test_picker_never_returns_same_canonical_work_twice(self) -> None:
        first = _make(title="Duplicate quota work", priority_score=50)
        duplicate = _make(
            category=PaperTrailEntry.CATEGORY_TOOLING_GAP,
            title="Duplicate quota work",
            priority_score=40,
        )
        unique = _make(title="Unique quota work", priority_score=30)

        picked = picker.pick_top_n(2)

        self.assertEqual([entry.pk for entry in picked], [first.pk, unique.pk])

    def test_picker_skips_open_copy_of_already_closed_work(self) -> None:
        closed = _make(title="Already handled quota work", priority_score=60)
        closed.status = PaperTrailEntry.STATUS_RESOLVED
        closed.resolved_at = closed.deferred_at
        closed.resolved_by = "test"
        closed.resolution_lessons = "Trap: duplicate closed work. Fix shape: skip it."
        closed.save()
        reopened_duplicate = _make(
            title="Already handled quota work",
            priority_score=50,
        )
        unique = _make(title="Fresh quota work", priority_score=40)

        picked = picker.pick_top_n(2)

        self.assertEqual([entry.pk for entry in picked], [unique.pk])
        self.assertNotIn(reopened_duplicate.pk, [entry.pk for entry in picked])
